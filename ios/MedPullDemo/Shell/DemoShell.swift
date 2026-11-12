import Foundation
import Observation

/// The presenter's side of the demo app: who can be picked, becoming one of
/// them, and the links that land the app on a screen.
///
/// `AppModel` (shared with the real app) stays what it is there: one
/// signed-in person and their feeds. This object sits beside it in the
/// environment and holds everything the real app has no notion of. The
/// shared screens never read it; the demo's own screens do.
@Observable
@MainActor
final class DemoShell {
    let app: AppModel
    /// The signed-in person's exercise calendar (ios/MedPullDemo/Exercises),
    /// emptied here whenever the app becomes someone else.
    let exercises: ExerciseStore

    /// The demo's front door takes no credential: the persona list, a
    /// session for one of them, the day reset and the texted links are all
    /// called before (or regardless of) a session. This client never carries
    /// a token, so those requests go out with no Authorization header.
    private let door = APIClient()

    init(app: AppModel, exercises: ExerciseStore) {
        self.app = app
        self.exercises = exercises
        version = DemoVersion(rawValue: UserDefaults.standard.string(forKey: Self.versionKey) ?? "") ?? .clinic
    }

    // MARK: Who is on the demo

    enum RosterState: Equatable {
        case idle, loading, loaded
        case failed(String)
    }

    /// `GET /api/demo/personas`, as last read.
    private(set) var roster: DemoRoster?
    private(set) var rosterState: RosterState = .idle
    /// The persona whose session is being requested, so their row can spin.
    private(set) var signingIn: String?
    /// Why the last sign-in did not happen; shown above the list.
    var signInError: String?

    private static let versionKey = "demo_version"

    /// The version last looked at: the picker opens on it, and "Switch
    /// person" stays inside it.
    var version: DemoVersion {
        didSet { UserDefaults.standard.set(version.rawValue, forKey: Self.versionKey) }
    }

    /// The signed-in person's organisation: the name the persona list
    /// groups them under, or what `/me` says when the list is not loaded.
    var organisation: String? {
        guard let me = app.me else { return nil }
        if let org = roster?.org(ofPersona: me.patient.id) { return org.name }
        if me.isSports { return me.sports?.teamLine ?? "MedPull Sports" }
        if me.isPersonal { return "MedPull Personal" }
        return me.patient.hospital?.name
    }

    /// Read the persona list. With a list already on screen a failed
    /// refresh keeps it; with none, the failure is the state.
    func loadRoster() async {
        guard rosterState != .loading else { return }
        if roster == nil { rosterState = .loading }
        #if DEBUG
        // Simulator verification of the loading state: hold it for N seconds.
        if let hold = AppConfig.debugFlag("MP_HOLD_ROSTER"), let seconds = Double(hold) {
            try? await Task.sleep(for: .seconds(seconds))
        }
        #endif
        do {
            roster = try await door.demoPersonas()
            rosterState = .loaded
        } catch {
            guard roster == nil else { return }
            if let sentence = Self.sentence(
                for: error,
                notFound: "This server has no demo people on it. The demo app needs a MedPull demo server: check the server address."
            ) {
                rosterState = .failed(sentence)
            } else {
                // The screen went away mid-request; the next appearance asks again.
                rosterState = .idle
            }
        }
    }

    /// Ask the server for a session as one of the demo's people. Nil when
    /// it did not happen; `signInError` then says why. The caller adopts the
    /// answer (`adopt`), after closing whatever sheet it is standing in.
    func session(for persona: DemoPersona) async -> DemoSessionResponse? {
        guard signingIn == nil else { return nil }
        signingIn = persona.id
        signInError = nil
        defer { signingIn = nil }
        do {
            return try await door.demoSession(personaId: persona.id)
        } catch {
            signInError = Self.sentence(
                for: error,
                notFound: "\(persona.name) is not on this demo any more. Pull down to refresh the list."
            )
            return nil
        }
    }

    /// Become this person. The token is always taken, even for the person
    /// already signed in: the server keeps one live session per person and
    /// device, so the one just issued is the one certain to work.
    func adopt(token: String, me: Me) {
        let samePerson = app.me?.patient.id == me.patient.id
        // The feeds belong to whoever was here before. The exercise
        // calendar goes first, so no screen draws the last person's day
        // under the new person's name.
        if !samePerson { exercises.reset() }
        app.adoptSession(token: token, me: me)
        if !samePerson {
            app.tasks = TasksResponse(open: [], recent: [])
            app.messages = []
            app.portfolio = []
            app.metrics = nil
            app.wearables = nil
            app.sportsCatalog = nil
            app.pendingTaskId = nil
            app.showConnections = false
            app.selectedTab = .today
        }
        app.lastError = nil
        signInError = nil
        version = DemoVersion(me: me)
        app.enterHome()
    }

