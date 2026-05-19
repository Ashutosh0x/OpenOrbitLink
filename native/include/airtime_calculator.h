/**
 * OpenOrbitLink — LoRa Airtime Calculator
 *
 * Calculates exact LoRa on-air time for packets and tracks ISM duty-cycle
 * budget compliance. Based on Semtech SX1276/SX1262 timing formulas.
 *
 * Regulatory duty cycles:
 *   EU868 (ETSI EN 300.220):  1% (36 seconds per hour)
 *   US915 (FCC Part 15.247):  No duty cycle, but dwell time < 400ms
 *   IN865 (WPC):              1% duty cycle
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef OOL_AIRTIME_CALCULATOR_H
#define OOL_AIRTIME_CALCULATOR_H

#include <stdint.h>
#include <stdbool.h>
#include <math.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ── LoRa Parameters ─────────────────────────────────────────────────────── */

typedef enum {
    OOL_SF7  = 7,
    OOL_SF8  = 8,
    OOL_SF9  = 9,
    OOL_SF10 = 10,
    OOL_SF11 = 11,
    OOL_SF12 = 12,
} OolSpreadingFactor;

typedef enum {
    OOL_BW_125  = 125000,   /* 125 kHz — standard, best range             */
    OOL_BW_250  = 250000,   /* 250 kHz — higher throughput                 */
    OOL_BW_500  = 500000,   /* 500 kHz — US915 uplink                      */
} OolBandwidth;

typedef enum {
    OOL_CR_4_5 = 1,          /* 4/5 coding rate (20% overhead)             */
    OOL_CR_4_6 = 2,          /* 4/6 coding rate (50% overhead)             */
    OOL_CR_4_7 = 3,          /* 4/7 coding rate (75% overhead)             */
    OOL_CR_4_8 = 4,          /* 4/8 coding rate (100% overhead)            */
} OolCodingRate;

typedef struct {
    OolSpreadingFactor sf;
    OolBandwidth       bw;
    OolCodingRate      cr;
    int                preamble_symbols;  /* 8 is standard                  */
    bool               explicit_header;   /* true for explicit header mode  */
    bool               crc_on;            /* CRC enabled                    */
    bool               low_data_rate_opt; /* Low data rate optimization     */
} OolLoraParams;

/* ── Default Parameters ──────────────────────────────────────────────────── */

static inline OolLoraParams ool_lora_defaults(void) {
    OolLoraParams p;
    p.sf = OOL_SF7;
    p.bw = OOL_BW_125;
    p.cr = OOL_CR_4_5;
    p.preamble_symbols = 8;
    p.explicit_header = true;
    p.crc_on = true;
    p.low_data_rate_opt = false;
    return p;
}

/* ── Airtime Calculation ─────────────────────────────────────────────────── */

/**
 * Calculate symbol duration in milliseconds.
 */
static inline float ool_lora_symbol_ms(const OolLoraParams *p) {
    return (float)(1 << p->sf) / ((float)p->bw / 1000.0f);
}

/**
 * Calculate preamble duration in milliseconds.
 */
static inline float ool_lora_preamble_ms(const OolLoraParams *p) {
    float t_sym = ool_lora_symbol_ms(p);
    return (p->preamble_symbols + 4.25f) * t_sym;
}

/**
 * Calculate payload symbol count.
 * Based on Semtech SX1276 datasheet formula.
 */
static inline int ool_lora_payload_symbols(const OolLoraParams *p,
                                            int payload_bytes) {
    int sf = (int)p->sf;
    int de = p->low_data_rate_opt ? 1 : 0;
    int ih = p->explicit_header ? 0 : 1;
    int crc = p->crc_on ? 1 : 0;

    /* Numerator: 8*PL - 4*SF + 28 + 16*CRC - 20*IH */
    float num = 8.0f * payload_bytes - 4.0f * sf + 28.0f +
                16.0f * crc - 20.0f * ih;
    if (num < 0) num = 0;

    /* Denominator: 4*(SF - 2*DE) */
    float den = 4.0f * (sf - 2.0f * de);
    if (den <= 0) den = 1.0f;

    int n_payload = (int)ceilf(num / den) * ((int)p->cr + 4);
    if (n_payload < 0) n_payload = 0;

    return 8 + n_payload;  /* 8 minimum payload symbols */
}

/**
 * Calculate total on-air time in milliseconds for a LoRa packet.
 *
 * @param p              LoRa radio parameters
 * @param payload_bytes  Number of payload bytes
 * @return On-air time in milliseconds
 */
static inline float ool_lora_airtime_ms(const OolLoraParams *p,
                                         int payload_bytes) {
    float t_sym = ool_lora_symbol_ms(p);
    float t_preamble = ool_lora_preamble_ms(p);
    int n_payload = ool_lora_payload_symbols(p, payload_bytes);
    float t_payload = n_payload * t_sym;
    return t_preamble + t_payload;
}

/**
 * Calculate effective bitrate in bps for given parameters.
 */
