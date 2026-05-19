package org.freesat.api

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import org.freesat.auth.AuthTokenManager
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Singleton API client with JWT auth interceptor.
 *
 * Usage:
 *   val client = ApiClient.getInstance(context)
 *   val inbox = client.api.getInbox()
 */
class ApiClient private constructor(context: Context) {

    companion object {
        private const val TAG = "OpenOrbitLink.API"
        private const val PREFS_NAME = "ool_api_settings"
        private const val KEY_BASE_URL = "base_url"
        private const val DEFAULT_URL = "http://10.0.2.2:8000/" // Android emulator → host localhost

        @Volatile
        private var instance: ApiClient? = null

        fun getInstance(context: Context): ApiClient {
            return instance ?: synchronized(this) {
                instance ?: ApiClient(context.applicationContext).also { instance = it }
            }
        }

        /** Destroy singleton (call on logout or URL change) */
        fun reset() {
            instance = null
        }

        /** Get saved backend URL */
        fun getBaseUrl(context: Context): String {
            return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .getString(KEY_BASE_URL, DEFAULT_URL) ?: DEFAULT_URL
        }

        /** Save backend URL (triggers client reset) */
        fun setBaseUrl(context: Context, url: String) {
            val normalized = if (url.endsWith("/")) url else "$url/"
            context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .edit().putString(KEY_BASE_URL, normalized).apply()
            reset()
        }

        /**
         * Quick health check — non-authenticated.
         * Returns true if backend is reachable.
         */
        suspend fun testConnection(baseUrl: String): Boolean {
            return try {
                val url = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
                val testClient = OkHttpClient.Builder()
                    .connectTimeout(5, TimeUnit.SECONDS)
                    .readTimeout(5, TimeUnit.SECONDS)
                    .build()
                val testApi = Retrofit.Builder()
                    .baseUrl(url)
                    .client(testClient)
                    .addConverterFactory(GsonConverterFactory.create())
                    .build()
                    .create(OpenOrbitLinkApi::class.java)
                val health = testApi.health()
                health.status == "ok"
            } catch (e: Exception) {
                Log.w(TAG, "Connection test failed: ${e.message}")
                false
            }
        }
    }

    private val authManager = AuthTokenManager(context)
    private val baseUrl = getBaseUrl(context)

    private val httpClient: OkHttpClient = OkHttpClient.Builder()
        // JWT auth interceptor
        .addInterceptor { chain ->
            val requestBuilder = chain.request().newBuilder()
            val token = authManager.getToken()
            if (!token.isNullOrBlank()) {
                requestBuilder.addHeader("Authorization", "Bearer $token")
            }
            requestBuilder.addHeader("User-Agent", "OpenOrbitLink-Android/1.0.0")
            chain.proceed(requestBuilder.build())
        }
        // Logging (debug only)
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        })
        // Timeouts — satellite messaging is slow, be patient
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val retrofit: Retrofit = Retrofit.Builder()
        .baseUrl(baseUrl)
        .client(httpClient)
        .addConverterFactory(GsonConverterFactory.create())
        .build()

    /** The API interface — use this for all calls */
    val api: OpenOrbitLinkApi = retrofit.create(OpenOrbitLinkApi::class.java)

    /** Login and save token */
    suspend fun login(username: String, password: String): Result<AuthResponse> {
        return try {
            val response = api.login(LoginRequest(username, password))
            authManager.saveToken(response.accessToken)
            Log.i(TAG, "Login successful for $username")
            Result.success(response)
        } catch (e: Exception) {
            Log.e(TAG, "Login failed: ${e.message}")
            Result.failure(e)
        }
    }

    /** Register and save token */
    suspend fun register(username: String, password: String, inviteCode: String): Result<AuthResponse> {
        return try {
            val response = api.register(RegisterRequest(username, password, inviteCode))
            authManager.saveToken(response.accessToken)
            Log.i(TAG, "Registration successful for $username")
            Result.success(response)
        } catch (e: Exception) {
            Log.e(TAG, "Registration failed: ${e.message}")
            Result.failure(e)
        }
    }

    /** Logout — clear token and reset client */
    fun logout() {
        authManager.clearToken()
        reset()
    }

    /** Check if we have a valid token */
    fun isAuthenticated(): Boolean = authManager.isLoggedIn()
}
