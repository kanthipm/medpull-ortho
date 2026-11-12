import Foundation

// Wire types and calls for the routes only the demo app uses: the persona
// list and the session for one of them, the day reset, the presenter's
// phone, and the links a text carries (docs/dev/showcase.md). Keys are
// snake_case on the wire; APIClient's decoder converts.
//
// Every type here decodes by hand and asks only for what the app cannot do
// without (an id, a name, a token). The routes are written by other streams
// and will grow: an extra key is ignored, a missing optional key gets its
// default, and one field of an unexpected type does not sink the answer.

// MARK: - Versions

/// The three versions of the product the demo shows.
enum DemoVersion: String, CaseIterable, Identifiable, Hashable {
    case clinic, personal, sports

    var id: String { rawValue }

    var label: String {
        switch self {
        case .clinic: return "Clinic"
        case .personal: return "Personal"
        case .sports: return "Sports"
        }
    }

    /// The line under the label until the server's own blurb has loaded.
    var blurb: String {
        switch self {
        case .clinic: return "Followed by a clinic between visits"
        case .personal: return "Reading your own body, on your own"
        case .sports: return "An athlete with a team’s staff"
        }
    }

    var symbol: String {
        switch self {
        case .clinic: return "building.2.fill"
        case .personal: return "sparkles"
        case .sports: return "figure.basketball"
        }
    }

    var family: MP.Category {
        switch self {
        case .clinic: return .blue
        case .personal: return .teal
        case .sports: return .indigo
        }
    }

    /// The version a signed-in person belongs to, from `/api/mobile/me`.
    init(me: Me) {
        self = me.isSports ? .sports : me.isPersonal ? .personal : .clinic
    }
}

// MARK: - Personas

/// `GET /api/demo/personas`.
struct DemoRoster: Decodable {
    let asOf: String?
    let sms: DemoSMS?
    let versions: [DemoVersionGroup]

    private enum CodingKeys: String, CodingKey { case asOf, sms, versions }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        asOf = c.lenient(String.self, .asOf)
        sms = c.lenient(DemoSMS.self, .sms)
        versions = c.lenientList(DemoVersionGroup.self, .versions)
    }

    func group(_ version: DemoVersion) -> DemoVersionGroup? {
        versions.first { $0.key == version.rawValue }
    }

    /// The organisation a person belongs to, wherever they are listed.
    func org(ofPersona id: String) -> DemoOrg? {
        versions.flatMap(\.orgs).first { $0.personas.contains { $0.id == id } }
    }

    func persona(_ id: String) -> DemoPersona? {
        versions.flatMap(\.orgs).flatMap(\.personas).first { $0.id == id }
    }
}

/// The demo's text line: the number a presenter texts first.
struct DemoSMS: Decodable, Equatable {
    let number: String?
    let textBody: String?
    let configured: Bool

    private enum CodingKeys: String, CodingKey { case number, textBody, configured }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        number = c.lenient(String.self, .number)
        textBody = c.lenient(String.self, .textBody)
        configured = c.lenient(Bool.self, .configured) ?? false
    }
}

struct DemoVersionGroup: Decodable, Identifiable {
    let key: String
    let label: String?
    let blurb: String?
    let orgs: [DemoOrg]

    var id: String { key }
    var personaCount: Int { orgs.reduce(0) { $0 + $1.personas.count } }

    private enum CodingKeys: String, CodingKey { case key, label, blurb, orgs }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        key = try c.decode(String.self, forKey: .key)
        label = c.lenient(String.self, .label)
        blurb = c.lenient(String.self, .blurb)
        orgs = c.lenientList(DemoOrg.self, .orgs)
    }
}

struct DemoOrg: Decodable, Identifiable, Hashable {
    let id: String
    let name: String
    let personas: [DemoPersona]

