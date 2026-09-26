import Foundation

// Wire types for the personal tier (/api/mobile/personal, /api/mobile/profiles).
// Keys are snake_case on the wire; the decoder converts.

/// One of the spaces a person can be in: their own, or a hospital record.
struct SpaceProfile: Codable, Identifiable, Hashable {
    var id: String { patientId }
    let patientId: String
    let kind: String      // personal | clinic
    let label: String
    let detail: String
    let current: Bool

    var isPersonal: Bool { kind == "personal" }
}

/// Access to the personal tier, as the paywall and Profile show it.
struct SubscriptionState: Codable, Hashable {
    let state: String          // trial | active | grace | expired | none
    let source: String?        // trial | apple | comp
    let productId: String?
    let expiresAt: String?
    let daysLeft: Int?
    let verified: Bool
    let autoRenew: Bool
    let entitled: Bool
    let trialUsed: Bool
    let products: [String]

    var isTrial: Bool { state == "trial" }
    var headline: String {
        switch state {
        case "trial":
            if let d = daysLeft { return d == 0 ? "Trial ends today" : "Trial: \(d) day\(d == 1 ? "" : "s") left" }
            return "Free trial"
        case "active": return "Subscribed"
        case "grace": return "Payment pending"
        case "expired": return "Subscription ended"
        default: return "Not subscribed"
        }
    }
}

struct PersonalProfile: Codable, Hashable {
    let goal: String
    let goalLabel: String
    let sport: String?
    let weeklyTargetMinutes: Int?
    let sleepTargetHours: Double?
    let injury: String?
    let anchorDate: String?
    let units: String
    let smsBriefs: Bool
    let briefHour: Int
    let createdAt: String?
}

struct PersonalProfileResponse: Codable {
    let profile: PersonalProfile
    let subscription: SubscriptionState?
    let profiles: [SpaceProfile]?
}

struct ProfilesResponse: Codable {
    let profiles: [SpaceProfile]
    let current: String
}

struct SwitchResponse: Codable {
    let sessionToken: String
    let me: Me
}

struct AddSpaceResponse: Codable {
    let sessionToken: String
    let me: Me
    let profiles: [SpaceProfile]
}

struct LinkHospitalResponse: Codable {
    let status: String
    let verificationId: Int?
    let phoneMasked: String?
    let sessionToken: String?
    let me: Me?
    let profiles: [SpaceProfile]?
}

// MARK: - The readouts

struct PanelPoint: Codable, Hashable, Identifiable {
    var id: String { date }
    let date: String
    let value: Double
    var day: Date { Dates.parse(date) ?? .distantPast }
}

struct PanelStat: Codable, Hashable, Identifiable {
    var id: String { label }
    let label: String
    let value: String
    let unit: String
}

/// One readout: readiness, HRV, sleep, load... The server computes the
/// numbers and the words; the app draws them.
struct Panel: Codable, Hashable {
    let key: String
    let title: String
    let status: String        // ok | watch | flag | nodata
    let statusText: String
    let headline: String
    let unit: String
    let sub: String
    let finding: String
    let method: String
    let confidence: String    // high | med | low
    let coverage: String
    let series: [PanelPoint]
    let stats: [PanelStat]
    let extra: JSONValue?

    var hasData: Bool { status != "nodata" }

    var tone: MP.Tone {
        switch status {
        case "ok": return .low
        case "watch": return .med
        case "flag": return .high
        default: return .missing
        }
    }

    /// A numeric field of `extra`, or nil.
    func number(_ key: String) -> Double? { extra?[key]?.number }
    func string(_ key: String) -> String? { extra?[key]?.string }
    func array(_ key: String) -> [JSONValue] { extra?[key]?.array ?? [] }
}

struct Verdict: Codable, Hashable {
    let kind: String          // push | steady | easy | rest | unknown
    let title: String
    let reason: String
    let detail: String
}

struct Dashboard: Codable, Hashable {
    let asOf: String
    let goal: String
    let daysWithData: Int
    let verdict: Verdict
    let sections: [String]
    let panels: [String: Panel]
    /// Thirteen weekly means per key metric; absent from an older server.
    let trends: [String: Trend]?
    /// This week against last; absent from an older server.
    let week: WeekReview?

    func panel(_ key: String) -> Panel? { panels[key] }
    /// Panels in the goal's order, skipping the care section (drawn apart).
    var ordered: [Panel] { sections.compactMap { panels[$0] } }
}

struct Brief: Codable, Hashable {
    /// The one line: verdict and readiness. Absent from an older server.
    let headline: String?
    let brief: String
    let guardrail: String?
    let provider: String?
    let generatedAt: String?
}

