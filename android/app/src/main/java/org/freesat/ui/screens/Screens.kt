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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.freesat.discovery.DiscoveryLinkPath
import org.freesat.discovery.NearbyPassCandidate
import org.freesat.discovery.NearbyPassScorer
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

enum class DeliveryState { QUEUED, WAITING_FOR_PASS, SENDING, SENT, DELIVERED, FAILED }

data class ConversationThread(
    val contact: String,
    val preview: String,
    val status: DeliveryState,
    val queuedCount: Int,
    val unreadCount: Int,
    val nextPass: String,
    val reliability: String,
)

data class MessageItem(
    val text: String,
    val isMine: Boolean,
    val timestamp: Long,
    val status: DeliveryState = DeliveryState.QUEUED,
    val isVoice: Boolean = false,
    val replyTo: String? = null,
    val retryable: Boolean = false,
) {
    val statusText get() = when (status) {
        DeliveryState.QUEUED -> "Queued"
        DeliveryState.WAITING_FOR_PASS -> "Waiting for pass"
        DeliveryState.SENDING -> "Sending burst"
        DeliveryState.SENT -> "Sent via satellite"
        DeliveryState.DELIVERED -> "Delivered"
        DeliveryState.FAILED -> "Failed"
    }
    val statusIcon get() = when (status) {
        DeliveryState.QUEUED -> Icons.Outlined.Schedule
        DeliveryState.WAITING_FOR_PASS -> Icons.Outlined.SatelliteAlt
        DeliveryState.SENDING -> Icons.Filled.Sync
        DeliveryState.SENT -> Icons.Outlined.Done
        DeliveryState.DELIVERED -> Icons.Filled.CheckCircle
        DeliveryState.FAILED -> Icons.Outlined.ErrorOutline
    }
    val statusColor get() = when (status) {
        DeliveryState.QUEUED -> WarningAmber
        DeliveryState.WAITING_FOR_PASS -> NebulaPurple
        DeliveryState.SENDING -> SatelliteBlue
        DeliveryState.SENT -> SatelliteBlue
        DeliveryState.DELIVERED -> SuccessGreen
        DeliveryState.FAILED -> AlertRed
    }
}

data class PttLogItem(val speaker: String, val event: String, val quality: String, val time: String)

// ── Messaging Screen ───────────────────────────────────────────

