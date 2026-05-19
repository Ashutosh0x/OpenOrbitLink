/**
 * OpenOrbitLink — Lyra Codec Wrapper
 *
 * Implements OolCodecOps for Lyra-mode neural codecs (3200/6000/9200 bps).
 * Uses TFLite models for encode/decode. Only active when sufficient
 * bandwidth and CPU are available.
 *
 * Encode path:
 *   PCM (16kHz, 320 samples/20ms) → SoundStream encoder → features →
 *   RVQ quantizer → quantized bitstream
 *
 * Decode path:
 *   Quantized bitstream → RVQ dequantizer → features →
 *   LyraGAN decoder → PCM (16kHz, 320 samples/20ms)
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "codec_interface.h"
#include "tflite_runtime.h"

/* ── Lyra Constants ──────────────────────────────────────────────────────── */

#define LYRA_SAMPLE_RATE     16000
#define LYRA_FRAME_RATE      50    /* 50 Hz = 20ms frames */
#define LYRA_HOP_SAMPLES     320   /* 16000 / 50 */
#define LYRA_NUM_FEATURES    64
#define LYRA_NUM_HEADER_BITS 0     /* No header in standalone mode */

/* Bitrate → quantized bits mapping (from lyra_config.h) */
static int lyra_bitrate_to_bits(int bitrate) {
    switch (bitrate) {
        case 3200:  return 64;
        case 6000:  return 120;
        case 9200:  return 184;
        default:    return -1;
    }
}

/* ── Lyra Private State ──────────────────────────────────────────────────── */

typedef struct {
    OolTfliteRuntime  *runtime;
    OolCodecMode       ool_mode;
    int                bitrate;
    int                num_quantized_bits;
    OolCodecDescriptor descriptor;
    bool               initialized;

    /* Intermediate buffers */
    float              features[LYRA_NUM_FEATURES];
} LyraState;

/* ── Static Descriptors ──────────────────────────────────────────────────── */

static const OolCodecDescriptor lyra_descriptors[] = {
    {
        .mode = OOL_CODEC_LYRA_3200,
        .name = "Lyra 3200",
        .capabilities = OOL_CAP_ENCODE | OOL_CAP_DECODE | OOL_CAP_NEURAL,
        .sample_rate_hz = 16000,
        .frame_samples = 320,
        .frame_ms = 20,
        .frame_bits = 64,
        .frame_bytes = 8,
        .bitrate_bps = 3200,
        .model_size_kb = 3500,
    },
    {
        .mode = OOL_CODEC_LYRA_6000,
        .name = "Lyra 6000",
        .capabilities = OOL_CAP_ENCODE | OOL_CAP_DECODE | OOL_CAP_NEURAL,
        .sample_rate_hz = 16000,
        .frame_samples = 320,
        .frame_ms = 20,
        .frame_bits = 120,
        .frame_bytes = 15,
        .bitrate_bps = 6000,
        .model_size_kb = 3500,
    },
    {
        .mode = OOL_CODEC_LYRA_9200,
        .name = "Lyra 9200",
        .capabilities = OOL_CAP_ENCODE | OOL_CAP_DECODE | OOL_CAP_NEURAL,
        .sample_rate_hz = 16000,
        .frame_samples = 320,
        .frame_ms = 20,
        .frame_bits = 184,
        .frame_bytes = 23,
        .bitrate_bps = 9200,
        .model_size_kb = 3500,
    },
};

#define NUM_LYRA_MODES (sizeof(lyra_descriptors) / sizeof(lyra_descriptors[0]))

static const OolCodecDescriptor* find_lyra_descriptor(OolCodecMode mode) {
    for (size_t i = 0; i < NUM_LYRA_MODES; i++) {
        if (lyra_descriptors[i].mode == mode) return &lyra_descriptors[i];
    }
    return NULL;
}

static int ool_mode_to_lyra_bitrate(OolCodecMode mode) {
    switch (mode) {
        case OOL_CODEC_LYRA_3200: return 3200;
        case OOL_CODEC_LYRA_6000: return 6000;
        case OOL_CODEC_LYRA_9200: return 9200;
        default: return -1;
    }
}

/* ── OolCodecOps Implementation ──────────────────────────────────────────── */

static OolError lyra_init(void *ctx, OolCodecMode mode) {
    LyraState *s = (LyraState *)ctx;
    if (!s) return OOL_ERR_NOT_INITIALIZED;

    const OolCodecDescriptor *desc = find_lyra_descriptor(mode);
    if (!desc) return OOL_ERR_INVALID_MODE;

    int bitrate = ool_mode_to_lyra_bitrate(mode);
    int num_bits = lyra_bitrate_to_bits(bitrate);
    if (num_bits < 0) return OOL_ERR_INVALID_MODE;

    s->ool_mode = mode;
    s->bitrate = bitrate;
    s->num_quantized_bits = num_bits;
    s->descriptor = *desc;

    /* Check if TFLite runtime has models loaded */
    if (!s->runtime || !ool_tflite_all_models_ready(s->runtime)) {
        return OOL_ERR_MODEL_MISSING;
    }

    s->initialized = true;
    return OOL_OK;
}

