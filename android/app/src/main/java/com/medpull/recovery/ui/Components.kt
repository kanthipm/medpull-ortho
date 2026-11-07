package com.medpull.recovery.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.ImageShader
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.ShaderBrush
import androidx.compose.ui.graphics.TileMode
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.imageResource
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import com.medpull.recovery.R

/**
 * The shared components, in the medpull.org language the iPhone app uses
 * (ios/MedPull/UI/Components.swift, Rows.swift): a card is a white glass
 * surface with a light rim and a soft layered shadow; the primary action is
 * the near-black capsule with a lime dot; icon tiles and heroes are grainy
 * earthy gradients with white marks; state is always a pill with a word.
 */

/** The iPhone's radii: surface 26, control 18, thumb 14, tile 9, canvas 34. */
object Radii {
    val surface = 26.dp; val control = 18.dp; val thumb = 14.dp; val tile = 9.dp; val canvas = 34.dp
}

val SurfaceShape = RoundedCornerShape(Radii.surface)
val ControlShape = RoundedCornerShape(Radii.control)
val ThumbShape = RoundedCornerShape(Radii.thumb)
val CapsuleShape = RoundedCornerShape(50)

/** Category colour: hue names a kind of thing, never a state. */
enum class Category { BLUE, TEAL, INDIGO, VIOLET }

@Composable fun categoryInk(f: Category): Color = MP.colors.let { when (f) { Category.BLUE -> it.amber; Category.TEAL -> it.teal; Category.INDIGO -> it.lilac; Category.VIOLET -> it.clay } }
@Composable fun categoryTint(f: Category): Color = MP.colors.let { when (f) { Category.BLUE -> it.amberTint; Category.TEAL -> it.tealTint; Category.INDIGO -> it.lilacTint; Category.VIOLET -> it.clayTint } }
fun categoryGradient(f: Category): MPGradient = when (f) { Category.BLUE -> MPGradient.AMBER; Category.TEAL -> MPGradient.SAGE; Category.INDIGO -> MPGradient.LILAC; Category.VIOLET -> MPGradient.CLAY }

// --- Grain and gradients -----------------------------------------------------------------

/** The site's grain, soft-light over whatever this draws on. */
@Composable
fun Modifier.grain(alpha: Float = 0.45f, soft: Boolean = false): Modifier {
    val bitmap = androidx.compose.ui.graphics.ImageBitmap.imageResource(if (soft) R.drawable.grain_soft else R.drawable.grain)
    val density = androidx.compose.ui.platform.LocalDensity.current.density
    val brush = remember(bitmap, density) {
        object : ShaderBrush() {
            override fun createShader(size: androidx.compose.ui.geometry.Size): androidx.compose.ui.graphics.Shader =
                ImageShader(bitmap, TileMode.Repeated, TileMode.Repeated).apply {
                    setLocalMatrix(android.graphics.Matrix().apply { setScale(density / 2f, density / 2f) })
                }
        }
    }
    // Wraps whatever is drawn AFTER it in the chain, so put it before the fill it should texture.
    return this.graphicsLayer(compositingStrategy = CompositingStrategy.Offscreen).drawWithContent {
        drawContent()
        if (soft) drawRect(brush, alpha = 0.6f) else drawRect(brush, alpha = alpha, blendMode = BlendMode.Softlight)
    }
}

/** A grainy earthy gradient (the 175° run with the warm glow pooling at the bottom), as a background. */
@Composable
fun Modifier.gradientFill(g: MPGradient, shape: Shape): Modifier = this
    .clip(shape)
    .grain()
    .drawBehind {
        drawRect(Brush.linearGradient(colorStops = g.stops.toTypedArray(),
            start = Offset(size.width * 0.54f, 0f), end = Offset(size.width * 0.46f, size.height)))
        g.glow?.let { (color, at) ->
            drawRect(Brush.radialGradient(listOf(color, color.copy(alpha = 0f)),
                center = Offset(size.width * at.first, size.height * at.second),
                radius = maxOf(size.width, size.height) * 0.55f))
        }
    }

// --- Glass -------------------------------------------------------------------------------

