package org.freesat.ui.screens

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.freesat.ui.theme.*

// ── Shared Components ──────────────────────────────────────────

@Composable
fun GlassCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(20.dp),
        color = SurfaceCard.copy(alpha = 0.6f),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.08f)),
        tonalElevation = 0.dp,
    ) { Column(modifier = Modifier.padding(20.dp), content = content) }
}

@Composable
fun ScreenHeader(title: String, subtitle: String, icon: ImageVector) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(bottom = 20.dp)) {
        Box(
            modifier = Modifier.size(48.dp).background(
                Brush.linearGradient(listOf(AccentGradientStart, AccentGradientEnd)), CircleShape
            ), contentAlignment = Alignment.Center
        ) { Icon(icon, null, tint = Color.White, modifier = Modifier.size(24.dp)) }
        Spacer(Modifier.width(14.dp))
        Column {
            Text(title, style = MaterialTheme.typography.headlineMedium, color = TextPrimary)
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = TextSecondary)
        }
    }
}

@Composable
fun StatChip(label: String, value: String, color: Color = SatelliteBlue) {
    Surface(shape = RoundedCornerShape(12.dp), color = color.copy(alpha = 0.1f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.3f))) {
        Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = color)
            Text(label, style = MaterialTheme.typography.labelSmall, color = TextSecondary)
        }
    }
}

@Composable
fun InfoRow(icon: ImageVector, label: String, value: String, valueColor: Color = TextPrimary) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, null, modifier = Modifier.size(18.dp), tint = SatelliteBlue)
        Spacer(Modifier.width(12.dp))
        Text(label, style = MaterialTheme.typography.bodyMedium, color = TextSecondary,
            modifier = Modifier.weight(1f))
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold,
            color = valueColor)
    }
}

// ── Data Classes ───────────────────────────────────────────────

data class MessageItem(
    val text: String, val isMine: Boolean, val timestamp: Long,
    val status: String = "queued", val isVoice: Boolean = false
) {
    val statusText get() = when (status) {
        "queued" -> "Queued for satellite pass"
        "sent" -> "Sent via satellite"
        "delivered" -> "Delivered"
        else -> status
    }
    val statusIcon get() = when (status) {
        "queued" -> Icons.Outlined.Schedule
        "sent" -> Icons.Outlined.SatelliteAlt
        "delivered" -> Icons.Filled.CheckCircle
        else -> Icons.Outlined.Info
    }
    val statusColor get() = when (status) {
        "queued" -> WarningAmber; "sent" -> SatelliteBlue
        "delivered" -> SuccessGreen; else -> TextSecondary
    }
}

// ── Messaging Screen ───────────────────────────────────────────

@Composable
fun MessagingScreen() {
    var messageText by remember { mutableStateOf("") }
    var messages by remember { mutableStateOf(listOf(
        MessageItem("Welcome to OpenOrbitLink! Messages encrypted with Signal SPQR + ML-KEM-768.", false, System.currentTimeMillis(), "delivered"),
        MessageItem("Next ISS pass: 14:23 UTC | 52\u00B0 elevation | 8m30s window", false, System.currentTimeMillis(), "delivered"),
    )) }
    var isRecording by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy))).padding(16.dp)) {

        ScreenHeader("Messages", "E2E Encrypted \u2022 Store-and-Forward", Icons.Filled.Chat)

        // Stats row
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(bottom = 16.dp)) {
            StatChip("Queued", "0", WarningAmber)
            StatChip("Sent", "0", SatelliteBlue)
            StatChip("Delivered", "2", SuccessGreen)
        }

        // Messages
        LazyColumn(modifier = Modifier.weight(1f), reverseLayout = true,
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(messages) { msg -> MessageBubble(msg) }
        }

        Spacer(Modifier.height(12.dp))

        // Input bar
        Surface(shape = RoundedCornerShape(28.dp), color = SurfaceCard.copy(alpha = 0.8f),
            border = BorderStroke(1.dp, Color.White.copy(alpha = 0.06f))) {
            Row(modifier = Modifier.padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { isRecording = !isRecording }) {
                    Icon(if (isRecording) Icons.Filled.Stop else Icons.Filled.Mic, "Voice",
                        tint = if (isRecording) SOSRed else SatelliteBlue)
                }
                TextField(value = messageText, onValueChange = { messageText = it },
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("Message via satellite...", color = TextSecondary) },
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent,
                        focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent,
                        cursorColor = SatelliteBlue), maxLines = 3)
                FilledIconButton(onClick = {
                    if (messageText.isNotBlank()) {
                        messages = listOf(MessageItem(messageText, true, System.currentTimeMillis())) + messages
                        messageText = ""
                    }
                }, colors = IconButtonDefaults.filledIconButtonColors(
                    containerColor = SatelliteBlue, contentColor = SpaceBlack)
                ) { Icon(Icons.Filled.Send, "Send") }
            }
        }
    }
}

