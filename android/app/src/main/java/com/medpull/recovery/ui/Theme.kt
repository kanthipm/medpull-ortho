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
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.sp
import com.medpull.recovery.R

/**
 * MedPull's tokens, the same values the iPhone app and the console use
 * (ios/MedPull/UI/Theme.swift, frontend/src/index.css): Outfit, warm
 * neutrals, a near-black primary capsule, sage as the brand fill, lime as
 * the one accent, four risk tones on solid tints, and the earthy gradients.
 */
data class MPColors(
    val canvas: Color, val panel: Color, val soft: Color, val track: Color,
    val ink: Color, val body: Color, val muted: Color, val faint: Color,
    val hairline: Color, val line: Color, val lineStrong: Color,
    val action: Color, val actionTop: Color, val onAction: Color,
    val brand: Color, val brandInk: Color, val brandDeep: Color, val brandTint: Color, val brandTintStrong: Color, val onBrand: Color,
    val lime: Color,
    val fill: Color, val fillStrong: Color,
    val glassTop: Color, val glassBottom: Color, val glassSolidTop: Color, val glassSolidBottom: Color,
    val glassRim: Color, val glassRing: Color, val shadow: Color,
    val riskHigh: Color, val riskHighBg: Color, val riskMed: Color, val riskMedBg: Color,
    val riskLow: Color, val riskLowBg: Color, val riskMissing: Color, val riskMissingBg: Color,
    /** Category inks and tints. Hue is category, never state. */
    val teal: Color, val tealTint: Color, val amber: Color, val amberTint: Color,
    val lilac: Color, val lilacTint: Color, val clay: Color, val clayTint: Color,
    val fogSage: Color, val fogAmber: Color, val fogClay: Color, val fogLilac: Color, val fogMint: Color,
    val isDark: Boolean,
)

val LightColors = MPColors(
    canvas = Color(0xFFFBFBF9), panel = Color(0xFFFFFFFF), soft = Color(0xFFF2F2F0), track = Color(0xFFE3E3E0),
    ink = Color(0xFF141414), body = Color(0xFF585B58), muted = Color(0xFF636662), faint = Color(0xFFA6A8A4),
    hairline = Color(0xFFECECEC), line = Color(0xFFDEDEDE), lineStrong = Color(0xFF8A8C88),
    action = Color(0xFF141414), actionTop = Color(0xFF3A3A3A), onAction = Color(0xFFFFFFFF),
    brand = Color(0xFF4A663E), brandInk = Color(0xFF3F5F33), brandDeep = Color(0xFF334D29),
    brandTint = Color(0xFFE9F1E4), brandTintStrong = Color(0xFFDBE8D3), onBrand = Color(0xFFFFFFFF),
    lime = Color(0xFFD4F14A),
    fill = Color(0x1A78786E), fillStrong = Color(0x2E78786E),
    glassTop = Color(0xEBFFFFFF), glassBottom = Color(0xC7FFFFFF), glassSolidTop = Color(0xF2FFFFFF), glassSolidBottom = Color(0xD6FFFFFF),
    glassRim = Color(0xD9FFFFFF), glassRing = Color(0x1A141414), shadow = Color(0xFF141414),
    riskHigh = Color(0xFFB04A26), riskHighBg = Color(0xFFFBECE6), riskMed = Color(0xFF7C5D0A), riskMedBg = Color(0xFFF8F0D8),
    riskLow = Color(0xFF43712F), riskLowBg = Color(0xFFE7EFE1), riskMissing = Color(0xFF4C5680), riskMissingBg = Color(0xFFE8EAF3),
    teal = Color(0xFF3F5F33), tealTint = Color(0xFFE9F1E4), amber = Color(0xFF7C5D0A), amberTint = Color(0xFFF8F0D8),
    lilac = Color(0xFF544E8E), lilacTint = Color(0xFFECEBF5), clay = Color(0xFF7A5946), clayTint = Color(0xFFF4ECE7),
    fogSage = Color(0x6B8FAE74), fogAmber = Color(0x66ECC76E), fogClay = Color(0x57E9A07D), fogLilac = Color(0x5C9AA3DC), fogMint = Color(0x5278BEAF),
    isDark = false,
)

