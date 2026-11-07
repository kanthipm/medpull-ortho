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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
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
import com.medpull.recovery.motion.CaptureState
import com.medpull.recovery.motion.LiveStats
import com.medpull.recovery.motion.MotionCaptureService
import com.medpull.recovery.ui.BackBar
import com.medpull.recovery.ui.Chip
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Field
import com.medpull.recovery.ui.FlowChips
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Guardrail
import com.medpull.recovery.ui.Hairline
import com.medpull.recovery.ui.ListRow
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PrimaryButton
import com.medpull.recovery.ui.Routes
import com.medpull.recovery.ui.SecondaryButton
import com.medpull.recovery.ui.SectionTitle
import com.medpull.recovery.ui.Stat
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
    data class Test(val name: String, val everyDays: Long, val keys: List<String>)
    val tests = listOf(
        Test("Guided walk", 2, listOf("cadence", "walking_steadiness", "step_length", "walking_speed")),
        Test("Six-minute walk", 7, listOf("six_min_walk")),
        Test("Range of motion", 3, listOf("rom_flexion", "rom_extension", "rom_abduction")),
    )
    fun lastDone(test: Test, portfolio: List<PortfolioMetric>): LocalDate? =
        portfolio.filter { it.key in test.keys }.flatMap { it.series }.mapNotNull { runCatching { LocalDate.parse(it.date.take(10)) }.getOrNull() }.maxOrNull()
    fun isDue(test: Test, portfolio: List<PortfolioMetric>): Boolean {
        val last = lastDone(test, portfolio) ?: return true
        return !last.plusDays(test.everyDays).isAfter(LocalDate.now())
    }
    fun due(portfolio: List<PortfolioMetric>): List<String> = tests.filter { isDue(it, portfolio) }.map { it.name }
}

