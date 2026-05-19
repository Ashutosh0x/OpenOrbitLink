/**
 * OpenOrbitLink — Universal Codec Interface
 *
 * Abstraction layer enabling pluggable voice codecs. Both Codec2 (deterministic
 * DSP) and Lyra-style (neural TFLite) codecs implement this interface.
 *
 * Design constraints:
 *   - C99 compatible (runs on embedded targets)
 *   - Zero heap allocation in hot path
 *   - Frame-oriented (not streaming)
 *   - Codec-agnostic framing for DTN chunking
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef OOL_CODEC_INTERFACE_H
#define OOL_CODEC_INTERFACE_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ── Codec Identification ────────────────────────────────────────────────── */

typedef enum {
    OOL_CODEC_NONE           = 0x00,

    /* Codec2 deterministic modes */
    OOL_CODEC_C2_700C        = 0x10,   /* 700 bps,  28 bits/40ms, 4 bytes/frame  */
    OOL_CODEC_C2_1200        = 0x11,   /* 1200 bps, 48 bits/40ms, 6 bytes/frame  */
    OOL_CODEC_C2_1300        = 0x12,   /* 1300 bps, 52 bits/40ms, 7 bytes/frame  */
    OOL_CODEC_C2_1600        = 0x13,   /* 1600 bps, 64 bits/40ms, 8 bytes/frame  */
    OOL_CODEC_C2_2400        = 0x14,   /* 2400 bps, 48 bits/20ms, 6 bytes/frame  */
    OOL_CODEC_C2_3200        = 0x15,   /* 3200 bps, 64 bits/20ms, 8 bytes/frame  */

    /* Neural codec modes (Lyra-inspired, TFLite) */
    OOL_CODEC_LYRA_3200      = 0x20,   /* 3200 bps,  64 quantized bits/20ms      */
    OOL_CODEC_LYRA_6000      = 0x21,   /* 6000 bps, 120 quantized bits/20ms      */
    OOL_CODEC_LYRA_9200      = 0x22,   /* 9200 bps, 184 quantized bits/20ms      */

    /* Special */
    OOL_CODEC_RAW_PCM        = 0xF0,   /* Uncompressed PCM (test / WiFi only)    */
    OOL_CODEC_PASSTHROUGH    = 0xFE,   /* No codec — relay raw bytes             */
} OolCodecMode;

/* ── Codec Capabilities ──────────────────────────────────────────────────── */

typedef enum {
    OOL_CAP_ENCODE           = 0x01,
    OOL_CAP_DECODE           = 0x02,
    OOL_CAP_BER_DECODE       = 0x04,   /* Decode with BER estimation input       */
    OOL_CAP_NEURAL           = 0x08,   /* Uses neural inference (TFLite)          */
    OOL_CAP_DETERMINISTIC    = 0x10,   /* Bit-exact output for same input        */
    OOL_CAP_LOW_POWER        = 0x20,   /* Suitable for battery-constrained use   */
    OOL_CAP_LORA_SAFE        = 0x40,   /* Frame size fits LoRa 80-byte limit     */
    OOL_CAP_FEC_INTEGRATED   = 0x80,   /* Codec has built-in error protection    */
} OolCodecCaps;

/* ── Error Codes ─────────────────────────────────────────────────────────── */

typedef enum {
    OOL_OK                   =  0,
    OOL_ERR_INVALID_MODE     = -1,
    OOL_ERR_NOT_INITIALIZED  = -2,
    OOL_ERR_BUFFER_TOO_SMALL = -3,
    OOL_ERR_BAD_FRAME        = -4,
    OOL_ERR_MODEL_MISSING    = -5,
    OOL_ERR_INFERENCE_FAIL   = -6,
    OOL_ERR_ALLOC_FAIL       = -7,
    OOL_ERR_UNSUPPORTED      = -8,
} OolError;

/* ── Codec Descriptor ────────────────────────────────────────────────────── */

/**
 * Static descriptor for a codec mode. Filled once at init, never mutated.
 */
typedef struct {
    OolCodecMode   mode;
    const char    *name;              /* e.g. "Codec2 700C", "Lyra 3200"      */
    uint32_t       capabilities;      /* Bitmask of OolCodecCaps              */
    int            sample_rate_hz;    /* Native sample rate (8000 or 16000)   */
    int            frame_samples;     /* PCM samples per frame                */
    int            frame_ms;          /* Frame duration in ms                 */
    int            frame_bits;        /* Encoded bits per frame               */
    int            frame_bytes;       /* Encoded bytes per frame (ceil)       */
    int            bitrate_bps;       /* Nominal bitrate                      */
    int            model_size_kb;     /* TFLite model size (0 for DSP codecs) */
} OolCodecDescriptor;

