package com.medpull.recovery.features.measure

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material.icons.automirrored.filled.DirectionsWalk
import androidx.compose.material.icons.filled.Architecture
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.medpull.recovery.R
import com.medpull.recovery.core.AppConfig
import com.medpull.recovery.core.Dates
import com.medpull.recovery.core.MotionUpload
import com.medpull.recovery.core.MotionWindowSummary
import com.medpull.recovery.core.PortfolioMetric
import com.medpull.recovery.core.RangeOfMotionResponse
import com.medpull.recovery.core.RangeOfMotionUpload
import com.medpull.recovery.core.SixMinuteWalkResponse
import com.medpull.recovery.core.SixMinuteWalkUpload
import com.medpull.recovery.core.rangeOfMotion
import com.medpull.recovery.core.sixMinuteWalk
import com.medpull.recovery.core.uploadMotion
import com.medpull.recovery.features.progress.Signals
import com.medpull.recovery.features.progress.fmt
import com.medpull.recovery.features.progress.signalIcon
import com.medpull.recovery.motion.CaptureSession
import com.medpull.recovery.motion.CaptureState
import com.medpull.recovery.motion.LiveStats
import com.medpull.recovery.motion.MotionCaptureService
import com.medpull.recovery.ui.BackBar
import com.medpull.recovery.ui.Category
import com.medpull.recovery.ui.Chip
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Field
import com.medpull.recovery.ui.FlowChips
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Glyph
import com.medpull.recovery.ui.Guardrail
import com.medpull.recovery.ui.Hairline
import com.medpull.recovery.ui.ListRow
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.MPType
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PrimaryButton
import com.medpull.recovery.ui.Routes
import com.medpull.recovery.ui.RowDivider
import com.medpull.recovery.ui.RowFigure
import com.medpull.recovery.ui.SecondaryButton
import com.medpull.recovery.ui.SectionHeading
import com.medpull.recovery.ui.SectionTitle
import com.medpull.recovery.ui.Stat
import com.medpull.recovery.ui.StateLabel
import com.medpull.recovery.ui.StatusPill
import com.medpull.recovery.ui.Tone
import com.medpull.recovery.ui.appModel
import java.time.LocalDate
import java.util.Locale
import kotlin.math.atan2
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch

/** When each test is due, from the portfolio's latest readings (as on iPhone). */
object MeasureStatus {
    data class Test(val id: String, val nameRes: Int, val everyDays: Long, val keys: List<String>)
    val tests = listOf(
        Test("guided_walk", R.string.test_guided_walk, 2, listOf("cadence", "walking_steadiness", "step_length", "walking_speed")),
        Test("six_minute_walk", R.string.test_six_minute_walk, 7, listOf("six_min_walk")),
        Test("rom", R.string.test_rom, 3, listOf("rom_flexion", "rom_extension", "rom_abduction")),
    )
    fun lastDone(test: Test, portfolio: List<PortfolioMetric>): LocalDate? =
        portfolio.filter { it.key in test.keys }.flatMap { it.series }.mapNotNull { runCatching { LocalDate.parse(it.date.take(10)) }.getOrNull() }.maxOrNull()
    fun isDue(test: Test, portfolio: List<PortfolioMetric>): Boolean {
        val last = lastDone(test, portfolio) ?: return true
        return !last.plusDays(test.everyDays).isAfter(LocalDate.now())
    }
    fun due(portfolio: List<PortfolioMetric>): List<Test> = tests.filter { isDue(it, portfolio) }
}

/** Height for step length: Health Connect later; typed once and kept for now. */
object Stature {
    fun get(context: Context): Double? = context.getSharedPreferences("medpull.config", Context.MODE_PRIVATE)
        .getFloat("stature_cm", 0f).toDouble().takeIf { it in 100.0..250.0 }
    fun set(context: Context, cm: Double) = context.getSharedPreferences("medpull.config", Context.MODE_PRIVATE)
        .edit().putFloat("stature_cm", cm.toFloat()).apply()
}

