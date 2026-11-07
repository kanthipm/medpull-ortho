package com.medpull.recovery.features.onboarding

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
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
    val model = remember { OnboardingModel(graph.api, app, graph.config) }
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
private val shownSteps = listOf(Step.CONSENT, Step.HOSPITAL, Step.PATH, Step.IDENTITY, Step.VERIFY, Step.HEALTH, Step.WALKS, Step.WEARABLE)
private fun slot(step: Step) = shownSteps.indexOf(if (step == Step.JOIN) Step.IDENTITY else step)
private fun eyebrow(step: Step): String = slot(step).let { if (it < 0) "Almost done" else "Step ${it + 1} of ${shownSteps.size}" }

/** One dot per step, filled up to and including the current one; the eyebrow says the same thing in words. */
@Composable
private fun StepDots(step: Step) {
    val c = MP.colors
    val reached = slot(step)
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.semantics { contentDescription = eyebrow(step) }) {
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
                IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = c.ink) }
            }
            Spacer(Modifier.weight(1f))
            if (step != null) StepDots(step)
            Spacer(Modifier.weight(1f))
        }
        val line = kicker ?: step?.let(::eyebrow)
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
    StepFrame(null, "MedPull", "Recovery, followed between visits.", back = false,
        blurb = "Your care team sees how you are doing from your phone and watch, and reaches out before you have to ask.") {
        PrimaryButton("Get started") { nav.navigate(Step.MODE.name) }
        Gap(24.dp)
        Guardrail()
    }
}

@Composable
private fun ModeStep(nav: NavHostController) {
    StepFrame(nav, "First", "Who set you up?") {
        Panel(onClick = { nav.navigate(Step.CONSENT.name) }) {
            Text("With my care team", style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
            Text("A hospital or clinic is following your recovery.", style = MaterialTheme.typography.bodyMedium, color = MP.colors.body)
        }
        Gap()
        Panel(onClick = { nav.navigate(Step.PERSONAL_SOON.name) }) {
            Text("On my own", style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
            Text("MedPull Personal: readiness, training and sleep for yourself.", style = MaterialTheme.typography.bodyMedium, color = MP.colors.body)
        }
    }
}

@Composable
private fun PersonalSoon(nav: NavHostController) {
    StepFrame(nav, "MedPull Personal", "Not on Android yet",
        blurb = "The personal tier is on iPhone today and comes to Android after the care-team app. If a clinic is following your recovery, continue with them.") {
        PrimaryButton("Continue with my care team") { nav.navigate(Step.CONSENT.name) }
    }
}

@Composable
private fun ConsentStep(nav: NavHostController, model: OnboardingModel) {
    val s by model.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    LaunchedEffect(Unit) { model.loadConsent() }
    StepFrame(nav, null, "Please read and agree", step = Step.CONSENT,
        blurb = "MedPull is a beta. Please read what we collect, where it goes and what you can do about it, then tick what you agree to and sign with your name.") {
        s.error?.let { ErrorBanner(it); Gap() }
        val doc = s.consent
        if (doc == null) { Text("Loading…", color = c.muted) ; return@StepFrame }
        Panel { Text(doc.text, style = MaterialTheme.typography.bodyMedium, color = c.body) }
        Gap()
        doc.scopes.forEach { sc ->
            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = s.consentScopes[sc.key] == true,
                    onCheckedChange = { v -> model.state.value = s.copy(consentScopes = s.consentScopes + (sc.key to v)) })
                Column {
                    Text(sc.label, style = MaterialTheme.typography.bodyLarge, color = c.ink)
                    Text(if (sc.required) "Needed to use MedPull" else "Your choice. Change it later in Profile.",
                        style = MaterialTheme.typography.bodyMedium, color = c.muted)
                    if (sc.detail.isNotBlank()) Text(sc.detail, style = MaterialTheme.typography.bodyMedium, color = c.body)
                }
            }
        }
        Gap()
        Field(s.signature, { model.state.value = s.copy(signature = it) }, "Type your name to sign")
        Gap(16.dp)
        PrimaryButton("Agree and continue", enabled = s.canAgree) {
            scope.launch { model.agree(); nav.navigate(Step.HOSPITAL.name) }
        }
    }
}

