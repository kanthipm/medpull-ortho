import Foundation
import Observation

/// Root state: who is signed in, what the server says about them, and the
/// three feeds the tabs show (tasks, messages, progress). One instance lives
/// in the environment; screens read it and call its actions.
@Observable
@MainActor
final class AppModel {
    enum Phase { case launching, onboarding, home }

    private(set) var phase: Phase = .launching
    let api = APIClient()
    let health = HealthConnector()

    var me: Me?
    var tasks: TasksResponse = TasksResponse(open: [], recent: [])
    var messages: [ChatMessage] = []
    var progress: [ProgressDay] = []
    var portfolio: [PortfolioMetric] = []
    var wearables: WearableSummary?
    var lastError: String?

    /// Set by a `medpull://tasks/<id>` link; the Tasks tab opens it.
    var pendingTaskId: Int?
    var selectedTab: Tab = .home

    enum Tab: Hashable { case home, tasks, talk, messages, health }

    private static let tokenKey = "session_token"

    // MARK: lifecycle

    func bootstrap() async {
        if let token = Keychain.get(Self.tokenKey) {
            api.token = token
            phase = .home
            health.restore()
            await refreshAll()
        } else {
            phase = .onboarding
        }
    }

    /// Enrollment succeeded: keep the credential and act as this patient,
    /// but stay in onboarding so the Health and wearable steps can run.
    func adoptSession(token: String, me: Me) {
        Keychain.set(token, for: Self.tokenKey)
        api.token = token
        self.me = me
    }

    func enterHome() {
        phase = .home
        Task { await refreshAll() }
    }

    func signOut() async {
        try? await api.signOut()
        await health.disconnect()
        Keychain.delete(Self.tokenKey)
        api.token = nil
        me = nil
        tasks = TasksResponse(open: [], recent: [])
        messages = []
        progress = []
        portfolio = []
        wearables = nil
        phase = .onboarding
    }

    // MARK: feeds

    func refreshAll() async {
        await refreshMe()
        await refreshTasks()
        await refreshMessages()
        await refreshPortfolio()
    }

    func refreshMe() async {
        do { me = try await api.me() } catch { note(error) }
    }

    func refreshTasks() async {
        do { tasks = try await api.tasks() } catch { note(error) }
    }

    func refreshMessages() async {
        do { messages = try await api.messages() } catch { note(error) }
    }

    func refreshProgress() async {
        do { progress = try await api.progress(days: 14).days } catch { note(error) }
    }

    func refreshPortfolio() async {
        do { portfolio = try await api.portfolio(days: 14).metrics } catch { note(error) }
    }

    func refreshWearables(force: Bool = false) async {
        do {
            let r = force ? try await api.refreshWearables() : try await api.wearables()
            wearables = r.summary
        } catch { note(error) }
    }

    // MARK: actions

    func complete(_ task: RecoveryTask, answers: [String: AnswerValue], via: String = "app") async throws {
        _ = try await api.complete(taskId: task.id, answers: answers, via: via)
        await refreshTasks()
        await refreshMe()
    }

    func skip(_ task: RecoveryTask) async throws {
        _ = try await api.skip(taskId: task.id)
        await refreshTasks()
    }

    func send(message text: String) async throws {
        let m = try await api.sendMessage(text)
        messages.append(m)
    }

    func markMessagesRead() async {
        try? await api.markMessagesRead()
        await refreshMe()
    }

    func ask(_ text: String, channel: String) async throws -> AgentResponse {
        let r = try await api.agent(text, channel: channel)
        await refreshTasks()
        await refreshMessages()
        return r
    }

    func connectAppleHealth() async -> Bool {
        guard let me else { return false }
        let ok = await health.connect(patientId: me.patient.id, api: api)
        if ok {
            await refreshWearables(force: true)
            await refreshMe()
        }
        return ok
    }

    // MARK: links

    func handle(url: URL) {
        guard url.scheme == AppConfig.scheme else { return }
        switch url.host {
        case "tasks":
            if let id = Int(url.lastPathComponent) {
                pendingTaskId = id
                selectedTab = .tasks
                Task { await refreshTasks() }
            }
        case "wearables":
            selectedTab = .health
            Task { await refreshWearables(force: true) }
        default:
            break
        }
    }

    private func note(_ error: Error) {
        if let e = error as? APIError, e.isUnauthorized {
            Task { await signOut() }
            return
        }
        lastError = error.localizedDescription
    }
}
