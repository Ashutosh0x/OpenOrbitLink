package org.freesat.codec

import android.util.Log
import org.json.JSONObject

/**
 * VoiceCodecManager — Kotlin interface to the native hybrid voice pipeline.
 *
 * Manages codec lifecycle, adaptive mode selection, encoding/decoding,
 * packet loss concealment, and airtime tracking through a unified JNI bridge.
 *
 * Usage:
 *   val mgr = VoiceCodecManager()
 *   mgr.init(CodecMode.CODEC2_700C)
 *   val encoded = mgr.encode(pcmSamples)
 *   val decoded = mgr.decode(encoded)
 *   mgr.destroy()
 */
class VoiceCodecManager {

    companion object {
        private const val TAG = "VoiceCodecManager"

        init {
            try {
                System.loadLibrary("ool_voice_jni")
                Log.i(TAG, "Native voice library loaded")
            } catch (e: UnsatisfiedLinkError) {
                Log.w(TAG, "Native library not available: ${e.message}")
            }
        }
    }

    private var handle: Long = 0
    private var isInitialized = false
    private var currentMode: CodecMode = CodecMode.CODEC2_700C

    /**
     * Initialize the voice pipeline with a specific codec mode.
     */
    fun init(mode: CodecMode = CodecMode.CODEC2_700C, modelPath: String? = null): Boolean {
        return try {
            handle = nativeCreatePipeline(mode.nativeId, modelPath ?: "")
            isInitialized = handle != 0L
            currentMode = mode
            if (isInitialized) {
                Log.i(TAG, "Pipeline initialized: ${mode.displayName} @ ${mode.bitrateBps} bps")
            }
            isInitialized
        } catch (e: UnsatisfiedLinkError) {
            Log.w(TAG, "JNI not available: ${e.message}")
            false
        }
    }

    /**
     * Encode one frame of PCM audio.
     * @param pcmSamples PCM samples (frame_samples count at 8kHz)
     * @return Encoded bytes, or null on failure
     */
    fun encode(pcmSamples: ShortArray): ByteArray? {
        if (!isInitialized) return null
        return try {
            nativeEncode(handle, pcmSamples)
        } catch (e: Exception) {
            Log.e(TAG, "Encode failed: ${e.message}")
            null
        }
    }

    /**
     * Decode one frame of encoded audio.
     * @param encodedData Encoded codec frame bytes
     * @return PCM samples, or null on failure
     */
    fun decode(encodedData: ByteArray): ShortArray? {
        if (!isInitialized) return null
        return try {
            nativeDecode(handle, encodedData)
        } catch (e: Exception) {
            Log.e(TAG, "Decode failed: ${e.message}")
            null
        }
    }

    /**
     * Generate a concealment frame for a lost packet (PLC).
     * Uses repeat-with-decay strategy.
     */
    fun concealLostFrame(): ShortArray? {
        if (!isInitialized) return null
        return try {
            nativeConcealFrame(handle)
        } catch (e: Exception) {
            Log.e(TAG, "PLC failed: ${e.message}")
            null
        }
    }

    /**
     * Switch codec mode dynamically.
     * @param mode New codec mode
     * @return true if switch was successful
     */
    fun setMode(mode: CodecMode): Boolean {
        if (!isInitialized) return false
        val success = nativeSetMode(handle, mode.nativeId)
        if (success) {
            currentMode = mode
            Log.i(TAG, "Mode switched to ${mode.displayName}")
        }
        return success
    }

    /**
     * Get the current codec mode.
     */
    fun getMode(): CodecMode = currentMode

    /**
     * Get number of PCM samples per frame.
     */
    fun getFrameSamples(): Int {
        return if (isInitialized) nativeGetFrameSamples(handle)
        else currentMode.frameSamples
    }

    /**
     * Get current bitrate in bps.
     */
    fun getBitrate(): Int {
        return if (isInitialized) nativeGetBitrate(handle)
        else currentMode.bitrateBps
    }

    /**
     * Calculate LoRa airtime for voice chunks.
     * @param numChunks Number of chunks to transmit
     * @param chunkBytes Average bytes per chunk
     * @return Airtime in seconds
     */
    fun calculateAirtime(numChunks: Int, chunkBytes: Int): Float {
        if (!isInitialized) return 0f
        return nativeCalculateAirtime(handle, numChunks, chunkBytes)
    }

    /**
     * Check if a transmission fits within ISM duty cycle budget.
     * @param txSeconds Proposed transmission duration
     * @return true if budget allows
     */
    fun canTransmit(txSeconds: Float): Boolean {
        if (!isInitialized) return false
        return nativeCanTransmit(handle, txSeconds)
    }

