package com.medpull.recovery.core

import android.net.Uri
import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class Phase { LAUNCHING, ONBOARDING, HOME }
enum class Tab { TODAY, PROGRESS, MEASURE, CARE }

/** Everything the screens read, in one immutable snapshot. */
data class AppState(
    val phase: Phase = Phase.LAUNCHING,
    val me: Me? = null,
    val tasks: TasksResponse = TasksResponse(),
    val messages: List<ChatMessage> = emptyList(),
    val portfolio: List<PortfolioMetric> = emptyList(),
    val metrics: PatientMetricsResponse? = null,
    val wearables: WearableSummary? = null,
    val lastError: String? = null,
    val pendingTaskId: Int? = null,
    val selectedTab: Tab = Tab.TODAY,
    val showConnections: Boolean = false,
    val paywall: Boolean = false,
) {
    val isPersonal get() = me?.isPersonal == true
    val needsConsent get() = me?.needsConsent == true
}

/**
 * Root state: who is signed in, what the server says about them, and the
 * feeds the tabs show. One instance lives in the app graph; screens read
 * it and call its actions. Mirrors ios/MedPull/Core/AppModel.swift.
 */
class AppModel(val api: ApiClient, private val session: SessionStore, val config: AppConfig) {
    private val _state = MutableStateFlow(AppState())
    val state: StateFlow<AppState> = _state
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    val current: AppState get() = _state.value

    // --- lifecycle ------------------------------------------------------------------

    fun bootstrap() {
        if (session.token != null) {
            _state.update { it.copy(phase = Phase.HOME) }
            scope.launch { refreshAll() }
        } else {
            _state.update { it.copy(phase = Phase.ONBOARDING) }
        }
    }

    /** Enrollment succeeded: keep the credential and act as this patient,
     *  but stay in onboarding so the Health and wearable steps can run. */
    fun adoptSession(token: String, me: Me) {
        session.set(token, me.patient.id)
        _state.update { it.copy(me = me) }
    }

    fun enterHome() {
        _state.update { it.copy(phase = Phase.HOME) }
        scope.launch { refreshAll() }
    }

    suspend fun signOut() {
        try { api.signOut() } catch (_: Exception) {}
        session.clear()
        _state.value = AppState(phase = Phase.ONBOARDING)
    }

    // --- feeds ------------------------------------------------------------------------

    enum class Outcome { OK, FAILED, CANCELLED }

    private suspend fun refresh(surface: Boolean = true, work: suspend () -> Unit): Outcome {
        return try {
            work()
            clearError()
            Outcome.OK
        } catch (e: CancellationException) {
            Outcome.CANCELLED
        } catch (e: ApiException) {
            if (e.isUnauthorized) { scope.launch { signOut() }; return Outcome.FAILED }
            if (e.isPaywall) { _state.update { it.copy(paywall = true) }; return Outcome.FAILED }
            if (surface) _state.update { it.copy(lastError = e.detail) }
            Outcome.FAILED
        } catch (e: Exception) {
            Log.w("AppModel", "refresh failed", e)
            if (surface) _state.update { it.copy(lastError = e.message ?: "Something went wrong.") }
            Outcome.FAILED
        }
    }

    /** Four calls share one banner: it shows only when nothing got through.
     *  The four are independent, so they go out together rather than one
     *  after another — the tabs fill in at once instead of in turn. Each
     *  still records its own outcome, so the banner rule is unchanged. */
    suspend fun refreshAll() {
        val outcomes = coroutineScope {
            listOf(
                async { refresh(false) { val me = api.me(); _state.update { it.copy(me = me) } } },
                async { refresh(false) { val t = api.tasks(); _state.update { it.copy(tasks = t) } } },
                async { refresh(false) { val m = api.messages(); _state.update { it.copy(messages = m) } } },
                async { refresh(false) { val p = api.portfolio(14); _state.update { it.copy(portfolio = p.metrics) } } },
            ).awaitAll()
        }
        if (Outcome.OK in outcomes) clearError()
        else if (Outcome.FAILED in outcomes) {
            _state.update { it.copy(lastError = "Can't reach MedPull right now. Check your connection.") }
        }
    }