/** Height for step length: Health Connect later; typed once and kept for now. */
object Stature {
    fun get(context: Context): Double? = context.getSharedPreferences("medpull.config", Context.MODE_PRIVATE)
        .getFloat("stature_cm", 0f).toDouble().takeIf { it in 100.0..250.0 }
    fun set(context: Context, cm: Double) = context.getSharedPreferences("medpull.config", Context.MODE_PRIVATE)
        .edit().putFloat("stature_cm", cm.toFloat()).apply()
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MeasureScreen(nav: NavHostController) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    var refreshing by remember { mutableStateOf(false) }
    PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.refreshPortfolio(); refreshing = false } }) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
            Text("MEASURE", style = MaterialTheme.typography.labelSmall, color = c.muted, modifier = Modifier.padding(top = 16.dp))
            Text("Short tests, your phone as the sensor", style = MaterialTheme.typography.displaySmall, color = c.ink)
            Text("Every number is worked out by MedPull from what the phone records, so it is the same on any phone.", color = c.body, style = MaterialTheme.typography.bodyLarge)
            Gap(16.dp)
            MeasureStatus.tests.forEach { t ->
                val due = MeasureStatus.isDue(t, state.portfolio)
                val last = MeasureStatus.lastDone(t, state.portfolio)
                Panel(onClick = {
                    when (t.name) {
                        "Guided walk" -> nav.navigate(Routes.walk(false)); "Six-minute walk" -> nav.navigate(Routes.walk(true)); else -> nav.navigate(Routes.ROM)
                    }
                }) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(t.name, style = MaterialTheme.typography.titleLarge, color = c.ink)
                            Text(when (t.name) {
                                "Guided walk" -> "Three minutes with the phone in a front pocket."
                                "Six-minute walk" -> "Six minutes at your own pace, for distance and endurance."
                                else -> "Two short holds with the phone on the limb."
                            }, color = c.body, style = MaterialTheme.typography.bodyMedium)
                            Text(if (last == null) "Not done yet" else "Last ${Dates.monthDay(last)} · every ${t.everyDays} days",
                                color = c.muted, style = MaterialTheme.typography.labelMedium)
                        }
                        Spacer(Modifier.width(8.dp))
                        StatusPill(if (due) "Due" else "Done", if (due) Tone.MED else Tone.LOW)
                    }
                }
                Gap()
            }
            val measured = state.portfolio.filter { it.key in Signals.measured }
            if (measured.isNotEmpty()) {
                Panel {
                    SectionTitle("Your readings")
                    measured.forEachIndexed { i, m ->
                        ListRow(m.label.ifBlank { m.key }, fmt(m.latest ?: m.series.lastOrNull()?.value, m.unit), onClick = { nav.navigate(Routes.signal(m.key)) })
                        if (i < measured.lastIndex) Hairline()
                    }
                }
                Gap()
            }
            Guardrail()
            Gap(24.dp)
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
    val title = if (sixMinute) "Six-minute walk" else "Guided walk"
    // The same lengths as the iPhone, so the two phones score comparable windows.
    val durationS = if (sixMinute) 360 else 180
    var phase by remember { mutableStateOf(WalkPhase.SETUP) }
    var pocket by remember { mutableStateOf(0) }
    var outdoors by remember { mutableStateOf(false) }
    var height by remember { mutableStateOf(Stature.get(context)?.let { "${it.toInt()}" } ?: "") }
    var error by remember { mutableStateOf<String?>(null) }
    var walkResult by remember { mutableStateOf<MotionWindowSummary?>(null) }
    var sixResult by remember { mutableStateOf<SixMinuteWalkResponse?>(null) }
    val capture by MotionCaptureService.state.collectAsStateWithLifecycle()
    val recorder = MotionCaptureService.current
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
        val rec = MotionCaptureService.current ?: return
        phase = WalkPhase.UPLOADING
        val h = height.toDoubleOrNull()?.takeIf { it in 100.0..250.0 }?.also { Stature.set(context, it) }
        val side = if (pocket == 0) "left" else "right"
        try {
            if (sixMinute) {
                // The server scales a walk stopped early, but only past a full
                // minute: anything shorter is a false start, not a test.
                if (live.elapsedS <= 60.0) throw IllegalStateException("Walk for at least a minute for the test to count. Try again.")
                val window = rec.window("six_minute_walk", side)
                val r = app.api.sixMinuteWalk(SixMinuteWalkUpload(
                    startedAt = Dates.iso(rec.startedAt), durationS = live.elapsedS, steps = rec.steps.takeIf { it > 0 },
                    pedometerDistanceM = null, gpsDistanceM = rec.gpsDistanceM, gpsAccuracyM = rec.gpsAccuracyM,
                    minuteSteps = rec.minuteStepCounts.takeIf { it.isNotEmpty() }, heightCm = h, deviceModel = AppConfig.deviceName, motion = window,
                ))
                sixResult = r
            } else {
                val window = rec.window("guided_walk", side) ?: throw IllegalStateException("The walk was too short to score. Try again.")
                val r = app.api.uploadMotion(MotionUpload(listOf(window), h, AppConfig.deviceName))
                walkResult = r.windows.firstOrNull()
            }
            phase = WalkPhase.RESULT
            app.refreshPortfolio(false)
        } catch (e: Exception) { error = e.message; phase = WalkPhase.SETUP }
        MotionCaptureService.reset()
    }

    LaunchedEffect(capture) { if (capture == CaptureState.DONE && phase == WalkPhase.RUNNING) upload() }
    DisposableEffect(Unit) { onDispose { if (MotionCaptureService.state.value == CaptureState.RUNNING) MotionCaptureService.stop(context) } }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        BackBar(nav, title)
        error?.let { ErrorBanner(it, onDismiss = { error = null }); Gap() }
        when (phase) {
            WalkPhase.SETUP -> {
                Panel {
                    Text("How it works", style = MaterialTheme.typography.titleMedium, color = c.ink)
                    Text(if (sixMinute) "Walk for six minutes at your own pace, on flat ground, with the phone in a front trouser pocket, top end up. Stop early if you need to; the test is scaled."
                    else "Walk for three minutes at your usual pace with the phone in a front trouser pocket, top end up. The server works out your speed, step length, evenness and steadiness.",
                        color = c.body, style = MaterialTheme.typography.bodyMedium)
                }
                Gap()
                Text("Which pocket?", style = MaterialTheme.typography.labelMedium, color = c.muted)
                Gap(6.dp)
                FlowChips(listOf("Left", "Right"), pocket) { pocket = it }
                Gap()
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Outdoors", color = c.ink)
                        Text("Uses GPS for distance.", color = c.muted, style = MaterialTheme.typography.bodyMedium)
                    }
                    Switch(checked = outdoors, onCheckedChange = { outdoors = it })
                }
                Gap()
                Field(height, { height = it.filter { ch -> ch.isDigit() }.take(3) }, "Your height in cm (for step length)", keyboard = KeyboardType.Number)
                Gap(16.dp)
                PrimaryButton("Start") {
                    if (permissionsOk()) {
                        MotionCaptureService.start(context, title, durationS, outdoors)
                        phase = WalkPhase.RUNNING
                    }
                }
            }
            WalkPhase.RUNNING -> {
                Panel(tint = c.brandTint) {
                    Text("Walking…", style = MaterialTheme.typography.labelMedium, color = c.brandInk)
                    val s = live.elapsedS.toInt()
                    Text(String.format(Locale.getDefault(), "%d:%02d", s / 60, s % 60), style = MaterialTheme.typography.displayLarge, color = c.ink)
                    Text("of ${durationS / 60}:${String.format(Locale.getDefault(), "%02d", durationS % 60)}", color = c.muted)
                    Gap(8.dp)
                    Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                        Stat("Steps", "${live.steps}")
                        live.distanceM?.let { Stat("Distance", "${it.toInt()} m") }
                        Stat("Samples", "${live.samples}")
                    }
                    if (!live.hasGyro) Text("No gyroscope: walking evenness will be unsigned.", color = c.muted, style = MaterialTheme.typography.labelMedium)
                    if (!live.hasBarometer) Text("No barometer: stairs won't be measured.", color = c.muted, style = MaterialTheme.typography.labelMedium)
                }
                Gap()
                SecondaryButton("Stop early") { MotionCaptureService.stop(context) }
            }
            WalkPhase.UPLOADING -> { Panel { Text("Sending to MedPull…", color = c.ink) } }
            WalkPhase.RESULT -> {
                Panel(tint = c.brandTint) {
                    Text("Done", style = MaterialTheme.typography.titleLarge, color = c.brandInk)
                    sixResult?.let { r ->
                        Gap(8.dp)
                        Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                            Stat("Distance", "${r.distanceM.toInt()} m"); r.steps?.let { Stat("Steps", "$it") }
                            r.cadenceSpm?.let { Stat("Cadence", "${it.toInt()} spm") }; r.fadePct?.let { Stat("Fade", "${it.toInt()}%") }
                        }
                        Text("Distance from ${r.method.replace('_', ' ')}.", color = c.muted, style = MaterialTheme.typography.labelMedium)
                    }
                    walkResult?.let { w ->
                        Gap(8.dp)
                        if (w.bouts == 0) Text("No steady walking was found in the recording. Keep the phone in a front pocket and walk without stopping.", color = c.ink)
                        Row(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                            w.cadenceSpm?.let { Stat("Cadence", "${it.toInt()} spm") }
                            w.walkingSpeedMps?.let { Stat("Speed", fmt(it, "m/s")) }
                            w.stepLengthM?.let { Stat("Step", fmt(it, "m")) }
                        }
                        Gap(4.dp)
                        Row(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                            w.asymmetryPct?.let { Stat("Evenness", fmt(it, "%")) }
                            w.doubleSupportPct?.let { Stat("Both feet", fmt(it, "%")) }
                            w.steadiness?.let { Stat("Steadiness", fmt(it)) }
                        }
                        if (w.stairs.isNotEmpty()) Text("Stairs: " + w.stairs.joinToString { "${it.direction} ${fmt(it.speedMps, "m/s")}" }, color = c.muted)
                        w.notes.forEach { Text(it, color = c.muted, style = MaterialTheme.typography.labelMedium) }
                    }
                }
                Gap()
                PrimaryButton("Back to Measure") { nav.popBackStack() }
            }
        }
        Gap(24.dp)
    }
}