    private enum CodingKeys: String, CodingKey { case id, name, personas }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        name = c.lenient(String.self, .name) ?? id
        personas = c.lenientList(DemoPersona.self, .personas)
    }

    /// The one to open first leads; the rest keep the server's order.
    var ordered: [DemoPersona] { personas.filter(\.hero) + personas.filter { !$0.hero } }
}

struct DemoPersona: Decodable, Identifiable, Hashable {
    struct Has: Decodable, Hashable {
        let wearable: Bool
        let exercises: Bool
        let thread: Bool

        private enum CodingKeys: String, CodingKey { case wearable, exercises, thread }

        init(wearable: Bool = false, exercises: Bool = false, thread: Bool = false) {
            self.wearable = wearable
            self.exercises = exercises
            self.thread = thread
        }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            wearable = c.lenient(Bool.self, .wearable) ?? false
            exercises = c.lenient(Bool.self, .exercises) ?? false
            thread = c.lenient(Bool.self, .thread) ?? false
        }
    }

    let id: String
    let name: String
    /// The one to open first in its organisation.
    let hero: Bool
    /// One line under the name: the program, the goal, the position.
    let tagline: String
    /// What today's story is ("Load spike, pain rising").
    let detail: String
    let accountKind: String?
    /// The clinic's priority tier (high | medium | low), or another
    /// version's own state word. Shown as a chip.
    let tier: String?
    let has: Has

    private enum CodingKeys: String, CodingKey {
        case id, name, hero, tagline, detail, accountKind, tier, has
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        hero = c.lenient(Bool.self, .hero) ?? false
        tagline = c.lenient(String.self, .tagline) ?? ""
        detail = c.lenient(String.self, .detail) ?? ""
        accountKind = c.lenient(String.self, .accountKind)
        tier = c.lenient(String.self, .tier)
        has = c.lenient(Has.self, .has) ?? Has()
    }

    /// "Cole Whitaker" -> "CW".
    var initials: String {
        let words = name.split(separator: " ").filter { !$0.hasSuffix(".") }
        let letters = [words.first, words.count > 1 ? words.last : nil].compactMap { $0?.first }
        return String(letters).uppercased()
    }

    /// The chip: the tier as a word and its tone, or nil when there is none.
    /// A clinic's tier is its priority; an athlete's may be an availability
    /// (the words the sports screens use). Any other word is shown as it
    /// is, in the tone that claims nothing about good or bad.
    var chip: (text: String, tone: MP.Tone)? {
        guard let tier, !tier.isEmpty else { return nil }
        switch tier.lowercased() {
        case "high": return ("High priority", .high)
        case "medium", "med", "moderate": return ("Medium priority", .med)
        case "low": return ("Low priority", .low)
        case "available": return ("Available", .low)
        case "modified": return ("Modified", .med)
        case "out": return ("Out", .high)
        default:
            let word = tier.replacingOccurrences(of: "_", with: " ")
            return (word.prefix(1).uppercased() + word.dropFirst(), .missing)
        }
    }
}

extension String {
    /// A server string set for the screen: apostrophes curled, and a middle
    /// dot between two facts given the thin spaces Outfit needs around it
    /// ("Rice · Men's Basketball", "3 sets × 10 reps · 10 kg").
    var demoTypeset: String {
        replacingOccurrences(of: " · ", with: MP.dot).typeset
    }
}

/// `POST /api/demo/session`.
struct DemoSessionResponse: Decodable {
    struct PersonaRef: Decodable {
        let id: String
        let name: String?
        let version: String?

        private enum CodingKeys: String, CodingKey { case id, name, version }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = try c.decode(String.self, forKey: .id)
            name = c.lenient(String.self, .name)
            version = c.lenient(String.self, .version)
        }
    }

    let sessionToken: String
    let me: Me
    let persona: PersonaRef?

    private enum CodingKeys: String, CodingKey { case sessionToken, me, persona }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        sessionToken = try c.decode(String.self, forKey: .sessionToken)
        me = try c.decode(Me.self, forKey: .me)
        persona = c.lenient(PersonaRef.self, .persona)
    }
}

