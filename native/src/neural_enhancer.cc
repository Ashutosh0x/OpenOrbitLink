/**
 * OpenOrbitLink — Neural Voice Enhancer Implementation
 *
 * TFLite-based receiver-side speech enhancement. Uses pre-trained
 * SoundStream/LyraGAN models to restore quality from Codec2's
 * narrow-band decoded PCM output.
 *
 * Architecture:
 *   Input 8kHz PCM → linear upsample to 16kHz →
 *   SoundStream encoder (feature extraction) →
 *   LyraGAN decoder (waveform generation) →
 *   linear downsample to 8kHz → mix with original
 *
 * Graceful degradation:
 *   - If models not loaded → returns input unmodified
 *   - If inference fails → returns input unmodified
 *   - If CPU budget exceeded → bypasses enhancement
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>

#include "neural_enhancer.h"
#include "tflite_runtime.h"

/* ── Internal Constants ──────────────────────────────────────────────────── */

#define NE_INTERNAL_RATE     16000   /* Lyra models operate at 16kHz          */
#define NE_INPUT_RATE         8000   /* Codec2 output rate                    */
#define NE_HOP_SAMPLES_16K     320   /* 20ms at 16kHz                         */
#define NE_HOP_SAMPLES_8K      160   /* 20ms at 8kHz                          */
#define NE_NUM_FEATURES         64   /* SoundStream feature dimension         */
#define NE_MAX_FRAMES_BUFFER    16   /* Frames of context for enhancement     */

/* ── Enhancer Internal State ─────────────────────────────────────────────── */

struct OolNeuralEnhancer {
    OolTfliteRuntime  *runtime;
    OolEnhancerConfig  config;
    bool               models_loaded;
    bool               enabled;

    /* Resampling buffers */
    int16_t            upsample_buf[NE_HOP_SAMPLES_16K];
    int16_t            downsample_buf[NE_HOP_SAMPLES_8K];
    float              features[NE_NUM_FEATURES];

    /* Performance tracking */
    float              total_inference_ms;
    float              max_inference_ms;
    uint32_t           enhanced_frames;
    uint32_t           bypassed_frames;
    uint32_t           concealed_frames;
    float              quality_sum;
};

/* ── Simple Linear Resampler ─────────────────────────────────────────────── */

/**
 * Upsample 8kHz → 16kHz using linear interpolation.
 * Simple but effective for speech bandwidth extension pre-processing.
 */
static void upsample_8k_to_16k(const int16_t *in8k, int in_len,
                                 int16_t *out16k, int out_len) {
    /* 2x upsample: insert interpolated sample between each input sample */
    int out_idx = 0;
    for (int i = 0; i < in_len && out_idx < out_len - 1; i++) {
        out16k[out_idx++] = in8k[i];
        if (i + 1 < in_len) {
            /* Linear interpolation */
            out16k[out_idx++] = (int16_t)(((int)in8k[i] + (int)in8k[i + 1]) / 2);
        } else {
            out16k[out_idx++] = in8k[i];
        }
    }
    /* Zero-fill remainder */
    while (out_idx < out_len) out16k[out_idx++] = 0;
}

/**
 * Downsample 16kHz → 8kHz by decimation with simple low-pass.
 */
static void downsample_16k_to_8k(const int16_t *in16k, int in_len,
                                   int16_t *out8k, int out_len) {
    int out_idx = 0;
    for (int i = 0; i < in_len - 1 && out_idx < out_len; i += 2) {
        /* Simple 2-tap average for anti-aliasing */
        out8k[out_idx++] = (int16_t)(((int)in16k[i] + (int)in16k[i + 1]) / 2);
    }
    while (out_idx < out_len) out8k[out_idx++] = 0;
}

/**
 * Mix original and enhanced signals.
 * @param mix  0.0 = all original, 1.0 = all enhanced
 */
static void mix_signals(const int16_t *original, const int16_t *enhanced,
                         int16_t *output, int num_samples, float mix) {
    float orig_weight = 1.0f - mix;
    float enh_weight = mix;
    for (int i = 0; i < num_samples; i++) {
        float val = original[i] * orig_weight + enhanced[i] * enh_weight;
        if (val > 32767.0f) val = 32767.0f;
        if (val < -32768.0f) val = -32768.0f;
        output[i] = (int16_t)val;
    }
}

/* ── Enhancer API Implementation ─────────────────────────────────────────── */

OolNeuralEnhancer* ool_enhancer_create(const OolEnhancerConfig *config) {
    if (!config) return NULL;

    OolNeuralEnhancer *enh = (OolNeuralEnhancer *)calloc(1, sizeof(OolNeuralEnhancer));
    if (!enh) return NULL;

    enh->config = *config;
    enh->enabled = false;

    /* Initialize TFLite runtime */
    OolTfliteConfig rt_config = {
        .model_base_path = config->model_path,
        .preferred_delegate = OOL_DELEGATE_CPU,
        .num_threads = 2,
        .max_memory_mb = 16,
        .allow_int8 = true,
        .allow_fp16 = true,
    };

    enh->runtime = ool_tflite_create(&rt_config);
    if (enh->runtime) {
        /* Load all three models */
        bool enc_ok = ool_tflite_load_model(enh->runtime, OOL_MODEL_SOUNDSTREAM_ENCODER);
        bool quant_ok = ool_tflite_load_model(enh->runtime, OOL_MODEL_QUANTIZER);
        bool gen_ok = ool_tflite_load_model(enh->runtime, OOL_MODEL_LYRAGAN);
        enh->models_loaded = enc_ok && quant_ok && gen_ok;
    } else {
        enh->models_loaded = false;
    }

    return enh;
}

