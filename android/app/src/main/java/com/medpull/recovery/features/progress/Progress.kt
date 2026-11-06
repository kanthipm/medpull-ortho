package com.medpull.recovery.features.progress

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.medpull.recovery.core.Dates
import com.medpull.recovery.core.PatientMetric
import com.medpull.recovery.core.PatientSignal
import com.medpull.recovery.core.PortfolioMetric
import com.medpull.recovery.core.Tab
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Guardrail
import com.medpull.recovery.ui.Hairline
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PlainButton
import com.medpull.recovery.ui.PrimaryButton
import com.medpull.recovery.ui.Routes
import com.medpull.recovery.ui.SectionTitle
import com.medpull.recovery.ui.SeriesChart
import com.medpull.recovery.ui.StatusPill
import com.medpull.recovery.ui.appModel
import com.medpull.recovery.ui.toneFor
import kotlinx.coroutines.launch
import java.time.LocalDate

/** The signal groups the iPhone's Progress tab uses, with Apple-only keys left out. */
object Signals {
    val groups: List<Pair<String, List<String>>> = listOf(
        "Movement" to listOf("walking_speed", "step_length", "cadence", "walking_asymmetry_pct", "double_support_pct",
            "walking_steadiness", "stair_speed_up", "stair_speed_down", "six_min_walk", "rom_flexion", "rom_extension", "rom_abduction"),
        "Activity" to listOf("steps", "exercise_session", "active_energy", "calories"),
        "Rest" to listOf("sleep_duration", "hrv_rmssd", "hrv_sdnn", "resting_hr", "stress_index", "respiratory_rate"),
        "Body" to listOf("skin_temp", "skin_temp_delta", "spo2", "pain_nrs", "body_weight", "bp_systolic", "bp_diastolic",
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
    val s = if (kotlin.math.abs(v) >= 100) String.format(java.util.Locale.getDefault(), "%,.0f", v)
    else String.format(java.util.Locale.getDefault(), "%.1f", v).trimEnd('0').trimEnd('.')
    return if (unit.isBlank()) s else "$s $unit"
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
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
            Text("PROGRESS", style = MaterialTheme.typography.labelSmall, color = c.muted, modifier = Modifier.padding(top = 16.dp))
            Text(state.me?.recovery?.label?.ifBlank { null } ?: "How you're doing", style = MaterialTheme.typography.displaySmall, color = c.ink)
            state.me?.recovery?.blurb?.takeIf { it.isNotBlank() }?.let { Text(it, color = c.body, style = MaterialTheme.typography.bodyLarge) }
            Gap(16.dp)
            if (metrics != null && metrics.metrics.isNotEmpty()) {
                Panel {
                    SectionTitle("What your care team sees", action = {
                        if (metrics.metrics.size > 3) PlainButton(if (showAll) "Fewer" else "Show all") { showAll = !showAll }
                    })
                    val shown = if (showAll) metrics.metrics else metrics.metrics.take(3)
                    shown.forEachIndexed { i, m ->
                        MetricRow(m) { nav.navigate(Routes.metric(m.id)) }
                        if (i < shown.lastIndex) Hairline()
                    }
                    metrics.overall.daysUntilFullPicture?.let { d ->
                        Gap(8.dp); Text("Your full picture shows in $d days.", color = c.muted, style = MaterialTheme.typography.bodyMedium)
                    }
                }
                Gap()
            }
            if (state.portfolio.isEmpty() && signalsByKey.isEmpty()) {
                Panel {
                    Text("Nothing to chart yet", style = MaterialTheme.typography.titleMedium, color = c.ink)
                    Text("Connect your phone's health data or run a walk test on the Measure tab.", color = c.body)
                    Gap(8.dp)
                    PrimaryButton("Go to Measure") { app.selectTab(Tab.MEASURE) }
                }
            }
            Signals.groups.forEach { (title, keys) ->
                val rows = keys.mapNotNull { k -> byKey[k]?.let { k to it } }
                val waiting = keys.mapNotNull { k -> signalsByKey[k]?.takeIf { byKey[k] == null && (it.availability == "active" || it.availability == "unavailable") } }
                if (rows.isEmpty() && waiting.isEmpty()) return@forEach
                Panel {
                    SectionTitle(title)
                    rows.forEachIndexed { i, (k, m) -> SignalRow(m, signalsByKey[k]) { nav.navigate(Routes.signal(k)) }; if (i < rows.lastIndex || waiting.isNotEmpty()) Hairline() }
                    waiting.forEachIndexed { i, s -> WaitingRow(s); if (i < waiting.lastIndex) Hairline() }
                }
                Gap()
            }
            Guardrail()
            Gap(24.dp)
        }
    }
}

@Composable
private fun MetricRow(m: PatientMetric, onClick: () -> Unit) {
    val c = MP.colors
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(m.title, style = MaterialTheme.typography.bodyLarge, color = c.ink)
            Text(m.headline, style = MaterialTheme.typography.bodyMedium, color = c.muted, maxLines = 2)
        }
        Spacer(Modifier.width(8.dp))
        StatusPill(m.stateLabel.ifBlank { m.state }, toneFor(m.state))
    }
}