/// `POST /api/demo/reset-day`.
struct DemoResetResponse: Decodable, Equatable {
    /// Today's exercise rows put back to "assigned".
    let reopened: Int
    /// The thread lines today's demo added, taken out again.
    let removed: Int

    private enum CodingKeys: String, CodingKey { case reopened, removed }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        reopened = c.lenient(Int.self, .reopened) ?? 0
        removed = c.lenient(Int.self, .removed) ?? 0
    }

    /// "3 exercises reopened and 2 thread lines removed."
    var sentence: String {
        if reopened == 0 && removed == 0 { return "Today was already at its start: nothing to put back." }
        let exercises = "\(reopened) exercise\(reopened == 1 ? "" : "s") reopened"
        let lines = "\(removed) thread line\(removed == 1 ? "" : "s") removed"
        return "\(exercises) and \(lines)."
    }
}

// MARK: - The presenter's phone

/// `GET | POST | DELETE /api/demo/phone`: the real number bound to the
/// signed-in persona, and whether the demo's texts can reach it yet.
struct DemoPhoneState: Decodable, Equatable {
    let phone: String?
    /// False until this number has texted the line once (Sendblue's free
    /// plan cannot start a conversation).
    let reachable: Bool
    let textTo: String?
    let textBody: String?
    /// Whether the welcome text went out.
    let sent: Bool
    let detail: String?

    private enum CodingKeys: String, CodingKey { case phone, reachable, textTo, textBody, sent, detail }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        phone = c.lenient(String.self, .phone)
        reachable = c.lenient(Bool.self, .reachable) ?? false
        textTo = c.lenient(String.self, .textTo)
        textBody = c.lenient(String.self, .textBody)
        sent = c.lenient(Bool.self, .sent) ?? false
        detail = c.lenient(String.self, .detail)
    }

    var isBound: Bool { !(phone ?? "").isEmpty }
}

// MARK: - Links

/// Where a link lands. `refId` is the assignment id for `exercise` and the
/// task id for `task` / `checkin`; the rest carry none.
struct AppLinkTarget: Codable, Hashable {
    let kind: String
    let refId: String?
    let day: String?

    private enum CodingKeys: String, CodingKey { case kind, refId, day }

    init(kind: String, refId: String? = nil, day: String? = nil) {
        self.kind = kind
        self.refId = refId
        self.day = day
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        kind = c.lenient(String.self, .kind) ?? "today"
        refId = c.lenientIdentifier(.refId)
        day = c.lenient(String.self, .day)
    }

    var refNumber: Int? { refId.flatMap { Int($0) } }
}

/// `GET /api/links/{token}`: what the link points at. Reading it has no
/// side effects.
struct AppLinkInfo: Decodable {
    let target: AppLinkTarget
    let expiresAt: String?
    /// Whether redeeming the link may start a session (the demo stack).
    let signin: Bool
    let patientFirstName: String?
    let clinicName: String?

    private enum CodingKeys: String, CodingKey { case expiresAt, signin, patient, clinic }
    private enum PatientKeys: String, CodingKey { case firstName }
    private enum ClinicKeys: String, CodingKey { case name }

    init(from decoder: Decoder) throws {
        target = try AppLinkTarget(from: decoder)
        let c = try decoder.container(keyedBy: CodingKeys.self)
        expiresAt = c.lenient(String.self, .expiresAt)
        signin = c.lenient(Bool.self, .signin) ?? false
        patientFirstName = (try? c.nestedContainer(keyedBy: PatientKeys.self, forKey: .patient))?
            .lenient(String.self, .firstName)
        clinicName = (try? c.nestedContainer(keyedBy: ClinicKeys.self, forKey: .clinic))?
            .lenient(String.self, .name)
    }
}