/** The white glass surface: gradient fill, light-catching rim, and the layered shadow. */
@Composable
fun Modifier.glassSurface(shape: Shape = SurfaceShape, solid: Boolean = false, elevated: Boolean = true, tint: Boolean = false): Modifier {
    val c = MP.colors
    val lift = if (!elevated) 0.dp else if (c.isDark) 12.dp else 10.dp
    val shadowAlpha = if (c.isDark) 0.5f else 0.16f
    return this
        .then(if (elevated) Modifier.shadow(lift, shape, clip = false, ambientColor = c.shadow.copy(alpha = shadowAlpha * 0.6f), spotColor = c.shadow.copy(alpha = shadowAlpha)) else Modifier)
        .border(0.5.dp, c.glassRing, shape)
        .background(Brush.linearGradient(listOf(if (solid) c.glassSolidTop else c.glassTop, if (solid) c.glassSolidBottom else c.glassBottom)), shape)
        .then(if (tint) Modifier.background(Brush.linearGradient(listOf(c.fogLilac.copy(alpha = if (c.isDark) .8f else .45f), c.fogAmber.copy(alpha = if (c.isDark) .6f else .32f))), shape) else Modifier)
        .border(1.dp, c.glassRim, shape)
}

/** The press response every card and button shares: a 0.97 scale on the site's spring. */
@Composable
fun Modifier.pressScale(interaction: MutableInteractionSource, enabled: Boolean = true): Modifier {
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed && enabled) 0.97f else 1f, spring(dampingRatio = 0.68f, stiffness = 600f), label = "press")
    return graphicsLayer { scaleX = scale; scaleY = scale }
}

/** A card: the glass surface at 26pt. `tint` is the briefing wash (lilac into amber) for a narrative card. */
@Composable
fun Panel(modifier: Modifier = Modifier, padding: Dp = 16.dp, tint: Color? = null, wash: Boolean = false,
          onClick: (() -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    Column(
        modifier = modifier.fillMaxWidth()
            .then(if (onClick != null) Modifier.pressScale(interaction) else Modifier)
            .glassSurface(SurfaceShape, tint = wash)
            .then(if (tint != null) Modifier.background(tint, SurfaceShape) else Modifier)
            .clip(SurfaceShape)
            .then(if (onClick != null) Modifier.clickable(interactionSource = interaction, indication = null, onClick = onClick) else Modifier)
            .padding(padding),
        content = content,
    )
}

// --- Titles ------------------------------------------------------------------------------

/** A header row inside a card: 15/500 ink, a muted note, a trailing text action. Pairs with `Panel(padding = 0)`. */
@Composable
fun CardTitleRow(title: String, note: String? = null, actionTitle: String? = null, onAction: (() -> Unit)? = null) {
    val c = MP.colors
    Row(Modifier.fillMaxWidth().heightIn(min = 40.dp).padding(horizontal = 16.dp).padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(title, style = MPType.cardTitle, color = c.ink)
        if (note != null) { Spacer(Modifier.width(10.dp)); Text(note, style = MPType.label, color = c.muted, maxLines = 1) }
        Spacer(Modifier.weight(1f))
        if (actionTitle != null && onAction != null) PlainButton(actionTitle, bare = true, onClick = onAction)
    }
}

/** A title inside a card that keeps its own padding (older screens): 15/500 ink with an optional trailing action. */
@Composable
fun SectionTitle(text: String, action: (@Composable () -> Unit)? = null, modifier: Modifier = Modifier, note: String? = null) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(text, style = MPType.cardTitle, color = MP.colors.ink)
        if (note != null) { Spacer(Modifier.width(10.dp)); Text(note, style = MPType.label, color = MP.colors.muted, maxLines = 1) }
        Spacer(Modifier.weight(1f))
        action?.invoke()
    }
}

/** A section title on the canvas: 20/500 ink, an optional note in the same line. */
@Composable
fun SectionHeading(text: String, note: String? = null, modifier: Modifier = Modifier, action: (@Composable () -> Unit)? = null) {
    Row(modifier.fillMaxWidth().padding(horizontal = 4.dp), verticalAlignment = Alignment.Bottom) {
        Text(text, style = MPType.subheadMedium, color = MP.colors.ink)
        if (note != null) { Spacer(Modifier.width(10.dp)); Text(note, style = MPType.copy, color = MP.colors.muted, maxLines = 1, modifier = Modifier.padding(bottom = 2.dp)) }
        Spacer(Modifier.weight(1f))
        action?.invoke()
    }
}

