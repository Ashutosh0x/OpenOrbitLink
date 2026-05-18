package org.freesat.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// ─── OpenOrbitLink Color System ──────────────────────────────────────────────
// Deep space-inspired palette with satellite accent colors

val SpaceBlack = Color(0xFF0A0E21)
val DeepNavy = Color(0xFF1A1A2E)
val CosmicIndigo = Color(0xFF16213E)
val NebulaPurple = Color(0xFF533483)
val SatelliteBlue = Color(0xFF00B4D8)
val SignalCyan = Color(0xFF90E0EF)
val AlertRed = Color(0xFFE94560)
val SOSRed = Color(0xFFFF1744)
val SuccessGreen = Color(0xFF00E676)
val WarningAmber = Color(0xFFFFAB00)
val SurfaceDark = Color(0xFF121228)
val SurfaceCard = Color(0xFF1E1E3A)
val TextPrimary = Color(0xFFEDF2F4)
val TextSecondary = Color(0xFF8D99AE)
val AccentGradientStart = Color(0xFF6C63FF)
val AccentGradientEnd = Color(0xFF00B4D8)

private val OpenOrbitLinkDarkColors = darkColorScheme(
    primary = SatelliteBlue,
    onPrimary = SpaceBlack,
    primaryContainer = CosmicIndigo,
    onPrimaryContainer = SignalCyan,
    secondary = NebulaPurple,
    onSecondary = TextPrimary,
    secondaryContainer = Color(0xFF2D2D5E),
    onSecondaryContainer = Color(0xFFCAC4DF),
    tertiary = SignalCyan,
    onTertiary = SpaceBlack,
    error = AlertRed,
    onError = Color.White,
    errorContainer = Color(0xFF93000A),
    background = SpaceBlack,
    onBackground = TextPrimary,
    surface = SurfaceDark,
    onSurface = TextPrimary,
    surfaceVariant = SurfaceCard,
    onSurfaceVariant = TextSecondary,
    outline = Color(0xFF3A3A5C),
    outlineVariant = Color(0xFF2A2A4A),
)

private val OpenOrbitLinkLightColors = lightColorScheme(
    primary = Color(0xFF0077B6),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFCAF0F8),
    onPrimaryContainer = Color(0xFF001F2A),
    secondary = Color(0xFF6C63FF),
    tertiary = Color(0xFF00B4D8),
    error = Color(0xFFBA1A1A),
    background = Color(0xFFF8F9FA),
    surface = Color.White,
    surfaceVariant = Color(0xFFE9ECF0),
    onSurfaceVariant = Color(0xFF44474E),
    outline = Color(0xFF74777F),
)

@Composable
fun OpenOrbitLinkTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context)
            else dynamicLightColorScheme(context)
        }
        darkTheme -> OpenOrbitLinkDarkColors
        else -> OpenOrbitLinkLightColors
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = OpenOrbitLinkTypography,
        shapes = OpenOrbitLinkShapes,
        content = content
    )
}

val OpenOrbitLinkTypography = Typography(
    displayLarge = TextStyle(
        fontWeight = FontWeight.Black,
        fontSize = 34.sp,
        lineHeight = 40.sp,
        letterSpacing = (-0.5).sp
    ),
    headlineLarge = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize = 28.sp,
        lineHeight = 36.sp,
        letterSpacing = (-0.25).sp
    ),
    headlineMedium = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize = 22.sp,
        lineHeight = 28.sp,
    ),
    titleLarge = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
        lineHeight = 26.sp,
    ),
    titleMedium = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
        lineHeight = 22.sp,
        letterSpacing = 0.15.sp
    ),
    bodyLarge = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
        lineHeight = 24.sp,
        letterSpacing = 0.5.sp
    ),
    bodyMedium = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        letterSpacing = 0.25.sp
    ),
    labelLarge = TextStyle(
        fontWeight = FontWeight.Medium,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        letterSpacing = 0.1.sp
    ),
    labelSmall = TextStyle(
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        lineHeight = 16.sp,
        letterSpacing = 0.5.sp
    ),
)

val OpenOrbitLinkShapes = Shapes(
    extraSmall = androidx.compose.foundation.shape.RoundedCornerShape(4.dp),
    small = androidx.compose.foundation.shape.RoundedCornerShape(8.dp),
    medium = androidx.compose.foundation.shape.RoundedCornerShape(16.dp),
    large = androidx.compose.foundation.shape.RoundedCornerShape(24.dp),
    extraLarge = androidx.compose.foundation.shape.RoundedCornerShape(32.dp),
)
