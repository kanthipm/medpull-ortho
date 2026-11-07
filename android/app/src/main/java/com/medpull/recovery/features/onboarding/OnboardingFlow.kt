package com.medpull.recovery.features.onboarding

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.google.android.gms.auth.api.phone.SmsRetriever
import com.google.android.gms.common.api.CommonStatusCodes
import com.google.android.gms.common.api.Status
import com.medpull.recovery.MedPullApp
import com.medpull.recovery.R
import com.medpull.recovery.core.AppModel
import com.medpull.recovery.features.consent.ConsentForm
import com.medpull.recovery.features.profile.HealthConnectCard
import com.medpull.recovery.features.profile.WearableLinkCard
import com.medpull.recovery.features.profile.rememberPassiveWalkEnabler
import com.medpull.recovery.motion.PassiveCapture
import com.medpull.recovery.ui.Chip
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Field
import com.medpull.recovery.ui.FlowChips
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Guardrail
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PlainButton
import com.medpull.recovery.ui.PrimaryButton
import com.medpull.recovery.ui.SecondaryButton
import com.medpull.recovery.ui.appModel
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

@Composable
fun OnboardingFlow() {
    val context = LocalContext.current
    val graph = (context.applicationContext as MedPullApp).graph
    val app = appModel()
    val model = remember { OnboardingModel(graph.api, app, graph.config, graph.strings) }
    val nav = rememberNavController()
    NavHost(nav, startDestination = Step.WELCOME.name, modifier = Modifier.fillMaxSize().safeDrawingPadding()) {
        composable(Step.WELCOME.name) { Welcome(nav) }
        composable(Step.MODE.name) { ModeStep(nav) }
        composable(Step.PERSONAL_SOON.name) { PersonalSoon(nav) }
        composable(Step.CONSENT.name) { ConsentStep(nav, model) }
        composable(Step.HOSPITAL.name) { HospitalStep(nav, model) }
        composable(Step.PATH.name) { PathStep(nav, model) }
        composable(Step.IDENTITY.name) { IdentityStep(nav, model) }
        composable(Step.JOIN.name) { JoinStep(nav, model) }
        composable(Step.VERIFY.name) { VerifyStep(nav, model) }
        composable(Step.HEALTH.name) { HealthStep(nav, app) }
        composable(Step.WALKS.name) { WalksStep(nav) }
        composable(Step.WEARABLE.name) { WearableStep(nav, app) }
        composable(Step.DONE.name) { DoneStep(app) }
    }
}

/** The steps a hospital patient walks through, in order, for the dots and the "Step N of M" eyebrow. */
// The consent form is not among them: it appears once, before a NEW record is
// created (PathStep / IdentityStep), and never for a patient finding a record.
private val shownSteps = listOf(Step.HOSPITAL, Step.PATH, Step.IDENTITY, Step.VERIFY, Step.HEALTH, Step.WALKS, Step.WEARABLE)
private fun slot(step: Step) = shownSteps.indexOf(if (step == Step.JOIN) Step.IDENTITY else step)
@Composable
private fun eyebrow(step: Step): String = slot(step).let { if (it < 0) stringResource(R.string.onboarding_almost_done) else stringResource(R.string.onboarding_step_n_of_m, it + 1, shownSteps.size) }

/** One dot per step, filled up to and including the current one; the eyebrow says the same thing in words. */
@Composable
private fun StepDots(step: Step) {
    val c = MP.colors
    val reached = slot(step)
    val words = eyebrow(step)
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.semantics { contentDescription = words }) {
        shownSteps.indices.forEach { i ->
            Box(Modifier.size(8.dp).clip(CircleShape).background(if (i <= reached) c.brand else c.line))
        }
    }
}

