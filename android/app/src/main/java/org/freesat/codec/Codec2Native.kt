package org.freesat.codec

/**
 * Codec2 Native Bridge — JNI wrapper for libcodec2
 *
 * Provides 700bps voice encoding/decoding for satellite communication.
 * Falls back to software LPC codec if native library unavailable.
 */
class Codec2Native {

    companion object {
        const val MODE_700C = 8
        const val MODE_1200 = 5
        const val MODE_1300 = 4
        const val SAMPLE_RATE = 8000
        const val FRAME_MS = 40
        const val SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS / 1000  // 320
    }

    private var handle: Long = 0
    private var isInitialized = false

    fun init(mode: Int = MODE_700C): Boolean {
        return try {
            handle = nativeInit(mode)
            isInitialized = handle != 0L
            isInitialized
        } catch (e: UnsatisfiedLinkError) {
            android.util.Log.w("Codec2", "Native library not available: ${e.message}")
            false
        }
    }

    fun encode(pcmSamples: ShortArray): ByteArray? {
        if (!isInitialized) return null
        require(pcmSamples.size == SAMPLES_PER_FRAME) {
            "Expected $SAMPLES_PER_FRAME samples, got ${pcmSamples.size}"
        }
        return nativeEncode(handle, pcmSamples)
    }

    fun decode(encoded: ByteArray): ShortArray? {
        if (!isInitialized) return null
        return nativeDecode(handle, encoded)
    }

    fun destroy() {
        if (isInitialized) {
            nativeDestroy(handle)
            handle = 0
            isInitialized = false
        }
    }

    fun getSamplesPerFrame(): Int {
        return if (isInitialized) nativeGetSamplesPerFrame(handle) else SAMPLES_PER_FRAME
    }

    // Native method declarations
    private external fun nativeInit(mode: Int): Long
    private external fun nativeEncode(handle: Long, pcmSamples: ShortArray): ByteArray?
    private external fun nativeDecode(handle: Long, encoded: ByteArray): ShortArray?
    private external fun nativeDestroy(handle: Long)
    private external fun nativeGetSamplesPerFrame(handle: Long): Int
}
