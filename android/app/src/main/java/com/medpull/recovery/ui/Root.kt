package com.medpull.recovery.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChatBubble
import androidx.compose.material.icons.filled.DirectionsWalk
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.medpull.recovery.MedPullApp
import com.medpull.recovery.core.AppModel
import com.medpull.recovery.core.Phase
import com.medpull.recovery.core.Tab
import com.medpull.recovery.features.care.CareScreen
import com.medpull.recovery.features.measure.GuidedWalkScreen
import com.medpull.recovery.features.measure.MeasureScreen
import com.medpull.recovery.features.measure.RangeOfMotionScreen
import com.medpull.recovery.features.onboarding.OnboardingFlow
import com.medpull.recovery.features.personal.ConsentGate
import com.medpull.recovery.features.personal.PersonalPlaceholder
import com.medpull.recovery.features.profile.ConnectionsScreen
import com.medpull.recovery.features.profile.ProfileScreen
import com.medpull.recovery.features.progress.CareMetricDetailScreen
import com.medpull.recovery.features.progress.ProgressScreen
import com.medpull.recovery.features.progress.SignalDetailScreen
import com.medpull.recovery.features.tasks.CheckinScreen
import com.medpull.recovery.features.tasks.TaskDetailScreen
import com.medpull.recovery.features.tasks.TaskHistoryScreen
import com.medpull.recovery.features.today.TodayScreen

@Composable
fun appModel(): AppModel = (LocalContext.current.applicationContext as MedPullApp).graph.app

@Composable
fun RootView() {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { if (state.phase == Phase.LAUNCHING) app.bootstrap() }
    Box(Modifier.fillMaxSize().background(MP.colors.canvas)) {
        when (state.phase) {
            Phase.LAUNCHING -> Spinner(Modifier.padding(top = 120.dp))
            Phase.ONBOARDING -> OnboardingFlow()
            Phase.HOME -> when {
                state.needsConsent -> ConsentGate()
                state.isPersonal -> PersonalPlaceholder()
                else -> MainTabs()
            }
        }
    }
}

object Routes {
    const val TODAY = "today"; const val PROGRESS = "progress"; const val MEASURE = "measure"; const val CARE = "care"
    const val TASK = "task/{id}"; const val CHECKIN = "checkin/{id}"; const val HISTORY = "history"
    const val SIGNAL = "signal/{key}"; const val METRIC = "metric/{id}"
    const val WALK = "walk/{sixMinute}"; const val ROM = "rom"
    const val PROFILE = "profile"; const val CONNECTIONS = "connections"
    fun task(id: Int) = "task/$id"
    fun checkin(id: Int) = "checkin/$id"
    fun signal(key: String) = "signal/$key"
    fun metric(id: String) = "metric/$id"
    fun walk(sixMinute: Boolean) = "walk/$sixMinute"
    val tabs = listOf(TODAY, PROGRESS, MEASURE, CARE)
}

@Composable
fun MainTabs() {
    val app = appModel()
    val state by app.state.collectAsStateWithLifecycle()
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route
    val c = MP.colors

    // The model's selected tab (deep links, cross-tab buttons) drives navigation.
    LaunchedEffect(state.selectedTab) {
        val target = when (state.selectedTab) {
            Tab.TODAY -> Routes.TODAY; Tab.PROGRESS -> Routes.PROGRESS; Tab.MEASURE -> Routes.MEASURE; Tab.CARE -> Routes.CARE
        }
        if (route != target) nav.navigateTab(target)
    }
    LaunchedEffect(state.showConnections) { if (state.showConnections) { nav.navigate(Routes.CONNECTIONS); app.showConnections(false) } }

    Scaffold(
        containerColor = c.canvas,
        bottomBar = {
            if (route in Routes.tabs) NavigationBar(containerColor = c.panel, tonalElevation = 0.dp) {
                val items = listOf(
                    Triple(Routes.TODAY, "Today", Icons.Default.Home),
                    Triple(Routes.PROGRESS, "Progress", Icons.Default.ShowChart),
                    Triple(Routes.MEASURE, "Measure", Icons.Default.DirectionsWalk),
                    Triple(Routes.CARE, "Care", Icons.Default.ChatBubble),
                )
                items.forEach { (r, label, icon) ->
                    val badge = when (r) {
                        Routes.TODAY -> state.tasks.open.size
                        Routes.CARE -> state.me?.unreadMessages ?: 0
                        else -> 0
                    }
                    NavigationBarItem(
                        selected = route == r,
                        onClick = { app.selectTab(tabFor(r)); nav.navigateTab(r) },
                        icon = {
                            BadgedBox(badge = { if (badge > 0) Badge { Text("$badge") } }) { Icon(icon, label) }
                        },
                        label = { Text(label) },
                        colors = NavigationBarItemDefaults.colors(selectedIconColor = c.ink, selectedTextColor = c.ink,
                            indicatorColor = c.soft, unselectedIconColor = c.muted, unselectedTextColor = c.muted),
                    )
                }
            }
        },
    ) { padding ->
        NavHost(nav, startDestination = Routes.TODAY, modifier = Modifier.padding(padding)) {
            composable(Routes.TODAY) { TodayScreen(nav) }
            composable(Routes.PROGRESS) { ProgressScreen(nav) }
            composable(Routes.MEASURE) { MeasureScreen(nav) }
            composable(Routes.CARE) { CareScreen(nav) }
            composable(Routes.TASK) { TaskDetailScreen(nav, it.arguments?.getString("id")?.toIntOrNull()) }
            composable(Routes.CHECKIN) { CheckinScreen(nav, it.arguments?.getString("id")?.toIntOrNull()) }
            composable(Routes.HISTORY) { TaskHistoryScreen(nav) }
            composable(Routes.SIGNAL) { SignalDetailScreen(nav, it.arguments?.getString("key").orEmpty()) }
            composable(Routes.METRIC) { CareMetricDetailScreen(nav, it.arguments?.getString("id").orEmpty()) }
            composable(Routes.WALK) { GuidedWalkScreen(nav, it.arguments?.getString("sixMinute") == "true") }
            composable(Routes.ROM) { RangeOfMotionScreen(nav) }
            composable(Routes.PROFILE) { ProfileScreen(nav) }
            composable(Routes.CONNECTIONS) { ConnectionsScreen(nav) }
        }
    }
}

private fun tabFor(route: String) = when (route) {
    Routes.PROGRESS -> Tab.PROGRESS; Routes.MEASURE -> Tab.MEASURE; Routes.CARE -> Tab.CARE; else -> Tab.TODAY
}

fun NavHostController.navigateTab(route: String) = navigate(route) {
    popUpTo(graph.startDestinationId) { saveState = true }
    launchSingleTop = true
    restoreState = true
}
