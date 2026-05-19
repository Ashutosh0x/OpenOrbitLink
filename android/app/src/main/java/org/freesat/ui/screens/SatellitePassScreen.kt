package org.freesat.ui.screens

import android.os.CountDownTimer
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
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
import kotlinx.coroutines.launch
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * Satellite Pass Timeline Screen
 *
 * Displays upcoming satellite passes with countdown timer, elevation arc,
 * and pass quality indicators. Queries backend /api/v1/passes endpoint.
 */

data class SatellitePassData(
    val satelliteName: String,
    val riseTime: Instant,
    val culminationTime: Instant,
    val setTime: Instant,
    val maxElevation: Double,
    val durationSeconds: Double,
    val riseAzimuth: Double,
    val setAzimuth: Double,
    val frequencyHz: Long = 868_000_000,
    val isHighPass: Boolean = false,
)

enum class PassState { UPCOMING, ACTIVE, PAST }

@Composable
fun SatellitePassScreen(
    passes: List<SatellitePassData> = emptyList(),
    isLoading: Boolean = false,
    onRefresh: () -> Unit = {},
) {
    val scope = rememberCoroutineScope()
    var currentTime by remember { mutableStateOf(Instant.now()) }

    // Update current time every second
    LaunchedEffect(Unit) {
        while (true) {
            currentTime = Instant.now()
            delay(1000)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    colors = listOf(
                        Color(0xFF0D1117),
                        Color(0xFF161B22),
                        Color(0xFF1A1A2E),
                    )
                )
            )
            .padding(16.dp)
    ) {
        // Header
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "Satellite Passes",
                color = Color.White,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
            )
            IconButton(onClick = onRefresh) {
                Icon(
                    Icons.Default.Refresh,
                    contentDescription = "Refresh",
                    tint = Color(0xFF4FC3F7),
                )
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        // Next pass countdown
        val nextPass = passes.firstOrNull {
            Duration.between(currentTime, it.riseTime).seconds > 0
        }
        if (nextPass != null) {
            NextPassCountdown(nextPass, currentTime)
            Spacer(modifier = Modifier.height(16.dp))
        }

        // Active pass indicator
        val activePass = passes.firstOrNull {
            currentTime.isAfter(it.riseTime) && currentTime.isBefore(it.setTime)
        }
        if (activePass != null) {
            ActivePassCard(activePass, currentTime)
            Spacer(modifier = Modifier.height(16.dp))
        }

        // Pass list
        if (isLoading) {
            Box(
                modifier = Modifier.fillMaxWidth().padding(32.dp),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(color = Color(0xFF4FC3F7))
            }
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(passes) { pass ->
                    val state = when {
                        currentTime.isAfter(pass.setTime) -> PassState.PAST
                        currentTime.isAfter(pass.riseTime) -> PassState.ACTIVE
                        else -> PassState.UPCOMING
                    }
                    PassCard(pass, state, currentTime)
                }
            }
        }
    }
}

@Composable
private fun NextPassCountdown(pass: SatellitePassData, now: Instant) {
    val eta = Duration.between(now, pass.riseTime)
    val hours = eta.toHours()
    val minutes = (eta.toMinutes() % 60)
    val seconds = (eta.seconds % 60)

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFF1A2332),
        ),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = "Next Pass",
                color = Color(0xFF8B949E),
                fontSize = 14.sp,
            )
            Text(
                text = pass.satelliteName,
                color = Color(0xFF4FC3F7),
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(modifier = Modifier.height(8.dp))

            // Countdown timer
            Row(
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                CountdownUnit(hours.toInt(), "h")
                Text(":", color = Color(0xFF4FC3F7), fontSize = 32.sp, fontWeight = FontWeight.Bold)
                CountdownUnit(minutes.toInt(), "m")
                Text(":", color = Color(0xFF4FC3F7), fontSize = 32.sp, fontWeight = FontWeight.Bold)
                CountdownUnit(seconds.toInt(), "s")
            }

            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Max elevation: ${pass.maxElevation.toInt()}\u00B0 | Duration: ${pass.durationSeconds.toInt()}s",
                color = Color(0xFF8B949E),
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
private fun CountdownUnit(value: Int, label: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = "%02d".format(value),
            color = Color.White,
            fontSize = 36.sp,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = label,
            color = Color(0xFF8B949E),
            fontSize = 12.sp,
        )
    }
}

