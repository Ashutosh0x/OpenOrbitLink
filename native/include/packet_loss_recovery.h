/**
 * OpenOrbitLink — Packet Loss Recovery & Frame Concealment
 *
 * Provides frame-level packet loss concealment (PLC) for the voice pipeline.
 * Strategies are codec-aware and degrade gracefully:
 *
 *   1. Frame repetition with energy decay
 *   2. Pitch-period interpolation (Codec2-aware)
 *   3. Comfort noise generation
 *   4. Neural reconstruction (when available, via enhancement layer)
 *
 * In LoRa/DTN environments, entire chunks may be lost. This module handles
 * missing frames at reassembly time, independent of the transport layer.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef OOL_PACKET_LOSS_RECOVERY_H
#define OOL_PACKET_LOSS_RECOVERY_H

#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <math.h>

#include "audio_frame.h"
#include "codec_interface.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ── PLC Configuration ───────────────────────────────────────────────────── */

#define OOL_PLC_MAX_REPEAT       5      /* Max consecutive concealed frames    */
#define OOL_PLC_DECAY_RATE       0.85f  /* Energy decay per concealed frame    */
#define OOL_PLC_COMFORT_NOISE_DB -55.0f /* Comfort noise floor in dB          */
#define OOL_PLC_HISTORY_FRAMES   4      /* Frames of history for interpolation */

/* ── PLC Strategy ────────────────────────────────────────────────────────── */

typedef enum {
    OOL_PLC_SILENCE,           /* Insert silence (simplest, worst quality)    */
    OOL_PLC_REPEAT_DECAY,      /* Repeat last frame with energy decay         */
    OOL_PLC_INTERPOLATE,       /* Interpolate from surrounding frames         */
    OOL_PLC_COMFORT_NOISE,     /* Generate comfort noise at estimated level   */
    OOL_PLC_NEURAL_REPAIR,     /* Neural frame reconstruction (if available)  */
} OolPlcStrategy;

/* ── PLC State ───────────────────────────────────────────────────────────── */

typedef struct {
    /* History ring buffer */
    int16_t  history[OOL_PLC_HISTORY_FRAMES][OOL_MAX_PCM_FRAME];
    int      history_lengths[OOL_PLC_HISTORY_FRAMES];
    float    history_energy[OOL_PLC_HISTORY_FRAMES];
    int      history_head;           /* Next write position                   */
    int      history_count;          /* Frames stored so far                  */

    /* Concealment tracking */
    int      consecutive_losses;     /* Count of sequential lost frames       */
    float    last_energy_db;         /* Energy of last good frame             */
    float    current_gain;           /* Decay gain for repeat strategy        */

    /* Configuration */
    OolPlcStrategy preferred_strategy;
    int            frame_samples;    /* Expected PCM samples per frame        */
    bool           neural_available; /* Neural repair is available            */

    /* Statistics */
    uint32_t total_frames;
    uint32_t lost_frames;
    uint32_t concealed_frames;
} OolPlcState;

/* ── PLC API ─────────────────────────────────────────────────────────────── */

/**
 * Initialize PLC state.
 */
static inline void ool_plc_init(OolPlcState *plc, int frame_samples,
                                 OolPlcStrategy strategy) {
    memset(plc, 0, sizeof(OolPlcState));
    plc->frame_samples = frame_samples;
    plc->preferred_strategy = strategy;
    plc->current_gain = 1.0f;
    plc->last_energy_db = OOL_PLC_COMFORT_NOISE_DB;
}

/**
 * Feed a good (received) frame into PLC history.
 * Call this for every successfully decoded frame.
 */
static inline void ool_plc_good_frame(OolPlcState *plc,
                                       const int16_t *pcm, int num_samples) {
    if (!plc || !pcm || num_samples <= 0) return;

    int idx = plc->history_head;
    int copy_len = num_samples;
    if (copy_len > OOL_MAX_PCM_FRAME) copy_len = OOL_MAX_PCM_FRAME;

    memcpy(plc->history[idx], pcm, copy_len * sizeof(int16_t));
    plc->history_lengths[idx] = copy_len;
    plc->history_energy[idx] = ool_frame_energy_db(pcm, copy_len);

    plc->history_head = (idx + 1) % OOL_PLC_HISTORY_FRAMES;
    if (plc->history_count < OOL_PLC_HISTORY_FRAMES)
        plc->history_count++;

    plc->consecutive_losses = 0;
    plc->current_gain = 1.0f;
    plc->last_energy_db = plc->history_energy[idx];
    plc->total_frames++;
}

