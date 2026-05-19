/**
 * OpenOrbitLink — Voice Chunker
 *
 * Splits encoded voice frames into DTN-compatible chunks that fit within
 * LoRa frame-size limits. Handles chunking, sequence numbering, and
 * reassembly of voice messages for store-and-forward transport.
 *
 * LoRa Frame Budget:
 *   Total LoRa payload:  80 bytes (ISM, SF7-SF12 safe)
 *   Voice chunk header:  10 bytes (see audio_frame.h)
 *   Available payload:   70 bytes per chunk
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef OOL_VOICE_CHUNKER_H
#define OOL_VOICE_CHUNKER_H

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "audio_frame.h"
#include "codec_interface.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ── Chunker Limits ──────────────────────────────────────────────────────── */

#define OOL_MAX_VOICE_DURATION_S   30     /* Max voice message duration       */
#define OOL_MAX_FRAMES_PER_MSG     750    /* 30s / 40ms = 750 frames (700C)  */
#define OOL_MAX_CHUNKS_PER_MSG     128    /* Max chunks after chunking       */

/* ── Chunking Result ─────────────────────────────────────────────────────── */

typedef struct {
    OolVoiceChunk chunks[OOL_MAX_CHUNKS_PER_MSG];
    int           num_chunks;
    uint32_t      message_id;
    OolCodecMode  codec_mode;
    int           total_frames;
    int           total_audio_ms;
    int           total_bytes;         /* Sum of all chunk lengths            */
    float         lora_airtime_s;      /* Estimated LoRa airtime at 577 bps  */
} OolChunkResult;

/* ── Reassembly Buffer ───────────────────────────────────────────────────── */

typedef struct {
    uint32_t      message_id;
    OolCodecMode  codec_mode;
    bool          chunk_received[OOL_MAX_CHUNKS_PER_MSG];
    uint8_t       payload[OOL_MAX_CHUNKS_PER_MSG][OOL_VOICE_MAX_PAYLOAD];
    int           payload_len[OOL_MAX_CHUNKS_PER_MSG];
    int           expected_chunks;     /* From FIRST_CHUNK metadata          */
    int           received_count;
    uint32_t      first_received_ms;   /* Timestamp of first chunk           */
    uint32_t      last_received_ms;    /* Timestamp of last chunk            */
    bool          complete;
} OolReassemblyBuffer;

/* ── Chunker API ─────────────────────────────────────────────────────────── */

/**
 * Generate a unique voice message ID.
 */
static inline uint32_t ool_voice_msg_id(void) {
    static uint32_t counter = 0;
    /* Simple incrementing counter — sufficient for local uniqueness.
     * In production, combine with device_id hash. */
    return ++counter;
}

/**
 * Calculate how many codec frames fit in one LoRa chunk.
 *
 * @param frame_bytes  Encoded bytes per codec frame
 * @return Number of frames per chunk
 */
static inline int ool_frames_per_chunk(int frame_bytes) {
    if (frame_bytes <= 0) return 0;
    return OOL_VOICE_MAX_PAYLOAD / frame_bytes;
}

/**
 * Calculate number of chunks needed for a voice message.
 *
 * @param total_frames Total encoded frames in the message
 * @param frame_bytes  Bytes per encoded frame
 * @return Number of LoRa chunks needed
 */
static inline int ool_chunks_needed(int total_frames, int frame_bytes) {
    int fpc = ool_frames_per_chunk(frame_bytes);
    if (fpc <= 0) return 0;
    return (total_frames + fpc - 1) / fpc;
}

/**
 * Chunk encoded voice frames into LoRa-compatible chunks.
 *
 * @param frames      Array of encoded audio frames
 * @param num_frames  Total number of frames
 * @param codec_mode  Codec mode used for encoding
 * @param result      [out] Chunking result
 * @return true on success
 */
