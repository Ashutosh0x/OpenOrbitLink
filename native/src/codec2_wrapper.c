/**
 * OpenOrbitLink — Codec2 Wrapper
 *
 * Implements OolCodecOps for all Codec2 modes (700C through 3200).
 * Wraps the upstream codec2_create/encode/decode/destroy API through the
 * universal codec interface, enabling transparent codec switching.
 *
 * Codec2 modes and their properties:
 *   700C:  28 bits/40ms, 320 samples/frame, 4 bytes/frame, 700 bps
 *   1200:  48 bits/40ms, 320 samples/frame, 6 bytes/frame, 1200 bps
 *   1300:  52 bits/40ms, 320 samples/frame, 7 bytes/frame, 1300 bps
 *   1600:  64 bits/40ms, 320 samples/frame, 8 bytes/frame, 1600 bps
 *   2400:  48 bits/20ms, 160 samples/frame, 6 bytes/frame, 2400 bps
 *   3200:  64 bits/20ms, 160 samples/frame, 8 bytes/frame, 3200 bps
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "codec_interface.h"

/* Include real Codec2 if available, otherwise use stub */
#ifdef OOL_HAS_CODEC2
#include "codec2/codec2.h"
#else
/* Forward-declare for compilation without Codec2 source */
struct CODEC2;
struct CODEC2 *codec2_create(int mode);
void codec2_destroy(struct CODEC2 *c2);
void codec2_encode(struct CODEC2 *c2, unsigned char *bytes, short speech[]);
void codec2_decode(struct CODEC2 *c2, short speech[], const unsigned char *bytes);
void codec2_decode_ber(struct CODEC2 *c2, short speech[],
                       const unsigned char *bytes, float ber_est);
int codec2_samples_per_frame(struct CODEC2 *c2);
int codec2_bits_per_frame(struct CODEC2 *c2);
int codec2_bytes_per_frame(struct CODEC2 *c2);
#endif

/* ── Codec2 Private State ────────────────────────────────────────────────── */

typedef struct {
    struct CODEC2    *c2;
    OolCodecMode      ool_mode;
    int               c2_mode;
    OolCodecDescriptor descriptor;
    bool              initialized;
} Codec2State;

/* ── Static Descriptors ──────────────────────────────────────────────────── */

static const OolCodecDescriptor c2_descriptors[] = {
    {
        .mode = OOL_CODEC_C2_700C,
        .name = "Codec2 700C",
        .capabilities = OOL_CAP_ENCODE | OOL_CAP_DECODE | OOL_CAP_DETERMINISTIC |
                         OOL_CAP_LOW_POWER | OOL_CAP_LORA_SAFE,
        .sample_rate_hz = 8000,
        .frame_samples = 320,
        .frame_ms = 40,
        .frame_bits = 28,
        .frame_bytes = 4,
        .bitrate_bps = 700,
        .model_size_kb = 0,
    },
    {
        .mode = OOL_CODEC_C2_1200,
        .name = "Codec2 1200",
        .capabilities = OOL_CAP_ENCODE | OOL_CAP_DECODE | OOL_CAP_DETERMINISTIC |
                         OOL_CAP_LOW_POWER | OOL_CAP_LORA_SAFE,
        .sample_rate_hz = 8000,
        .frame_samples = 320,
        .frame_ms = 40,
        .frame_bits = 48,
        .frame_bytes = 6,
        .bitrate_bps = 1200,
        .model_size_kb = 0,
    },
    {
        .mode = OOL_CODEC_C2_1300,
        .name = "Codec2 1300",
        .capabilities = OOL_CAP_ENCODE | OOL_CAP_DECODE | OOL_CAP_BER_DECODE |
                         OOL_CAP_DETERMINISTIC | OOL_CAP_LOW_POWER | OOL_CAP_LORA_SAFE,
        .sample_rate_hz = 8000,
        .frame_samples = 320,
        .frame_ms = 40,
        .frame_bits = 52,
        .frame_bytes = 7,
        .bitrate_bps = 1300,
        .model_size_kb = 0,
    },
    {
        .mode = OOL_CODEC_C2_1600,
        .name = "Codec2 1600",
        .capabilities = OOL_CAP_ENCODE | OOL_CAP_DECODE | OOL_CAP_DETERMINISTIC |
                         OOL_CAP_LOW_POWER | OOL_CAP_LORA_SAFE,
        .sample_rate_hz = 8000,
        .frame_samples = 320,
        .frame_ms = 40,
        .frame_bits = 64,
        .frame_bytes = 8,
        .bitrate_bps = 1600,
        .model_size_kb = 0,
    },
    {
        .mode = OOL_CODEC_C2_2400,
        .name = "Codec2 2400",
        .capabilities = OOL_CAP_ENCODE | OOL_CAP_DECODE | OOL_CAP_DETERMINISTIC |
                         OOL_CAP_LOW_POWER,
        .sample_rate_hz = 8000,
        .frame_samples = 160,
        .frame_ms = 20,
        .frame_bits = 48,
        .frame_bytes = 6,
        .bitrate_bps = 2400,
        .model_size_kb = 0,
    },
    {
        .mode = OOL_CODEC_C2_3200,
        .name = "Codec2 3200",
        .capabilities = OOL_CAP_ENCODE | OOL_CAP_DECODE | OOL_CAP_DETERMINISTIC |
                         OOL_CAP_LOW_POWER,
        .sample_rate_hz = 8000,
        .frame_samples = 160,
        .frame_ms = 20,
        .frame_bits = 64,
        .frame_bytes = 8,
        .bitrate_bps = 3200,
        .model_size_kb = 0,
    },
};

