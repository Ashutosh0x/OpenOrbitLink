package org.freesat.ui.screens

import androidx.compose.animation.animateContentSize
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.freesat.ui.theme.*

data class SetupStep(
    val title: String, val description: String, val icon: ImageVector,
    val checkItems: List<String>, val isCompleted: Boolean = false
)

@Composable
fun HardwareSetupScreen() {
    var selectedPath by remember { mutableStateOf(2) } // 0=NTN, 1=SDR, 2=LoRa
    var expandedStep by remember { mutableStateOf(0) }

    val paths = listOf(
        Triple("Path A \u2014 Direct NTN", "$0 \u2022 No hardware needed", SatelliteBlue),
        Triple("Path B \u2014 USB SDR", "$80 \u2022 RTL-SDR V4 + Antenna", NebulaPurple),
        Triple("Path C \u2014 LoRa Mesh", "$10 \u2022 SX1276 + Bluetooth", SuccessGreen),
    )

    val stepsPerPath = mapOf(
        0 to listOf(
            SetupStep("Check Phone Compatibility", "Verify your phone has NTN modem", Icons.Filled.Smartphone,
                listOf("Pixel 9/10 or Galaxy S25+", "Android 15+ with NTN API", "SIM card with satellite plan"), true),
            SetupStep("Enable Satellite Mode", "Turn on NTN in system settings", Icons.Filled.SettingsInputAntenna,
                listOf("Settings > Connectivity > Satellite", "Accept emergency terms", "Test SOS connectivity")),
            SetupStep("Install OpenOrbitLink", "Configure the app for NTN path", Icons.Filled.InstallMobile,
                listOf("Select Path A in OpenOrbitLink settings", "Grant location permission", "Send first test message")),
        ),
        1 to listOf(
            SetupStep("Acquire Hardware", "Get RTL-SDR V4 + antenna kit", Icons.Filled.ShoppingCart,
                listOf("RTL-SDR Blog V4 dongle ($30)", "Dipole antenna kit ($15)", "USB-C OTG adapter ($5)", "Optional: Yagi antenna ($50)"), true),
            SetupStep("Connect SDR", "Plug in via USB OTG", Icons.Filled.Usb,
                listOf("Connect OTG adapter to phone", "Plug RTL-SDR into adapter", "Attach antenna to SMA port", "Grant USB permission in app")),
            SetupStep("Tune & Verify", "Receive first satellite signal", Icons.Filled.Waves,
                listOf("Select 137.100 MHz (NOAA)", "Verify signal on waterfall", "Decode first APT image", "Try 145.800 MHz (ISS APRS)")),
            SetupStep("Go Operational", "Start receiving messages", Icons.Filled.Rocket,
                listOf("Enable DTN store-and-forward", "Set auto-track schedule", "Join SatNOGS network")),
        ),
        2 to listOf(
            SetupStep("Get LoRa Module", "Acquire SX1276 hardware", Icons.Filled.Memory,
                listOf("Heltec LoRa 32 V3 ($10)", "Or: TTGO LoRa32 ($12)", "868 MHz antenna (included)", "Micro-USB cable"), true),
            SetupStep("Flash Firmware", "Install OpenOrbitLink LoRa firmware", Icons.Filled.SystemUpdate,
                listOf("Download OpenOrbitLink-lora.bin", "Flash via Arduino IDE or esptool", "Configure frequency: 868 MHz", "Set spreading factor: SF12")),
            SetupStep("Pair via Bluetooth", "Connect LoRa module to phone", Icons.Filled.Bluetooth,
                listOf("Power on LoRa module", "Open OpenOrbitLink > Settings > Bluetooth", "Select 'OpenOrbitLink-LoRa-XXXX'", "Verify connection indicator")),
            SetupStep("Join Mesh", "Connect to nearby nodes", Icons.Filled.Hub,
                listOf("Scan for mesh neighbors", "Relay through satellite-capable node", "Send first mesh message", "Check delivery confirmation")),
        ),
    )

    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp).verticalScroll(rememberScrollState())) {

        ScreenHeader("Hardware Setup", "Step-by-step connection wizard", Icons.Filled.Build)

        // Path selector
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            paths.forEachIndexed { index, (title, subtitle, color) ->
                Surface(modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(14.dp),
                    color = if (selectedPath == index) color.copy(alpha = 0.15f) else SurfaceCard.copy(alpha = 0.4f),
                    border = BorderStroke(1.5.dp,
                        if (selectedPath == index) color.copy(alpha = 0.5f) else Color.Transparent),
                    onClick = { selectedPath = index; expandedStep = 0 }) {
                    Column(modifier = Modifier.padding(12.dp),
                        horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(title.split(" \u2014 ")[1], fontSize = 13.sp,
                            fontWeight = FontWeight.Bold, color = if (selectedPath == index) color else TextSecondary)
                        Text(subtitle.split(" \u2022 ")[0], fontSize = 11.sp, color = TextSecondary)
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // Setup steps
        val steps = stepsPerPath[selectedPath] ?: emptyList()
        steps.forEachIndexed { index, step ->
            val isExpanded = expandedStep == index
            val stepColor = paths[selectedPath].third

            Surface(modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp)
                .animateContentSize(),
                shape = RoundedCornerShape(16.dp),
                color = if (isExpanded) stepColor.copy(alpha = 0.06f) else SurfaceCard.copy(alpha = 0.5f),
                border = BorderStroke(1.dp,
                    if (isExpanded) stepColor.copy(alpha = 0.3f) else Color.White.copy(alpha = 0.05f)),
                onClick = { expandedStep = index }) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        // Step number
                        Box(modifier = Modifier.size(36.dp)
                            .background(
                                if (step.isCompleted) SuccessGreen.copy(alpha = 0.2f)
                                else stepColor.copy(alpha = 0.15f), CircleShape),
                            contentAlignment = Alignment.Center) {
                            if (step.isCompleted) {
                                Icon(Icons.Filled.Check, null, tint = SuccessGreen,
                                    modifier = Modifier.size(20.dp))
                            } else {
                                Text("${index + 1}", fontWeight = FontWeight.Bold,
                                    color = stepColor, fontSize = 14.sp)
                            }
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(step.title, fontWeight = FontWeight.Bold, color = TextPrimary)
                            Text(step.description, fontSize = 12.sp, color = TextSecondary)
                        }
                        Icon(step.icon, null, tint = stepColor.copy(alpha = 0.6f),
                            modifier = Modifier.size(24.dp))
                    }

                    // Expanded checklist
                    if (isExpanded) {
                        Spacer(Modifier.height(14.dp))
                        step.checkItems.forEach { item ->
                            Row(modifier = Modifier.padding(start = 48.dp, bottom = 8.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                Icon(if (step.isCompleted) Icons.Filled.CheckCircle else Icons.Filled.RadioButtonUnchecked,
                                    null, tint = if (step.isCompleted) SuccessGreen else TextSecondary,
                                    modifier = Modifier.size(16.dp))
                                Spacer(Modifier.width(10.dp))
                                Text(item, fontSize = 13.sp,
                                    color = if (step.isCompleted) TextSecondary else TextPrimary)
                            }
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // Hardware BOM summary
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Estimated Cost", style = MaterialTheme.typography.titleMedium, color = paths[selectedPath].third)
            Spacer(Modifier.height(8.dp))
            val costs = when (selectedPath) {
                0 -> listOf("Phone (existing)" to "$0", "SIM/Plan" to "$0", "Total" to "$0")
                1 -> listOf("RTL-SDR V4" to "$30", "Antenna" to "$15", "OTG Adapter" to "$5", "Total" to "$50-80")
                else -> listOf("LoRa Module" to "$10", "USB Cable" to "$2", "Total" to "$10-12")
            }
            costs.forEach { (item, cost) ->
                Row(modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
                    Text(item, fontSize = 13.sp, color = if (item == "Total") TextPrimary else TextSecondary,
                        fontWeight = if (item == "Total") FontWeight.Bold else FontWeight.Normal,
                        modifier = Modifier.weight(1f))
                    Text(cost, fontSize = 13.sp, fontWeight = FontWeight.Bold,
                        color = if (item == "Total") paths[selectedPath].third else TextPrimary)
                }
            }
        }
    }
}
