package com.medpull.recovery.features.measure

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import com.medpull.recovery.core.PortfolioMetric
import com.medpull.recovery.ui.MP
import java.time.LocalDate

/** When each test is due, from the portfolio's latest readings (as on iPhone). */
object MeasureStatus {
    data class Test(val name: String, val everyDays: Long, val keys: List<String>)
    val tests = listOf(
        Test("Guided walk", 2, listOf("cadence", "walking_steadiness", "step_length", "walking_speed")),
        Test("Six-minute walk", 7, listOf("six_min_walk")),
        Test("Range of motion", 3, listOf("rom_flexion", "rom_extension", "rom_abduction")),
    )
    fun lastDone(test: Test, portfolio: List<PortfolioMetric>): LocalDate? =
        portfolio.filter { it.key in test.keys }.flatMap { it.series }.mapNotNull { runCatching { LocalDate.parse(it.date.take(10)) }.getOrNull() }.maxOrNull()
    fun isDue(test: Test, portfolio: List<PortfolioMetric>): Boolean {
        val last = lastDone(test, portfolio) ?: return true
        return !last.plusDays(test.everyDays).isAfter(LocalDate.now())
    }
    fun due(portfolio: List<PortfolioMetric>): List<String> = tests.filter { isDue(it, portfolio) }.map { it.name }
}

@Composable
fun MeasureScreen(nav: NavHostController) {
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("Measure", style = MaterialTheme.typography.displaySmall, color = MP.colors.ink)
        Text("The walk and range-of-motion tests land in the next build.", color = MP.colors.muted)
    }
}

@Composable
fun GuidedWalkScreen(nav: NavHostController, sixMinute: Boolean) { Text("Soon", modifier = Modifier.padding(16.dp)) }

@Composable
fun RangeOfMotionScreen(nav: NavHostController) { Text("Soon", modifier = Modifier.padding(16.dp)) }