    /// Back to "Who do you want to be?" with nobody signed in.
    func startOver() async {
        exercises.reset()
        await app.signOut()
    }

    // MARK: Reset today

    /// How many times this launch put a day back. The exercise screens
    /// watch it and read their feeds again when it changes.
    private(set) var dayResets = 0

    /// Put the signed-in clinic person's day back to its start, so the
    /// walkthrough can be run again: today's exercises reopened, the lines
    /// today's demo added to the thread removed.
    func resetDay() async throws -> DemoResetResponse {
        guard let id = app.me?.patient.id else {
            throw APIError(status: 0, detail: "Nobody is signed in.")
        }
        let answer = try await door.demoResetDay(personaId: id)
        dayResets += 1
        await app.refreshAll()
        return answer
    }

    // MARK: The server

    /// What the server at the address in use says about itself.
    enum ServerState: Equatable {
        case unknown, checking
        /// `GET /api/health` answered: a demo server or not, and the day
        /// its people were last brought up to (when it says).
        case known(demo: Bool, filledOn: String?)
        /// No answer: the address leads nowhere, or not to a MedPull server.
        case unreachable
    }

    private(set) var serverState: ServerState = .unknown

    /// Whether the server is a demo, as far as it has said. The sample clip
    /// in the exercise session is offered only when it is.
    var isDemoServer: Bool {
        if case .known(let demo, _) = serverState { return demo }
        return false
    }

    /// Ask the server whether it is a demo (`GET /api/health`). Asked at
    /// launch, when the address changes, and when the profile sheet opens.
    func checkServer() async {
        if serverState == .unknown || serverState == .unreachable { serverState = .checking }
        let asked = AppConfig.baseURL
        do {
            let health = try await door.serverHealth()
            guard asked == AppConfig.baseURL else { return }
            serverState = .known(demo: health.demo, filledOn: health.filledOn)
        } catch {
            guard asked == AppConfig.baseURL else { return }
            if Self.sentence(for: error, notFound: "") != nil { serverState = .unreachable }
        }
    }

    /// Point the app at another server (nil: the one it was built with).
    /// A session belongs to the server that issued it, so the next read
    /// either works (the same database) or answers 401 and lands on the
    /// picker, which reads the new server's list. Nothing here waits for
    /// the network: an address that leads nowhere must not hold the sheet.
    func useServer(_ url: URL?) {
        if let url {
            AppConfig.baseURL = url
        } else {
            UserDefaults.standard.removeObject(forKey: "api_base_url")
        }
        roster = nil
        rosterState = .idle
        serverState = .unknown
        exercises.reset()
        Task {
            async let server: Void = checkServer()
            if app.phase == .home { await app.refreshAll() }
            await loadRoster()
            await server
        }
    }

    // MARK: Links

    /// A link that could not be opened, for the small sheet that says why.
    struct LinkFailure: Identifiable, Equatable {
        let id = UUID()
        let title: String
        let message: String
    }

    var linkFailure: LinkFailure?
    /// True while a texted link is being redeemed.
    private(set) var openingLink = false

    private var bootstrapped = false
    /// A link that arrived before `bootstrap` finished (a cold start from a
    /// tap in Messages): opened as soon as the app knows who it is.
    private var heldLink: DemoLink?

    /// A URL the system handed over: a universal link, or the app's scheme.
    func handle(url: URL) {
        guard let link = DemoLink(url: url) else { return }
        if bootstrapped {
            Task { await open(link) }
        } else {
            heldLink = link
        }
    }

    func open(_ link: DemoLink) async {
        switch link {
        case .token(let token): await redeem(token)
        case .taskToken(let token): await openTaskLink(token)
        case .task(let id): openTask(id)
        case .exercise(let id): openExercise(id)
        }
    }

    /// Open a task by id, as the real app's `medpull://tasks/<id>` does.
    func openTask(_ id: Int) {
        app.pendingTaskId = id
        app.selectedTab = .today
        Task { await app.refreshTasks() }
    }

    /// Open one assigned exercise on Today. The exercise store holds what
    /// Today has open, so the screen is there however the tabs are being
    /// rebuilt around it (a link may have just changed who the app is).
    func openExercise(_ id: Int) {
        exercises.openOnToday = ExerciseRef(id: id)
        app.selectedTab = .today
    }