    /**
     * Get pipeline metrics as JSON.
     */
    fun getMetrics(): PipelineMetrics {
        if (!isInitialized) return PipelineMetrics()
        return try {
            val json = nativeGetMetrics(handle)
            PipelineMetrics.fromJson(json)
        } catch (e: Exception) {
            PipelineMetrics()
        }
    }

    /**
     * Release all native resources.
     */
    fun destroy() {
        if (isInitialized) {
            nativeDestroyPipeline(handle)
            handle = 0
            isInitialized = false
            Log.i(TAG, "Pipeline destroyed")
        }
    }

    // ── Native Methods ──────────────────────────────────────────────────── //

    private external fun nativeCreatePipeline(mode: Int, modelPath: String): Long
    private external fun nativeEncode(handle: Long, pcm: ShortArray): ByteArray?
    private external fun nativeDecode(handle: Long, data: ByteArray): ShortArray?
    private external fun nativeConcealFrame(handle: Long): ShortArray?
    private external fun nativeSetMode(handle: Long, mode: Int): Boolean
    private external fun nativeGetMetrics(handle: Long): String
    private external fun nativeCalculateAirtime(handle: Long, chunks: Int, bytes: Int): Float
    private external fun nativeCanTransmit(handle: Long, txSeconds: Float): Boolean
    private external fun nativeGetFrameSamples(handle: Long): Int
    private external fun nativeGetBitrate(handle: Long): Int
    private external fun nativeDestroyPipeline(handle: Long)
}

/**
 * Codec modes available in the hybrid voice pipeline.
 */
enum class CodecMode(
    val nativeId: Int,
    val displayName: String,
    val bitrateBps: Int,
    val frameSamples: Int,
    val frameMs: Int,
    val frameBytes: Int,
    val isNeural: Boolean = false,
    val isLoraSafe: Boolean = false,
) {
    CODEC2_700C(0x10, "Codec2 700C", 700, 320, 40, 4, isLoraSafe = true),
    CODEC2_1200(0x11, "Codec2 1200", 1200, 320, 40, 6, isLoraSafe = true),
    CODEC2_1300(0x12, "Codec2 1300", 1300, 320, 40, 7, isLoraSafe = true),
    CODEC2_1600(0x13, "Codec2 1600", 1600, 320, 40, 8, isLoraSafe = true),
    CODEC2_2400(0x14, "Codec2 2400", 2400, 160, 20, 6),
    CODEC2_3200(0x15, "Codec2 3200", 3200, 160, 20, 8),
    LYRA_3200(0x20, "Lyra 3200", 3200, 320, 20, 8, isNeural = true),
    LYRA_6000(0x21, "Lyra 6000", 6000, 320, 20, 15, isNeural = true),
    LYRA_9200(0x22, "Lyra 9200", 9200, 320, 20, 23, isNeural = true);

    companion object {
        fun fromNativeId(id: Int): CodecMode? = entries.find { it.nativeId == id }

        /** Best mode for given bandwidth constraint */
        fun bestForBandwidth(maxBps: Int, loraSafe: Boolean = false): CodecMode {
            return entries
                .filter { !it.isNeural }  // Prefer deterministic by default
                .filter { it.bitrateBps <= maxBps }
                .filter { !loraSafe || it.isLoraSafe }
                .maxByOrNull { it.bitrateBps }
                ?: CODEC2_700C
        }
    }
}

/**
 * Pipeline performance metrics.
 */
data class PipelineMetrics(
    val mode: String = "none",
    val name: String = "none",
    val bitrate: Int = 0,
    val encodes: Long = 0,
    val decodes: Long = 0,
    val plcLossRate: Float = 0f,
    val plcConcealed: Long = 0,
    val dutyRemainingS: Float = 36f,
    val dutyUsedS: Float = 0f,
    val neuralEnabled: Boolean = false,
) {
    companion object {
        fun fromJson(jsonStr: String): PipelineMetrics {
            return try {
                val json = JSONObject(jsonStr)
                PipelineMetrics(
                    mode = json.optString("mode", "none"),
                    name = json.optString("name", "none"),
                    bitrate = json.optInt("bitrate", 0),
                    encodes = json.optLong("encodes", 0),
                    decodes = json.optLong("decodes", 0),
                    plcLossRate = json.optDouble("plc_loss_rate", 0.0).toFloat(),
                    plcConcealed = json.optLong("plc_concealed", 0),
                    dutyRemainingS = json.optDouble("duty_remaining_s", 36.0).toFloat(),
                    dutyUsedS = json.optDouble("duty_used_s", 0.0).toFloat(),
                    neuralEnabled = json.optBoolean("neural_enabled", false),
                )
            } catch (e: Exception) {
                PipelineMetrics()
            }
        }
    }
}
