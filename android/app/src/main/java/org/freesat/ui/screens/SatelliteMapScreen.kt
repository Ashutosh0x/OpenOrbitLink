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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polyline
import org.freesat.ui.theme.*

data class SatellitePosition(
    val name: String, val norad: Int, val lat: Double, val lon: Double,
    val alt: Double, val velocity: Double, val footprintKm: Double,
    val color: Long, val nextPassMin: Int
)

@Composable
fun SatelliteMapScreen() {
    val context = LocalContext.current
    val satellites = remember { mutableStateListOf(
        SatellitePosition("ISS (ZARYA)", 25544, 28.47, -80.53, 408.0, 7.66, 2200.0, 0xFF00B4D8, 23),
        SatellitePosition("NOAA-19", 33591, 45.12, 12.34, 870.0, 7.45, 2800.0, 0xFF533483, 67),
        SatellitePosition("OSCAR-100", 43700, -2.0, 28.0, 520.0, 7.58, 2400.0, 0xFF00E676, 120),
    )}

    var selectedSat by remember { mutableStateOf<SatellitePosition?>(null) }
    var showGroundStations by remember { mutableStateOf(true) }

    val pulseAnim = rememberInfiniteTransition(label = "mapPulse")
    val pulse by pulseAnim.animateFloat(0.5f, 1f,
        infiniteRepeatable(tween(1500), RepeatMode.Reverse), label = "p")

    Column(modifier = Modifier.fillMaxSize().background(
        Brush.verticalGradient(listOf(SpaceBlack, DeepNavy)))) {

        // Header
        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(modifier = Modifier.size(48.dp).background(
                Brush.linearGradient(listOf(AccentGradientStart, AccentGradientEnd)), CircleShape),
                contentAlignment = Alignment.Center
            ) { Icon(Icons.Filled.Map, null, tint = Color.White, modifier = Modifier.size(24.dp)) }
            Spacer(Modifier.width(14.dp))
            Column {
                Text("Satellite Map", style = MaterialTheme.typography.headlineMedium, color = TextPrimary)
                Text("Live tracking \u2022 ${satellites.size} satellites", style = MaterialTheme.typography.bodySmall, color = TextSecondary)
            }
            Spacer(Modifier.weight(1f))
            IconButton(onClick = { showGroundStations = !showGroundStations }) {
                Icon(Icons.Filled.CellTower, "Ground Stations",
                    tint = if (showGroundStations) SatelliteBlue else TextSecondary)
            }
        }

        // Map
        Box(modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 8.dp)
            .clip(RoundedCornerShape(20.dp))) {
            AndroidView(
                factory = { ctx ->
                    Configuration.getInstance().userAgentValue = "OpenOrbitLink/1.0"
                    MapView(ctx).apply {
                        setTileSource(TileSourceFactory.MAPNIK)
                        setMultiTouchControls(true)
                        controller.setZoom(3.5)
                        controller.setCenter(GeoPoint(20.0, 0.0))
                        setBackgroundColor(android.graphics.Color.parseColor("#0A0E21"))

                        // Add satellite markers
                        satellites.forEach { sat ->
                            val marker = Marker(this)
                            marker.position = GeoPoint(sat.lat, sat.lon)
                            marker.title = sat.name
                            marker.snippet = "Alt: ${sat.alt}km | Speed: ${sat.velocity} km/s"
                            marker.setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                            overlays.add(marker)

                            // Ground track line (simplified orbit arc)
                            val track = Polyline()
                            track.outlinePaint.color = sat.color.toInt()
                            track.outlinePaint.strokeWidth = 3f
                            val points = (0..36).map { i ->
                                val angle = i * 10.0
                                GeoPoint(sat.lat + 15 * Math.sin(Math.toRadians(angle)),
                                    sat.lon + angle * 1.5)
                            }
                            track.setPoints(points)
                            overlays.add(track)
                        }

                        // Ground stations
                        if (showGroundStations) {
                            listOf(
                                Triple("SatNOGS Athens", 37.98, 23.73),
                                Triple("SatNOGS Berlin", 52.52, 13.40),
                                Triple("SatNOGS NYC", 40.71, -74.01),
                                Triple("SatNOGS Tokyo", 35.68, 139.69),
                                Triple("SatNOGS Sydney", -33.87, 151.21),
                                Triple("OpenOrbitLink GS-001", 28.61, 77.21),
                            ).forEach { (name, lat, lon) ->
                                val m = Marker(this)
                                m.position = GeoPoint(lat, lon)
                                m.title = name
                                m.setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                                overlays.add(m)
                            }
                        }
                        invalidate()
                    }
                }, modifier = Modifier.fillMaxSize()
            )

            // Satellite legend overlay
            Column(modifier = Modifier.align(Alignment.TopEnd).padding(12.dp)) {
                satellites.forEach { sat ->
                    Surface(shape = RoundedCornerShape(8.dp),
                        color = SpaceBlack.copy(alpha = 0.85f),
                        border = BorderStroke(1.dp, Color(sat.color).copy(alpha = 0.5f)),
                        modifier = Modifier.padding(bottom = 4.dp),
                        onClick = { selectedSat = sat }) {
                        Row(modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(8.dp).clip(CircleShape)
                                .background(Color(sat.color).copy(alpha = pulse)))
                            Spacer(Modifier.width(6.dp))
                            Text(sat.name, fontSize = 11.sp, color = TextPrimary, fontWeight = FontWeight.Medium)
                        }
                    }
                }
            }
        }

        // Bottom satellite info cards
        Row(modifier = Modifier.padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            satellites.forEach { sat ->
                Surface(modifier = Modifier.weight(1f), shape = RoundedCornerShape(16.dp),
                    color = SurfaceCard.copy(alpha = 0.7f),
                    border = BorderStroke(1.dp, Color(sat.color).copy(alpha = 0.3f)),
                    onClick = { selectedSat = sat }) {
                    Column(modifier = Modifier.padding(12.dp),
                        horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(sat.name.split(" ")[0], fontSize = 12.sp,
                            fontWeight = FontWeight.Bold, color = Color(sat.color))
                        Text("${sat.alt.toInt()} km", fontSize = 10.sp, color = TextSecondary)
                        Spacer(Modifier.height(4.dp))
                        Text("${sat.nextPassMin}m", fontSize = 16.sp,
                            fontWeight = FontWeight.Black, color = TextPrimary)
                        Text("next pass", fontSize = 9.sp, color = TextSecondary)
                    }
                }
            }
        }
    }
}