/// `POST /api/links/{token}/session`.
struct AppLinkSession: Decodable {
    let sessionToken: String
    let me: Me
    /// Absent from an answer that only signs in; the link's own target
    /// (from the GET) is used then.
    let target: AppLinkTarget?

    private enum CodingKeys: String, CodingKey { case sessionToken, me, target }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        sessionToken = try c.decode(String.self, forKey: .sessionToken)
        me = try c.decode(Me.self, forKey: .me)
        target = c.lenient(AppLinkTarget.self, .target)
    }
}

/// `GET /api/tasks/{token}`: the task a `/t/<token>` text points at. That
/// older link names a task and signs nobody in.
struct TaskLinkInfo: Decodable {
    let firstName: String?
    let taskId: Int

    private enum CodingKeys: String, CodingKey { case firstName, task }
    private enum TaskKeys: String, CodingKey { case id }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        firstName = c.lenient(String.self, .firstName)
        taskId = try c.nestedContainer(keyedBy: TaskKeys.self, forKey: .task).decode(Int.self, forKey: .id)
    }
}

// MARK: - Lenient decoding

private struct Lossy<T: Decodable>: Decodable {
    let value: T?
    init(from decoder: Decoder) throws { value = try? T(from: decoder) }
}

extension KeyedDecodingContainer {
    /// The value for `key`, or nil when it is absent, null or of another
    /// type. For optional fields of routes that are still being written.
    func lenient<T: Decodable>(_ type: T.Type, _ key: Key) -> T? {
        (try? decodeIfPresent(type, forKey: key)) ?? nil
    }

    /// A list that keeps every element it can read: one malformed person
    /// does not empty an organisation.
    func lenientList<T: Decodable>(_ type: T.Type, _ key: Key) -> [T] {
        (lenient([Lossy<T>].self, key) ?? []).compactMap(\.value)
    }

    /// An id that may arrive as a string or a number ("42" or 42).
    func lenientIdentifier(_ key: Key) -> String? {
        if let s = lenient(String.self, key) { return s.isEmpty ? nil : s }
        if let n = lenient(Int.self, key) { return String(n) }
        return nil
    }
}

// MARK: - Calls

extension APIClient {
    private struct DemoSessionBody: Encodable { let personaId: String; let deviceName: String }
    private struct DemoResetBody: Encodable { let personaId: String }
    private struct DemoPhoneBody: Encodable { let phone: String }
    private struct LinkSessionBody: Encodable { let deviceName: String }

    // The first three and the link calls are made on a client with no
    // token (DemoShell.door): they are the demo's front door, and the server
    // refuses nothing for the lack of a credential there.

    func demoPersonas() async throws -> DemoRoster { try await get("/api/demo/personas") }

    func demoSession(personaId: String) async throws -> DemoSessionResponse {
        try await post("/api/demo/session",
                       body: DemoSessionBody(personaId: personaId, deviceName: UIDeviceName.current))
    }

    func demoResetDay(personaId: String) async throws -> DemoResetResponse {
        try await post("/api/demo/reset-day", body: DemoResetBody(personaId: personaId))
    }

    func appLink(token: String) async throws -> AppLinkInfo { try await get("/api/links/\(token)") }

    func appLinkSession(token: String) async throws -> AppLinkSession {
        try await post("/api/links/\(token)/session", body: LinkSessionBody(deviceName: UIDeviceName.current))
    }

    func taskLink(token: String) async throws -> TaskLinkInfo { try await get("/api/tasks/\(token)") }

    // The phone routes are authorised by the persona's own app session, so
    // they go out on the signed-in client (AppModel.api).

    func demoPhone() async throws -> DemoPhoneState { try await get("/api/demo/phone") }

    func demoBindPhone(_ phone: String) async throws -> DemoPhoneState {
        try await post("/api/demo/phone", body: DemoPhoneBody(phone: phone))
    }

    func demoUnbindPhone() async throws -> DemoPhoneState { try await delete("/api/demo/phone") }
}