@Composable
private fun StepFrame(nav: NavHostController?, kicker: String?, title: String, blurb: String? = null,
                      back: Boolean = true, step: Step? = null, content: @Composable () -> Unit) {
    val c = MP.colors
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 20.dp, vertical = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.height(48.dp)) {
            if (back && nav != null && nav.previousBackStackEntry != null) {
                IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back), tint = c.ink) }
            }
            Spacer(Modifier.weight(1f))
            if (step != null) StepDots(step)
            Spacer(Modifier.weight(1f))
        }
        val line = kicker ?: step?.let { eyebrow(it) }
        if (line != null) Text(line.uppercase(), style = MaterialTheme.typography.labelSmall, color = c.muted)
        Gap(6.dp)
        Text(title, style = MaterialTheme.typography.displaySmall, color = c.ink)
        if (blurb != null) { Gap(8.dp); Text(blurb, style = MaterialTheme.typography.bodyLarge, color = c.body) }
        Gap(20.dp)
        content()
        Gap(32.dp)
    }
}

@Composable
private fun Welcome(nav: NavHostController) {
    StepFrame(null, stringResource(R.string.app_name), stringResource(R.string.onboarding_welcome_title), back = false,
        blurb = stringResource(R.string.onboarding_welcome_blurb)) {
        PrimaryButton(stringResource(R.string.onboarding_get_started)) { nav.navigate(Step.MODE.name) }
        Gap(24.dp)
        Guardrail()
    }
}

