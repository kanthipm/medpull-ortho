package com.medpull.recovery.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * MedPull's tokens, the same values the iPhone app and the console use
 * (ios/MedPull/UI/Theme.swift, frontend/src/index.css): sage brand on a warm
 * canvas, lime as the one accent, four risk tones.
 */
data class MPColors(
    val canvas: Color, val panel: Color, val soft: Color,
    val ink: Color, val body: Color, val muted: Color, val faint: Color,
    val hairline: Color, val line: Color, val lineStrong: Color,
    val brand: Color, val brandInk: Color, val brandTint: Color, val onBrand: Color,
    val lime: Color,
    val riskHigh: Color, val riskHighBg: Color, val riskMed: Color, val riskMedBg: Color,
    val riskLow: Color, val riskLowBg: Color, val riskMissing: Color, val riskMissingBg: Color,
    val teal: Color, val tealTint: Color, val amber: Color, val amberTint: Color,
    val lilac: Color, val lilacTint: Color, val clay: Color, val clayTint: Color,
)

val LightColors = MPColors(
    canvas = Color(0xFFFBFBF9), panel = Color(0xFFFFFFFF), soft = Color(0xFFF2F2F0),
    ink = Color(0xFF141414), body = Color(0xFF585B58), muted = Color(0xFF636662), faint = Color(0xFFA6A8A4),
    hairline = Color(0xFFECECEC), line = Color(0xFFDEDEDE), lineStrong = Color(0xFF8A8C88),
    brand = Color(0xFF4A663E), brandInk = Color(0xFF3F5F33), brandTint = Color(0x1C4A663E), onBrand = Color(0xFFFFFFFF),
    lime = Color(0xFFD4F14A),
    riskHigh = Color(0xFFB04A26), riskHighBg = Color(0x1AB04A26), riskMed = Color(0xFF7C5D0A), riskMedBg = Color(0x1F7C5D0A),
    riskLow = Color(0xFF43712F), riskLowBg = Color(0x1A43712F), riskMissing = Color(0xFF4C5680), riskMissingBg = Color(0x1A4C5680),
    teal = Color(0xFF206E6E), tealTint = Color(0x1C206E6E), amber = Color(0xFFB07414), amberTint = Color(0x21B07414),
    lilac = Color(0xFF544E8E), lilacTint = Color(0x1C544E8E), clay = Color(0xFFB04A26), clayTint = Color(0x1CB04A26),
)

val DarkColors = MPColors(
    canvas = Color(0xFF0B0B0C), panel = Color(0xFF1C1C1E), soft = Color(0xFF141416),
    ink = Color(0xFFF5F5F7), body = Color(0xFFA1A1A6), muted = Color(0xFF8E8E93), faint = Color(0xFF58585D),
    hairline = Color(0xFF2C2C2F), line = Color(0xFF3A3A3D), lineStrong = Color(0xFF78787D),
    brand = Color(0xFF5A7D4A), brandInk = Color(0xFFB7D68A), brandTint = Color(0x24B7D68A), onBrand = Color(0xFF0B0B0C),
    lime = Color(0xFFD4F14A),
    riskHigh = Color(0xFFFF9477), riskHighBg = Color(0x24FF9477), riskMed = Color(0xFFF3C46A), riskMedBg = Color(0x24F3C46A),
    riskLow = Color(0xFF9FD67A), riskLowBg = Color(0x249FD67A), riskMissing = Color(0xFFAAB3E6), riskMissingBg = Color(0x24AAB3E6),
    teal = Color(0xFF78C8C8), tealTint = Color(0x2478C8C8), amber = Color(0xFFF3C46A), amberTint = Color(0x24F3C46A),
    lilac = Color(0xFFAAB3E6), lilacTint = Color(0x24AAB3E6), clay = Color(0xFFFF9477), clayTint = Color(0x24FF9477),
)

val LocalMPColors = staticCompositionLocalOf { LightColors }

object MP {
    val colors: MPColors @Composable get() = LocalMPColors.current
}

private fun scheme(c: MPColors, dark: Boolean): ColorScheme = if (dark) darkColorScheme(
    primary = c.brandInk, onPrimary = c.onBrand, primaryContainer = c.brandTint, onPrimaryContainer = c.brandInk,
    secondary = c.teal, background = c.canvas, onBackground = c.ink, surface = c.panel, onSurface = c.ink,
    surfaceVariant = c.soft, onSurfaceVariant = c.body, outline = c.line, outlineVariant = c.hairline,
    error = c.riskHigh, onError = c.canvas, errorContainer = c.riskHighBg, onErrorContainer = c.riskHigh,
) else lightColorScheme(
    primary = c.brand, onPrimary = c.onBrand, primaryContainer = c.brandTint, onPrimaryContainer = c.brandInk,
    secondary = c.teal, background = c.canvas, onBackground = c.ink, surface = c.panel, onSurface = c.ink,
    surfaceVariant = c.soft, onSurfaceVariant = c.body, outline = c.line, outlineVariant = c.hairline,
    error = c.riskHigh, onError = c.panel, errorContainer = c.riskHighBg, onErrorContainer = c.riskHigh,
)

/** Two bands, as on the iPhone: a UI band (12–20) and a light display band (28–44). */
val MPTypography = Typography(
    displayLarge = TextStyle(fontSize = 44.sp, lineHeight = 48.sp, fontWeight = FontWeight.Light, letterSpacing = (-1.4).sp),
    displayMedium = TextStyle(fontSize = 34.sp, lineHeight = 38.sp, fontWeight = FontWeight.Light, letterSpacing = (-1.0).sp),
    displaySmall = TextStyle(fontSize = 28.sp, lineHeight = 32.sp, fontWeight = FontWeight.Light, letterSpacing = (-0.6).sp),
    headlineSmall = TextStyle(fontSize = 20.sp, lineHeight = 26.sp, fontWeight = FontWeight.Medium, letterSpacing = (-0.2).sp),
    titleLarge = TextStyle(fontSize = 18.sp, lineHeight = 24.sp, fontWeight = FontWeight.Medium),
    titleMedium = TextStyle(fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.Medium),
    bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 24.sp, fontWeight = FontWeight.Normal),
    bodyMedium = TextStyle(fontSize = 14.sp, lineHeight = 20.sp, fontWeight = FontWeight.Normal),
    labelLarge = TextStyle(fontSize = 14.sp, lineHeight = 18.sp, fontWeight = FontWeight.Medium),
    labelMedium = TextStyle(fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.Medium, letterSpacing = 0.4.sp),
    labelSmall = TextStyle(fontSize = 11.sp, lineHeight = 14.sp, fontWeight = FontWeight.Medium, letterSpacing = 0.6.sp),
)

@Composable
fun MedPullTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val colors = if (dark) DarkColors else LightColors
    CompositionLocalProvider(LocalMPColors provides colors) {
        MaterialTheme(colorScheme = scheme(colors, dark), typography = MPTypography, content = content)
    }
}
