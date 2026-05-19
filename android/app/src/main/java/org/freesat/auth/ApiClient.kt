package org.freesat.auth

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

/**
 * OpenOrbitLink API Client — REST communication with the FastAPI backend.
 * Every authenticated request includes the Bearer JWT from AuthTokenManager.
 */
class ApiClient(
    private val baseUrl: String = "http://10.0.2.2:8000",
    private val tokenManager: AuthTokenManager? = null
) {
    companion object {
        private const val TAG = "OpenOrbitLink.API"
        private const val TIMEOUT_MS = 15_000
    }

    data class AuthResult(
        val success: Boolean, val token: String = "", val userId: Int = -1,
        val username: String = "", val expiresInHours: Int = 72, val error: String = ""
    )

    data class SendResult(
        val success: Boolean, val messageId: Int = -1,
        val bundleId: String = "", val error: String = ""
    )

    suspend fun register(username: String, password: String, inviteCode: String, email: String? = null): AuthResult =
        withContext(Dispatchers.IO) {
            try {
                val body = JSONObject().apply {
                    put("username", username); put("password", password)
                    put("invite_code", inviteCode); email?.let { put("email", it) }
                }
                val r = post("/api/v1/auth/register", body)
                if (r.getInt("status") == 201) {
                    val d = r.getJSONObject("body")
                    AuthResult(true, d.getString("access_token"), d.getInt("user_id"),
                        d.getString("username"), d.optInt("expires_in_hours", 72))
                } else AuthResult(false, error = r.optJSONObject("body")?.optString("detail") ?: "Registration failed")
            } catch (e: Exception) { Log.e(TAG, "Register failed", e); AuthResult(false, error = e.message ?: "Network error") }
        }

    suspend fun login(username: String, password: String): AuthResult =
        withContext(Dispatchers.IO) {
            try {
                val body = JSONObject().apply { put("username", username); put("password", password) }
                val r = post("/api/v1/auth/login", body)
                if (r.getInt("status") == 200) {
                    val d = r.getJSONObject("body")
                    AuthResult(true, d.getString("access_token"), d.getInt("user_id"),
                        d.getString("username"), d.optInt("expires_in_hours", 72))
                } else AuthResult(false, error = r.optJSONObject("body")?.optString("detail") ?: "Login failed")
            } catch (e: Exception) { Log.e(TAG, "Login failed", e); AuthResult(false, error = e.message ?: "Network error") }
        }

    suspend fun sendMessage(text: String, destination: String = "", band: String = "ism", encrypted: Boolean = false): SendResult =
        withContext(Dispatchers.IO) {
            try {
                val body = JSONObject().apply {
                    put("text", text); put("destination", destination)
                    put("band", band); put("encrypted", encrypted)
                }
                val r = post("/api/v1/send", body, true)
                if (r.getInt("status") == 201) {
                    val d = r.getJSONObject("body")
                    SendResult(true, d.getInt("id"), d.optString("bundle_id", ""))
                } else SendResult(false, error = r.optJSONObject("body")?.optString("detail") ?: "Send failed")
            } catch (e: Exception) { Log.e(TAG, "Send failed", e); SendResult(false, error = e.message ?: "Network error") }
        }

    suspend fun getInbox(limit: Int = 50): JSONObject = withContext(Dispatchers.IO) { get("/api/v1/inbox?limit=$limit", true) }
    suspend fun getQueueStatus(): JSONObject = withContext(Dispatchers.IO) { get("/api/v1/queue", true) }
    suspend fun getStationStatus(): JSONObject = withContext(Dispatchers.IO) { get("/api/v1/status", true) }
    suspend fun getProfile(): JSONObject = withContext(Dispatchers.IO) { get("/api/v1/auth/me", true) }

    private fun post(path: String, body: JSONObject, authenticated: Boolean = false): JSONObject {
        val conn = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"; setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
            if (authenticated) tokenManager?.getBearerHeader()?.let { setRequestProperty("Authorization", it) }
            connectTimeout = TIMEOUT_MS; readTimeout = TIMEOUT_MS; doOutput = true
        }
        try {
            OutputStreamWriter(conn.outputStream).use { it.write(body.toString()) }
            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val text = BufferedReader(InputStreamReader(stream ?: conn.inputStream)).use { it.readText() }
            return JSONObject().apply {
                put("status", status)
                put("body", if (text.startsWith("{")) JSONObject(text) else JSONObject())
            }
        } finally { conn.disconnect() }
    }

    private fun get(path: String, authenticated: Boolean = false): JSONObject {
        val conn = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"; setRequestProperty("Accept", "application/json")
            if (authenticated) tokenManager?.getBearerHeader()?.let { setRequestProperty("Authorization", it) }
            connectTimeout = TIMEOUT_MS; readTimeout = TIMEOUT_MS
        }
        try {
            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val text = BufferedReader(InputStreamReader(stream ?: conn.inputStream)).use { it.readText() }
            return JSONObject().apply {
                put("status", status)
                put("body", if (text.startsWith("{") || text.startsWith("[")) JSONObject().put("data", text) else JSONObject())
            }
        } finally { conn.disconnect() }
    }
}