@Composable
private fun ModeStep(nav: NavHostController) {
    StepFrame(nav, stringResource(R.string.onboarding_first), stringResource(R.string.onboarding_who_set_up)) {
        // No consent yet: a returning patient finding their record has signed
        // already, and the server says so (the gate in Root covers an account
        // that still needs to). The form comes before a NEW record is created.
        Panel(onClick = { nav.navigate(Step.HOSPITAL.name) }) {
            Text(stringResource(R.string.onboarding_with_team), style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
            Text(stringResource(R.string.onboarding_with_team_body), style = MaterialTheme.typography.bodyMedium, color = MP.colors.body)
        }
        Gap()
        Panel(onClick = { nav.navigate(Step.PERSONAL_SOON.name) }) {
            Text(stringResource(R.string.onboarding_on_my_own), style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
            Text(stringResource(R.string.onboarding_on_my_own_body), style = MaterialTheme.typography.bodyMedium, color = MP.colors.body)
        }
    }
}

@Composable
private fun PersonalSoon(nav: NavHostController) {
    StepFrame(nav, stringResource(R.string.onboarding_personal), stringResource(R.string.personal_not_on_android),
        blurb = stringResource(R.string.onboarding_personal_blurb)) {
        PrimaryButton(stringResource(R.string.onboarding_continue_with_team)) { nav.navigate(Step.HOSPITAL.name) }
    }
}

@Composable
private fun ConsentStep(nav: NavHostController, model: OnboardingModel) {
    val s by model.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    LaunchedEffect(Unit) { model.loadConsent() }
    StepFrame(nav, stringResource(R.string.onboarding_consent_eyebrow), stringResource(R.string.onboarding_consent_title),
        blurb = stringResource(R.string.onboarding_consent_blurb)) {
        s.error?.let { ErrorBanner(it); Gap() }
        val doc = s.consent
        if (doc == null) { Text(stringResource(R.string.loading), color = c.muted) ; return@StepFrame }
        ConsentForm(doc, s.consentScopes, onScope = { k, v -> model.state.update { it.copy(consentScopes = it.consentScopes + (k to v)) } },
            signature = s.signature, onSignature = { v -> model.state.update { it.copy(signature = v) } })
        Gap(16.dp)
        PrimaryButton(stringResource(R.string.onboarding_agree_continue), enabled = s.canAgree) {
            // The consent precedes the call that creates a record; it is
            // carried into join as `accepted`.
            scope.launch { model.agree(); nav.navigate(Step.JOIN.name) }
        }
    }
}

@Composable
private fun HospitalStep(nav: NavHostController, model: OnboardingModel) {
    val s by model.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { if (s.hospitals.isEmpty()) model.loadHospitals() }
    StepFrame(nav, null, stringResource(R.string.onboarding_where_treated), step = Step.HOSPITAL) {
        s.error?.let { if (s.hospitals.isEmpty()) { ErrorBanner(it); Gap() } }
        Field(s.hospitalQuery, { model.state.value = s.copy(hospitalQuery = it) }, stringResource(R.string.onboarding_search_hospitals))
        Gap()
        model.filteredHospitals().forEach { h ->
            Panel(padding = 14.dp, onClick = {
                model.state.value = s.copy(hospital = h, candidates = emptyList(), selected = null)
                nav.navigate(Step.PATH.name)
            }) {
                Text(h.name, style = MaterialTheme.typography.titleMedium, color = MP.colors.ink)
                Text(listOfNotNull(h.system, h.city.takeIf { it.isNotBlank() }, h.state.takeIf { it.isNotBlank() }).joinToString(" · "),
                    style = MaterialTheme.typography.bodyMedium, color = MP.colors.muted)
            }
            Gap(8.dp)
        }
    }
}

@Composable
private fun PathStep(nav: NavHostController, model: OnboardingModel) {
    val s by model.state.collectAsStateWithLifecycle()
    StepFrame(nav, null, s.hospital?.name ?: stringResource(R.string.your_hospital), step = Step.PATH) {
        Panel(onClick = { model.state.value = s.copy(path = Path.FIND_RECORD); nav.navigate(Step.IDENTITY.name) }) {
            Text(stringResource(R.string.onboarding_team_set_me_up), style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
            Text(stringResource(R.string.onboarding_team_set_me_up_body), style = MaterialTheme.typography.bodyMedium, color = MP.colors.body)
        }
        Gap()
        Panel(onClick = {
            model.state.value = s.copy(path = Path.JOIN_GENERAL)
            // Starting a record creates an account, so the consent comes first — once.
            nav.navigate((if (s.accepted == null) Step.CONSENT else Step.JOIN).name)
        }) {
            Text(stringResource(R.string.onboarding_new_here), style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
            Text(stringResource(R.string.onboarding_new_here_body), style = MaterialTheme.typography.bodyMedium, color = MP.colors.body)
        }
    }
}

@Composable
private fun IdentityStep(nav: NavHostController, model: OnboardingModel) {
    val s by model.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    LaunchedEffect(s.name, s.phone) { delay(350); model.search() }
    StepFrame(nav, null, stringResource(R.string.onboarding_find_record), step = Step.IDENTITY, blurb = stringResource(R.string.onboarding_find_record_blurb)) {
        s.error?.let { ErrorBanner(it, onDismiss = { model.state.value = s.copy(error = null) }); Gap() }
        Field(s.name, { model.state.value = s.copy(name = it) }, stringResource(R.string.onboarding_full_name))
        Gap(8.dp)
        Field(s.phone, { model.state.value = s.copy(phone = it) }, stringResource(R.string.onboarding_mobile), keyboard = KeyboardType.Phone)
        Gap()
        if (s.searching) Text(stringResource(R.string.onboarding_searching), color = c.muted, style = MaterialTheme.typography.bodyMedium)
        s.candidates.forEach { cand ->
            val sel = s.selected?.patientId == cand.patientId
            Panel(padding = 14.dp, tint = if (sel) c.brandTint else null, onClick = { model.state.value = s.copy(selected = cand) }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(cand.displayName, style = MaterialTheme.typography.titleMedium, color = c.ink)
                        Text(listOfNotNull(cand.procedureDisplay.takeIf { it.isNotBlank() }, cand.surgeryMonth).joinToString(" · "),
                            style = MaterialTheme.typography.bodyMedium, color = c.muted)
                    }
                    if (cand.phoneMatch) Text(stringResource(R.string.onboarding_number_matches), style = MaterialTheme.typography.labelMedium, color = c.brandInk)
                }
            }
            Gap(8.dp)
        }
        if (s.name.trim().length >= 2 && !s.searching && s.candidates.isEmpty()) {
            Text(stringResource(R.string.onboarding_not_on_list), color = c.muted, style = MaterialTheme.typography.bodyMedium)
        }
        PlainButton(stringResource(R.string.onboarding_join_instead)) {
            model.state.value = s.copy(path = Path.JOIN_GENERAL)
            nav.navigate((if (s.accepted == null) Step.CONSENT else Step.JOIN).name)
        }
        Gap()
        PrimaryButton(stringResource(R.string.onboarding_this_is_me), enabled = s.canEnroll, loading = s.working) {
            scope.launch { model.enroll()?.let { nav.navigate(it.name) } }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun JoinStep(nav: NavHostController, model: OnboardingModel) {
    val s by model.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    var pickDob by remember { mutableStateOf(false) }
    var pickSurgery by remember { mutableStateOf(false) }
    LaunchedEffect(s.hadSurgery) { if (s.hadSurgery) model.loadProcedures() }
    StepFrame(nav, null, stringResource(R.string.onboarding_join_title), step = Step.JOIN) {
        s.error?.let { ErrorBanner(it, onDismiss = { model.state.value = s.copy(error = null) }); Gap() }
        Field(s.name, { model.state.value = s.copy(name = it) }, stringResource(R.string.onboarding_full_name))
        Gap(8.dp)
        Field(s.phone, { model.state.value = s.copy(phone = it) }, stringResource(R.string.onboarding_mobile), keyboard = KeyboardType.Phone)
        Gap()
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.onboarding_dob), Modifier.weight(1f), color = c.ink)
            TextButton(onClick = { pickDob = true }) { Text(s.dateOfBirth?.toString() ?: stringResource(R.string.onboarding_add_optional)) }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.onboarding_recovering), Modifier.weight(1f), color = c.ink)
            Switch(checked = s.hadSurgery, onCheckedChange = { v ->
                model.state.value = s.copy(hadSurgery = v, path = if (v) Path.JOIN_AFTER_SURGERY else Path.JOIN_GENERAL)
            })
        }
        if (s.hadSurgery) {
            Gap(8.dp)
            Text(stringResource(R.string.onboarding_which_operation), style = MaterialTheme.typography.labelMedium, color = c.muted)
            Gap(6.dp)
            FlowChips(s.procedures.map { it.label }, s.procedures.indexOf(s.procedure)) { i ->
                model.state.value = s.copy(procedure = s.procedures[i])
            }
            Gap(8.dp)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.onboarding_surgery_date), Modifier.weight(1f), color = c.ink)
                TextButton(onClick = { pickSurgery = true }) { Text(s.surgeryDate.toString()) }
            }
        }
        Gap(16.dp)
        PrimaryButton(stringResource(R.string.onboarding_join), enabled = s.canJoin, loading = s.working) {
            scope.launch { model.join()?.let { nav.navigate(it.name) } }
        }
    }
    if (pickDob) DateDialog(s.dateOfBirth ?: LocalDate.now().minusYears(60), { pickDob = false }) {
        model.state.value = s.copy(dateOfBirth = it); pickDob = false
    }
    if (pickSurgery) DateDialog(s.surgeryDate, { pickSurgery = false }) { model.state.value = s.copy(surgeryDate = it); pickSurgery = false }
}

