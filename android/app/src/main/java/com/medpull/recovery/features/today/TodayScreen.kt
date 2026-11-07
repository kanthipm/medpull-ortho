package com.medpull.recovery.features.today

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChatBubbleOutline
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.DirectionsWalk
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.medpull.recovery.core.Dates
import com.medpull.recovery.core.Me
import com.medpull.recovery.core.RecoveryTask
import com.medpull.recovery.core.Tab
import com.medpull.recovery.features.measure.MeasureStatus
import com.medpull.recovery.features.profile.PassiveWalksNudge
import com.medpull.recovery.features.tasks.TaskRow
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.GradientTile
import com.medpull.recovery.ui.Guardrail
import com.medpull.recovery.ui.Hairline
import com.medpull.recovery.ui.Initials
import com.medpull.recovery.ui.ListRow
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PlainButton
import com.medpull.recovery.ui.PrimaryButton
import com.medpull.recovery.ui.Routes
import com.medpull.recovery.ui.StatusPill
import com.medpull.recovery.ui.Tone
import com.medpull.recovery.ui.appModel
import java.time.LocalDate
import java.time.LocalTime
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TodayScreen(nav: NavHostController) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    var refreshing by remember { mutableStateOf(false) }

    // A texted link or a message's button opened a task.
    LaunchedEffect(state.pendingTaskId, state.tasks) {
        val id = state.pendingTaskId ?: return@LaunchedEffect
        val task = (state.tasks.open + state.tasks.recent).firstOrNull { it.id == id } ?: return@LaunchedEffect
        app.consumePendingTask()
        nav.navigate(if (task.isCheckin) Routes.checkin(id) else Routes.task(id))
    }

    PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.refreshAll(); refreshing = false } }) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
            Row(Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("MEDPULL", style = MaterialTheme.typography.labelSmall, color = c.muted)
                    Text(greeting(state.me), style = MaterialTheme.typography.displaySmall, color = c.ink)
                    state.me?.let { Text(subtitle(it), style = MaterialTheme.typography.bodyLarge, color = c.body) }
                }
                state.me?.let { me ->
                    Box(Modifier.padding(start = 8.dp)) {
                        androidx.compose.material3.IconButton(onClick = { nav.navigate(Routes.PROFILE) }) { Initials(me.patient.initials.ifBlank { me.patient.name }) }
                    }
                }
            }
            state.lastError?.let { ErrorBanner(it, onDismiss = { app.clearError() }); Gap() }
            Gap(8.dp)
            state.me?.let { RecoveryHero(it) { app.selectTab(Tab.PROGRESS) } }
            Gap()
            PlanCard(state.tasks.open, doneToday(state.tasks.recent), nav) { task -> scope.launch { try { app.complete(task, emptyMap()) } catch (e: Exception) { app.note(e) } } }
            Gap()
            val due = MeasureStatus.due(state.portfolio)
            Panel(onClick = { app.selectTab(Tab.MEASURE) }) {
                ListRow("Measure", if (due.isEmpty()) "All tests are up to date" else "${due.joinToString(", ")} due",
                    leading = { Icon(Icons.Default.DirectionsWalk, null, tint = c.teal) })
            }
            Gap()
            CareRow(state.messages.lastOrNull { it.sender != "patient" }, state.me?.unreadMessages ?: 0, state.me) { app.selectTab(Tab.CARE) }
            Gap()
            val wear = state.me?.wearables
            if (wear != null && !wear.deviceHealth.connected && wear.devices.isEmpty() && state.me?.features?.deviceHealth == true) {
                Panel(tint = c.brandTint, onClick = { app.showConnections(true) }) {
                    ListRow("Connect your phone's health data", "Steps, sleep and heart rate from Health Connect",
                        leading = { Icon(Icons.Default.Favorite, null, tint = c.brandInk) })
                }
                Gap()
            }
            if (state.me?.isPersonal == false) { PassiveWalksNudge(); Gap() }
            Guardrail()
            Gap(24.dp)
        }
    }
}

/** "Day 12 · Knee replacement" for a recovery, "St Mary's · 4 days in" for a general programme. */
private fun subtitle(me: Me): String {
    val p = me.patient
    if (p.isRecovery) return listOfNotNull(p.postopDay?.let { "Day $it" }, p.procedureDisplay.takeIf { it.isNotBlank() }).joinToString(" · ")
    val since = if (p.daysEnrolled == 0) "joined today" else "${p.daysEnrolled} days in"
    return listOfNotNull(p.hospital?.name, since).joinToString(" · ")
}

/** Tasks finished today, from the recent list. */
private fun doneToday(recent: List<RecoveryTask>): List<RecoveryTask> =
    recent.filter { t -> Dates.parse(t.completedAt)?.toLocalDate() == LocalDate.now() }

