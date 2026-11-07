package com.medpull.recovery.features.profile

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.material3.Switch
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.medpull.recovery.MedPullApp
import com.medpull.recovery.R
import com.medpull.recovery.core.AppConfig
import com.medpull.recovery.core.AppModel
import com.medpull.recovery.core.Dates
import com.medpull.recovery.core.Reminders
import com.medpull.recovery.core.wearableLink
import com.medpull.recovery.health.HealthConnectState
import com.medpull.recovery.ui.AppearanceMode
import com.medpull.recovery.ui.BackBar
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Field
import com.medpull.recovery.ui.FlowChips
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
        BackBar(nav, stringResource(R.string.profile_title))
        if (me != null) {
            Panel {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Initials(me.patient.initials.ifBlank { me.patient.name }, size = 48.dp)
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text(me.patient.name, style = MaterialTheme.typography.titleLarge, color = c.ink)
                        Text(listOfNotNull(me.patient.procedureDisplay.takeIf { it.isNotBlank() }, me.patient.hospital?.name).joinToString(" · "),
                            color = c.muted, style = MaterialTheme.typography.bodyMedium)
                    }
                }
                Gap(8.dp)
                me.patient.surgeryDate?.let { ListRow(stringResource(R.string.profile_surgery), Dates.day(it)?.let { d -> Dates.monthDay(d) } ?: it) }
                me.patient.phoneMasked?.let { ListRow(stringResource(R.string.profile_mobile), it) }
                ListRow(stringResource(R.string.profile_enrolled), stringResource(R.string.n_days, me.patient.daysEnrolled))
            }
            Gap()
            if (me.patient.careTeam.isNotEmpty()) {
                Panel {
                    SectionTitle(stringResource(R.string.profile_your_care_team))
                    me.patient.careTeam.forEach { ListRow(it.name, it.role, leading = { Initials(it.name, size = 32.dp, tone = Tone.MISSING) }) }
                }
                Gap()
            }
            me.profiles?.takeIf { it.size > 1 }?.let { spaces ->
                Panel {
                    SectionTitle(stringResource(R.string.profile_spaces))
                    spaces.forEach { sp ->
                        ListRow(sp.label.ifBlank { sp.kind }, sp.detail, trailing = {
                            if (sp.current) StatusPill(stringResource(R.string.profile_current), Tone.BRAND) else PlainButton(stringResource(R.string.profile_switch)) {
                                scope.launch { try { app.switchSpace(sp.patientId) } catch (e: Exception) { app.note(e) } }
                            }
                        })
                    }
                }
                Gap()
            }
        }
        Panel {
            SectionTitle(stringResource(R.string.connections_title))
            ListRow(stringResource(R.string.profile_hc_wearables), if (me?.wearables?.deviceHealth?.connected == true) stringResource(R.string.connected) else stringResource(R.string.not_connected),
                onClick = { nav.navigate(Routes.CONNECTIONS) })
            Hairline()
            ListRow(stringResource(R.string.profile_app_permissions), stringResource(R.string.profile_app_permissions_body), onClick = {
                context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}")))
            })
        }
        Gap()
        AppearanceCard()
        Gap()
        Panel {
            SectionTitle(stringResource(R.string.profile_developer))
            Text(stringResource(R.string.profile_developer_body), color = c.muted, style = MaterialTheme.typography.bodyMedium)
            Gap(8.dp)
            Field(serverUrl, { serverUrl = it }, stringResource(R.string.profile_server_url))
            Gap(8.dp)
            Row {
                PlainButton(stringResource(R.string.save)) { app.config.baseUrl = serverUrl; scope.launch { app.refreshAll() } }
                PlainButton(stringResource(R.string.profile_default), color = c.muted) { serverUrl = app.config.defaultBaseUrl; app.config.baseUrl = ""; scope.launch { app.refreshAll() } }
            }
            Text(stringResource(R.string.profile_version, app.config.appVersion, AppConfig.deviceName), color = c.faint, style = MaterialTheme.typography.labelSmall)
        }
        Gap()
        SecondaryButton(stringResource(R.string.profile_sign_out), loading = signingOut) { scope.launch { signingOut = true; app.signOut() } }
        Guardrail()
        Gap(24.dp)
    }
}

