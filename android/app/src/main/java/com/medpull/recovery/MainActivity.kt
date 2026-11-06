package com.medpull.recovery

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import com.medpull.recovery.ui.MedPullTheme
import com.medpull.recovery.ui.RootView

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MedPullTheme { RootView() }
        }
        intent?.data?.let { (application as MedPullApp).graph.app.handle(it) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.data?.let { (application as MedPullApp).graph.app.handle(it) }
    }
}