val DarkColors = MPColors(
    canvas = Color(0xFF0B0B0C), panel = Color(0xFF1C1C1E), soft = Color(0xFF262628), track = Color(0xFF343437),
    ink = Color(0xFFF5F5F7), body = Color(0xFFA1A1A6), muted = Color(0xFF8E8E93), faint = Color(0xFF58585D),
    hairline = Color(0xFF2C2C2F), line = Color(0xFF3A3A3D), lineStrong = Color(0xFF78787D),
    action = Color(0xFFF5F5F7), actionTop = Color(0xFFFFFFFF), onAction = Color(0xFF141414),
    brand = Color(0xFF5A7D4A), brandInk = Color(0xFFB7D68A), brandDeep = Color(0xFF4A663E),
    brandTint = Color(0xFF2C3428), brandTintStrong = Color(0xFF35402F), onBrand = Color(0xFFFFFFFF),
    lime = Color(0xFFD4F14A),
    fill = Color(0x12FFFFFF), fillStrong = Color(0x1FFFFFFF),
    glassTop = Color(0xF0242428), glassBottom = Color(0xE61C1C1E), glassSolidTop = Color(0xF52E2E32), glassSolidBottom = Color(0xEB222226),
    glassRim = Color(0x0FFFFFFF), glassRing = Color(0x80000000), shadow = Color(0xFF000000),
    riskHigh = Color(0xFFFF9477), riskHighBg = Color(0xFF402B28), riskMed = Color(0xFFF3C46A), riskMedBg = Color(0xFF3E3426),
    riskLow = Color(0xFF9FD67A), riskLowBg = Color(0xFF2D3628), riskMissing = Color(0xFFAAB3E6), riskMissingBg = Color(0xFF303240),
    teal = Color(0xFFB7D68A), tealTint = Color(0xFF2C3428), amber = Color(0xFFF3C46A), amberTint = Color(0xFF3E3426),
    lilac = Color(0xFFB3AEF0), lilacTint = Color(0xFF2C2B42), clay = Color(0xFFE0B49A), clayTint = Color(0xFF3A2C26),
    fogSage = Color(0x298FAE74), fogAmber = Color(0x17ECC76E), fogClay = Color(0x17E9A07D), fogLilac = Color(0x269AA3DC), fogMint = Color(0x1778BEAF),
    isDark = true,
)

val LocalMPColors = staticCompositionLocalOf { LightColors }

object MP {
    val colors: MPColors @Composable get() = LocalMPColors.current
}

/** The site's grainy gradient tiles: dark at the top where white text sits, light at the bottom. */
enum class MPGradient(val stops: List<Pair<Float, Color>>, val glow: Pair<Color, Pair<Float, Float>>?) {
    SAGE(listOf(0f to Color(0xFF405A36), 0.52f to Color(0xFF5F7D4C), 1f to Color(0xFFAEBF87)), Color(0xFFE6DB7C) to (0.5f to 1.08f)),
    MEADOW(listOf(0f to Color(0xFF3F5735), 0.42f to Color(0xFF587548), 0.78f to Color(0xFF8AA56A), 1f to Color(0xFFB8B977)), Color(0xFFD9CF7E) to (0.7f to 1.1f)),
    AMBER(listOf(0f to Color(0xFF7D6420), 0.42f to Color(0xFFA88C35), 1f to Color(0xFFCDB46A)), Color(0xFFEEC27A) to (0.25f to 1.0f)),
    CLAY(listOf(0f to Color(0xFF7A5946), 0.48f to Color(0xFFA27A64), 1f to Color(0xFFC9A893)), Color(0xFFE3AA66) to (0.3f to 1.0f)),
    DUSK(listOf(0f to Color(0xFF9A5A39), 0.42f to Color(0xFFA8807A), 1f to Color(0xFF6B7FA0)), null),
    LILAC(listOf(0f to Color(0xFF40457F), 0.62f to Color(0xFF544E8E), 1f to Color(0xFF806B8C)), null),
    MINT(listOf(0f to Color(0xFF3F7F74), 0.5f to Color(0xFF78BBA8), 1f to Color(0xFFD4E0A6)), null);