private fun testIcon(id: String): ImageVector = when (id) {
    "guided_walk" -> Icons.AutoMirrored.Filled.DirectionsWalk; "six_minute_walk" -> Icons.Default.Timer; else -> Icons.Default.Architecture
}

private fun testSubtitle(id: String): Int = when (id) {
    "guided_walk" -> R.string.test_guided_walk_sub
    "six_minute_walk" -> R.string.test_six_minute_walk_sub
    else -> R.string.test_rom_sub
}

/** "Due", "Due tomorrow", "Due in 3 days": when the next one falls. */
@Composable
private fun dueLabel(test: MeasureStatus.Test, last: LocalDate?): String {
    if (last == null) return stringResource(R.string.due)
    val days = java.time.temporal.ChronoUnit.DAYS.between(LocalDate.now(), last.plusDays(test.everyDays))
    return when { days <= 0 -> stringResource(R.string.due); days == 1L -> stringResource(R.string.measure_due_tomorrow); else -> stringResource(R.string.measure_due_in_days, days) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MeasureScreen(nav: NavHostController) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    var refreshing by remember { mutableStateOf(false) }
    fun open(id: String) = when (id) {
        "guided_walk" -> nav.navigate(Routes.walk(false)); "six_minute_walk" -> nav.navigate(Routes.walk(true)); else -> nav.navigate(Routes.ROM)
    }
    PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.refreshPortfolio(); refreshing = false } }) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(stringResource(R.string.tab_measure), style = MPType.displayS, color = c.ink)
                Text(stringResource(R.string.measure_intro),
                    style = MPType.copyLarge, color = c.body, modifier = Modifier.padding(horizontal = 4.dp))
            }
            MeasureStatus.tests.forEach { t ->
                val due = MeasureStatus.isDue(t, state.portfolio)
                val last = MeasureStatus.lastDone(t, state.portfolio)
                Panel {
                    Row(verticalAlignment = Alignment.Top) {
                        Glyph(testIcon(t.id), Category.TEAL, 40.dp)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(stringResource(t.nameRes), style = MPType.ledeMedium, color = c.ink, modifier = Modifier.weight(1f))
                                StateLabel(dueLabel(t, last), if (due) Tone.MED else Tone.LOW)
                            }
                            Text(stringResource(testSubtitle(t.id)), style = MPType.copy, color = c.body)
                            Text(if (last == null) stringResource(R.string.measure_nothing_recorded) else stringResource(R.string.measure_last, Dates.monthDay(last)), style = MPType.figuresLabel, color = c.muted)
                        }
                    }
                    Gap(12.dp)
                    if (due) PrimaryButton(stringResource(R.string.start), icon = Icons.Default.PlayArrow) { open(t.id) }
                    else SecondaryButton(stringResource(R.string.measure_do_again), icon = Icons.Default.Refresh) { open(t.id) }
                }
            }
            val measured = state.portfolio.filter { it.key in Signals.measured }
            if (measured.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    SectionHeading(stringResource(R.string.measure_your_readings), note = stringResource(R.string.measure_last_two_weeks))
                    Panel(padding = 0.dp) {
                        measured.forEachIndexed { i, m ->
                            ListRow(m.label.ifBlank { m.key }, icon = signalIcon(m.key), family = Category.TEAL, inset = true,
                                trailing = { RowFigure(fmt(m.latest ?: m.series.lastOrNull()?.value), m.unit.takeIf { it.isNotBlank() }) },
                                onClick = { nav.navigate(Routes.signal(m.key)) })
                            if (i < measured.lastIndex) RowDivider()
                        }
                    }
                }
            }
            Text(stringResource(R.string.measure_footer),
                style = MPType.label, color = c.muted, modifier = Modifier.padding(horizontal = 4.dp))
            Gap(10.dp)
        }
    }
}

