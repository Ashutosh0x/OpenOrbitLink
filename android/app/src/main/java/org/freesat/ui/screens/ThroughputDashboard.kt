package org.freesat.ui.screens

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.freesat.ui.theme.*

/**
 * ThroughputDashboard — Premium real-time modem performance visualization.
 *
 * Shows adaptive modulation status, link budget pipeline, throughput
 * timeline during satellite passes, and capacity comparison between
 * LoRa SF12, Adaptive SF, and LR-FHSS modes.
 *
 * Inspired by Jio's per-beam throughput optimization for satellite links.
 */

// Throughput data for each SF during a simulated pass
private data class PassTimePoint(
    val timeS: Int,
    val elevationDeg: Float,
    val sf: Int,
    val bitrateBps: Int,
    val profileName: String,
)

// Generate simulated pass throughput timeline
private fun generatePassTimeline(durationS: Int = 420, maxElevation: Float = 55f): List<PassTimePoint> {
    val points = mutableListOf<PassTimePoint>()
    for (t in 0 until durationS step 10) {
        val progress = t.toFloat() / durationS
        val el = maxElevation * kotlin.math.sin(progress * Math.PI).toFloat()
        val effectiveEl = el.coerceAtLeast(2f)

        val (sf, bitrate, name) = when {
            effectiveEl > 60 -> Triple(7, 5469, "SF7/BW125")
            effectiveEl > 45 -> Triple(8, 3125, "SF8/BW125")
            effectiveEl > 30 -> Triple(9, 1758, "SF9/BW125")
            effectiveEl > 20 -> Triple(10, 977, "SF10/BW125")
            effectiveEl > 10 -> Triple(11, 537, "SF11/BW125")
            else -> Triple(12, 293, "SF12/BW125")
        }
        points.add(PassTimePoint(t, effectiveEl, sf, bitrate, name))
    }
    return points
}

private fun sfColor(sf: Int): Color = when (sf) {
    7 -> SuccessGreen
    8 -> Color(0xFF00E5A0)
    9 -> SatelliteBlue
    10 -> Color(0xFF64B5F6)
    11 -> WarningAmber
    12 -> AlertRed
    else -> TextSecondary
}

