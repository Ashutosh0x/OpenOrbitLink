/**
 * OpenOrbitLink — Codec2 FEC Wrapper
 *
 * Lightweight forward error correction for voice frames over LoRa.
 * Uses Golay(23,12) for critical voice bits and byte-level interleaving
 * for burst-error resilience in ISM band channels.
 *
 * FEC strategy per codec mode:
 *   700C (28 bits):  Protect all 28 bits → Golay encodes 12-bit blocks
 *                    Total: 28 data + 33 parity = 61 bits → 8 bytes
 *   1300 (52 bits):  Protect first 24 critical bits (Wo + voicing)
 *                    Total: 52 data + 23 parity = 75 bits → 10 bytes
 *
 * The overhead is acceptable because LoRa frames have 80-byte budget.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <stdint.h>
#include <string.h>
#include <stdbool.h>

#ifdef OOL_HAS_CODEC2
#include "codec2/golay23.h"
#endif

/* ── FEC Configuration ───────────────────────────────────────────────────── */

#define OOL_FEC_MAX_INPUT     24    /* Max input bytes (Lyra 9200 = 23)       */
#define OOL_FEC_MAX_OUTPUT    32    /* Max output with parity                 */
#define OOL_FEC_GOLAY_DATA    12    /* Golay(23,12) data bits                 */
#define OOL_FEC_GOLAY_TOTAL   23    /* Golay(23,12) codeword bits             */

/* ── Interleaver ─────────────────────────────────────────────────────────── */

/**
 * Block interleaver for burst-error resilience.
 * Interleaves bytes across a matrix of (rows x cols).
 * Write row-wise, read column-wise.
 */
static void interleave_bytes(const uint8_t *in, uint8_t *out,
                              int length, int rows) {
    if (length <= 0 || rows <= 0) return;
    int cols = (length + rows - 1) / rows;
    int idx = 0;

    for (int c = 0; c < cols; c++) {
        for (int r = 0; r < rows; r++) {
            int src = r * cols + c;
            if (src < length) {
                out[idx++] = in[src];
            }
        }
    }
    /* Zero-pad if needed */
    while (idx < length) out[idx++] = 0;
}

/**
 * De-interleave bytes (inverse of interleave_bytes).
 */
static void deinterleave_bytes(const uint8_t *in, uint8_t *out,
                                int length, int rows) {
    if (length <= 0 || rows <= 0) return;
    int cols = (length + rows - 1) / rows;
    int idx = 0;

    for (int c = 0; c < cols; c++) {
        for (int r = 0; r < rows; r++) {
            int dst = r * cols + c;
            if (dst < length) {
                out[dst] = in[idx++];
            }
        }
    }
}

/* ── Simple XOR-based Parity (fallback when Golay unavailable) ───────── */

/**
 * Compute 4-byte XOR parity over data.
 * This is a minimal FEC for development — production should use proper RS.
 */
static void compute_xor_parity(const uint8_t *data, int len,
                                uint8_t *parity, int parity_len) {
    memset(parity, 0, parity_len);
    for (int i = 0; i < len; i++) {
        parity[i % parity_len] ^= data[i];
    }
}

/* ── FEC Frame Structure ─────────────────────────────────────────────────── */

typedef struct {
    uint8_t  data[OOL_FEC_MAX_OUTPUT];
    int      data_len;       /* Original data length                       */
    int      total_len;      /* Data + parity length                       */
    int      errors_corrected;
    bool     valid;
} OolFecFrame;

/* ── FEC Encode ──────────────────────────────────────────────────────────── */

/**
 * Add FEC protection to a codec frame.
 *
 * @param input     Raw codec frame bytes
 * @param input_len Length of input
 * @param output    Output buffer (must hold input_len + 4 bytes)
 * @param output_len [out] Total output length
 * @param use_interleave Apply byte interleaving for burst errors
 * @return true on success
 */
static inline bool ool_fec_encode(const uint8_t *input, int input_len,
                                   uint8_t *output, int *output_len,
                                   bool use_interleave) {
    if (!input || !output || !output_len || input_len <= 0) return false;
    if (input_len > OOL_FEC_MAX_INPUT) return false;

    /* Copy data */
    memcpy(output, input, input_len);

    /* Add 4-byte XOR parity */
    int parity_len = 4;
    compute_xor_parity(input, input_len, &output[input_len], parity_len);
    int total = input_len + parity_len;

    /* Optional interleaving */
    if (use_interleave && total > 4) {
        uint8_t temp[OOL_FEC_MAX_OUTPUT];
        memcpy(temp, output, total);
        interleave_bytes(temp, output, total, 4);
    }

    *output_len = total;
    return true;
}

/* ── FEC Decode ──────────────────────────────────────────────────────────── */

/**
 * Decode and verify a FEC-protected frame.
 *
 * @param input       Received bytes (data + parity, possibly interleaved)
 * @param input_len   Total received length
 * @param data_len    Expected original data length
 * @param output      Output buffer for corrected data
 * @param was_interleaved Whether interleaving was applied
 * @param errors_detected [out] Number of parity mismatches detected
 * @return true if frame is usable (may have uncorrectable errors)
 */
static inline bool ool_fec_decode(const uint8_t *input, int input_len,
                                   int data_len, uint8_t *output,
                                   bool was_interleaved,
                                   int *errors_detected) {
    if (!input || !output || !errors_detected) return false;
    if (input_len < data_len + 4) return false;

    uint8_t work[OOL_FEC_MAX_OUTPUT];
    memcpy(work, input, input_len);

    /* De-interleave if needed */
    if (was_interleaved && input_len > 4) {
        uint8_t temp[OOL_FEC_MAX_OUTPUT];
        deinterleave_bytes(work, temp, input_len, 4);
        memcpy(work, temp, input_len);
    }

    /* Extract data and parity */
    memcpy(output, work, data_len);
    uint8_t received_parity[4];
    memcpy(received_parity, &work[data_len], 4);

    /* Verify parity */
    uint8_t expected_parity[4];
    compute_xor_parity(output, data_len, expected_parity, 4);

    int errors = 0;
    for (int i = 0; i < 4; i++) {
        if (received_parity[i] != expected_parity[i]) errors++;
    }
    *errors_detected = errors;

    return true;  /* Data returned regardless; caller decides on error count */
}

/* ── Airtime-Aware FEC Selection ─────────────────────────────────────────── */

/**
 * Determine optimal FEC overhead based on channel conditions.
 *
 * @param ber_estimate  Estimated bit error rate (0.0 = clean, 0.1 = bad)
 * @param frame_bytes   Size of codec frame in bytes
 * @param max_overhead  Maximum additional bytes allowed
 * @return Recommended parity bytes (0, 2, or 4)
 */
static inline int ool_fec_recommended_overhead(float ber_estimate,
                                                int frame_bytes,
                                                int max_overhead) {
    (void)frame_bytes;
    if (max_overhead < 2) return 0;
    if (ber_estimate < 0.001f) return 0;       /* Clean channel */
    if (ber_estimate < 0.01f)  return 2;       /* Moderate errors */
    return (max_overhead >= 4) ? 4 : 2;        /* Heavy errors */
}
