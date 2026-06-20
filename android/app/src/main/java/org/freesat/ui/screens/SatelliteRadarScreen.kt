package org.freesat.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.freesat.ui.theme.*
import kotlin.math.*

// ── Data Model ──────────────────────────────────────────────────────────────

data class SatelliteUiData(
    val name: String, val noradId: Int,
    val latitude: Double, val longitude: Double,
    val altitudeKm: Double, val azimuthDeg: Double,
    val elevationDeg: Double, val rangeKm: Double,
    val dopplerHz: Double, val velocityKmS: Double,
    val isVisible: Boolean, val footprintKm: Double,
    val category: String, val color: Long,
    val frequencyHz: Long, val signalQuality: Float,
    val nextPassMinutes: Int? = null,
    val passRemainingSeconds: Int? = null,
)

enum class ServiceModeUi(val label: String, val color: Color) {
    STANDBY("STANDBY", WarningAmber),
    ACTIVE("ACTIVE", SuccessGreen),
    EMERGENCY("EMERGENCY", SOSRed),
}

// ── Demo Satellites ─────────────────────────────────────────────────────────

private fun generateDemoSatellites(tickCount: Long): List<SatelliteUiData> {
    val t = tickCount.toDouble()
    return listOf(
        SatelliteUiData("ISS (ZARYA)", 25544, 28.47 + sin(t * 0.02) * 10, -80.53 + t * 0.05,
            408.0, (120.0 + t * 2.4) % 360, 35.0 + sin(t * 0.08) * 40, 800.0 + cos(t * 0.05) * 300,
            3800.0 * cos(t * 0.03), 7.66, true, 2200.0, "comms", 0xFF00B4D8, 145_825_000, 0.72f,
            nextPassMinutes = null, passRemainingSeconds = (480 - (t % 480)).toInt()),
        SatelliteUiData("FOSSASAT-2E", 50985, 45.0 + sin(t * 0.015) * 15, 12.0 + t * 0.04,
            550.0, (200.0 + t * 1.8) % 360, 22.0 + sin(t * 0.06) * 30, 1200.0 + cos(t * 0.04) * 400,
            2100.0 * cos(t * 0.04), 7.58, true, 2400.0, "comms", 0xFF00E676, 868_000_000, 0.58f,
            nextPassMinutes = (14 + (t * 0.1).toInt() % 30)),
        SatelliteUiData("NOAA-19", 33591, 50.0 + sin(t * 0.01) * 20, 30.0 + t * 0.03,
            870.0, (45.0 + t * 1.2) % 360, 18.0 + sin(t * 0.05) * 25, 1800.0,
            -1500.0 * sin(t * 0.02), 7.45, true, 2800.0, "weather", 0xFF533483, 137_100_000, 0.45f,
            nextPassMinutes = (67 - (t * 0.2).toInt() % 60).coerceAtLeast(1)),
        SatelliteUiData("METEOR-M2 3", 57166, -10.0 + sin(t * 0.018) * 30, 80.0 + t * 0.035,
            835.0, (310.0 + t * 1.5) % 360, 42.0 + sin(t * 0.07) * 35, 950.0,
            2800.0 * cos(t * 0.025), 7.47, true, 2700.0, "weather", 0xFFFF9800, 137_900_000, 0.65f),
        SatelliteUiData("FUNcube-1", 39444, 55.0 + sin(t * 0.022) * 12, -40.0 + t * 0.06,
            695.0, (150.0 + t * 2.1) % 360, 55.0 + sin(t * 0.09) * 30, 650.0,
            4500.0 * cos(t * 0.035), 7.52, true, 2500.0, "amateur", 0xFFE040FB, 145_935_000, 0.82f),
        SatelliteUiData("CAS-4A", 44881, 20.0 + sin(t * 0.012) * 18, 110.0 + t * 0.045,
            520.0, (80.0 + t * 1.6) % 360, -8.0 + sin(t * 0.04) * 15, 2200.0,
            -1200.0 * sin(t * 0.03), 7.59, false, 2350.0, "amateur", 0xFF00BCD4, 145_855_000, 0.1f,
            nextPassMinutes = (90 - (t * 0.15).toInt() % 80).coerceAtLeast(5)),
        SatelliteUiData("TEVEL-5", 51069, 35.0 + sin(t * 0.02) * 14, -20.0 + t * 0.055,
            530.0, (260.0 + t * 1.9) % 360, 12.0 + sin(t * 0.065) * 20, 1500.0,
            3200.0 * cos(t * 0.028), 7.57, true, 2380.0, "amateur", 0xFF64FFDA, 436_400_000, 0.38f),
        SatelliteUiData("NOAA-18", 28654, -30.0 + sin(t * 0.008) * 22, -100.0 + t * 0.025,
            860.0, (170.0 + t * 1.1) % 360, -15.0 + sin(t * 0.03) * 10, 2800.0,
            -800.0 * sin(t * 0.02), 7.46, false, 2780.0, "weather", 0xFFFF5722, 137_912_500, 0.0f,
            nextPassMinutes = (120 - (t * 0.1).toInt() % 110).coerceAtLeast(10)),
        SatelliteUiData("STARLINK-30K", 60001, 10.0 + sin(t * 0.025) * 25, 50.0 + t * 0.07,
            550.0, (30.0 + t * 2.6) % 360, 68.0 + sin(t * 0.1) * 20, 580.0,
            5200.0 * cos(t * 0.04), 7.58, true, 2400.0, "comms", 0xFF42A5F5, 12_000_000_000, 0.88f),
        SatelliteUiData("OSCAR-100", 43700, -2.0, 28.0,
            35786.0, (185.0 + sin(t * 0.001) * 2) % 360, 25.0 + sin(t * 0.002) * 3, 37500.0,
            50.0 * sin(t * 0.01), 3.07, true, 17200.0, "amateur", 0xFF6C63FF, 10_489_750_000, 0.35f),
        SatelliteUiData("GOES-16", 41866, 0.1, -75.2,
            35786.0, (240.0 + sin(t * 0.0005) * 1) % 360, -5.0 + sin(t * 0.001) * 3, 40200.0,
            -20.0 * sin(t * 0.005), 3.07, false, 17200.0, "weather", 0xFFFFC107, 1_694_100_000, 0.0f,
            nextPassMinutes = null),
        SatelliteUiData("CUBEBEL-2", 44909, 42.0 + sin(t * 0.017) * 16, 65.0 + t * 0.05,
            480.0, (95.0 + t * 2.0) % 360, 5.0 + sin(t * 0.055) * 18, 1900.0,
            2600.0 * cos(t * 0.032), 7.61, true, 2280.0, "amateur", 0xFF76FF03, 435_580_000, 0.28f),
    )
}