@Composable
private fun VerifyStep(nav: NavHostController, model: OnboardingModel) {
    val s by model.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    if (s.textFirst) {
        TextFirstStep(nav, model)
        return
    }
    val context = LocalContext.current
    // The texted code, read with the person's consent (the SMS User Consent
    // API: Android shows one sheet naming the message; nothing else is read).
    // The iPhone autofills it from the keyboard; this is the nearest thing.
    val consent = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode != Activity.RESULT_OK) return@rememberLauncherForActivityResult
        val message = result.data?.getStringExtra(SmsRetriever.EXTRA_SMS_MESSAGE).orEmpty()
        Regex("""\b(\d{6})\b""").find(message)?.value?.let { code -> model.state.update { it.copy(code = code) } }
    }
    DisposableEffect(Unit) {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(c: Context, intent: Intent) {
                if (intent.action != SmsRetriever.SMS_RETRIEVED_ACTION) return
                val extras = intent.extras ?: return
                @Suppress("DEPRECATION")
                val status = extras.get(SmsRetriever.EXTRA_STATUS) as? Status ?: return
                if (status.statusCode != CommonStatusCodes.SUCCESS) return
                @Suppress("DEPRECATION")
                val sheet = extras.getParcelable<Intent>(SmsRetriever.EXTRA_CONSENT_INTENT) ?: return
                try { consent.launch(sheet) } catch (_: ActivityNotFoundException) {}
            }
        }
        ContextCompat.registerReceiver(context, receiver, IntentFilter(SmsRetriever.SMS_RETRIEVED_ACTION),
            SmsRetriever.SEND_PERMISSION, null, ContextCompat.RECEIVER_EXPORTED)
        try { SmsRetriever.getClient(context).startSmsUserConsent(null) } catch (_: Exception) {}
        onDispose { try { context.unregisterReceiver(receiver) } catch (_: Exception) {} }
    }
    StepFrame(nav, null, stringResource(R.string.onboarding_enter_code), step = Step.VERIFY,
        blurb = stringResource(R.string.onboarding_code_sent, s.phoneMasked ?: stringResource(R.string.your_number))) {
        s.error?.let { ErrorBanner(it, onDismiss = { model.state.value = s.copy(error = null) }); Gap() }
        Field(s.code, { model.state.value = s.copy(code = it.filter { ch -> ch.isDigit() }.take(8)) }, stringResource(R.string.onboarding_code_field),
            keyboard = KeyboardType.NumberPassword)
        Gap(16.dp)
        PrimaryButton(stringResource(R.string.onboarding_confirm), enabled = s.code.length >= 4, loading = s.working) {
            scope.launch { model.verify()?.let { nav.navigate(it.name) } }
        }
        PlainButton(stringResource(R.string.onboarding_send_new_code)) { scope.launch { model.resend() } }
    }
}

