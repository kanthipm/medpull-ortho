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

    /// What one refresh did. Cancelled is its own answer: SwiftUI tears down
    /// the task behind `.task` and `.refreshable` on every tab switch, and
    /// that is the screen moving on, not a success to report or a failure to
    /// complain about.
    enum Outcome { case ok, failed, cancelled }

    @discardableResult
    private func refresh(surface: Bool = true, _ work: () async throws -> Void) async -> Outcome {
        do {
            try await work()
            clearError()
            return .ok
        } catch is CancellationError {
            return .cancelled
        } catch {
            if let e = error as? APIError, e.isUnauthorized {
                Task { await signOut() }
                return .failed
            }
            if surface { lastError = error.localizedDescription }
            return .failed
        }
    }

    func refreshAll() async {
        // These four share one banner, and they used to write it in turn, so
        // the last one to finish decided whether the app looked broken. The
        // 14-day portfolio is the heaviest call and the first to be throttled,
        // which is how a working app ended up claiming it could not reach the
        // server while the three calls before it had just succeeded. The
        // banner now means what it says: nothing got through.
        let outcomes = [
            await refresh(surface: false) { self.me = try await self.api.me() },
            await refresh(surface: false) { self.tasks = try await self.api.tasks() },
            await refresh(surface: false) { self.messages = try await self.api.messages() },
            await refresh(surface: false) {
                self.portfolio = try await self.api.portfolio(days: 14).metrics
            },
        ]
        if outcomes.contains(.ok) {
            clearError()
        } else if outcomes.contains(.failed) {
            lastError = "Can't reach MedPull right now. Check your connection."
        }
    }

    @discardableResult
    func refreshMe(surface: Bool = true) async -> Outcome {
        await refresh(surface: surface) { self.me = try await self.api.me() }
    }

    @discardableResult
    func refreshTasks(surface: Bool = true) async -> Outcome {
        await refresh(surface: surface) { self.tasks = try await self.api.tasks() }
    }

    @discardableResult
    func refreshMessages(surface: Bool = true) async -> Outcome {
        await refresh(surface: surface) { self.messages = try await self.api.messages() }
    }

    @discardableResult
    func refreshProgress(surface: Bool = true) async -> Outcome {
        await refresh(surface: surface) { self.progress = try await self.api.progress(days: 14).days }
    }

    @discardableResult
    func refreshPortfolio(surface: Bool = true) async -> Outcome {
        await refresh(surface: surface) {
            self.portfolio = try await self.api.portfolio(days: 14).metrics
        }
    }

    @discardableResult
    func refreshWearables(force: Bool = false, surface: Bool = true) async -> Outcome {
        await refresh(surface: surface) {
            let r = force ? try await self.api.refreshWearables() : try await self.api.wearables()
            self.wearables = r.summary
        }
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

    /// Write to the care team. A photo can be the whole message, so the
    /// text may be empty when something is attached.
    func send(message text: String, attachmentIds: [Int] = []) async throws {
        let m = try await api.sendMessage(text, attachmentIds: attachmentIds)
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

    /// A successful request means the server is reachable again: drop a
    /// banner left over from an earlier failure (cold start, brief outage).
    private func clearError() { lastError = nil }

    /// What to show the person when an action fails, or nil when there is
    /// nothing to say. A cancelled request means the screen went away while
    /// it was in flight, which is not a failure and reads like nonsense when
    /// it is printed ("The operation couldn't be completed").
    static func message(for error: Error) -> String? {
        if error is CancellationError { return nil }
        if let e = error as? URLError, e.code == .cancelled { return nil }
        return error.localizedDescription
    }

    /// Surface a failure from an action the person is waiting on — sending a
    /// message, completing a task. Refreshes go through `refresh` instead,
    /// which knows the difference between a failure and a cancelled screen.
    func note(_ error: Error) {
        if error is CancellationError { return }
        if let e = error as? APIError, e.isUnauthorized {
            Task { await signOut() }
            return
        }
        lastError = error.localizedDescription
    }
}
