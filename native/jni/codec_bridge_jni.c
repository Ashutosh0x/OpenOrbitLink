/**
 * OpenOrbitLink — Unified Codec Bridge JNI
 *
 * Single JNI entry point for the entire voice pipeline: codec abstraction,
 * adaptive mode selection, neural enhancement, chunking, and airtime
 * management. Replaces the old single-purpose codec2_jni.c.
 *
 * JNI Method Mapping:
 *   Kotlin class: org.freesat.codec.VoiceCodecManager
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <jni.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef __ANDROID__
#include <android/log.h>
#define LOG_TAG "OOL-Voice"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#else
#include <stdio.h>
#define LOGI(...) printf(__VA_ARGS__)
#define LOGW(...) fprintf(stderr, __VA_ARGS__)
#define LOGE(...) fprintf(stderr, __VA_ARGS__)
#endif

#include "codec_interface.h"
#include "audio_frame.h"
#include "voice_chunker.h"
#include "airtime_calculator.h"
#include "packet_loss_recovery.h"

/* ── Pipeline State ──────────────────────────────────────────────────────── */

typedef struct {
    OolCodecInstance    *codec;
    OolCodecMode         mode;
    OolPlcState          plc;
    OolDutyCycleTracker  duty;
    OolLoraParams        lora;
    bool                 neural_enabled;
    bool                 initialized;
    /* Metrics */
    uint32_t             encode_count;
    uint32_t             decode_count;
    float                total_encode_ms;
    float                total_decode_ms;
} VoicePipeline;

/* ── External codec factory (defined in codec2_wrapper.c) ────────────────── */

extern OolCodecInstance* ool_codec2_create(OolCodecMode mode, const char *model_path);

/* ── JNI: Create Pipeline ────────────────────────────────────────────────── */

JNIEXPORT jlong JNICALL
Java_org_freesat_codec_VoiceCodecManager_nativeCreatePipeline(
    JNIEnv *env, jobject thiz, jint mode, jstring model_path)
{
    VoicePipeline *pipeline = (VoicePipeline *)calloc(1, sizeof(VoicePipeline));
    if (!pipeline) {
        LOGE("Failed to allocate voice pipeline");
        return 0;
    }

    OolCodecMode codec_mode = (OolCodecMode)mode;

    /* Create codec instance */
    if (ool_mode_is_codec2(codec_mode)) {
        pipeline->codec = ool_codec2_create(codec_mode, NULL);
    }
    /* TODO: Add Lyra codec creation when TFLite is integrated */

    if (!pipeline->codec) {
        LOGW("Codec creation failed for mode 0x%02X, pipeline will operate in passthrough", mode);
    }

    pipeline->mode = codec_mode;

    /* Initialize PLC */
    const OolCodecDescriptor *desc = pipeline->codec ?
        ool_codec_descriptor(pipeline->codec) : NULL;
    int frame_samples = desc ? desc->frame_samples : 320;
    ool_plc_init(&pipeline->plc, frame_samples, OOL_PLC_REPEAT_DECAY);

    /* Initialize duty cycle tracker (1% ISM) */
    ool_duty_init(&pipeline->duty, 1, 0);  /* Epoch will be set properly */

    /* Initialize LoRa parameters */
    pipeline->lora = ool_lora_defaults();

    pipeline->initialized = true;
    LOGI("Voice pipeline created: mode=0x%02X, samples/frame=%d",
         mode, frame_samples);

    return (jlong)(intptr_t)pipeline;
}

/* ── JNI: Encode ─────────────────────────────────────────────────────────── */

