package org.freesat.codec

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.os.SystemClock
import android.util.Log
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean

/**
 * PushToTalkEngine — Full PTT lifecycle for asynchronous voice messaging.
 *
 * This is NOT a real-time VoIP engine. It records, encodes, chunks, and
 * queues voice messages for DTN/LoRa store-and-forward transmission.
 *
 * Lifecycle:
 *   1. Press PTT → startRecording()
 *   2. Audio captured → encoded frame by frame
 *   3. Release PTT → stopRecording()
 *   4. Encoded frames → chunked for LoRa (80-byte limit)
 *   5. Chunks → queued for DTN transmission
 *
 * Usage:
 *   val ptt = PushToTalkEngine(context, codecManager)
 *   ptt.setOnMessageReady { message -> dtnEngine.queue(message) }
 *   ptt.startRecording()
 *   // ... user speaks ...
 *   ptt.stopRecording()
 */
class PushToTalkEngine(
    private val context: Context,
    private val codecManager: VoiceCodecManager,
    private val enhancer: NeuralEnhancer? = null,
) {
    companion object {
        private const val TAG = "PTTEngine"
        private const val SAMPLE_RATE = 8000
        private const val MAX_DURATION_S = 30
    }

    /** PTT State */
    enum class State {
        IDLE,
        RECORDING,
        ENCODING,
        READY,       // Voice message ready for transmission
        ERROR
    }

    /** Callback for when a voice message is ready for DTN queueing */
    private var onMessageReady: ((VoiceMessage) -> Unit)? = null

    /** Callback for recording level (for UI meters) */
    private var onLevelUpdate: ((Float) -> Unit)? = null

    /** Callback for state changes */
    private var onStateChange: ((State) -> Unit)? = null

    private var state: State = State.IDLE
    private val isRecording = AtomicBoolean(false)
    private var audioRecord: AudioRecord? = null
    private var recordJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())

    /** Encoded frames accumulated during recording */
    private val encodedFrames = ConcurrentLinkedQueue<ByteArray>()
    private var recordStartMs: Long = 0
    private var frameCount: Int = 0

    /**
     * Start recording audio for a voice message.
     */
    fun startRecording(): Boolean {
        if (isRecording.get()) {
            Log.w(TAG, "Already recording")
            return false
        }

        if (!hasAudioPermission()) {
            Log.e(TAG, "RECORD_AUDIO permission not granted")
            setState(State.ERROR)
            return false
        }

        if (!codecManager.getMetrics().let { true }) {
            // Codec manager doesn't need to be initialized for recording
            // but encoding will fail without it
        }

        try {
            val bufferSize = AudioRecord.getMinBufferSize(
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT
            )

            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize.coerceAtLeast(codecManager.getFrameSamples() * 2 * 4)
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord failed to initialize")
                setState(State.ERROR)
                return false
            }

            encodedFrames.clear()
            frameCount = 0
            recordStartMs = SystemClock.elapsedRealtime()
            isRecording.set(true)
            setState(State.RECORDING)

            audioRecord?.startRecording()

            // Start capture loop
            recordJob = scope.launch {
                captureLoop()
            }

            Log.i(TAG, "Recording started: ${codecManager.getMode().displayName}")
            return true
        } catch (e: SecurityException) {
            Log.e(TAG, "Security exception: ${e.message}")
            setState(State.ERROR)
            return false
        }
    }

    /**
     * Stop recording and finalize the voice message.
     */
    fun stopRecording(): VoiceMessage? {
        if (!isRecording.get()) return null

        isRecording.set(false)
        recordJob?.cancel()

        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null

        val durationMs = (SystemClock.elapsedRealtime() - recordStartMs).toInt()

        setState(State.ENCODING)

        // Build voice message from encoded frames
        val frames = encodedFrames.toList()
        if (frames.isEmpty()) {
            Log.w(TAG, "No frames recorded")
            setState(State.IDLE)
            return null
        }

        val message = VoiceMessage(
            messageId = generateMessageId(),
            codecMode = codecManager.getMode(),
            frames = frames,
            durationMs = durationMs,
            sampleRate = SAMPLE_RATE,
            totalFrames = frames.size,
            timestamp = System.currentTimeMillis(),
        )

        Log.i(TAG, "Recording stopped: ${frames.size} frames, ${durationMs}ms, " +
                   "${message.totalBytes} bytes, ${message.estimatedChunks} LoRa chunks")

        setState(State.READY)
        onMessageReady?.invoke(message)

        setState(State.IDLE)
        return message
    }

    /**
     * Audio capture loop — runs on background coroutine.
     */
    private suspend fun captureLoop() {
        val frameSamples = codecManager.getFrameSamples()
        val pcmBuffer = ShortArray(frameSamples)
        val maxFrames = (MAX_DURATION_S * 1000) / codecManager.getMode().frameMs

        while (isRecording.get() && frameCount < maxFrames) {
            val read = audioRecord?.read(pcmBuffer, 0, frameSamples) ?: -1

            if (read == frameSamples) {
                // Calculate level for UI
                val energy = calculateEnergy(pcmBuffer)
                withContext(Dispatchers.Main) {
                    onLevelUpdate?.invoke(energy)
                }

                // Skip silence frames (simple VAD)
                if (energy > -50f) {
                    val encoded = codecManager.encode(pcmBuffer)
                    if (encoded != null) {
                        encodedFrames.add(encoded)
                        frameCount++
                    }
                }
            } else if (read < 0) {
                Log.e(TAG, "AudioRecord read error: $read")
                break
            }
        }

        // Auto-stop if max duration reached
        if (frameCount >= maxFrames) {
            Log.w(TAG, "Max duration reached ($MAX_DURATION_S s)")
            withContext(Dispatchers.Main) {
                stopRecording()
            }
        }
    }

    /**
     * Play back a received voice message.
     */
    fun playMessage(message: VoiceMessage) {
        scope.launch {
            try {
                val mode = message.codecMode
                val prevMode = codecManager.getMode()

                // Switch codec if needed
                if (prevMode != mode) {
                    codecManager.setMode(mode)
                }

                val frameSamples = codecManager.getFrameSamples()
                val allPcm = ShortArray(frameSamples * message.totalFrames)
                var offset = 0

                for ((index, frame) in message.frames.withIndex()) {
                    val decoded = codecManager.decode(frame)
                    if (decoded != null) {
                        // Apply neural enhancement if available
                        val enhanced = enhancer?.takeIf { it.isEnabled() }?.enhance(decoded) ?: decoded
                        enhanced.copyInto(allPcm, offset)
                        offset += enhanced.size
                    } else {
                        // PLC concealment for failed decode
                        val concealed = codecManager.concealLostFrame()
                        if (concealed != null) {
                            concealed.copyInto(allPcm, offset)
                            offset += concealed.size
                        }
                    }
                }

                // Play on audio track
                val audioTrack = AudioTrack.Builder()
                    .setAudioFormat(
                        AudioFormat.Builder()
                            .setSampleRate(message.sampleRate)
                            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                            .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                            .build()
                    )
                    .setBufferSizeInBytes(offset * 2)
                    .build()

                audioTrack.play()
                audioTrack.write(allPcm, 0, offset)
                audioTrack.stop()
                audioTrack.release()

                // Restore codec mode
                if (prevMode != mode) {
                    codecManager.setMode(prevMode)
                }

                Log.i(TAG, "Playback complete: ${offset} samples")
            } catch (e: Exception) {
                Log.e(TAG, "Playback failed: ${e.message}")
            }
        }
    }

    // ── Callbacks ───────────────────────────────────────────────────────── //

    fun setOnMessageReady(callback: (VoiceMessage) -> Unit) {
        onMessageReady = callback
    }

    fun setOnLevelUpdate(callback: (Float) -> Unit) {
        onLevelUpdate = callback
    }

    fun setOnStateChange(callback: (State) -> Unit) {
        onStateChange = callback
    }

    fun getState(): State = state

    fun isRecording(): Boolean = isRecording.get()

    // ── Private Helpers ─────────────────────────────────────────────────── //

    private fun setState(newState: State) {
        state = newState
        onStateChange?.invoke(newState)
    }

    private fun hasAudioPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            context, Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun calculateEnergy(pcm: ShortArray): Float {
        var sum = 0.0
        for (s in pcm) {
            sum += s.toDouble() * s.toDouble()
        }
        val rms = sum / pcm.size
        if (rms < 1.0) return -96f
        return (10.0 * Math.log10(rms / (32768.0 * 32768.0))).toFloat()
    }

    private fun generateMessageId(): Long {
        return System.currentTimeMillis() xor (Math.random() * Long.MAX_VALUE).toLong()
    }

    /**
     * Release all resources.
     */
    fun destroy() {
        stopRecording()
        scope.cancel()
    }
}