@Composable
fun MessageBubble(msg: MessageItem) {
    Column(modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = if (msg.isMine) Alignment.End else Alignment.Start) {
        Surface(
            shape = RoundedCornerShape(
                topStart = 18.dp, topEnd = 18.dp,
                bottomStart = if (msg.isMine) 18.dp else 4.dp,
                bottomEnd = if (msg.isMine) 4.dp else 18.dp),
            color = if (msg.isMine) SatelliteBlue.copy(alpha = 0.15f) else SurfaceCard,
            border = BorderStroke(1.dp,
                if (msg.isMine) SatelliteBlue.copy(alpha = 0.3f) else Color.White.copy(alpha = 0.05f)),
            modifier = Modifier.widthIn(max = 300.dp)
        ) {
            Column(modifier = Modifier.padding(14.dp)) {
                Text(msg.text, style = MaterialTheme.typography.bodyMedium, color = TextPrimary)
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(msg.statusIcon, null, modifier = Modifier.size(12.dp), tint = msg.statusColor)
                    Spacer(Modifier.width(4.dp))
                    Text(msg.statusText, style = MaterialTheme.typography.labelSmall, color = msg.statusColor)
                }
            }
        }
    }
}

// ── Satellite Tracker ──────────────────────────────────────────

@Composable
fun SatelliteTrackerScreen() {
    val pulseAnim = rememberInfiniteTransition(label = "pulse")
    val pulseAlpha by pulseAnim.animateFloat(0.3f, 1f, infiniteRepeatable(
        tween(1500), RepeatMode.Reverse), label = "alpha")

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp).verticalScroll(rememberScrollState())) {

        ScreenHeader("Satellite Tracker", "SGP4 Orbital Prediction \u2022 Live TLE", Icons.Filled.SatelliteAlt)

        // Live status
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(10.dp).clip(CircleShape)
                    .background(SuccessGreen.copy(alpha = pulseAlpha)))
                Spacer(Modifier.width(10.dp))
                Text("Tracking 3 satellites", color = SuccessGreen,
                    style = MaterialTheme.typography.labelLarge)
                Spacer(Modifier.weight(1f))
                Text("TLE: 2h ago", color = TextSecondary, style = MaterialTheme.typography.labelSmall)
            }
        }

        Spacer(Modifier.height(16.dp))

        // Pass cards
        PassCard("ISS (ZARYA)", "NORAD 25544", "14:23 UTC", "52\u00B0", "8m 30s",
            "+16.3 dB", "\u00B13.8 kHz", 0.72f, SatelliteBlue)
        Spacer(Modifier.height(12.dp))
        PassCard("NOAA-19", "NORAD 33591", "15:01 UTC", "38\u00B0", "11m 20s",
            "+22.1 dB", "\u00B12.1 kHz", 0.58f, NebulaPurple)
        Spacer(Modifier.height(12.dp))
        PassCard("FUNcube-1", "NORAD 39444", "16:45 UTC", "71\u00B0", "6m 10s",
            "+27.4 dB", "\u00B14.5 kHz", 0.85f, AccentGradientStart)

        Spacer(Modifier.height(16.dp))

        // Performance stats
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Engine Performance", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            InfoRow(Icons.Filled.Speed, "SGP4 prediction", "254 ms / 24hr")
            InfoRow(Icons.Filled.Satellite, "Doppler model", "<5 ms inference")
            InfoRow(Icons.Filled.Memory, "TFLite quantized", "INT8 (420 KB)")
            InfoRow(Icons.Filled.Storage, "TLE data source", "CelesTrak API")
        }
    }
}

