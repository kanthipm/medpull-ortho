package com.medpull.recovery.motion

import android.Manifest
import android.annotation.SuppressLint
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import com.google.android.gms.location.ActivityRecognition
import com.google.android.gms.location.ActivityTransition
import com.google.android.gms.location.ActivityTransitionRequest
import com.google.android.gms.location.ActivityTransitionResult
import com.google.android.gms.location.DetectedActivity

/**
 * The Android answer to Apple's passive daily gait: when the phone notices
 * the person has started walking, record a short window in the background
 * and upload it as a free-living bout for the same algorithm the guided
 * walk uses. Opt-in from Connections, at most one capture every half hour,
 * and only when the phone is signed in.
 */
object PassiveCapture {
    private const val PREFS = "medpull.passive"
    private const val KEY_ENABLED = "enabled"
    private const val KEY_LAST = "last_capture_ms"
    const val WINDOW_S = 120
    const val COOLDOWN_MS = 30L * 60 * 1000
    private const val ACTION = "com.medpull.recovery.motion.ACTIVITY_TRANSITION"

    fun isEnabled(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY_ENABLED, false)

    fun hasPermission(context: Context) =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACTIVITY_RECOGNITION) == PackageManager.PERMISSION_GRANTED

    @SuppressLint("MissingPermission")
    fun setEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(KEY_ENABLED, enabled).apply()
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

    private fun pendingIntent(context: Context): PendingIntent {
        val intent = Intent(context, WalkReceiver::class.java).setAction(ACTION)
        return PendingIntent.getBroadcast(context, 7, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE)
    }

    fun noteCapture(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putLong(KEY_LAST, System.currentTimeMillis()).apply()

    fun cooledDown(context: Context) =
        System.currentTimeMillis() - context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getLong(KEY_LAST, 0) > COOLDOWN_MS

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
            if (started && isEnabled(context) && cooledDown(context) && MotionCaptureService.state.value != CaptureState.RUNNING) {
                noteCapture(context)
                MotionCaptureService.start(context, "Recording your walk", WINDOW_S, outdoors = false, freeLiving = true)
            } else if (stopped && MotionCaptureService.state.value == CaptureState.RUNNING && MotionCaptureService.freeLiving) {
                MotionCaptureService.stop(context)
            }
        }
    }
}
