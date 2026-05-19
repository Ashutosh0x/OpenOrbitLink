package org.freesat.ui.components

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

/**
 * ISM Duty Cycle Budget Gauge
 *
 * Circular gauge showing remaining TX seconds this hour.
 * 1% ISM duty cycle = 36 seconds per hour maximum TX time.
 *
 * Color gradient:
 *   Green  (>20s remaining)
 *   Yellow (10-20s remaining)
 *   Red    (<10s remaining)
 *
 * Auto-refreshes every 30 seconds from backend /api/v1/duty_cycle endpoint.
 */

data class DutyCycleState(
    val budgetSeconds: Float = 36f,
    val usedSeconds: Float = 0f,
    val remainingSeconds: Float = 36f,
    val utilizationPercent: Float = 0f,
)

@Composable
fun DutyCycleGauge(
    state: DutyCycleState,
    modifier: Modifier = Modifier,
    onRefresh: (() -> Unit)? = null,
) {
    val remaining = state.remainingSeconds
    val total = state.budgetSeconds
    val progress = if (total > 0) (remaining / total).coerceIn(0f, 1f) else 0f

    // Determine color based on remaining budget
    val gaugeColor = when {
        remaining > 20f -> Color(0xFF4CAF50)     // Green
        remaining > 10f -> Color(0xFFFFC107)     // Yellow
        else -> Color(0xFFF44336)                 // Red
    }

    val animatedProgress by animateFloatAsState(
        targetValue = progress,
        animationSpec = tween(800, easing = EaseInOutCubic),
        label = "gaugeProgress",
    )

    // Auto-refresh
    LaunchedEffect(Unit) {
        while (true) {
            delay(30_000)
            onRefresh?.invoke()
        }
    }

    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFF161B22),
        ),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = "TX Duty Cycle Budget",
                color = Color(0xFF8B949E),
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium,
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Circular gauge
            Box(
                modifier = Modifier.size(140.dp),
                contentAlignment = Alignment.Center,
            ) {
                Canvas(modifier = Modifier.fillMaxSize()) {
                    val strokeWidth = 12.dp.toPx()
                    val radius = (size.minDimension - strokeWidth) / 2
                    val topLeft = Offset(
                        (size.width - radius * 2) / 2,
                        (size.height - radius * 2) / 2,
                    )
                    val arcSize = Size(radius * 2, radius * 2)

                    // Background arc
                    drawArc(
                        color = Color(0xFF30363D),
                        startAngle = 135f,
                        sweepAngle = 270f,
                        useCenter = false,
                        topLeft = topLeft,
                        size = arcSize,
                        style = Stroke(width = strokeWidth, cap = StrokeCap.Round),
                    )

                    // Progress arc with gradient
                    drawArc(
                        brush = Brush.sweepGradient(
                            colors = listOf(
                                gaugeColor.copy(alpha = 0.3f),
                                gaugeColor,
                            ),
                        ),
                        startAngle = 135f,
                        sweepAngle = 270f * animatedProgress,
                        useCenter = false,
                        topLeft = topLeft,
                        size = arcSize,
                        style = Stroke(width = strokeWidth, cap = StrokeCap.Round),
                    )
                }

                // Center text
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "${remaining.toInt()}",
                        color = gaugeColor,
                        fontSize = 36.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = "sec left",
                        color = Color(0xFF8B949E),
                        fontSize = 12.sp,
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Stats row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
            ) {
                DutyCycleStatItem(
                    value = "${state.usedSeconds.toInt()}s",
                    label = "Used",
                    color = Color(0xFFF44336),
                )
                DutyCycleStatItem(
                    value = "${remaining.toInt()}s",
                    label = "Available",
                    color = gaugeColor,
                )
                DutyCycleStatItem(
                    value = "${state.utilizationPercent.toInt()}%",
                    label = "Utilized",
                    color = Color(0xFF4FC3F7),
                )
            }

            // Warning text
            if (remaining < 10f) {
                Spacer(modifier = Modifier.height(12.dp))
                Surface(
                    color = Color(0xFFF44336).copy(alpha = 0.12f),
                    shape = RoundedCornerShape(8.dp),
                ) {
                    Text(
                        text = "Low TX budget -- messages will queue until next hour",
                        color = Color(0xFFF44336),
                        fontSize = 11.sp,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun DutyCycleStatItem(
    value: String,
    label: String,
    color: Color,
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
            color = color,
            fontSize = 18.sp,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = label,
            color = Color(0xFF6E7681),
            fontSize = 11.sp,
        )
    }
}
