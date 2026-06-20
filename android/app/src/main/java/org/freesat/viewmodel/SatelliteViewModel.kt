package org.freesat.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import kotlin.math.*

/**
 * ViewModel for real-time satellite tracking.
 *
 * Manages satellite positions with 1-second updates using simulated
 * SGP4 orbital propagation. In production, connects to backend
 * WebSocket /ws/radar for live data.
 */

enum class ServiceMode(val label: String, val pollIntervalMs: Long) {
    STANDBY("Standby", 300_000),    // 5 min polling
    ACTIVE("Active", 1_000),         // 1s updates
    EMERGENCY("Emergency", 500),     // 0.5s updates, SOS priority
}

data class SatelliteUiState(
    val name: String,
    val noradId: Int,
    val latitude: Double,
    val longitude: Double,
    val altitudeKm: Double,
    val azimuthDeg: Double,
    val elevationDeg: Double,
    val rangeKm: Double,
    val dopplerHz: Double,
    val velocityKmS: Double,
    val isVisible: Boolean,
    val footprintKm: Double,
    val category: String,
    val color: Long,
    val frequencyHz: Long,
    val signalQuality: Float,
    val nextPassMinutes: Int? = null,
    val passRemainingSeconds: Int? = null,
)

class SatelliteViewModel(application: Application) : AndroidViewModel(application) {

    companion object {
        private const val TAG = "OpenOrbitLink.SatVM"
        private const val EARTH_RADIUS_KM = 6371.0
        private const val OBSERVER_LAT = 28.6139
        private const val OBSERVER_LON = 77.2090
    }

    // ── State ───────────────────────────────────────────────────

    private val _trackedSatellites = MutableStateFlow<List<SatelliteUiState>>(emptyList())
    val trackedSatellites: StateFlow<List<SatelliteUiState>> = _trackedSatellites.asStateFlow()

    val visibleSatellites: StateFlow<List<SatelliteUiState>> = _trackedSatellites
        .map { sats -> sats.filter { it.isVisible } }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _connectedSatellite = MutableStateFlow<SatelliteUiState?>(null)
    val connectedSatellite: StateFlow<SatelliteUiState?> = _connectedSatellite.asStateFlow()

    private val _serviceMode = MutableStateFlow(ServiceMode.ACTIVE)
    val serviceMode: StateFlow<ServiceMode> = _serviceMode.asStateFlow()

    private val _isTracking = MutableStateFlow(false)
    val isTracking: StateFlow<Boolean> = _isTracking.asStateFlow()

    private val _tleAgeHours = MutableStateFlow(2)
    val tleAgeHours: StateFlow<Int> = _tleAgeHours.asStateFlow()

    private var trackingJob: Job? = null
    private var tickCount = 0L

    // ── Satellite Catalog ───────────────────────────────────────

    private data class SatEntry(
        val name: String, val noradId: Int, val category: String,
        val color: Long, val frequencyHz: Long, val altitudeKm: Double,
        val inclination: Double, val meanMotionFactor: Double,
        val initialAz: Double, val initialEl: Double,
    )

    private val catalog = listOf(
        SatEntry("ISS (ZARYA)", 25544, "comms", 0xFF00B4D8, 145_825_000, 408.0, 51.6, 2.4, 120.0, 35.0),
        SatEntry("FOSSASAT-2E", 50985, "comms", 0xFF00E676, 868_000_000, 550.0, 97.5, 1.8, 200.0, 22.0),
        SatEntry("NOAA-19", 33591, "weather", 0xFF533483, 137_100_000, 870.0, 99.2, 1.2, 45.0, 18.0),
        SatEntry("METEOR-M2 3", 57166, "weather", 0xFFFF9800, 137_900_000, 835.0, 98.8, 1.5, 310.0, 42.0),
        SatEntry("FUNcube-1", 39444, "amateur", 0xFFE040FB, 145_935_000, 695.0, 97.6, 2.1, 150.0, 55.0),
        SatEntry("CAS-4A", 44881, "amateur", 0xFF00BCD4, 145_855_000, 520.0, 98.2, 1.6, 80.0, -8.0),
        SatEntry("TEVEL-5", 51069, "amateur", 0xFF64FFDA, 436_400_000, 530.0, 97.5, 1.9, 260.0, 12.0),
        SatEntry("NOAA-18", 28654, "weather", 0xFFFF5722, 137_912_500, 860.0, 99.0, 1.1, 170.0, -15.0),
        SatEntry("STARLINK-30K", 60001, "comms", 0xFF42A5F5, 12_000_000_000, 550.0, 53.0, 2.6, 30.0, 68.0),
        SatEntry("OSCAR-100", 43700, "amateur", 0xFF6C63FF, 10_489_750_000, 35786.0, 0.01, 0.001, 185.0, 25.0),
        SatEntry("GOES-16", 41866, "weather", 0xFFFFC107, 1_694_100_000, 35786.0, 0.04, 0.0005, 240.0, -5.0),
        SatEntry("CUBEBEL-2", 44909, "amateur", 0xFF76FF03, 435_580_000, 480.0, 97.7, 2.0, 95.0, 5.0),
    )

