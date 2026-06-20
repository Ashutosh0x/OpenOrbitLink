package org.freesat.api

import retrofit2.http.*

/**
 * OpenOrbitLink REST API — matches FastAPI backend at /api/v1/
 *
 * All authenticated endpoints require Bearer token via OkHttp interceptor.
 */
interface OpenOrbitLinkApi {

    // ── Auth ──────────────────────────────────────────────────

    @POST("api/v1/auth/register")
    suspend fun register(@Body request: RegisterRequest): AuthResponse

    @POST("api/v1/auth/login")
    suspend fun login(@Body request: LoginRequest): AuthResponse

    @GET("api/v1/auth/me")
    suspend fun getProfile(): UserProfile

    // ── Messaging ─────────────────────────────────────────────

    @POST("api/v1/send")
    suspend fun sendMessage(@Body request: SendRequest): SendResponse

    @GET("api/v1/inbox")
    suspend fun getInbox(): List<MessageResponse>

    @GET("api/v1/queue")
    suspend fun getQueue(): QueueResponse

    // ── Station ───────────────────────────────────────────────

    @GET("api/v1/status")
    suspend fun getStatus(): StationStatus

    // ── Satellite Passes ──────────────────────────────────────

    @GET("api/v1/passes")
    suspend fun getPasses(): List<PassResponse>

    @GET("api/v1/passes/next")
    suspend fun getNextPass(): NextPassResponse

    @GET("api/v1/passes/duty")
    suspend fun getDutyCycle(): DutyCycleStatus

    // ── Health ────────────────────────────────────────────────

    @GET("api/v1/health")
    suspend fun health(): HealthResponse
}
