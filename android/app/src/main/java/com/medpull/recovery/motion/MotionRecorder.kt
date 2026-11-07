package com.medpull.recovery.motion

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.location.Location
import android.os.Looper
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.medpull.recovery.core.Dates
import com.medpull.recovery.core.MotionWindowUpload
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.time.Instant
import kotlin.math.pow
import kotlin.math.roundToInt

data class LiveStats(
    val elapsedS: Double = 0.0, val samples: Int = 0, val steps: Int = 0, val distanceM: Double? = null,
    val gpsAccuracyM: Double? = null, val hasGyro: Boolean = false, val hasBarometer: Boolean = false,
)

/**
 * Records the window the server computes gait from: the raw accelerometer
 * (reaction force, m/s², gravity included), gyroscope (rad/s), the gravity
 * vector, per-sample timestamps, relative altitude from the barometer, the
 * phone's step counter per minute and, outdoors, GPS distance. Nothing is
 * computed here; the server converts the Android frame (`platform: android`).
 *
 * Gyro and gravity are sampled-and-held onto the accelerometer's clock so
 * the three arrays have one row per accelerometer sample, which the API
 * requires.
 */
class MotionRecorder(private val context: Context) : SensorEventListener {
    private val sm = context.getSystemService(SensorManager::class.java)
    private val accelSensor = sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroSensor = sm.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
    private val gravitySensor = sm.getDefaultSensor(Sensor.TYPE_GRAVITY)
    private val pressureSensor = sm.getDefaultSensor(Sensor.TYPE_PRESSURE)
    private val stepSensor = sm.getDefaultSensor(Sensor.TYPE_STEP_COUNTER)

    private val accel = ArrayList<FloatArray>(MAX_SAMPLES)
    private val gyro = ArrayList<FloatArray>(MAX_SAMPLES)
    private val gravity = ArrayList<FloatArray>(MAX_SAMPLES)
    private val timestamps = ArrayList<Double>(MAX_SAMPLES)
    private val altitude = ArrayList<DoubleArray>()
    private var lastGyro: FloatArray? = null
    private var lastGravity: FloatArray? = null
    private var t0Ns = -1L
    private var lastPressureAtNs = -1L
    private var p0: Float? = null
    private var stepBase = -1
    private var stepsNow = 0
    private val minuteSteps = ArrayList<Int>()
    private var lastMinuteStepTotal = 0
    private var gpsDistance = 0.0
    private var gpsAccuracies = ArrayList<Double>()
    private var lastLocation: Location? = null
    private var fused: FusedLocationProviderClient? = null
    private var locationCallback: LocationCallback? = null
    var startedAt: Instant = Instant.now(); private set
    var running = false; private set

    private val _live = MutableStateFlow(LiveStats(hasGyro = gyroSensor != null, hasBarometer = pressureSensor != null))
    val live: StateFlow<LiveStats> = _live

    val hasGyroscope get() = gyroSensor != null
    val hasBarometer get() = pressureSensor != null