static inline bool ool_chunk_voice_message(
    const OolAudioFrame *frames, int num_frames,
    OolCodecMode codec_mode, OolChunkResult *result)
{
    if (!frames || !result || num_frames <= 0) return false;

    memset(result, 0, sizeof(OolChunkResult));
    result->message_id = ool_voice_msg_id();
    result->codec_mode = codec_mode;
    result->total_frames = num_frames;

    /* Determine frame size from first frame */
    int frame_bytes = frames[0].encoded_len;
    if (frame_bytes <= 0) return false;

    int fpc = ool_frames_per_chunk(frame_bytes);
    if (fpc <= 0) return false;

    int frame_idx = 0;
    int chunk_idx = 0;

    while (frame_idx < num_frames && chunk_idx < OOL_MAX_CHUNKS_PER_MSG) {
        int batch = num_frames - frame_idx;
        if (batch > fpc) batch = fpc;

        uint8_t flags = OOL_VFLAG_NONE;
        if (chunk_idx == 0) flags |= OOL_VFLAG_FIRST_CHUNK;

        /* Check if this is the last chunk */
        if (frame_idx + batch >= num_frames) flags |= OOL_VFLAG_LAST_CHUNK;

        int packed = ool_voice_chunk_pack(
            &result->chunks[chunk_idx],
            &frames[frame_idx],
            batch,
            result->message_id,
            (uint16_t)chunk_idx,
            flags);

        if (packed <= 0) break;

        result->total_bytes += result->chunks[chunk_idx].length;
        frame_idx += packed;
        chunk_idx++;
    }

    result->num_chunks = chunk_idx;

    /* Calculate audio duration */
    const OolCodecDescriptor *desc = NULL;
    /* Inline lookup for frame_ms */
    int frame_ms = 40;
    if (codec_mode == OOL_CODEC_C2_2400 || codec_mode == OOL_CODEC_C2_3200 ||
        codec_mode >= OOL_CODEC_LYRA_3200) {
        frame_ms = 20;
    }
    result->total_audio_ms = num_frames * frame_ms;

    /* Estimate LoRa airtime at 577 bps effective */
    result->lora_airtime_s = (float)(result->total_bytes * 8) / 577.0f;

    return chunk_idx > 0;
}

/* ── Reassembly API ──────────────────────────────────────────────────────── */

/**
 * Initialize a reassembly buffer for a new message.
 */
static inline void ool_reassembly_init(OolReassemblyBuffer *buf,
                                        uint32_t message_id) {
    memset(buf, 0, sizeof(OolReassemblyBuffer));
    buf->message_id = message_id;
}

/**
 * Feed a received chunk into the reassembly buffer.
 *
 * @param buf   Reassembly buffer
 * @param chunk Received voice chunk
 * @param now_ms Current timestamp in milliseconds
 * @return true if the message is now complete
 */
static inline bool ool_reassembly_add_chunk(
    OolReassemblyBuffer *buf,
    const OolVoiceChunk *chunk,
    uint32_t now_ms)
{
    if (!buf || !chunk || chunk->length < OOL_VOICE_HEADER_SIZE) return false;

    /* Parse header */
    uint32_t msg_id;
    uint16_t seq_num;
    uint8_t flags;
    OolCodecMode mode;
    int payload_offset = ool_voice_chunk_unpack_header(
        chunk->data, chunk->length, &msg_id, &seq_num, &flags, &mode);

    if (payload_offset < 0) return false;
    if (msg_id != buf->message_id) return false;
    if (seq_num >= OOL_MAX_CHUNKS_PER_MSG) return false;

    /* Store payload */
    int payload_len = chunk->length - payload_offset;
    if (payload_len > OOL_VOICE_MAX_PAYLOAD) return false;

    if (!buf->chunk_received[seq_num]) {
        memcpy(buf->payload[seq_num], &chunk->data[payload_offset], payload_len);
        buf->payload_len[seq_num] = payload_len;
        buf->chunk_received[seq_num] = true;
        buf->received_count++;
        buf->codec_mode = mode;

        if (buf->first_received_ms == 0) buf->first_received_ms = now_ms;
        buf->last_received_ms = now_ms;
    }

    /* Check if we have the last chunk to know expected count */
    if (flags & OOL_VFLAG_LAST_CHUNK) {
        buf->expected_chunks = seq_num + 1;
    }

    /* Check completeness */
    if (buf->expected_chunks > 0 && buf->received_count >= buf->expected_chunks) {
        buf->complete = true;
    }

    return buf->complete;
}

/**
 * Get the loss rate for a partially received message.
 */
static inline float ool_reassembly_loss_rate(const OolReassemblyBuffer *buf) {
    if (!buf || buf->expected_chunks <= 0) return 0.0f;
    int missing = buf->expected_chunks - buf->received_count;
    return (float)missing / (float)buf->expected_chunks;
}

#ifdef __cplusplus
}
#endif

#endif /* OOL_VOICE_CHUNKER_H */
