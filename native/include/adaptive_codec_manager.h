/**
 * OpenOrbitLink — Adaptive Codec Manager
 *
 * Intelligence layer that selects the optimal codec based on current link
 * conditions, device state, and regulatory constraints. Sits between the
 * PTT engine and the codec implementations.
 *
 * Decision inputs:
 *   - Estimated link bandwidth (bps)
 *   - Packet loss rate
 *   - LoRa airtime budget remaining
 *   - Battery level
 *   - CPU thermal state
 *   - Active transmit band
 *   - Neural model availability
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef OOL_ADAPTIVE_CODEC_MANAGER_H
#define OOL_ADAPTIVE_CODEC_MANAGER_H

#include <stdint.h>
#include <stdbool.h>

#include "codec_interface.h"
#include "neural_enhancer.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ── Link Condition Assessment ───────────────────────────────────────────── */

typedef enum {
    OOL_LINK_LORA_ISM       = 0,   /* LoRa ISM 868/915 MHz                  */
    OOL_LINK_LORA_SATELLITE = 1,   /* LoRa LEO satellite (FOSSA/Lacuna)     */
    OOL_LINK_BLE_MESH       = 2,   /* Bluetooth Low Energy mesh             */
    OOL_LINK_WIFI_LOCAL     = 3,   /* Local WiFi (no internet)              */
    OOL_LINK_WIFI_INTERNET  = 4,   /* WiFi with internet                    */
    OOL_LINK_NTN_CARRIER    = 5,   /* Carrier NTN (Starlink/Iridium)        */
    OOL_LINK_UNKNOWN        = 6,
} OolLinkType;

typedef struct {
    OolLinkType link_type;
    int         bandwidth_bps;        /* Estimated available bandwidth        */
    float       packet_loss_rate;     /* 0.0 - 1.0                           */
    int         rtt_ms;               /* Round-trip time (-1 = unknown/DTN)   */
    float       snr_db;               /* Signal-to-noise ratio                */
    float       ber_estimate;         /* Bit error rate estimate              */
} OolLinkCondition;

/* ── Device State ────────────────────────────────────────────────────────── */

typedef enum {
    OOL_THERMAL_NORMAL      = 0,
    OOL_THERMAL_WARM        = 1,
    OOL_THERMAL_HOT         = 2,    /* Throttle neural inference             */
    OOL_THERMAL_CRITICAL    = 3,    /* Disable all optional processing       */
} OolThermalState;

typedef struct {
    int              battery_percent;    /* 0-100                             */
    OolThermalState  thermal;
    bool             power_saving;       /* OS power-saving mode active       */
    bool             charging;           /* Device is charging                */
} OolDeviceState;

/* ── Transmit Band Constraints ───────────────────────────────────────────── */

typedef enum {
    OOL_BAND_ISM            = 0,    /* ISM band — encryption allowed         */
    OOL_BAND_AMATEUR        = 1,    /* Amateur — plaintext only, Codec2 only */
    OOL_BAND_LICENSED       = 2,    /* Licensed — full capability            */
    OOL_BAND_NTN            = 3,    /* Carrier NTN                           */
} OolBandConstraint;

/* ── Airtime Budget ──────────────────────────────────────────────────────── */

typedef struct {
    float    budget_seconds;           /* Total TX time budget per hour       */
    float    used_seconds;             /* TX time used in current hour        */
    float    remaining_seconds;        /* Budget remaining                    */
    int      duty_cycle_percent;       /* Regulatory duty cycle (1% ISM)     */
} OolAirtimeBudget;

/* ── Codec Decision ──────────────────────────────────────────────────────── */

typedef struct {
    OolCodecMode   selected_mode;      /* Chosen codec mode                  */
    bool           neural_enhance;     /* Apply neural enhancement on RX     */
    bool           fec_enabled;        /* Add FEC protection                 */
    int            fec_overhead_bytes;  /* Additional FEC bytes               */
    bool           interleave;         /* Apply byte interleaving            */
    float          confidence;         /* Decision confidence (0-1)          */
    const char    *reason;             /* Human-readable decision reason     */
} OolCodecDecision;

/* ── Manager State (opaque) ──────────────────────────────────────────────── */

typedef struct OolAdaptiveCodecManager OolAdaptiveCodecManager;

/* ── Manager API ─────────────────────────────────────────────────────────── */

/**
 * Create the adaptive codec manager.
 * @param model_path  Path to TFLite models (or NULL if neural unavailable)
 * @return Manager handle
 */
OolAdaptiveCodecManager* ool_acm_create(const char *model_path);

/**
 * Select the optimal codec for current conditions.
 *
 * @param mgr     Manager handle
 * @param link    Current link conditions
 * @param device  Current device state
 * @param band    Transmit band constraints
 * @param airtime Current airtime budget
 * @return Codec decision
 */
OolCodecDecision ool_acm_select(
    OolAdaptiveCodecManager *mgr,
    const OolLinkCondition *link,
    const OolDeviceState *device,
    OolBandConstraint band,
    const OolAirtimeBudget *airtime);

/**
 * Force a specific codec mode (overrides adaptive selection).
 * Pass OOL_CODEC_NONE to re-enable adaptive mode.
 */
void ool_acm_force_mode(OolAdaptiveCodecManager *mgr, OolCodecMode mode);

/**
 * Get the currently active codec instance.
 */
OolCodecInstance* ool_acm_get_codec(OolAdaptiveCodecManager *mgr);

/**
 * Get the neural enhancer (if available).
 */
OolNeuralEnhancer* ool_acm_get_enhancer(OolAdaptiveCodecManager *mgr);

/**
 * Update link conditions (triggers re-evaluation).
 */
void ool_acm_update_link(OolAdaptiveCodecManager *mgr,
                          const OolLinkCondition *link);

/**
 * Update device state (triggers re-evaluation).
 */
void ool_acm_update_device(OolAdaptiveCodecManager *mgr,
                            const OolDeviceState *device);

/**
 * Get manager statistics.
 */
typedef struct {
    uint32_t      total_decisions;
    uint32_t      mode_switches;
    OolCodecMode  current_mode;
    bool          neural_active;
    float         avg_decision_ms;
    /* Mode usage histogram */
    uint32_t      codec2_700c_frames;
    uint32_t      codec2_1300_frames;
    uint32_t      codec2_3200_frames;
    uint32_t      lyra_3200_frames;
    uint32_t      lyra_6000_frames;
    uint32_t      lyra_9200_frames;
} OolAcmStats;

OolAcmStats ool_acm_get_stats(const OolAdaptiveCodecManager *mgr);

/**
 * Destroy manager and all managed codecs.
 */
void ool_acm_destroy(OolAdaptiveCodecManager *mgr);

#ifdef __cplusplus
}
#endif

#endif /* OOL_ADAPTIVE_CODEC_MANAGER_H */
