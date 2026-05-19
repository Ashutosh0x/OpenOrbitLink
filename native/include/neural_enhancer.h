/**
 * OpenOrbitLink — Neural Voice Enhancer
 *
 * Optional receiver-side post-processor that uses Lyra-inspired neural
 * models to enhance decoded Codec2 audio. Operates on the PCM output
 * after Codec2 decode, applying:
 *
 *   1. Spectral restoration (bandwidth extension from 4kHz → 8kHz)
 *   2. Noise suppression
 *   3. Missing-frame reconstruction
 *   4. Perceptual quality improvement
 *
 * Architecture:
 *   Codec2 decoded PCM (8kHz) → Upsample to 16kHz →
 *   SoundStream encoder → feature extraction →
 *   LyraGAN decoder → enhanced 16kHz PCM →
 *   Downsample to 8kHz (if needed)
 *
 * Falls back gracefully: if TFLite models are unavailable or CPU is
 * constrained, returns the original decoded PCM unmodified.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef OOL_NEURAL_ENHANCER_H
#define OOL_NEURAL_ENHANCER_H

#include <stdint.h>
#include <stdbool.h>

#include "tflite_runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ── Enhancer Configuration ──────────────────────────────────────────────── */

typedef struct {
    const char *model_path;        /* Path to TFLite model files              */
    bool        enable_denoising;  /* Apply noise suppression                 */
    bool        enable_bwe;        /* Apply bandwidth extension               */
    bool        enable_plc;        /* Use neural PLC for lost frames          */
    float       enhancement_mix;   /* 0.0 = original, 1.0 = fully enhanced   */
    float       max_cpu_percent;   /* Max CPU budget for enhancement (0-100)  */
    int         max_latency_ms;    /* Max added latency allowed               */
} OolEnhancerConfig;

/* ── Enhancer State (opaque) ─────────────────────────────────────────────── */

typedef struct OolNeuralEnhancer OolNeuralEnhancer;

/* ── Enhancement Result ──────────────────────────────────────────────────── */

typedef struct {
    bool    was_enhanced;        /* True if neural processing was applied     */
    float   inference_ms;       /* Time spent in neural inference             */
    float   quality_delta;      /* Estimated quality improvement (0-1)        */
    int     output_samples;     /* Number of output PCM samples               */
} OolEnhanceResult;

/* ── Enhancer API ────────────────────────────────────────────────────────── */

/**
 * Create a neural enhancer.
 * @param config  Enhancement configuration
 * @return Enhancer handle, or NULL if models unavailable
 */
OolNeuralEnhancer* ool_enhancer_create(const OolEnhancerConfig *config);

/**
 * Enhance a frame of decoded PCM audio.
 *
 * @param enh          Enhancer handle
 * @param pcm_in       Input PCM (Codec2 decoded, 8kHz)
 * @param num_samples  Input sample count
 * @param pcm_out      Output PCM buffer (same sample count)
 * @param out_samples  [out] Actual output samples
 * @return Enhancement result
 */
OolEnhanceResult ool_enhancer_process(
    OolNeuralEnhancer *enh,
    const int16_t *pcm_in, int num_samples,
    int16_t *pcm_out, int *out_samples);

/**
 * Neural packet loss concealment — generate missing frame from context.
 *
 * @param enh          Enhancer handle
 * @param pcm_out      Output concealment PCM
 * @param num_samples  Desired output samples
 * @return Enhancement result
 */
OolEnhanceResult ool_enhancer_conceal(
    OolNeuralEnhancer *enh,
    int16_t *pcm_out, int num_samples);

/**
 * Check if enhancer is ready and models are loaded.
 */
bool ool_enhancer_ready(const OolNeuralEnhancer *enh);

/**
 * Enable/disable enhancement at runtime.
 */
void ool_enhancer_set_enabled(OolNeuralEnhancer *enh, bool enabled);

/**
 * Get enhancement status.
 */
bool ool_enhancer_enabled(const OolNeuralEnhancer *enh);

/**
 * Set the enhancement mix level.
 * @param mix  0.0 = bypass, 1.0 = fully enhanced
 */
void ool_enhancer_set_mix(OolNeuralEnhancer *enh, float mix);

/**
 * Get enhancer performance metrics.
 */
typedef struct {
    float    avg_inference_ms;
    float    max_inference_ms;
    uint32_t total_enhanced_frames;
    uint32_t total_bypassed_frames;
    uint32_t total_concealed_frames;
    float    avg_quality_delta;
    bool     models_loaded;
    bool     enabled;
} OolEnhancerMetrics;

OolEnhancerMetrics ool_enhancer_get_metrics(const OolNeuralEnhancer *enh);

/**
 * Destroy enhancer and free resources.
 */
void ool_enhancer_destroy(OolNeuralEnhancer *enh);

#ifdef __cplusplus
}
#endif

#endif /* OOL_NEURAL_ENHANCER_H */