@Composable
fun ThroughputDashboard() {
    val scrollState = rememberScrollState()

    // Animated values
    val infiniteTransition = rememberInfiniteTransition(label = "throughput")
    val pulseAlpha by infiniteTransition.animateFloat(
        initialValue = 0.6f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1500), RepeatMode.Reverse), label = "pulse"
    )

    // Simulated current state
    var currentSf by remember { mutableIntStateOf(12) }
    var currentBitrate by remember { mutableIntStateOf(293) }
    var currentMargin by remember { mutableFloatStateOf(2.1f) }
    var currentElevation by remember { mutableFloatStateOf(15f) }
    var adaptiveEnabled by remember { mutableStateOf(true) }
    var elapsedS by remember { mutableIntStateOf(0) }

    val timeline = remember { generatePassTimeline() }

    // Simulated pass animation
    LaunchedEffect(adaptiveEnabled) {
        while (true) {
            delay(1500)
            elapsedS = (elapsedS + 10) % 420
            val idx = (elapsedS / 10).coerceIn(0, timeline.size - 1)
            val point = timeline[idx]
            if (adaptiveEnabled) {
                currentSf = point.sf
                currentBitrate = point.bitrateBps
            } else {
                currentSf = 12
                currentBitrate = 293
            }
            currentElevation = point.elevationDeg
            currentMargin = when (currentSf) {
                7 -> 14.1f; 8 -> 11.0f; 9 -> 8.0f
                10 -> 5.0f; 11 -> 3.5f; else -> 2.1f
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(SpaceBlack)
            .verticalScroll(scrollState)
            .padding(16.dp)
    ) {
        // Header
        ScreenHeader("Throughput", "Adaptive Modem • Link Optimization", Icons.Filled.Speed)

        Spacer(Modifier.height(16.dp))

        // Adaptive toggle + current profile
        GlassCard {
            Column(Modifier.padding(16.dp)) {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Adaptive Modem", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Switch(
                        checked = adaptiveEnabled,
                        onCheckedChange = { adaptiveEnabled = it },
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = SuccessGreen,
                            checkedTrackColor = SuccessGreen.copy(alpha = 0.3f)
                        )
                    )
                }

                Spacer(Modifier.height(12.dp))

                // Current profile display
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                    ProfileChip("SF", "$currentSf", sfColor(currentSf), pulseAlpha)
                    ProfileChip("BW", "125k", SatelliteBlue, 1f)
                    ProfileChip("CR", "4/5", NebulaPurple, 1f)
                    ProfileChip("bps", "$currentBitrate", sfColor(currentSf), pulseAlpha)
                }

                Spacer(Modifier.height(12.dp))

                // Bitrate bar
                val maxBitrate = 5469f
                val bitrateProgress = currentBitrate / maxBitrate
                Text(
                    if (adaptiveEnabled) "⚡ ${currentBitrate} bps (${(currentBitrate.toFloat() / 293).let { "%.1f".format(it) }}× faster)"
                    else "🔒 Fixed SF12 — 293 bps",
                    color = if (adaptiveEnabled) sfColor(currentSf) else TextSecondary,
                    fontWeight = FontWeight.SemiBold, fontSize = 14.sp
                )
                Spacer(Modifier.height(4.dp))
                LinearProgressIndicator(
                    progress = { bitrateProgress },
                    modifier = Modifier.fillMaxWidth().height(6.dp),
                    color = sfColor(currentSf),
                    trackColor = DeepNavy,
                )
            }
        }

        Spacer(Modifier.height(16.dp))

        // Link Budget Pipeline
        GlassCard {
            Column(Modifier.padding(16.dp)) {
                Text("Link Budget", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Spacer(Modifier.height(4.dp))
                Text("Ground → Satellite path at ${currentElevation.toInt()}° elevation",
                    color = TextSecondary, fontSize = 12.sp)
                Spacer(Modifier.height(12.dp))
                LinkBudgetPipeline(currentElevation, currentSf, currentMargin)
            }
        }

        Spacer(Modifier.height(16.dp))

        // Throughput Timeline
        GlassCard {
            Column(Modifier.padding(16.dp)) {
                Text("Pass Throughput Timeline", color = TextPrimary,
                    fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Spacer(Modifier.height(4.dp))
                Text("7-minute pass • Max elevation 55°", color = TextSecondary, fontSize = 12.sp)
                Spacer(Modifier.height(12.dp))
                ThroughputBarChart(timeline, elapsedS)
                Spacer(Modifier.height(8.dp))
                // SF legend
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                    for (sf in 7..12) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Canvas(Modifier.size(8.dp)) { drawCircle(sfColor(sf)) }
                            Spacer(Modifier.width(3.dp))
                            Text("SF$sf", color = TextSecondary, fontSize = 10.sp)
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // Capacity Comparison
        GlassCard {
            Column(Modifier.padding(16.dp)) {
                Text("Capacity Comparison", color = TextPrimary,
                    fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Spacer(Modifier.height(4.dp))
                Text("Bytes per hour under 1% duty cycle", color = TextSecondary, fontSize = 12.sp)
                Spacer(Modifier.height(16.dp))
                CapacityBar("LoRa SF12 (Fixed)", 960, 51000, AlertRed)
                Spacer(Modifier.height(8.dp))
                CapacityBar("Adaptive SF", 19200, 51000, SuccessGreen)
                Spacer(Modifier.height(8.dp))
                CapacityBar("LR-FHSS CR2/3", 7500, 51000, SatelliteBlue)
                Spacer(Modifier.height(8.dp))
                CapacityBar("Combined (S-Band)", 51000, 51000, NebulaPurple)
            }
        }

        Spacer(Modifier.height(16.dp))

        // Stats row
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val pktHr = if (adaptiveEnabled) (36000 / (if (currentBitrate > 1000) 92 else 2867)).coerceAtMost(240) else 12
            Box(Modifier.weight(1f)) { StatChip("Packets/hr", "$pktHr") }
            Box(Modifier.weight(1f)) { StatChip("Bytes/hr", "${pktHr * 80}") }
            Box(Modifier.weight(1f)) { StatChip("Margin", "+${"%.1f".format(currentMargin)} dB") }
        }

        Spacer(Modifier.height(80.dp))
    }
}

@Composable
private fun ProfileChip(label: String, value: String, color: Color, alpha: Float) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, color = TextSecondary, fontSize = 10.sp)
        Text(
            value,
            color = color.copy(alpha = alpha),
            fontWeight = FontWeight.ExtraBold,
            fontSize = 22.sp
        )
    }
}