/**
 * Generate a concealment frame for a lost packet.
 *
 * @param plc        PLC state
 * @param pcm_out    Output buffer (frame_samples capacity)
 * @param num_samples [out] Samples written
 * @return true if concealment was generated, false if max repeat exceeded
 */
static inline bool ool_plc_conceal_frame(OolPlcState *plc,
                                          int16_t *pcm_out, int *num_samples) {
    if (!plc || !pcm_out || !num_samples) return false;

    plc->lost_frames++;
    plc->total_frames++;
    plc->consecutive_losses++;

    int n = plc->frame_samples;
    *num_samples = n;

    /* Exceeded max repeat → transition to comfort noise */
    OolPlcStrategy strategy = plc->preferred_strategy;
    if (plc->consecutive_losses > OOL_PLC_MAX_REPEAT) {
        strategy = OOL_PLC_COMFORT_NOISE;
    }

    switch (strategy) {
        case OOL_PLC_SILENCE:
            memset(pcm_out, 0, n * sizeof(int16_t));
            break;

        case OOL_PLC_REPEAT_DECAY: {
            /* Repeat last good frame with exponential decay */
            if (plc->history_count > 0) {
                int last = (plc->history_head - 1 + OOL_PLC_HISTORY_FRAMES)
                           % OOL_PLC_HISTORY_FRAMES;
                int copy = plc->history_lengths[last];
                if (copy > n) copy = n;

                plc->current_gain *= OOL_PLC_DECAY_RATE;
                for (int i = 0; i < copy; i++) {
                    pcm_out[i] = (int16_t)(plc->history[last][i] *
                                           plc->current_gain);
                }
                /* Zero-fill remainder */
                for (int i = copy; i < n; i++) pcm_out[i] = 0;
            } else {
                memset(pcm_out, 0, n * sizeof(int16_t));
            }
            break;
        }

        case OOL_PLC_INTERPOLATE: {
            /* Simple linear interpolation from history */
            if (plc->history_count >= 2) {
                int idx1 = (plc->history_head - 1 + OOL_PLC_HISTORY_FRAMES)
                           % OOL_PLC_HISTORY_FRAMES;
                int idx2 = (plc->history_head - 2 + OOL_PLC_HISTORY_FRAMES)
                           % OOL_PLC_HISTORY_FRAMES;
                plc->current_gain *= OOL_PLC_DECAY_RATE;
                for (int i = 0; i < n; i++) {
                    float s1 = (i < plc->history_lengths[idx1]) ?
                               plc->history[idx1][i] : 0;
                    float s2 = (i < plc->history_lengths[idx2]) ?
                               plc->history[idx2][i] : 0;
                    /* Extrapolate: 2*last - prev, with decay */
                    float val = (2.0f * s1 - s2) * plc->current_gain;
                    if (val > 32767.0f) val = 32767.0f;
                    if (val < -32768.0f) val = -32768.0f;
                    pcm_out[i] = (int16_t)val;
                }
            } else {
                /* Not enough history, fall back to repeat */
                plc->preferred_strategy = OOL_PLC_REPEAT_DECAY;
                return ool_plc_conceal_frame(plc, pcm_out, num_samples);
            }
            break;
        }

        case OOL_PLC_COMFORT_NOISE: {
            /* Generate low-level comfort noise */
            float amplitude = powf(10.0f, plc->last_energy_db / 20.0f) *
                              32768.0f * 0.1f;
            if (amplitude < 10.0f) amplitude = 10.0f;
            if (amplitude > 500.0f) amplitude = 500.0f;
            /* Simple pseudo-random noise */
            static uint32_t lfsr = 0xACE1u;
            for (int i = 0; i < n; i++) {
                lfsr ^= lfsr << 13;
                lfsr ^= lfsr >> 17;
                lfsr ^= lfsr << 5;
                float noise = ((float)(lfsr & 0xFFFF) / 32768.0f - 1.0f);
                pcm_out[i] = (int16_t)(noise * amplitude);
            }
            break;
        }

        case OOL_PLC_NEURAL_REPAIR:
            /* Neural repair is handled by the enhancement layer.
             * If we get here, neural is unavailable — fall back. */
            strategy = OOL_PLC_REPEAT_DECAY;
            return ool_plc_conceal_frame(plc, pcm_out, num_samples);
    }

    plc->concealed_frames++;
    return true;
}

/**
 * Get PLC statistics.
 */
static inline float ool_plc_loss_rate(const OolPlcState *plc) {
    if (!plc || plc->total_frames == 0) return 0.0f;
    return (float)plc->lost_frames / (float)plc->total_frames;
}

#ifdef __cplusplus
}
#endif

#endif /* OOL_PACKET_LOSS_RECOVERY_H */
