package com.medpull.recovery.features.progress

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.DirectionsRun
import androidx.compose.material.icons.automirrored.filled.DirectionsWalk
import androidx.compose.material.icons.automirrored.filled.ShowChart
import androidx.compose.material.icons.automirrored.filled.TrendingUp
import androidx.compose.material.icons.filled.Accessibility
import androidx.compose.material.icons.filled.Air
import androidx.compose.material.icons.filled.AltRoute
import androidx.compose.material.icons.filled.Architecture
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.Chair
import androidx.compose.material.icons.filled.Checklist
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Healing
import androidx.compose.material.icons.filled.LocalFireDepartment
import androidx.compose.material.icons.filled.MonitorHeart
import androidx.compose.material.icons.filled.Scale
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Stairs
import androidx.compose.material.icons.filled.Straighten
import androidx.compose.material.icons.filled.Thermostat
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material.icons.filled.WbTwilight
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.medpull.recovery.R
import com.medpull.recovery.core.Dates
import com.medpull.recovery.core.MetricExplain
import com.medpull.recovery.core.MetricReadiness
import com.medpull.recovery.core.PatientMetric
import com.medpull.recovery.core.PatientSignal
import com.medpull.recovery.core.PortfolioMetric
import com.medpull.recovery.core.Tab
import com.medpull.recovery.features.today.DOT
import com.medpull.recovery.ui.BackBar
import com.medpull.recovery.ui.CardTitleRow
import com.medpull.recovery.ui.Category
import com.medpull.recovery.ui.Chevron
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Glyph
import com.medpull.recovery.ui.Guardrail
import com.medpull.recovery.ui.Hairline
import com.medpull.recovery.ui.InsetDivider
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.MPType
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PlainButton
import com.medpull.recovery.ui.PrimaryButton
import com.medpull.recovery.ui.Routes
import com.medpull.recovery.ui.RowDivider
import com.medpull.recovery.ui.RowFigure
import com.medpull.recovery.ui.SecondaryButton
import com.medpull.recovery.ui.SectionHeading
import com.medpull.recovery.ui.SectionTitle
import com.medpull.recovery.ui.SeriesChart
import com.medpull.recovery.ui.Stat
import com.medpull.recovery.ui.StateLabel
import com.medpull.recovery.ui.StatusPill
import com.medpull.recovery.ui.Tone
import com.medpull.recovery.ui.appModel
import com.medpull.recovery.ui.toneFor
import java.time.LocalDate
import java.util.Locale
import kotlin.math.abs
import kotlinx.coroutines.launch

/** The signal groups the iPhone's Progress tab uses, with Apple-only keys left out. */
object Signals {
    val groups: List<Pair<Int, List<String>>> = listOf(
        R.string.signals_movement to listOf("walking_speed", "step_length", "cadence", "walking_asymmetry_pct", "double_support_pct",
            "walking_steadiness", "stair_speed_up", "stair_speed_down", "six_min_walk", "rom_flexion", "rom_extension", "rom_abduction"),
        R.string.signals_activity to listOf("steps", "exercise_session", "active_energy", "calories"),
        R.string.signals_rest to listOf("sleep_duration", "hrv_rmssd", "hrv_sdnn", "resting_hr", "stress_index", "respiratory_rate"),
        R.string.signals_body to listOf("skin_temp", "skin_temp_delta", "spo2", "pain_nrs", "body_weight", "bp_systolic", "bp_diastolic",
            "blood_glucose", "vo2_max", "hr_recovery_1min"),
    )
    val measured = setOf("walking_speed", "step_length", "cadence", "walking_asymmetry_pct", "double_support_pct",
        "walking_steadiness", "stair_speed_up", "stair_speed_down", "six_min_walk", "rom_flexion", "rom_extension", "rom_abduction")
    val dailyTotals = setOf("steps", "active_energy", "exercise_session", "calories")
}

/** 14 daily slots ending today, null where no reading. */
fun dailySlots(series: List<com.medpull.recovery.core.PortfolioPoint>, days: Int = 14): List<Double?> {
    val today = LocalDate.now()
    val byDay = series.associate { it.date.take(10) to it.value }
    return (days - 1 downTo 0).map { byDay[today.minusDays(it.toLong()).toString()] }
}

