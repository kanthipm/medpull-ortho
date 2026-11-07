package com.medpull.recovery.features.consent

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.medpull.recovery.R
import com.medpull.recovery.core.ConsentDocument
import com.medpull.recovery.ui.Field
import com.medpull.recovery.ui.Gap
import com.medpull.recovery.ui.MP
import com.medpull.recovery.ui.Panel

/**
 * The beta consent, as onboarding and the in-app gate both show it: the text
 * the server serves, one checkbox per scope, and a typed signature. The
 * caller owns the state and the button.
 */
@Composable
fun ConsentForm(doc: ConsentDocument, scopes: Map<String, Boolean>, onScope: (String, Boolean) -> Unit,
                signature: String, onSignature: (String) -> Unit) {
    val c = MP.colors
    Panel { Text(doc.text, style = MaterialTheme.typography.bodyMedium, color = c.body) }
    Gap()
    doc.scopes.forEach { sc ->
        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = scopes[sc.key] == true, onCheckedChange = { onScope(sc.key, it) })
            Column {
                Text(sc.label, style = MaterialTheme.typography.bodyLarge, color = c.ink)
                Text(if (sc.required) stringResource(R.string.consent_required) else stringResource(R.string.consent_optional),
                    style = MaterialTheme.typography.bodyMedium, color = c.muted)
                if (sc.detail.isNotBlank()) Text(sc.detail, style = MaterialTheme.typography.bodyMedium, color = c.body)
            }
        }
    }
    Gap()
    Field(signature, onSignature, stringResource(R.string.consent_sign_field))
}

/** Every required scope ticked and a name typed. */
fun ConsentDocument.agreed(scopes: Map<String, Boolean>, signature: String): Boolean =
    this.scopes.filter { it.required }.all { scopes[it.key] == true } && signature.trim().length >= 2