/** Sendblue's free plan cannot text a number that has never texted the line, so the server is
 *  waiting on one text from this phone. One tap opens Messages with the words already written;
 *  the code goes out the moment the text lands, and the step moves on to the field by itself. */
@Composable
private fun TextFirstStep(nav: NavHostController, model: OnboardingModel) {
    val s by model.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val c = MP.colors
    LaunchedEffect(s.verificationId) {
        // Poll while waiting, so the field appears without another tap.
        while (true) { delay(3_000); model.pollForCode() }
    }
    StepFrame(nav, stringResource(R.string.onboarding_step_n_of_m, 4, 5), stringResource(R.string.onboarding_text_us_first),
        blurb = stringResource(R.string.onboarding_text_first_blurb, s.phoneMasked ?: stringResource(R.string.your_number))) {
        Panel {
            Text(stringResource(R.string.onboarding_text_body_to, s.textBody ?: stringResource(R.string.onboarding_default_text)), style = MaterialTheme.typography.labelMedium, color = c.muted)
            Gap(4.dp)
            Text(formatPhone(s.textTo), style = MaterialTheme.typography.titleLarge, color = c.ink)
            Gap(6.dp)
            Text(stringResource(R.string.onboarding_well_text_code), style = MaterialTheme.typography.bodyMedium, color = c.body)
        }
        s.error?.let { Gap(); ErrorBanner(it, onDismiss = { model.state.value = s.copy(error = null) }) }
        Gap(16.dp)
        PrimaryButton(stringResource(R.string.onboarding_open_messages)) {
            val uri = model.textFirstUri() ?: return@PrimaryButton
            try {
                context.startActivity(Intent(Intent.ACTION_SENDTO, Uri.parse(uri)))
            } catch (_: ActivityNotFoundException) {
                model.state.value = s.copy(error = context.getString(R.string.onboarding_no_messaging_app, formatPhone(s.textTo)))
            }
        }
        Gap(8.dp)
        SecondaryButton(stringResource(R.string.onboarding_sent_it), loading = s.working) {
            scope.launch { model.continueAfterText()?.let { if (it != Step.VERIFY) nav.navigate(it.name) } }
        }
    }
}

/** "+15049081262" as "(504) 908-1262" for a US number; anything else as is. */
private fun formatPhone(e164: String?): String {
    if (e164 == null) return ""
    val m = Regex("""^\+1(\d{3})(\d{3})(\d{4})$""").find(e164) ?: return e164
    val (a, b, d) = m.destructured
    return "($a) $b-$d"
}

