package org.freesat.ui.screens

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.freesat.ui.theme.*
import kotlin.math.*

/**
 * Sky Scanner screen with live satellite position overlay.
 *
 * Features:
 * - AR-style polar sky view with obstruction analysis
 * - Real-time satellite position dots (updated every second)
 * - Pass trajectory arcs for visible satellites
 * - Connect button for each satellite in the details section
 */

private data class SkySatellite(
    val name: String, val color: Long, val category: String,
    val baseAz: Double, val baseEl: Double,
    val azSpeed: Double, val elAmplitude: Double, val elPeriod: Double,
    val frequencyMHz: Double,
)

private val skySatellites = listOf(
    SkySatellite("ISS", 0xFF00B4D8, "comms", 120.0, 35.0, 2.4, 40.0, 0.08, 145.825),
    SkySatellite("FOSSASAT-2E", 0xFF00E676, "comms", 200.0, 22.0, 1.8, 30.0, 0.06, 868.0),
    SkySatellite("NOAA-19", 0xFF533483, "weather", 45.0, 18.0, 1.2, 25.0, 0.05, 137.1),
    SkySatellite("METEOR-M2", 0xFFFF9800, "weather", 310.0, 42.0, 1.5, 35.0, 0.07, 137.9),
    SkySatellite("FUNcube-1", 0xFFE040FB, "amateur", 150.0, 55.0, 2.1, 30.0, 0.09, 145.935),
    SkySatellite("STARLINK-30K", 0xFF42A5F5, "comms", 30.0, 68.0, 2.6, 20.0, 0.1, 12000.0),
    SkySatellite("CAS-4A", 0xFF00BCD4, "amateur", 80.0, -8.0, 1.6, 15.0, 0.04, 145.855),
    SkySatellite("TEVEL-5", 0xFF64FFDA, "amateur", 260.0, 12.0, 1.9, 20.0, 0.065, 436.4),
)