private enum class WalkPhase { SETUP, RUNNING, UPLOADING, RESULT }

/** The guided walk (60 s) and the six-minute walk (360 s): same capture, different test. */
@Composable
fun GuidedWalkScreen(nav: NavHostController, sixMinute: Boolean) {
    val app = appModel()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val c = MP.colors
    val title = stringResource(if (sixMinute) R.string.test_six_minute_walk else R.string.test_guided_walk)
    // The same lengths as the iPhone, so the two phones score comparable windows.
    val durationS = if (sixMinute) 360 else 180
    var phase by remember { mutableStateOf(WalkPhase.SETUP) }
    var pocket by remember { mutableStateOf(0) }
    var outdoors by remember { mutableStateOf(false) }
    var height by remember { mutableStateOf(Stature.get(context)?.let { "${it.toInt()}" } ?: "") }
    var error by remember { mutableStateOf<String?>(null) }
    var walkResult by remember { mutableStateOf<MotionWindowSummary?>(null) }
    var sixResult by remember { mutableStateOf<SixMinuteWalkResponse?>(null) }
    val capture by CaptureSession.state.collectAsStateWithLifecycle()
    val recorder = CaptureSession.recorder
    val live by (recorder?.live ?: MutableStateFlow(LiveStats())).collectAsStateWithLifecycle()

    val askPerms = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { }

    fun permissionsOk(): Boolean {
        val needed = mutableListOf(Manifest.permission.ACTIVITY_RECOGNITION)
        if (outdoors) needed += Manifest.permission.ACCESS_FINE_LOCATION
        if (android.os.Build.VERSION.SDK_INT >= 33) needed += Manifest.permission.POST_NOTIFICATIONS
        val missing = needed.filter { ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) { askPerms.launch(missing.toTypedArray()); return false }
        return true
    }

    suspend fun upload() {
        val rec = CaptureSession.recorder ?: return
        phase = WalkPhase.UPLOADING
        val h = height.toDoubleOrNull()?.takeIf { it in 100.0..250.0 }?.also { Stature.set(context, it) }
        val side = if (pocket == 0) "left" else "right"
        try {
            if (sixMinute) {
                // The server scales a walk stopped early, but only past a full
                // minute: anything shorter is a false start, not a test.
                if (live.elapsedS <= 60.0) throw IllegalStateException(context.getString(R.string.walk_too_short_minute))
                val window = rec.window("six_minute_walk", side)
                val r = app.api.sixMinuteWalk(SixMinuteWalkUpload(
                    startedAt = Dates.iso(rec.startedAt), durationS = live.elapsedS, steps = rec.steps.takeIf { it > 0 },
                    pedometerDistanceM = null, gpsDistanceM = rec.gpsDistanceM, gpsAccuracyM = rec.gpsAccuracyM,
                    minuteSteps = rec.minuteStepCounts.takeIf { it.isNotEmpty() }, heightCm = h, deviceModel = AppConfig.deviceName, motion = window,
                ))
                sixResult = r
            } else {
                val window = rec.window("guided_walk", side) ?: throw IllegalStateException(context.getString(R.string.walk_too_short_score))
                val r = app.api.uploadMotion(MotionUpload(listOf(window), h, AppConfig.deviceName))
                walkResult = r.windows.firstOrNull()
            }
            phase = WalkPhase.RESULT
            app.refreshPortfolio(false)
        } catch (e: Exception) { error = e.message; phase = WalkPhase.SETUP }
        CaptureSession.reset()
    }

    LaunchedEffect(capture) { if (capture == CaptureState.DONE && phase == WalkPhase.RUNNING) upload() }
    DisposableEffect(Unit) { onDispose { if (CaptureSession.state.value == CaptureState.RUNNING) MotionCaptureService.stop(context) } }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        BackBar(nav, title)
        error?.let { ErrorBanner(it, onDismiss = { error = null }); Gap() }
        when (phase) {
            WalkPhase.SETUP -> {
                Panel {
                    Text(stringResource(R.string.walk_how_it_works), style = MaterialTheme.typography.titleMedium, color = c.ink)
                    Text(if (sixMinute) stringResource(R.string.walk_six_instructions)
                    else stringResource(R.string.walk_guided_instructions),
                        color = c.body, style = MaterialTheme.typography.bodyMedium)
                }
                Gap()
                Text(stringResource(R.string.walk_which_pocket), style = MaterialTheme.typography.labelMedium, color = c.muted)
                Gap(6.dp)
                FlowChips(listOf(stringResource(R.string.left), stringResource(R.string.right)), pocket) { pocket = it }
                Gap()
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(stringResource(R.string.walk_outdoors), color = c.ink)
                        Text(stringResource(R.string.walk_outdoors_body), color = c.muted, style = MaterialTheme.typography.bodyMedium)
                    }
                    Switch(checked = outdoors, onCheckedChange = { outdoors = it })
                }
                Gap()
                Field(height, { height = it.filter { ch -> ch.isDigit() }.take(3) }, stringResource(R.string.walk_height_field), keyboard = KeyboardType.Number)
                Gap(16.dp)
                PrimaryButton(stringResource(R.string.start)) {
                    if (permissionsOk()) {
                        MotionCaptureService.start(context, title, durationS, outdoors)
                        phase = WalkPhase.RUNNING
                    }
                }
            }
            WalkPhase.RUNNING -> {
                Panel(tint = c.brandTint) {
                    Text(stringResource(R.string.walk_walking), style = MaterialTheme.typography.labelMedium, color = c.brandInk)
                    val s = live.elapsedS.toInt()
                    Text(String.format(Locale.getDefault(), "%d:%02d", s / 60, s % 60), style = MaterialTheme.typography.displayLarge, color = c.ink)
                    Text(stringResource(R.string.walk_of_duration, durationS / 60, String.format(Locale.getDefault(), "%02d", durationS % 60)), color = c.muted)
                    Gap(8.dp)
                    Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                        Stat(stringResource(R.string.stat_steps), "${live.steps}")
                        live.distanceM?.let { Stat(stringResource(R.string.stat_distance), stringResource(R.string.unit_m, it.toInt())) }
                        Stat(stringResource(R.string.stat_samples), "${live.samples}")
                    }
                    if (!live.hasGyro) Text(stringResource(R.string.walk_no_gyro), color = c.muted, style = MaterialTheme.typography.labelMedium)
                    if (!live.hasBarometer) Text(stringResource(R.string.walk_no_barometer), color = c.muted, style = MaterialTheme.typography.labelMedium)
                }
                Gap()
                SecondaryButton(stringResource(R.string.walk_stop_early)) { MotionCaptureService.stop(context) }
            }
            WalkPhase.UPLOADING -> { Panel { Text(stringResource(R.string.walk_sending), color = c.ink) } }
            WalkPhase.RESULT -> {
                Panel(tint = c.brandTint) {
                    Text(stringResource(R.string.done), style = MaterialTheme.typography.titleLarge, color = c.brandInk)
                    sixResult?.let { r ->
                        Gap(8.dp)
                        Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                            Stat(stringResource(R.string.stat_distance), stringResource(R.string.unit_m, r.distanceM.toInt())); r.steps?.let { Stat(stringResource(R.string.stat_steps), "$it") }
                            r.cadenceSpm?.let { Stat(stringResource(R.string.stat_cadence), stringResource(R.string.unit_spm, it.toInt())) }; r.fadePct?.let { Stat(stringResource(R.string.stat_fade), stringResource(R.string.unit_pct, it.toInt())) }
                        }
                        Text(stringResource(R.string.walk_distance_from, r.method.replace('_', ' ')), color = c.muted, style = MaterialTheme.typography.labelMedium)
                    }
                    walkResult?.let { w ->
                        Gap(8.dp)
                        if (w.bouts == 0) Text(stringResource(R.string.walk_no_steady), color = c.ink)
                        Row(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                            w.cadenceSpm?.let { Stat(stringResource(R.string.stat_cadence), stringResource(R.string.unit_spm, it.toInt())) }
                            w.walkingSpeedMps?.let { Stat(stringResource(R.string.stat_speed), fmt(it, "m/s")) }
                            w.stepLengthM?.let { Stat(stringResource(R.string.stat_step), fmt(it, "m")) }
                        }
                        Gap(4.dp)
                        Row(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                            w.asymmetryPct?.let { Stat(stringResource(R.string.stat_evenness), fmt(it, "%")) }
                            w.doubleSupportPct?.let { Stat(stringResource(R.string.stat_both_feet), fmt(it, "%")) }
                            w.steadiness?.let { Stat(stringResource(R.string.stat_steadiness), fmt(it)) }
                        }
                        if (w.stairs.isNotEmpty()) Text(stringResource(R.string.walk_stairs, w.stairs.joinToString { "${it.direction} ${fmt(it.speedMps, "m/s")}" }), color = c.muted)
                        w.notes.forEach { Text(it, color = c.muted, style = MaterialTheme.typography.labelMedium) }
                    }
                }
                Gap()
                PrimaryButton(stringResource(R.string.measure_back)) { nav.popBackStack() }
            }
        }
        Gap(24.dp)
    }
}

