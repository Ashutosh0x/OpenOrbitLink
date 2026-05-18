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
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.freesat.ui.theme.*
import kotlin.math.cos
import kotlin.math.sin

@Composable
fun LinkDashboardScreen() {
    // Simulated live telemetry
    val anim = rememberInfiniteTransition(label = "telem")
    val snrValue by anim.animateFloat(18f, 28f, infiniteRepeatable(tween(4000), RepeatMode.Reverse), label = "snr")
    val dopplerShift by anim.animateFloat(-4.2f, 4.8f, infiniteRepeatable(tween(6000), RepeatMode.Reverse), label = "dop")
    val berValue by anim.animateFloat(0.001f, 0.0001f, infiniteRepeatable(tween(5000), RepeatMode.Reverse), label = "ber")
    val passProgress by anim.animateFloat(0f, 1f, infiniteRepeatable(tween(12000), RepeatMode.Restart), label = "pass")
    val fecCorr by anim.animateFloat(0f, 5f, infiniteRepeatable(tween(3000), RepeatMode.Reverse), label = "fec")

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp).verticalScroll(rememberScrollState())) {

        // Header
        ScreenHeader("Link Dashboard", "Real-time satellite link telemetry", Icons.Filled.Speed)

        // Pass progress bar
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.SatelliteAlt, null, tint = SatelliteBlue, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
                Text("ISS Pass Progress", style = MaterialTheme.typography.labelLarge, color = TextPrimary)
                Spacer(Modifier.weight(1f))
                Text("${(passProgress * 8.5).toInt()}m / 8m 30s", fontSize = 12.sp, color = SatelliteBlue)
            }
            Spacer(Modifier.height(10.dp))
            LinearProgressIndicator(progress = { passProgress },
                modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)),
                color = SatelliteBlue, trackColor = SatelliteBlue.copy(alpha = 0.15f))
            Spacer(Modifier.height(6.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("AOS 14:23", fontSize = 10.sp, color = TextSecondary)
                Text("TCA 14:27", fontSize = 10.sp, color = SatelliteBlue)
                Text("LOS 14:31", fontSize = 10.sp, color = TextSecondary)
            }
        }

        Spacer(Modifier.height(16.dp))

        // SNR Gauge + Doppler side by side
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            // SNR Gauge
            GlassCard(modifier = Modifier.weight(1f)) {
                Text("SNR", fontSize = 12.sp, color = TextSecondary, textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                Box(modifier = Modifier.fillMaxWidth().aspectRatio(1f)
                    .drawBehind {
                        val strokeWidth = 12.dp.toPx()
                        val radius = (size.minDimension - strokeWidth) / 2
                        val center = Offset(size.width / 2, size.height / 2)
                        // Track
                        drawArc(Color(0xFF2A2A4A), 135f, 270f, false,
                            topLeft = Offset(center.x - radius, center.y - radius),
                            size = Size(radius * 2, radius * 2),
                            style = Stroke(strokeWidth, cap = StrokeCap.Round))
                        // Value arc
                        val sweep = (snrValue / 35f) * 270f
                        val color = when {
                            snrValue > 20 -> Color(0xFF00E676)
                            snrValue > 10 -> Color(0xFFFFAB00)
                            else -> Color(0xFFE94560)
                        }
                        drawArc(color, 135f, sweep, false,
                            topLeft = Offset(center.x - radius, center.y - radius),
                            size = Size(radius * 2, radius * 2),
                            style = Stroke(strokeWidth, cap = StrokeCap.Round))
                    }, contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("${String.format("%.1f", snrValue)}", fontSize = 28.sp,
                            fontWeight = FontWeight.Black, color = SuccessGreen)
                        Text("dB", fontSize = 12.sp, color = TextSecondary)
                    }
                }
                Text(if (snrValue > 20) "EXCELLENT" else if (snrValue > 10) "GOOD" else "MARGINAL",
                    fontSize = 11.sp, color = if (snrValue > 20) SuccessGreen else WarningAmber,
                    textAlign = TextAlign.Center, fontWeight = FontWeight.Bold,
                    modifier = Modifier.fillMaxWidth())
            }

            // Doppler
            GlassCard(modifier = Modifier.weight(1f)) {
                Text("Doppler Shift", fontSize = 12.sp, color = TextSecondary,
                    textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                Box(modifier = Modifier.fillMaxWidth().aspectRatio(1f)
                    .drawBehind {
                        val center = Offset(size.width / 2, size.height / 2)
                        val radius = size.minDimension / 2 - 20.dp.toPx()
                        // Dial marks
                        for (i in -5..5) {
                            val angle = Math.toRadians((135 + ((i + 5) / 10.0) * 270).toDouble())
                            val inner = radius * 0.8f
                            drawLine(Color(0xFF3A3A5C),
                                Offset(center.x + inner * cos(angle).toFloat(), center.y + inner * sin(angle).toFloat()),
                                Offset(center.x + radius * cos(angle).toFloat(), center.y + radius * sin(angle).toFloat()),
                                strokeWidth = if (i == 0) 3f else 1.5f)
                        }
                        // Needle
                        val needleAngle = 135 + ((dopplerShift + 5) / 10) * 270
                        rotate(needleAngle, center) {
                            drawLine(Color(0xFFE94560), center,
                                Offset(center.x, center.y - radius * 0.7f), strokeWidth = 3f)
                        }
                        drawCircle(Color(0xFFE94560), 6.dp.toPx(), center)
                    }, contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier.padding(top = 30.dp)) {
                        Text(String.format("%+.1f", dopplerShift), fontSize = 22.sp,
                            fontWeight = FontWeight.Black, color = AlertRed)
                        Text("kHz", fontSize = 12.sp, color = TextSecondary)
                    }
                }
                Text("AI Compensated", fontSize = 11.sp, color = SatelliteBlue,
                    textAlign = TextAlign.Center, fontWeight = FontWeight.Bold,
                    modifier = Modifier.fillMaxWidth())
            }
        }

        Spacer(Modifier.height(16.dp))

        // Stats grid
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricCard("BER", String.format("%.4f", berValue), if (berValue < 0.001) SuccessGreen else WarningAmber, Modifier.weight(1f))
            MetricCard("FEC Fix", "${fecCorr.toInt()}/block", SatelliteBlue, Modifier.weight(1f))
            MetricCard("Packets", "247 OK", SuccessGreen, Modifier.weight(1f))
            MetricCard("Lost", "3", AlertRed, Modifier.weight(1f))
        }

        Spacer(Modifier.height(16.dp))

        // Frequency info
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("RF Parameters", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            InfoRow(Icons.Filled.Waves, "Center frequency", "145.800 MHz")
            InfoRow(Icons.Filled.GraphicEq, "Modulation", "BPSK @ 1200 baud")
            InfoRow(Icons.Filled.Memory, "FEC", "RS(255,223) + Viterbi k=7")
            InfoRow(Icons.Filled.Security, "Encryption", "AES-256-GCM active")
            InfoRow(Icons.Filled.Thermostat, "Noise temp", "520 K")
            InfoRow(Icons.Filled.SettingsInputAntenna, "Antenna", "1/4\u03BB whip (0 dBi)")
        }
    }
}

@Composable
fun MetricCard(label: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Surface(modifier = modifier, shape = RoundedCornerShape(14.dp),
        color = color.copy(alpha = 0.08f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.25f))) {
        Column(modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, fontSize = 14.sp, fontWeight = FontWeight.Bold, color = color,
                textAlign = TextAlign.Center)
            Text(label, fontSize = 10.sp, color = TextSecondary)
        }
    }
}
