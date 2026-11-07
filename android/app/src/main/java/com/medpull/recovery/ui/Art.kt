package com.medpull.recovery.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlin.math.pow
import kotlin.math.sqrt

/**
 * White line art for gradient tiles, the medpull.org vocabulary: a smooth
 * curve, a dashed reference, faint rules, and a lime marker on the newest
 * point. Decorative; the tile's number and caption carry the reading.
 */

/** A monotone cubic through unit points (Fritsch–Carlson): smooth, never overshooting. */
fun DrawScope.smoothLine(points: List<Offset>): Path {
    val path = Path()
    if (points.size < 2) return path
    val p = points.map { Offset(it.x * size.width, it.y * size.height) }
    val n = p.size
    val m = FloatArray(n - 1) { i -> (p[i + 1].y - p[i].y) / maxOf(p[i + 1].x - p[i].x, 0.0001f) }
    val t = FloatArray(n)
    t[0] = m[0]; t[n - 1] = m[n - 2]
    for (i in 1 until n - 1) t[i] = if (m[i - 1] * m[i] <= 0) 0f else (m[i - 1] + m[i]) / 2
    for (i in 0 until n - 1) if (m[i] != 0f) {
        val a = t[i] / m[i]; val b = t[i + 1] / m[i]; val s = a * a + b * b
        if (s > 9) { val k = 3 / sqrt(s); t[i] = k * a * m[i]; t[i + 1] = k * b * m[i] }
    }
    path.moveTo(p[0].x, p[0].y)
    for (i in 0 until n - 1) {
        val h = (p[i + 1].x - p[i].x) / 3
        path.cubicTo(p[i].x + h, p[i].y + t[i] * h, p[i + 1].x - h, p[i + 1].y - t[i + 1] * h, p[i + 1].x, p[i + 1].y)
    }
    return path
}

/** Values to unit points (x 0..1, y 0..1 top-down) with headroom. */
fun unitPoints(values: List<Double>, pad: Double = 0.14): List<Offset> {
    if (values.size < 2) return emptyList()
    val lo = values.min(); val hi = values.max()
    val span = if (hi - lo == 0.0) 1.0 else hi - lo
    val low = lo - span * pad; val high = hi + span * pad
    return values.mapIndexed { i, v -> Offset(i / (values.size - 1).toFloat(), (1 - (v - low) / (high - low)).toFloat()) }
}

/** A curve tile: faint rules, an optional dashed reference, the patient's line, the lime marker at its end. */
@Composable
fun CurveArt(points: List<Offset>, reference: List<Offset>? = null, height: Dp = 120.dp, modifier: Modifier = Modifier) {
    val lime = MP.colors.lime
    Canvas(modifier.fillMaxWidth().height(height)) {
        for (i in 0 until 4) {
            val y = size.height * i / 3f
            drawLine(Color.White.copy(alpha = .22f), Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
        }
        if (reference != null && reference.size > 1) {
            drawPath(smoothLine(reference), Color.White.copy(alpha = .6f),
                style = Stroke(1.5.dp.toPx(), cap = StrokeCap.Round, pathEffect = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 6.dp.toPx()))))
        }
        if (points.size > 1) {
            drawPath(smoothLine(points), Color.White, style = Stroke(2.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
            val last = points.last()
            val at = Offset(last.x * size.width, last.y * size.height)
            drawCircle(lime.copy(alpha = .25f), 14.dp.toPx(), at)
            drawCircle(lime.copy(alpha = .35f), 8.dp.toPx(), at)
            drawCircle(lime, 6.dp.toPx(), at)
        }
    }
}

private val typicalCurve: List<Offset> = (0..8).map { i ->
    val x = i / 8f
    Offset(x, 0.9f - 0.72f * (1 - (1 - x).toDouble().pow(2.2).toFloat()))
}

/** The recovery tile's art from one number: the typical curve (dashed) and the patient's own, `pct` above or below it. */
@Composable
fun RecoveryCurveArt(pct: Double?, modifier: Modifier = Modifier) {
    if (pct != null) {
        val shift = pct.coerceIn(-40.0, 40.0).toFloat() / 100
        val patient = typicalCurve.map { p -> Offset(p.x, (p.y - shift * 0.9f * p.x.toDouble().pow(1.4).toFloat()).coerceIn(0.08f, 0.95f)) }
        CurveArt(patient, typicalCurve, modifier = modifier)
    } else CurveArt(emptyList(), typicalCurve, modifier = modifier)
}

/** White columns; the newest is outlined in lime. */
@Composable
fun BarsArt(values: List<Double>, height: Dp = 110.dp, modifier: Modifier = Modifier) {
    val lime = MP.colors.lime
    Canvas(modifier.fillMaxWidth().height(height)) {
        val shown = values.takeLast(14)
        if (shown.isEmpty()) return@Canvas
        val top = maxOf(shown.max(), 0.0001)
        val gap = 5.dp.toPx(); val w = (size.width - gap * (shown.size - 1)) / shown.size
        shown.forEachIndexed { i, v ->
            val h = (size.height * maxOf(0.05, v / top)).toFloat()
            val x = i * (w + gap); val y = size.height - h
            val last = i == shown.lastIndex
            drawRoundRect(if (last) Color.White.copy(alpha = .35f) else Color.White.copy(alpha = .9f), Offset(x, y),
                androidx.compose.ui.geometry.Size(w, h), androidx.compose.ui.geometry.CornerRadius(4.dp.toPx()))
            if (last) drawRoundRect(lime, Offset(x, y), androidx.compose.ui.geometry.Size(w, h), androidx.compose.ui.geometry.CornerRadius(4.dp.toPx()), style = Stroke(1.5.dp.toPx()))
        }
    }
}
