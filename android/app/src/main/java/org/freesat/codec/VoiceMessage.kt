package org.freesat.codec

/**
 * VoiceMessage — Data class representing an encoded voice message.
 *
 * Contains all encoded frames, metadata for DTN transport, and
 * pre-computed chunking information for LoRa transmission.
 *
 * This is the unit that flows from PushToTalkEngine → DTN BundleStore.
 */
data class VoiceMessage(
    /** Unique message identifier */
    val messageId: Long,

    /** Codec mode used for encoding */
    val codecMode: CodecMode,

    /** Encoded audio frames (each frame is codec-specific bytes) */
    val frames: List<ByteArray>,

    /** Total voice duration in milliseconds */
    val durationMs: Int,

    /** Sample rate used during capture */
    val sampleRate: Int = 8000,

    /** Total number of encoded frames */
    val totalFrames: Int,

    /** Unix timestamp of recording */
    val timestamp: Long,

    /** Optional: sender node ID for mesh routing */
    val senderNodeId: String? = null,

    /** Optional: recipient node ID (null for broadcast) */
    val recipientNodeId: String? = null,

    /** Priority level (0=normal, 1=voice, 2=SOS) */
    val priority: Int = 1,
) {
    /** Total encoded bytes across all frames */
    val totalBytes: Int
        get() = frames.sumOf { it.size }

    /** Bytes per frame */
    val bytesPerFrame: Int
        get() = codecMode.frameBytes

    /** Estimated number of LoRa chunks needed (80-byte limit, 10-byte header) */
    val estimatedChunks: Int
        get() {
            val payloadPerChunk = 70  // 80 - 10 header bytes
            val framesPerChunk = payloadPerChunk / bytesPerFrame
            return if (framesPerChunk > 0) (totalFrames + framesPerChunk - 1) / framesPerChunk else totalFrames
        }

    /** Estimated LoRa airtime at 577 bps effective rate */
    val estimatedAirtimeS: Float
        get() = (totalBytes * 8).toFloat() / 577f

    /** Duration formatted as M:SS */
    val durationFormatted: String
        get() {
            val seconds = durationMs / 1000
            return "${seconds / 60}:${(seconds % 60).toString().padStart(2, '0')}"
        }

    /** Check if this message fits in the ISM duty cycle budget (36s/hour) */
    fun fitsInDutyCycle(usedAirtimeS: Float = 0f): Boolean {
        val budget = 36f - usedAirtimeS
        return estimatedAirtimeS <= budget
    }

    /** Chunk the encoded frames for LoRa transport */
    fun toChunks(): List<VoiceChunk> {
        val payloadPerChunk = 70
        val framesPerChunk = payloadPerChunk / bytesPerFrame
        if (framesPerChunk <= 0) return emptyList()

        val chunks = mutableListOf<VoiceChunk>()
        var frameIdx = 0
        var seqNum = 0

        while (frameIdx < frames.size) {
            val batchEnd = minOf(frameIdx + framesPerChunk, frames.size)
            val batchFrames = frames.subList(frameIdx, batchEnd)

            // Serialize chunk
            val payload = ByteArray(batchFrames.sumOf { it.size })
            var offset = 0
            for (frame in batchFrames) {
                frame.copyInto(payload, offset)
                offset += frame.size
            }

            chunks.add(VoiceChunk(
                messageId = messageId,
                sequenceNum = seqNum,
                codecModeId = codecMode.nativeId,
                isFirst = seqNum == 0,
                isLast = batchEnd >= frames.size,
                payload = payload,
                frameCount = batchFrames.size,
            ))

            frameIdx = batchEnd
            seqNum++
        }

        return chunks
    }

    /** Summary for logging */
    override fun toString(): String {
        return "VoiceMessage(id=$messageId, codec=${codecMode.displayName}, " +
               "frames=$totalFrames, duration=${durationFormatted}, " +
               "bytes=$totalBytes, chunks=$estimatedChunks, " +
               "airtime=${String.format("%.1f", estimatedAirtimeS)}s)"
    }
}

/**
 * VoiceChunk — One LoRa-sized chunk of a voice message.
 * Ready for DTN BundleStore queueing.
 */
