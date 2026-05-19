package org.freesat.api

import com.google.gson.annotations.SerializedName

// ── Auth ────────────────────────────────────────────────────────

data class RegisterRequest(
    val username: String,
    val password: String,
    @SerializedName("invite_code") val inviteCode: String
)

data class LoginRequest(
    val username: String,
    val password: String
)

data class AuthResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("token_type") val tokenType: String = "bearer",
    @SerializedName("user_id") val userId: String? = null,
    val username: String? = null
)

data class UserProfile(
    @SerializedName("user_id") val userId: String,
    val username: String,
    @SerializedName("created_at") val createdAt: String? = null
)

// ── Messages ────────────────────────────────────────────────────

data class SendRequest(
    val text: String,
    val destination: String,
    val band: String = "ism",
    val priority: Int = 2
)

data class SendResponse(
    @SerializedName("bundle_id") val bundleId: String,
    val status: String,
    @SerializedName("queued_at") val queuedAt: String? = null,
    @SerializedName("estimated_tx") val estimatedTx: String? = null
)

data class MessageResponse(
    @SerializedName("message_id") val messageId: String,
    @SerializedName("bundle_id") val bundleId: String? = null,
    val source: String,
    val destination: String,
    val text: String,
    val timestamp: Long,
    val status: String = "delivered",
    val band: String? = null,
    @SerializedName("payload_type") val payloadType: String = "text"
)

// ── Queue ────────────────────────────────────────────────────────

data class QueueResponse(
    val pending: Int = 0,
    val transmitting: Int = 0,
    val delivered: Int = 0,
    val failed: Int = 0,
    val items: List<QueueItem> = emptyList()
)

data class QueueItem(
    @SerializedName("bundle_id") val bundleId: String,
    val status: String,
    val destination: String,
    val text: String? = null,
    @SerializedName("created_at") val createdAt: Long = 0,
    @SerializedName("retry_count") val retryCount: Int = 0,
    val priority: Int = 2
)

// ── Station ─────────────────────────────────────────────────────

data class StationStatus(
    val online: Boolean = false,
    @SerializedName("duty_cycle") val dutyCycle: DutyCycleStatus? = null,
    val frequency: String? = null,
    @SerializedName("tx_power_dbm") val txPowerDbm: Int = 14,
    @SerializedName("connected_nodes") val connectedNodes: Int = 0,
    @SerializedName("uptime_seconds") val uptimeSeconds: Long = 0
)

data class DutyCycleStatus(
    @SerializedName("budget_remaining_ms") val budgetRemainingMs: Long = 36000,
    @SerializedName("budget_total_ms") val budgetTotalMs: Long = 36000,
    @SerializedName("utilization_pct") val utilizationPct: Float = 0f,
    @SerializedName("window_reset_at") val windowResetAt: String? = null
)

// ── Passes ──────────────────────────────────────────────────────

data class PassResponse(
    @SerializedName("satellite_name") val satelliteName: String,
    @SerializedName("norad_id") val noradId: Int = 0,
    @SerializedName("rise_utc") val riseUtc: String,
    @SerializedName("culmination_utc") val culminationUtc: String,
    @SerializedName("set_utc") val setUtc: String,
    @SerializedName("max_elevation_deg") val maxElevationDeg: Float,
    @SerializedName("duration_seconds") val durationSeconds: Int,
    @SerializedName("doppler_shift_hz") val dopplerShiftHz: Float = 0f,
    @SerializedName("link_margin_db") val linkMarginDb: Float = 0f,
    @SerializedName("quality_score") val qualityScore: Float = 0f
)

data class NextPassResponse(
    @SerializedName("satellite_name") val satelliteName: String,
    @SerializedName("starts_in_seconds") val startsInSeconds: Long,
    @SerializedName("rise_utc") val riseUtc: String,
    @SerializedName("max_elevation_deg") val maxElevationDeg: Float,
    @SerializedName("duration_seconds") val durationSeconds: Int,
    @SerializedName("is_active") val isActive: Boolean = false
)

// ── Health ───────────────────────────────────────────────────────

data class HealthResponse(
    val status: String = "ok",
    val version: String? = null,
    @SerializedName("uptime_seconds") val uptimeSeconds: Long = 0
)