@Composable
fun MessagingScreen() {
    var activeTab by remember { mutableStateOf("inbox") }
    var messageText by remember { mutableStateOf("") }
    var messages by remember { mutableStateOf(listOf(
        MessageItem("Next ISS pass: 14:23 UTC | 52\u00B0 elevation | 8m30s window", false, System.currentTimeMillis(), DeliveryState.DELIVERED),
        MessageItem("Copy. I will hold transmission until the pass opens.", true, System.currentTimeMillis(), DeliveryState.SENT, replyTo = "Can you confirm relay window?"),
        MessageItem("Can you confirm relay window?", false, System.currentTimeMillis(), DeliveryState.DELIVERED),
        MessageItem("Voice memo queued as Codec2 700C frames.", true, System.currentTimeMillis(), DeliveryState.WAITING_FOR_PASS, isVoice = true),
        MessageItem("Retry route via LoRa neighbor if ISS window closes.", true, System.currentTimeMillis(), DeliveryState.FAILED, retryable = true),
    )) }
    var isRecording by remember { mutableStateOf(false) }
    val threads = remember {
        listOf(
            ConversationThread("Field Team Alpha", "Retry route via LoRa neighbor if ISS window closes.", DeliveryState.FAILED, 2, 1, "Visible now", "82%"),
            ConversationThread("Medical Relay", "Vitals bundle queued with priority HIGH.", DeliveryState.WAITING_FOR_PASS, 3, 0, "Next pass in 14m", "74%"),
            ConversationThread("Ground Station FS-GS-001", "Antenna locked. Packet feed clean.", DeliveryState.DELIVERED, 0, 2, "Best pass in 41m", "91%"),
        )
    }

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy))).padding(16.dp)) {

        ScreenHeader("Messages", "Inbox, chat, queue, and pass-aware delivery", Icons.Filled.Chat)

        // Stats row
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(bottom = 16.dp)) {
            StatChip("Queued", "5", WarningAmber)
            StatChip("Waiting", "3", NebulaPurple)
            StatChip("Delivered", "8", SuccessGreen)
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(bottom = 12.dp)) {
            FilterChip(
                selected = activeTab == "inbox",
                onClick = { activeTab = "inbox" },
                label = { Text("Inbox") },
                leadingIcon = { Icon(Icons.Filled.Inbox, null, modifier = Modifier.size(16.dp)) },
                colors = FilterChipDefaults.filterChipColors(selectedContainerColor = SatelliteBlue.copy(alpha = 0.18f))
            )
            FilterChip(
                selected = activeTab == "chat",
                onClick = { activeTab = "chat" },
                label = { Text("Chat") },
                leadingIcon = { Icon(Icons.Filled.Forum, null, modifier = Modifier.size(16.dp)) },
                colors = FilterChipDefaults.filterChipColors(selectedContainerColor = SatelliteBlue.copy(alpha = 0.18f))
            )
        }

        if (activeTab == "inbox") {
            LazyColumn(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(threads) { thread ->
                    ConversationThreadCard(thread) { activeTab = "chat" }
                }
            }
            return@Column
        }

        ActiveChatHeader()

        LazyColumn(modifier = Modifier.weight(1f), reverseLayout = true,
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(messages) { msg ->
                MessageBubble(msg, onRetry = {
                    messages = messages.map {
                        if (it == msg) it.copy(status = DeliveryState.WAITING_FOR_PASS, retryable = false) else it
                    }
                })
            }
        }

        Spacer(Modifier.height(12.dp))

        // Input bar
        Surface(shape = RoundedCornerShape(28.dp), color = SurfaceCard.copy(alpha = 0.8f),
            border = BorderStroke(1.dp, Color.White.copy(alpha = 0.06f))) {
            Row(modifier = Modifier.padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { }) {
                    Icon(Icons.Filled.AttachFile, "Attach", tint = TextSecondary)
                }
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
                        messages = listOf(MessageItem(messageText, true, System.currentTimeMillis(), DeliveryState.WAITING_FOR_PASS)) + messages
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
fun ConversationThreadCard(thread: ConversationThread, onOpen: () -> Unit) {
    GlassCard(modifier = Modifier.fillMaxWidth().clickable { onOpen() }) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier.size(44.dp).clip(CircleShape)
                    .background(thread.status.statusColor.copy(alpha = 0.16f)),
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Filled.Person, null, tint = thread.status.statusColor)
            }
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(thread.contact, fontWeight = FontWeight.Bold, color = TextPrimary,
                        maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    if (thread.unreadCount > 0) {
                        Surface(shape = CircleShape, color = AlertRed) {
                            Text("${thread.unreadCount}", color = Color.White, fontSize = 11.sp,
                                modifier = Modifier.padding(horizontal = 7.dp, vertical = 3.dp))
                        }
                    }
                }
                Text(thread.preview, color = TextSecondary, fontSize = 12.sp,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    StatusPill(thread.status.statusText, thread.status.statusColor)
                    StatusPill(thread.nextPass, SatelliteBlue)
                    if (thread.queuedCount > 0) StatusPill("${thread.queuedCount} queued", WarningAmber)
                }
            }
        }
    }
}

private val DeliveryState.statusText: String get() = when (this) {
    DeliveryState.QUEUED -> "Queued"
    DeliveryState.WAITING_FOR_PASS -> "Waiting"
    DeliveryState.SENDING -> "Sending"
    DeliveryState.SENT -> "Sent"
    DeliveryState.DELIVERED -> "Delivered"
    DeliveryState.FAILED -> "Retry"
}

private val DeliveryState.statusColor: Color get() = when (this) {
    DeliveryState.QUEUED -> WarningAmber
    DeliveryState.WAITING_FOR_PASS -> NebulaPurple
    DeliveryState.SENDING -> SatelliteBlue
    DeliveryState.SENT -> SatelliteBlue
    DeliveryState.DELIVERED -> SuccessGreen
    DeliveryState.FAILED -> AlertRed
}

@Composable
fun StatusPill(label: String, color: Color) {
    Surface(shape = RoundedCornerShape(10.dp), color = color.copy(alpha = 0.10f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.25f))) {
        Text(label, color = color, fontSize = 11.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp))
    }
}