@Composable
fun PassCard(name: String, norad: String, time: String, elev: String, dur: String,
             margin: String, doppler: String, quality: Float, accentColor: Color) {
    GlassCard(modifier = Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(name, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = TextPrimary)
                Text(norad, style = MaterialTheme.typography.labelSmall, color = TextSecondary)
            }
            Surface(shape = RoundedCornerShape(8.dp),
                color = accentColor.copy(alpha = 0.15f)) {
                Text("  $time  ", color = accentColor, fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(vertical = 4.dp))
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            Column { Text("Elevation", style = MaterialTheme.typography.labelSmall, color = TextSecondary)
                Text(elev, fontWeight = FontWeight.Bold, color = TextPrimary) }
            Column { Text("Duration", style = MaterialTheme.typography.labelSmall, color = TextSecondary)
                Text(dur, fontWeight = FontWeight.Bold, color = TextPrimary) }
            Column { Text("Margin", style = MaterialTheme.typography.labelSmall, color = TextSecondary)
                Text(margin, fontWeight = FontWeight.Bold, color = SuccessGreen) }
            Column { Text("Doppler", style = MaterialTheme.typography.labelSmall, color = TextSecondary)
                Text(doppler, fontWeight = FontWeight.Bold, color = TextPrimary) }
        }
        Spacer(Modifier.height(10.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Quality", style = MaterialTheme.typography.labelSmall, color = TextSecondary)
            Spacer(Modifier.width(8.dp))
            LinearProgressIndicator(progress = { quality }, modifier = Modifier.weight(1f).height(6.dp)
                .clip(RoundedCornerShape(3.dp)),
                color = accentColor, trackColor = accentColor.copy(alpha = 0.15f))
            Spacer(Modifier.width(8.dp))
            Text("${(quality * 100).toInt()}%", fontWeight = FontWeight.Bold, fontSize = 13.sp,
                color = accentColor)
        }
    }
}

// ── Mesh Network ───────────────────────────────────────────────

@Composable
fun MeshNetworkScreen() {
    val scanAnim = rememberInfiniteTransition(label = "scan")
    val scanAlpha by scanAnim.animateFloat(0.2f, 0.8f, infiniteRepeatable(
        tween(2000), RepeatMode.Reverse), label = "scan")

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp).verticalScroll(rememberScrollState())) {

        ScreenHeader("Mesh Network", "LoRa SX1276 + Bluetooth Low Energy", Icons.Filled.Hub)

        // Mesh stats
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(bottom = 16.dp)) {
            StatChip("Nodes", "0", SatelliteBlue)
            StatChip("Hops", "0", NebulaPurple)
            StatChip("Range", "5km", SuccessGreen)
        }

        // Scanning status
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(10.dp).clip(CircleShape)
                    .background(WarningAmber.copy(alpha = scanAlpha)))
                Spacer(Modifier.width(10.dp))
                Text("Scanning for nearby nodes...", color = WarningAmber,
                    style = MaterialTheme.typography.labelLarge)
            }
            Spacer(Modifier.height(16.dp))
            InfoRow(Icons.Filled.Bluetooth, "Bluetooth LE", "Scanning...", WarningAmber)
            InfoRow(Icons.Filled.Router, "LoRa SX1276", "Not connected", AlertRed)
            InfoRow(Icons.Filled.Wifi, "Mesh relay", "Waiting for peers", TextSecondary)
        }

        Spacer(Modifier.height(16.dp))

        // LoRa specs
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("LoRa Specifications", style = MaterialTheme.typography.titleMedium,
                color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            InfoRow(Icons.Filled.SignalCellularAlt, "Frequency", "868/915 MHz")
            InfoRow(Icons.Filled.Speed, "SF12 bitrate", "293 bps")
            InfoRow(Icons.Filled.SignalCellular4Bar, "Sensitivity", "-137 dBm")
            InfoRow(Icons.Filled.Explore, "Urban range", "2-5 km")
            InfoRow(Icons.Filled.Landscape, "Rural range", "10-15 km")
            InfoRow(Icons.Filled.Bolt, "TX power", "14 dBm (25 mW)")
        }

        Spacer(Modifier.height(16.dp))

        // Routing
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Routing Strategy", style = MaterialTheme.typography.titleMedium,
                color = NebulaPurple)
            Spacer(Modifier.height(12.dp))
            Text("1. Direct satellite upload (if visible + TX capable)", color = TextPrimary,
                style = MaterialTheme.typography.bodySmall)
            Text("2. Relay to neighbor with satellite access", color = TextPrimary,
                style = MaterialTheme.typography.bodySmall)
            Text("3. Multi-hop toward ground station", color = TextPrimary,
                style = MaterialTheme.typography.bodySmall)
            Text("4. Store locally, retry next pass", color = TextPrimary,
                style = MaterialTheme.typography.bodySmall)
        }
    }
}