// ── Main Screen ─────────────────────────────────────────────────────────────

@Composable
fun SatelliteRadarScreen() {
    var tickCount by remember { mutableLongStateOf(0L) }
    var satellites by remember { mutableStateOf(generateDemoSatellites(0)) }
    var selectedSat by remember { mutableStateOf<SatelliteUiData?>(null) }
    var connectedSat by remember { mutableStateOf<String?>(null) }
    var serviceMode by remember { mutableStateOf(ServiceModeUi.ACTIVE) }
    var isTracking by remember { mutableStateOf(true) }

    // 1-second update loop
    LaunchedEffect(isTracking) {
        while (isTracking) {
            delay(1000)
            tickCount++
            satellites = generateDemoSatellites(tickCount)
        }
    }

    val visibleCount = satellites.count { it.isVisible }
    val trackedCount = satellites.size

    // Sweep animation
    val sweepAnim = rememberInfiniteTransition(label = "sweep")
    val sweepAngle by sweepAnim.animateFloat(0f, 360f,
        infiniteRepeatable(tween(3000, easing = LinearEasing)), label = "sweepAngle")

    // Pulse for visible satellites
    val pulseAnim = rememberInfiniteTransition(label = "pulse")
    val pulseScale by pulseAnim.animateFloat(0.7f, 1.0f,
        infiniteRepeatable(tween(1200), RepeatMode.Reverse), label = "pulseScale")
    val pulseAlpha by pulseAnim.animateFloat(0.4f, 1.0f,
        infiniteRepeatable(tween(1500), RepeatMode.Reverse), label = "pulseAlpha")

    // Connected satellite glow
    val connectedGlow by pulseAnim.animateFloat(0.3f, 0.9f,
        infiniteRepeatable(tween(800), RepeatMode.Reverse), label = "connGlow")

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy, Color(0xFF0D0D1A))))) {

        // ── Header ──────────────────────────────────────────────
        Row(modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Box(modifier = Modifier.size(44.dp).background(
                Brush.linearGradient(listOf(AccentGradientStart, AccentGradientEnd)), CircleShape),
                contentAlignment = Alignment.Center
            ) { Icon(Icons.Filled.SatelliteAlt, null, tint = Color.White, modifier = Modifier.size(22.dp)) }
            Spacer(Modifier.width(12.dp))
            Column {
                Text("Satellite Radar", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
                Text("Real-time • $trackedCount tracked • $visibleCount visible",
                    fontSize = 11.sp, color = TextSecondary)
            }
            Spacer(Modifier.weight(1f))

            // Service mode chip
            Surface(
                shape = RoundedCornerShape(20.dp),
                color = serviceMode.color.copy(alpha = 0.15f),
                border = BorderStroke(1.dp, serviceMode.color.copy(alpha = 0.4f)),
                onClick = {
                    serviceMode = when (serviceMode) {
                        ServiceModeUi.STANDBY -> ServiceModeUi.ACTIVE
                        ServiceModeUi.ACTIVE -> ServiceModeUi.EMERGENCY
                        ServiceModeUi.EMERGENCY -> ServiceModeUi.STANDBY
                    }
                }
            ) {
                Row(modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(6.dp).clip(CircleShape)
                        .background(serviceMode.color.copy(alpha = pulseAlpha)))
                    Spacer(Modifier.width(5.dp))
                    Text(serviceMode.label, fontSize = 10.sp, fontWeight = FontWeight.Bold,
                        color = serviceMode.color)
                }
            }
        }

        // ── Stats Row ───────────────────────────────────────────
        Row(modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            RadarStatChip("Tracked", "$trackedCount", SatelliteBlue, Modifier.weight(1f))
            RadarStatChip("Visible", "$visibleCount", SuccessGreen, Modifier.weight(1f))
            RadarStatChip("Connected", connectedSat?.split(" ")?.firstOrNull() ?: "None",
                if (connectedSat != null) SuccessGreen else TextSecondary, Modifier.weight(1.3f))
        }

        // ── RADAR DISPLAY ───────────────────────────────────────
        Box(modifier = Modifier
            .fillMaxWidth()
            .weight(1f)
            .padding(horizontal = 8.dp, vertical = 4.dp)
            .clip(RoundedCornerShape(20.dp))
            .background(Color(0xFF080812))
            .border(1.dp, Color.White.copy(alpha = 0.06f), RoundedCornerShape(20.dp))
            .pointerInput(satellites) {
                detectTapGestures { offset ->
                    val centerX = size.width / 2f
                    val centerY = size.height / 2f
                    val maxR = minOf(centerX, centerY) * 0.88f

                    // Find tapped satellite
                    satellites.forEach { sat ->
                        if (sat.elevationDeg < -10) return@forEach
                        val el = sat.elevationDeg.coerceIn(-10.0, 90.0)
                        val r = maxR * (1.0 - (el + 10) / 100.0).toFloat()
                        val azRad = Math.toRadians(sat.azimuthDeg)
                        val sx = centerX + r * sin(azRad).toFloat()
                        val sy = centerY - r * cos(azRad).toFloat()
                        val dist = sqrt((offset.x - sx).pow(2) + (offset.y - sy).pow(2))
                        if (dist < 36f) {
                            selectedSat = sat
                        }
                    }
                }
            }
            .drawBehind {
                drawRadar(this, satellites, sweepAngle, pulseScale, pulseAlpha, connectedSat, connectedGlow)
            },
            contentAlignment = Alignment.Center
        ) {
            // Compass labels
            Text("N", modifier = Modifier.align(Alignment.TopCenter).padding(top = 6.dp),
                fontSize = 13.sp, color = Color(0xFF4FC3F7), fontWeight = FontWeight.Bold)
            Text("S", modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 6.dp),
                fontSize = 13.sp, color = TextSecondary.copy(alpha = 0.6f))
            Text("E", modifier = Modifier.align(Alignment.CenterEnd).padding(end = 8.dp),
                fontSize = 13.sp, color = TextSecondary.copy(alpha = 0.6f))
            Text("W", modifier = Modifier.align(Alignment.CenterStart).padding(start = 8.dp),
                fontSize = 13.sp, color = TextSecondary.copy(alpha = 0.6f))

            // Center zenith marker
            Text("90°", fontSize = 9.sp, color = TextSecondary.copy(alpha = 0.4f))
        }

        // ── Selected Satellite Detail Card ──────────────────────
        AnimatedVisibility(
            visible = selectedSat != null,
            enter = slideInVertically(initialOffsetY = { it }) + fadeIn(),
            exit = slideOutVertically(targetOffsetY = { it }) + fadeOut(),
        ) {
            selectedSat?.let { sat ->
                SatelliteDetailCard(
                    sat = sat,
                    isConnected = connectedSat == sat.name,
                    onConnect = {
                        connectedSat = if (connectedSat == sat.name) null else sat.name
                    },
                    onDismiss = { selectedSat = null },
                )
            }
        }

        // ── Connected Satellite Bar ─────────────────────────────
        if (connectedSat != null && selectedSat == null) {
            val connected = satellites.find { it.name == connectedSat }
            if (connected != null) {
                Surface(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp),
                    shape = RoundedCornerShape(16.dp),
                    color = SuccessGreen.copy(alpha = 0.08f),
                    border = BorderStroke(1.dp, SuccessGreen.copy(alpha = connectedGlow * 0.5f)),
                    onClick = { selectedSat = connected }
                ) {
                    Row(modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(10.dp).clip(CircleShape)
                            .background(SuccessGreen.copy(alpha = connectedGlow)))
                        Spacer(Modifier.width(10.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Connected: ${connected.name}", color = SuccessGreen,
                                fontWeight = FontWeight.Bold, fontSize = 13.sp)
                            Text("EL ${connected.elevationDeg.toInt()}° • AZ ${connected.azimuthDeg.toInt()}° • ${connected.rangeKm.toInt()} km",
                                color = TextSecondary, fontSize = 11.sp)
                        }
                        if (connected.passRemainingSeconds != null) {
                            StatusPill("${connected.passRemainingSeconds}s left", SuccessGreen)
                        } else if (connected.isVisible) {
                            StatusPill("VISIBLE", SuccessGreen)
                        } else {
                            StatusPill("BELOW HORIZON", WarningAmber)
                        }
                    }
                }
            }
        }
    }
}