JNIEXPORT jbyteArray JNICALL
Java_org_freesat_codec_VoiceCodecManager_nativeEncode(
    JNIEnv *env, jobject thiz, jlong handle, jshortArray pcm_samples)
{
    VoicePipeline *p = (VoicePipeline *)(intptr_t)handle;
    if (!p || !p->initialized || !p->codec) return NULL;

    const OolCodecDescriptor *desc = ool_codec_descriptor(p->codec);
    jsize len = (*env)->GetArrayLength(env, pcm_samples);

    if (len != desc->frame_samples) {
        LOGE("Expected %d samples, got %d", desc->frame_samples, (int)len);
        return NULL;
    }

    jshort *pcm = (*env)->GetShortArrayElements(env, pcm_samples, NULL);

    uint8_t encoded[OOL_MAX_ENCODED_FRAME];
    int encoded_len = 0;

    OolError err = ool_codec_encode(p->codec, pcm, len, encoded, &encoded_len);
    (*env)->ReleaseShortArrayElements(env, pcm_samples, pcm, 0);

    if (err != OOL_OK) {
        LOGE("Encode failed: %d", err);
        return NULL;
    }

    jbyteArray result = (*env)->NewByteArray(env, encoded_len);
    (*env)->SetByteArrayRegion(env, result, 0, encoded_len, (jbyte *)encoded);

    p->encode_count++;
    return result;
}

/* ── JNI: Decode ─────────────────────────────────────────────────────────── */

JNIEXPORT jshortArray JNICALL
Java_org_freesat_codec_VoiceCodecManager_nativeDecode(
    JNIEnv *env, jobject thiz, jlong handle, jbyteArray encoded_data)
{
    VoicePipeline *p = (VoicePipeline *)(intptr_t)handle;
    if (!p || !p->initialized || !p->codec) return NULL;

    const OolCodecDescriptor *desc = ool_codec_descriptor(p->codec);

    jsize data_len = (*env)->GetArrayLength(env, encoded_data);
    jbyte *data = (*env)->GetByteArrayElements(env, encoded_data, NULL);

    int16_t pcm[OOL_MAX_PCM_FRAME];
    int num_samples = 0;

    OolError err = ool_codec_decode(p->codec, (uint8_t *)data, data_len,
                                     pcm, &num_samples);
    (*env)->ReleaseByteArrayElements(env, encoded_data, data, 0);

    if (err != OOL_OK) {
        LOGE("Decode failed: %d", err);
        return NULL;
    }

    /* Feed good frame to PLC */
    ool_plc_good_frame(&p->plc, pcm, num_samples);

    jshortArray result = (*env)->NewShortArray(env, num_samples);
    (*env)->SetShortArrayRegion(env, result, 0, num_samples, pcm);

    p->decode_count++;
    return result;
}

/* ── JNI: Conceal Lost Frame ─────────────────────────────────────────────── */

JNIEXPORT jshortArray JNICALL
Java_org_freesat_codec_VoiceCodecManager_nativeConcealFrame(
    JNIEnv *env, jobject thiz, jlong handle)
{
    VoicePipeline *p = (VoicePipeline *)(intptr_t)handle;
    if (!p || !p->initialized) return NULL;

    int16_t pcm[OOL_MAX_PCM_FRAME];
    int num_samples = 0;

    if (!ool_plc_conceal_frame(&p->plc, pcm, &num_samples)) {
        return NULL;
    }

    jshortArray result = (*env)->NewShortArray(env, num_samples);
    (*env)->SetShortArrayRegion(env, result, 0, num_samples, pcm);
    return result;
}

/* ── JNI: Set Mode ───────────────────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_org_freesat_codec_VoiceCodecManager_nativeSetMode(
    JNIEnv *env, jobject thiz, jlong handle, jint new_mode)
{
    VoicePipeline *p = (VoicePipeline *)(intptr_t)handle;
    if (!p) return JNI_FALSE;

    OolCodecMode mode = (OolCodecMode)new_mode;
    if (mode == p->mode && p->codec) return JNI_TRUE;

    /* Destroy existing codec */
    if (p->codec) {
        ool_codec_destroy(p->codec);
        free(p->codec);
        p->codec = NULL;
    }

    /* Create new codec */
    if (ool_mode_is_codec2(mode)) {
        p->codec = ool_codec2_create(mode, NULL);
    }

    if (p->codec) {
        p->mode = mode;
        const OolCodecDescriptor *desc = ool_codec_descriptor(p->codec);
        ool_plc_init(&p->plc, desc->frame_samples, OOL_PLC_REPEAT_DECAY);
        LOGI("Mode switched to 0x%02X (%s)", mode, desc->name);
        return JNI_TRUE;
    }

    LOGE("Failed to create codec for mode 0x%02X", new_mode);
    return JNI_FALSE;
}