    // ── Init ────────────────────────────────────────────────────

    init {
        startTracking()
    }

    // ── Actions ─────────────────────────────────────────────────

    fun startTracking() {
        if (_isTracking.value) return
        _isTracking.value = true
        trackingJob = viewModelScope.launch {
            Log.i(TAG, "Satellite tracking started (${_serviceMode.value.label} mode)")
            while (_isTracking.value) {
                tickCount++
                _trackedSatellites.value = computePositions(tickCount)

                // Update connected satellite position
                _connectedSatellite.value?.let { conn ->
                    _connectedSatellite.value = _trackedSatellites.value
                        .find { it.name == conn.name }
                }

                delay(_serviceMode.value.pollIntervalMs)
            }
        }
    }

    fun stopTracking() {
        _isTracking.value = false
        trackingJob?.cancel()
        trackingJob = null
        Log.i(TAG, "Satellite tracking stopped")
    }

    fun connectToSatellite(name: String) {
        val sat = _trackedSatellites.value.find { it.name == name }
        _connectedSatellite.value = sat
        Log.i(TAG, "Connected to satellite: $name")
    }

    fun disconnectSatellite() {
        Log.i(TAG, "Disconnected from: ${_connectedSatellite.value?.name}")
        _connectedSatellite.value = null
    }

    fun setServiceMode(mode: ServiceMode) {
        _serviceMode.value = mode
        Log.i(TAG, "Service mode: ${mode.label}")
        // Restart tracking with new interval
        if (_isTracking.value) {
            stopTracking()
            startTracking()
        }
    }

    fun refreshPositions() {
        viewModelScope.launch {
            tickCount++
            _trackedSatellites.value = computePositions(tickCount)
        }
    }

    // ── Orbital Simulation ──────────────────────────────────────

    private fun computePositions(tick: Long): List<SatelliteUiState> {
        val t = tick.toDouble()
        return catalog.map { sat -> computeSatPosition(sat, t) }
    }

    private fun computeSatPosition(sat: SatEntry, t: Double): SatelliteUiState {
        // Simulate orbital motion using simple Keplerian approximation
        val azSpeed = sat.meanMotionFactor
        val elAmplitude = if (sat.altitudeKm > 10000) 3.0 else 35.0
        val elPeriod = if (sat.altitudeKm > 10000) 0.002 else 0.06 + sat.meanMotionFactor * 0.01

        val az = (sat.initialAz + t * azSpeed) % 360.0
        val el = sat.initialEl + sin(t * elPeriod) * elAmplitude
        val isVisible = el > 0

        // Velocity from orbital mechanics: v = sqrt(GM / r)
        val velocity = sqrt(398600.4418 / (EARTH_RADIUS_KM + sat.altitudeKm))

        // Range estimation
        val range = if (el > 0) {
            val elRad = Math.toRadians(el.coerceAtLeast(1.0))
            sat.altitudeKm / sin(elRad)
        } else {
            sqrt(EARTH_RADIUS_KM.pow(2) + (EARTH_RADIUS_KM + sat.altitudeKm).pow(2))
        }

        // Doppler estimation
        val doppler = if (sat.altitudeKm < 10000) {
            velocity * 1000 * cos(Math.toRadians(el + 90)) / 299_792_458.0 * sat.frequencyHz
        } else {
            sin(t * 0.01) * 50 // GEO sats have minimal Doppler
        }

        // Signal quality
        val quality = when {
            el < 0 -> 0.0f
            el < 5 -> 0.05f
            else -> (0.6f * (el / 60.0).coerceAtMost(1.0) + 0.4f * (1.0 - range / 5000.0).coerceIn(0.1, 1.0)).toFloat()
        }

        // Sub-satellite point (simplified)
        val lat = sat.inclination * sin(Math.toRadians(t * azSpeed * 0.5))
        val lon = ((az * 2 - t * 0.05 * 360 / 86400) % 360).let { if (it > 180) it - 360 else it }

        // Pass timing
        val nextPass = if (!isVisible && sat.altitudeKm < 10000) {
            ((60 - (t * 0.2).toInt() % 55).coerceAtLeast(1))
        } else null

        val passRemaining = if (isVisible && el > 5 && sat.altitudeKm < 10000) {
            (480 - (t % 480).toInt()).coerceAtLeast(1)
        } else null

        return SatelliteUiState(
            name = sat.name,
            noradId = sat.noradId,
            latitude = lat,
            longitude = lon,
            altitudeKm = sat.altitudeKm,
            azimuthDeg = az,
            elevationDeg = el,
            rangeKm = range,
            dopplerHz = doppler,
            velocityKmS = velocity,
            isVisible = isVisible,
            footprintKm = 2 * EARTH_RADIUS_KM * acos(EARTH_RADIUS_KM / (EARTH_RADIUS_KM + sat.altitudeKm)),
            category = sat.category,
            color = sat.color,
            frequencyHz = sat.frequencyHz,
            signalQuality = quality,
            nextPassMinutes = nextPass,
            passRemainingSeconds = passRemaining,
        )
    }

    override fun onCleared() {
        super.onCleared()
        stopTracking()
    }
}