// ── Radar Drawing ───────────────────────────────────────────────────────────

private fun drawRadar(
    scope: DrawScope,
    satellites: List<SatelliteUiData>,
    sweepAngle: Float,
    pulseScale: Float,
    pulseAlpha: Float,
    connectedSat: String?,
    connectedGlow: Float,
) = with(scope) {
    val cx = size.width / 2f
    val cy = size.height / 2f
    val maxR = minOf(cx, cy) * 0.88f

    // Grid lines (elevation rings)
    val elevations = listOf(0f, 15f, 30f, 45f, 60f, 75f)
    elevations.forEach { el ->
        val r = maxR * (1f - el / 90f)
        drawCircle(Color.White.copy(alpha = 0.06f), r, Offset(cx, cy), style = Stroke(1f))
    }
    // Horizon ring (thicker)
    drawCircle(Color(0xFF1A3350).copy(alpha = 0.6f), maxR, Offset(cx, cy), style = Stroke(2f))

    // Compass lines (N, NE, E, SE, S, SW, W, NW)
    for (i in 0 until 8) {
        val angle = Math.toRadians(i * 45.0)
        val alpha = if (i % 2 == 0) 0.12f else 0.05f
        drawLine(
            Color.White.copy(alpha = alpha),
            Offset(cx, cy),
            Offset(cx + maxR * sin(angle).toFloat(), cy - maxR * cos(angle).toFloat()),
            strokeWidth = 1f,
        )
    }

    // Radar sweep line with afterglow
    val sweepRad = Math.toRadians(sweepAngle.toDouble())
    drawLine(
        Color(0xFF00B4D8).copy(alpha = 0.6f),
        Offset(cx, cy),
        Offset(cx + maxR * sin(sweepRad).toFloat(), cy - maxR * cos(sweepRad).toFloat()),
        strokeWidth = 2f, cap = StrokeCap.Round,
    )

    // Sweep afterglow arc
    drawArc(
        Brush.sweepGradient(
            0f to Color.Transparent,
            0.7f to Color.Transparent,
            0.85f to Color(0xFF00B4D8).copy(alpha = 0.03f),
            1f to Color(0xFF00B4D8).copy(alpha = 0.12f),
        ),
        startAngle = sweepAngle - 90f - 40f,
        sweepAngle = 40f,
        useCenter = true,
        topLeft = Offset(cx - maxR, cy - maxR),
        size = Size(maxR * 2, maxR * 2),
    )

    // Draw satellites
    satellites.forEach { sat ->
        val el = sat.elevationDeg.coerceIn(-15.0, 90.0)
        val r = maxR * (1.0 - (el + 15) / 105.0).toFloat()
        val azRad = Math.toRadians(sat.azimuthDeg)
        val sx = cx + r * sin(azRad).toFloat()
        val sy = cy - r * cos(azRad).toFloat()
        val satColor = Color(sat.color)

        if (sat.isVisible) {
            // Outer glow for visible satellites
            val glowR = 14f * pulseScale
            drawCircle(satColor.copy(alpha = 0.15f * pulseAlpha), glowR, Offset(sx, sy))

            // Connected satellite ring
            if (sat.name == connectedSat) {
                drawCircle(SuccessGreen.copy(alpha = connectedGlow * 0.6f), 18f, Offset(sx, sy),
                    style = Stroke(2.5f))
                drawCircle(SuccessGreen.copy(alpha = connectedGlow * 0.2f), 24f, Offset(sx, sy))
            }

            // Main dot
            drawCircle(satColor, 6f, Offset(sx, sy))
            drawCircle(Color.White, 2.5f, Offset(sx, sy))
        } else {
            // Below horizon — faint dot
            drawCircle(satColor.copy(alpha = 0.2f), 4f, Offset(sx, sy))
            drawCircle(satColor.copy(alpha = 0.08f), 8f, Offset(sx, sy))
        }
    }

    // Center crosshair (zenith)
    val chSize = 8f
    drawLine(Color.White.copy(alpha = 0.2f), Offset(cx - chSize, cy), Offset(cx + chSize, cy), 1f)
    drawLine(Color.White.copy(alpha = 0.2f), Offset(cx, cy - chSize), Offset(cx, cy + chSize), 1f)
    drawCircle(Color.White.copy(alpha = 0.15f), 3f, Offset(cx, cy))
}