private data class Protocol(val id: String, val labelRes: Int, val referenceRes: Int, val movementRes: Int)
private val PROTOCOLS = listOf(
    Protocol("knee_flexion_supine", R.string.rom_knee_bend, R.string.rom_knee_bend_ref, R.string.rom_knee_bend_move),
    Protocol("knee_extension_supine", R.string.rom_knee_straighten, R.string.rom_knee_straighten_ref, R.string.rom_knee_straighten_move),
    Protocol("hip_flexion_supine", R.string.rom_hip_bend, R.string.rom_hip_bend_ref, R.string.rom_hip_bend_move),
    Protocol("shoulder_flexion_standing", R.string.rom_arm_forward, R.string.rom_arm_forward_ref, R.string.rom_arm_forward_move),
    Protocol("shoulder_abduction_standing", R.string.rom_arm_sideways, R.string.rom_arm_sideways_ref, R.string.rom_arm_sideways_move),
)

/** Two two-second holds of the gravity vector; the server reads the angle. */
@Composable
fun RangeOfMotionScreen(nav: NavHostController) {
    val app = appModel()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val c = MP.colors
    var protocol by remember { mutableStateOf(0) }
    var side by remember { mutableStateOf(0) }
    var reference by remember { mutableStateOf<List<List<Double>>?>(null) }
    var movement by remember { mutableStateOf<List<List<Double>>?>(null) }
    var capturing by remember { mutableStateOf(false) }
    var sending by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var result by remember { mutableStateOf<RangeOfMotionResponse?>(null) }
    var tilt by remember { mutableStateOf<Double?>(null) }
    val buffer = remember { ArrayDeque<FloatArray>() }

    DisposableEffect(Unit) {
        val sm = context.getSystemService(SensorManager::class.java)
        val sensor = sm.getDefaultSensor(Sensor.TYPE_GRAVITY) ?: sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        val l = object : SensorEventListener {
            override fun onSensorChanged(e: SensorEvent) {
                val g = e.values.clone()
                synchronized(buffer) { buffer.addLast(g); while (buffer.size > 100) buffer.removeFirst() }
                // Android's gravity is the negative of Apple's; the server's atan2(-gy, -gz) becomes atan2(gy, gz) here.
                tilt = Math.toDegrees(atan2(g[1].toDouble(), g[2].toDouble()))
            }
            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
        }
        if (sensor != null) sm.registerListener(l, sensor, 20_000)
        onDispose { sm.unregisterListener(l) }
    }

    fun snapshot(): List<List<Double>> = synchronized(buffer) { buffer.map { g -> g.map { Math.round(it * 1000.0) / 1000.0 } } }

    suspend fun capture(into: (List<List<Double>>) -> Unit) {
        capturing = true
        delay(2000)
        val s = snapshot()
        capturing = false
        if (s.size < 3) { error = context.getString(R.string.rom_hold_still); return }
        into(s)
    }

    val p = PROTOCOLS[protocol]
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        BackBar(nav, stringResource(R.string.test_rom))
        error?.let { ErrorBanner(it, onDismiss = { error = null }); Gap() }
        if (result == null) {
            FlowChips(PROTOCOLS.map { stringResource(it.labelRes) }, protocol) { protocol = it; reference = null; movement = null }
            Gap(8.dp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { Chip(stringResource(R.string.left), side == 0) { side = 0 }; Chip(stringResource(R.string.right), side == 1) { side = 1 } }
            Gap()
            Panel {
                Text(stringResource(R.string.rom_live_tilt), style = MaterialTheme.typography.labelMedium, color = c.muted)
                Text(tilt?.let { "${it.toInt()}°" } ?: "—", style = MaterialTheme.typography.displayMedium, color = c.ink)
                Text(stringResource(R.string.rom_live_tilt_body), color = c.muted, style = MaterialTheme.typography.labelMedium)
            }
            Gap()
            Panel(tint = if (reference != null) c.brandTint else null) {
                Text(stringResource(R.string.rom_step_reference), style = MaterialTheme.typography.titleMedium, color = c.ink)
                Text(stringResource(p.referenceRes), color = c.body, style = MaterialTheme.typography.bodyMedium)
                Gap(8.dp)
                SecondaryButton(if (reference == null) stringResource(R.string.rom_capture) else stringResource(R.string.rom_captured_redo), loading = capturing) { scope.launch { capture { reference = it } } }
            }
            Gap()
            Panel(tint = if (movement != null) c.brandTint else null) {
                Text(stringResource(R.string.rom_step_movement), style = MaterialTheme.typography.titleMedium, color = c.ink)
                Text(stringResource(p.movementRes), color = c.body, style = MaterialTheme.typography.bodyMedium)
                Gap(8.dp)
                SecondaryButton(if (movement == null) stringResource(R.string.rom_capture) else stringResource(R.string.rom_captured_redo), loading = capturing, enabled = reference != null) { scope.launch { capture { movement = it } } }
            }
            Gap(16.dp)
            PrimaryButton(stringResource(R.string.send), enabled = reference != null && movement != null, loading = sending) {
                scope.launch {
                    sending = true
                    try {
                        result = app.api.rangeOfMotion(RangeOfMotionUpload(Dates.iso(), p.id, if (side == 0) "left" else "right", reference!!, movement!!, AppConfig.deviceName))
                        app.refreshPortfolio(false)
                    } catch (e: Exception) { error = e.message }
                    sending = false
                }
            }
        } else {
            val r = result!!
            Panel(tint = c.brandTint) {
                Text("${r.joint.replaceFirstChar { it.uppercase() }} ${r.movement}, ${r.side}", style = MaterialTheme.typography.labelMedium, color = c.brandInk)
                Text("${r.angleDeg}°", style = MaterialTheme.typography.displayLarge, color = c.ink)
                if (!r.steady) Text(stringResource(R.string.rom_moved), color = c.riskHigh)
            }
            Gap()
            PrimaryButton(stringResource(R.string.rom_another_joint)) { result = null; reference = null; movement = null }
            Gap(8.dp)
            SecondaryButton(stringResource(R.string.measure_back)) { nav.popBackStack() }
        }
        Gap(24.dp)
    }
}
