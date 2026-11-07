package com.medpull.recovery.features.today

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.DirectionsWalk
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Forum
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.QuestionAnswer
import androidx.compose.material.icons.outlined.RemoveCircleOutline
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.medpull.recovery.R
import com.medpull.recovery.core.CareTeamMember
import com.medpull.recovery.core.Dates
import com.medpull.recovery.core.Me
import com.medpull.recovery.core.RecoveryTask
import com.medpull.recovery.core.Tab
import com.medpull.recovery.features.measure.MeasureStatus
import com.medpull.recovery.features.profile.PassiveWalksNudge
import com.medpull.recovery.features.tasks.taskIcon
import com.medpull.recovery.ui.CapsuleShape
import com.medpull.recovery.ui.CardTitleRow
import com.medpull.recovery.ui.Category
import com.medpull.recovery.ui.Chevron
import com.medpull.recovery.ui.EmptyRow
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Glyph
import com.medpull.recovery.ui.GradientTile
import com.medpull.recovery.ui.Guardrail
import com.medpull.recovery.ui.Initials
import com.medpull.recovery.ui.InsetDivider
import com.medpull.recovery.ui.ListRow
import com.medpull.recovery.ui.Lockup
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.MPType
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PrimaryButton
import com.medpull.recovery.ui.RecoveryCurveArt
import com.medpull.recovery.ui.Routes
import com.medpull.recovery.ui.RowDivider
import com.medpull.recovery.ui.StateLabel
import com.medpull.recovery.ui.StatusPill
import com.medpull.recovery.ui.Tone
import com.medpull.recovery.ui.appModel
import com.medpull.recovery.ui.toneFor
import java.time.LocalDate
import kotlinx.coroutines.launch

/** "Day 8 · Total Knee Replacement": the dot held off each word by thin spaces, as on the iPhone. */
const val DOT = "  ·  "

/**
 * A hospital patient's day, in the order they ask about it: how am I doing
 * (the recovery hero), what do I do now (the plan), is a measurement due,
 * and has my care team said anything. Mirrors ios TodayView.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TodayScreen(nav: NavHostController) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    var refreshing by remember { mutableStateOf(false) }
    var quickError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(state.pendingTaskId, state.tasks) {
        val id = state.pendingTaskId ?: return@LaunchedEffect
        val task = (state.tasks.open + state.tasks.recent).firstOrNull { it.id == id } ?: return@LaunchedEffect
        app.consumePendingTask()
        nav.navigate(if (task.isCheckin) Routes.checkin(id) else Routes.task(id))
    }

    Box(Modifier.fillMaxSize()) {
        PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.refreshAll(); refreshing = false } }) {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                Row(Modifier.fillMaxWidth().padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Lockup()
                    Spacer(Modifier.weight(1f))
                    state.me?.let { me ->
                        Box(Modifier.size(44.dp).clip(CircleShape).clickable { nav.navigate(Routes.PROFILE) }, contentAlignment = Alignment.Center) {
                            Initials(me.patient.initials.ifBlank { me.patient.name }, size = 36.dp)
                        }
                    }
                }
                Greeting(state.me)
                state.me?.let { RecoveryHero(it) { app.selectTab(Tab.PROGRESS) } }
                PlanCard(state.tasks.open, state.tasks.recent, nav,
                    markDone = { task -> scope.launch { try { quickError = null; app.complete(task, emptyMap()) } catch (e: Exception) { quickError = e.message } } },
                    onHistory = { nav.navigate(Routes.HISTORY) })
                MeasureRow(state.portfolio.let { MeasureStatus.due(it) }) { app.selectTab(Tab.MEASURE) }
                CareRow(state.messages.lastOrNull { it.sender != "patient" }?.text, state.me?.unreadMessages ?: 0, state.me?.patient?.careTeam.orEmpty()) { app.selectTab(Tab.CARE) }
                val wear = state.me?.wearables
                if (wear != null && !wear.deviceHealth.connected && wear.devices.isEmpty() && state.me?.features?.deviceHealth == true) {
                    Panel(padding = 0.dp, onClick = { app.showConnections(true) }) {
                        ListRow(stringResource(R.string.today_connect_hc), stringResource(R.string.today_connect_hc_body),
                            icon = Icons.Default.Favorite, family = Category.VIOLET, chevron = true, inset = true)
                    }
                }
                if (state.me?.isPersonal == false) PassiveWalksNudge()
                quickError?.let { ErrorBanner(it) { quickError = null } }
                state.lastError?.let { ErrorBanner(it, onDismiss = { app.clearError() }) }
                Guardrail()
                Gap(10.dp)
            }
        }
    }
}

@Composable
private fun Greeting(me: Me?) {
    val c = MP.colors
    val hour = java.time.LocalTime.now().hour
    val part = when { hour < 12 -> stringResource(R.string.greeting_morning); hour < 17 -> stringResource(R.string.greeting_afternoon); else -> stringResource(R.string.greeting_evening) }
    val name = me?.patient?.firstName?.takeIf { it.isNotBlank() } ?: stringResource(R.string.greeting_there)
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(stringResource(R.string.greeting, part, name), style = MPType.displayM, color = c.ink)
        if (me != null) {
            val line = if (me.patient.isRecovery) stringResource(R.string.day_n, me.patient.postopDay ?: 0) + DOT + me.patient.procedureDisplay
                else (me.patient.hospital?.name ?: stringResource(R.string.your_hospital)) + DOT +
                    (if (me.patient.daysEnrolled == 0) stringResource(R.string.joined_today) else stringResource(R.string.days_in, me.patient.daysEnrolled))
            Text(line, style = MPType.copyLarge, color = c.body)
        }
    }
}

/**
 * The recovery tile: the typical curve dashed, the patient's own in white,
 * the headline figure, and the care team's sentence on the glass caption.
 */