fun fmt(v: Double?, unit: String = ""): String {
    if (v == null) return "—"
    val s = if (abs(v) >= 100) String.format(Locale.getDefault(), "%,.0f", v)
    else String.format(Locale.getDefault(), "%.1f", v).trimEnd('0').trimEnd('.')
    return if (unit.isBlank()) s else "$s $unit"
}

fun signalIcon(key: String): ImageVector = when (key) {
    "steps", "walking_speed" -> Icons.AutoMirrored.Filled.DirectionsWalk
    "step_length" -> Icons.Default.Straighten
    "cadence" -> Icons.Default.Speed
    "walking_asymmetry_pct", "double_support_pct", "walking_steadiness" -> Icons.Default.Accessibility
    "stair_speed_up", "stair_speed_down" -> Icons.Default.Stairs
    "six_min_walk" -> Icons.Default.Timer
    "rom_flexion", "rom_extension", "rom_abduction" -> Icons.Default.Architecture
    "exercise_session" -> Icons.AutoMirrored.Filled.DirectionsRun
    "active_energy", "calories" -> Icons.Default.LocalFireDepartment
    "sleep_duration" -> Icons.Default.Bedtime
    "resting_hr", "bp_systolic", "bp_diastolic", "hr_recovery_1min" -> Icons.Default.Favorite
    "hrv_rmssd", "hrv_sdnn" -> Icons.Default.MonitorHeart
    "stress_index", "respiratory_rate", "spo2", "vo2_max" -> Icons.Default.Air
    "blood_glucose" -> Icons.Default.WaterDrop
    "body_weight" -> Icons.Default.Scale
    "pain_nrs" -> Icons.Default.Healing
    "skin_temp", "skin_temp_delta" -> Icons.Default.Thermostat
    else -> Icons.AutoMirrored.Filled.ShowChart
}

fun signalFamily(key: String): Category = when (Signals.groups.firstOrNull { key in it.second }?.first) {
    R.string.signals_movement -> Category.TEAL; R.string.signals_activity -> Category.BLUE; R.string.signals_rest -> Category.INDIGO; else -> Category.VIOLET
}

fun metricIcon(id: String): ImageVector = when (id) {
    "M1" -> Icons.AutoMirrored.Filled.DirectionsWalk; "M2" -> Icons.Default.Healing; "M3" -> Icons.Default.Accessibility
    "M4", "M7" -> Icons.Default.Speed; "M5" -> Icons.Default.Timer; "M6", "C6" -> Icons.Default.Chair; "M8" -> Icons.Default.Stairs
    "M9" -> Icons.Default.Bedtime; "M10" -> Icons.Default.MonitorHeart; "M11" -> Icons.Default.WbTwilight; "M12" -> Icons.Default.Favorite
    "M13" -> Icons.Default.Thermostat; "M14" -> Icons.Default.Checklist; "M17" -> Icons.AutoMirrored.Filled.TrendingUp
    "M18" -> Icons.Default.AltRoute; "C1" -> Icons.Default.Scale; "C2", "C5" -> Icons.Default.Air; "C3" -> Icons.Default.WaterDrop
    "C4" -> Icons.Default.Favorite; else -> Icons.AutoMirrored.Filled.ShowChart
}

fun metricFamily(id: String): Category = when (id) {
    "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "C6" -> Category.TEAL
    "M9", "M10", "M11", "M17", "M18" -> Category.INDIGO
    "M12", "M13", "C1", "C2", "C3", "C4", "C5" -> Category.VIOLET
    else -> Category.BLUE
}