/* ── JNI: Get Metrics ────────────────────────────────────────────────────── */

JNIEXPORT jstring JNICALL
Java_org_freesat_codec_VoiceCodecManager_nativeGetMetrics(
    JNIEnv *env, jobject thiz, jlong handle)
{
    VoicePipeline *p = (VoicePipeline *)(intptr_t)handle;
    if (!p) return (*env)->NewStringUTF(env, "{}");

    const OolCodecDescriptor *desc = p->codec ?
        ool_codec_descriptor(p->codec) : NULL;

    char buf[512];
    snprintf(buf, sizeof(buf),
        "{\"mode\":\"0x%02X\",\"name\":\"%s\",\"bitrate\":%d,"
        "\"encodes\":%u,\"decodes\":%u,"
        "\"plc_loss_rate\":%.4f,\"plc_concealed\":%u,"
        "\"duty_remaining_s\":%.1f,\"duty_used_s\":%.1f,"
        "\"neural_enabled\":%s}",
        p->mode,
        desc ? desc->name : "none",
        desc ? desc->bitrate_bps : 0,
        p->encode_count, p->decode_count,
        ool_plc_loss_rate(&p->plc),
        p->plc.concealed_frames,
        ool_duty_remaining(&p->duty),
        p->duty.used_tx_seconds,
        p->neural_enabled ? "true" : "false");

    return (*env)->NewStringUTF(env, buf);
}

/* ── JNI: Calculate Airtime ──────────────────────────────────────────────── */

JNIEXPORT jfloat JNICALL
Java_org_freesat_codec_VoiceCodecManager_nativeCalculateAirtime(
    JNIEnv *env, jobject thiz, jlong handle,
    jint num_chunks, jint chunk_bytes)
{
    VoicePipeline *p = (VoicePipeline *)(intptr_t)handle;
    if (!p) return 0.0f;

    return ool_voice_airtime_estimate(&p->lora, num_chunks, chunk_bytes, 100.0f);
}

/* ── JNI: Check Duty Cycle Budget ────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_org_freesat_codec_VoiceCodecManager_nativeCanTransmit(
    JNIEnv *env, jobject thiz, jlong handle, jfloat tx_seconds)
{
    VoicePipeline *p = (VoicePipeline *)(intptr_t)handle;
    if (!p) return JNI_FALSE;

    return ool_duty_can_transmit(&p->duty, tx_seconds, 0) ?
           JNI_TRUE : JNI_FALSE;
}

/* ── JNI: Get Descriptor ─────────────────────────────────────────────────── */

JNIEXPORT jint JNICALL
Java_org_freesat_codec_VoiceCodecManager_nativeGetFrameSamples(
    JNIEnv *env, jobject thiz, jlong handle)
{
    VoicePipeline *p = (VoicePipeline *)(intptr_t)handle;
    if (!p || !p->codec) return 320;
    const OolCodecDescriptor *desc = ool_codec_descriptor(p->codec);
    return desc ? desc->frame_samples : 320;
}

JNIEXPORT jint JNICALL
Java_org_freesat_codec_VoiceCodecManager_nativeGetBitrate(
    JNIEnv *env, jobject thiz, jlong handle)
{
    VoicePipeline *p = (VoicePipeline *)(intptr_t)handle;
    if (!p || !p->codec) return 700;
    const OolCodecDescriptor *desc = ool_codec_descriptor(p->codec);
    return desc ? desc->bitrate_bps : 700;
}

/* ── JNI: Destroy ────────────────────────────────────────────────────────── */

JNIEXPORT void JNICALL
Java_org_freesat_codec_VoiceCodecManager_nativeDestroyPipeline(
    JNIEnv *env, jobject thiz, jlong handle)
{
    VoicePipeline *p = (VoicePipeline *)(intptr_t)handle;
    if (!p) return;

    if (p->codec) {
        ool_codec_destroy(p->codec);
        free(p->codec);
    }
    free(p);
    LOGI("Voice pipeline destroyed");
}
