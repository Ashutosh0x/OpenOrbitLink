/**
 * OpenOrbitLink — Codec Registry
 *
 * Central registry of all available voice codecs. Provides codec enumeration,
 * capability queries, and factory creation. The adaptive codec manager uses
 * this registry to select the optimal codec for current link conditions.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef OOL_CODEC_REGISTRY_H
#define OOL_CODEC_REGISTRY_H

#include "codec_interface.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Maximum number of codecs that can be registered */
#define OOL_MAX_CODECS 16

/* ── Registry Entry ──────────────────────────────────────────────────────── */

typedef struct {
    OolCodecDescriptor  descriptor;
    /**
     * Factory function: allocate and initialize a codec instance.
     * @param mode  Requested mode (must match descriptor.mode)
     * @param model_path  Path to TFLite models (NULL for DSP codecs)
     * @return Initialized codec instance, or NULL on failure
     */
    OolCodecInstance* (*create)(OolCodecMode mode, const char *model_path);
    bool available;   /* true if runtime deps are satisfied */
} OolCodecRegistryEntry;

/* ── Registry API ────────────────────────────────────────────────────────── */

/**
 * Initialize the codec registry. Must be called once at startup.
 * Automatically registers all built-in codecs (Codec2 modes).
 * Neural codecs are registered conditionally based on model availability.
 */
void ool_registry_init(const char *model_base_path);

/**
 * Register a codec. Called by codec implementations during init.
 * @return OOL_OK or OOL_ERR_ALLOC_FAIL if registry is full
 */
OolError ool_registry_register(const OolCodecRegistryEntry *entry);

/**
 * Get number of registered codecs.
 */
int ool_registry_count(void);

/**
 * Get registry entry by index (0..count-1).
 */
const OolCodecRegistryEntry* ool_registry_get(int index);

/**
 * Find a registry entry by mode.
 * @return Entry pointer, or NULL if mode not registered
 */
const OolCodecRegistryEntry* ool_registry_find(OolCodecMode mode);

/**
 * Create a codec instance for the given mode.
 * @param mode        Desired codec mode
 * @param model_path  Path to neural model files (NULL for Codec2)
 * @return Initialized codec instance, or NULL on failure
 */
OolCodecInstance* ool_registry_create(OolCodecMode mode, const char *model_path);

/**
 * Find the best codec for given constraints.
 * @param max_bitrate_bps   Maximum bitrate allowed by link
 * @param require_lora_safe Only return codecs with LoRa-safe frame sizes
 * @param allow_neural      Whether neural codecs are permitted
 * @return Best matching mode, or OOL_CODEC_NONE if none available
 */
OolCodecMode ool_registry_best_for(int max_bitrate_bps,
                                    bool require_lora_safe,
                                    bool allow_neural);

/**
 * Get a sorted list of all available modes (ascending by bitrate).
 * @param modes_out  Output array (must hold OOL_MAX_CODECS entries)
 * @return Number of available modes written
 */
int ool_registry_available_modes(OolCodecMode *modes_out);

/**
 * Check if neural codecs are available (TFLite models present).
 */
bool ool_registry_neural_available(void);

/* ── Built-in Registration Functions ─────────────────────────────────────── */

/** Register all Codec2 modes. Called by ool_registry_init. */
void ool_register_codec2_modes(void);

/** Register Lyra neural modes. Called by ool_registry_init if models exist. */
void ool_register_lyra_modes(const char *model_path);

#ifdef __cplusplus
}
#endif

#endif /* OOL_CODEC_REGISTRY_H */
