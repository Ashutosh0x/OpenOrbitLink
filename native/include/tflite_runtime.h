/**
 * OpenOrbitLink — TFLite Runtime Abstraction
 *
 * Minimal wrapper for TensorFlow Lite inference on Android (NDK).
 * Handles model loading, interpreter lifecycle, delegate selection
 * (CPU/GPU/NNAPI), and memory budgeting for neural voice codecs.
 *
 * Design goals:
 *   - Graceful fallback if TFLite unavailable
 *   - Memory-bounded: configurable max model memory
 *   - Thread-safe model lifecycle (not inference — single-threaded)
 *   - Supports both float32 and int8-quantized models
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef OOL_TFLITE_RUNTIME_H
#define OOL_TFLITE_RUNTIME_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ── Delegate Types ──────────────────────────────────────────────────────── */

typedef enum {
    OOL_DELEGATE_CPU        = 0,    /* Default CPU with XNNPACK              */
    OOL_DELEGATE_GPU        = 1,    /* OpenGL ES / Vulkan GPU delegate       */
    OOL_DELEGATE_NNAPI      = 2,    /* Android NNAPI (NPU/DSP acceleration)  */
    OOL_DELEGATE_HEXAGON    = 3,    /* Qualcomm Hexagon DSP                  */
} OolTfliteDelegate;

/* ── Model Types ─────────────────────────────────────────────────────────── */

typedef enum {
    OOL_MODEL_SOUNDSTREAM_ENCODER = 0,   /* SoundStream feature extractor    */
    OOL_MODEL_QUANTIZER           = 1,   /* Residual Vector Quantizer        */
    OOL_MODEL_LYRAGAN             = 2,   /* LyraGAN generative decoder       */
    OOL_MODEL_COUNT               = 3,
} OolModelType;

/* ── Model File Names ────────────────────────────────────────────────────── */

static const char* const OOL_MODEL_FILENAMES[OOL_MODEL_COUNT] = {
    "soundstream_encoder.tflite",     /* ~1.7 MB */
    "quantizer.tflite",               /* ~329 KB */
    "lyragan.tflite",                 /* ~1.5 MB */
};

/* ── Runtime Configuration ───────────────────────────────────────────────── */

typedef struct {
    const char         *model_base_path;    /* Directory containing .tflite   */
    OolTfliteDelegate   preferred_delegate; /* Preferred hardware delegate    */
    int                 num_threads;        /* CPU threads (1-4, default 2)   */
    size_t              max_memory_mb;      /* Max total model memory (MB)    */
    bool                allow_int8;         /* Allow INT8 quantized models    */
    bool                allow_fp16;         /* Allow FP16 compute             */
} OolTfliteConfig;

/* ── Runtime State (opaque) ──────────────────────────────────────────────── */

typedef struct OolTfliteRuntime OolTfliteRuntime;

/* ── Inference Result ────────────────────────────────────────────────────── */

typedef struct {
    bool     success;
    float    inference_ms;      /* Time spent in inference                   */
    int      output_size;       /* Elements in output tensor                 */
} OolInferenceResult;

/* ── Runtime API ─────────────────────────────────────────────────────────── */

/**
 * Create and initialize the TFLite runtime.
 * @param config  Runtime configuration
 * @return Runtime handle, or NULL if TFLite unavailable
 */
OolTfliteRuntime* ool_tflite_create(const OolTfliteConfig *config);

/**
 * Load a specific model.
 * @param rt         Runtime handle
 * @param model_type Which model to load
 * @return true if model loaded successfully
 */
bool ool_tflite_load_model(OolTfliteRuntime *rt, OolModelType model_type);

/**
 * Check if a model is loaded and ready.
 */
bool ool_tflite_model_ready(const OolTfliteRuntime *rt, OolModelType model_type);

/**
 * Check if all required models are loaded.
 */
bool ool_tflite_all_models_ready(const OolTfliteRuntime *rt);

/**
 * Run SoundStream encoder: PCM → features.
 * @param rt         Runtime handle
 * @param pcm_in     Input PCM samples (16kHz, 320 samples = 20ms)
 * @param num_samples Number of input samples
 * @param features   Output feature vector (kNumFeatures = 64 floats)
 * @param num_features [out] Number of features written
 * @return Inference result
 */
OolInferenceResult ool_tflite_extract_features(
    OolTfliteRuntime *rt,
    const int16_t *pcm_in, int num_samples,
    float *features, int *num_features);

/**
 * Run RVQ quantizer: features → quantized bits.
 * @param rt             Runtime handle
 * @param features       Input features (64 floats)
 * @param num_features   Number of features
 * @param num_bits       Target quantized bits (64, 120, or 184)
 * @param quantized_out  Output quantized bytes
 * @param out_len        [out] Bytes written
 * @return Inference result
 */
OolInferenceResult ool_tflite_quantize(
    OolTfliteRuntime *rt,
    const float *features, int num_features,
    int num_bits,
    uint8_t *quantized_out, int *out_len);

/**
 * Run RVQ dequantizer: quantized bits → features.
 */
OolInferenceResult ool_tflite_dequantize(
    OolTfliteRuntime *rt,
    const uint8_t *quantized_in, int in_len,
    float *features, int *num_features);

/**
 * Run LyraGAN decoder: features → PCM.
 * @param rt          Runtime handle
 * @param features    Input features (64 floats)
 * @param num_features Number of features
 * @param pcm_out     Output PCM samples (16kHz, 320 samples = 20ms)
 * @param num_samples [out] Samples written
 * @return Inference result
 */
OolInferenceResult ool_tflite_generate_audio(
    OolTfliteRuntime *rt,
    const float *features, int num_features,
    int16_t *pcm_out, int *num_samples);

/**
 * Get runtime performance metrics.
 */
typedef struct {
    float    avg_encode_ms;      /* Average SoundStream encode time          */
    float    avg_quantize_ms;    /* Average RVQ quantize time                */
    float    avg_generate_ms;    /* Average LyraGAN generate time            */
    float    total_inference_ms; /* Total inference time since creation      */
    uint32_t total_frames;       /* Total frames processed                   */
    size_t   memory_used_kb;     /* Approximate memory usage                 */
    OolTfliteDelegate active_delegate; /* Currently active delegate          */
} OolTfliteMetrics;

OolTfliteMetrics ool_tflite_get_metrics(const OolTfliteRuntime *rt);

/**
 * Destroy the runtime and free all resources.
 */
void ool_tflite_destroy(OolTfliteRuntime *rt);

/**
 * Check if TFLite runtime is available on this platform.
 */
bool ool_tflite_available(void);

/**
 * Check if model files exist at the given path.
 */
bool ool_tflite_models_exist(const char *model_base_path);

#ifdef __cplusplus
}
#endif

#endif /* OOL_TFLITE_RUNTIME_H */