/** Light, dark or system. Light is the default, as on the iPhone. */
@Composable
private fun AppearanceCard() {
    val context = LocalContext.current
    val appearance = (context.applicationContext as MedPullApp).graph.appearance
    val mode by appearance.mode.collectAsStateWithLifecycle()
    val modes = AppearanceMode.entries
    Panel {
        SectionTitle(stringResource(R.string.profile_appearance))
        Gap(8.dp)
        FlowChips(modes.map { stringResource(it.labelRes) }, modes.indexOf(mode)) { appearance.set(modes[it]) }
        Gap(6.dp)
        Text(stringResource(R.string.profile_appearance_body), color = MP.colors.muted, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
fun ConnectionsScreen(nav: NavHostController) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { app.refreshWearables(force = false, surface = false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        BackBar(nav, stringResource(R.string.connections_title))
        state.lastError?.let { ErrorBanner(it, onDismiss = { app.clearError() }); Gap() }
        HealthConnectCard(app)
        Gap()
        WearableLinkCard(app)
        Gap()
        PassiveWalksCard()
        Gap()
        ReminderCard()
        Gap()
        PlainButton(stringResource(R.string.refresh)) { scope.launch { app.refreshWearables(force = true) } }
        Gap(24.dp)
    }
}

@Composable
fun ReminderCard() {
    val context = LocalContext.current
    val c = MP.colors
    var hour by remember { mutableStateOf(Reminders.hour(context)) }
    val askNotify = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    Panel {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.reminder_title), style = MaterialTheme.typography.titleLarge, color = c.ink)
                Text(hour?.let { stringResource(R.string.reminder_every_day_at, hourLabel(it)) } ?: stringResource(R.string.reminder_off), color = c.body, style = MaterialTheme.typography.bodyMedium)
            }
            Switch(checked = hour != null, onCheckedChange = { on ->
                if (on) {
                    if (Build.VERSION.SDK_INT >= 33) askNotify.launch(Manifest.permission.POST_NOTIFICATIONS)
                    Reminders.set(context, 8); hour = 8
                } else { Reminders.set(context, null); hour = null }
            })
        }
        if (hour != null) {
            Gap(8.dp)
            FlowChips(listOf(7, 8, 9, 10, 18).map { hourLabel(it) }, listOf(7, 8, 9, 10, 18).indexOf(hour)) { i ->
                val h = listOf(7, 8, 9, 10, 18)[i]; Reminders.set(context, h); hour = h
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
    val askPermissions = rememberLauncherForActivityResult(contract) { deferred ->
        scope.launch {
            health.onPermissions(deferred.await())
            app.refreshWearables(force = true, surface = false); app.refreshMe(false)
        }
    }
    Panel {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.hc_title), style = MaterialTheme.typography.titleLarge, color = c.ink)
                Text(when (val s = hc) {
                    is HealthConnectState.Connected -> s.syncLine ?: stringResource(R.string.hc_connected_syncing)
                    is HealthConnectState.Failed -> s.message
                    HealthConnectState.Unavailable -> stringResource(R.string.hc_unavailable)
                    HealthConnectState.Connecting -> stringResource(R.string.hc_connecting)
                    else -> if (serverSays) stringResource(R.string.hc_connected) else stringResource(R.string.hc_intro)
                }, color = c.body, style = MaterialTheme.typography.bodyMedium)
            }
            if (connected) StatusPill(stringResource(R.string.connected), Tone.LOW)
        }
        Gap(10.dp)
        if (!ready) ErrorBanner(stringResource(R.string.hc_server_not_ready))
        else if (!connected) PrimaryButton(stringResource(R.string.today_connect_hc), loading = hc == HealthConnectState.Connecting) {
            scope.launch { if (health.signIn(app)) askPermissions.launch(Unit) }
        } else Row {
            PlainButton(stringResource(R.string.hc_sync_now)) { scope.launch { health.syncNow(); app.refreshWearables(force = true, surface = false) } }
            PlainButton(stringResource(R.string.hc_disconnect), color = c.muted) { scope.launch { health.disconnect(); app.refreshMe(false) } }
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
        SectionTitle(stringResource(R.string.wearables_title))
        if (devices.isEmpty()) Text(stringResource(R.string.wearables_none), color = c.muted, style = MaterialTheme.typography.bodyMedium)
        devices.forEach { d ->
            ListRow(d.model.ifBlank { d.provider }, d.lastSyncAt?.let { Dates.relative(it) }?.let { stringResource(R.string.wearable_last_sync, it) } ?: d.provider,
                trailing = { StatusPill(d.status.ifBlank { "linked" }, toneFor(d.status)) })
        }
        Gap(8.dp)
        SecondaryButton(if (devices.isEmpty()) stringResource(R.string.wearables_add) else stringResource(R.string.wearables_add_another), loading = linking,
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

/** "7 am", "6 pm". */
@Composable
private fun hourLabel(h: Int): String =
    stringResource(R.string.hour_label, if (h > 12) h - 12 else h, stringResource(if (h >= 12) R.string.pm else R.string.am))
