package com.medpull.recovery.features.tasks

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.Checklist
import androidx.compose.material.icons.filled.DirectionsWalk
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.Healing
import androidx.compose.material.icons.filled.Medication
import androidx.compose.material.icons.filled.QuestionAnswer
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.medpull.recovery.R
import com.medpull.recovery.core.AnswerValue
import com.medpull.recovery.core.Dates
import com.medpull.recovery.core.Question
import com.medpull.recovery.core.RecoveryTask
import com.medpull.recovery.ui.BackBar
import com.medpull.recovery.ui.Chip
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Hairline
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
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

fun taskIcon(kind: String): ImageVector = when (kind) {
    "checkin" -> Icons.Default.QuestionAnswer; "exercise" -> Icons.Default.FitnessCenter
    "walk" -> Icons.Default.DirectionsWalk; "medication" -> Icons.Default.Medication
    "wound_check" -> Icons.Default.Healing; "sleep" -> Icons.Default.Bedtime; else -> Icons.Default.Checklist
}

@Composable
fun TaskRow(task: RecoveryTask, onOpen: () -> Unit, onDone: (() -> Unit)? = null) {
    val c = MP.colors
    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(taskIcon(task.kind), task.kindLabel.ifBlank { null }, tint = c.teal)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f).clickable(onClick = onOpen)) {
            Text(task.title.ifBlank { task.kindLabel }, style = MaterialTheme.typography.bodyLarge, color = c.ink)
            val sub = listOfNotNull(task.scheduleLabel, if (task.inSmsConversation) stringResource(R.string.task_in_progress_by_text_lower) else null,
                task.completedVia?.let { stringResource(R.string.task_done_by_lower, it) }).joinToString(" · ")
            if (sub.isNotBlank()) Text(sub, style = MaterialTheme.typography.bodyMedium, color = c.muted)
        }
        if (onDone != null) PlainButton(stringResource(R.string.done), onClick = onDone)
    }
}

@Composable
fun TaskHistoryScreen(nav: NavHostController) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { app.refreshTasks(false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        BackBar(nav, stringResource(R.string.tasks_title))
        Panel {
            SectionTitle(stringResource(R.string.tasks_to_do))
            if (state.tasks.open.isEmpty()) Text(stringResource(R.string.tasks_nothing_open), color = MP.colors.muted)
            state.tasks.open.forEach { t -> TaskRow(t, onOpen = { nav.navigate(if (t.isCheckin) Routes.checkin(t.id) else Routes.task(t.id)) }); Hairline() }
        }
        Gap()
        Panel {
            SectionTitle(stringResource(R.string.tasks_recently_done))
            if (state.tasks.recent.isEmpty()) Text(stringResource(R.string.tasks_nothing_yet), color = MP.colors.muted)
            state.tasks.recent.forEach { t -> TaskRow(t, onOpen = { nav.navigate(Routes.task(t.id)) }); Hairline() }
        }
        Gap(24.dp)
    }
}

@Composable
fun TaskDetailScreen(nav: NavHostController, id: Int?) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    val task = (state.tasks.open + state.tasks.recent).firstOrNull { it.id == id }
    val answers = remember { mutableStateMapOf<String, AnswerValue>() }
    var sending by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var done by remember { mutableStateOf(false) }
    if (task == null) { Column(Modifier.padding(16.dp)) { BackBar(nav, stringResource(R.string.task_title)); Text(stringResource(R.string.task_gone), color = c.muted) }; return }
    if (task.isCheckin) { CheckinScreen(nav, id); return }

    val haptic = LocalHapticFeedback.current
    LaunchedEffect(error) { if (error != null) haptic.performHapticFeedback(HapticFeedbackType.Reject) }
    LaunchedEffect(done) { if (done) { haptic.performHapticFeedback(HapticFeedbackType.Confirm); delay(1200); nav.popBackStack() } }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp)) {
        BackBar(nav, task.kindLabel.ifBlank { stringResource(R.string.task_title) })
        Text(task.title, style = MaterialTheme.typography.displaySmall, color = c.ink)
        if (task.why.isNotBlank()) { Gap(6.dp); Text(task.why, style = MaterialTheme.typography.bodyLarge, color = c.body) }
        Gap(8.dp)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (task.inSmsConversation) StatusPill(stringResource(R.string.task_in_progress_by_text), Tone.MED)
            if (!task.isOpen) StatusPill(task.completedVia?.let { stringResource(R.string.task_done_by, it) } ?: stringResource(R.string.done), Tone.LOW)
            task.dueAt?.let { Dates.relative(it) }?.let { StatusPill(stringResource(R.string.task_due, it), Tone.MISSING) }
        }
        Gap(16.dp)
        error?.let { ErrorBanner(it, onDismiss = { error = null }); Gap() }
        if (done) {
            Panel(tint = c.brandTint) { Text(stringResource(R.string.sent_to_care_team), style = MaterialTheme.typography.titleMedium, color = c.brandInk) }
        } else if (task.isOpen) {
            task.questions.forEach { q ->
                Panel {
                    Text(q.prompt, style = MaterialTheme.typography.titleMedium, color = c.ink)
                    Gap(10.dp)
                    QuestionView(q, answers[q.id]) { v -> if (v == null) answers.remove(q.id) else answers[q.id] = v }
                }
                Gap(10.dp)
            }
            Gap(8.dp)
            PrimaryButton(stringResource(R.string.task_mark_done), loading = sending) {
                scope.launch {
                    sending = true
                    try { app.complete(task, answers.toMap()); done = true } catch (e: Exception) { error = e.message }
                    sending = false
                }
            }
            Gap(8.dp)
            SecondaryButton(stringResource(R.string.task_skip_today)) {
                scope.launch { try { app.skip(task); nav.popBackStack() } catch (e: Exception) { error = e.message } }
            }
        }
        Gap(24.dp)
    }
}

