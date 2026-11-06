package com.medpull.recovery.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** The iPhone's radii: surface 26, control 18, thumb 14, tile 9. */
object Radii {
    val surface = 26.dp; val control = 18.dp; val thumb = 14.dp; val tile = 9.dp
}

@Composable
fun Panel(modifier: Modifier = Modifier, padding: Dp = 16.dp, tint: Color? = null,
          onClick: (() -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) {
    val c = MP.colors
    Surface(
        modifier = modifier.fillMaxWidth().let { if (onClick != null) it.clickable(onClick = onClick) else it },
        shape = RoundedCornerShape(Radii.surface),
        color = tint ?: c.panel,
        border = BorderStroke(1.dp, c.hairline),
    ) {
        Column(modifier = Modifier.padding(padding), content = content)
    }
}

@Composable
fun SectionTitle(text: String, action: (@Composable () -> Unit)? = null, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(text, style = MaterialTheme.typography.titleMedium, color = MP.colors.ink, modifier = Modifier.weight(1f))
        action?.invoke()
    }
}

@Composable
fun Eyebrow(text: String, modifier: Modifier = Modifier) {
    Text(text.uppercase(), style = MaterialTheme.typography.labelSmall, color = MP.colors.muted, modifier = modifier)
}

@Composable
fun PrimaryButton(title: String, modifier: Modifier = Modifier, enabled: Boolean = true, loading: Boolean = false,
                  icon: ImageVector? = null, onClick: () -> Unit) {
    val c = MP.colors
    Button(
        onClick = onClick, enabled = enabled && !loading,
        modifier = modifier.fillMaxWidth().defaultMinSize(minHeight = 52.dp),
        shape = RoundedCornerShape(Radii.control),
        colors = ButtonDefaults.buttonColors(containerColor = c.ink, contentColor = c.canvas,
            disabledContainerColor = c.soft, disabledContentColor = c.muted),
    ) {
        if (loading) CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp, color = c.canvas)
        else {
            if (icon != null) { Icon(icon, null, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(8.dp)) }
            else { Box(Modifier.size(8.dp).clip(CircleShape).background(c.lime)); Spacer(Modifier.width(10.dp)) }
            Text(title, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
fun SecondaryButton(title: String, modifier: Modifier = Modifier, enabled: Boolean = true, loading: Boolean = false,
                    icon: ImageVector? = null, onClick: () -> Unit) {
    val c = MP.colors
    Button(
        onClick = onClick, enabled = enabled && !loading,
        modifier = modifier.fillMaxWidth().defaultMinSize(minHeight = 52.dp),
        shape = RoundedCornerShape(Radii.control),
        colors = ButtonDefaults.buttonColors(containerColor = c.soft, contentColor = c.ink,
            disabledContainerColor = c.soft, disabledContentColor = c.muted),
    ) {
        if (loading) CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp, color = c.ink)
        else {
            if (icon != null) { Icon(icon, null, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(8.dp)) }
            Text(title, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
fun PlainButton(title: String, modifier: Modifier = Modifier, color: Color? = null, onClick: () -> Unit) {
    Text(
        title, style = MaterialTheme.typography.labelLarge, color = color ?: MP.colors.brandInk,
        modifier = modifier.clip(RoundedCornerShape(Radii.thumb)).clickable(onClick = onClick).padding(horizontal = 12.dp, vertical = 10.dp),
    )
}

@Composable
fun Chip(label: String, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val c = MP.colors
    Surface(
        modifier = modifier.defaultMinSize(minHeight = 48.dp).clip(RoundedCornerShape(Radii.control)).clickable(onClick = onClick),
        shape = RoundedCornerShape(Radii.control),
        color = if (selected) c.brand else c.soft,
        border = if (selected) null else BorderStroke(1.dp, c.line),
    ) {
        Box(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), contentAlignment = Alignment.Center) {
            Text(label, style = MaterialTheme.typography.bodyLarge, color = if (selected) c.onBrand else c.ink)
        }
    }
}

enum class Tone { LOW, MED, HIGH, MISSING, BRAND }

fun toneFor(state: String?): Tone = when (state) {
    "good", "ok", "low", "connected" -> Tone.LOW
    "watch", "medium", "med" -> Tone.MED
    "reviewing", "flag", "high", "error" -> Tone.HIGH
    else -> Tone.MISSING
}

@Composable
fun StatusPill(text: String, tone: Tone, modifier: Modifier = Modifier) {
    val c = MP.colors
    val (fg, bg) = when (tone) {
        Tone.LOW -> c.riskLow to c.riskLowBg
        Tone.MED -> c.riskMed to c.riskMedBg
        Tone.HIGH -> c.riskHigh to c.riskHighBg
        Tone.MISSING -> c.riskMissing to c.riskMissingBg
        Tone.BRAND -> c.brandInk to c.brandTint
    }
    Row(
        modifier = modifier.clip(RoundedCornerShape(999.dp)).background(bg).padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(7.dp).clip(CircleShape).let { if (tone == Tone.MISSING) it.border(1.5.dp, fg, CircleShape) else it.background(fg) })
        Spacer(Modifier.width(6.dp))
        Text(text, style = MaterialTheme.typography.labelMedium, color = fg)
    }
}

@Composable
fun ErrorBanner(text: String, modifier: Modifier = Modifier, onDismiss: (() -> Unit)? = null) {
    val c = MP.colors
    Row(
        modifier = modifier.fillMaxWidth().clip(RoundedCornerShape(Radii.control)).background(c.amberTint)
            .let { if (onDismiss != null) it.clickable(onClick = onDismiss) else it }.padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Default.Warning, null, tint = c.amber, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(10.dp))
        Text(text, style = MaterialTheme.typography.bodyMedium, color = c.ink)
    }
}

@Composable
fun Initials(text: String, size: Dp = 40.dp, tone: Tone = Tone.BRAND) {
    val c = MP.colors
    val brush = when (tone) {
        Tone.HIGH -> Brush.linearGradient(listOf(c.clay, c.riskHigh))
        Tone.MED -> Brush.linearGradient(listOf(c.amber, c.riskMed))
        Tone.MISSING -> Brush.linearGradient(listOf(c.lilac, c.riskMissing))
        else -> Brush.linearGradient(listOf(Color(0xFF5E7D4E), Color(0xFF445F39)))
    }
    Box(Modifier.size(size).clip(CircleShape).background(brush), contentAlignment = Alignment.Center) {
        Text(text.take(2).uppercase(), color = Color.White, fontWeight = FontWeight.Medium,
            fontSize = (size.value * 0.38f).sp)
    }
}

/** The hero: a gradient tile with a kicker, a large light number and a caption. */
@Composable
fun GradientTile(kicker: String, value: String, unit: String? = null, caption: String? = null,
                 modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, art: (@Composable () -> Unit)? = null) {
    Surface(
        modifier = modifier.fillMaxWidth().let { if (onClick != null) it.clickable(onClick = onClick) else it },
        shape = RoundedCornerShape(Radii.surface), color = Color.Transparent,
    ) {
        Column(
            Modifier.background(Brush.linearGradient(listOf(Color(0xFF5E7D4E), Color(0xFF3F5F33)))).padding(20.dp),
        ) {
            Text(kicker.uppercase(), style = MaterialTheme.typography.labelSmall, color = Color.White.copy(alpha = .8f))
            Row(verticalAlignment = Alignment.Bottom) {
                Text(value, style = MaterialTheme.typography.displayMedium, color = Color.White)
                if (unit != null) {
                    Spacer(Modifier.width(6.dp))
                    Text(unit, style = MaterialTheme.typography.titleMedium, color = Color.White.copy(alpha = .85f),
                        modifier = Modifier.padding(bottom = 6.dp))
                }
            }
            if (art != null) { Spacer(Modifier.height(10.dp)); art() }
            if (caption != null) {
                Spacer(Modifier.height(10.dp))
                Text(caption, style = MaterialTheme.typography.bodyMedium, color = Color.White.copy(alpha = .9f))
            }
        }
    }
}

@Composable
fun RowScope.Weight(w: Float = 1f) = Spacer(Modifier.weight(w))

@Composable
fun ListRow(title: String, subtitle: String? = null, leading: (@Composable () -> Unit)? = null,
            trailing: (@Composable () -> Unit)? = null, onClick: (() -> Unit)? = null) {
    val c = MP.colors
    Row(
        Modifier.fillMaxWidth().let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (leading != null) { leading(); Spacer(Modifier.width(12.dp)) }
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge, color = c.ink, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (!subtitle.isNullOrBlank()) Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = c.muted,
                maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        if (trailing != null) { Spacer(Modifier.width(12.dp)); trailing() }
    }
}

@Composable
fun Hairline() = Box(Modifier.fillMaxWidth().height(1.dp).background(MP.colors.hairline))

@Composable
fun Spinner(modifier: Modifier = Modifier) = Box(modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
    CircularProgressIndicator(color = MP.colors.brand, strokeWidth = 2.dp)
}

@Composable
fun Guardrail(modifier: Modifier = Modifier) = Text(
    "Monitoring signals for clinician review, not a diagnosis.",
    style = MaterialTheme.typography.labelMedium, color = MP.colors.muted, modifier = modifier.padding(vertical = 8.dp),
)

@Composable
fun Gap(h: Dp = 12.dp) = Spacer(Modifier.height(h))