@Composable
fun RecoveryHero(me: Me, onClick: () -> Unit) {
    val c = MP.colors
    val rec = me.recovery
    val pct = rec.trajectory.pct?.takeIf { rec.trajectory.state != "unknown" }
    val recovery = me.patient.isRecovery
    val day = me.patient.postopDay
    val value = when {
        pct != null -> (if (pct >= 0) "+" else "−") + "%.0f%%".format(kotlin.math.abs(pct))
        day != null && recovery -> stringResource(R.string.day_n, day)
        else -> "${rec.daysWithData ?: 0}"
    }
    val unit = if (pct != null) (if (recovery) stringResource(R.string.hero_vs_expected) else stringResource(R.string.hero_vs_baseline)) else if (recovery && day != null) stringResource(R.string.hero_of_recovery) else stringResource(R.string.hero_days_of_data)
    val side: Pair<String, String>? = when {
        pct != null && recovery && day != null -> stringResource(R.string.day_n, day) to stringResource(R.string.hero_of_recovery)
        pct != null && rec.daysWithData != null -> "${rec.daysWithData}" to stringResource(R.string.hero_days_of_data)
        else -> null
    }
    GradientTile(kicker = if (recovery) stringResource(R.string.hero_your_recovery) else stringResource(R.string.hero_your_signals), value = value, unit = unit, side = side, onClick = onClick,
        art = { RecoveryCurveArt(pct, Modifier.padding(top = 4.dp)) }) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            StatusPill(rec.label.ifBlank { stringResource(R.string.hero_waiting) }, toneFor(rec.level))
            Spacer(Modifier.weight(1f))
            Text(stringResource(R.string.tab_progress), style = MPType.labelMedium, color = c.brandInk)
            Icon(Icons.Default.ChevronRight, null, tint = c.brandInk, modifier = Modifier.size(14.dp))
        }
        if (rec.blurb.isNotBlank()) { Gap(8.dp); Text(rec.blurb, style = MPType.copyLarge, color = c.ink) }
    }
}