/** The care team's four states, in a row's width. */
@Composable
private fun stateLine(s: PatientSignal?, m: PortfolioMetric): Pair<String, Tone?> {
    if (s != null) {
        if (s.state == "waiting") return (s.headline.ifBlank { s.stateLabel.ifBlank { stringResource(R.string.progress_waiting_new_data) } }) to null
        return when (s.state) {
            "good" -> stringResource(R.string.signal_steady); "watch" -> stringResource(R.string.signal_watch)
            "reviewing" -> stringResource(R.string.signal_reviewing); else -> s.stateLabel
        } to toneFor(s.state)
    }
    val last = m.series.lastOrNull()?.date?.let { Dates.day(it) }
    val ago = last?.let { java.time.temporal.ChronoUnit.DAYS.between(it, LocalDate.now()) }
    return (when (ago) {
        null -> ""; 0L -> stringResource(R.string.today); 1L -> stringResource(R.string.yesterday); else -> stringResource(R.string.days_ago, ago)
    }) to null
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProgressScreen(nav: NavHostController) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    var refreshing by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        if (state.portfolio.isEmpty()) app.refreshPortfolio(false)
        if (state.metrics == null) app.refreshMetrics(false)
    }
    val metrics = state.metrics
    val byKey = state.portfolio.associateBy { it.key }
    val signalsByKey = metrics?.signals?.associateBy { it.key }.orEmpty()
    var showAll by remember { mutableStateOf(false) }

    PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.refreshPortfolio(); app.refreshMetrics(); app.refreshMe(false); refreshing = false } }) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(stringResource(R.string.tab_progress), style = MPType.displayS, color = c.ink)
                state.me?.let { me ->
                    val days = me.recovery.daysWithData ?: 0
                    val full = metrics?.overall?.daysUntilFullPicture?.takeIf { it > 0 }
                    val parts = listOfNotNull(
                        if (me.patient.isRecovery) me.patient.postopDay?.let { stringResource(R.string.day_n, it) } else null,
                        if (days > 0) stringResource(R.string.progress_days_of_data, days) else stringResource(R.string.progress_no_data),
                        full?.let { pluralStringResource(R.plurals.progress_full_picture_in, it, it) },
                    )
                    Text(parts.joinToString(DOT), style = MPType.copyLarge, color = c.body, modifier = Modifier.padding(horizontal = 4.dp))
                }
            }
            if (metrics != null && metrics.metrics.isNotEmpty()) {
                val shown = if (showAll) metrics.metrics else metrics.metrics.take(3)
                Panel(padding = 0.dp) {
                    CardTitleRow(stringResource(R.string.progress_what_team_sees), note = metrics.overall.waiting.takeIf { it > 0 }?.let { stringResource(R.string.progress_on_the_way, it) })
                    metrics.overall.blurb?.takeIf { it.isNotBlank() }?.let {
                        Text(it, style = MPType.copy, color = c.body, modifier = Modifier.padding(horizontal = 16.dp).padding(bottom = 10.dp))
                    }
                    InsetDivider()
                    shown.forEachIndexed { i, m ->
                        MetricRow(m) { nav.navigate(Routes.metric(m.id)) }
                        if (i < shown.lastIndex) RowDivider()
                    }
                    if (metrics.metrics.size > 3) {
                        InsetDivider()
                        PlainButton(if (showAll) stringResource(R.string.progress_show_fewer) else stringResource(R.string.progress_show_all, metrics.metrics.size), bare = true,
                            modifier = Modifier.padding(horizontal = 16.dp)) { showAll = !showAll }
                    } else Gap(4.dp)
                }
            }
            if (state.portfolio.isEmpty() && signalsByKey.isEmpty()) {
                Panel {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Glyph(Icons.AutoMirrored.Filled.ShowChart, Category.TEAL, 40.dp)
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text(stringResource(R.string.progress_nothing_yet), style = MPType.copyLargeMedium, color = c.ink)
                            Text(stringResource(R.string.progress_nothing_yet_body), style = MPType.copy, color = c.body)
                        }
                    }
                    Gap(14.dp)
                    SecondaryButton(stringResource(R.string.progress_measure_walk), icon = Icons.AutoMirrored.Filled.DirectionsWalk) { app.selectTab(Tab.MEASURE) }
                }
            }
            Signals.groups.forEach { (titleRes, keys) ->
                val rows = keys.mapNotNull { k -> byKey[k]?.let { k to it } }
                val waiting = keys.mapNotNull { k -> signalsByKey[k]?.takeIf { byKey[k] == null && (it.availability == "active" || it.availability == "unavailable") } }
                if (rows.isEmpty() && waiting.isEmpty()) return@forEach
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    SectionHeading(stringResource(titleRes), note = if (titleRes == R.string.signals_movement && rows.any { it.first in Signals.measured }) stringResource(R.string.progress_phone_and_watch) else null)
                    Panel(padding = 0.dp) {
                        rows.forEachIndexed { i, (k, m) -> SignalRow(m, signalsByKey[k]) { nav.navigate(Routes.signal(k)) }; if (i < rows.lastIndex || waiting.isNotEmpty()) RowDivider() }
                        waiting.forEachIndexed { i, s -> WaitingRow(s); if (i < waiting.lastIndex) RowDivider() }
                    }
                }
            }
            Guardrail()
            Gap(10.dp)
        }
    }
}