@Composable
private fun ActivePassCard(pass: SatellitePassData, now: Instant) {
    val elapsed = Duration.between(pass.riseTime, now).seconds.toFloat()
    val total = pass.durationSeconds.toFloat()
    val progress = (elapsed / total).coerceIn(0f, 1f)

    val pulseAnim = rememberInfiniteTransition(label = "pulse")
    val alpha by pulseAnim.animateFloat(
        initialValue = 0.6f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "pulseAlpha",
    )

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFF1A3322).copy(alpha = alpha),
        ),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Box(
                    modifier = Modifier
                        .size(12.dp)
                        .clip(CircleShape)
                        .background(Color(0xFF4CAF50)),
                )
                Text(
                    text = "LIVE: ${pass.satelliteName} OVERHEAD",
                    color = Color(0xFF4CAF50),
                    fontWeight = FontWeight.Bold,
                    fontSize = 16.sp,
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            LinearProgressIndicator(
                progress = { progress },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .clip(RoundedCornerShape(3.dp)),
                color = Color(0xFF4CAF50),
                trackColor = Color(0xFF1A2332),
            )

            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "${(total - elapsed).toInt()}s remaining | Queued messages will transmit now",
                color = Color(0xFF8B949E),
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
private fun PassCard(
    pass: SatellitePassData,
    state: PassState,
    now: Instant,
) {
    val borderColor = when (state) {
        PassState.ACTIVE -> Color(0xFF4CAF50)
        PassState.UPCOMING -> if (pass.isHighPass) Color(0xFFFF9800) else Color(0xFF4FC3F7)
        PassState.PAST -> Color(0xFF30363D)
    }

    val formatter = DateTimeFormatter.ofPattern("HH:mm:ss")
        .withZone(ZoneId.systemDefault())

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFF161B22),
        ),
        shape = RoundedCornerShape(12.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, borderColor.copy(alpha = 0.3f)),
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Elevation indicator
            ElevationArc(
                maxElevation = pass.maxElevation.toFloat(),
                modifier = Modifier.size(48.dp),
                color = borderColor,
            )

            Spacer(modifier = Modifier.width(12.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = pass.satelliteName,
                    color = Color.White,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 16.sp,
                )
                Text(
                    text = "${formatter.format(pass.riseTime)} - ${formatter.format(pass.setTime)}",
                    color = Color(0xFF8B949E),
                    fontSize = 13.sp,
                )
                Text(
                    text = "Max ${pass.maxElevation.toInt()}\u00B0 | ${pass.durationSeconds.toInt()}s | ${pass.frequencyHz / 1_000_000} MHz",
                    color = Color(0xFF6E7681),
                    fontSize = 11.sp,
                )
            }

            // Quality badge
            val quality = when {
                pass.maxElevation > 60 -> "A+"
                pass.maxElevation > 45 -> "A"
                pass.maxElevation > 30 -> "B"
                pass.maxElevation > 15 -> "C"
                else -> "D"
            }
            val qualityColor = when {
                pass.maxElevation > 45 -> Color(0xFF4CAF50)
                pass.maxElevation > 20 -> Color(0xFFFF9800)
                else -> Color(0xFFF44336)
            }

            Text(
                text = quality,
                color = qualityColor,
                fontWeight = FontWeight.Bold,
                fontSize = 18.sp,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
}

@Composable
private fun ElevationArc(
    maxElevation: Float,
    modifier: Modifier = Modifier,
    color: Color = Color(0xFF4FC3F7),
) {
    Canvas(modifier = modifier) {
        val radius = size.minDimension / 2 - 4.dp.toPx()
        val center = Offset(size.width / 2, size.height / 2)

        // Background arc (180 degrees)
        drawArc(
            color = Color(0xFF30363D),
            startAngle = 180f,
            sweepAngle = 180f,
            useCenter = false,
            topLeft = Offset(center.x - radius, center.y - radius),
            size = androidx.compose.ui.geometry.Size(radius * 2, radius * 2),
            style = Stroke(width = 3.dp.toPx(), cap = StrokeCap.Round),
        )

        // Elevation arc (proportional to max elevation)
        val sweep = (maxElevation / 90f) * 180f
        drawArc(
            color = color,
            startAngle = 180f,
            sweepAngle = sweep,
            useCenter = false,
            topLeft = Offset(center.x - radius, center.y - radius),
            size = androidx.compose.ui.geometry.Size(radius * 2, radius * 2),
            style = Stroke(width = 3.dp.toPx(), cap = StrokeCap.Round),
        )
    }
}
