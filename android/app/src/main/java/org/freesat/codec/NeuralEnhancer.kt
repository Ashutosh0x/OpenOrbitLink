package org.freesat.codec

import android.util.Log

/**
 * NeuralEnhancer — Kotlin wrapper for TFLite-based neural voice enhancement.
 *
 * Manages TFLite model lifecycle, GPU/NNAPI delegate selection, and
 * provides optional receiver-side post-processing for Codec2 decoded audio.
 *
 * Enhancement pipeline:
 *   Codec2 decoded PCM (8kHz) → Upsample 16kHz → SoundStream features →
 *   LyraGAN generation → Enhanced PCM (16kHz) → Downsample 8kHz
 *
 * Usage:
 *   val enhancer = NeuralEnhancer(context.assets.path("models"))
 *   enhancer.enable()
 *   val enhanced = enhancer.enhance(decodedPcm)
 *   enhancer.destroy()
 */
class NeuralEnhancer(private val modelPath: String) {

    companion object {
        private const val TAG = "NeuralEnhancer"

        /** TFLite model file names */
        const val MODEL_SOUNDSTREAM = "soundstream_encoder.tflite"
        const val MODEL_QUANTIZER = "quantizer.tflite"
        const val MODEL_LYRAGAN = "lyragan.tflite"

        /** Total model size in KB */
        const val TOTAL_MODEL_SIZE_KB = 3500
    }

    /** Enhancement status */
    enum class Status {
        NOT_INITIALIZED,
        MODELS_LOADING,
        READY,
        DISABLED,
        ERROR
    }

    /** Delegate for hardware acceleration */
    enum class Delegate(val displayName: String) {
        CPU("CPU (XNNPACK)"),
        GPU("GPU (OpenGL ES)"),
        NNAPI("NNAPI (NPU/DSP)")
    }

    /** Enhancement configuration */
    data class Config(
        val enableDenoising: Boolean = true,
        val enableBandwidthExtension: Boolean = true,
        val enableNeuralPLC: Boolean = true,
        val mixLevel: Float = 0.8f,        // 0.0 = bypass, 1.0 = fully enhanced
        val maxCpuPercent: Float = 30f,     // Max CPU budget
        val preferredDelegate: Delegate = Delegate.CPU,
    )

    /** Performance metrics */
    data class Metrics(
        val avgInferenceMs: Float = 0f,
        val maxInferenceMs: Float = 0f,
        val totalEnhancedFrames: Long = 0,
        val totalBypassedFrames: Long = 0,
        val totalConcealedFrames: Long = 0,
        val modelsLoaded: Boolean = false,
        val activeDelegate: Delegate = Delegate.CPU,
    )

    private var status: Status = Status.NOT_INITIALIZED
    private var config: Config = Config()
    private var enabled: Boolean = false
    private var metrics: Metrics = Metrics()

    /**
     * Initialize the enhancer with given configuration.
     * @return true if models were loaded successfully
     */
    fun init(config: Config = Config()): Boolean {
        this.config = config
        status = Status.MODELS_LOADING

        // Check if model files exist
        val modelsExist = checkModels()
        if (!modelsExist) {
            Log.w(TAG, "Neural models not found at: $modelPath")
            status = Status.ERROR
            return false
        }

        // TODO: Initialize TFLite runtime via JNI when TFLite NDK integration is complete
        // For now, mark as ready for development purposes
        Log.i(TAG, "Neural enhancer initialized with ${config.preferredDelegate.displayName}")
        status = Status.READY
        return true
    }

    /**
     * Enhance decoded PCM audio.
     *
     * @param pcm Decoded PCM samples (8kHz from Codec2)
     * @return Enhanced PCM samples, or original if enhancement unavailable
     */
    fun enhance(pcm: ShortArray): ShortArray {
        if (!enabled || status != Status.READY) {
            return pcm  // Graceful passthrough
        }

        // TODO: Call native TFLite enhancement pipeline
        // For now, return original audio (development stub)
        return pcm
    }

    /**
     * Neural packet loss concealment.
     * @param numSamples Desired output samples
     * @return Concealed PCM frame, or null if unavailable
     */
    fun conceal(numSamples: Int): ShortArray? {
        if (!enabled || status != Status.READY) return null

        // TODO: Call native neural PLC
        return null
    }

    /** Enable neural enhancement */
    fun enable() {
        if (status == Status.READY) {
            enabled = true
            Log.i(TAG, "Neural enhancement enabled (mix=${config.mixLevel})")
        }
    }

    /** Disable neural enhancement */
    fun disable() {
        enabled = false
        Log.i(TAG, "Neural enhancement disabled")
    }

    /** Check if enhancement is active */
    fun isEnabled(): Boolean = enabled && status == Status.READY

    /** Get current status */
    fun getStatus(): Status = status

    /** Get performance metrics */
    fun getMetrics(): Metrics = metrics

    /** Set enhancement mix level (0.0 = bypass, 1.0 = fully enhanced) */
    fun setMixLevel(mix: Float) {
        config = config.copy(mixLevel = mix.coerceIn(0f, 1f))
    }

    /** Check if all neural model files exist */
    private fun checkModels(): Boolean {
        val models = listOf(MODEL_SOUNDSTREAM, MODEL_QUANTIZER, MODEL_LYRAGAN)
        return models.all { model ->
            val file = java.io.File(modelPath, model)
            file.exists()
        }
    }

    /** Release all resources */
    fun destroy() {
        enabled = false
        status = Status.NOT_INITIALIZED
        Log.i(TAG, "Neural enhancer destroyed")
    }
}