struct DeepDive: Codable, Hashable, Identifiable {
    var id: String { domain }
    let domain: String
    let title: String
    let body: String
    let guardrail: String?
    let provider: String?
}

/// One of the clinic engine's care metrics (M1–M18), for the recovery goal.
struct CareMetricView: Codable, Hashable, Identifiable {
    let id: String
    let key: String
    let name: String
    let family: String
    let status: String
    let statusText: String
    let value: String?
    let unit: String
    let valueLabel: String
    let finding: String
    let method: String
    let confidence: String
    let coverageText: String
    let unlock: String?

    var tone: MP.Tone {
        switch status {
        case "ok": return .low
        case "watch": return .med
        case "flag": return .high
        default: return .missing
        }
    }
}

struct CareSection: Codable, Hashable {
    let pathway: String?
    let headline: [String]
    let metrics: [CareMetricView]
    let postopDay: Int?
}

struct TrendWeek: Codable, Hashable, Identifiable {
    var id: String { week }
    let week: String
    let value: Double?
    let days: Int
    var start: Date { Dates.parse(week) ?? .distantPast }
}

struct Trend: Codable, Hashable {
    let label: String
    let unit: String
    let weeks: [TrendWeek]
    let changePct: Double?
    let weeksWithData: Int
}

struct WeekMetric: Codable, Hashable {
    let unit: String
    let this: Double?
    let last: Double?
    let deltaPct: Double?
}

struct WeekDay: Codable, Hashable {
    let date: String
    let value: Double
}

struct WeekReadinessDays: Codable, Hashable {
    let best: WeekDay
    let worst: WeekDay
}

struct WeekStreaks: Codable, Hashable {
    let checkinDays: Int
    let sleepOnNeedDays: Int
}

struct WeekReview: Codable, Hashable {
    let start: String
    let end: String
    let metrics: [String: WeekMetric]
    let readinessDays: WeekReadinessDays?
    let sessions: Int
    let sessionMinutes: Double?
    let streaks: WeekStreaks
    let highlights: [String]
}

struct WeekResponse: Codable {
    let week: WeekReview?
    let trends: [String: Trend]?
    let review: DeepDive
}

/// The beta consent form, as the server publishes it.
struct ConsentScope: Codable, Hashable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
    let detail: String
    let required: Bool
}

struct ConsentDocument: Codable, Hashable {
    let kind: String
    let version: String
    let text: String
    let textSha256: String
    let scopes: [ConsentScope]
    let beta: Bool
}

/// What the app sends back: the version read, the scopes ticked, the name typed.
struct ConsentAcceptance: Codable, Hashable {
    let version: String
    let scopes: [String: Bool]
    let signature: String?
}

struct ForgotResponse: Codable {
    let sent: Bool
    let phoneMasked: String?
    let verificationId: Int?
    let detail: String?
}

struct DashboardResponse: Codable {
    let dashboard: Dashboard
    let brief: Brief
    let care: CareSection?
    let profile: PersonalProfile
    let subscription: SubscriptionState
    let profiles: [SpaceProfile]
}

struct StartDayResponse: Codable {
    let dashboard: Dashboard
    let brief: Brief
    let care: CareSection?
    let profile: PersonalProfile
    let subscription: SubscriptionState
    let profiles: [SpaceProfile]
}

struct AppleTransactionResponse: Codable {
    let ok: Bool
    let subscription: SubscriptionState
}

struct ExportResponse: Codable {
    let url: String?
    let bytes: Int
}

/// A loosely typed JSON value, for a panel's `extra` bag: the server adds
/// fields per panel and the app reads the few it draws.
indirect enum JSONValue: Codable, Hashable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case null
    case array([JSONValue])
    case object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null; return }
        if let b = try? c.decode(Bool.self) { self = .bool(b); return }
        if let n = try? c.decode(Double.self) { self = .number(n); return }
        if let s = try? c.decode(String.self) { self = .string(s); return }
        if let a = try? c.decode([JSONValue].self) { self = .array(a); return }
        if let o = try? c.decode([String: JSONValue].self) { self = .object(o); return }
        throw DecodingError.dataCorruptedError(in: c, debugDescription: "Unknown JSON")
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .number(let n): try c.encode(n)
        case .bool(let b): try c.encode(b)
        case .null: try c.encodeNil()
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        }
    }

    subscript(key: String) -> JSONValue? {
        if case .object(let o) = self { return o[key] }
        return nil
    }

    var number: Double? {
        if case .number(let n) = self { return n }
        return nil
    }
    var string: String? {
        if case .string(let s) = self { return s }
        return nil
    }
    var bool: Bool? {
        if case .bool(let b) = self { return b }
        return nil
    }
    var array: [JSONValue]? {
        if case .array(let a) = self { return a }
        return nil
    }
}