#define NUM_C2_MODES (sizeof(c2_descriptors) / sizeof(c2_descriptors[0]))

/* ── Find descriptor for OOL mode ────────────────────────────────────────── */

static const OolCodecDescriptor* find_c2_descriptor(OolCodecMode mode) {
    for (size_t i = 0; i < NUM_C2_MODES; i++) {
        if (c2_descriptors[i].mode == mode) return &c2_descriptors[i];
    }
    return NULL;
}

/* ── OolCodecOps Implementation ──────────────────────────────────────────── */

static OolError c2_init(void *ctx, OolCodecMode mode) {
    Codec2State *s = (Codec2State *)ctx;
    if (!s) return OOL_ERR_NOT_INITIALIZED;

    const OolCodecDescriptor *desc = find_c2_descriptor(mode);
    if (!desc) return OOL_ERR_INVALID_MODE;

    int c2_mode = ool_mode_to_codec2_mode(mode);
    if (c2_mode < 0) return OOL_ERR_INVALID_MODE;

    s->c2 = codec2_create(c2_mode);
    if (!s->c2) return OOL_ERR_ALLOC_FAIL;

    s->ool_mode = mode;
    s->c2_mode = c2_mode;
    s->descriptor = *desc;
    s->initialized = true;

    return OOL_OK;
}

static OolError c2_encode(void *ctx, const int16_t *pcm_in, int num_samples,
                           uint8_t *out, int *out_len) {
    Codec2State *s = (Codec2State *)ctx;
    if (!s || !s->initialized || !s->c2) return OOL_ERR_NOT_INITIALIZED;
    if (num_samples != s->descriptor.frame_samples) return OOL_ERR_BAD_FRAME;
    if (!out || !out_len) return OOL_ERR_BUFFER_TOO_SMALL;

    /* Codec2 API takes non-const short* (historical API, does not modify) */
    codec2_encode(s->c2, out, (short *)pcm_in);
    *out_len = s->descriptor.frame_bytes;

    return OOL_OK;
}

static OolError c2_decode(void *ctx, const uint8_t *data, int data_len,
                           int16_t *pcm_out, int *num_samples) {
    Codec2State *s = (Codec2State *)ctx;
    if (!s || !s->initialized || !s->c2) return OOL_ERR_NOT_INITIALIZED;
    if (data_len < s->descriptor.frame_bytes) return OOL_ERR_BAD_FRAME;
    if (!pcm_out || !num_samples) return OOL_ERR_BUFFER_TOO_SMALL;

    codec2_decode(s->c2, pcm_out, data);
    *num_samples = s->descriptor.frame_samples;

    return OOL_OK;
}

static OolError c2_decode_ber(void *ctx, const uint8_t *data, int data_len,
                               float ber_est, int16_t *pcm_out, int *num_samples) {
    Codec2State *s = (Codec2State *)ctx;
    if (!s || !s->initialized || !s->c2) return OOL_ERR_NOT_INITIALIZED;
    if (data_len < s->descriptor.frame_bytes) return OOL_ERR_BAD_FRAME;

    /* BER-aware decode only available for mode 1300 */
    if (s->ool_mode == OOL_CODEC_C2_1300) {
        codec2_decode_ber(s->c2, pcm_out, data, ber_est);
    } else {
        codec2_decode(s->c2, pcm_out, data);
    }
    *num_samples = s->descriptor.frame_samples;

    return OOL_OK;
}

static const OolCodecDescriptor* c2_get_descriptor(void *ctx) {
    Codec2State *s = (Codec2State *)ctx;
    if (!s) return NULL;
    return &s->descriptor;
}

static void c2_destroy(void *ctx) {
    Codec2State *s = (Codec2State *)ctx;
    if (!s) return;
    if (s->c2) {
        codec2_destroy(s->c2);
        s->c2 = NULL;
    }
    s->initialized = false;
    free(s);
}

/* ── Codec2 vtable ───────────────────────────────────────────────────────── */

static const OolCodecOps codec2_ops = {
    .init           = c2_init,
    .encode         = c2_encode,
    .decode         = c2_decode,
    .decode_ber     = c2_decode_ber,
    .get_descriptor = c2_get_descriptor,
    .destroy        = c2_destroy,
};

/* ── Factory Function ────────────────────────────────────────────────────── */

/**
 * Create a Codec2 codec instance.
 *
 * @param mode       One of OOL_CODEC_C2_700C through OOL_CODEC_C2_3200
 * @param model_path Ignored for Codec2 (no models needed)
 * @return Initialized instance, or NULL on failure
 */
OolCodecInstance* ool_codec2_create(OolCodecMode mode, const char *model_path) {
    (void)model_path;

    if (!ool_mode_is_codec2(mode)) return NULL;

    Codec2State *state = (Codec2State *)calloc(1, sizeof(Codec2State));
    if (!state) return NULL;

    OolCodecInstance *inst = (OolCodecInstance *)calloc(1, sizeof(OolCodecInstance));
    if (!inst) { free(state); return NULL; }

    inst->ctx = state;
    inst->ops = &codec2_ops;
    inst->mode = mode;

    OolError err = c2_init(state, mode);
    if (err != OOL_OK) {
        free(state);
        free(inst);
        return NULL;
    }

    inst->initialized = true;
    return inst;
}
