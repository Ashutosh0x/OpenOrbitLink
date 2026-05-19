package org.freesat.auth

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * OpenOrbitLink Authentication Token Manager.
 *
 * Stores JWT tokens securely in Android Keystore-backed EncryptedSharedPreferences.
 * This ensures tokens are hardware-protected and not accessible to other apps
 * or even root-level filesystem inspection on devices with TEE/StrongBox.
 *
 * Usage:
 *   val auth = AuthTokenManager(context)
 *   auth.saveToken(jwt)            // After login
 *   val token = auth.getToken()    // For API calls
 *   auth.clearToken()              // On logout
 */
class AuthTokenManager(context: Context) {

    companion object {
        private const val PREFS_NAME = "openorbitlink_auth_prefs"
        private const val KEY_JWT_TOKEN = "jwt_token"
        private const val KEY_USERNAME = "username"
        private const val KEY_USER_ID = "user_id"
        private const val KEY_TOKEN_EXPIRY = "token_expiry_ms"
        private const val KEY_LOGIN_TIMESTAMP = "login_timestamp_ms"
    }

    private val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .setRequestStrongBoxBacked(true)  // Use StrongBox if available
        .build()

    private val prefs = EncryptedSharedPreferences.create(
        context,
        PREFS_NAME,
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    /**
     * Save JWT token and associated user metadata after successful login.
     */
    fun saveToken(
        token: String,
        username: String,
        userId: Int,
        expiresInHours: Int = 72
    ) {
        val expiryMs = System.currentTimeMillis() + (expiresInHours * 3600 * 1000L)
        prefs.edit()
            .putString(KEY_JWT_TOKEN, token)
            .putString(KEY_USERNAME, username)
            .putInt(KEY_USER_ID, userId)
            .putLong(KEY_TOKEN_EXPIRY, expiryMs)
            .putLong(KEY_LOGIN_TIMESTAMP, System.currentTimeMillis())
            .apply()
    }

    /**
     * Retrieve the stored JWT token. Returns null if not logged in or expired.
     */
    fun getToken(): String? {
        val token = prefs.getString(KEY_JWT_TOKEN, null) ?: return null
        val expiry = prefs.getLong(KEY_TOKEN_EXPIRY, 0L)

        // Check if token has expired locally
        if (expiry > 0 && System.currentTimeMillis() > expiry) {
            clearToken()
            return null
        }

        return token
    }

    /**
     * Get the stored username.
     */
    fun getUsername(): String? = prefs.getString(KEY_USERNAME, null)

    /**
     * Get the stored user ID.
     */
    fun getUserId(): Int = prefs.getInt(KEY_USER_ID, -1)

    /**
     * Check if the user is currently logged in with a valid (non-expired) token.
     */
    fun isLoggedIn(): Boolean = getToken() != null

    /**
     * Clear all auth data (logout).
     */
    fun clearToken() {
        prefs.edit()
            .remove(KEY_JWT_TOKEN)
            .remove(KEY_USERNAME)
            .remove(KEY_USER_ID)
            .remove(KEY_TOKEN_EXPIRY)
            .remove(KEY_LOGIN_TIMESTAMP)
            .apply()
    }

    /**
     * Get the Bearer token header value for API calls.
     */
    fun getBearerHeader(): String? {
        val token = getToken() ?: return null
        return "Bearer $token"
    }
}