@Composable
fun ActiveChatHeader() {
    GlassCard(modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text("Field Team Alpha", fontWeight = FontWeight.Bold, color = TextPrimary)
                Text("Next usable pass: 14m | 52\u00B0 max elevation | 82% reliability",
                    color = TextSecondary, fontSize = 12.sp)
            }
            StatusPill("DTN active", SuccessGreen)
        }
    }
}

@Composable
fun MessageBubble(msg: MessageItem, onRetry: () -> Unit = {}) {
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
                msg.replyTo?.let {
                    Surface(shape = RoundedCornerShape(10.dp), color = Color.White.copy(alpha = 0.05f)) {
                        Text(it, color = TextSecondary, fontSize = 12.sp,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp))
                    }
                    Spacer(Modifier.height(8.dp))
                }
                if (msg.isVoice) {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(bottom = 6.dp)) {
                        Icon(Icons.Filled.GraphicEq, null, modifier = Modifier.size(16.dp), tint = NebulaPurple)
                        Spacer(Modifier.width(6.dp))
                        Text("Codec2 voice burst", color = NebulaPurple, fontSize = 12.sp)
                    }
                }
                Text(msg.text, style = MaterialTheme.typography.bodyMedium, color = TextPrimary)
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(msg.statusIcon, null, modifier = Modifier.size(12.dp), tint = msg.statusColor)
                    Spacer(Modifier.width(4.dp))
                    Text(msg.statusText, style = MaterialTheme.typography.labelSmall, color = msg.statusColor)
                    if (msg.retryable) {
                        Spacer(Modifier.width(8.dp))
                        TextButton(onClick = onRetry, contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)) {
                            Text("Retry", color = AlertRed, fontSize = 12.sp)
                        }
                    }
                }
            }
        }
    }
}

// â”€â”€ Call / PTT Screen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@Composable
fun CallPttScreen() {
    var callState by remember { mutableStateOf("Outgoing") }
    var pttHeld by remember { mutableStateOf(false) }
    var muted by remember { mutableStateOf(false) }
    var speaker by remember { mutableStateOf(true) }
    val quality = if (pttHeld) 0.72f else 0.58f
    val log = remember {
        listOf(
            PttLogItem("You", "Queued 4 Codec2 frames", "Good", "now"),
            PttLogItem("Field Team Alpha", "Received 2.1s burst", "Fair", "1m"),
            PttLogItem("System", "Fallback text prepared", "Ready", "2m"),
        )
    }

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp).verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally) {

        ScreenHeader("Call / PTT", "Half-duplex satellite voice with text fallback", Icons.Filled.Call)

        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text("Field Team Alpha", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                    Text("$callState | next burst slot in 18s", color = TextSecondary, fontSize = 12.sp)
                }
                StatusPill(if (quality > 0.7f) "Usable link" else "Marginal link", if (quality > 0.7f) SuccessGreen else WarningAmber)
            }
            Spacer(Modifier.height(16.dp))
            LinearProgressIndicator(progress = { quality }, modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)),
                color = if (quality > 0.7f) SuccessGreen else WarningAmber,
                trackColor = Color.White.copy(alpha = 0.08f))
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text("Packet loss 6%", color = TextSecondary, fontSize = 12.sp)
                Text("Codec2 700C | 700 bps", color = TextSecondary, fontSize = 12.sp)
            }
        }

        Spacer(Modifier.height(24.dp))

        Button(
            onClick = {
                pttHeld = !pttHeld
                callState = if (pttHeld) "Listening" else "Transmitting"
            },
            modifier = Modifier.size(160.dp),
            shape = CircleShape,
            colors = ButtonDefaults.buttonColors(containerColor = if (pttHeld) SOSRed else SatelliteBlue)
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(if (pttHeld) Icons.Filled.Stop else Icons.Filled.Mic, null, modifier = Modifier.size(42.dp))
                Spacer(Modifier.height(6.dp))
                Text(if (pttHeld) "RELEASE" else "PUSH", fontWeight = FontWeight.Black, fontSize = 20.sp)
            }
        }

        Spacer(Modifier.height(18.dp))

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            AssistChip(onClick = { muted = !muted },
                label = { Text(if (muted) "Muted" else "Mute") },
                leadingIcon = { Icon(if (muted) Icons.Filled.MicOff else Icons.Filled.Mic, null, modifier = Modifier.size(16.dp)) })
            AssistChip(onClick = { speaker = !speaker },
                label = { Text(if (speaker) "Speaker" else "Earpiece") },
                leadingIcon = { Icon(Icons.Filled.VolumeUp, null, modifier = Modifier.size(16.dp)) })
            AssistChip(onClick = { callState = "Text fallback" },
                label = { Text("Text") },
                leadingIcon = { Icon(Icons.Filled.Chat, null, modifier = Modifier.size(16.dp)) })
        }

        Spacer(Modifier.height(18.dp))

        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Burst Log", color = SatelliteBlue, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(10.dp))
            log.forEach {
                Row(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.GraphicEq, null, tint = SatelliteBlue, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(10.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text("${it.speaker}: ${it.event}", color = TextPrimary, fontSize = 13.sp)
                        Text("${it.quality} | ${it.time}", color = TextSecondary, fontSize = 11.sp)
                    }
                }
            }
        }
    }
}

