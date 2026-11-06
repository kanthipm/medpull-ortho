package com.medpull.recovery.core

import android.app.AlarmManager
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.medpull.recovery.MainActivity
import com.medpull.recovery.MedPullApp
import com.medpull.recovery.R
import java.util.Calendar

/** One repeating local reminder a day, at the hour the person picks. No push. */
object Reminders {
    private const val PREFS = "medpull.reminders"
    private const val KEY_HOUR = "hour"
    private const val REQUEST = 9

    fun hour(context: Context): Int? = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getInt(KEY_HOUR, -1).takeIf { it >= 0 }

    fun set(context: Context, hour: Int?) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val am = context.getSystemService(AlarmManager::class.java)
        val pending = PendingIntent.getBroadcast(context, REQUEST, Intent(context, Receiver::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        if (hour == null) { prefs.edit().remove(KEY_HOUR).apply(); am.cancel(pending); return }
        prefs.edit().putInt(KEY_HOUR, hour).apply()
        val at = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, hour); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0)
            if (before(Calendar.getInstance())) add(Calendar.DAY_OF_YEAR, 1)
        }
        am.setInexactRepeating(AlarmManager.RTC_WAKEUP, at.timeInMillis, AlarmManager.INTERVAL_DAY, pending)
    }

    class Receiver : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
            val n = NotificationCompat.Builder(context, MedPullApp.CHANNEL_REMINDER)
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle("Your check-in is waiting")
                .setContentText("Open MedPull for today's plan.")
                .setContentIntent(open).setAutoCancel(true).build()
            try { context.getSystemService(NotificationManager::class.java).notify(REQUEST, n) } catch (_: SecurityException) {}
        }
    }
}