@Composable
private fun LinkBudgetPipeline(elevation: Float, sf: Int, margin: Float) {
    val textMeasurer = rememberTextMeasurer()

    Canvas(
        modifier = Modifier.fillMaxWidth().height(80.dp)
    ) {
        val w = size.width
        val h = size.height
        val segmentW = w / 5

        val txPower = 14f
        val txGain = 2.15f
        val pathLoss = 152f - (elevation - 30) * 0.5f
        val rxGain = 2f
        val rxPower = txPower + txGain - pathLoss + rxGain

        data class PipelineStage(val label: String, val value: String, val color: Color)
        val stages = listOf(
            PipelineStage("TX Power", "+${txPower.toInt()} dBm", SuccessGreen),
            PipelineStage("TX Ant", "+${String.format("%.1f", txGain)} dBi", SatelliteBlue),
            PipelineStage("Path Loss", "-${pathLoss.toInt()} dB", AlertRed),
            PipelineStage("RX Ant", "+${rxGain.toInt()} dBi", SatelliteBlue),
            PipelineStage("Margin", "+${String.format("%.1f", margin)} dB",
                if (margin > 5) SuccessGreen else if (margin > 2) WarningAmber else AlertRed),
        )

        for ((i, stage) in stages.withIndex()) {
            val x = i * segmentW
            val centerX = x + segmentW / 2

            // Box
            drawRoundRect(
                color = stage.color.copy(alpha = 0.15f),
                topLeft = Offset(x + 4, 10f),
                size = Size(segmentW - 8, h - 20),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(8f)
            )
            drawRoundRect(
                color = stage.color.copy(alpha = 0.6f),
                topLeft = Offset(x + 4, 10f),
                size = Size(segmentW - 8, h - 20),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(8f),
                style = Stroke(1.5f)
            )

            // Arrow between stages
            if (i < stages.size - 1) {
                drawLine(
                    color = TextSecondary.copy(alpha = 0.4f),
                    start = Offset(x + segmentW - 4, h / 2),
                    end = Offset(x + segmentW + 4, h / 2),
                    strokeWidth = 2f
                )
            }

            // Labels
            val labelResult = textMeasurer.measure(
                AnnotatedString(stage.label),
                style = TextStyle(fontSize = 9.sp, color = TextSecondary)
            )
            drawText(labelResult, topLeft = Offset(centerX - labelResult.size.width / 2, 16f))

            val valueResult = textMeasurer.measure(
                AnnotatedString(stage.value),
                style = TextStyle(fontSize = 11.sp, color = stage.color, fontWeight = FontWeight.Bold)
            )
            drawText(valueResult, topLeft = Offset(centerX - valueResult.size.width / 2, h / 2 - 4))
        }
    }
}

@Composable
private fun ThroughputBarChart(timeline: List<PassTimePoint>, currentTimeS: Int) {
    val textMeasurer = rememberTextMeasurer()

    Canvas(modifier = Modifier.fillMaxWidth().height(140.dp)) {
        val w = size.width
        val h = size.height
        val maxBitrate = 5469f
        val barWidth = w / timeline.size
        val bottomPadding = 20f

        for ((i, point) in timeline.withIndex()) {
            val x = i * barWidth
            val barH = (point.bitrateBps / maxBitrate) * (h - bottomPadding - 10)
            val color = sfColor(point.sf)
            val isActive = point.timeS == currentTimeS

            drawRect(
                color = if (isActive) color else color.copy(alpha = 0.6f),
                topLeft = Offset(x + 1, h - bottomPadding - barH),
                size = Size(barWidth - 2, barH),
            )

            if (isActive) {
                drawRect(
                    color = color,
                    topLeft = Offset(x, h - bottomPadding - barH - 2),
                    size = Size(barWidth, barH + 2),
                    style = Stroke(2f)
                )
            }
        }

        // Time axis labels
        for (t in listOf(0, 120, 210, 300, 420)) {
            val idx = (t / 10).coerceIn(0, timeline.size - 1)
            val x = idx * barWidth
            val label = "${t / 60}m${t % 60}s"
            val result = textMeasurer.measure(
                AnnotatedString(label),
                style = TextStyle(fontSize = 8.sp, color = TextSecondary)
            )
            drawText(result, topLeft = Offset(x, h - 16f))
        }
    }
}

@Composable
private fun CapacityBar(label: String, value: Int, maxValue: Int, color: Color) {
    Column {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(label, color = TextPrimary, fontSize = 13.sp)
            Text("${String.format("%,d", value)} B/hr", color = color,
                fontWeight = FontWeight.Bold, fontSize = 13.sp)
        }
        Spacer(Modifier.height(4.dp))
        LinearProgressIndicator(
            progress = { value.toFloat() / maxValue },
            modifier = Modifier.fillMaxWidth().height(10.dp),
            color = color,
            trackColor = DeepNavy,
            strokeCap = StrokeCap.Round,
        )
    }
}