    val top: Color get() = stops.first().second
}

/** The medpull.org face, bundled at 200–600. 600 is only the bold-text step. */
val Outfit = FontFamily(
    Font(R.font.outfit_extralight, FontWeight.W200),
    Font(R.font.outfit_light, FontWeight.W300),
    Font(R.font.outfit_regular, FontWeight.W400),
    Font(R.font.outfit_medium, FontWeight.W500),
    Font(R.font.outfit_semibold, FontWeight.W600),
)

private val trim = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.None)

private fun rung(size: Int, weight: FontWeight, lineHeight: Int, tracking: Float, figures: Boolean = false) = TextStyle(
    fontFamily = Outfit, fontSize = size.sp, lineHeight = lineHeight.sp, fontWeight = weight, letterSpacing = tracking.sp,
    lineHeightStyle = trim, fontFeatureSettings = if (figures) "tnum" else null,
)

/**
 * The frozen ladder: 12 / 14 / 16 / 18 / 20 for UI, 28 / 34 / 44 / 54 for
 * display in the light weight. Tracking is the site's, in points.
 */
object MPType {
    val axis = rung(11, FontWeight.W400, 14, 0f)
    val label = rung(12, FontWeight.W400, 16, 0f)
    val labelMedium = rung(12, FontWeight.W500, 16, 0f)
    val copy = rung(14, FontWeight.W400, 20, -0.06f)
    val copyMedium = rung(14, FontWeight.W500, 20, -0.06f)
    val copyLarge = rung(16, FontWeight.W400, 22, -0.1f)
    val copyLargeMedium = rung(16, FontWeight.W500, 22, -0.1f)
    val cardTitle = rung(15, FontWeight.W500, 20, -0.08f)
    val lede = rung(18, FontWeight.W400, 24, -0.18f)
    val ledeMedium = rung(18, FontWeight.W500, 24, -0.18f)
    val subhead = rung(20, FontWeight.W400, 26, -0.4f)
    val subheadMedium = rung(20, FontWeight.W500, 26, -0.4f)
    val displayS = rung(28, FontWeight.W300, 32, -1.1f)
    val displayM = rung(34, FontWeight.W300, 38, -1.4f)
    val displayL = rung(44, FontWeight.W300, 48, -2.0f)
    val displayXL = rung(54, FontWeight.W300, 58, -2.7f)
    val figuresLabel = rung(12, FontWeight.W400, 16, 0f, figures = true)
    val figuresCopy = rung(14, FontWeight.W400, 20, -0.06f, figures = true)
    val figuresCopyLarge = rung(16, FontWeight.W500, 22, -0.1f, figures = true)
    val figuresLede = rung(18, FontWeight.W500, 24, -0.18f, figures = true)
    val figuresSubhead = rung(20, FontWeight.W500, 26, -0.4f, figures = true)
    fun figuresDisplay(size: Int) = rung(size, FontWeight.W300, size + 4, -size * 0.045f, figures = true)
}

/** Material's slots mapped onto the ladder, so every stock widget speaks Outfit. */
val MPTypography = Typography(
    displayLarge = MPType.displayL, displayMedium = MPType.displayM, displaySmall = MPType.displayS,
    headlineLarge = MPType.displayS, headlineMedium = MPType.subheadMedium, headlineSmall = MPType.subheadMedium,
    titleLarge = MPType.ledeMedium, titleMedium = MPType.copyLargeMedium, titleSmall = MPType.copyMedium,
    bodyLarge = MPType.copyLarge, bodyMedium = MPType.copy, bodySmall = MPType.label,
    labelLarge = MPType.copyLargeMedium, labelMedium = MPType.labelMedium, labelSmall = MPType.labelMedium,
)

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

@Composable
fun MedPullTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val colors = if (dark) DarkColors else LightColors
    CompositionLocalProvider(LocalMPColors provides colors) {
        MaterialTheme(colorScheme = scheme(colors, dark), typography = MPTypography, content = content)
    }
}