@Composable
fun Eyebrow(text: String, modifier: Modifier = Modifier) {
    Text(text.uppercase(), style = MPType.labelMedium.copy(letterSpacing = 0.6.sp), color = MP.colors.muted, modifier = modifier)
}

// --- Buttons -----------------------------------------------------------------------------

/** The site's lime accent dot with its halo. */
@Composable
fun LimeDot(size: Dp = 8.dp) {
    val lime = MP.colors.lime
    Box(Modifier.size(size * 1.9f), contentAlignment = Alignment.Center) {
        Box(Modifier.size(size * 1.9f).clip(CircleShape).background(lime.copy(alpha = .35f)))
        Box(Modifier.size(size).clip(CircleShape).background(lime))
    }
}

private enum class ButtonKind { FILLED, GRAY, TINTED, DESTRUCTIVE }

@Composable
private fun CapsuleButton(kind: ButtonKind, enabled: Boolean, loading: Boolean, modifier: Modifier, onClick: () -> Unit,
                          content: @Composable RowScope.() -> Unit) {
    val c = MP.colors
    val interaction = remember { MutableInteractionSource() }
    val label = when { !enabled -> c.muted; kind == ButtonKind.FILLED -> c.onAction; kind == ButtonKind.DESTRUCTIVE -> c.riskHigh; else -> c.ink }
    val base = modifier.fillMaxWidth().defaultMinSize(minHeight = 52.dp).pressScale(interaction, enabled)
    val styled = when {
        !enabled -> base.background(c.soft, CapsuleShape)
        kind == ButtonKind.FILLED -> base
            .shadow(9.dp, CapsuleShape, clip = false, ambientColor = c.shadow.copy(alpha = if (c.isDark) .5f else .22f), spotColor = c.shadow.copy(alpha = if (c.isDark) .5f else .3f))
            .clip(CapsuleShape)
            .drawBehind {
                drawRect(Brush.radialGradient(listOf(c.actionTop, c.action), center = Offset(size.width * 0.3f, 0f), radius = 140.dp.toPx()))
                drawRoundRect(Brush.verticalGradient(listOf(Color.White.copy(alpha = if (c.isDark) .9f else .24f), Color.Transparent), endY = size.height / 2),
                    cornerRadius = CornerRadius(size.height / 2), style = Stroke(1.dp.toPx()))
            }
        kind == ButtonKind.GRAY -> base.glassSurface(CapsuleShape, solid = true)
        kind == ButtonKind.DESTRUCTIVE -> base.background(c.riskHighBg, CapsuleShape)
        else -> base.background(c.fill, CapsuleShape)
    }
    Row(
        styled.clip(CapsuleShape).clickable(interactionSource = interaction, indication = null, enabled = enabled && !loading, onClick = onClick)
            .padding(horizontal = 24.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically,
    ) {
        if (loading) CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp, color = label)
        else androidx.compose.runtime.CompositionLocalProvider(androidx.compose.material3.LocalContentColor provides label) { content() }
    }
}

/** The one full-width commit button: the near-black capsule with the lime dot, 52pt. */
@Composable
fun PrimaryButton(title: String, modifier: Modifier = Modifier, enabled: Boolean = true, loading: Boolean = false,
                  icon: ImageVector? = null, onClick: () -> Unit) {
    CapsuleButton(ButtonKind.FILLED, enabled, loading, modifier, onClick) {
        if (enabled) {
            if (icon != null) Icon(icon, null, modifier = Modifier.size(18.dp)) else LimeDot(7.dp)
            Spacer(Modifier.width(10.dp))
        }
        Text(title, style = MPType.copyLargeMedium, textAlign = TextAlign.Center)
    }
}

/** The quieter full-width button: the white glass capsule, 52pt. */
@Composable
fun SecondaryButton(title: String, modifier: Modifier = Modifier, enabled: Boolean = true, loading: Boolean = false,
                    icon: ImageVector? = null, onClick: () -> Unit) {
    CapsuleButton(ButtonKind.GRAY, enabled, loading, modifier, onClick) {
        if (icon != null) { Icon(icon, null, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(8.dp)) }
        Text(title, style = MPType.copyLargeMedium, textAlign = TextAlign.Center)
    }
}

/** The warm grey capsule for a secondary action beside a primary one. */
@Composable
fun TintedButton(title: String, modifier: Modifier = Modifier, enabled: Boolean = true, loading: Boolean = false, onClick: () -> Unit) {
    CapsuleButton(ButtonKind.TINTED, enabled, loading, modifier, onClick) { Text(title, style = MPType.copyLargeMedium, textAlign = TextAlign.Center) }
}

