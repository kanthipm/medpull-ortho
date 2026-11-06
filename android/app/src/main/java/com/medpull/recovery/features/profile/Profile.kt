package com.medpull.recovery.features.profile

import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.browser.customtabs.CustomTabsIntent
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
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.medpull.recovery.MedPullApp
import com.medpull.recovery.core.AppConfig
import com.medpull.recovery.core.AppModel
import com.medpull.recovery.core.Dates
import com.medpull.recovery.core.wearableLink
import com.medpull.recovery.features.onboarding.Field
import com.medpull.recovery.health.HealthConnectState
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Guardrail
import com.medpull.recovery.ui.Hairline
import com.medpull.recovery.ui.Initials
import com.medpull.recovery.ui.ListRow
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PlainButton
import com.medpull.recovery.ui.PrimaryButton
import com.medpull.recovery.ui.Routes
import com.medpull.recovery.ui.SecondaryButton
import com.medpull.recovery.ui.SectionTitle
import com.medpull.recovery.ui.StatusPill
import com.medpull.recovery.ui.Tone
import com.medpull.recovery.ui.appModel
import com.medpull.recovery.ui.toneFor
import kotlinx.coroutines.launch

@Composable
private fun Bar(nav: NavHostController, title: String) {
    Row(Modifier.fillMaxWidth().height(52.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = MP.colors.ink) }
        Text(title, style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
    }
}

@Composable
fun ProfileScreen(nav: NavHostController) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val c = MP.colors
    val me = state.me
    var serverUrl by remember { mutableStateOf(app.config.baseUrl) }
    var signingOut by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        Bar(nav, "Profile")
        if (me != null) {
            Panel {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Initials(me.patient.initials.ifBlank { me.patient.name }, size = 48.dp)
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text(me.patient.name, style = MaterialTheme.typography.titleLarge, color = c.ink)
                        Text(listOfNotNull(me.patient.procedureDisplay.takeIf { it.isNotBlank() }, me.patient.hospital).joinToString(" · "),
                            color = c.muted, style = MaterialTheme.typography.bodyMedium)
                    }
                }
                Gap(8.dp)
                me.patient.surgeryDate?.let { ListRow("Surgery", Dates.day(it)?.let { d -> Dates.monthDay(d) } ?: it) }
                me.patient.phoneMasked?.let { ListRow("Mobile", it) }
                ListRow("Enrolled", "${me.patient.daysEnrolled} days")
            }
            Gap()
            if (me.patient.careTeam.isNotEmpty()) {
                Panel {
                    SectionTitle("Your care team")
                    me.patient.careTeam.forEach { ListRow(it.name, it.role, leading = { Initials(it.name, size = 32.dp, tone = Tone.MISSING) }) }
                }
                Gap()
            }
            me.profiles?.takeIf { it.size > 1 }?.let { spaces ->
                Panel {
                    SectionTitle("Spaces")
                    spaces.forEach { sp ->
                        ListRow(sp.label.ifBlank { sp.kind }, sp.detail, trailing = {
                            if (sp.current) StatusPill("Current", Tone.BRAND) else PlainButton("Switch") {
                                scope.launch { try { app.switchSpace(sp.patientId) } catch (e: Exception) { app.note(e) } }
                            }
                        })
                    }
                }
                Gap()
            }
        }
        Panel {
            SectionTitle("Connections")
            ListRow("Health Connect and wearables", if (me?.wearables?.deviceHealth?.connected == true) "Connected" else "Not connected",
                onClick = { nav.navigate(Routes.CONNECTIONS) })
            Hairline()
            ListRow("App permissions", "Motion, location, notifications", onClick = {
                context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}")))
            })
        }
        Gap()
        Panel {
            SectionTitle("Developer")
            Text("Where the app talks to. The emulator reaches a laptop at 10.0.2.2.", color = c.muted, style = MaterialTheme.typography.bodyMedium)
            Gap(8.dp)
            Field(serverUrl, { serverUrl = it }, "Server URL")
            Gap(8.dp)
            Row {
                PlainButton("Save") { app.config.baseUrl = serverUrl; scope.launch { app.refreshAll() } }
                PlainButton("Default", color = c.muted) { serverUrl = app.config.defaultBaseUrl; app.config.baseUrl = ""; scope.launch { app.refreshAll() } }
            }
            Text("Version ${app.config.appVersion} · ${AppConfig.deviceName}", color = c.faint, style = MaterialTheme.typography.labelSmall)
        }
        Gap()
        SecondaryButton("Sign out", loading = signingOut) { scope.launch { signingOut = true; app.signOut() } }
        Guardrail()
        Gap(24.dp)
    }
}

@Composable
fun ConnectionsScreen(nav: NavHostController) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { app.refreshWearables(force = false, surface = false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        Bar(nav, "Connections")
        state.lastError?.let { ErrorBanner(it, onDismiss = { app.clearError() }); Gap() }
        HealthConnectCard(app)
        Gap()
        WearableLinkCard(app)
        Gap()
        PassiveWalksCard()
        Gap()
        ReminderCard()
        Gap()
        PlainButton("Refresh") { scope.launch { app.refreshWearables(force = true) } }
        Gap(24.dp)
    }
}

