package com.medpull.recovery.features.onboarding

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.medpull.recovery.MedPullApp
import com.medpull.recovery.core.AppModel
import com.medpull.recovery.features.profile.HealthConnectCard
import com.medpull.recovery.features.profile.WearableLinkCard
import com.medpull.recovery.ui.Chip
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.Guardrail
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.Panel
import com.medpull.recovery.ui.PlainButton
import com.medpull.recovery.ui.PrimaryButton
import com.medpull.recovery.ui.SecondaryButton
import com.medpull.recovery.ui.appModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

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
        composable(Step.WEARABLE.name) { WearableStep(nav, app) }
        composable(Step.DONE.name) { DoneStep(app) }
    }
}

@Composable
private fun StepFrame(nav: NavHostController?, kicker: String?, title: String, blurb: String? = null,
                      back: Boolean = true, content: @Composable () -> Unit) {
    val c = MP.colors
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 20.dp, vertical = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.height(48.dp)) {
            if (back && nav != null && nav.previousBackStackEntry != null) {
                IconButton(onClick = { nav.popBackStack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = c.ink) }
            }
        }
        if (kicker != null) Text(kicker.uppercase(), style = MaterialTheme.typography.labelSmall, color = c.muted)
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
    StepFrame(nav, "Step 1", "Who set you up?") {
        // No consent yet: a returning patient finding their record has signed
        // already, and the server says so (the gate in Root covers an account
        // that still needs to). The form comes before a NEW record is created.
        Panel(onClick = { nav.navigate(Step.HOSPITAL.name) }) {
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
        PrimaryButton("Continue with my care team") { nav.navigate(Step.HOSPITAL.name) }
    }
}

@Composable
private fun ConsentStep(nav: NavHostController, model: OnboardingModel) {
    val s by model.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    LaunchedEffect(Unit) { model.loadConsent() }
    StepFrame(nav, "Before we start", "Please read and agree",
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
    StepFrame(nav, "Step 1 of 5", "Where are you being treated?") {
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
    StepFrame(nav, "Step 2 of 5", s.hospital?.name ?: "Your hospital") {
        Panel(onClick = { model.state.value = s.copy(path = Path.FIND_RECORD); nav.navigate(Step.IDENTITY.name) }) {
            Text("My care team set me up", style = MaterialTheme.typography.titleLarge, color = MP.colors.ink)
            Text("Find the record they made for you.", style = MaterialTheme.typography.bodyMedium, color = MP.colors.body)
        }
        Gap()
        Panel(onClick = {
            model.state.value = s.copy(path = Path.JOIN_GENERAL)
            // Starting a record creates an account, so the consent comes first — once.
            nav.navigate((if (s.accepted == null) Step.CONSENT else Step.JOIN).name)
        }) {
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
    StepFrame(nav, "Step 3 of 5", "Find your record", blurb = "Your name and mobile number, as your care team has them.") {
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
        PlainButton("Join as a new patient instead") {
            model.state.value = s.copy(path = Path.JOIN_GENERAL)
            nav.navigate((if (s.accepted == null) Step.CONSENT else Step.JOIN).name)
        }
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
    StepFrame(nav, "Step 3 of 5", "Join as a new patient") {
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
    if (s.textFirst) {
        TextFirstStep(nav, model)
        return
    }
    StepFrame(nav, "Step 4 of 5", "Enter the code we texted",
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
    StepFrame(nav, "Step 4 of 5", "Text us first",
        blurb = "Before we can text ${s.phoneMasked ?: "your number"}, send us one message from it. Tap below — the text is already written — then come back here.") {
        Panel {
            Text("Text “${s.textBody ?: "Hi MedPull"}” to", style = MaterialTheme.typography.labelMedium, color = c.muted)
            Gap(4.dp)
            Text(formatPhone(s.textTo), style = MaterialTheme.typography.titleLarge, color = c.ink)
            Gap(6.dp)
            Text("We'll text your code the moment it arrives.", style = MaterialTheme.typography.bodyMedium, color = c.body)
        }
        s.error?.let { Gap(); ErrorBanner(it, onDismiss = { model.state.value = s.copy(error = null) }) }
        Gap(16.dp)
        PrimaryButton("Open Messages") {
            val uri = model.textFirstUri() ?: return@PrimaryButton
            try {
                context.startActivity(Intent(Intent.ACTION_SENDTO, Uri.parse(uri)))
            } catch (_: ActivityNotFoundException) {
                model.state.value = s.copy(error = "No messaging app found — text ${formatPhone(s.textTo)} from your phone, then come back.")
            }
        }
        Gap(8.dp)
        SecondaryButton("I've sent it — send my code", loading = s.working) {
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
    StepFrame(nav, "Step 5 of 5", "Connect Health Connect", back = false,
        blurb = "Steps, sleep, heart rate and workouts from your phone and watch, so your care team can follow your recovery between visits.") {
        HealthConnectCard(app)
        Gap()
        SecondaryButton("Skip for now") { nav.navigate(Step.WEARABLE.name) }
        Gap(8.dp)
        PrimaryButton("Continue") { nav.navigate(Step.WEARABLE.name) }
    }
}

@Composable
private fun WearableStep(nav: NavHostController, app: AppModel) {
    StepFrame(nav, "Almost done", "Add a wearable", back = false,
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

@Composable
fun Field(value: String, onChange: (String) -> Unit, label: String, keyboard: KeyboardType = KeyboardType.Text,
          password: Boolean = false, modifier: Modifier = Modifier, singleLine: Boolean = true) {
    val c = MP.colors
    OutlinedTextField(
        value = value, onValueChange = onChange, label = { Text(label) }, singleLine = singleLine,
        modifier = modifier.fillMaxWidth().heightIn(min = 52.dp),
        keyboardOptions = KeyboardOptions(keyboardType = keyboard),
        visualTransformation = if (password) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        shape = androidx.compose.foundation.shape.RoundedCornerShape(14.dp),
        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = c.brand, unfocusedBorderColor = c.lineStrong,
            focusedTextColor = c.ink, unfocusedTextColor = c.ink, cursorColor = c.brand, focusedLabelColor = c.brandInk,
            unfocusedLabelColor = c.muted),
    )
}

@Composable
fun FlowChips(labels: List<String>, selected: Int, onSelect: (Int) -> Unit) {
    androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        labels.forEachIndexed { i, l -> Chip(l, selected = i == selected) { onSelect(i) } }
    }
}

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