private data class Protocol(val id: String, val label: String, val reference: String, val movement: String)
private val PROTOCOLS = listOf(
    Protocol("knee_flexion_supine", "Knee bend", "Lie on your back, leg straight, phone resting on your shin, top end toward the knee.", "Slide your heel toward you as far as it goes and hold."),
    Protocol("knee_extension_supine", "Knee straighten", "Lie on your back with the phone flat on the bed beside you.", "Rest the phone on your shin, heel propped, and press the knee down."),
    Protocol("hip_flexion_supine", "Hip bend", "Lie on your back, thigh flat, phone on your thigh.", "Bring the knee toward your chest and hold."),
    Protocol("shoulder_flexion_standing", "Arm forward", "Stand with the arm hanging, phone on your upper arm.", "Raise the arm forward as high as it goes and hold."),
    Protocol("shoulder_abduction_standing", "Arm sideways", "Stand with the arm hanging, phone on your upper arm.", "Raise the arm out to the side as high as it goes and hold."),
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
        if (s.size < 3) { error = "Hold the phone still for two seconds."; return }
        into(s)
    }

    val p = PROTOCOLS[protocol]
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        BackBar(nav, "Range of motion")
        error?.let { ErrorBanner(it, onDismiss = { error = null }); Gap() }
        if (result == null) {
            FlowChips(PROTOCOLS.map { it.label }, protocol) { protocol = it; reference = null; movement = null }
            Gap(8.dp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { Chip("Left", side == 0) { side = 0 }; Chip("Right", side == 1) { side = 1 } }
            Gap()
            Panel {
                Text("Live tilt", style = MaterialTheme.typography.labelMedium, color = c.muted)
                Text(tilt?.let { "${it.toInt()}°" } ?: "—", style = MaterialTheme.typography.displayMedium, color = c.ink)
                Text("The server reads the angle from two still holds; this is only to see the phone is moving with the limb.", color = c.muted, style = MaterialTheme.typography.labelMedium)
            }
            Gap()
            Panel(tint = if (reference != null) c.brandTint else null) {
                Text("1 · Reference position", style = MaterialTheme.typography.titleMedium, color = c.ink)
                Text(p.reference, color = c.body, style = MaterialTheme.typography.bodyMedium)
                Gap(8.dp)
                SecondaryButton(if (reference == null) "Capture (hold still 2 s)" else "Captured ✓ · redo", loading = capturing) { scope.launch { capture { reference = it } } }
            }
            Gap()
            Panel(tint = if (movement != null) c.brandTint else null) {
                Text("2 · Movement", style = MaterialTheme.typography.titleMedium, color = c.ink)
                Text(p.movement, color = c.body, style = MaterialTheme.typography.bodyMedium)
                Gap(8.dp)
                SecondaryButton(if (movement == null) "Capture (hold still 2 s)" else "Captured ✓ · redo", loading = capturing, enabled = reference != null) { scope.launch { capture { movement = it } } }
            }
            Gap(16.dp)
            PrimaryButton("Send", enabled = reference != null && movement != null, loading = sending) {
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
                if (!r.steady) Text("The phone moved during a hold. Try again with the phone resting still.", color = c.riskHigh)
            }
            Gap()
            PrimaryButton("Another joint") { result = null; reference = null; movement = null }
            Gap(8.dp)
            SecondaryButton("Back to Measure") { nav.popBackStack() }
        }
        Gap(24.dp)
    }
}