/** One of the care team's metrics as a row: glyph, title, the state in words, a chevron. */
@Composable
private fun MetricRow(m: PatientMetric, onClick: () -> Unit) {
    val c = MP.colors
    val tone = toneFor(m.state)
    val words = if (m.isWaiting) (m.daysLeftText?.let { d ->
        if (d.startsWith("waiting")) stringResource(R.string.progress_waiting_new_data) else if (d.startsWith("early read")) stringResource(R.string.progress_early_read) + d.removePrefix("early read") else stringResource(R.string.progress_shows_in, d)
    } ?: m.stateLabel.ifBlank { stringResource(R.string.progress_not_showing_yet) }) else m.stateLabel.ifBlank { m.state }
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 16.dp, vertical = 11.dp), verticalAlignment = Alignment.CenterVertically) {
        Glyph(metricIcon(m.id), metricFamily(m.id))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(m.title, style = MPType.copyLargeMedium, color = c.ink)
            StateLabel(words, tone)
        }
        Spacer(Modifier.width(8.dp))
        Chevron()
    }
}

/** One signal as a row: glyph, name, state in words, a two-week sparkline, the latest reading. */
@Composable
private fun SignalRow(m: PortfolioMetric, s: PatientSignal?, onClick: () -> Unit) {
    val c = MP.colors
    val (line, tone) = stateLine(s, m)
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 16.dp, vertical = 11.dp).heightIn(min = 34.dp), verticalAlignment = Alignment.CenterVertically) {
        Glyph(signalIcon(m.key), signalFamily(m.key))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(s?.title?.ifBlank { null } ?: m.label.ifBlank { m.key }, style = MPType.copyLargeMedium, color = c.ink)
            if (tone != null) StateLabel(line, tone) else if (line.isNotBlank()) Text(line, style = MPType.label, color = c.muted)
        }
        Spacer(Modifier.width(8.dp))
        if (m.series.size > 1) {
            SeriesChart(dailySlots(m.series), bars = m.key in Signals.dailyTotals, modifier = Modifier.width(60.dp), height = 24.dp, showAverage = false, color = c.ink.copy(alpha = .55f))
            Spacer(Modifier.width(10.dp))
        }
        val v = m.latest ?: m.series.lastOrNull()?.value
        RowFigure(fmt(v), m.unit.takeIf { it.isNotBlank() && it != "%" && it != "score" })
        Spacer(Modifier.width(6.dp))
        Chevron()
    }
}

@Composable
private fun WaitingRow(s: PatientSignal) {
    val c = MP.colors
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 11.dp), verticalAlignment = Alignment.CenterVertically) {
        Glyph(signalIcon(s.key), signalFamily(s.key))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(s.title.ifBlank { s.key }, style = MPType.copyLargeMedium, color = c.ink)
            Text(s.headline.ifBlank { s.stateLabel }, style = MPType.label, color = c.muted, maxLines = 2)
        }
        Spacer(Modifier.width(8.dp))
        StateLabel(s.stateLabel.ifBlank { stringResource(R.string.waiting) }, Tone.MISSING)
    }
}