@Composable
fun DestructiveButton(title: String, modifier: Modifier = Modifier, loading: Boolean = false, onClick: () -> Unit) {
    CapsuleButton(ButtonKind.DESTRUCTIVE, true, loading, modifier, onClick) { Text(title, style = MPType.copyLargeMedium, textAlign = TextAlign.Center) }
}

/** No fill, sage label. `bare` drops the inset so it aligns with surrounding text. */
@Composable
fun PlainButton(title: String, modifier: Modifier = Modifier, color: Color? = null, bare: Boolean = false, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    Text(
        title, style = MPType.copyLargeMedium, color = color ?: MP.colors.brandInk,
        modifier = modifier.clip(CapsuleShape)
            .background(if (pressed && !bare) MP.colors.fill else Color.Transparent)
            .clickable(interactionSource = interaction, indication = null, onClick = onClick)
            .graphicsLayer { alpha = if (pressed && bare) 0.6f else 1f }
            .padding(horizontal = if (bare) 0.dp else 14.dp, vertical = 10.dp),
    )
}

/** The patient's own words: the sage bubble gradient. */
val BubbleBrush = Brush.verticalGradient(listOf(Color(0xFF5E7D4E), Color(0xFF445F39)))

/** A quick reply: a white capsule with a ring; picked, the sage bubble with a check. 48pt. */
@Composable
fun Chip(label: String, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val c = MP.colors
    val interaction = remember { MutableInteractionSource() }
    val base = modifier.defaultMinSize(minHeight = 48.dp).pressScale(interaction)
    val styled = if (selected) base
        .shadow(8.dp, CapsuleShape, clip = false, ambientColor = Color(0xFF4A663E).copy(alpha = .3f), spotColor = Color(0xFF4A663E).copy(alpha = .45f))
        .clip(CapsuleShape).grain().background(BubbleBrush)
    else base
        .shadow(if (c.isDark) 0.dp else 6.dp, CapsuleShape, clip = false, ambientColor = c.shadow.copy(alpha = .08f), spotColor = c.shadow.copy(alpha = .12f))
        .background(if (c.isDark) c.fill else c.panel, CapsuleShape)
        .border(1.dp, c.lineStrong.copy(alpha = .6f), CapsuleShape)
    Row(
        styled.clip(CapsuleShape).clickable(interactionSource = interaction, indication = null, onClick = onClick).padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center,
    ) {
        if (selected) { Icon(Icons.Default.Check, null, tint = Color.White, modifier = Modifier.size(15.dp)); Spacer(Modifier.width(6.dp)) }
        Text(label, style = MPType.copyLargeMedium, color = if (selected) Color.White else c.ink)
    }
}

@Composable
fun FlowChips(labels: List<String>, selected: Int, onSelect: (Int) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        labels.forEachIndexed { i, l -> Chip(l, selected = i == selected) { onSelect(i) } }
    }
}

// --- State -------------------------------------------------------------------------------

enum class Tone { LOW, MED, HIGH, MISSING, BRAND }

fun toneFor(state: String?): Tone = when (state) {
    "good", "ok", "low", "connected" -> Tone.LOW
    "watch", "medium", "med" -> Tone.MED
    "reviewing", "flag", "high", "error" -> Tone.HIGH
    else -> Tone.MISSING
}

@Composable fun toneInk(tone: Tone): Color = MP.colors.let { when (tone) { Tone.LOW -> it.riskLow; Tone.MED -> it.riskMed; Tone.HIGH -> it.riskHigh; Tone.MISSING -> it.riskMissing; Tone.BRAND -> it.brandInk } }
@Composable fun toneTint(tone: Tone): Color = MP.colors.let { when (tone) { Tone.LOW -> it.riskLowBg; Tone.MED -> it.riskMedBg; Tone.HIGH -> it.riskHighBg; Tone.MISSING -> it.riskMissingBg; Tone.BRAND -> it.brandTint } }

@Composable
private fun ToneDot(tone: Tone) {
    val ink = toneInk(tone)
    Box(Modifier.size(6.dp).clip(CircleShape).let { if (tone == Tone.MISSING) it.border(1.5.dp, ink, CircleShape) else it.background(ink) })
}

