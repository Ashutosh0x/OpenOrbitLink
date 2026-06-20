package org.freesat.network

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Connectivity Orchestrator — Automatic Transport Path Selection
 *
 * Implements Starlink-inspired automatic fallback chain:
 *   WiFi/Internet → Carrier NTN → LoRa ISM → APRS-IS → Local Queue
 *
 * Monitors connectivity changes and selects the best available path
 * for message delivery, enabling seamless offline-to-online transitions.
 */

enum class TransportPath(
    val label: String,
    val description: String,
    val priority: Int,
    val color: Long,
    val icon: String,
) {
    WIFI_API(
        "Internet", "WiFi/Cellular → Backend API",
        priority = 0, color = 0xFF00E676, icon = "wifi"
    ),
    CARRIER_NTN(
        "Carrier NTN", "5G NTN → Satellite Manager API",
        priority = 1, color = 0xFF00B4D8, icon = "satellite"
    ),
    LORA_ISM(
        "LoRa ISM", "868/915 MHz → Ground Station → Satellite",
        priority = 2, color = 0xFF6C63FF, icon = "router"
    ),
    APRS_IS(
        "APRS-IS", "144.39 MHz → Internet Gateway (plaintext)",
        priority = 3, color = 0xFFFF9800, icon = "cell_tower"
    ),
    LOCAL_QUEUE(
        "Offline Queue", "Stored locally → Sync when connected",
        priority = 4, color = 0xFFE94560, icon = "storage"
    );
}

data class PathStatus(
    val path: TransportPath,
    val available: Boolean,
    val signalStrength: Float = 0f, // 0.0 - 1.0
    val latencyMs: Int = -1,
    val reason: String = "",
)

class ConnectivityOrchestrator(private val context: Context) {

    companion object {
        private const val TAG = "OpenOrbitLink.Connectivity"
    }

    private val connectivityManager =
        context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

    private val _currentPath = MutableStateFlow(TransportPath.LOCAL_QUEUE)
    val currentPath: StateFlow<TransportPath> = _currentPath.asStateFlow()

    private val _pathLabel = MutableStateFlow("Offline Queue")
    val pathLabel: StateFlow<String> = _pathLabel.asStateFlow()

    private val _allPaths = MutableStateFlow<List<PathStatus>>(emptyList())
    val allPaths: StateFlow<List<PathStatus>> = _allPaths.asStateFlow()

    private val _isOnline = MutableStateFlow(false)
    val isOnline: StateFlow<Boolean> = _isOnline.asStateFlow()

    init {
        evaluateAllPaths()
        registerNetworkCallback()
    }

    /**
     * Select the best available transport path based on current connectivity.
     */
    fun bestAvailablePath(): TransportPath {
        val paths = evaluateAllPaths()
        val best = paths
            .filter { it.available }
            .minByOrNull { it.path.priority }
            ?.path ?: TransportPath.LOCAL_QUEUE

        _currentPath.value = best
        _pathLabel.value = best.label
        return best
    }

    /**
     * Evaluate availability and quality of all transport paths.
     */
    private fun evaluateAllPaths(): List<PathStatus> {
        val statuses = listOf(
            checkWifiApi(),
            checkCarrierNtn(),
            checkLoraIsm(),
            checkAprsIs(),
            PathStatus(TransportPath.LOCAL_QUEUE, true, 1.0f, 0, "Always available"),
        )
        _allPaths.value = statuses

        val best = statuses.filter { it.available }.minByOrNull { it.path.priority }
        if (best != null) {
            _currentPath.value = best.path
            _pathLabel.value = best.path.label
            _isOnline.value = best.path != TransportPath.LOCAL_QUEUE
        }

        Log.d(TAG, "Path evaluation: ${statuses.map { "${it.path.label}=${it.available}" }}")
        return statuses
    }

    private fun checkWifiApi(): PathStatus {
        val network = connectivityManager.activeNetwork
        val caps = network?.let { connectivityManager.getNetworkCapabilities(it) }

        val hasInternet = caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
                && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)

        val isWifi = caps?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
        val isCellular = caps?.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) == true

        val signal = when {
            isWifi -> 0.95f
            isCellular -> 0.7f
            else -> 0f
        }

        return PathStatus(
            TransportPath.WIFI_API,
            hasInternet,
            signal,
            if (hasInternet) 50 else -1,
            when {
                isWifi -> "WiFi connected"
                isCellular -> "Cellular data"
                else -> "No internet"
            }
        )
    }

    private fun checkCarrierNtn(): PathStatus {
        // Check for NTN (Non-Terrestrial Network) support via SatelliteManager
        // Available on Android 14+ with compatible hardware (Pixel 9+, Galaxy S25+)
        return try {
            val hasSatellite = android.os.Build.VERSION.SDK_INT >= 34
            // In production, check android.telephony.satellite.SatelliteManager
            PathStatus(
                TransportPath.CARRIER_NTN,
                false, // NTN is not yet widely available
                0f,
                -1,
                if (hasSatellite) "NTN modem present, no service" else "Hardware not supported"
            )
        } catch (e: Exception) {
            PathStatus(TransportPath.CARRIER_NTN, false, 0f, -1, "Not available")
        }
    }

    private fun checkLoraIsm(): PathStatus {
        // Check for LoRa ground station connectivity
        // In production, ping the ground station gRPC endpoint
        return PathStatus(
            TransportPath.LORA_ISM,
            false, // Requires physical LoRa hardware
            0f,
            -1,
            "No LoRa node detected"
        )
    }

    private fun checkAprsIs(): PathStatus {
        // APRS-IS requires amateur radio license + internet
        val hasInternet = _allPaths.value.firstOrNull()?.available == true
        return PathStatus(
            TransportPath.APRS_IS,
            false, // Requires callsign configuration
            0f,
            -1,
            if (hasInternet) "Callsign not configured" else "No internet for APRS-IS"
        )
    }

    private fun registerNetworkCallback() {
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()

        try {
            connectivityManager.registerNetworkCallback(request, object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    Log.i(TAG, "Network available")
                    bestAvailablePath()
                }

                override fun onLost(network: Network) {
                    Log.i(TAG, "Network lost")
                    bestAvailablePath()
                }

                override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                    bestAvailablePath()
                }
            })
        } catch (e: Exception) {
            Log.w(TAG, "Failed to register network callback: ${e.message}")
        }
    }
}
