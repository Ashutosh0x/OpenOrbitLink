package org.freesat

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.style.TextAlign
import androidx.navigation.NavController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import org.freesat.ui.theme.*
import org.freesat.ui.screens.*

class MainActivity : ComponentActivity() {
    companion object {
        init {
            try { System.loadLibrary("codec2_jni") }
            catch (e: UnsatisfiedLinkError) {
                android.util.Log.w("OpenOrbitLink", "Codec2 native not available")
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            OpenOrbitLinkTheme(darkTheme = true, dynamicColor = false) {
                OpenOrbitLinkApp()
            }
        }
    }
}

// ─── Navigation Items ──────────────────────────────────────────────────
sealed class NavItem(val route: String, val label: String,
                     val icon: ImageVector, val selectedIcon: ImageVector,
                     val group: NavGroup = NavGroup.PRIMARY) {
    // Primary (bottom bar — 5 most used)
    object Messages : NavItem("messaging", "Messages", Icons.Outlined.Chat, Icons.Filled.Chat)
    object Radar : NavItem("radar", "Radar", Icons.Outlined.SatelliteAlt, Icons.Filled.SatelliteAlt)
    object Dashboard : NavItem("dashboard", "Link", Icons.Outlined.Speed, Icons.Filled.Speed)
    object SOS : NavItem("sos", "SOS", Icons.Outlined.Warning, Icons.Filled.Warning)
    object Settings : NavItem("settings", "More", Icons.Outlined.Menu, Icons.Filled.Menu)

    // Secondary (accessible from top bar / drawer / More screen)
    object Map : NavItem("map", "Map", Icons.Outlined.Map, Icons.Filled.Map, NavGroup.SECONDARY)
    object Nearby : NavItem("nearby", "Nearby", Icons.Outlined.Explore, Icons.Filled.Explore, NavGroup.SECONDARY)
    object Call : NavItem("call", "PTT", Icons.Outlined.Call, Icons.Filled.Call, NavGroup.SECONDARY)
    object Tracker : NavItem("satellite", "Tracker", Icons.Outlined.Bolt, Icons.Filled.Bolt, NavGroup.SECONDARY)
    object Mesh : NavItem("mesh", "Mesh", Icons.Outlined.Hub, Icons.Filled.Hub, NavGroup.SECONDARY)
    object SkyScan : NavItem("skyscan", "Sky Scan", Icons.Outlined.CameraAlt, Icons.Filled.CameraAlt, NavGroup.SECONDARY)
    object Network : NavItem("network", "Network", Icons.Outlined.AccountTree, Icons.Filled.AccountTree, NavGroup.SECONDARY)
    object GroundStation : NavItem("ground", "Station", Icons.Outlined.CellTower, Icons.Filled.CellTower, NavGroup.SECONDARY)
    object Hardware : NavItem("hardware", "Setup", Icons.Outlined.Build, Icons.Filled.Build, NavGroup.SECONDARY)
}

enum class NavGroup { PRIMARY, SECONDARY }

val primaryNavItems = listOf(NavItem.Messages, NavItem.Radar, NavItem.Dashboard, NavItem.SOS, NavItem.Settings)
val secondaryNavItems = listOf(NavItem.Map, NavItem.Nearby, NavItem.Call, NavItem.Tracker, NavItem.Mesh, NavItem.SkyScan, NavItem.Network, NavItem.GroundStation, NavItem.Hardware)
val allNavItems = primaryNavItems + secondaryNavItems

// ─── App Shell ─────────────────────────────────────────────────────────
@Composable
fun OpenOrbitLinkApp() {
    val navController = rememberNavController()
    val startDest = "radar"  // Skip login — go straight to satellite radar
    val currentRoute = navController.currentBackStackEntryAsState().value?.destination?.route
    val showBottomBar = true

    Scaffold(
        containerColor = Color.Transparent,
        modifier = Modifier.background(
            Brush.verticalGradient(listOf(SpaceBlack, DeepNavy, SpaceBlack))
        ),
        bottomBar = { if (showBottomBar) OpenOrbitLinkNavBar(navController) }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = startDest,
            modifier = Modifier
                .padding(innerPadding)
                .background(Color.Transparent),
            enterTransition = { fadeIn(tween(300)) + slideInHorizontally { it / 4 } },
            exitTransition = { fadeOut(tween(200)) },
        ) {
            // Login removed — direct satellite access
            // Auth can be re-enabled for backend sync later

            // Primary screens
            composable("messaging") { MessagingScreen() }
            composable("radar") { SatelliteRadarScreen() }
            composable("map") { SatelliteMapScreen() }
            composable("dashboard") { LinkDashboardScreen() }
            composable("sos") { EmergencySOSScreen() }
            composable("settings") { MoreScreen(navController) }

            // Secondary screens
            composable("nearby") { NearbyPassesScreen() }
            composable("call") { CallPttScreen() }
            composable("satellite") { SatelliteTrackerScreen() }
            composable("mesh") { MeshNetworkScreen() }
            composable("skyscan") { SkyScannerScreen() }
            composable("network") { NetworkPathScreen() }
            composable("ground") { GroundStationScreen() }
            composable("hardware") { HardwareSetupScreen() }
        }
    }
}