/** Today's plan: the check-in as the one primary action, other open tasks as rows, what is done folded underneath. */
@Composable
private fun PlanCard(open: List<RecoveryTask>, recent: List<RecoveryTask>, nav: NavHostController,
                     markDone: (RecoveryTask) -> Unit, onHistory: () -> Unit) {
    val c = MP.colors
    val checkin = open.firstOrNull { it.isCheckin }
    val others = open.filter { it.id != checkin?.id }
    val done = recent.filter { Dates.parse(it.completedAt)?.toLocalDate() == LocalDate.now() }
    var showDone by remember { mutableStateOf(false) }
    Panel(padding = 0.dp) {
        CardTitleRow(stringResource(R.string.today_plan), note = if (open.isEmpty() && done.isEmpty()) null else stringResource(R.string.today_plan_note, done.size, open.size + done.size),
            actionTitle = stringResource(R.string.today_all_tasks), onAction = onHistory)
        if (open.isEmpty()) {
            EmptyRow(Icons.Default.Check, if (done.isEmpty()) stringResource(R.string.today_nothing_waiting) else stringResource(R.string.today_all_done),
                if (done.isEmpty()) stringResource(R.string.today_nothing_waiting_body) else stringResource(R.string.today_all_done_body))
        } else {
            if (checkin != null) {
                Column(Modifier.padding(horizontal = 16.dp).padding(top = 6.dp, bottom = if (others.isEmpty()) 16.dp else 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    PrimaryButton(stringResource(R.string.today_start_checkin), icon = Icons.Default.QuestionAnswer) { nav.navigate(Routes.checkin(checkin.id)) }
                    Text(if (checkin.inSmsConversation) stringResource(R.string.today_checkin_by_text) else stringResource(R.string.today_checkin_hint),
                        style = MPType.label, color = c.muted, modifier = Modifier.padding(horizontal = 4.dp))
                }
            }
            if (others.isNotEmpty()) {
                if (checkin != null) InsetDivider()
                others.forEachIndexed { i, t ->
                    PlanRow(t, onOpen = { nav.navigate(Routes.task(t.id)) })
                    if (i < others.lastIndex) RowDivider()
                }
            }
        }
        if (done.isNotEmpty()) {
            InsetDivider()
            Row(Modifier.fillMaxWidth().clickable { showDone = !showDone }.padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.CheckCircle, null, tint = c.riskLow, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text(stringResource(R.string.today_done_today), style = MPType.copyMedium, color = c.ink)
                Spacer(Modifier.width(6.dp))
                Text("${done.size}", style = MPType.copyMedium, color = c.muted)
                Spacer(Modifier.weight(1f))
                Icon(Icons.Default.KeyboardArrowDown, null, tint = c.muted, modifier = Modifier.size(18.dp).rotate(if (showDone) 180f else 0f))
            }
            if (showDone) done.forEach { t -> RowDivider(); PlanRow(t, onOpen = { nav.navigate(Routes.task(t.id)) }) }
        } else Gap(4.dp)
    }
}

fun taskFamily(kind: String): Category = when (kind) {
    "exercise", "walk" -> Category.TEAL
    "medication", "wound_check" -> Category.VIOLET
    "sleep" -> Category.INDIGO
    else -> Category.BLUE
}

/** One task as a row: a category glyph, the title, one meta line, a chevron or the state glyph. */
@Composable
fun PlanRow(task: RecoveryTask, onOpen: () -> Unit) {
    val c = MP.colors
    val isDone = task.status == "done"
    val status: Pair<String, Color>? = when {
        isDone && task.completedVia != null -> stringResource(R.string.task_done_by_lower, task.completedVia) to c.muted
        task.inSmsConversation -> stringResource(R.string.task_in_progress_by_text_lower) to c.riskMed
        task.dueAt != null -> stringResource(R.string.task_due_lower, Dates.relative(task.dueAt) ?: "") to c.muted
        task.scheduleLabel != null -> task.scheduleLabel to c.muted
        else -> null
    }
    Row(Modifier.fillMaxWidth().clickable(onClick = onOpen).padding(horizontal = 16.dp, vertical = 11.dp).heightIn(min = 30.dp), verticalAlignment = Alignment.CenterVertically) {
        Glyph(taskIcon(task.kind), taskFamily(task.kind))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(task.title.ifBlank { task.kindLabel }, style = MPType.copyLargeMedium, color = c.ink,
                textDecoration = if (isDone) TextDecoration.LineThrough else null)
            Row {
                Text(task.kindLabel, style = MPType.label, color = c.muted)
                if (status != null) { Text(DOT, style = MPType.label, color = c.muted); Text(status.first, style = MPType.label, color = status.second, maxLines = 1) }
            }
        }
        Spacer(Modifier.width(8.dp))
        when {
            task.isOpen -> Chevron()
            isDone -> Icon(Icons.Default.CheckCircle, null, tint = c.riskLow, modifier = Modifier.size(18.dp))
            else -> Icon(Icons.Outlined.RemoveCircleOutline, null, tint = c.muted, modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
private fun MeasureRow(due: List<MeasureStatus.Test>, onClick: () -> Unit) {
    val subtitle = when {
        due.size == MeasureStatus.tests.size -> stringResource(R.string.today_measure_all_tests)
        due.isNotEmpty() -> { val names = due.map { stringResource(it.nameRes).lowercase() }
            val list = if (names.size == 1) names[0] else stringResource(R.string.list_and, names.dropLast(1).joinToString(", "), names.last())
            stringResource(if (due.size == 1) R.string.today_measure_due_one else R.string.today_measure_due_many, list.replaceFirstChar { it.uppercase() }) }
        else -> stringResource(R.string.today_measure_caught_up)
    }
    Panel(padding = 0.dp, onClick = onClick) {
        ListRow(stringResource(R.string.tab_measure), subtitle, icon = Icons.Default.DirectionsWalk, family = Category.TEAL, chevron = true, inset = true,
            trailing = if (due.isNotEmpty()) ({ StateLabel(stringResource(R.string.due), Tone.MED) }) else null)
    }
}

@Composable
private fun CareRow(last: String?, unread: Int, team: List<CareTeamMember>, onClick: () -> Unit) {
    val c = MP.colors
    val subtitle = last?.takeIf { it.isNotBlank() } ?: team.joinToString(", ") { it.name }.ifBlank { stringResource(R.string.today_care_placeholder) }
    Panel(padding = 0.dp, onClick = onClick) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            TeamAvatars(team)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.care_team), style = MPType.copyLargeMedium, color = c.ink)
                Text(subtitle, style = MPType.label, color = c.muted, maxLines = 2)
            }
            Spacer(Modifier.width(8.dp))
            if (unread > 0) Text("$unread", style = MPType.figuresLabel, color = c.onAction,
                modifier = Modifier.clip(CapsuleShape).background(c.action).padding(horizontal = 8.dp, vertical = 3.dp))
            Spacer(Modifier.width(6.dp))
            Chevron()
        }
    }
}

/** The care team as overlapping soft discs. */
@Composable
fun TeamAvatars(team: List<CareTeamMember>) {
    val c = MP.colors
    if (team.isEmpty()) { Glyph(Icons.Default.Forum, Category.BLUE, 36.dp); return }
    Row(horizontalArrangement = Arrangement.spacedBy((-10).dp)) {
        team.take(3).forEach { m ->
            Box(Modifier.size(38.dp).clip(CircleShape).background(c.panel), contentAlignment = Alignment.Center) {
                Initials(m.name, size = 34.dp, tone = Tone.MISSING, soft = true)
            }
        }
    }
}