/** A state pill: a capsule on the tone's tint, a dot and the word. 12/500. */
@Composable
fun StatusPill(text: String, tone: Tone, modifier: Modifier = Modifier) {
    Row(modifier.clip(CapsuleShape).background(toneTint(tone)).padding(horizontal = 10.dp, vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
        ToneDot(tone); Spacer(Modifier.width(5.dp))
        Text(text, style = MPType.labelMedium, color = toneInk(tone), maxLines = 1)
    }
}

/** A state as a dot and a word, no fill: for a row. The pill is for a hero. */
@Composable
fun StateLabel(text: String, tone: Tone, modifier: Modifier = Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        ToneDot(tone); Spacer(Modifier.width(5.dp))
        Text(text, style = MPType.label, color = toneInk(tone), maxLines = 1)
    }
}

@Composable
fun ErrorBanner(text: String, modifier: Modifier = Modifier, onDismiss: (() -> Unit)? = null) {
    val c = MP.colors
    Row(
        modifier = modifier.fillMaxWidth().clip(ControlShape).background(c.riskMedBg)
            .let { if (onDismiss != null) it.clickable(onClick = onDismiss) else it }.padding(12.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Icon(Icons.Default.Warning, null, tint = c.riskMed, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(8.dp))
        Text(text, style = MPType.copyMedium, color = c.ink)
    }
}

// --- Glyphs, tiles, avatars --------------------------------------------------------------

/** A category glyph: an icon in the category's ink on its tint disc. Rows start with one. */
@Composable
fun Glyph(icon: ImageVector, family: Category = Category.TEAL, size: Dp = 32.dp) {
    Box(Modifier.size(size).clip(CircleShape).background(categoryTint(family)), contentAlignment = Alignment.Center) {
        Icon(icon, null, tint = categoryInk(family), modifier = Modifier.size(size * 0.5f))
    }
}

/** The site's gradient glyph square: a white icon on a grainy gradient with an inner highlight. */
@Composable
fun IconTile(icon: ImageVector, family: Category = Category.BLUE, size: Dp = 30.dp) {
    val c = MP.colors
    val shape = RoundedCornerShape(size * 0.3f)
    Box(
        Modifier.size(size)
            .shadow(5.dp, shape, clip = false, ambientColor = c.shadow.copy(alpha = .15f), spotColor = c.shadow.copy(alpha = .22f))
            .gradientFill(categoryGradient(family), shape)
            .border(1.dp, Brush.verticalGradient(listOf(Color.White.copy(alpha = .35f), Color.Transparent)), shape),
        contentAlignment = Alignment.Center,
    ) { Icon(icon, null, tint = Color.White, modifier = Modifier.size(size * 16 / 30)) }
}

private val initialTones = listOf(
    Color(0xFFC08462) to Color(0xFF8A5942), Color(0xFF8797BB) to Color(0xFF525F86), Color(0xFFC9A44C) to Color(0xFF8F6F1F),
    Color(0xFF88A86E) to Color(0xFF4A673E), Color(0xFF9D93CB) to Color(0xFF6468A8),
)

/** "Dr. Priya Shah" -> "PS": honorifics end in a period. */
fun initialsOf(name: String): String {
    val words = name.split(" ").filter { it.isNotBlank() && !it.endsWith(".") }
    val letters = listOfNotNull(words.firstOrNull()?.first(), if (words.size > 1) words.last().first() else null)
    return letters.joinToString("").uppercase().ifBlank { name.take(2).uppercase() }
}

/** An avatar disc: the grainy gradient with white initials, its tone picked from the text; `soft` keeps a tint with its ink. */
@Composable
fun Initials(text: String, size: Dp = 40.dp, tone: Tone = Tone.BRAND, soft: Boolean = false) {
    val c = MP.colors
    val shown = if (text.length > 2) initialsOf(text) else text.uppercase()
    val style = TextStyle(fontFamily = Outfit, fontSize = (size.value * 0.36f).sp, fontWeight = androidx.compose.ui.text.font.FontWeight.W500)
    if (soft && tone != Tone.BRAND && tone != Tone.HIGH) {
        Box(Modifier.size(size).clip(CircleShape).background(toneTint(tone)), contentAlignment = Alignment.Center) {
            Text(shown, style = style, color = toneInk(tone), maxLines = 1)
        }
        return
    }
    val pair = if (tone == Tone.HIGH) Color(0xFFC9795A) to Color(0xFF9A4A2E)
        else initialTones[(text.fold(0) { h, ch -> (h * 31 + ch.code) and 0xFFFF }) % initialTones.size]
    Box(
        Modifier.size(size)
            .shadow(3.dp, CircleShape, clip = false, ambientColor = c.shadow.copy(alpha = .15f), spotColor = c.shadow.copy(alpha = .25f))
            .clip(CircleShape).grain().background(Brush.linearGradient(listOf(pair.first, pair.second)))
            .border(1.dp, Brush.verticalGradient(listOf(Color.White.copy(alpha = .3f), Color.Transparent)), CircleShape),
        contentAlignment = Alignment.Center,
    ) { Text(shown, style = style, color = Color.White, maxLines = 1) }
}

/** The MedPull mark on its white tile beside the wordmark. */
@Composable
fun Lockup(badge: String? = null) {
    val c = MP.colors
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier.size(30.dp).shadow(1.dp, RoundedCornerShape(9.dp), clip = false, ambientColor = Color.Black.copy(alpha = .08f), spotColor = Color.Black.copy(alpha = .12f))
                .background(Color.White, RoundedCornerShape(9.dp)).border(0.5.dp, Color.Black.copy(alpha = .08f), RoundedCornerShape(9.dp)),
            contentAlignment = Alignment.Center,
        ) { androidx.compose.foundation.Image(painterResource(R.drawable.medpull_mark), null, modifier = Modifier.size(21.dp)) }
        Spacer(Modifier.width(9.dp))
        Text("MedPull", style = TextStyle(fontFamily = Outfit, fontSize = 19.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.W500, letterSpacing = (-0.5).sp), color = c.ink)
        if (badge != null) {
            Spacer(Modifier.width(6.dp))
            Text(badge, style = MPType.labelMedium, color = c.brandInk, modifier = Modifier.clip(CapsuleShape).background(c.brandTint).padding(horizontal = 8.dp, vertical = 3.dp))
        }
    }
}