/** scale -> 0–10 slider, yes_no/choice -> chips, number -> number field, else text. */
@Composable
fun QuestionView(q: Question, value: AnswerValue?, onChange: (AnswerValue?) -> Unit) {
    val c = MP.colors
    when (q.kind) {
        "scale" -> {
            val lo = (q.min ?: 0).toFloat(); val hi = (q.max ?: 10).toFloat()
            val current = (value as? AnswerValue.Num)?.value
            Text(if (current == null) stringResource(R.string.task_drag_to_answer) else painWords(q.id, current), style = MaterialTheme.typography.bodyLarge,
                color = if (current == null) c.muted else c.ink)
            val haptic = LocalHapticFeedback.current
            Slider(value = (current ?: lo.toInt()).toFloat(), onValueChange = { v ->
                if (v.toInt() != current) haptic.performHapticFeedback(HapticFeedbackType.SegmentFrequentTick)
                onChange(AnswerValue.Num(v.toInt()))
            },
                valueRange = lo..hi, steps = (hi - lo).toInt() - 1,
                colors = SliderDefaults.colors(thumbColor = c.brand, activeTrackColor = c.brand, inactiveTrackColor = c.line))
        }
        "yes_no", "choice" -> {
            val options = q.options ?: listOf("yes", "no")
            val sel = (value as? AnswerValue.Text)?.value
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                options.forEach { o -> Chip(choiceLabel(o), selected = sel == o) { onChange(if (sel == o) null else AnswerValue.Text(o)) } }
            }
        }
        "number" -> OutlinedTextField(
            value = (value as? AnswerValue.Num)?.value?.toString().orEmpty(),
            onValueChange = { t -> onChange(t.toIntOrNull()?.let { AnswerValue.Num(it) }) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth(), singleLine = true,
        )
        else -> OutlinedTextField(
            value = (value as? AnswerValue.Text)?.value.orEmpty(),
            onValueChange = { t -> onChange(if (t.isBlank()) null else AnswerValue.Text(t)) },
            modifier = Modifier.fillMaxWidth(), minLines = 2, placeholder = { Text(stringResource(R.string.task_type_here)) },
        )
    }
}

@Composable
fun choiceLabel(o: String): String = when (o) {
    "yes" -> stringResource(R.string.choice_yes); "no" -> stringResource(R.string.choice_no)
    "well" -> stringResource(R.string.choice_well); "rough" -> stringResource(R.string.choice_rough)
    "all" -> stringResource(R.string.choice_all); "some" -> stringResource(R.string.choice_some)
    "none" -> stringResource(R.string.choice_none)
    else -> o.replaceFirstChar { it.uppercase() }
}

@Composable
fun painWords(id: String, v: Int): String {
    if (id != "pain") return "$v"
    // The same words the iPhone and the console transcript use for the score.
    val word = stringResource(when { v == 0 -> R.string.pain_none; v <= 3 -> R.string.pain_mild; v <= 6 -> R.string.pain_moderate; v <= 8 -> R.string.pain_bad; else -> R.string.pain_severe })
    return stringResource(R.string.pain_score, v, word)
}