static inline float ool_lora_effective_bitrate(const OolLoraParams *p,
                                                int payload_bytes) {
    float airtime_s = ool_lora_airtime_ms(p, payload_bytes) / 1000.0f;
    if (airtime_s <= 0) return 0;
    return (payload_bytes * 8.0f) / airtime_s;
}

/* ── Duty Cycle Tracker ──────────────────────────────────────────────────── */

typedef struct {
    float    duty_cycle_limit;      /* e.g., 0.01 for 1%                    */
    float    window_seconds;         /* Tracking window (3600 = 1 hour)      */
    float    max_tx_seconds;         /* duty_cycle_limit * window_seconds    */
    float    used_tx_seconds;        /* TX time used in current window       */
    uint32_t window_start_epoch;     /* Window start (Unix seconds)          */
    uint32_t last_tx_epoch;          /* Last TX timestamp                    */
    uint32_t tx_count;               /* Number of transmissions              */
} OolDutyCycleTracker;

/**
 * Initialize duty cycle tracker.
 *
 * @param tracker        Tracker state
 * @param duty_percent   Duty cycle limit (1 = 1%)
 * @param now_epoch      Current Unix timestamp
 */
static inline void ool_duty_init(OolDutyCycleTracker *tracker,
                                  int duty_percent,
                                  uint32_t now_epoch) {
    tracker->duty_cycle_limit = (float)duty_percent / 100.0f;
    tracker->window_seconds = 3600.0f;  /* 1 hour window */
    tracker->max_tx_seconds = tracker->duty_cycle_limit *
                               tracker->window_seconds;
    tracker->used_tx_seconds = 0.0f;
    tracker->window_start_epoch = now_epoch;
    tracker->last_tx_epoch = 0;
    tracker->tx_count = 0;
}

/**
 * Check if a transmission of given duration is allowed.
 *
 * @param tracker       Tracker state
 * @param tx_seconds    Duration of proposed transmission
 * @param now_epoch     Current Unix timestamp
 * @return true if transmission is within duty cycle budget
 */
static inline bool ool_duty_can_transmit(OolDutyCycleTracker *tracker,
                                          float tx_seconds,
                                          uint32_t now_epoch) {
    /* Roll window if needed */
    float elapsed = (float)(now_epoch - tracker->window_start_epoch);
    if (elapsed >= tracker->window_seconds) {
        tracker->window_start_epoch = now_epoch;
        tracker->used_tx_seconds = 0.0f;
    }

    return (tracker->used_tx_seconds + tx_seconds) <=
           tracker->max_tx_seconds;
}

/**
 * Record a completed transmission.
 */
static inline void ool_duty_record_tx(OolDutyCycleTracker *tracker,
                                       float tx_seconds,
                                       uint32_t now_epoch) {
    tracker->used_tx_seconds += tx_seconds;
    tracker->last_tx_epoch = now_epoch;
    tracker->tx_count++;
}

/**
 * Get remaining TX budget in seconds.
 */
static inline float ool_duty_remaining(const OolDutyCycleTracker *tracker) {
    float remaining = tracker->max_tx_seconds - tracker->used_tx_seconds;
    return (remaining > 0) ? remaining : 0.0f;
}

/**
 * Get remaining TX budget as percentage.
 */
static inline float ool_duty_remaining_percent(
    const OolDutyCycleTracker *tracker) {
    if (tracker->max_tx_seconds <= 0) return 0.0f;
    return ool_duty_remaining(tracker) / tracker->max_tx_seconds * 100.0f;
}

/* ── Voice Message Airtime Estimation ────────────────────────────────────── */

/**
 * Estimate total LoRa airtime for a voice message.
 *
 * @param lora_params    LoRa radio parameters
 * @param num_chunks     Number of chunks to transmit
 * @param chunk_bytes    Average bytes per chunk
 * @param inter_pkt_ms   Inter-packet gap in milliseconds
 * @return Total airtime in seconds
 */
static inline float ool_voice_airtime_estimate(
    const OolLoraParams *lora_params,
    int num_chunks, int chunk_bytes, float inter_pkt_ms)
{
    float total_ms = 0;
    for (int i = 0; i < num_chunks; i++) {
        total_ms += ool_lora_airtime_ms(lora_params, chunk_bytes);
        if (i < num_chunks - 1) total_ms += inter_pkt_ms;
    }
    return total_ms / 1000.0f;
}

/**
 * Check if a voice message fits within the remaining duty cycle budget.
 */
static inline bool ool_voice_fits_budget(
    const OolDutyCycleTracker *tracker,
    const OolLoraParams *lora_params,
    int num_chunks, int chunk_bytes)
{
    float airtime = ool_voice_airtime_estimate(
        lora_params, num_chunks, chunk_bytes, 100.0f);
    float remaining = ool_duty_remaining(tracker);
    return airtime <= remaining;
}

#ifdef __cplusplus
}
#endif

#endif /* OOL_AIRTIME_CALCULATOR_H */