/* ── Codec Interface (vtable) ────────────────────────────────────────────── */

/**
 * Function-pointer-based interface. Each codec implementation provides
 * a filled OolCodecOps struct. The opaque `ctx` is the codec's private state.
 */
typedef struct OolCodecOps {
    /**
     * Initialize codec in the given mode.
     * @param ctx     Opaque codec state (pre-allocated by create function)
     * @param mode    Requested codec mode
     * @return OOL_OK on success
     */
    OolError (*init)(void *ctx, OolCodecMode mode);

    /**
     * Encode one frame of PCM to compressed bytes.
     * @param ctx         Codec state
     * @param pcm_in      Input PCM samples (frame_samples count)
     * @param num_samples Number of input samples (must == descriptor.frame_samples)
     * @param out         Output buffer (must be >= descriptor.frame_bytes)
     * @param out_len     [out] Actual bytes written
     * @return OOL_OK on success
     */
    OolError (*encode)(void *ctx, const int16_t *pcm_in, int num_samples,
                       uint8_t *out, int *out_len);

    /**
     * Decode compressed bytes to one frame of PCM.
     * @param ctx         Codec state
     * @param data        Compressed frame bytes
     * @param data_len    Length of compressed data
     * @param pcm_out     Output PCM buffer (must hold >= frame_samples)
     * @param num_samples [out] Actual samples written
     * @return OOL_OK on success
     */
    OolError (*decode)(void *ctx, const uint8_t *data, int data_len,
                       int16_t *pcm_out, int *num_samples);

    /**
     * Decode with bit-error-rate hint (Codec2 1300 mode).
     * Falls back to normal decode if not supported.
     */
    OolError (*decode_ber)(void *ctx, const uint8_t *data, int data_len,
                           float ber_est, int16_t *pcm_out, int *num_samples);

    /**
     * Get the static descriptor for this codec.
     */
    const OolCodecDescriptor* (*get_descriptor)(void *ctx);

    /**
     * Release all resources. ctx is invalid after this call.
     */
    void (*destroy)(void *ctx);

} OolCodecOps;

/* ── Codec Instance ──────────────────────────────────────────────────────── */

/**
 * A live codec instance: opaque state + vtable.
 */
typedef struct {
    void                *ctx;
    const OolCodecOps   *ops;
    OolCodecMode         mode;
    bool                 initialized;
} OolCodecInstance;

/* ── Convenience macros ──────────────────────────────────────────────────── */

#define ool_codec_encode(inst, pcm, n, out, olen) \
    ((inst)->ops->encode((inst)->ctx, pcm, n, out, olen))

#define ool_codec_decode(inst, data, dlen, pcm, nsamp) \
    ((inst)->ops->decode((inst)->ctx, data, dlen, pcm, nsamp))

#define ool_codec_descriptor(inst) \
    ((inst)->ops->get_descriptor((inst)->ctx))

#define ool_codec_destroy(inst) do { \
    if ((inst)->ops && (inst)->ops->destroy) \
        (inst)->ops->destroy((inst)->ctx); \
    (inst)->ctx = NULL; \
    (inst)->initialized = false; \
} while(0)

/* ── Mode Helpers ────────────────────────────────────────────────────────── */

static inline bool ool_mode_is_codec2(OolCodecMode m) {
    return (m >= OOL_CODEC_C2_700C && m <= OOL_CODEC_C2_3200);
}

static inline bool ool_mode_is_neural(OolCodecMode m) {
    return (m >= OOL_CODEC_LYRA_3200 && m <= OOL_CODEC_LYRA_9200);
}

static inline bool ool_mode_is_lora_safe(OolCodecMode m) {
    /* Only Codec2 sub-2kbps modes produce frames small enough for LoRa */
    return (m == OOL_CODEC_C2_700C || m == OOL_CODEC_C2_1200 ||
            m == OOL_CODEC_C2_1300 || m == OOL_CODEC_C2_1600);
}

static inline int ool_mode_to_codec2_mode(OolCodecMode m) {
    switch (m) {
        case OOL_CODEC_C2_700C: return 8;  /* CODEC2_MODE_700C */
        case OOL_CODEC_C2_1200: return 5;  /* CODEC2_MODE_1200 */
        case OOL_CODEC_C2_1300: return 4;  /* CODEC2_MODE_1300 */
        case OOL_CODEC_C2_1600: return 2;  /* CODEC2_MODE_1600 */
        case OOL_CODEC_C2_2400: return 1;  /* CODEC2_MODE_2400 */
        case OOL_CODEC_C2_3200: return 0;  /* CODEC2_MODE_3200 */
        default: return -1;
    }
}

#ifdef __cplusplus
}
#endif

#endif /* OOL_CODEC_INTERFACE_H */