    /// Land on the screen a link names. A kind this build does not know, or
    /// a tab this person's version does not have, opens Today.
    func go(to target: AppLinkTarget) {
        let clinic = app.me.map { DemoVersion(me: $0) == .clinic } ?? false
        switch target.kind {
        case "exercise":
            if clinic, let id = target.refNumber { openExercise(id) } else { app.selectedTab = .today }
        case "program":
            if clinic {
                // The day the link is about, when it names one.
                exercises.calendarDay = target.day
                app.selectedTab = .calendar
            } else {
                app.selectedTab = .today
            }
        case "task", "checkin":
            if let id = target.refNumber { openTask(id) } else { app.selectedTab = .today }
        case "thread":
            app.selectedTab = .care
        case "measure":
            app.selectedTab = clinic ? .measure : .today
        case "progress":
            app.selectedTab = .progress
        default:
            app.selectedTab = .today
        }
    }

    /// A link from a demo text: read what it points at, exchange it for a
    /// session, become that person and open the place it names.
    private func redeem(_ token: String) async {
        guard !openingLink else { return }
        openingLink = true
        defer { openingLink = false }
        do {
            let info = try await door.appLink(token: token)
            let session = try await door.appLinkSession(token: token)
            adopt(token: session.sessionToken, me: session.me)
            go(to: session.target ?? info.target)
        } catch {
            guard let sentence = Self.sentence(
                for: error,
                notFound: "This link is no longer valid. It may have expired, or it was made on another server."
            ) else { return }
            linkFailure = LinkFailure(title: "This link didn’t open", message: sentence)
        }
    }

    /// The older `/t/<token>` link: it names a task and carries no session,
    /// so it opens only when that task is the signed-in person's.
    private func openTaskLink(_ token: String) async {
        do {
            let info = try await door.taskLink(token: token)
            guard app.phase == .home else {
                linkFailure = LinkFailure(
                    title: "Pick who you are first",
                    message: "This link opens a task for \(info.firstName ?? "one of the demo’s people"). Choose them, then open the link again."
                )
                return
            }
            await app.refreshTasks(surface: false)
            if (app.tasks.open + app.tasks.recent).contains(where: { $0.id == info.taskId }) {
                openTask(info.taskId)
            } else {
                linkFailure = LinkFailure(
                    title: "This task is someone else’s",
                    message: "It belongs to \(info.firstName ?? "another person on the demo"). Switch to them from the profile sheet, then open the link again."
                )
            }
        } catch {
            guard let sentence = Self.sentence(
                for: error, notFound: "This task link is no longer valid."
            ) else { return }
            linkFailure = LinkFailure(title: "This link didn’t open", message: sentence)
        }
    }

    // MARK: Launch

    /// Restore whoever was signed in last time, then open any link that
    /// started the app.
    func bootstrap() async {
        Task { await checkServer() }
        #if DEBUG
        // Simulator verification: `-MP_DEMO_PERSONA hirt-cole` signs in as
        // that persona through the same route a tap on their row uses.
        if let id = AppConfig.debugFlag("MP_DEMO_PERSONA") {
            do {
                let answer = try await door.demoSession(personaId: id)
                app.adoptSession(token: answer.sessionToken, me: answer.me)
            } catch {
                Keychain.deleteAll()
                signInError = "Couldn’t sign in as “\(id)”. "
                    + (Self.sentence(for: error, notFound: "This server has no demo person with that id.") ?? "")
            }
        }
        #endif
        await app.bootstrap()
        if let me = app.me { version = DemoVersion(me: me) }
        #if DEBUG
        if let raw = AppConfig.debugFlag("MP_DEMO_VERSION"), let chosen = DemoVersion(rawValue: raw) {
            version = chosen
        }
        // `-MP_TAB calendar`: the one tab AppModel's own switch does not know.
        if AppConfig.debugFlag("MP_TAB") == "calendar" { app.selectedTab = .calendar }
        // `-MP_OPEN_LINK <token>` (or a whole link) opens it as a tap would.
        if let raw = AppConfig.debugFlag("MP_OPEN_LINK"), heldLink == nil {
            heldLink = URL(string: raw).flatMap(DemoLink.init(url:)) ?? .token(raw)
        }
        #endif
        bootstrapped = true
        if let link = heldLink {
            heldLink = nil
            await open(link)
        }
    }

    // MARK: Words

    /// What to tell the presenter when a call fails, or nil when the screen
    /// simply went away. A bare 404 ("Not Found") says nothing, so each call
    /// site supplies its own sentence for it; anything else the server said
    /// is shown as it said it.
    static func sentence(for error: Error, notFound: String) -> String? {
        if error is CancellationError { return nil }
        if let e = error as? URLError, e.code == .cancelled { return nil }
        if let e = error as? APIError {
            if e.status == 404, e.detail.caseInsensitiveCompare("Not Found") == .orderedSame { return notFound }
            if e.status == 0 {
                let host = AppConfig.baseURL.host ?? AppConfig.baseURL.absoluteString
                return "Can’t reach \(host). Check the connection, or the server address."
            }
            return e.detail.typeset
        }
        return error.localizedDescription
    }
}
