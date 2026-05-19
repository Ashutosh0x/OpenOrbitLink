package org.freesat.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import org.freesat.api.ApiClient
import org.freesat.api.NextPassResponse
import org.freesat.api.StationStatus
import org.freesat.data.MessageEntity
import org.freesat.data.MessageRepository
import org.freesat.data.PassEntity

/**
 * Main ViewModel for the messaging and dashboard screens.
 *
 * - Exposes reactive flows from Room (offline-first)
 * - Syncs with server every 30s (inbox) and 60s (passes)
 * - Manages pass countdown timer
 */
class MessagingViewModel(application: Application) : AndroidViewModel(application) {

    companion object {
        private const val TAG = "OpenOrbitLink.VM"
        private const val INBOX_POLL_MS = 30_000L
        private const val PASS_POLL_MS = 60_000L
    }

    private val repo = MessageRepository(application)
    private val apiClient = ApiClient.getInstance(application)

    // ── Reactive state from Room ────────────────────────────────

    val allMessages: StateFlow<List<MessageEntity>> = repo.allMessages
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val inbox: StateFlow<List<MessageEntity>> = repo.inbox
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val pendingMessages: StateFlow<List<MessageEntity>> = repo.pendingMessages
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val passes: StateFlow<List<PassEntity>> = repo.passes
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    // ── Server-side state ───────────────────────────────────────

    private val _stationStatus = MutableStateFlow<StationStatus?>(null)
    val stationStatus: StateFlow<StationStatus?> = _stationStatus.asStateFlow()

    private val _nextPass = MutableStateFlow<NextPassResponse?>(null)
    val nextPass: StateFlow<NextPassResponse?> = _nextPass.asStateFlow()

    private val _nextPassCountdown = MutableStateFlow<Long>(0)
    val nextPassCountdown: StateFlow<Long> = _nextPassCountdown.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    // ── Stats ───────────────────────────────────────────────────

    private val _stats = MutableStateFlow(MessageStats())
    val stats: StateFlow<MessageStats> = _stats.asStateFlow()

    data class MessageStats(
        val queued: Int = 0,
        val waiting: Int = 0,
        val delivered: Int = 0,
        val failed: Int = 0
    )

    // ── Init ────────────────────────────────────────────────────

    init {
        startPeriodicSync()
        startPassCountdown()
    }

    // ── Actions ─────────────────────────────────────────────────

    fun sendMessage(text: String, destination: String) {
        viewModelScope.launch {
            val result = repo.sendMessage(text, destination)
            if (result.isFailure) {
                _error.value = "Message queued locally — will send when connected"
            }
            refreshStats()
        }
    }

    fun retryMessage(messageId: String) {
        viewModelScope.launch {
            repo.retryMessage(messageId)
            refreshStats()
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _isRefreshing.value = true
            syncAll()
            _isRefreshing.value = false
        }
    }

    fun clearError() {
        _error.value = null
    }

    // ── Periodic sync ───────────────────────────────────────────

    private fun startPeriodicSync() {
        // Inbox sync every 30s
        viewModelScope.launch {
            while (true) {
                syncAll()
                delay(INBOX_POLL_MS)
            }
        }

        // Pass sync every 60s
        viewModelScope.launch {
            while (true) {
                syncPasses()
                delay(PASS_POLL_MS)
            }
        }
    }

    private suspend fun syncAll() {
        try {
            repo.syncInbox()
            repo.syncQueue()
            refreshStats()
            fetchStationStatus()
        } catch (e: Exception) {
            Log.w(TAG, "Sync cycle failed: ${e.message}")
        }
    }

    private suspend fun syncPasses() {
        try {
            repo.syncPasses()
            fetchNextPass()
        } catch (e: Exception) {
            Log.w(TAG, "Pass sync failed: ${e.message}")
        }
    }

    private suspend fun fetchStationStatus() {
        try {
            _stationStatus.value = apiClient.api.getStatus()
        } catch (_: Exception) { }
    }

    private suspend fun fetchNextPass() {
        try {
            val next = apiClient.api.getNextPass()
            _nextPass.value = next
            _nextPassCountdown.value = next.startsInSeconds
        } catch (_: Exception) { }
    }

    private suspend fun refreshStats() {
        _stats.value = MessageStats(
            queued = repo.countQueued(),
            waiting = repo.countWaiting(),
            delivered = repo.countDelivered(),
            failed = repo.countFailed()
        )
    }

    // ── Pass countdown timer ────────────────────────────────────

    private fun startPassCountdown() {
        viewModelScope.launch {
            while (true) {
                val current = _nextPassCountdown.value
                if (current > 0) {
                    _nextPassCountdown.value = current - 1
                }
                delay(1000)
            }
        }
    }
}
