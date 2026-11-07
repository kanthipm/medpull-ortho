package com.medpull.recovery.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * A small series chart drawn to scale: bars for daily totals, a line with
 * points otherwise, a dashed rule at the average, and a lime marker on the
 * newest value. Values may be null for days with no reading.
 */
@Composable
fun SeriesChart(values: List<Double?>, bars: Boolean, modifier: Modifier = Modifier, height: Dp = 140.dp,
                showAverage: Boolean = true, color: Color? = null, picked: Int? = null, onPick: ((Int?) -> Unit)? = null) {
    val c = MP.colors
    val stroke = color ?: c.brand
    val present = values.filterNotNull()
    // A finger on the chart picks the nearest slot with a reading; lifting it lets go.
    val scrub = if (onPick == null) Modifier else Modifier.pointerInput(values) {
        fun slotAt(px: Float): Int? {
            val n = values.size
            if (n == 0) return null
            val i = if (bars) (px / (size.width / n)).toInt() else ((px / size.width) * (n - 1)).roundToInt()
            val near = i.coerceIn(0, n - 1)
            return (0 until n).filter { values[it] != null }.minByOrNull { abs(it - near) }
        }
        detectHorizontalDragGestures(
            onDragStart = { onPick(slotAt(it.x)) },
            onDragEnd = { onPick(null) }, onDragCancel = { onPick(null) },
        ) { change, _ -> change.consume(); onPick(slotAt(change.position.x)) }
    }
    Canvas(modifier.fillMaxWidth().height(height).then(scrub)) {
        if (present.isEmpty()) return@Canvas
        val lo = minOf(present.min(), if (bars) 0.0 else present.min())
        val hi = present.max()
        val span = (hi - lo).takeIf { it > 1e-9 } ?: 1.0
        val padTop = 8.dp.toPx(); val padBottom = 6.dp.toPx()
        val h = size.height - padTop - padBottom
        val n = values.size
        fun y(v: Double) = padTop + (1 - (v - lo) / span).toFloat() * h
        fun x(i: Int) = if (n == 1) size.width / 2 else size.width * i / (n - 1).toFloat()
        // grid
        for (k in 0..2) {
            val yy = padTop + h * k / 2f
            drawLine(c.hairline, Offset(0f, yy), Offset(size.width, yy), strokeWidth = 1f)
        }
        if (bars) {
            val slot = size.width / n
            val w = slot * 0.58f
            values.forEachIndexed { i, v ->
                if (v == null) return@forEachIndexed
                val top = y(v); val bottom = y(lo)
                val last = i == values.indexOfLast { it != null }
                drawRoundRect(if (last) stroke else stroke.copy(alpha = .55f), Offset(i * slot + (slot - w) / 2, top),
                    Size(w, (bottom - top).coerceAtLeast(2f)), cornerRadius = CornerRadius(4.dp.toPx()))
            }
        } else {
            val path = Path(); var started = false
            values.forEachIndexed { i, v ->
                if (v == null) { started = false; return@forEachIndexed }
                val p = Offset(x(i), y(v))
                if (!started) { path.moveTo(p.x, p.y); started = true } else path.lineTo(p.x, p.y)
            }
            drawPath(path, stroke, style = Stroke(width = 2.5.dp.toPx(), cap = StrokeCap.Round))
            values.forEachIndexed { i, v -> if (v != null) drawCircle(stroke, 3.dp.toPx(), Offset(x(i), y(v))) }
        }
        if (showAverage && present.size > 1) {
            val avg = present.average()
            drawLine(c.lineStrong, Offset(0f, y(avg)), Offset(size.width, y(avg)), strokeWidth = 1.5f,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 6f)))
        }
        val lastIndex = values.indexOfLast { it != null }
        if (lastIndex >= 0) {
            val v = values[lastIndex]!!
            val p = if (bars) Offset((lastIndex + 0.5f) * size.width / n, y(v) - 6.dp.toPx()) else Offset(x(lastIndex), y(v))
            drawCircle(c.lime, 5.dp.toPx(), p)
            drawCircle(stroke, 5.dp.toPx(), p, style = Stroke(1.5.dp.toPx()))
        }
        if (picked != null && picked in values.indices) values[picked]?.let { v ->
            val px = if (bars) (picked + 0.5f) * size.width / n else x(picked)
            drawLine(c.lineStrong, Offset(px, padTop), Offset(px, padTop + h), strokeWidth = 1.5f)
            drawCircle(c.ink, 5.dp.toPx(), Offset(px, y(v)))
        }
    }
}