    suspend fun refreshMe(surface: Boolean = true) = refresh(surface) { val me = api.me(); _state.update { it.copy(me = me) } }
    suspend fun refreshTasks(surface: Boolean = true) = refresh(surface) { val t = api.tasks(); _state.update { it.copy(tasks = t) } }
    suspend fun refreshMessages(surface: Boolean = true) = refresh(surface) { val m = api.messages(); _state.update { it.copy(messages = m) } }
    suspend fun refreshPortfolio(surface: Boolean = true) = refresh(surface) { val p = api.portfolio(14); _state.update { it.copy(portfolio = p.metrics) } }
    suspend fun refreshMetrics(surface: Boolean = true) = refresh(surface) { val m = api.metrics(); _state.update { it.copy(metrics = m) } }
    suspend fun refreshWearables(force: Boolean = false, surface: Boolean = true) = refresh(surface) {
        val r = if (force) api.refreshWearables() else api.wearables()
        _state.update { it.copy(wearables = r.summary) }
    }

    // --- actions ----------------------------------------------------------------------

    suspend fun complete(task: RecoveryTask, answers: Map<String, AnswerValue>, via: String = "app") {
        api.complete(task.id, answers, via)
        refreshTasks(); refreshMe()
    }

    suspend fun skip(task: RecoveryTask) { api.skip(task.id); refreshTasks() }

    suspend fun send(text: String, attachmentIds: List<Int> = emptyList()) {
        val m = api.sendMessage(text, attachmentIds)
        _state.update { it.copy(messages = it.messages + m) }
    }

    suspend fun markMessagesRead() { try { api.markMessagesRead() } catch (_: Exception) {}; refreshMe(false) }

    suspend fun ask(text: String, channel: String): AgentResponse {
        val r = api.agent(text, channel)
        refreshTasks(false); refreshMessages(false)
        return r
    }

    suspend fun acceptConsent(doc: ConsentDocument, scopes: Map<String, Boolean>, signature: String) {
        api.acceptConsent(ConsentBody(doc.version, scopes, signature, AppConfig.deviceName, config.appVersion))
        refreshMe()
    }

    suspend fun switchSpace(patientId: String) {
        val stored = session.tokenFor(patientId)
        if (stored != null) {
            session.set(stored, patientId)
            if (refreshMe(false) == Outcome.OK) { refreshAll(); return }
        }
        val r = api.switchProfile(SwitchBody(patientId, AppConfig.deviceName, config.appVersion))
        val token = r.sessionToken ?: throw ApiException(0, "The server didn't return a session.")
        session.set(token, patientId)
        r.me?.let { me -> _state.update { it.copy(me = me) } }
        refreshAll()
    }

    // --- ui state ---------------------------------------------------------------------

    fun selectTab(tab: Tab) = _state.update { it.copy(selectedTab = tab) }
    fun showConnections(show: Boolean) = _state.update { it.copy(showConnections = show) }
    fun consumePendingTask() = _state.update { it.copy(pendingTaskId = null) }
    fun clearError() = _state.update { it.copy(lastError = null) }
    fun dismissPaywall() = _state.update { it.copy(paywall = false) }

    /** What to show the person when an action fails, or null when there is nothing to say. */
    fun note(e: Throwable) {
        if (e is CancellationException) return
        if (e is ApiException && e.isUnauthorized) { scope.launch { signOut() }; return }
        _state.update { it.copy(lastError = e.message ?: "Something went wrong.") }
    }

    // --- links ------------------------------------------------------------------------

    /** medpull://tasks/<id> opens the task; medpull://wearables[/connected] refreshes. */
    fun handle(uri: Uri) {
        if (uri.scheme != config.scheme) return
        when (uri.host) {
            "tasks" -> uri.lastPathSegment?.toIntOrNull()?.let { id ->
                _state.update { it.copy(pendingTaskId = id, selectedTab = Tab.TODAY) }
                scope.launch { refreshTasks(false) }
            }
            "wearables" -> {
                _state.update { it.copy(showConnections = true) }
                scope.launch { refreshWearables(force = true, surface = false) }
            }
        }
    }
}