@Composable
private fun HospitalStep(nav: NavHostController, model: OnboardingModel) {
    val s by model.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { if (s.hospitals.isEmpty()) model.loadHospitals() }
    StepFrame(nav, null, "Where are you being treated?", step = Step.HOSPITAL) {
        s.error?.let { if (s.hospitals.isEmpty()) { ErrorBanner(it); Gap() } }
        Field(s.hospitalQuery, { model.state.value = s.copy(hospitalQuery = it) }, "Search hospitals")
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
    StepFrame(nav, null, s.hospital?.name ?: "Your hospital", step = Step.PATH) {
        Panel(onClick = { model.state.value = s.copy(path = Path.FIND_RECORD); nav.navigate(Step.IDENTITY.name) }) {
            Text("My care team set me up", style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
            Text("Find the record they made for you.", style = MaterialTheme.typography.bodyMedium, color = MP.colors.body)
        }
        Gap()
        Panel(onClick = { model.state.value = s.copy(path = Path.JOIN_GENERAL); nav.navigate(Step.JOIN.name) }) {
            Text("I'm new here", style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
            Text("Join as a new patient at this hospital.", style = MaterialTheme.typography.bodyMedium, color = MP.colors.body)
        }
    }
}

@Composable
private fun IdentityStep(nav: NavHostController, model: OnboardingModel) {
    val s by model.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    LaunchedEffect(s.name, s.phone) { delay(350); model.search() }
    StepFrame(nav, null, "Find your record", step = Step.IDENTITY, blurb = "Your name and mobile number, as your care team has them.") {
        s.error?.let { ErrorBanner(it, onDismiss = { model.state.value = s.copy(error = null) }); Gap() }
        Field(s.name, { model.state.value = s.copy(name = it) }, "Full name")
        Gap(8.dp)
        Field(s.phone, { model.state.value = s.copy(phone = it) }, "Mobile number", keyboard = KeyboardType.Phone)
        Gap()
        if (s.searching) Text("Searching…", color = c.muted, style = MaterialTheme.typography.bodyMedium)
        s.candidates.forEach { cand ->
            val sel = s.selected?.patientId == cand.patientId
            Panel(padding = 14.dp, tint = if (sel) c.brandTint else null, onClick = { model.state.value = s.copy(selected = cand) }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(cand.displayName, style = MaterialTheme.typography.titleMedium, color = c.ink)
                        Text(listOfNotNull(cand.procedureDisplay.takeIf { it.isNotBlank() }, cand.surgeryMonth).joinToString(" · "),
                            style = MaterialTheme.typography.bodyMedium, color = c.muted)
                    }
                    if (cand.phoneMatch) Text("Number matches", style = MaterialTheme.typography.labelMedium, color = c.brandInk)
                }
            }
            Gap(8.dp)
        }
        if (s.name.trim().length >= 2 && !s.searching && s.candidates.isEmpty()) {
            Text("Not on the list?", color = c.muted, style = MaterialTheme.typography.bodyMedium)
        }
        PlainButton("Join as a new patient instead") { model.state.value = s.copy(path = Path.JOIN_GENERAL); nav.navigate(Step.JOIN.name) }
        Gap()
        PrimaryButton("This is me", enabled = s.canEnroll, loading = s.working) {
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
    StepFrame(nav, null, "Join as a new patient", step = Step.JOIN) {
        s.error?.let { ErrorBanner(it, onDismiss = { model.state.value = s.copy(error = null) }); Gap() }
        Field(s.name, { model.state.value = s.copy(name = it) }, "Full name")
        Gap(8.dp)
        Field(s.phone, { model.state.value = s.copy(phone = it) }, "Mobile number", keyboard = KeyboardType.Phone)
        Gap()
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Date of birth", Modifier.weight(1f), color = c.ink)
            TextButton(onClick = { pickDob = true }) { Text(s.dateOfBirth?.toString() ?: "Add (optional)") }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("I'm recovering from an operation", Modifier.weight(1f), color = c.ink)
            Switch(checked = s.hadSurgery, onCheckedChange = { v ->
                model.state.value = s.copy(hadSurgery = v, path = if (v) Path.JOIN_AFTER_SURGERY else Path.JOIN_GENERAL)
            })
        }
        if (s.hadSurgery) {
            Gap(8.dp)
            Text("Which operation?", style = MaterialTheme.typography.labelMedium, color = c.muted)
            Gap(6.dp)
            FlowChips(s.procedures.map { it.label }, s.procedures.indexOf(s.procedure)) { i ->
                model.state.value = s.copy(procedure = s.procedures[i])
            }
            Gap(8.dp)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Date of surgery", Modifier.weight(1f), color = c.ink)
                TextButton(onClick = { pickSurgery = true }) { Text(s.surgeryDate.toString()) }
            }
        }
        Gap(16.dp)
        PrimaryButton("Join", enabled = s.canJoin, loading = s.working) {
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
    val context = LocalContext.current
    // The texted code, read with the person's consent (the SMS User Consent
    // API: Android shows one sheet naming the message; nothing else is read).
    // The iPhone autofills it from the keyboard; this is the nearest thing.
    val consent = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode != Activity.RESULT_OK) return@rememberLauncherForActivityResult
        val message = result.data?.getStringExtra(SmsRetriever.EXTRA_SMS_MESSAGE).orEmpty()
        Regex("""(\d{6})""").find(message)?.value?.let { code -> model.state.update { it.copy(code = code) } }
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
    StepFrame(nav, null, "Enter the code we texted", step = Step.VERIFY,
        blurb = "Sent to ${s.phoneMasked ?: "your number"}. It expires in ten minutes.") {
        s.error?.let { ErrorBanner(it, onDismiss = { model.state.value = s.copy(error = null) }); Gap() }
        Field(s.code, { model.state.value = s.copy(code = it.filter { ch -> ch.isDigit() }.take(8)) }, "6-digit code",
            keyboard = KeyboardType.NumberPassword)
        Gap(16.dp)
        PrimaryButton("Confirm", enabled = s.code.length >= 4, loading = s.working) {
            scope.launch { model.verify()?.let { nav.navigate(it.name) } }
        }
        PlainButton("Send a new code") { scope.launch { model.resend() } }
    }
}

@Composable
private fun HealthStep(nav: NavHostController, app: AppModel) {
    StepFrame(nav, null, "Connect Health Connect", back = false, step = Step.HEALTH,
        blurb = "Steps, sleep, heart rate and workouts from your phone and watch, so your care team can follow your recovery between visits.") {
        HealthConnectCard(app)
        Gap()
        SecondaryButton("Skip for now") { nav.navigate(Step.WALKS.name) }
        Gap(8.dp)
        PrimaryButton("Continue") { nav.navigate(Step.WALKS.name) }
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
    StepFrame(nav, null, "Let MedPull notice your walks", back = false, step = Step.WALKS,
        blurb = "Your walking speed, step length and symmetry tell your care team how you are healing. With your phone in a pocket, MedPull can measure them from everyday walks without you doing anything.") {
        Panel {
            Text("How it works", style = MaterialTheme.typography.titleMedium, color = c.ink)
            Gap(6.dp)
            Text("• When your phone notices you walking, it records two minutes of motion, at most once every half hour.", color = c.body, style = MaterialTheme.typography.bodyMedium)
            Text("• A silent line shows in your notifications while it records. You can swipe it away.", color = c.body, style = MaterialTheme.typography.bodyMedium)
            Text("• Nothing is recorded when you are still, and you can turn it off any time from Connections.", color = c.body, style = MaterialTheme.typography.bodyMedium)
        }
        Gap()
        if (on) {
            Text("On. Your walks will be measured automatically.", color = c.brandInk, style = MaterialTheme.typography.bodyMedium)
            Gap(8.dp)
            PrimaryButton("Continue") { nav.navigate(Step.WEARABLE.name) }
        } else {
            if (declined) { Text("You can turn this on later from Today or Connections.", color = c.muted, style = MaterialTheme.typography.bodyMedium); Gap(8.dp) }
            SecondaryButton("Not now") { nav.navigate(Step.WEARABLE.name) }
            Gap(8.dp)
            PrimaryButton("Turn on") { enable() }
        }
    }
}

@Composable
private fun WearableStep(nav: NavHostController, app: AppModel) {
    StepFrame(nav, null, "Add a wearable", back = false, step = Step.WEARABLE,
        blurb = "Oura, Fitbit, Garmin, Whoop, Withings or Polar: sign in once and MedPull reads it from then on.") {
        WearableLinkCard(app)
        Gap()
        PrimaryButton("Done") { nav.navigate(Step.DONE.name) }
    }
}

@Composable
private fun DoneStep(app: AppModel) {
    val state by app.state.collectAsStateWithLifecycle()
    val name = state.me?.patient?.firstName?.takeIf { it.isNotBlank() }
    StepFrame(null, "You're set", if (name != null) "Welcome, $name." else "Welcome.", back = false,
        blurb = "Your care team can now see how you are doing. Open the app each day for your plan, and tap Measure every few days for a short walk test.") {
        PrimaryButton("Open MedPull") { app.enterHome() }
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
        }) { Text("OK") }
    }, dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }) { DatePicker(state = st) }
}