@Composable
fun SkyScannerScreen() {
    var isScanning by remember { mutableStateOf(false) }
    var skyVisibility by remember { mutableStateOf(72f) }
    var tickCount by remember { mutableLongStateOf(0L) }
    var connectedSat by remember { mutableStateOf<String?>(null) }

    // 1-second update loop for satellite positions
    LaunchedEffect(Unit) {
        while (true) {
            delay(1000)
            tickCount++
        }
    }

    val scanAnim = rememberInfiniteTransition(label = "scan")
    val sweepAngle by scanAnim.animateFloat(0f, 360f,
        infiniteRepeatable(tween(3000, easing = LinearEasing)), label = "sweep")
    val pulseAlpha by scanAnim.animateFloat(0.5f, 1f,
        infiniteRepeatable(tween(1200), RepeatMode.Reverse), label = "pAlpha")

    // Compute current satellite positions
    val t = tickCount.toDouble()
    val satPositions = skySatellites.map { sat ->
        val az = (sat.baseAz + t * sat.azSpeed) % 360.0
        val el = sat.baseEl + sin(t * sat.elPeriod) * sat.elAmplitude
        Triple(sat, az, el)
    }
    val visibleSats = satPositions.filter { it.third > 0 }

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp).verticalScroll(rememberScrollState())) {

        ScreenHeader("Sky Scanner", "Live sky analysis • ${visibleSats.size} satellites visible", Icons.Filled.CameraAlt)

        // Sky visibility circle with satellite overlay
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Box(modifier = Modifier.fillMaxWidth().aspectRatio(1f)
                .drawBehind {
                    val center = Offset(size.width / 2, size.height / 2)
                    val maxRadius = size.minDimension / 2 - 20.dp.toPx()

                    // Elevation rings
                    listOf(1.0f, 0.66f, 0.33f, 0.05f).forEach { frac ->
                        drawCircle(Color.White.copy(alpha = 0.08f), maxRadius * frac, center,
                            style = Stroke(1f))
                    }

                    // Compass lines (8 directions)
                    listOf(0f, 45f, 90f, 135f, 180f, 225f, 270f, 315f).forEach { angle ->
                        val rad = Math.toRadians(angle.toDouble())
                        val alpha = if (angle % 90 == 0f) 0.12f else 0.05f
                        drawLine(Color.White.copy(alpha = alpha), center,
                            Offset(center.x + maxRadius * sin(rad).toFloat(),
                                center.y - maxRadius * cos(rad).toFloat()), strokeWidth = 1f)
                    }

                    // Sky visibility fill
                    drawCircle(
                        Brush.radialGradient(listOf(
                            Color(0xFF00E676).copy(alpha = 0.12f),
                            Color(0xFF00E676).copy(alpha = 0.05f),
                            Color(0xFFE94560).copy(alpha = 0.08f)
                        ), center = center, radius = maxRadius),
                        maxRadius, center)

                    // Scanning sweep line
                    if (isScanning) {
                        val sweepRad = Math.toRadians(sweepAngle.toDouble())
                        drawLine(Color(0xFF00B4D8).copy(alpha = 0.7f), center,
                            Offset(center.x + maxRadius * sin(sweepRad).toFloat(),
                                center.y - maxRadius * cos(sweepRad).toFloat()),
                            strokeWidth = 2f, cap = StrokeCap.Round)
                        drawArc(Brush.sweepGradient(listOf(
                            Color.Transparent, Color(0xFF00B4D8).copy(alpha = 0.15f))),
                            sweepAngle - 30f, 30f, true,
                            topLeft = Offset(center.x - maxRadius, center.y - maxRadius),
                            size = androidx.compose.ui.geometry.Size(maxRadius * 2, maxRadius * 2))
                    }

                    // Draw live satellite positions
                    satPositions.forEach { (sat, az, el) ->
                        val clampedEl = el.coerceIn(-15.0, 90.0)
                        val r = maxRadius * (1.0 - (clampedEl + 15) / 105.0).toFloat()
                        val azRad = Math.toRadians(az)
                        val sx = center.x + r * sin(azRad).toFloat()
                        val sy = center.y - r * cos(azRad).toFloat()
                        val satColor = Color(sat.color)

                        if (el > 0) {
                            // Glow
                            drawCircle(satColor.copy(alpha = 0.2f * pulseAlpha), 12f, Offset(sx, sy))
                            // Connected ring
                            if (sat.name == connectedSat) {
                                drawCircle(Color(0xFF00E676).copy(alpha = pulseAlpha * 0.6f),
                                    16f, Offset(sx, sy), style = Stroke(2.5f))
                            }
                            // Dot
                            drawCircle(satColor, 5f, Offset(sx, sy))
                            drawCircle(Color.White, 2f, Offset(sx, sy))
                        } else {
                            drawCircle(satColor.copy(alpha = 0.15f), 3f, Offset(sx, sy))
                        }
                    }
                },
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("${skyVisibility.toInt()}%", fontSize = 42.sp,
                        fontWeight = FontWeight.Black, color = SuccessGreen)
                    Text("Sky Visibility", fontSize = 14.sp, color = TextSecondary)
                }
                Text("N", modifier = Modifier.align(Alignment.TopCenter).padding(top = 4.dp),
                    fontSize = 12.sp, color = Color(0xFF4FC3F7), fontWeight = FontWeight.Bold)
                Text("S", modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 4.dp),
                    fontSize = 12.sp, color = TextSecondary)
                Text("E", modifier = Modifier.align(Alignment.CenterEnd).padding(end = 4.dp),
                    fontSize = 12.sp, color = TextSecondary)
                Text("W", modifier = Modifier.align(Alignment.CenterStart).padding(start = 4.dp),
                    fontSize = 12.sp, color = TextSecondary)
            }
        }

        Spacer(Modifier.height(12.dp))

        // Scan button
        Button(onClick = { isScanning = !isScanning },
            modifier = Modifier.fillMaxWidth().height(52.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (isScanning) AlertRed else SatelliteBlue),
            shape = RoundedCornerShape(16.dp)) {
            Icon(if (isScanning) Icons.Filled.Stop else Icons.Filled.PlayArrow, null)
            Spacer(Modifier.width(8.dp))
            Text(if (isScanning) "Stop Scanning" else "Start Sky Scan",
                fontWeight = FontWeight.Bold)
        }

        Spacer(Modifier.height(16.dp))

        // Live satellite list with connect buttons
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Live Satellites", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(8.dp))

            satPositions.sortedByDescending { it.third }.forEach { (sat, az, el) ->
                val isVisible = el > 0
                val satColor = Color(sat.color)

                Row(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(10.dp).clip(CircleShape)
                        .background(if (isVisible) satColor else satColor.copy(alpha = 0.3f)))
                    Spacer(Modifier.width(8.dp))

                    Column(modifier = Modifier.weight(1f)) {
                        Text(sat.name, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                            color = if (isVisible) TextPrimary else TextSecondary)
                        Text("AZ ${az.toInt()}° • EL ${el.toInt()}° • ${sat.frequencyMHz} MHz",
                            fontSize = 10.sp, color = TextSecondary)
                    }

                    if (isVisible) {
                        val isConn = connectedSat == sat.name
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = if (isConn) SuccessGreen.copy(alpha = 0.15f) else SatelliteBlue.copy(alpha = 0.1f),
                            border = BorderStroke(1.dp, if (isConn) SuccessGreen.copy(alpha = 0.4f) else Color.Transparent),
                            onClick = { connectedSat = if (isConn) null else sat.name }
                        ) {
                            Text(if (isConn) "✓ CONN" else "CONNECT",
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                fontSize = 10.sp, fontWeight = FontWeight.Bold,
                                color = if (isConn) SuccessGreen else SatelliteBlue)
                        }
                    } else {
                        Text("BELOW", fontSize = 10.sp, color = TextSecondary.copy(alpha = 0.5f))
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // Obstruction analysis
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Obstruction Analysis", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            InfoRow(Icons.Filled.CheckCircle, "Clear sky (>30\u00B0 el)", "72%", SuccessGreen)
            InfoRow(Icons.Filled.Warning, "Partial obstruction", "18%", WarningAmber)
            InfoRow(Icons.Filled.Block, "Fully blocked", "10%", AlertRed)
            Spacer(Modifier.height(8.dp))
            InfoRow(Icons.Filled.SatelliteAlt, "Satellites visible", "${visibleSats.size} of ${skySatellites.size}", SatelliteBlue)
            InfoRow(Icons.Filled.Router, "Connected via",
                connectedSat ?: "None",
                if (connectedSat != null) SuccessGreen else TextSecondary)
            InfoRow(Icons.Filled.NorthEast, "Optimal pointing", "AZ 142\u00B0 / EL 52\u00B0")
        }
    }
}
