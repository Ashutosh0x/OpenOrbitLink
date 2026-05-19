/**
 * OpenOrbitLink — Audio Frame Structure
 *
 * Common audio frame container with metadata for DTN chunking, sequence
 * tracking, and codec identification. Used throughout the voice pipeline.
 *
 * Wire format for voice chunks sent over LoRa/DTN:
 * ┌────────┬───────┬──────┬──────┬───────┬──────────────┐
 * │ MAGIC  │MSG_ID │SEQ_NO│FLAGS │CODEC  │ PAYLOAD      │
 * │ 2 byte │4 byte │2 byte│1 byte│1 byte │ variable     │
 * └────────┴───────┴──────┴──────┴───────┴──────────────┘
 *  Total header: 10 bytes, leaving 70 bytes for payload in 80-byte LoRa frame
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef OOL_AUDIO_FRAME_H
#define OOL_AUDIO_FRAME_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>

#include "codec_interface.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ── Constants ───────────────────────────────────────────────────────────── */

#define OOL_VOICE_MAGIC          0x564D  /* "VM" — Voice Message                */
#define OOL_VOICE_HEADER_SIZE    10      /* Bytes in voice chunk header          */
#define OOL_LORA_MAX_FRAME       80      /* Max LoRa payload (ISM, duty-safe)    */
#define OOL_VOICE_MAX_PAYLOAD    (OOL_LORA_MAX_FRAME - OOL_VOICE_HEADER_SIZE)
#define OOL_MAX_PCM_FRAME        960     /* 48kHz * 20ms (Lyra max)              */
#define OOL_MAX_ENCODED_FRAME    24      /* Lyra 9200: ceil(184/8) = 23 bytes    */

/* ── Voice Chunk Flags ───────────────────────────────────────────────────── */

typedef enum {
    OOL_VFLAG_NONE           = 0x00,
    OOL_VFLAG_FIRST_CHUNK    = 0x01,   /* First chunk of a voice message       */
    OOL_VFLAG_LAST_CHUNK     = 0x02,   /* Last chunk of a voice message        */
    OOL_VFLAG_FEC_ATTACHED   = 0x04,   /* FEC parity bytes follow payload      */
    OOL_VFLAG_ENHANCED       = 0x08,   /* Neural enhancement was applied       */
    OOL_VFLAG_DTX_SILENCE    = 0x10,   /* Frame is silence (DTX mode)          */
    OOL_VFLAG_PRIORITY_SOS   = 0x20,   /* Emergency voice message              */
    OOL_VFLAG_ENCRYPTED      = 0x40,   /* Payload is encrypted (ISM only)      */
} OolVoiceFlags;

/* ── Audio Frame (in-memory) ─────────────────────────────────────────────── */

/**
 * In-memory representation of a single codec frame with metadata.
 * NOT the wire format — use ool_voice_chunk_t for serialization.
 */
typedef struct {
    OolCodecMode codec_mode;           /* Which codec produced this frame      */
    uint32_t     message_id;           /* Voice message this frame belongs to  */
    uint16_t     sequence_num;         /* Frame sequence within the message    */
    uint16_t     total_frames;         /* Total frames in the message (0=unknown)*/
    uint32_t     timestamp_ms;         /* Capture timestamp (monotonic ms)     */
    uint8_t      flags;                /* OolVoiceFlags bitmask                */

    /* Encoded data */
    uint8_t      encoded[OOL_MAX_ENCODED_FRAME];
    int          encoded_len;          /* Actual encoded bytes                 */

    /* Decoded PCM (populated after decode) */
    int16_t      pcm[OOL_MAX_PCM_FRAME];
    int          pcm_samples;          /* Actual sample count                  */

    /* Quality metrics */
    float        energy_db;            /* Frame energy in dB                   */
    float        ber_estimate;         /* Channel BER estimate (0 = clean)     */
    bool         is_lost;              /* Frame was not received               */
    bool         was_concealed;        /* Frame was reconstructed by PLC       */
} OolAudioFrame;

/* ── Voice Chunk (wire format) ───────────────────────────────────────────── */

/**
 * Serialized voice chunk for LoRa/DTN transport.
 * Multiple codec frames may be packed into one chunk.
 */