// ── Emergency SOS ──────────────────────────────────────────────

@Composable
fun EmergencySOSScreen() {
    val haptic = LocalHapticFeedback.current
    var sosSent by remember { mutableStateOf(false) }
    var countdown by remember { mutableStateOf(3) }
    val pulseAnim = rememberInfiniteTransition(label = "sos")
    val scale by pulseAnim.animateFloat(1f, 1.08f, infiniteRepeatable(
        tween(800), RepeatMode.Reverse), label = "scale")

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(
            if (sosSent) listOf(Color(0xFF1A0000), Color(0xFF330000))
            else listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.SpaceBetween) {

        ScreenHeader("Emergency SOS", "All-channel distress signal", Icons.Filled.Warning)

        // SOS button
        Column(horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.weight(1f), verticalArrangement = Arrangement.Center) {
            Box(contentAlignment = Alignment.Center) {
                // Outer glow
                if (!sosSent) {
                    Box(Modifier.size((200 * scale).dp).clip(CircleShape)
                        .background(SOSRed.copy(alpha = 0.08f)))
                    Box(Modifier.size((170 * scale).dp).clip(CircleShape)
                        .background(SOSRed.copy(alpha = 0.12f)))
                }
                Button(onClick = {
                    haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                    sosSent = true
                },
                    modifier = Modifier.size(140.dp),
                    shape = CircleShape,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (sosSent) SuccessGreen else SOSRed),
                    elevation = ButtonDefaults.buttonElevation(8.dp)) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(if (sosSent) Icons.Filled.CheckCircle else Icons.Filled.Warning,
                            null, modifier = Modifier.size(36.dp))
                        Spacer(Modifier.height(4.dp))
                        Text(if (sosSent) "SENT" else "SOS",
                            fontWeight = FontWeight.Black, fontSize = 22.sp)
                    }
                }
            }

            Spacer(Modifier.height(24.dp))
            Text(if (sosSent) "Emergency signal transmitted on all channels"
                else "Tap to send GPS + distress signal",
                style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Center,
                color = if (sosSent) SuccessGreen else TextSecondary)
        }

        // SOS info
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Transmission Details", style = MaterialTheme.typography.titleMedium,
                color = if (sosSent) SuccessGreen else SOSRed)
            Spacer(Modifier.height(8.dp))
            InfoRow(Icons.Filled.MyLocation, "GPS coordinates", "Auto-attached")
            InfoRow(Icons.Filled.SatelliteAlt, "Satellite channel", "ISS APRS 144.39 MHz")
            InfoRow(Icons.Filled.Router, "LoRa mesh", "All neighbors")
            InfoRow(Icons.Filled.Repeat, "Retry policy", "Every pass until ACK")
            InfoRow(Icons.Filled.Lock, "Priority", "CRITICAL (0)", SOSRed)
        }
    }
}

// ── Settings ─────────────────────────────────────────────────────────

