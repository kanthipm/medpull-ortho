package com.medpull.recovery.features.profile

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DirectionsWalk
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.app.ActivityCompat
import com.medpull.recovery.motion.PassiveCapture
import com.medpull.recovery.ui.ListRow
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.Panel

/**
 * One way to switch passive walks on, shared by onboarding, the Today nudge
 * and the Connections card. Asks the system for Physical Activity (and the
 * notification on 13+); after Android has stopped showing the dialog, opens
 * the app's settings page instead. The result lambda says whether capture is
 * now on.
 */
@Composable
fun rememberPassiveWalkEnabler(onResult: (Boolean) -> Unit): () -> Unit {
    val context = LocalContext.current
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        PassiveCapture.markAsked(context)
        val ok = grants[Manifest.permission.ACTIVITY_RECOGNITION] == true
        if (ok) PassiveCapture.setEnabled(context, true)
        onResult(ok)
    }
    return {
        when {
            PassiveCapture.hasPermission(context) -> { PassiveCapture.setEnabled(context, true); onResult(true) }
            PassiveCapture.wasAsked(context) && !canStillAsk(context) -> { PassiveCapture.openSettings(context); onResult(false) }
            else -> ask.launch(PassiveCapture.permissions())
        }
    }
}

private fun canStillAsk(context: Context): Boolean {
    val activity = context.activity() ?: return true
    return ActivityCompat.shouldShowRequestPermissionRationale(activity, Manifest.permission.ACTIVITY_RECOGNITION)
}

private fun Context.activity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.activity()
    else -> null
}

/** Connections: the on/off switch, with the settings page as the way back after a hard deny. */
@Composable
fun PassiveWalksCard() {
    val context = LocalContext.current
    val c = MP.colors
    var active by remember { mutableStateOf(PassiveCapture.isActive(context)) }
    val enable = rememberPassiveWalkEnabler { active = it }
    val blocked = !PassiveCapture.hasPermission(context) && PassiveCapture.wasAsked(context) && !canStillAsk(context)
    Panel {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Record walks automatically", style = MaterialTheme.typography.titleLarge, color = c.ink)
                Text(
                    if (blocked) "Physical activity is turned off for MedPull in your phone's settings. Switch it on there to record walks."
                    else "When your phone notices you walking, it records two minutes in a pocket and sends them to MedPull, at most once every half hour. A silent line shows in your notifications while it records; you can swipe it away.",
                    color = c.body, style = MaterialTheme.typography.bodyMedium,
                )
            }
            Switch(checked = active, onCheckedChange = { on ->
                if (on) enable() else { PassiveCapture.setEnabled(context, false); active = false }
            })
        }
    }
}

/** Today: shown until capture is on, so a skipped onboarding step or a revoked permission is one tap away. */
@Composable
fun PassiveWalksNudge() {
    val context = LocalContext.current
    val c = MP.colors
    var active by remember { mutableStateOf(PassiveCapture.isActive(context)) }
    if (active) return
    val enable = rememberPassiveWalkEnabler { active = it }
    Panel(tint = c.brandTint, onClick = enable) {
        ListRow("Record walks automatically", "Your walks aren't being measured between tests. Turn on",
            leading = { Icon(Icons.Default.DirectionsWalk, null, tint = c.brandInk) })
    }
}
