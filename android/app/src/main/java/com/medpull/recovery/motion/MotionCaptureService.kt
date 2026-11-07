package com.medpull.recovery.motion

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import com.medpull.recovery.MainActivity
import com.medpull.recovery.MedPullApp
import com.medpull.recovery.R
import com.medpull.recovery.core.AppConfig
import com.medpull.recovery.core.MotionUpload
import com.medpull.recovery.features.measure.Stature
import java.util.Locale
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

enum class CaptureState { IDLE, RUNNING, DONE }

/**
 * Keeps the sensors alive for the length of a Measure test (or a passive
 * walking bout) with a quiet ongoing notification showing the clock, and
 * stops itself at the time limit. A guided test leaves the recorder for the
 * screen to upload; a free-living bout uploads itself.
 */
class MotionCaptureService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var ticker: Job? = null
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> { finish(); return START_NOT_STICKY }
            else -> {
                val durationS = intent?.getIntExtra(EXTRA_DURATION_S, 180) ?: 180
                val outdoors = intent?.getBooleanExtra(EXTRA_OUTDOORS, false) ?: false
                val title = intent?.getStringExtra(EXTRA_TITLE) ?: "Measure test"
                freeLiving = intent?.getBooleanExtra(EXTRA_FREE_LIVING, false) ?: false
                begin(title, durationS, outdoors)
            }
        }
        return START_NOT_STICKY
    }

    private fun begin(title: String, durationS: Int, outdoors: Boolean) {
        val recorder = MotionRecorder(applicationContext)
        current = recorder
        _state.value = CaptureState.RUNNING
        val notification = notification(title, "Starting…")
        if (Build.VERSION.SDK_INT >= 34) startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH)
        else startForeground(NOTIFICATION_ID, notification)
        wakeLock = getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "medpull:measure").apply {
            acquire((durationS + 30) * 1000L)
        }
        recorder.start(outdoors)
        ticker?.cancel()
        ticker = scope.launch {
            var seconds = 0
            while (isActive) {
                delay(1000)
                seconds += 1
                if (seconds % 60 == 0) recorder.closeMinute()
                val mm = seconds / 60; val ss = seconds % 60
                // A passive bout stays quiet: its line in the shade only moves every half minute.
                if (!freeLiving || seconds % 30 == 0)
                    notify(title, String.format(Locale.getDefault(), "%d:%02d · %d steps", mm, ss, recorder.steps))
                if (seconds >= durationS) { finish(); break }
            }
        }
    }

    private fun finish() {
        ticker?.cancel(); ticker = null
        val recorder = current
        recorder?.stop()
        _state.value = CaptureState.DONE
        wakeLock?.let { if (it.isHeld) it.release() }; wakeLock = null
        if (freeLiving && recorder != null) {
            // Nobody is watching: hand the bout to WorkManager, which outlives
            // this service and the process and waits for a network.
            val window = recorder.window("free_living", null)
            freeLiving = false
            current = null
            _state.value = CaptureState.IDLE
            if (window != null) {
                val upload = MotionUpload(listOf(window), Stature.get(applicationContext), AppConfig.deviceName)
                MotionUploadWorker.enqueue(applicationContext, upload, (application as MedPullApp).graph.api.json)
            }
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun notify(title: String, text: String) {
        getSystemService(android.app.NotificationManager::class.java).notify(NOTIFICATION_ID, notification(title, text))
    }

    private fun notification(title: String, text: String): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, MotionCaptureService::class.java).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE)
        val b = NotificationCompat.Builder(this, MedPullApp.CHANNEL_MOTION)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(title).setContentText(text).setOnlyAlertOnce(true).setSilent(true)
            .setContentIntent(open)
            .setPriority(NotificationCompat.PRIORITY_MIN)
        if (freeLiving) {
            // Nobody asked for this one: let Android hold it back for its first seconds (no action
            // buttons, or it shows at once) and let the person swipe it away; the capture carries on.
            b.setOngoing(false).setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_DEFERRED)
        } else {
            b.setOngoing(true).addAction(0, "Stop", stop)
                .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
        }
        return b.build()
    }

    override fun onDestroy() { ticker?.cancel(); wakeLock?.let { if (it.isHeld) it.release() }; super.onDestroy() }

    companion object {
        const val ACTION_STOP = "com.medpull.recovery.motion.STOP"
        const val EXTRA_DURATION_S = "duration_s"
        const val EXTRA_OUTDOORS = "outdoors"
        const val EXTRA_TITLE = "title"
        const val EXTRA_FREE_LIVING = "free_living"
        private const val NOTIFICATION_ID = 41

        /** The recorder of the current or last test, read by the Measure screens. */
        @Volatile var current: MotionRecorder? = null; private set
        @Volatile var freeLiving: Boolean = false; private set
        private val _state = MutableStateFlow(CaptureState.IDLE)
        val state: StateFlow<CaptureState> = _state

        fun start(context: Context, title: String, durationS: Int, outdoors: Boolean, freeLiving: Boolean = false) {
            _state.value = CaptureState.IDLE
            val intent = Intent(context, MotionCaptureService::class.java)
                .putExtra(EXTRA_TITLE, title).putExtra(EXTRA_DURATION_S, durationS).putExtra(EXTRA_OUTDOORS, outdoors)
                .putExtra(EXTRA_FREE_LIVING, freeLiving)
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            context.startService(Intent(context, MotionCaptureService::class.java).setAction(ACTION_STOP))
        }

        fun reset() { current = null; _state.value = CaptureState.IDLE }
    }
}
