package org.freesat.codec

import android.util.Log

/**
 * Codec2 Native Bridge — Legacy JNI wrapper for libcodec2
 *
 * @deprecated Use [VoiceCodecManager] instead, which provides a unified
 * interface for both Codec2 and neural codecs with adaptive mode selection,
 * packet loss concealment, and airtime management.
 *
 * This class is retained for backward compatibility. Internally delegates
 * to VoiceCodecManager when available.
 */
@Deprecated(
    message = "Use VoiceCodecManager for full hybrid codec support",
    replaceWith = ReplaceWith("VoiceCodecManager()")
)
class Codec2Native {

    companion object {
        const val MODE_700C = 8
        const val MODE_1200 = 5
        const val MODE_1300 = 4
        const val SAMPLE_RATE = 8000
        const val FRAME_MS = 40
        const val SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS / 1000  // 320

        private const val TAG = "Codec2Native"

        init {
            try {
                System.loadLibrary("ool_voice_jni")
            } catch (e: UnsatisfiedLinkError) {
                try {
                    System.loadLibrary("codec2_jni")
                } catch (e2: UnsatisfiedLinkError) {
                    Log.w(TAG, "No native codec library available")
                }
            }
        }

        /**
         * Convert legacy Codec2 mode to new CodecMode enum.
         */
        fun legacyModeToCodecMode(mode: Int): CodecMode = when (mode) {
            MODE_700C -> CodecMode.CODEC2_700C
            MODE_1200 -> CodecMode.CODEC2_1200
            MODE_1300 -> CodecMode.CODEC2_1300
            else -> CodecMode.CODEC2_700C
        }
    }

    private var codecManager: VoiceCodecManager? = null
    private var isInitialized = false

    // Legacy handle for backward compat with old JNI bridge
    private var handle: Long = 0

    fun init(mode: Int = MODE_700C): Boolean {
        return try {
            // Prefer new unified pipeline
            val mgr = VoiceCodecManager()
            val codecMode = legacyModeToCodecMode(mode)
            if (mgr.init(codecMode)) {
                codecManager = mgr
                isInitialized = true
                Log.i(TAG, "Initialized via VoiceCodecManager: ${codecMode.displayName}")
                return true
            }

            // Fallback to legacy JNI
            handle = nativeInit(mode)
            isInitialized = handle != 0L
            if (isInitialized) {
                Log.i(TAG, "Initialized via legacy JNI: mode=$mode")
            }
            isInitialized
        } catch (e: UnsatisfiedLinkError) {
            Log.w(TAG, "Native library not available: ${e.message}")
            false
        }
    }

    fun encode(pcmSamples: ShortArray): ByteArray? {
        if (!isInitialized) return null
        require(pcmSamples.size == SAMPLES_PER_FRAME) {
            "Expected $SAMPLES_PER_FRAME samples, got ${pcmSamples.size}"
        }

        // Prefer unified pipeline
        codecManager?.let { return it.encode(pcmSamples) }

        // Legacy fallback
        return nativeEncode(handle, pcmSamples)
    }

    fun decode(encoded: ByteArray): ShortArray? {
        if (!isInitialized) return null

        // Prefer unified pipeline
        codecManager?.let { return it.decode(encoded) }

        // Legacy fallback
        return nativeDecode(handle, encoded)
    }

    fun destroy() {
        codecManager?.destroy()
        codecManager = null

        if (handle != 0L) {
            nativeDestroy(handle)
            handle = 0
        }
        isInitialized = false
    }

    fun getSamplesPerFrame(): Int {
        codecManager?.let { return it.getFrameSamples() }
        return if (isInitialized && handle != 0L)
            nativeGetSamplesPerFrame(handle)
        else SAMPLES_PER_FRAME
    }

    // Legacy native method declarations (old codec2_jni.c bridge)
    private external fun nativeInit(mode: Int): Long
    private external fun nativeEncode(handle: Long, pcmSamples: ShortArray): ByteArray?
    private external fun nativeDecode(handle: Long, encoded: ByteArray): ShortArray?
    private external fun nativeDestroy(handle: Long)
    private external fun nativeGetSamplesPerFrame(handle: Long): Int
}
