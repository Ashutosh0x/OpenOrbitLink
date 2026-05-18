/**
 * FreeSat Codec2 JNI Bridge
 *
 * Provides Java/Kotlin interface to libcodec2 for Android.
 * Enables 700bps voice encoding/decoding on-device.
 *
 * Usage from Kotlin:
 *   val codec = Codec2Native()
 *   codec.init(Codec2Native.MODE_700C)
 *   val encoded = codec.encode(pcmSamples)
 *   val decoded = codec.decode(encoded)
 *   codec.destroy()
 */

#include <jni.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <android/log.h>

/* Codec2 header — will be available when codec2 source is compiled */
/* #include "codec2.h" */

#define LOG_TAG "FreeSat-Codec2"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

/* Mode constants matching codec2.h */
#define CODEC2_MODE_700C  8
#define CODEC2_MODE_1200  5
#define CODEC2_MODE_1300  4

/* Samples per frame at 8kHz for 40ms frames */
#define SAMPLES_PER_FRAME_700C 320
#define BITS_PER_FRAME_700C    28

/**
 * Codec2 state stored as a long pointer in Java
 */
typedef struct {
    void *codec2_state;
    int mode;
    int samples_per_frame;
    int bits_per_frame;
    int bytes_per_frame;
} FreeSatCodecState;

/*
 * Initialize Codec2 with specified mode
 */
JNIEXPORT jlong JNICALL
Java_org_freesat_codec_Codec2Native_nativeInit(JNIEnv *env, jobject thiz, jint mode) {
    FreeSatCodecState *state = (FreeSatCodecState *)malloc(sizeof(FreeSatCodecState));
    if (!state) {
        LOGE("Failed to allocate codec state");
        return 0;
    }

    state->mode = mode;

    /* TODO: Initialize actual codec2 when library is compiled
     * state->codec2_state = codec2_create(mode);
     * state->samples_per_frame = codec2_samples_per_frame(state->codec2_state);
     * state->bits_per_frame = codec2_bits_per_frame(state->codec2_state);
     */

    /* Default values for 700C mode */
    state->samples_per_frame = SAMPLES_PER_FRAME_700C;
    state->bits_per_frame = BITS_PER_FRAME_700C;
    state->bytes_per_frame = (BITS_PER_FRAME_700C + 7) / 8;
    state->codec2_state = NULL;

    LOGI("Codec2 initialized: mode=%d, samples=%d, bits=%d",
         mode, state->samples_per_frame, state->bits_per_frame);

    return (jlong)(intptr_t)state;
}

/*
 * Encode PCM samples to Codec2 frame
 */
JNIEXPORT jbyteArray JNICALL
Java_org_freesat_codec_Codec2Native_nativeEncode(JNIEnv *env, jobject thiz,
                                                  jlong handle, jshortArray pcm_samples) {
    FreeSatCodecState *state = (FreeSatCodecState *)(intptr_t)handle;
    if (!state) return NULL;

    jsize len = (*env)->GetArrayLength(env, pcm_samples);
    if (len != state->samples_per_frame) {
        LOGE("Expected %d samples, got %d", state->samples_per_frame, len);
        return NULL;
    }

    jshort *samples = (*env)->GetShortArrayElements(env, pcm_samples, NULL);

    /* Allocate output */
    jbyteArray result = (*env)->NewByteArray(env, state->bytes_per_frame);
    jbyte *output = (*env)->GetByteArrayElements(env, result, NULL);

    /* TODO: Call codec2_encode when library available
     * codec2_encode(state->codec2_state, (unsigned char *)output, samples);
     */

    /* Placeholder: simple energy-based encoding */
    memset(output, 0, state->bytes_per_frame);
    double energy = 0;
    for (int i = 0; i < len; i++) {
        energy += (double)samples[i] * samples[i];
    }
    energy = energy / len;
    output[0] = (jbyte)((int)(energy / 1000000.0) & 0xFF);

    (*env)->ReleaseShortArrayElements(env, pcm_samples, samples, 0);
    (*env)->ReleaseByteArrayElements(env, result, output, 0);

    return result;
}

/*
 * Decode Codec2 frame to PCM samples
 */
JNIEXPORT jshortArray JNICALL
Java_org_freesat_codec_Codec2Native_nativeDecode(JNIEnv *env, jobject thiz,
                                                  jlong handle, jbyteArray encoded) {
    FreeSatCodecState *state = (FreeSatCodecState *)(intptr_t)handle;
    if (!state) return NULL;

    jbyte *input = (*env)->GetByteArrayElements(env, encoded, NULL);

    jshortArray result = (*env)->NewShortArray(env, state->samples_per_frame);
    jshort *output = (*env)->GetShortArrayElements(env, result, NULL);

    /* TODO: Call codec2_decode when library available
     * codec2_decode(state->codec2_state, output, (unsigned char *)input);
     */

    /* Placeholder: generate silence */
    memset(output, 0, state->samples_per_frame * sizeof(jshort));

    (*env)->ReleaseByteArrayElements(env, encoded, input, 0);
    (*env)->ReleaseShortArrayElements(env, result, output, 0);

    return result;
}

/*
 * Clean up
 */
JNIEXPORT void JNICALL
Java_org_freesat_codec_Codec2Native_nativeDestroy(JNIEnv *env, jobject thiz, jlong handle) {
    FreeSatCodecState *state = (FreeSatCodecState *)(intptr_t)handle;
    if (state) {
        /* TODO: codec2_destroy(state->codec2_state); */
        free(state);
        LOGI("Codec2 destroyed");
    }
}

/*
 * Get samples per frame for current mode
 */
JNIEXPORT jint JNICALL
Java_org_freesat_codec_Codec2Native_nativeGetSamplesPerFrame(JNIEnv *env, jobject thiz, jlong handle) {
    FreeSatCodecState *state = (FreeSatCodecState *)(intptr_t)handle;
    return state ? state->samples_per_frame : 0;
}
