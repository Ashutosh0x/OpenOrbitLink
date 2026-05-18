package org.freesat.discovery

enum class DiscoveryLinkPath {
    DIRECT_NTN,
    AMATEUR_LEO,
    LORA_RELAY,
    GROUND_STATION,
}

data class NearbyPassCandidate(
    val name: String,
    val path: DiscoveryLinkPath,
    val startsInMinutes: Int,
    val durationSeconds: Int,
    val elevationDeg: Double,
    val azimuthDeg: Double,
    val snrMarginDb: Double,
    val stateLabel: String,
)

object NearbyPassScorer {
    fun score(candidate: NearbyPassCandidate): Int {
        val elevationScore = (candidate.elevationDeg / 90.0).coerceIn(0.0, 1.0)
        val durationScore = (candidate.durationSeconds / 720.0).coerceIn(0.0, 1.0)
        val marginScore = ((candidate.snrMarginDb + 5.0) / 35.0).coerceIn(0.0, 1.0)
        val waitScore = (1.0 - (candidate.startsInMinutes / 90.0).coerceIn(0.0, 1.0))

        return ((elevationScore * 0.45 +
            durationScore * 0.25 +
            marginScore * 0.20 +
            waitScore * 0.10) * 100).toInt()
    }

    fun recommendation(candidate: NearbyPassCandidate): String {
        val score = score(candidate)
        return when {
            candidate.startsInMinutes <= 0 && score >= 70 -> "Track now"
            score >= 75 -> "Prepare"
            score >= 55 -> "Queue for pass"
            else -> "Hold traffic"
        }
    }

    fun demoCandidates(): List<NearbyPassCandidate> = listOf(
        NearbyPassCandidate(
            name = "ISS (ZARYA)",
            path = DiscoveryLinkPath.AMATEUR_LEO,
            startsInMinutes = 0,
            durationSeconds = 510,
            elevationDeg = 52.0,
            azimuthDeg = 231.0,
            snrMarginDb = 16.3,
            stateLabel = "Visible now",
        ),
        NearbyPassCandidate(
            name = "NOAA-19",
            path = DiscoveryLinkPath.GROUND_STATION,
            startsInMinutes = 14,
            durationSeconds = 680,
            elevationDeg = 38.0,
            azimuthDeg = 171.0,
            snrMarginDb = 22.1,
            stateLabel = "Next pass",
        ),
        NearbyPassCandidate(
            name = "Direct NTN beam",
            path = DiscoveryLinkPath.DIRECT_NTN,
            startsInMinutes = 41,
            durationSeconds = 740,
            elevationDeg = 64.0,
            azimuthDeg = 104.0,
            snrMarginDb = 18.4,
            stateLabel = "Best reliability",
        ),
        NearbyPassCandidate(
            name = "LoRa neighbor relay",
            path = DiscoveryLinkPath.LORA_RELAY,
            startsInMinutes = 8,
            durationSeconds = 420,
            elevationDeg = 29.0,
            azimuthDeg = 287.0,
            snrMarginDb = 8.6,
            stateLabel = "Mesh assisted",
        ),
    )
}