@Composable
private fun HealthStep(nav: NavHostController, app: AppModel) {
    StepFrame(nav, null, stringResource(R.string.today_connect_hc), back = false, step = Step.HEALTH,
        blurb = stringResource(R.string.onboarding_hc_blurb)) {
        HealthConnectCard(app)
        Gap()
        SecondaryButton(stringResource(R.string.onboarding_skip_for_now)) { nav.navigate(Step.WALKS.name) }
        Gap(8.dp)
        PrimaryButton(stringResource(R.string.continue_label)) { nav.navigate(Step.WALKS.name) }
    }
}

/** On by default: one tap fires the system prompts, and capture starts as soon as they are granted. */
@Composable
private fun WalksStep(nav: NavHostController) {
    val context = LocalContext.current
    val c = MP.colors
    var on by remember { mutableStateOf(PassiveCapture.isActive(context)) }
    var declined by remember { mutableStateOf(false) }
    val enable = rememberPassiveWalkEnabler { ok -> on = ok; if (!ok) declined = true }
    StepFrame(nav, null, stringResource(R.string.onboarding_walks_title), back = false, step = Step.WALKS,
        blurb = stringResource(R.string.onboarding_walks_blurb)) {
        Panel {
            Text(stringResource(R.string.walk_how_it_works), style = MaterialTheme.typography.titleMedium, color = c.ink)
            Gap(6.dp)
            Text(stringResource(R.string.onboarding_walks_1), color = c.body, style = MaterialTheme.typography.bodyMedium)
            Text(stringResource(R.string.onboarding_walks_2), color = c.body, style = MaterialTheme.typography.bodyMedium)
            Text(stringResource(R.string.onboarding_walks_3), color = c.body, style = MaterialTheme.typography.bodyMedium)
        }
        Gap()
        if (on) {
            Text(stringResource(R.string.onboarding_walks_on), color = c.brandInk, style = MaterialTheme.typography.bodyMedium)
            Gap(8.dp)
            PrimaryButton(stringResource(R.string.continue_label)) { nav.navigate(Step.WEARABLE.name) }
        } else {
            if (declined) { Text(stringResource(R.string.onboarding_walks_later), color = c.muted, style = MaterialTheme.typography.bodyMedium); Gap(8.dp) }
            SecondaryButton(stringResource(R.string.onboarding_not_now)) { nav.navigate(Step.WEARABLE.name) }
            Gap(8.dp)
            PrimaryButton(stringResource(R.string.onboarding_turn_on)) { enable() }
        }
    }
}

@Composable
private fun WearableStep(nav: NavHostController, app: AppModel) {
    StepFrame(nav, null, stringResource(R.string.wearables_add), back = false, step = Step.WEARABLE,
        blurb = stringResource(R.string.onboarding_wearable_blurb)) {
        WearableLinkCard(app)
        Gap()
        PrimaryButton(stringResource(R.string.done)) { nav.navigate(Step.DONE.name) }
    }
}

@Composable
private fun DoneStep(app: AppModel) {
    val state by app.state.collectAsStateWithLifecycle()
    val name = state.me?.patient?.firstName?.takeIf { it.isNotBlank() }
    StepFrame(null, stringResource(R.string.onboarding_youre_set), if (name != null) stringResource(R.string.onboarding_welcome_name, name) else stringResource(R.string.onboarding_welcome_dot), back = false,
        blurb = stringResource(R.string.onboarding_done_blurb)) {
        PrimaryButton(stringResource(R.string.onboarding_open_medpull)) { app.enterHome() }
    }
}

// --- small shared pieces --------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DateDialog(initial: LocalDate, onDismiss: () -> Unit, onPick: (LocalDate) -> Unit) {
    val st = rememberDatePickerState(initialSelectedDateMillis = initial.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli())
    DatePickerDialog(onDismissRequest = onDismiss, confirmButton = {
        TextButton(onClick = {
            st.selectedDateMillis?.let { onPick(Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate()) } ?: onDismiss()
        }) { Text(stringResource(R.string.ok)) }
    }, dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } }) { DatePicker(state = st) }
}
