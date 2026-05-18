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
import org.freesat.ui.theme.*
import kotlin.math.*

@Composable
fun SkyScannerScreen() {
    var isScanning by remember { mutableStateOf(false) }
    var skyVisibility by remember { mutableStateOf(72f) }

    val scanAnim = rememberInfiniteTransition(label = "scan")
    val sweepAngle by scanAnim.animateFloat(0f, 360f,
        infiniteRepeatable(tween(3000, easing = LinearEasing)), label = "sweep")
    val pulseRadius by scanAnim.animateFloat(0.3f, 1f,
        infiniteRepeatable(tween(2000), RepeatMode.Reverse), label = "radius")

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp).verticalScroll(rememberScrollState())) {

        ScreenHeader("Sky Scanner", "AR sky visibility analysis", Icons.Filled.CameraAlt)

        // Sky visibility circle
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Box(modifier = Modifier.fillMaxWidth().aspectRatio(1f)
                .drawBehind {
                    val center = Offset(size.width / 2, size.height / 2)
                    val maxRadius = size.minDimension / 2 - 20.dp.toPx()

                    // Elevation rings: 10, 30, 60, 90
                    listOf(0.9f, 0.66f, 0.33f, 0.05f).forEachIndexed { i, frac ->
                        drawCircle(Color.White.copy(alpha = 0.08f), maxRadius * frac, center,
                            style = Stroke(1f))
                    }

                    // Compass lines
                    listOf(0f, 90f, 180f, 270f).forEach { angle ->
                        val rad = Math.toRadians(angle.toDouble())
                        drawLine(Color.White.copy(alpha = 0.1f), center,
                            Offset(center.x + maxRadius * sin(rad).toFloat(),
                                center.y - maxRadius * cos(rad).toFloat()), strokeWidth = 1f)
                    }

                    // Sky visibility fill (green = clear, red = obstructed)
                    drawCircle(
                        Brush.radialGradient(listOf(
                            Color(0xFF00E676).copy(alpha = 0.15f),
                            Color(0xFF00E676).copy(alpha = 0.05f),
                            Color(0xFFE94560).copy(alpha = 0.1f)
                        ), center = center, radius = maxRadius),
                        maxRadius, center)

                    // Scanning sweep line
                    if (isScanning) {
                        val sweepRad = Math.toRadians(sweepAngle.toDouble())
                        drawLine(Color(0xFF00B4D8).copy(alpha = 0.7f), center,
                            Offset(center.x + maxRadius * sin(sweepRad).toFloat(),
                                center.y - maxRadius * cos(sweepRad).toFloat()),
                            strokeWidth = 2f, cap = StrokeCap.Round)
                        // Sweep glow
                        drawArc(Brush.sweepGradient(listOf(
                            Color.Transparent, Color(0xFF00B4D8).copy(alpha = 0.2f))),
                            sweepAngle - 30f, 30f, true,
                            topLeft = Offset(center.x - maxRadius, center.y - maxRadius),
                            size = androidx.compose.ui.geometry.Size(maxRadius * 2, maxRadius * 2))
                    }

                    // Satellite pass arc (predicted ISS track)
                    val passPoints = (0..20).map { i ->
                        val t = i / 20f
                        val az = Math.toRadians((120 + t * 180).toDouble())
                        val elFrac = 1f - sin(t * Math.PI).toFloat() * 0.6f
                        Offset(center.x + maxRadius * elFrac * sin(az).toFloat(),
                            center.y - maxRadius * elFrac * cos(az).toFloat())
                    }
                    for (i in 0 until passPoints.size - 1) {
                        drawLine(Color(0xFF00B4D8), passPoints[i], passPoints[i + 1],
                            strokeWidth = 3f, cap = StrokeCap.Round)
                    }

                    // ISS position dot
                    val issIdx = (pulseRadius * 15).toInt().coerceIn(0, passPoints.size - 1)
                    drawCircle(Color(0xFF00B4D8), 8.dp.toPx() * pulseRadius, passPoints[issIdx])
                    drawCircle(Color.White, 4.dp.toPx(), passPoints[issIdx])
                },
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("${skyVisibility.toInt()}%", fontSize = 42.sp,
                        fontWeight = FontWeight.Black, color = SuccessGreen)
                    Text("Sky Visibility", fontSize = 14.sp, color = TextSecondary)
                }
                // Compass labels
                Text("N", modifier = Modifier.align(Alignment.TopCenter).padding(top = 4.dp),
                    fontSize = 12.sp, color = TextSecondary, fontWeight = FontWeight.Bold)
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

        // Visibility details
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Obstruction Analysis", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            InfoRow(Icons.Filled.CheckCircle, "Clear sky (>30\u00B0 el)", "72%", SuccessGreen)
            InfoRow(Icons.Filled.Warning, "Partial obstruction", "18%", WarningAmber)
            InfoRow(Icons.Filled.Block, "Fully blocked", "10%", AlertRed)
            Spacer(Modifier.height(8.dp))
            InfoRow(Icons.Filled.SatelliteAlt, "ISS visibility", "PASS IN VIEW", SuccessGreen)
            InfoRow(Icons.Filled.Schedule, "Next ISS pass", "14:23 UTC (23 min)")
            InfoRow(Icons.Filled.NorthEast, "Optimal pointing", "AZ 142\u00B0 / EL 52\u00B0")
        }
    }
}