@Composable
fun SettingsScreen() {
    var selectedPath by remember { mutableStateOf("ntn") }
    var biometricEnabled by remember { mutableStateOf(false) }
    var passAlerts by remember { mutableStateOf(true) }
    var offlineMaps by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp).verticalScroll(rememberScrollState())) {

        ScreenHeader("Settings", "Hardware \u2022 Voice \u2022 Security \u2022 Network", Icons.Filled.Settings)

        // Hardware path
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Hardware Path", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            listOf(
                Triple("ntn", "A \u2014 Direct NTN Modem", "Pixel 9/10, Galaxy S25+ | Cost: \$0"),
                Triple("sdr", "B \u2014 USB SDR Receiver", "RTL-SDR V4 + antenna | Cost: \$80"),
                Triple("lora", "C \u2014 LoRa Mesh Relay", "SX1276 via Bluetooth | Cost: \$10"),
            ).forEach { (key, title, desc) ->
                Surface(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    shape = RoundedCornerShape(12.dp),
                    color = if (selectedPath == key) SatelliteBlue.copy(alpha = 0.1f) else Color.Transparent,
                    border = BorderStroke(1.dp,
                        if (selectedPath == key) SatelliteBlue.copy(alpha = 0.4f) else Color.Transparent),
                    onClick = { selectedPath = key }
                ) {
                    Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(selected = selectedPath == key, onClick = { selectedPath = key },
                            colors = RadioButtonDefaults.colors(selectedColor = SatelliteBlue))
                        Column(modifier = Modifier.padding(start = 8.dp)) {
                            Text(title, fontWeight = FontWeight.SemiBold, color = TextPrimary)
                            Text(desc, style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // Notifications & Privacy
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Notifications & Privacy", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Notifications, null, tint = SatelliteBlue, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(12.dp))
                Text("Satellite pass alerts", color = TextSecondary, modifier = Modifier.weight(1f))
                Switch(checked = passAlerts, onCheckedChange = { passAlerts = it },
                    colors = SwitchDefaults.colors(checkedTrackColor = SatelliteBlue))
            }
            Spacer(Modifier.height(8.dp))
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Fingerprint, null, tint = NebulaPurple, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(12.dp))
                Text("Biometric lock", color = TextSecondary, modifier = Modifier.weight(1f))
                Switch(checked = biometricEnabled, onCheckedChange = { biometricEnabled = it },
                    colors = SwitchDefaults.colors(checkedTrackColor = NebulaPurple))
            }
            Spacer(Modifier.height(8.dp))
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Map, null, tint = SuccessGreen, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(12.dp))
                Text("Offline map tiles", color = TextSecondary, modifier = Modifier.weight(1f))
                Switch(checked = offlineMaps, onCheckedChange = { offlineMaps = it },
                    colors = SwitchDefaults.colors(checkedTrackColor = SuccessGreen))
            }
        }

        Spacer(Modifier.height(16.dp))

        // Voice codec
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Voice Codec", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            InfoRow(Icons.Filled.Mic, "Codec", "Codec2 700C")
            InfoRow(Icons.Filled.Speed, "Bitrate", "700 bps")
            InfoRow(Icons.Filled.GraphicEq, "Sample rate", "8,000 Hz")
            InfoRow(Icons.Filled.Timer, "Frame size", "40 ms / 28 bits")
            InfoRow(Icons.Filled.AutoFixHigh, "Neural PLC", "WaveRNN gap-fill")
            InfoRow(Icons.Filled.Memory, "NDK library", "libcodec2.so (ARM64)")
        }

        Spacer(Modifier.height(16.dp))

        // Security
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Security", style = MaterialTheme.typography.titleMedium, color = NebulaPurple)
            Spacer(Modifier.height(12.dp))
            InfoRow(Icons.Filled.Lock, "Encryption", "AES-256-GCM")
            InfoRow(Icons.Filled.Key, "Key exchange", "Signal SPQR Triple Ratchet")
            InfoRow(Icons.Filled.Shield, "Post-quantum", "ML-KEM-768 (NIST FIPS 203)")
            InfoRow(Icons.Filled.VerifiedUser, "Bundle security", "BPSec RFC 9172")
            InfoRow(Icons.Filled.Fingerprint, "Key storage", "Android Keystore")
        }

        Spacer(Modifier.height(16.dp))

        // About
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("About OpenOrbitLink", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            InfoRow(Icons.Filled.Info, "Version", "1.0.0-alpha")
            InfoRow(Icons.Filled.Code, "License", "GPLv3")
            InfoRow(Icons.Filled.Public, "Source", "github.com/OpenOrbitLink-project")
            InfoRow(Icons.Filled.Science, "Protocol", "AX.25 + CCSDS + DTN hybrid")
        }
    }
}