// â”€â”€ Nearby Passes Screen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@Composable
fun NearbyPassesScreen() {
    var discoveryEnabled by remember { mutableStateOf(true) }
    val passes = remember { NearbyPassScorer.demoCandidates() }
    val best = passes.maxBy { NearbyPassScorer.score(it) }

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp).verticalScroll(rememberScrollState())) {

        ScreenHeader("Nearby Passes", "Foreground discovery with pass quality scoring", Icons.Filled.Explore)

        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.NotificationsActive, null, tint = if (discoveryEnabled) SuccessGreen else TextSecondary)
                Spacer(Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(if (discoveryEnabled) "Discovery running" else "Discovery paused", color = TextPrimary, fontWeight = FontWeight.Bold)
                    Text("Best candidate: ${best.name} | ${NearbyPassScorer.score(best)}%", color = TextSecondary, fontSize = 12.sp)
                }
                Switch(checked = discoveryEnabled, onCheckedChange = { discoveryEnabled = it },
                    colors = SwitchDefaults.colors(checkedTrackColor = SuccessGreen))
            }
        }

        Spacer(Modifier.height(16.dp))

        passes.forEach { candidate ->
            NearbyPassCard(candidate)
            Spacer(Modifier.height(12.dp))
        }

        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Scoring Inputs", color = SatelliteBlue, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(10.dp))
            InfoRow(Icons.Filled.Explore, "Elevation", "45% weight")
            InfoRow(Icons.Filled.Timer, "Duration", "25% weight")
            InfoRow(Icons.Filled.SignalCellularAlt, "Link margin", "20% weight")
            InfoRow(Icons.Filled.BatterySaver, "Battery wait cost", "10% weight")
        }
    }
}

@Composable
fun NearbyPassCard(candidate: NearbyPassCandidate) {
    val score = NearbyPassScorer.score(candidate)
    val color = when {
        score >= 80 -> SuccessGreen
        score >= 60 -> SatelliteBlue
        else -> WarningAmber
    }
    GlassCard(modifier = Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(candidate.name, color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Text("${candidate.path.label} | ${candidate.stateLabel}", color = TextSecondary, fontSize = 12.sp)
            }
            StatusPill("${score}%", color)
        }
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            MetricBlock("Starts", if (candidate.startsInMinutes <= 0) "Now" else "${candidate.startsInMinutes}m")
            MetricBlock("Elev.", "${candidate.elevationDeg.toInt()}\u00B0")
            MetricBlock("Duration", "${candidate.durationSeconds / 60}m")
            MetricBlock("Margin", "${candidate.snrMarginDb.toInt()} dB")
        }
        Spacer(Modifier.height(12.dp))
        Button(onClick = { }, modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = color.copy(alpha = 0.9f), contentColor = SpaceBlack)) {
            Icon(if (candidate.startsInMinutes <= 0) Icons.Filled.SatelliteAlt else Icons.Filled.Schedule, null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Text(NearbyPassScorer.recommendation(candidate), fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
fun MetricBlock(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, color = TextPrimary, fontWeight = FontWeight.Bold)
        Text(label, color = TextSecondary, fontSize = 11.sp)
    }
}

private val DiscoveryLinkPath.label: String get() = when (this) {
    DiscoveryLinkPath.DIRECT_NTN -> "Direct NTN"
    DiscoveryLinkPath.AMATEUR_LEO -> "Amateur LEO"
    DiscoveryLinkPath.LORA_RELAY -> "LoRa relay"
    DiscoveryLinkPath.GROUND_STATION -> "Ground station"
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