// --- Gradient tile -----------------------------------------------------------------------

/**
 * The site's signature card: a grainy gradient, white type in the dark top
 * band (kicker, big light number, a side note), white line art in the
 * middle, and an ink caption on solid glass at the bottom.
 */
@Composable
fun GradientTile(kicker: String, value: String?, unit: String? = null, side: Pair<String, String>? = null,
                 gradient: MPGradient = MPGradient.SAGE, valueSize: Int = 44, modifier: Modifier = Modifier,
                 onClick: (() -> Unit)? = null, art: (@Composable () -> Unit)? = null,
                 caption: (@Composable ColumnScope.() -> Unit)? = null) {
    val c = MP.colors
    val interaction = remember { MutableInteractionSource() }
    val scrim = Color(0xFF18160E)
    Column(
        modifier.fillMaxWidth()
            .then(if (onClick != null) Modifier.pressScale(interaction) else Modifier)
            .shadow(14.dp, SurfaceShape, clip = false, ambientColor = c.shadow.copy(alpha = .18f), spotColor = c.shadow.copy(alpha = .3f))
            .gradientFill(gradient, SurfaceShape)
            .drawBehind {
                drawRect(Brush.verticalGradient(0f to scrim.copy(alpha = .3f), 0.34f to scrim.copy(alpha = .1f), 0.55f to Color.Transparent))
            }
            .border(0.5.dp, Color.White.copy(alpha = .14f), SurfaceShape)
            .then(if (onClick != null) Modifier.clickable(interactionSource = interaction, indication = null, onClick = onClick) else Modifier),
    ) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp).padding(top = 16.dp), verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Text(kicker, style = MPType.labelMedium, color = Color.White)
                if (value != null) {
                    Spacer(Modifier.height(4.dp))
                    Row {
                        Text(value, style = MPType.figuresDisplay(valueSize), color = Color.White, maxLines = 1, modifier = Modifier.alignByBaseline())
                        if (!unit.isNullOrBlank()) {
                            Spacer(Modifier.width(4.dp))
                            Text(unit, style = MPType.copyMedium, color = Color.White.copy(alpha = .9f), modifier = Modifier.alignByBaseline())
                        }
                    }
                }
            }
            if (side != null) {
                Column(horizontalAlignment = Alignment.End) {
                    Text(side.first, style = MPType.subhead.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.W300), color = Color.White)
                    Text(side.second, style = MPType.label, color = Color.White.copy(alpha = .92f))
                }
            }
        }
        if (art != null) Box(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 12.dp)) { art() } else Spacer(Modifier.height(12.dp))
        if (caption != null) {
            Column(
                Modifier.padding(horizontal = 8.dp).padding(bottom = 8.dp).fillMaxWidth()
                    .glassSurface(ControlShape, solid = true, elevated = false).padding(14.dp),
                content = caption,
            )
        }
    }
}

