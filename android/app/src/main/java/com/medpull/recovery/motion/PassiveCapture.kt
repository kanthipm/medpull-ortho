package com.medpull.recovery.motion

import android.Manifest
import android.annotation.SuppressLint
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.ContextCompat
import com.google.android.gms.location.ActivityRecognition
import com.google.android.gms.location.ActivityTransition
import com.google.android.gms.location.ActivityTransitionRequest
import com.google.android.gms.location.ActivityTransitionResult
import com.google.android.gms.location.DetectedActivity
import com.medpull.recovery.core.Reminders

/**
 * The Android answer to Apple's passive daily gait: when the phone notices
 * the person has started walking, record a short window in the background
 * and upload it as a free-living bout for the same algorithm the guided
 * walk uses. On by default once the person grants the Physical Activity
 * permission (asked during onboarding, nudged from Today until then); off
 * from Connections. At most one capture every half hour, only when signed in.
 */
object PassiveCapture {
    private const val PREFS = "medpull.passive"
    private const val KEY_ENABLED = "enabled"
    private const val KEY_ASKED = "asked"
    private const val KEY_LAST = "last_capture_ms"
    const val WINDOW_S = 120
    const val COOLDOWN_MS = 30L * 60 * 1000
    private const val ACTION = "com.medpull.recovery.motion.ACTIVITY_TRANSITION"

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** The person's choice; defaults to on so the first grant switches capture on. */
    fun isEnabled(context: Context) = prefs(context).getBoolean(KEY_ENABLED, true)

    fun hasPermission(context: Context) =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACTIVITY_RECOGNITION) == PackageManager.PERMISSION_GRANTED

    /** Capturing right now: wanted and allowed. */
    fun isActive(context: Context) = isEnabled(context) && hasPermission(context)

    /** Whether the system dialog has been shown at least once, to tell "never asked" from "denied twice". */
    fun wasAsked(context: Context) = prefs(context).getBoolean(KEY_ASKED, false)
    fun markAsked(context: Context) = prefs(context).edit().putBoolean(KEY_ASKED, true).apply()

    /** What the system dialog has to grant: activity, and on 13+ the notification the capture shows. */
    fun permissions(): Array<String> {
        val wanted = mutableListOf(Manifest.permission.ACTIVITY_RECOGNITION)
        if (Build.VERSION.SDK_INT >= 33) wanted += Manifest.permission.POST_NOTIFICATIONS
        return wanted.toTypedArray()
    }

    @SuppressLint("MissingPermission")
    fun setEnabled(context: Context, enabled: Boolean) {
        prefs(context).edit().putBoolean(KEY_ENABLED, enabled).apply()
        val client = ActivityRecognition.getClient(context)
        val pending = pendingIntent(context)
        if (enabled && hasPermission(context)) {
            val transitions = listOf(
                ActivityTransition.Builder().setActivityType(DetectedActivity.WALKING)
                    .setActivityTransition(ActivityTransition.ACTIVITY_TRANSITION_ENTER).build(),
                ActivityTransition.Builder().setActivityType(DetectedActivity.WALKING)
                    .setActivityTransition(ActivityTransition.ACTIVITY_TRANSITION_EXIT).build(),
            )
            client.requestActivityTransitionUpdates(ActivityTransitionRequest(transitions), pending)
        } else {
            client.removeActivityTransitionUpdates(pending)
        }
    }

    /** Re-register after a reboot or a process start; transition requests do not survive a reboot. */
    fun restore(context: Context) { if (isActive(context)) setEnabled(context, true) }

    /** After two denials Android stops showing the dialog, so the only way on is the app's settings page. */
    fun openSettings(context: Context) {
        val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
    }

    private fun pendingIntent(context: Context): PendingIntent {
        val intent = Intent(context, WalkReceiver::class.java).setAction(ACTION)
        return PendingIntent.getBroadcast(context, 7, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE)
    }

    fun noteCapture(context: Context) = prefs(context).edit().putLong(KEY_LAST, System.currentTimeMillis()).apply()

    fun cooledDown(context: Context) = System.currentTimeMillis() - prefs(context).getLong(KEY_LAST, 0) > COOLDOWN_MS

    class WalkReceiver : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (!ActivityTransitionResult.hasResult(intent)) return
            val result = ActivityTransitionResult.extractResult(intent) ?: return
            val started = result.transitionEvents.any {
                it.activityType == DetectedActivity.WALKING && it.transitionType == ActivityTransition.ACTIVITY_TRANSITION_ENTER
            }
            val stopped = result.transitionEvents.any {
                it.activityType == DetectedActivity.WALKING && it.transitionType == ActivityTransition.ACTIVITY_TRANSITION_EXIT
            }
            if (started && isActive(context) && cooledDown(context) && MotionCaptureService.state.value != CaptureState.RUNNING) {
                noteCapture(context)
                MotionCaptureService.start(context, "Recording your walk", WINDOW_S, outdoors = false, freeLiving = true)
            } else if (stopped && MotionCaptureService.state.value == CaptureState.RUNNING && MotionCaptureService.freeLiving) {
                MotionCaptureService.stop(context)
            }
        }
    }

    /** Boot: walking-transition requests and alarms are cleared by the system, so put them back. */
    class BootReceiver : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
            restore(context)
            Reminders.hour(context)?.let { Reminders.set(context, it) }
        }
    }
}