@Composable
private fun SignalRow(m: PortfolioMetric, s: PatientSignal?, onClick: () -> Unit) {
    val c = MP.colors
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(s?.title?.ifBlank { null } ?: m.label.ifBlank { m.key }, style = MaterialTheme.typography.bodyLarge, color = c.ink)
            Text(fmt(m.latest ?: m.series.lastOrNull()?.value, m.unit) + (if (m.key in Signals.measured) " · measured by MedPull" else ""),
                style = MaterialTheme.typography.bodyMedium, color = c.muted)
        }
        Spacer(Modifier.width(12.dp))
        SeriesChart(dailySlots(m.series), bars = m.key in Signals.dailyTotals, modifier = Modifier.width(96.dp), height = 36.dp, showAverage = false)
    }
}

@Composable
private fun WaitingRow(s: PatientSignal) {
    val c = MP.colors
    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(s.title.ifBlank { s.key }, style = MaterialTheme.typography.bodyLarge, color = c.ink)
            Text(s.headline, style = MaterialTheme.typography.bodyMedium, color = c.muted, maxLines = 2)
        }
        StatusPill(s.stateLabel.ifBlank { "Waiting" }, com.medpull.recovery.ui.Tone.MISSING)
    }
}

@Composable
private fun DetailBar(nav: NavHostController, title: String) {
    Row(Modifier.fillMaxWidth().height(52.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = MP.colors.ink) }
        Text(title, style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
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
        DetailBar(nav, s?.title?.ifBlank { null } ?: m?.label ?: key)
        if (m == null) { Text("No readings yet.", color = c.muted); return@Column }
        val slots = dailySlots(m.series)
        val present = slots.filterNotNull()
        Panel {
            Row(verticalAlignment = Alignment.Bottom) {
                Text(fmt(m.latest ?: m.series.lastOrNull()?.value), style = MaterialTheme.typography.displayMedium, color = c.ink)
                Spacer(Modifier.width(6.dp))
                Text(m.unit, style = MaterialTheme.typography.titleMedium, color = c.muted, modifier = Modifier.padding(bottom = 8.dp))
            }
            m.series.lastOrNull()?.let { Text("Latest ${Dates.day(it.date)?.let { d -> Dates.monthDay(d) } ?: it.date}", color = c.muted, style = MaterialTheme.typography.bodyMedium) }
            Gap(12.dp)
            SeriesChart(slots, bars = key in Signals.dailyTotals, height = 160.dp)
            Gap(8.dp)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = androidx.compose.foundation.layout.Arrangement.SpaceBetween) {
                Stat("Average", fmt(present.takeIf { it.isNotEmpty() }?.average()))
                Stat("Low", fmt(present.minOrNull()))
                Stat("High", fmt(present.maxOrNull()))
                Stat("Days", "${present.size}")
            }
            if (key in Signals.measured) { Gap(8.dp); Text("Measured by MedPull from your phone's sensors.", color = c.brandInk, style = MaterialTheme.typography.labelMedium) }
        }
        Gap()
        s?.let { sig ->
            if (sig.headline.isNotBlank()) Panel { Text(sig.stateLabel, style = MaterialTheme.typography.labelMedium, color = c.muted); Text(sig.headline, color = c.ink) }
            sig.explain?.let { e ->
                Gap()
                Panel {
                    e.what?.let { Explain("What it is", it) }
                    e.why?.let { Explain("Why it matters", it) }
                    e.how?.let { Explain("How to help it show", it) }
                    e.reading?.let { Explain("Where it stands", it) }
                }
            }
        }
        Gap(24.dp)
    }
}

@Composable
private fun Stat(label: String, value: String) {
    Column { Text(label, style = MaterialTheme.typography.labelSmall, color = MP.colors.muted); Text(value, style = MaterialTheme.typography.titleMedium, color = MP.colors.ink) }
}

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
        DetailBar(nav, m?.title ?: id)
        if (m == null) { Text("Not available.", color = c.muted); return@Column }
        Panel {
            StatusPill(m.stateLabel.ifBlank { m.state }, toneFor(m.state))
            Gap(8.dp)
            Text(m.headline, style = MaterialTheme.typography.bodyLarge, color = c.ink)
            m.daysLeftText?.let { Gap(4.dp); Text(it, color = c.muted, style = MaterialTheme.typography.bodyMedium) }
            val pts = m.chart?.points.orEmpty().mapNotNull { it.y }
            if (pts.size >= 2) { Gap(12.dp); SeriesChart(pts, bars = m.chart?.kind == "bars", height = 150.dp) }
            m.value?.let { Gap(8.dp); Text(fmt(it, m.unit), style = MaterialTheme.typography.displaySmall, color = c.ink) }
        }
        m.explain?.let { e ->
            Gap()
            Panel {
                e.what?.let { Explain("What it is", it) }
                e.why?.let { Explain("Why it matters", it) }
                e.how?.let { Explain("How to help it show", it) }
                e.reading?.let { Explain("Where it stands", it) }
            }
        }
        Gap(24.dp)
    }
}