private fun greeting(me: Me?): String {
    val hour = LocalTime.now().hour
    val part = when { hour < 12 -> "Good morning"; hour < 18 -> "Good afternoon"; else -> "Good evening" }
    val name = me?.patient?.firstName?.takeIf { it.isNotBlank() }
    return if (name != null) "$part, $name" else part
}

@Composable
fun RecoveryHero(me: Me, onClick: () -> Unit) {
    val rec = me.recovery
    val pct = rec.trajectory.pct
    val day = me.patient.postopDay
    val (kicker, value, unit) = when {
        pct != null && rec.trajectory.state != "unknown" -> Triple("Vs. expected", (if (pct >= 0) "+" else "") + "${pct.toInt()}", "%")
        day != null -> Triple("Post-op day", "D$day", null)
        else -> Triple("Days of data", "${rec.daysWithData ?: me.patient.daysEnrolled}", null)
    }
    GradientTile(kicker, value, unit, caption = listOfNotNull(rec.label.takeIf { it.isNotBlank() }, rec.blurb.takeIf { it.isNotBlank() }).joinToString(". "),
        onClick = onClick)
}

/** Today's plan: the check-in as the one primary action, every other open
 *  task as a row, what is already done folded away underneath. */
@Composable
private fun PlanCard(open: List<RecoveryTask>, done: List<RecoveryTask>, nav: NavHostController, markDone: (RecoveryTask) -> Unit) {
    val c = MP.colors
    val checkin = open.firstOrNull { it.isCheckin }
    val others = open.filter { !it.isCheckin }
    var showDone by remember { mutableStateOf(false) }
    Panel {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Today's plan", style = MaterialTheme.typography.titleMedium, color = c.ink)
            if (open.isNotEmpty() || done.isNotEmpty()) {
                Spacer(Modifier.width(8.dp))
                Text("${done.size} of ${open.size + done.size} done", style = MaterialTheme.typography.labelMedium, color = c.muted)
            }
            Spacer(Modifier.weight(1f))
            PlainButton("All tasks") { nav.navigate(Routes.HISTORY) }
        }
        Gap(8.dp)
        if (open.isEmpty()) {
            Text(if (done.isEmpty()) "Nothing waiting" else "All done for today", style = MaterialTheme.typography.bodyLarge, color = c.ink)
            Text(if (done.isEmpty()) "New tasks from your care team show up here." else "Your care team will see what you did with their next review.",
                style = MaterialTheme.typography.bodyMedium, color = c.muted)
        }
        if (checkin != null) {
            PrimaryButton("Start today's check-in") { nav.navigate(Routes.checkin(checkin.id)) }
            Gap(4.dp)
            Text(if (checkin.inSmsConversation) "You started this by text. Finishing it here is fine." else "About two minutes. Every question can be skipped.",
                style = MaterialTheme.typography.labelMedium, color = c.muted)
            Gap(8.dp)
        }
        others.forEachIndexed { i, t ->
            TaskRow(t, onOpen = { nav.navigate(Routes.task(t.id)) }, onDone = if (t.questions.isEmpty()) ({ markDone(t) }) else null)
            if (i < others.lastIndex) Hairline()
        }
        if (done.isNotEmpty()) {
            Hairline()
            Row(Modifier.fillMaxWidth().clickable { showDone = !showDone }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.CheckCircle, null, tint = c.riskLow)
                Spacer(Modifier.width(8.dp))
                Text("Done today", style = MaterialTheme.typography.bodyLarge, color = c.ink)
                Spacer(Modifier.width(6.dp))
                Text("${done.size}", style = MaterialTheme.typography.bodyLarge, color = c.muted)
                Spacer(Modifier.weight(1f))
                Icon(if (showDone) Icons.Default.ExpandLess else Icons.Default.ExpandMore, if (showDone) "Collapse" else "Expand", tint = c.muted)
            }
            if (showDone) done.forEach { t -> Hairline(); TaskRow(t, onOpen = { nav.navigate(Routes.task(t.id)) }) }
        }
    }
}

@Composable
private fun CareRow(last: com.medpull.recovery.core.ChatMessage?, unread: Int, me: Me?, onClick: () -> Unit) {
    val c = MP.colors
    Panel(onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.ChatBubbleOutline, null, tint = c.brandInk)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("Care team", style = MaterialTheme.typography.titleMedium, color = c.ink)
                val team = me?.patient?.careTeam.orEmpty()
                Text(last?.text?.takeIf { it.isNotBlank() }
                    ?: team.takeIf { it.isNotEmpty() }?.joinToString(", ") { it.name }
                    ?: "Write to your care team, or tell MedPull how you feel.",
                    style = MaterialTheme.typography.bodyMedium, color = c.muted, maxLines = 2)
            }
            if (unread > 0) StatusPill("$unread new", Tone.BRAND)
        }
    }
}
