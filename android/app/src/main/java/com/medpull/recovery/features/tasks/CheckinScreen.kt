package com.medpull.recovery.features.tasks

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import com.medpull.recovery.R
import com.medpull.recovery.core.AnswerValue
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Hairline
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PlainButton
import com.medpull.recovery.ui.PrimaryButton
import com.medpull.recovery.ui.SecondaryButton
import com.medpull.recovery.ui.appModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** One question at a time, every one optional, a review page, then send. */
@Composable
fun CheckinScreen(nav: NavHostController, id: Int?) {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    val task = (state.tasks.open + state.tasks.recent).firstOrNull { it.id == id }
    val answers = remember { mutableStateMapOf<String, AnswerValue>() }
    var step by remember { mutableIntStateOf(0) }
    var sending by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var done by remember { mutableStateOf(false) }
    if (task == null) { Column(Modifier.padding(16.dp)) { Text(stringResource(R.string.checkin_gone), color = c.muted) }; return }
    val qs = task.questions
    val reviewing = step >= qs.size
    // Felt as well as seen: a tick per step, a confirm when sent, a buzz on failure.
    val haptic = LocalHapticFeedback.current
    LaunchedEffect(step) { if (step > 0) haptic.performHapticFeedback(HapticFeedbackType.SegmentTick) }
    LaunchedEffect(error) { if (error != null) haptic.performHapticFeedback(HapticFeedbackType.Reject) }
    LaunchedEffect(done) { if (done) { haptic.performHapticFeedback(HapticFeedbackType.Confirm); delay(1400); nav.popBackStack() } }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp)) {
        Row(Modifier.fillMaxWidth().height(52.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { if (step > 0 && !done) step -= 1 else nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back), tint = c.ink) }
            Text(task.title.ifBlank { stringResource(R.string.checkin_title) }, style = MaterialTheme.typography.titleLarge, color = c.ink)
        }
        if (done) {
            Panel(tint = c.brandTint) {
                Text(stringResource(R.string.sent_to_care_team), style = MaterialTheme.typography.titleLarge, color = c.brandInk)
                Text(stringResource(R.string.checkin_sent_body), color = c.body)
            }
            return@Column
        }
        error?.let { ErrorBanner(it, onDismiss = { error = null }); Gap() }
        if (!reviewing) {
            val q = qs[step]
            Text(stringResource(R.string.checkin_question_n, step + 1, qs.size), style = MaterialTheme.typography.labelMedium, color = c.muted)
            Row(Modifier.padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                qs.indices.forEach { i ->
                    Box(Modifier.size(8.dp).clip(CircleShape).background(
                        if (i <= step) c.brand else c.line))
                }
            }
            Gap(8.dp)
            Text(q.prompt, style = MaterialTheme.typography.displaySmall, color = c.ink)
            Gap(20.dp)
            QuestionView(q, answers[q.id]) { v -> if (v == null) answers.remove(q.id) else answers[q.id] = v }
            Gap(28.dp)
            PrimaryButton(if (step == qs.lastIndex) stringResource(R.string.review) else stringResource(R.string.next)) { step += 1 }
            Gap(8.dp)
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                if (step > 0) PlainButton(stringResource(R.string.back)) { step -= 1 } else Spacer(Modifier)
                PlainButton(if (answers.containsKey(q.id)) stringResource(R.string.clear) else stringResource(R.string.checkin_skip_one), color = c.muted) { answers.remove(q.id); step += 1 }
            }
        } else {
            Text(stringResource(R.string.review), style = MaterialTheme.typography.displaySmall, color = c.ink)
            Gap(12.dp)
            Panel {
                qs.forEachIndexed { i, q ->
                    Row(Modifier.fillMaxWidth().clickable { step = i }.padding(vertical = 10.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(q.prompt, style = MaterialTheme.typography.bodyMedium, color = c.muted)
                            Text(spoken(q.id, answers[q.id]), style = MaterialTheme.typography.bodyLarge, color = c.ink)
                        }
                    }
                    if (i < qs.lastIndex) Hairline()
                }
            }
            Gap(20.dp)
            val nothing = answers.isEmpty()
            PrimaryButton(if (nothing) stringResource(R.string.checkin_send_nothing) else stringResource(R.string.checkin_send), loading = sending) {
                scope.launch {
                    sending = true
                    try {
                        if (nothing) app.skip(task) else app.complete(task, answers.toMap())
                        done = true
                    } catch (e: Exception) { error = e.message }
                    sending = false
                }
            }
            Gap(8.dp)
            SecondaryButton(stringResource(R.string.checkin_back_to_questions)) { step = 0 }
        }
        Gap(24.dp)
    }
}

@Composable
private fun spoken(id: String, v: AnswerValue?): String = when (v) {
    null -> stringResource(R.string.skipped)
    is AnswerValue.Num -> painWords(id, v.value)
    is AnswerValue.Text -> choiceLabel(v.value)
}