// --- Rows --------------------------------------------------------------------------------

@Composable
fun RowScope.Weight(w: Float = 1f) = Spacer(Modifier.weight(w))

@Composable
fun Chevron() = Icon(Icons.Default.ChevronRight, null, tint = MP.colors.faint, modifier = Modifier.size(18.dp))

/**
 * A navigation row: glyph, 16/500 title, a two-line 12pt subtitle, trailing
 * content, a chevron. `inset` adds the card's 16pt side padding for use in
 * a `Panel(padding = 0)`.
 */
@Composable
fun ListRow(title: String, subtitle: String? = null, leading: (@Composable () -> Unit)? = null,
            trailing: (@Composable () -> Unit)? = null, onClick: (() -> Unit)? = null,
            icon: ImageVector? = null, family: Category = Category.TEAL, chevron: Boolean = onClick != null,
            inset: Boolean = false, titleColor: Color? = null) {
    val c = MP.colors
    Row(
        Modifier.fillMaxWidth().let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(horizontal = if (inset) 16.dp else 0.dp, vertical = 11.dp).heightIn(min = 30.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) { Glyph(icon, family); Spacer(Modifier.width(12.dp)) }
        else if (leading != null) { leading(); Spacer(Modifier.width(12.dp)) }
        Column(Modifier.weight(1f)) {
            Text(title, style = MPType.copyLargeMedium, color = titleColor ?: c.ink, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (!subtitle.isNullOrBlank()) Text(subtitle, style = MPType.label, color = c.muted, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        if (trailing != null) { Spacer(Modifier.width(8.dp)); trailing() }
        if (chevron) { Spacer(Modifier.width(6.dp)); Chevron() }
    }
}

/** A full-width hairline. */
@Composable
fun Hairline() = Box(Modifier.fillMaxWidth().height(1.dp).background(MP.colors.hairline))

/** An inset hairline between rows in a card, aligned to the row text. */
@Composable
fun InsetDivider(leading: Dp = 16.dp, trailing: Dp = 16.dp) =
    Box(Modifier.fillMaxWidth().padding(start = leading, end = trailing).height(0.75.dp).background(MP.colors.hairline))

/** The divider between two rows that start with a 32pt glyph. */
@Composable
fun RowDivider(glyph: Boolean = true) = InsetDivider(if (glyph) 60.dp else 16.dp)

/** The in-card empty state: a quiet gradient glyph and one line of ink. */
@Composable
fun EmptyRow(icon: ImageVector, title: String, detail: String? = null) {
    val c = MP.colors
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        IconTile(icon, Category.TEAL, 40.dp)
        Spacer(Modifier.height(10.dp))
        Text(title, style = MPType.copyLargeMedium, color = c.ink, textAlign = TextAlign.Center)
        if (detail != null) { Spacer(Modifier.height(4.dp)); Text(detail, style = MPType.copy, color = c.muted, textAlign = TextAlign.Center) }
    }
}

/** A figure with its unit, for a row's trailing edge: 16/500 figures and a 12pt unit. */
@Composable
fun RowFigure(value: String, unit: String? = null) {
    Row { Text(value, style = MPType.figuresCopyLarge, color = MP.colors.ink, modifier = Modifier.alignByBaseline())
        if (!unit.isNullOrBlank()) { Spacer(Modifier.width(3.dp)); Text(unit, style = MPType.label, color = MP.colors.muted, modifier = Modifier.alignByBaseline()) } }
}

/** A big figure for a detail screen: the display face, light, the unit beside it. */
@Composable
fun BigFigure(value: String, unit: String? = null, size: Int = 44) {
    Row { Text(value, style = MPType.figuresDisplay(size), color = MP.colors.ink, maxLines = 1, modifier = Modifier.alignByBaseline())
        if (!unit.isNullOrBlank()) { Spacer(Modifier.width(6.dp)); Text(unit, style = MPType.copyMedium, color = MP.colors.muted, modifier = Modifier.alignByBaseline()) } }
}

// --- Misc --------------------------------------------------------------------------------

@Composable
fun Spinner(modifier: Modifier = Modifier) = Box(modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
    CircularProgressIndicator(color = MP.colors.brandInk, strokeWidth = 2.dp)
}

@Composable
fun Guardrail(modifier: Modifier = Modifier) = Text(
    "Monitoring signals for your care team — not a diagnosis.",
    style = MPType.label, color = MP.colors.muted, modifier = modifier.padding(top = 2.dp),
)

@Composable
fun Gap(h: Dp = 12.dp) = Spacer(Modifier.height(h))

/** The back bar every pushed screen uses: the arrow and the title. */
@Composable
fun BackBar(nav: NavHostController, title: String) {
    Row(Modifier.fillMaxWidth().height(52.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = MP.colors.ink) }
        Text(title, style = MPType.ledeMedium, color = MP.colors.ink)
    }
}

/** A small labelled figure, for a row of results. */
@Composable
fun Stat(label: String, value: String) {
    Column { Text(label, style = MPType.label, color = MP.colors.muted); Text(value, style = MPType.figuresLede, color = MP.colors.ink) }
}

/** A text field, the site's form control: a light fill, 14pt corners and a `lineStrong` ring. */
@Composable
fun Field(value: String, onChange: (String) -> Unit, label: String, keyboard: KeyboardType = KeyboardType.Text,
          password: Boolean = false, modifier: Modifier = Modifier, singleLine: Boolean = true) {
    val c = MP.colors
    OutlinedTextField(
        value = value, onValueChange = onChange, placeholder = { Text(label, style = MPType.copyLarge, color = c.muted) }, singleLine = singleLine,
        modifier = modifier.fillMaxWidth().heightIn(min = 52.dp), textStyle = MPType.copyLarge,
        keyboardOptions = KeyboardOptions(keyboardType = keyboard),
        visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
        shape = ThumbShape,
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = c.brand, unfocusedBorderColor = c.lineStrong.copy(alpha = .75f),
            focusedContainerColor = c.panel.copy(alpha = .8f), unfocusedContainerColor = c.panel.copy(alpha = .8f),
            focusedTextColor = c.ink, unfocusedTextColor = c.ink, cursorColor = c.brand,
        ),
    )
}