static OolError lyra_encode(void *ctx, const int16_t *pcm_in, int num_samples,
                             uint8_t *out, int *out_len) {
    LyraState *s = (LyraState *)ctx;
    if (!s || !s->initialized) return OOL_ERR_NOT_INITIALIZED;
    if (num_samples != LYRA_HOP_SAMPLES) return OOL_ERR_BAD_FRAME;

    /* Step 1: Extract features via SoundStream encoder */
    int num_features = 0;
    OolInferenceResult fe_result = ool_tflite_extract_features(
        s->runtime, pcm_in, num_samples, s->features, &num_features);
    if (!fe_result.success) return OOL_ERR_INFERENCE_FAIL;

    /* Step 2: Quantize features via RVQ */
    OolInferenceResult q_result = ool_tflite_quantize(
        s->runtime, s->features, num_features,
        s->num_quantized_bits, out, out_len);
    if (!q_result.success) return OOL_ERR_INFERENCE_FAIL;

    return OOL_OK;
}

static OolError lyra_decode(void *ctx, const uint8_t *data, int data_len,
                             int16_t *pcm_out, int *num_samples) {
    LyraState *s = (LyraState *)ctx;
    if (!s || !s->initialized) return OOL_ERR_NOT_INITIALIZED;

    /* Step 1: Dequantize to features */
    int num_features = 0;
    OolInferenceResult dq_result = ool_tflite_dequantize(
        s->runtime, data, data_len, s->features, &num_features);
    if (!dq_result.success) return OOL_ERR_INFERENCE_FAIL;

    /* Step 2: Generate audio via LyraGAN */
    OolInferenceResult gen_result = ool_tflite_generate_audio(
        s->runtime, s->features, num_features, pcm_out, num_samples);
    if (!gen_result.success) return OOL_ERR_INFERENCE_FAIL;

    return OOL_OK;
}

static OolError lyra_decode_ber(void *ctx, const uint8_t *data, int data_len,
                                 float ber_est, int16_t *pcm_out, int *num_samples) {
    /* Neural codec doesn't use BER estimation — just decode normally.
     * The generative model inherently handles noisy features. */
    (void)ber_est;
    return lyra_decode(ctx, data, data_len, pcm_out, num_samples);
}

static const OolCodecDescriptor* lyra_get_descriptor(void *ctx) {
    LyraState *s = (LyraState *)ctx;
    return s ? &s->descriptor : NULL;
}

static void lyra_destroy(void *ctx) {
    LyraState *s = (LyraState *)ctx;
    if (!s) return;
    /* Note: TFLite runtime is shared — don't destroy it here */
    s->initialized = false;
    free(s);
}

/* ── Lyra vtable ─────────────────────────────────────────────────────────── */

static const OolCodecOps lyra_ops = {
    .init           = lyra_init,
    .encode         = lyra_encode,
    .decode         = lyra_decode,
    .decode_ber     = lyra_decode_ber,
    .get_descriptor = lyra_get_descriptor,
    .destroy        = lyra_destroy,
};

/* ── Factory Function ────────────────────────────────────────────────────── */

/**
 * Create a Lyra neural codec instance.
 *
 * @param mode       One of OOL_CODEC_LYRA_3200/6000/9200
 * @param model_path Path to directory containing .tflite model files
 * @return Initialized instance, or NULL on failure
 */
OolCodecInstance* ool_lyra_create(OolCodecMode mode, const char *model_path) {
    if (!ool_mode_is_neural(mode)) return NULL;
    if (!model_path) return NULL;

    /* Create TFLite runtime */
    OolTfliteConfig rt_config = {
        .model_base_path = model_path,
        .preferred_delegate = OOL_DELEGATE_CPU,
        .num_threads = 2,
        .max_memory_mb = 16,
        .allow_int8 = true,
        .allow_fp16 = true,
    };

    OolTfliteRuntime *runtime = ool_tflite_create(&rt_config);
    if (!runtime) return NULL;

    /* Load models */
    if (!ool_tflite_load_model(runtime, OOL_MODEL_SOUNDSTREAM_ENCODER) ||
        !ool_tflite_load_model(runtime, OOL_MODEL_QUANTIZER) ||
        !ool_tflite_load_model(runtime, OOL_MODEL_LYRAGAN)) {
        ool_tflite_destroy(runtime);
        return NULL;
    }

    LyraState *state = (LyraState *)calloc(1, sizeof(LyraState));
    if (!state) { ool_tflite_destroy(runtime); return NULL; }

    state->runtime = runtime;

    OolCodecInstance *inst = (OolCodecInstance *)calloc(1, sizeof(OolCodecInstance));
    if (!inst) { free(state); ool_tflite_destroy(runtime); return NULL; }

    inst->ctx = state;
    inst->ops = &lyra_ops;
    inst->mode = mode;

    OolError err = lyra_init(state, mode);
    if (err != OOL_OK) {
        free(state);
        free(inst);
        ool_tflite_destroy(runtime);
        return NULL;
    }

    inst->initialized = true;
    return inst;
}
