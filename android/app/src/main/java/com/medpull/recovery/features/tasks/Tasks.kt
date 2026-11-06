package com.medpull.recovery.features.tasks

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.medpull.recovery.core.AnswerValue
import com.medpull.recovery.core.Dates
import com.medpull.recovery.core.Question
import com.medpull.recovery.core.RecoveryTask
import com.medpull.recovery.ui.Chip
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Hairline
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PlainButton
import com.medpull.recovery.ui.PrimaryButton
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
        Icon(taskIcon(task.kind), null, tint = c.teal)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f).clickable(onClick = onOpen)) {
            Text(task.title.ifBlank { task.kindLabel }, style = MaterialTheme.typography.bodyLarge, color = c.ink)
            val sub = listOfNotNull(task.scheduleLabel, if (task.inSmsConversation) "in progress by text" else null,
                task.completedVia?.let { "done by $it" }).joinToString(" · ")
            if (sub.isNotBlank()) Text(sub, style = MaterialTheme.typography.bodyMedium, color = c.muted)
        }
        if (onDone != null) PlainButton("Done", onClick = onDone)
    }
}

@Composable
private fun BackBar(nav: NavHostController, title: String) {
    Row(Modifier.fillMaxWidth().height(52.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = MP.colors.ink) }
        Text(title, style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
    }
}

@Composable
fun TaskHistoryScreen(nav: NavHostController) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { app.refreshTasks(false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        BackBar(nav, "Tasks")
        Panel {
            SectionTitle("To do")
            if (state.tasks.open.isEmpty()) Text("Nothing open.", color = MP.colors.muted)
            state.tasks.open.forEach { t -> TaskRow(t, onOpen = { nav.navigate(if (t.isCheckin) "checkin/${t.id}" else "task/${t.id}") }); Hairline() }
        }
        Gap()
        Panel {
            SectionTitle("Recently done")
            if (state.tasks.recent.isEmpty()) Text("Nothing yet.", color = MP.colors.muted)
            state.tasks.recent.forEach { t -> TaskRow(t, onOpen = { nav.navigate("task/${t.id}") }); Hairline() }
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
    if (task == null) { Column(Modifier.padding(16.dp)) { BackBar(nav, "Task"); Text("This task is no longer here.", color = c.muted) }; return }
    if (task.isCheckin) { CheckinScreen(nav, id); return }

    LaunchedEffect(done) { if (done) { delay(1200); nav.popBackStack() } }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp)) {
        BackBar(nav, task.kindLabel.ifBlank { "Task" })
        Text(task.title, style = MaterialTheme.typography.displaySmall, color = c.ink)
        if (task.why.isNotBlank()) { Gap(6.dp); Text(task.why, style = MaterialTheme.typography.bodyLarge, color = c.body) }
        Gap(8.dp)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (task.inSmsConversation) StatusPill("In progress by text", Tone.MED)
            if (!task.isOpen) StatusPill(task.completedVia?.let { "Done by $it" } ?: "Done", Tone.LOW)
            task.dueAt?.let { Dates.relative(it) }?.let { StatusPill("Due $it", Tone.MISSING) }
        }
        Gap(16.dp)
        error?.let { ErrorBanner(it, onDismiss = { error = null }); Gap() }
        if (done) {
            Panel(tint = c.brandTint) { Text("Sent to your care team", style = MaterialTheme.typography.titleMedium, color = c.brandInk) }
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
            PrimaryButton("Mark done", loading = sending) {
                scope.launch {
                    sending = true
                    try { app.complete(task, answers.toMap()); done = true } catch (e: Exception) { error = e.message }
                    sending = false
                }
            }
            Gap(8.dp)
            SecondaryButton("Skip for today") {
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
            Text(if (current == null) "Drag to answer" else painWords(q.id, current), style = MaterialTheme.typography.bodyLarge,
                color = if (current == null) c.muted else c.ink)
            Slider(value = (current ?: lo.toInt()).toFloat(), onValueChange = { onChange(AnswerValue.Num(it.toInt())) },
                valueRange = lo..hi, steps = (hi - lo).toInt() - 1,
                colors = SliderDefaults.colors(thumbColor = c.brand, activeTrackColor = c.brand, inactiveTrackColor = c.line))
        }
        "yes_no", "choice" -> {
            val options = q.options ?: listOf("yes", "no")
            val sel = (value as? AnswerValue.Text)?.value
            androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
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
            modifier = Modifier.fillMaxWidth(), minLines = 2, placeholder = { Text("Type here") },
        )
    }
}

fun choiceLabel(o: String) = when (o) {
    "yes" -> "Yes"; "no" -> "No"; "well" -> "Well"; "rough" -> "Rough night"; "all" -> "All of them"; "some" -> "Some"; "none" -> "Not today"
    else -> o.replaceFirstChar { it.uppercase() }
}

fun painWords(id: String, v: Int): String = if (id != "pain") "$v" else "$v out of 10 — " + when {
    v == 0 -> "None"; v <= 3 -> "Mild"; v <= 6 -> "Moderate"; v <= 8 -> "Severe"; else -> "Worst imaginable"
}