typedef struct {
    uint8_t  data[OOL_LORA_MAX_FRAME]; /* Complete serialized chunk            */
    int      length;                    /* Total bytes (header + payload)       */
    int      num_frames;               /* Number of codec frames in this chunk */
} OolVoiceChunk;

/* ── Frame Initialization ────────────────────────────────────────────────── */

static inline void ool_audio_frame_init(OolAudioFrame *frame) {
    memset(frame, 0, sizeof(OolAudioFrame));
    frame->codec_mode = OOL_CODEC_NONE;
}

/* ── Voice Chunk Serialization ───────────────────────────────────────────── */

/**
 * Serialize audio frames into a voice chunk for LoRa transport.
 *
 * @param chunk      Output chunk
 * @param frames     Array of encoded audio frames
 * @param num_frames Number of frames to pack
 * @param msg_id     Voice message ID
 * @param seq_start  Starting sequence number
 * @param flags      Chunk-level flags
 * @return Number of frames actually packed (limited by 80-byte LoRa frame)
 */
static inline int ool_voice_chunk_pack(
    OolVoiceChunk *chunk,
    const OolAudioFrame *frames,
    int num_frames,
    uint32_t msg_id,
    uint16_t seq_start,
    uint8_t flags)
{
    if (!chunk || !frames || num_frames <= 0) return 0;

    /* Write header */
    chunk->data[0] = (OOL_VOICE_MAGIC >> 8) & 0xFF;
    chunk->data[1] = OOL_VOICE_MAGIC & 0xFF;
    chunk->data[2] = (msg_id >> 24) & 0xFF;
    chunk->data[3] = (msg_id >> 16) & 0xFF;
    chunk->data[4] = (msg_id >>  8) & 0xFF;
    chunk->data[5] =  msg_id & 0xFF;
    chunk->data[6] = (seq_start >> 8) & 0xFF;
    chunk->data[7] =  seq_start & 0xFF;
    chunk->data[8] = flags;
    chunk->data[9] = (uint8_t)frames[0].codec_mode;

    int offset = OOL_VOICE_HEADER_SIZE;
    int packed = 0;

    for (int i = 0; i < num_frames; i++) {
        int needed = frames[i].encoded_len;
        if (offset + needed > OOL_LORA_MAX_FRAME) break;
        memcpy(&chunk->data[offset], frames[i].encoded, needed);
        offset += needed;
        packed++;
    }

    chunk->length = offset;
    chunk->num_frames = packed;
    return packed;
}

/**
 * Deserialize a voice chunk header.
 *
 * @param data       Raw chunk bytes
 * @param data_len   Length of data
 * @param msg_id     [out] Voice message ID
 * @param seq_num    [out] Sequence number
 * @param flags      [out] Chunk flags
 * @param codec_mode [out] Codec mode
 * @return Payload offset (bytes after header), or -1 on error
 */
static inline int ool_voice_chunk_unpack_header(
    const uint8_t *data, int data_len,
    uint32_t *msg_id, uint16_t *seq_num,
    uint8_t *flags, OolCodecMode *codec_mode)
{
    if (!data || data_len < OOL_VOICE_HEADER_SIZE) return -1;

    uint16_t magic = ((uint16_t)data[0] << 8) | data[1];
    if (magic != OOL_VOICE_MAGIC) return -1;

    *msg_id = ((uint32_t)data[2] << 24) | ((uint32_t)data[3] << 16) |
              ((uint32_t)data[4] <<  8) |  (uint32_t)data[5];
    *seq_num = ((uint16_t)data[6] << 8) | data[7];
    *flags = data[8];
    *codec_mode = (OolCodecMode)data[9];

    return OOL_VOICE_HEADER_SIZE;
}

/* ── Frame Energy Calculation ────────────────────────────────────────────── */

/**
 * Compute frame energy in dB from PCM samples.
 */
static inline float ool_frame_energy_db(const int16_t *pcm, int num_samples) {
    if (!pcm || num_samples <= 0) return -96.0f;
    double sum = 0.0;
    for (int i = 0; i < num_samples; i++) {
        double s = (double)pcm[i];
        sum += s * s;
    }
    double rms = sum / num_samples;
    if (rms < 1.0) return -96.0f;
    /* dB relative to full-scale int16 */
    return (float)(10.0 * log10(rms / (32768.0 * 32768.0)));
}

#ifdef __cplusplus
}
#endif

#endif /* OOL_AUDIO_FRAME_H */
