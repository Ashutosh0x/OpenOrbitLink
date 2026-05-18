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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.freesat.ui.theme.*

@Composable
fun GroundStationScreen() {
    val anim = rememberInfiniteTransition(label = "gs")
    val signalPulse by anim.animateFloat(0.4f, 1f,
        infiniteRepeatable(tween(1500), RepeatMode.Reverse), label = "sig")
    val packetCount by anim.animateFloat(0f, 100f,
        infiniteRepeatable(tween(10000, easing = LinearEasing)), label = "pkt")

    var azimuth by remember { mutableStateOf(142f) }
    var elevation by remember { mutableStateOf(52f) }
    var frequency by remember { mutableStateOf(145.800f) }
    var isTracking by remember { mutableStateOf(true) }
    var host by remember { mutableStateOf("192.168.1.50") }
    var port by remember { mutableStateOf("50051") }
    var isConnected by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp).verticalScroll(rememberScrollState())) {

        ScreenHeader("Ground Station", "FS-GS-001 \u2022 Remote Control", Icons.Filled.CellTower)

        // Status
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(12.dp).clip(CircleShape)
                    .background((if (isConnected) SuccessGreen else WarningAmber).copy(alpha = signalPulse)))
                Spacer(Modifier.width(10.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(if (isConnected) "Station Online" else "Station Ready",
                        color = if (isConnected) SuccessGreen else WarningAmber,
                        fontWeight = FontWeight.Bold)
                    Text("$host:$port | RPi 4B | RTL-SDR V4", fontSize = 11.sp, color = TextSecondary)
                }
            }
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                TextField(value = host, onValueChange = { host = it },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    label = { Text("Host") },
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = SurfaceDark,
                        unfocusedContainerColor = SurfaceDark,
                        focusedIndicatorColor = SatelliteBlue,
                        unfocusedIndicatorColor = TextSecondary.copy(alpha = 0.4f)))
                TextField(value = port, onValueChange = { port = it.filter { ch -> ch.isDigit() }.take(5) },
                    modifier = Modifier.width(96.dp),
                    singleLine = true,
                    label = { Text("Port") },
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = SurfaceDark,
                        unfocusedContainerColor = SurfaceDark,
                        focusedIndicatorColor = SatelliteBlue,
                        unfocusedIndicatorColor = TextSecondary.copy(alpha = 0.4f)))
                Button(onClick = { isConnected = !isConnected },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isConnected) AlertRed else SatelliteBlue)) {
                    Text(if (isConnected) "Drop" else "Link")
                }
            }
        }

        Spacer(Modifier.height(12.dp))

        // Telemetry cards
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricCard("Signal", "-98 dBm", SuccessGreen, Modifier.weight(1f))
            MetricCard("Temp", "42\u00B0C", WarningAmber, Modifier.weight(1f))
            MetricCard("Packets", "${packetCount.toInt()}", SatelliteBlue, Modifier.weight(1f))
            MetricCard("Errors", "2", AlertRed, Modifier.weight(1f))
        }

        Spacer(Modifier.height(16.dp))

        // Antenna Control
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Antenna Control", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
                Spacer(Modifier.weight(1f))
                Surface(shape = RoundedCornerShape(8.dp),
                    color = if (isTracking) SuccessGreen.copy(alpha = 0.15f) else SurfaceCard,
                    onClick = { isTracking = !isTracking }) {
                    Text(if (isTracking) " AUTO TRACK " else " MANUAL ",
                        fontSize = 11.sp, fontWeight = FontWeight.Bold,
                        color = if (isTracking) SuccessGreen else TextSecondary,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp))
                }
            }
            Spacer(Modifier.height(16.dp))

            // Azimuth slider
            Text("Azimuth: ${azimuth.toInt()}\u00B0", fontSize = 13.sp, color = TextPrimary,
                fontWeight = FontWeight.SemiBold)
            Slider(value = azimuth, onValueChange = { azimuth = it }, valueRange = 0f..360f,
                colors = SliderDefaults.colors(thumbColor = SatelliteBlue,
                    activeTrackColor = SatelliteBlue, inactiveTrackColor = SatelliteBlue.copy(alpha = 0.15f)),
                enabled = !isTracking)

            // Elevation slider
            Text("Elevation: ${elevation.toInt()}\u00B0", fontSize = 13.sp, color = TextPrimary,
                fontWeight = FontWeight.SemiBold)
            Slider(value = elevation, onValueChange = { elevation = it }, valueRange = 0f..90f,
                colors = SliderDefaults.colors(thumbColor = NebulaPurple,
                    activeTrackColor = NebulaPurple, inactiveTrackColor = NebulaPurple.copy(alpha = 0.15f)),
                enabled = !isTracking)
        }

        Spacer(Modifier.height(16.dp))

        // Frequency Tuning
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Frequency Tuning", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))

            // Preset buttons
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf(
                    "ISS APRS" to 145.800f,
                    "NOAA-19" to 137.100f,
                    "CW Beacon" to 144.390f,
                ).forEach { (label, freq) ->
                    Surface(shape = RoundedCornerShape(8.dp),
                        color = if (frequency == freq) SatelliteBlue.copy(alpha = 0.2f) else Color.Transparent,
                        border = BorderStroke(1.dp,
                            if (frequency == freq) SatelliteBlue else Color.White.copy(alpha = 0.1f)),
                        onClick = { frequency = freq }) {
                        Text(label, fontSize = 11.sp, color = if (frequency == freq) SatelliteBlue else TextSecondary,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp))
                    }
                }
            }

            Spacer(Modifier.height(12.dp))
            Text("${String.format("%.3f", frequency)} MHz", fontSize = 28.sp,
                fontWeight = FontWeight.Black, color = TextPrimary)
            Slider(value = frequency, onValueChange = { frequency = it }, valueRange = 130f..170f,
                colors = SliderDefaults.colors(thumbColor = AccentGradientStart,
                    activeTrackColor = AccentGradientStart))
        }

        Spacer(Modifier.height(16.dp))

        // Recent decoded packets
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Decoded Packets", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            listOf(
                Triple("14:23:01", "ISS APRS", "RS0ISS>CQ,ARISS: Hello from ISS!"),
                Triple("14:22:45", "BEACON", "FS-GS-001 alive | lat=28.61 lon=77.21"),
                Triple("14:21:30", "NOAA-19", "APT frame 2847 | 137.100 MHz | SNR 22dB"),
            ).forEach { (time, type, content) ->
                Surface(modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp),
                    shape = RoundedCornerShape(10.dp), color = SurfaceCard.copy(alpha = 0.5f)) {
                    Row(modifier = Modifier.padding(10.dp), verticalAlignment = Alignment.Top) {
                        Text(time, fontSize = 10.sp, color = TextSecondary,
                            modifier = Modifier.width(56.dp))
                        Surface(shape = RoundedCornerShape(4.dp),
                            color = SatelliteBlue.copy(alpha = 0.15f)) {
                            Text(" $type ", fontSize = 9.sp, color = SatelliteBlue,
                                fontWeight = FontWeight.Bold)
                        }
                        Spacer(Modifier.width(8.dp))
                        Text(content, fontSize = 11.sp, color = TextPrimary,
                            modifier = Modifier.weight(1f))
                    }
                }
            }
        }
    }
}
