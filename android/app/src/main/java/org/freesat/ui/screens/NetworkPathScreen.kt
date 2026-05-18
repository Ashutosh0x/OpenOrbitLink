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
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.freesat.ui.theme.*

data class NetworkHop(
    val name: String, val icon: ImageVector, val status: String,
    val latencyMs: Int, val color: Color, val detail: String
)

@Composable
fun NetworkPathScreen() {
    val anim = rememberInfiniteTransition(label = "flow")
    val dotOffset by anim.animateFloat(0f, 1f,
        infiniteRepeatable(tween(2000, easing = LinearEasing)), label = "dot")
    val pulseAlpha by anim.animateFloat(0.3f, 1f,
        infiniteRepeatable(tween(1200), RepeatMode.Reverse), label = "pulse")

    val hops = listOf(
        NetworkHop("Your Phone", Icons.Filled.Smartphone, "Connected", 0, SatelliteBlue, "OpenOrbitLink v1.0 | Path C: LoRa"),
        NetworkHop("LoRa Relay", Icons.Filled.Router, "Active", 145, SuccessGreen, "SX1276 | SF12 | 868 MHz | -120 dBm"),
        NetworkHop("Ground Station", Icons.Filled.CellTower, "Online", 52, SatelliteBlue, "FS-GS-001 | RPi 4 | RTL-SDR V4"),
        NetworkHop("ISS APRS", Icons.Filled.SatelliteAlt, "In Range", 890, NebulaPurple, "144.390 MHz | NORAD 25544 | 52\u00B0 el"),
        NetworkHop("Destination", Icons.Filled.Person, "Queued", 0, WarningAmber, "Store-and-forward | Next pass ~45min"),
    )

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp).verticalScroll(rememberScrollState())) {

        ScreenHeader("Network Path", "Live data flow visualization", Icons.Filled.AccountTree)

        // Total latency
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Timer, null, tint = SatelliteBlue)
                Spacer(Modifier.width(10.dp))
                Column {
                    Text("End-to-End Latency", style = MaterialTheme.typography.labelLarge, color = TextPrimary)
                    Text("Store-and-forward mode", fontSize = 11.sp, color = TextSecondary)
                }
                Spacer(Modifier.weight(1f))
                Column(horizontalAlignment = Alignment.End) {
                    Text("~45 min", fontSize = 22.sp, fontWeight = FontWeight.Black, color = WarningAmber)
                    Text("1 orbit period", fontSize = 11.sp, color = TextSecondary)
                }
            }
        }

        Spacer(Modifier.height(20.dp))

        // Path visualization
        hops.forEachIndexed { index, hop ->
            // Hop node
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
                // Left: icon column with connecting line
                Column(horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.width(56.dp)) {
                    Box(modifier = Modifier.size(48.dp)
                        .background(hop.color.copy(alpha = 0.15f), CircleShape)
                        .border(2.dp, hop.color.copy(alpha = if (hop.status == "In Range") pulseAlpha else 0.6f), CircleShape),
                        contentAlignment = Alignment.Center) {
                        Icon(hop.icon, null, tint = hop.color, modifier = Modifier.size(24.dp))
                    }
                    // Connecting line + animated dot
                    if (index < hops.size - 1) {
                        Box(modifier = Modifier.width(3.dp).height(60.dp)
                            .drawBehind {
                                // Dashed line
                                drawLine(hop.color.copy(alpha = 0.3f),
                                    Offset(size.width / 2, 0f),
                                    Offset(size.width / 2, size.height),
                                    strokeWidth = 2f,
                                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 8f)))
                                // Animated dot
                                val y = dotOffset * size.height
                                drawCircle(hop.color, radius = 5f, center = Offset(size.width / 2, y))
                            })
                    }
                }

                Spacer(Modifier.width(12.dp))

                // Right: info card
                Surface(modifier = Modifier.weight(1f).padding(bottom = if (index < hops.size - 1) 12.dp else 0.dp),
                    shape = RoundedCornerShape(14.dp),
                    color = SurfaceCard.copy(alpha = 0.6f),
                    border = BorderStroke(1.dp, hop.color.copy(alpha = 0.2f))) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(hop.name, fontWeight = FontWeight.Bold, color = TextPrimary)
                            Spacer(Modifier.weight(1f))
                            Box(modifier = Modifier.background(hop.color.copy(alpha = 0.15f),
                                RoundedCornerShape(6.dp)).padding(horizontal = 8.dp, vertical = 2.dp)) {
                                Text(hop.status, fontSize = 10.sp, color = hop.color, fontWeight = FontWeight.Bold)
                            }
                        }
                        Spacer(Modifier.height(4.dp))
                        Text(hop.detail, fontSize = 11.sp, color = TextSecondary)
                        if (hop.latencyMs > 0) {
                            Spacer(Modifier.height(4.dp))
                            Text("Latency: ${hop.latencyMs}ms", fontSize = 11.sp,
                                color = if (hop.latencyMs < 200) SuccessGreen else WarningAmber)
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(20.dp))

        // Speed test
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Link Speed Test", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                MetricCard("Upload", "700 bps", SatelliteBlue, Modifier.weight(1f))
                MetricCard("Download", "1.2 kbps", SuccessGreen, Modifier.weight(1f))
                MetricCard("Jitter", "12 ms", WarningAmber, Modifier.weight(1f))
            }
            Spacer(Modifier.height(12.dp))
            Button(onClick = {}, modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = SatelliteBlue.copy(alpha = 0.15f)),
                shape = RoundedCornerShape(12.dp)) {
                Icon(Icons.Filled.PlayArrow, null, tint = SatelliteBlue)
                Spacer(Modifier.width(8.dp))
                Text("Run Speed Test", color = SatelliteBlue)
            }
        }
    }
}
