package com.medpull.recovery.features.personal

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.medpull.recovery.core.ConsentDocument
import com.medpull.recovery.core.consentDocument
import com.medpull.recovery.features.consent.ConsentForm
import com.medpull.recovery.features.consent.agreed
import com.medpull.recovery.ui.ErrorBanner
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.PlainButton
import com.medpull.recovery.ui.PrimaryButton
import com.medpull.recovery.ui.SecondaryButton
import com.medpull.recovery.ui.appModel
import kotlinx.coroutines.launch

/** The consent gate: whenever the server says the form moved, before anything else. */
@Composable
fun ConsentGate() {
    val app = appModel()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    var doc by remember { mutableStateOf<ConsentDocument?>(null) }
    var scopes by remember { mutableStateOf<Map<String, Boolean>>(emptyMap()) }
    var signature by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var working by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        try { val d = app.api.consentDocument(); doc = d; scopes = d.scopes.associate { it.key to true } }
        catch (e: Exception) { error = e.message }
    }
    Column(Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(20.dp)) {
        Text("BEFORE WE CONTINUE", style = MaterialTheme.typography.labelSmall, color = c.muted)
        Text("Our consent form has changed", style = MaterialTheme.typography.displaySmall, color = c.ink)
        Gap()
        error?.let { ErrorBanner(it); Gap() }
        val d = doc
        if (d != null) {
            ConsentForm(d, scopes, onScope = { k, v -> scopes = scopes + (k to v) }, signature = signature, onSignature = { signature = it })
            Gap(16.dp)
            PrimaryButton("Agree", enabled = d.agreed(scopes, signature), loading = working) {
                scope.launch {
                    working = true
                    try { app.acceptConsent(d, scopes, signature.trim()) } catch (e: Exception) { error = e.message }
                    working = false
                }
            }
        }
        Gap()
        PlainButton("Sign out instead") { scope.launch { app.signOut() } }
    }
}

/** A personal-tier account on Android: the readouts are iPhone-only for now. */
@Composable
fun PersonalPlaceholder() {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val c = MP.colors
    val clinic = state.me?.profiles?.firstOrNull { it.kind == "clinic" }
    Column(Modifier.fillMaxSize().safeDrawingPadding().padding(20.dp)) {
        Text("MEDPULL PERSONAL", style = MaterialTheme.typography.labelSmall, color = c.muted)
        Text("Not on Android yet", style = MaterialTheme.typography.displaySmall, color = c.ink)
        Gap()
        Text("Your readiness, training and sleep readouts are on iPhone today and come to Android after the care-team app. Your account and data are unchanged.",
            style = MaterialTheme.typography.bodyLarge, color = c.body)
        Gap(20.dp)
        if (clinic != null) {
            PrimaryButton("Switch to my hospital space") { scope.launch { try { app.switchSpace(clinic.patientId) } catch (e: Exception) { app.note(e) } } }
            Gap(8.dp)
        }
        SecondaryButton("Sign out") { scope.launch { app.signOut() } }
    }
}
