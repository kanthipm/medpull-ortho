package com.medpull.recovery

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import com.medpull.recovery.motion.PassiveCapture

class MedPullApp : Application() {
    lateinit var graph: AppGraph
        private set

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph(this)
        graph.health.restore()
        PassiveCapture.restore(this)
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_MOTION, getString(R.string.motion_channel), NotificationManager.IMPORTANCE_MIN).apply {
                description = getString(R.string.motion_channel_description)
                setShowBadge(false)
            }
        )
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_REMINDER, getString(R.string.reminder_channel), NotificationManager.IMPORTANCE_DEFAULT)
        )
    }

    companion object {
        const val CHANNEL_MOTION = "medpull.motion"
        const val CHANNEL_REMINDER = "medpull.reminder"
    }
}
