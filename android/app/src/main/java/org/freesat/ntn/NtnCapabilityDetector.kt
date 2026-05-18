package org.freesat.ntn

import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings

data class NtnAvailability(
    val hardwareFeature: Boolean,
    val satelliteService: Boolean,
    val safetySettingsAvailable: Boolean,
    val androidApiLevel: Int,
) {
    val statusLabel: String
        get() = when {
            satelliteService -> "Carrier NTN API visible"
            hardwareFeature -> "Satellite feature advertised"
            else -> "No carrier NTN feature"
        }

    val detail: String
        get() = when {
            satelliteService -> "Check Safety & emergency for Satellite SOS registration."
            hardwareFeature -> "Device reports satellite hardware; OS/carrier API may still be gated."
            else -> "Use LoRa ISM or licensed amateur paths; no phone NTN modem path detected."
        }
}

object NtnCapabilityDetector {
    const val FEATURE_TELEPHONY_SATELLITE = "android.hardware.telephony.satellite"
    private const val SATELLITE_SERVICE = "satellite"
    private const val ACTION_SAFETY_CENTER = "android.settings.SAFETY_CENTER"

    fun detect(context: Context): NtnAvailability {
        val appContext = context.applicationContext
        val packageManager = appContext.packageManager
        val hardwareFeature = packageManager.hasSystemFeature(FEATURE_TELEPHONY_SATELLITE)
        val satelliteService = hardwareFeature && Build.VERSION.SDK_INT >= 36 &&
            runCatching { appContext.getSystemService(SATELLITE_SERVICE) != null }.getOrDefault(false)
        val safetySettingsAvailable = safetySettingsIntent()
            .resolveActivity(packageManager) != null

        return NtnAvailability(
            hardwareFeature = hardwareFeature,
            satelliteService = satelliteService,
            safetySettingsAvailable = safetySettingsAvailable,
            androidApiLevel = Build.VERSION.SDK_INT,
        )
    }

    fun safetySettingsIntent(): Intent =
        Intent(ACTION_SAFETY_CENTER).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    fun fallbackSettingsIntent(): Intent =
        Intent(Settings.ACTION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
}