@Composable
fun SignalDetailScreen(nav: NavHostController, key: String) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val c = MP.colors
    val m = state.portfolio.firstOrNull { it.key == key }
    val s = state.metrics?.signals?.firstOrNull { it.key == key }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        BackBar(nav, s?.title?.ifBlank { null } ?: m?.label ?: key)
        if (m == null) { Text(stringResource(R.string.progress_no_readings), color = c.muted); return@Column }
        val slots = dailySlots(m.series)
        val present = slots.filterNotNull()
        // A finger on the chart shows that day's reading in place of the latest.
        var picked by remember { mutableStateOf<Int?>(null) }
        val shownValue = picked?.let { slots[it] } ?: m.latest ?: m.series.lastOrNull()?.value
        val shownDay = picked?.let { LocalDate.now().minusDays((slots.size - 1 - it).toLong()) } ?: m.series.lastOrNull()?.let { Dates.day(it.date) }
        Panel {
            Row(verticalAlignment = Alignment.Bottom) {
                Text(fmt(shownValue), style = MaterialTheme.typography.displayMedium, color = c.ink)
                Spacer(Modifier.width(6.dp))
                Text(m.unit, style = MaterialTheme.typography.titleMedium, color = c.muted, modifier = Modifier.padding(bottom = 8.dp))
            }
            shownDay?.let { Text(if (picked == null) stringResource(R.string.progress_latest, Dates.monthDay(it)) else Dates.monthDay(it), color = c.muted, style = MaterialTheme.typography.bodyMedium) }
            Gap(12.dp)
            SeriesChart(slots, bars = key in Signals.dailyTotals, height = 160.dp, picked = picked, onPick = { picked = it })
            Gap(8.dp)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Stat(stringResource(R.string.stat_average), fmt(present.takeIf { it.isNotEmpty() }?.average()))
                Stat(stringResource(R.string.stat_low), fmt(present.minOrNull()))
                Stat(stringResource(R.string.stat_high), fmt(present.maxOrNull()))
                Stat(stringResource(R.string.stat_days), "${present.size}")
            }
            if (key in Signals.measured) { Gap(8.dp); Text(stringResource(R.string.progress_measured_by_phone), color = c.brandInk, style = MaterialTheme.typography.labelMedium) }
        }
        Gap()
        s?.let { sig ->
            if (sig.headline.isNotBlank()) Panel { Text(sig.stateLabel, style = MaterialTheme.typography.labelMedium, color = c.muted); Text(sig.headline, color = c.ink) }
            sig.explain?.let { e -> Gap(); ExplainCard(e, sig.readiness) }
        }
        Gap(24.dp)
    }
}

/** The explanation the server wrote, word for word, plus how far the reading is from showing. */
@Composable
fun ExplainCard(e: MetricExplain, readiness: MetricReadiness? = null) {
    Panel {
        if (e.what.isNotBlank()) Explain(stringResource(R.string.explain_what), e.what)
        if (e.why.isNotBlank()) Explain(stringResource(R.string.explain_why), e.why)
        if (e.help.isNotBlank()) Explain(stringResource(R.string.explain_help), e.help)
        readiness?.sentence()?.let { Explain(stringResource(R.string.explain_where), it) }
    }
}

/** "Needs 5 days of steps; you have 3." (ios MetricReadiness.sentence). */
@Composable
fun MetricReadiness.sentence(): String? {
    val what = note?.let { stringResource(R.string.readiness_of, it) } ?: ""
    val have = have ?: return null
    val need = need ?: return null
    if (ready == true) {
        val firmLeft = firmLeft ?: 0
        return if (stage == "provisional" && firmLeft > 0 && firm != null) stringResource(R.string.readiness_showing_from, have, unitWord(have), what, firm) else null
    }
    return stringResource(R.string.readiness_needs, need, unitWord(need), what, have)
}

private fun MetricReadiness.unitWord(n: Int): String = if (n == 1 && unit.endsWith("s")) unit.dropLast(1) else unit

@Composable
private fun Explain(title: String, body: String) {
    Text(title, style = MaterialTheme.typography.labelMedium, color = MP.colors.muted)
    Text(body, color = MP.colors.body, style = MaterialTheme.typography.bodyMedium)
    Gap(8.dp)
}

@Composable
fun CareMetricDetailScreen(nav: NavHostController, id: String) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val c = MP.colors
    val m = state.metrics?.metrics?.firstOrNull { it.id == id }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        BackBar(nav, m?.title ?: id)
        if (m == null) { Text(stringResource(R.string.progress_not_available), color = c.muted); return@Column }
        Panel {
            StatusPill(m.stateLabel.ifBlank { m.state }, toneFor(m.state))
            Gap(8.dp)
            Text(m.headline, style = MaterialTheme.typography.bodyLarge, color = c.ink)
            m.daysLeftText?.let { Gap(4.dp); Text(it, color = c.muted, style = MaterialTheme.typography.bodyMedium) }
            val pts = m.chart?.points.orEmpty().mapNotNull { it.y }
            if (pts.size >= 2) { Gap(12.dp); SeriesChart(pts, bars = m.chart?.kind == "bars", height = 150.dp) }
            if (!m.isWaiting) m.value?.takeIf { it.isNotBlank() }?.let {
                Gap(8.dp)
                Text(if (m.unit.isBlank()) it else "$it ${m.unit}", style = MaterialTheme.typography.displaySmall, color = c.ink)
            }
        }
        m.explain?.let { e -> Gap(); ExplainCard(e, m.readiness) }
        Gap(24.dp)
    }
}
