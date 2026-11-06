package com.medpull.recovery.features.care

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import com.medpull.recovery.ui.MP

@Composable
fun CareScreen(nav: NavHostController) {
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("Care", style = MaterialTheme.typography.displaySmall, color = MP.colors.ink)
        Text("The thread lands in the next build.", color = MP.colors.muted)
    }
}