// ── Satellite Detail Card ───────────────────────────────────────────────────

@Composable
private fun SatelliteDetailCard(
    sat: SatelliteUiData,
    isConnected: Boolean,
    onConnect: () -> Unit,
    onDismiss: () -> Unit,
) {
    val satColor = Color(sat.color)
    val categoryLabel = when (sat.category) {
        "comms" -> "📡 Communications"
        "weather" -> "🌤️ Weather"
        "amateur" -> "📻 Amateur Radio"
        else -> "🛰️ Other"
    }

    Surface(
        modifier = Modifier.fillMaxWidth().padding(8.dp),
        shape = RoundedCornerShape(20.dp),
        color = SurfaceCard.copy(alpha = 0.95f),
        border = BorderStroke(1.dp, satColor.copy(alpha = 0.3f)),
        tonalElevation = 4.dp,
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header row
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(modifier = Modifier.size(40.dp).clip(CircleShape)
                    .background(satColor.copy(alpha = 0.15f)),
                    contentAlignment = Alignment.Center) {
                    Box(Modifier.size(14.dp).clip(CircleShape).background(satColor))
                }
                Spacer(Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(sat.name, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = TextPrimary)
                    Text("NORAD ${sat.noradId} • $categoryLabel",
                        fontSize = 11.sp, color = TextSecondary)
                }
                IconButton(onClick = onDismiss) {
                    Icon(Icons.Filled.Close, "Close", tint = TextSecondary, modifier = Modifier.size(20.dp))
                }
            }

            Spacer(Modifier.height(12.dp))

            // Status badge
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (sat.isVisible) {
                    StatusPill(if (sat.passRemainingSeconds != null)
                        "OVERHEAD • ${sat.passRemainingSeconds}s" else "VISIBLE", SuccessGreen)
                } else {
                    StatusPill("BELOW HORIZON", WarningAmber)
                }
                if (sat.nextPassMinutes != null) {
                    StatusPill("Next: ${sat.nextPassMinutes}m", SatelliteBlue)
                }
                StatusPill("${sat.frequencyHz / 1_000_000} MHz", NebulaPurple)
            }

            Spacer(Modifier.height(12.dp))

            // Metrics grid
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                MetricItem("Azimuth", "${sat.azimuthDeg.toInt()}°", satColor)
                MetricItem("Elevation", "${sat.elevationDeg.toInt()}°",
                    if (sat.elevationDeg > 30) SuccessGreen else if (sat.elevationDeg > 0) SatelliteBlue else AlertRed)
                MetricItem("Range", "${sat.rangeKm.toInt()} km", TextPrimary)
                MetricItem("Alt", "${sat.altitudeKm.toInt()} km", TextPrimary)
            }

            Spacer(Modifier.height(8.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                MetricItem("Velocity", "${sat.velocityKmS} km/s", TextPrimary)
                MetricItem("Doppler", "${sat.dopplerHz.toInt()} Hz", NebulaPurple)
                MetricItem("Footprint", "${sat.footprintKm.toInt()} km", TextPrimary)
                MetricItem("Quality", "${(sat.signalQuality * 100).toInt()}%",
                    if (sat.signalQuality > 0.6f) SuccessGreen else WarningAmber)
            }

            Spacer(Modifier.height(10.dp))

            // Signal quality bar
            Text("Signal Quality", fontSize = 11.sp, color = TextSecondary)
            Spacer(Modifier.height(4.dp))
            LinearProgressIndicator(
                progress = { sat.signalQuality },
                modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
                color = when {
                    sat.signalQuality > 0.7f -> SuccessGreen
                    sat.signalQuality > 0.4f -> SatelliteBlue
                    sat.signalQuality > 0.2f -> WarningAmber
                    else -> AlertRed
                },
                trackColor = Color.White.copy(alpha = 0.06f),
            )

            Spacer(Modifier.height(14.dp))

            // CONNECT / DISCONNECT button
            Button(
                onClick = onConnect,
                modifier = Modifier.fillMaxWidth().height(50.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isConnected) SuccessGreen else SatelliteBlue,
                    contentColor = SpaceBlack,
                ),
                elevation = ButtonDefaults.buttonElevation(
                    defaultElevation = if (isConnected) 8.dp else 4.dp
                ),
            ) {
                Icon(
                    if (isConnected) Icons.Filled.CheckCircle else Icons.Filled.SatelliteAlt,
                    null, modifier = Modifier.size(20.dp),
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    if (isConnected) "CONNECTED ✓ Routing via ${sat.name.split(" ")[0]}"
                    else "CONNECT TO ${sat.name.split(" ")[0]}",
                    fontWeight = FontWeight.Black, fontSize = 14.sp,
                )
            }

            if (isConnected) {
                Spacer(Modifier.height(6.dp))
                Text("Messages will route via this satellite during next pass window",
                    fontSize = 11.sp, color = SuccessGreen.copy(alpha = 0.7f),
                    textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            }
        }
    }
}

// ── Helper Composables ──────────────────────────────────────────────────────

@Composable
private fun RadarStatChip(label: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        color = color.copy(alpha = 0.08f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.2f)),
    ) {
        Column(modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = color,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(label, fontSize = 10.sp, color = TextSecondary)
        }
    }
}

@Composable
private fun MetricItem(label: String, value: String, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = color)
        Text(label, fontSize = 10.sp, color = TextSecondary)
    }
}