data class VoiceChunk(
    val messageId: Long,
    val sequenceNum: Int,
    val codecModeId: Int,
    val isFirst: Boolean,
    val isLast: Boolean,
    val payload: ByteArray,
    val frameCount: Int,
) {
    /** Total wire size including 10-byte voice header */
    val wireSize: Int get() = 10 + payload.size

    /** Serialize to wire format (matching native ool_voice_chunk_pack) */
    fun serialize(): ByteArray {
        val data = ByteArray(wireSize)
        // Magic: "VM" = 0x564D
        data[0] = 0x56
        data[1] = 0x4D
        // Message ID (4 bytes, big-endian)
        data[2] = ((messageId shr 24) and 0xFF).toByte()
        data[3] = ((messageId shr 16) and 0xFF).toByte()
        data[4] = ((messageId shr 8) and 0xFF).toByte()
        data[5] = (messageId and 0xFF).toByte()
        // Sequence number (2 bytes)
        data[6] = ((sequenceNum shr 8) and 0xFF).toByte()
        data[7] = (sequenceNum and 0xFF).toByte()
        // Flags
        var flags = 0
        if (isFirst) flags = flags or 0x01
        if (isLast) flags = flags or 0x02
        data[8] = flags.toByte()
        // Codec mode
        data[9] = codecModeId.toByte()
        // Payload
        payload.copyInto(data, 10)
        return data
    }

    companion object {
        /** Deserialize from wire format */
        fun deserialize(data: ByteArray): VoiceChunk? {
            if (data.size < 10) return null
            if (data[0] != 0x56.toByte() || data[1] != 0x4D.toByte()) return null

            val msgId = ((data[2].toLong() and 0xFF) shl 24) or
                        ((data[3].toLong() and 0xFF) shl 16) or
                        ((data[4].toLong() and 0xFF) shl 8) or
                        (data[5].toLong() and 0xFF)
            val seqNum = ((data[6].toInt() and 0xFF) shl 8) or
                         (data[7].toInt() and 0xFF)
            val flags = data[8].toInt() and 0xFF
            val codecMode = data[9].toInt() and 0xFF
            val payload = data.copyOfRange(10, data.size)

            return VoiceChunk(
                messageId = msgId,
                sequenceNum = seqNum,
                codecModeId = codecMode,
                isFirst = (flags and 0x01) != 0,
                isLast = (flags and 0x02) != 0,
                payload = payload,
                frameCount = 0, // Unknown at deserialization
            )
        }
    }

    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is VoiceChunk) return false
        return messageId == other.messageId && sequenceNum == other.sequenceNum
    }

    override fun hashCode(): Int = 31 * messageId.hashCode() + sequenceNum
}

/**
 * AirtimeTracker — ISM duty-cycle aware transmission gating.
 *
 * Tracks LoRa transmit time to enforce the 1% ISM duty cycle limit
 * (36 seconds per hour). Voice chunks are only permitted if budget allows.
 */
class AirtimeTracker(
    private val dutyCyclePercent: Int = 1,
    private val windowSeconds: Int = 3600,
) {
    private var usedSeconds: Float = 0f
    private var windowStartMs: Long = System.currentTimeMillis()
    private var txCount: Int = 0

    /** Maximum TX time per window */
    val maxTxSeconds: Float = dutyCyclePercent * windowSeconds / 100f

    /** Remaining TX budget in seconds */
    val remainingSeconds: Float
        get() {
            rollWindow()
            return (maxTxSeconds - usedSeconds).coerceAtLeast(0f)
        }

    /** Remaining budget as percentage */
    val remainingPercent: Float
        get() = if (maxTxSeconds > 0) remainingSeconds / maxTxSeconds * 100f else 0f

    /**
     * Check if a transmission is allowed.
     * @param txSeconds Duration of proposed TX
     * @return true if within budget
     */
    fun canTransmit(txSeconds: Float): Boolean {
        rollWindow()
        return (usedSeconds + txSeconds) <= maxTxSeconds
    }

    /**
     * Record a completed transmission.
     */
    fun recordTx(txSeconds: Float) {
        rollWindow()
        usedSeconds += txSeconds
        txCount++
    }

    /**
     * Check if a voice message fits in the remaining budget.
     */
    fun canSendMessage(message: VoiceMessage): Boolean {
        return canTransmit(message.estimatedAirtimeS)
    }

    private fun rollWindow() {
        val now = System.currentTimeMillis()
        val elapsed = (now - windowStartMs) / 1000f
        if (elapsed >= windowSeconds) {
            windowStartMs = now
            usedSeconds = 0f
        }
    }

    override fun toString(): String {
        return "AirtimeTracker(remaining=${String.format("%.1f", remainingSeconds)}s / " +
               "${String.format("%.0f", maxTxSeconds)}s, tx=$txCount)"
    }
}
