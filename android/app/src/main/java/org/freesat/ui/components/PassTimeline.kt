package org.freesat.ui.components

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.freesat.data.PassEntity
import org.freesat.ui.theme.*

/**
 * Horizontal scrollable timeline showing upcoming satellite passes.
 *
 * Visual:
 *   Now  ──●────────────●──────────●────── 24h
 *          ISS 14:23    FOSSA      ISS 16:45
 *          52° 8m30s    38° 11m    71° 6m
 */
@Composable
fun PassTimeline(
    passes: List<PassEntity>,
    nextPassCountdown: Long,
    modifier: Modifier = Modifier
) {
    val scrollState = rememberScrollState()

    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = SurfaceCard.copy(alpha = 0.6f),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.08f))
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Pass Timeline", fontWeight = FontWeight.Bold, color = SatelliteBlue)
                Spacer(Modifier.weight(1f))
                if (nextPassCountdown > 0) {
                    Surface(
                        shape = RoundedCornerShape(10.dp),
                        color = SatelliteBlue.copy(alpha = 0.15f)
                    ) {
                        Text(
                            formatCountdown(nextPassCountdown),
                            color = SatelliteBlue,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
                        )
                    }
                }
            }

            Spacer(Modifier.height(16.dp))

            if (passes.isEmpty()) {
                Text(
                    "No passes scheduled — connect to backend to fetch",
                    color = TextSecondary,
                    fontSize = 12.sp
                )
                return@Column
            }

            // Timeline track
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(scrollState),
                verticalAlignment = Alignment.Top
            ) {
                // "Now" marker
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(
                        Modifier
                            .size(12.dp)
                            .clip(CircleShape)
                            .background(SuccessGreen)
                    )
                    Spacer(Modifier.height(4.dp))
                    Text("Now", fontSize = 10.sp, color = SuccessGreen)
                }

                passes.forEachIndexed { index, pass ->
                    // Connector line
                    Box(
                        Modifier
                            .width(80.dp)
                            .height(2.dp)
                            .offset(y = 5.dp)
                            .background(
                                Brush.horizontalGradient(
                                    listOf(
                                        if (index == 0) SuccessGreen else SatelliteBlue.copy(alpha = 0.3f),
                                        passColor(pass).copy(alpha = 0.6f)
                                    )
                                )
                            )
                    )

                    // Pass node
                    PassTimelineNode(pass)
                }

                // Trailing line
                Box(
                    Modifier
                        .width(40.dp)
                        .height(2.dp)
                        .offset(y = 5.dp)
                        .background(Color.White.copy(alpha = 0.1f))
                )

                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(
                        Modifier
                            .size(8.dp)
                            .clip(CircleShape)
                            .background(Color.White.copy(alpha = 0.2f))
                    )
                    Spacer(Modifier.height(4.dp))
                    Text("24h", fontSize = 10.sp, color = TextSecondary)
                }
            }
        }
    }
}

@Composable
private fun PassTimelineNode(pass: PassEntity) {
    val color = passColor(pass)

    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.width(90.dp)
    ) {
        // Dot
        Box(
            Modifier
                .size(14.dp)
                .clip(CircleShape)
                .background(color)
                .border(2.dp, color.copy(alpha = 0.3f), CircleShape)
        )

        Spacer(Modifier.height(6.dp))

        // Satellite name
        Text(
            pass.satelliteName.take(12),
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            color = TextPrimary,
            maxLines = 1
        )

        // Time
        Text(
            pass.riseUtc.takeLast(8).take(5), // HH:MM from ISO timestamp
            fontSize = 10.sp,
            color = color
        )

        // Stats
        Text(
            "${pass.maxElevationDeg.toInt()}° ${pass.durationSeconds / 60}m",
            fontSize = 9.sp,
            color = TextSecondary
        )
    }
}

private fun passColor(pass: PassEntity): Color {
    return when {
        pass.qualityScore >= 0.8f -> SuccessGreen
        pass.qualityScore >= 0.5f -> SatelliteBlue
        pass.maxElevationDeg >= 60f -> SuccessGreen
        pass.maxElevationDeg >= 30f -> SatelliteBlue
        else -> WarningAmber
    }
}

private fun formatCountdown(seconds: Long): String {
    if (seconds <= 0) return "Active now"
    val h = seconds / 3600
    val m = (seconds % 3600) / 60
    val s = seconds % 60
    return if (h > 0) "${h}h ${m}m" else "${m}m ${s}s"
}