// --- Screen backgrounds ------------------------------------------------------------------

/**
 * The site's canvas: warm white with soft colour fog at the top, a faint dot
 * grid, and grain. Static; the drift the iPhone animates is left out.
 */
@Composable
fun FogBackground(height: Dp = 520.dp, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val c = MP.colors
    Box(modifier.fillMaxSize().background(c.canvas)) {
        Canvas(Modifier.fillMaxWidth().height(height).graphicsLayer(compositingStrategy = CompositingStrategy.Offscreen)) {
            val w = size.width; val h = size.height
            fun blob(color: Color, d: Float, x: Float, y: Float) =
                drawCircle(Brush.radialGradient(listOf(color, color.copy(alpha = 0f)), center = Offset(x, y), radius = d / 2), radius = d / 2, center = Offset(x, y))
            blob(c.fogSage, w * 1.0f, w * 0.78f, h * 0.12f)
            blob(c.fogAmber, w * 0.8f, w * 1.02f, h * 0.52f)
            blob(c.fogClay, w * 0.75f, w * 0.42f, h * 0.78f)
            blob(c.fogLilac, w * 0.8f, w * 0.02f, h * 0.08f)
            blob(c.fogMint, w * 0.6f, w * -0.05f, h * 0.7f)
            val step = 22.dp.toPx(); val dot = c.ink.copy(alpha = .06f)
            var y = step / 2
            while (y < h * 0.7f) { var x = step / 2; while (x < w) { drawCircle(dot, 0.75.dp.toPx(), Offset(x, y)); x += step }; y += step }
            drawRect(Brush.verticalGradient(0f to Color.Black, 0.62f to Color.Black, 1f to Color.Transparent), blendMode = BlendMode.DstIn)
        }
        Box(Modifier.fillMaxSize().grain(soft = true)) {}
        content()
    }
}

@Composable
fun painter(id: Int): Painter = painterResource(id)