    @SuppressLint("MissingPermission")
    fun start(outdoors: Boolean) {
        if (running) return
        running = true
        startedAt = Instant.now()
        accel.clear(); gyro.clear(); gravity.clear(); timestamps.clear(); altitude.clear(); minuteSteps.clear()
        lastGyro = null; lastGravity = null; t0Ns = -1; p0 = null; stepBase = -1; stepsNow = 0; lastMinuteStepTotal = 0
        gpsDistance = 0.0; gpsAccuracies.clear(); lastLocation = null
        accelSensor?.let { sm.registerListener(this, it, SAMPLE_PERIOD_US) }
        gyroSensor?.let { sm.registerListener(this, it, SAMPLE_PERIOD_US) }
        gravitySensor?.let { sm.registerListener(this, it, SAMPLE_PERIOD_US) }
        pressureSensor?.let { sm.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL) }
        stepSensor?.let { sm.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL) }
        if (outdoors) {
            val client = LocationServices.getFusedLocationProviderClient(context).also { fused = it }
            val cb = object : LocationCallback() {
                override fun onLocationResult(result: LocationResult) {
                    for (loc in result.locations) {
                        if (!loc.hasAccuracy() || loc.accuracy > 20f) continue
                        lastLocation?.let { gpsDistance += it.distanceTo(loc) }
                        lastLocation = loc
                        gpsAccuracies.add(loc.accuracy.toDouble())
                    }
                    publish()
                }
            }.also { locationCallback = it }
            val req = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 1000L).setMinUpdateDistanceMeters(2f).build()
            client.requestLocationUpdates(req, cb, Looper.getMainLooper())
        }
    }

    fun stop() {
        if (!running) return
        running = false
        sm.unregisterListener(this)
        locationCallback?.let { fused?.removeLocationUpdates(it) }
        locationCallback = null; fused = null
        // The partial last minute, unless the ticker closed one within the
        // last few seconds (a walk that ran to its limit ends on a boundary).
        val elapsed = timestamps.lastOrNull() ?: 0.0
        if (elapsed - minuteSteps.size * 60.0 > 5.0) closeMinute()
        publish()
    }

    /** Called by the service's ticker once a minute to bucket the step counter. */
    fun closeMinute() { minuteSteps.add(stepsNow - lastMinuteStepTotal); lastMinuteStepTotal = stepsNow }

    override fun onSensorChanged(e: SensorEvent) {
        when (e.sensor.type) {
            Sensor.TYPE_GYROSCOPE -> lastGyro = e.values.clone()
            Sensor.TYPE_GRAVITY -> lastGravity = e.values.clone()
            Sensor.TYPE_ACCELEROMETER -> {
                if (accel.size >= MAX_SAMPLES) return
                if (t0Ns < 0) t0Ns = e.timestamp
                accel.add(e.values.clone())
                gyro.add(lastGyro ?: ZERO)
                gravity.add(lastGravity ?: unit(e.values))
                timestamps.add((e.timestamp - t0Ns) / 1e9)
                if (accel.size % 25 == 0) publish()
            }
            Sensor.TYPE_PRESSURE -> {
                val p = e.values[0]
                val base = p0 ?: p.also { p0 = it }
                if (t0Ns < 0 || e.timestamp - lastPressureAtNs < 400_000_000L) return
                lastPressureAtNs = e.timestamp
                // Standard atmosphere, relative to the first reading.
                val h = 44330.0 * (1.0 - (p / base).toDouble().pow(1.0 / 5.255))
                altitude.add(doubleArrayOf((e.timestamp - t0Ns) / 1e9, h))
            }
            Sensor.TYPE_STEP_COUNTER -> {
                val total = e.values[0].roundToInt()
                if (stepBase < 0) stepBase = total
                stepsNow = total - stepBase
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    private fun publish() {
        _live.value = LiveStats(
            elapsedS = timestamps.lastOrNull() ?: 0.0, samples = accel.size, steps = stepsNow,
            distanceM = if (lastLocation != null) gpsDistance else null,
            gpsAccuracyM = gpsAccuracies.takeIf { it.isNotEmpty() }?.average(),
            hasGyro = gyroSensor != null, hasBarometer = pressureSensor != null,
        )
    }

    val steps get() = stepsNow
    val minuteStepCounts: List<Int> get() = minuteSteps.toList()
    val gpsDistanceM: Double? get() = if (lastLocation != null) gpsDistance else null
    val gpsAccuracyM: Double? get() = gpsAccuracies.takeIf { it.isNotEmpty() }?.average()
    val sampleCount get() = accel.size

    /** The upload payload, or null when the window is too short to score. */
    fun window(context: String, pocketSide: String?): MotionWindowUpload? {
        if (accel.size < 50) return null
        val n = accel.size
        val fs = if (n > 1) (n - 1) / (timestamps[n - 1] - timestamps[0]).coerceAtLeast(1e-3) else 50.0
        return MotionWindowUpload(
            startedAt = Dates.iso(startedAt), sampleRateHz = fs.coerceIn(5.0, 200.0),
            accel = accel.map { r3(it) },
            gyro = if (gyroSensor != null) gyro.map { r3(it) } else null,
            gravity = if (gravitySensor != null) gravity.map { r3(it) } else null,
            timestamps = timestamps.map { Math.round(it * 1000.0) / 1000.0 },
            altitude = altitude.takeIf { it.isNotEmpty() }?.map { listOf(Math.round(it[0] * 100.0) / 100.0, Math.round(it[1] * 1000.0) / 1000.0) },
            gpsDistanceM = gpsDistanceM, gpsAccuracyM = gpsAccuracyM,
            pedometerSteps = if (stepSensor != null) stepsNow else null, pedometerDistanceM = null,
            pocketSide = pocketSide, context = context, platform = "android",
        )
    }

    companion object {
        const val MAX_SAMPLES = 36_000
        const val SAMPLE_PERIOD_US = 20_000
        private val ZERO = floatArrayOf(0f, 0f, 0f)
        private fun unit(v: FloatArray): FloatArray {
            val n = kotlin.math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).takeIf { it > 0 } ?: 1f
            return floatArrayOf(v[0] / n, v[1] / n, v[2] / n)
        }
        private fun r3(v: FloatArray) = listOf(Math.round(v[0] * 1000.0) / 1000.0, Math.round(v[1] * 1000.0) / 1000.0, Math.round(v[2] * 1000.0) / 1000.0)
    }
}