// ─── Bottom Navigation ─────────────────────────────────────────────────
@Composable
fun OpenOrbitLinkNavBar(navController: NavController) {
    val currentRoute = navController.currentBackStackEntryAsState().value?.destination?.route

    NavigationBar(
        containerColor = SurfaceDark.copy(alpha = 0.95f),
        tonalElevation = 0.dp,
    ) {
        primaryNavItems.forEach { item ->
            val selected = currentRoute == item.route ||
                (item is NavItem.Settings && currentRoute in secondaryNavItems.map { it.route })
            NavigationBarItem(
                selected = selected,
                onClick = {
                    if (currentRoute != item.route) {
                        navController.navigate(item.route) {
                            popUpTo("messaging") { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    }
                },
                icon = {
                    Icon(
                        if (selected) item.selectedIcon else item.icon,
                        contentDescription = item.label,
                        tint = when {
                            item is NavItem.SOS && selected -> SOSRed
                            selected -> SatelliteBlue
                            else -> TextSecondary
                        }
                    )
                },
                label = {
                    Text(item.label, style = MaterialTheme.typography.labelSmall,
                        color = if (selected) SatelliteBlue else TextSecondary)
                },
                colors = NavigationBarItemDefaults.colors(
                    indicatorColor = if (item is NavItem.SOS) SOSRed.copy(alpha = 0.15f)
                                    else SatelliteBlue.copy(alpha = 0.12f)
                )
            )
        }
    }
}

// ─── More / Hub Screen ─────────────────────────────────────────────────
@Composable
fun MoreScreen(navController: NavController) {
    Column(modifier = Modifier.fillMaxSize()
        .background(Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))
        .padding(16.dp)) {

        ScreenHeader("OpenOrbitLink Hub", "All features & tools", Icons.Filled.Apps)

        // Quick access grid
        val hubItems = listOf(
            Triple(NavItem.Radar, "Real-time satellite radar scanner", SatelliteBlue),
            Triple(NavItem.Map, "Satellite positions on world map", AccentGradientEnd),
            Triple(NavItem.Nearby, "Nearby passes and best contact windows", SuccessGreen),
            Triple(NavItem.Call, "Half-duplex voice with text fallback", NebulaPurple),
            Triple(NavItem.Tracker, "Satellite pass predictions", AccentGradientStart),
            Triple(NavItem.Mesh, "LoRa mesh network", SuccessGreen),
            Triple(NavItem.SkyScan, "AR sky visibility scan", NebulaPurple),
            Triple(NavItem.Network, "Data path visualizer", AccentGradientStart),
            Triple(NavItem.GroundStation, "Remote station control", WarningAmber),
            Triple(NavItem.Hardware, "Setup wizard", AlertRed),
        )

        hubItems.chunked(2).forEach { row ->
            Row(modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                row.forEach { (item, desc, color) ->
                    Surface(modifier = Modifier.weight(1f).height(120.dp),
                        shape = RoundedCornerShape(18.dp),
                        color = color.copy(alpha = 0.08f),
                        border = androidx.compose.foundation.BorderStroke(1.dp, color.copy(alpha = 0.2f)),
                        onClick = {
                            navController.navigate(item.route) {
                                popUpTo("messaging") { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        }) {
                        Column(modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.SpaceBetween) {
                            Icon(item.selectedIcon, null, tint = color,
                                modifier = Modifier.size(28.dp))
                            Column {
                                Text(item.label, fontWeight = FontWeight.Bold,
                                    color = TextPrimary, fontSize = 15.sp)
                                Text(desc, fontSize = 10.sp, color = TextSecondary,
                                    lineHeight = 13.sp)
                            }
                        }
                    }
                }
                // Pad odd rows
                if (row.size == 1) { Spacer(Modifier.weight(1f)) }
            }
        }

        Spacer(Modifier.height(16.dp))

        // Settings section
        GlassCard(modifier = Modifier.fillMaxWidth()) {
            Text("Settings", style = MaterialTheme.typography.titleMedium, color = SatelliteBlue)
            Spacer(Modifier.height(12.dp))
            InfoRow(Icons.Filled.Fingerprint, "Biometric Lock", "OFF")
            InfoRow(Icons.Filled.Notifications, "Pass Alerts", "ON", SuccessGreen)
            InfoRow(Icons.Filled.DarkMode, "Theme", "Space Dark")
            InfoRow(Icons.Filled.Storage, "DTN Bundle Cache", "12.4 MB")
            InfoRow(Icons.Filled.Info, "Version", "1.0.0-alpha")
        }

        Spacer(Modifier.height(16.dp))

        // App info
        Text(
            "OpenOrbitLink — LoRa Satellite Mesh",
            color = TextSecondary,
            fontSize = 11.sp,
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.Center
        )
    }
}