/** Opt-in background walking bouts: the Android stand-in for Apple's passive gait. */
@Composable
fun PassiveWalksCard() {
    val context = LocalContext.current
    val c = MP.colors
    var enabled by remember { mutableStateOf(com.medpull.recovery.motion.PassiveCapture.isEnabled(context)) }
    val ask = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        if (grants[android.Manifest.permission.ACTIVITY_RECOGNITION] == true) {
            com.medpull.recovery.motion.PassiveCapture.setEnabled(context, true); enabled = true
        }
    }
    Panel {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Record walks automatically", style = MaterialTheme.typography.titleLarge, color = c.ink)
                Text("When your phone notices you walking, it records two minutes in a pocket and sends them to MedPull, at most once every half hour. A small notification shows while it records.",
                    color = c.body, style = MaterialTheme.typography.bodyMedium)
            }
            androidx.compose.material3.Switch(checked = enabled, onCheckedChange = { on ->
                if (on && !com.medpull.recovery.motion.PassiveCapture.hasPermission(context)) {
                    val wanted = mutableListOf(android.Manifest.permission.ACTIVITY_RECOGNITION)
                    if (android.os.Build.VERSION.SDK_INT >= 33) wanted += android.Manifest.permission.POST_NOTIFICATIONS
                    ask.launch(wanted.toTypedArray())
                } else { com.medpull.recovery.motion.PassiveCapture.setEnabled(context, on); enabled = on }
            })
        }
    }
}

@Composable
fun ReminderCard() {
    val context = LocalContext.current
    val c = MP.colors
    var hour by remember { mutableStateOf(com.medpull.recovery.core.Reminders.hour(context)) }
    val askNotify = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) { }
    Panel {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Daily reminder", style = MaterialTheme.typography.titleLarge, color = c.ink)
                Text(hour?.let { "Every day at ${if (it > 12) it - 12 else it} ${if (it >= 12) "pm" else "am"}" } ?: "Off", color = c.body, style = MaterialTheme.typography.bodyMedium)
            }
            androidx.compose.material3.Switch(checked = hour != null, onCheckedChange = { on ->
                if (on) {
                    if (android.os.Build.VERSION.SDK_INT >= 33) askNotify.launch(android.Manifest.permission.POST_NOTIFICATIONS)
                    com.medpull.recovery.core.Reminders.set(context, 8); hour = 8
                } else { com.medpull.recovery.core.Reminders.set(context, null); hour = null }
            })
        }
        if (hour != null) {
            Gap(8.dp)
            com.medpull.recovery.features.onboarding.FlowChips(listOf("7 am", "8 am", "9 am", "10 am", "6 pm"), listOf(7, 8, 9, 10, 18).indexOf(hour)) { i ->
                val h = listOf(7, 8, 9, 10, 18)[i]; com.medpull.recovery.core.Reminders.set(context, h); hour = h
            }
        }
    }
}

/** The phone's health store: Health Connect through Junction's SDK. */
@Composable
fun HealthConnectCard(app: AppModel) {
    val state by app.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val health = (context.applicationContext as MedPullApp).graph.health
    val hc by health.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    val serverSays = state.me?.wearables?.deviceHealth?.connected == true
    val ready = state.me?.features?.deviceHealth ?: false
    val connected = hc is HealthConnectState.Connected || serverSays
    val contract = remember { health.permissionContract() }
    val askPermissions = androidx.activity.compose.rememberLauncherForActivityResult(contract) { deferred ->
        scope.launch {
            health.onPermissions(deferred.await())
            app.refreshWearables(force = true, surface = false); app.refreshMe(false)
        }
    }
    Panel {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Health Connect", style = MaterialTheme.typography.titleLarge, color = c.ink)
                Text(when (val s = hc) {
                    is HealthConnectState.Connected -> s.syncLine ?: "Connected. Syncing in the background."
                    is HealthConnectState.Failed -> s.message
                    HealthConnectState.Unavailable -> "Health Connect is not available on this phone."
                    HealthConnectState.Connecting -> "Connecting…"
                    else -> if (serverSays) "Connected." else "Steps, sleep, heart rate and workouts from your phone and watch."
                }, color = c.body, style = MaterialTheme.typography.bodyMedium)
            }
            if (connected) StatusPill("Connected", Tone.LOW)
        }
        Gap(10.dp)
        if (!ready) ErrorBanner("The server isn't connected to its wearable service yet, so Health Connect can't be linked.")
        else if (!connected) PrimaryButton("Connect Health Connect", loading = hc == HealthConnectState.Connecting) {
            scope.launch { if (health.signIn(app)) askPermissions.launch(Unit) }
        } else Row {
            PlainButton("Sync now") { scope.launch { health.syncNow(); app.refreshWearables(force = true, surface = false) } }
            PlainButton("Disconnect", color = c.muted) { scope.launch { health.disconnect(); app.refreshMe(false) } }
        }
    }
}

/** Oura, Fitbit, Garmin and the rest, through Junction's hosted page. */
@Composable
fun WearableLinkCard(app: AppModel) {
    val state by app.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val c = MP.colors
    var linking by remember { mutableStateOf(false) }
    val devices = state.me?.wearables?.devices.orEmpty()
    Panel {
        SectionTitle("Wearables")
        if (devices.isEmpty()) Text("Nothing linked yet.", color = c.muted, style = MaterialTheme.typography.bodyMedium)
        devices.forEach { d ->
            ListRow(d.model.ifBlank { d.provider }, d.lastSyncAt?.let { "Last sync ${Dates.relative(it)}" } ?: d.provider,
                trailing = { StatusPill(d.status.ifBlank { "linked" }, toneFor(d.status)) })
        }
        Gap(8.dp)
        SecondaryButton(if (devices.isEmpty()) "Add a wearable" else "Add another", loading = linking,
            enabled = state.me?.features?.deviceHealth == true) {
            scope.launch {
                linking = true
                try {
                    val link = app.api.wearableLink()
                    CustomTabsIntent.Builder().build().launchUrl(context, Uri.parse(link.linkUrl))
                } catch (e: Exception) { app.note(e) }
                linking = false
            }
        }
    }
}