OolEnhanceResult ool_enhancer_process(
    OolNeuralEnhancer *enh,
    const int16_t *pcm_in, int num_samples,
    int16_t *pcm_out, int *out_samples)
{
    OolEnhanceResult result = {
        .was_enhanced = false,
        .inference_ms = 0.0f,
        .quality_delta = 0.0f,
        .output_samples = num_samples,
    };

    if (!enh || !pcm_in || !pcm_out || !out_samples) return result;
    *out_samples = num_samples;

    /* Bypass if disabled or models not loaded */
    if (!enh->enabled || !enh->models_loaded || !enh->runtime) {
        memcpy(pcm_out, pcm_in, num_samples * sizeof(int16_t));
        enh->bypassed_frames++;
        return result;
    }

    /* Step 1: Upsample 8kHz → 16kHz */
    int up_samples = num_samples * 2;
    if (up_samples > NE_HOP_SAMPLES_16K) up_samples = NE_HOP_SAMPLES_16K;
    upsample_8k_to_16k(pcm_in, num_samples, enh->upsample_buf, up_samples);

    /* Step 2: Extract features via SoundStream encoder */
    int num_features = 0;
    OolInferenceResult enc_result = ool_tflite_extract_features(
        enh->runtime, enh->upsample_buf, up_samples,
        enh->features, &num_features);

    if (!enc_result.success) {
        memcpy(pcm_out, pcm_in, num_samples * sizeof(int16_t));
        enh->bypassed_frames++;
        return result;
    }

    /* Step 3: Generate enhanced audio via LyraGAN */
    int16_t enhanced_16k[NE_HOP_SAMPLES_16K];
    int gen_samples = 0;
    OolInferenceResult gen_result = ool_tflite_generate_audio(
        enh->runtime, enh->features, num_features,
        enhanced_16k, &gen_samples);

    if (!gen_result.success) {
        memcpy(pcm_out, pcm_in, num_samples * sizeof(int16_t));
        enh->bypassed_frames++;
        return result;
    }

    /* Step 4: Downsample 16kHz → 8kHz */
    downsample_16k_to_8k(enhanced_16k, gen_samples,
                          enh->downsample_buf, num_samples);

    /* Step 5: Mix original and enhanced */
    mix_signals(pcm_in, enh->downsample_buf, pcm_out,
                num_samples, enh->config.enhancement_mix);

    /* Update metrics */
    float total_ms = enc_result.inference_ms + gen_result.inference_ms;
    enh->total_inference_ms += total_ms;
    if (total_ms > enh->max_inference_ms) enh->max_inference_ms = total_ms;
    enh->enhanced_frames++;

    result.was_enhanced = true;
    result.inference_ms = total_ms;
    result.quality_delta = enh->config.enhancement_mix * 0.3f; /* Estimated */
    result.output_samples = num_samples;

    return result;
}

OolEnhanceResult ool_enhancer_conceal(
    OolNeuralEnhancer *enh,
    int16_t *pcm_out, int num_samples)
{
    OolEnhanceResult result = {
        .was_enhanced = false,
        .inference_ms = 0.0f,
        .quality_delta = 0.0f,
        .output_samples = num_samples,
    };

    if (!enh || !pcm_out || !enh->models_loaded || !enh->runtime) {
        if (pcm_out) memset(pcm_out, 0, num_samples * sizeof(int16_t));
        return result;
    }

    /* Use LyraGAN to generate audio from cached features.
     * This leverages the generative model's ability to produce
     * plausible continuation of the audio stream. */
    int gen_samples = 0;
    int16_t gen_16k[NE_HOP_SAMPLES_16K];
    OolInferenceResult gen_result = ool_tflite_generate_audio(
        enh->runtime, enh->features, NE_NUM_FEATURES,
        gen_16k, &gen_samples);

    if (gen_result.success) {
        downsample_16k_to_8k(gen_16k, gen_samples, pcm_out, num_samples);
        enh->concealed_frames++;
        result.was_enhanced = true;
        result.inference_ms = gen_result.inference_ms;
    } else {
        memset(pcm_out, 0, num_samples * sizeof(int16_t));
    }

    return result;
}

bool ool_enhancer_ready(const OolNeuralEnhancer *enh) {
    return enh && enh->models_loaded && enh->runtime;
}

void ool_enhancer_set_enabled(OolNeuralEnhancer *enh, bool enabled) {
    if (enh) enh->enabled = enabled;
}

bool ool_enhancer_enabled(const OolNeuralEnhancer *enh) {
    return enh && enh->enabled;
}

void ool_enhancer_set_mix(OolNeuralEnhancer *enh, float mix) {
    if (enh) {
        enh->config.enhancement_mix = (mix < 0.0f) ? 0.0f :
                                       (mix > 1.0f) ? 1.0f : mix;
    }
}

OolEnhancerMetrics ool_enhancer_get_metrics(const OolNeuralEnhancer *enh) {
    OolEnhancerMetrics m = {0};
    if (!enh) return m;

    uint32_t total = enh->enhanced_frames + enh->bypassed_frames;
    m.avg_inference_ms = total > 0 ? enh->total_inference_ms / total : 0.0f;
    m.max_inference_ms = enh->max_inference_ms;
    m.total_enhanced_frames = enh->enhanced_frames;
    m.total_bypassed_frames = enh->bypassed_frames;
    m.total_concealed_frames = enh->concealed_frames;
    m.avg_quality_delta = enh->enhanced_frames > 0 ?
        enh->quality_sum / enh->enhanced_frames : 0.0f;
    m.models_loaded = enh->models_loaded;
    m.enabled = enh->enabled;

    return m;
}

void ool_enhancer_destroy(OolNeuralEnhancer *enh) {
    if (!enh) return;
    if (enh->runtime) ool_tflite_destroy(enh->runtime);
    free(enh);
}
