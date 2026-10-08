import Foundation

// Wire types for /api/mobile. Keys are snake_case on the wire; the decoder
// converts. Timestamps stay strings and are parsed on demand (Dates.parse)
// because the backend writes naive ISO-8601 with microseconds.

struct Hospital: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let system: String?
    let city: String
    let state: String
}

struct Candidate: Codable, Identifiable, Hashable {
    var id: String { patientId }
    let patientId: String
    let displayName: String
    let procedureDisplay: String
    let surgeryMonth: String
    let confidence: String
    let phoneMatch: Bool
    let hasPhoneOnFile: Bool
}

struct EnrollResponse: Codable {
    let status: String
    let verificationId: Int?
    let phoneMasked: String?
    let expiresAt: String?
    let verified: Bool?
    let sessionToken: String?
    let me: Me?
}

struct Me: Codable {
    let patient: PatientProfile
    let recovery: Recovery
    let tasksOpen: Int
    let unreadMessages: Int
    let wearables: WearableSummary
    let features: Features
    /// The spaces this person can move between (a hospital record and its
    /// paired personal space). Absent from an older server.
    let profiles: [SpaceProfile]?
    /// The personal tier's access state; nil on a hospital record.
    let subscription: SubscriptionState?
    /// Whether the beta consent has been accepted at its current version.
    let consent: ConsentStatus?

    var isPersonal: Bool { patient.isPersonal }
    var needsConsent: Bool { consent?.needsConsent ?? false }
    var otherSpace: SpaceProfile? { profiles?.first { !$0.current } }
}

struct PatientProfile: Codable {
    let id: String
    let name: String
    let firstName: String
    let initials: String
    /// "recovery" (had surgery, followed along a curve), "general" (joined
    /// the hospital's programme; no operation) or "personal" (a subscriber's
    /// own space, no hospital).
    let mode: String
    /// "clinic" or "personal". Absent from an older server (clinic).
    let accountKind: String?
    let procedureDisplay: String
    let surgeryDate: String?
    let joinedDate: String
    let postopDay: Int?
    let daysEnrolled: Int
    let carePathway: String?
    let phoneMasked: String?
    /// The login email of a personal space; nil on a hospital record.
    let email: String?
    let hospital: Hospital?
    let careTeam: [CareTeamMember]

    var isRecovery: Bool { mode == "recovery" }
    var isPersonal: Bool { mode == "personal" || accountKind == "personal" }
}

struct Procedure: Codable, Identifiable, Hashable {
    let id: String
    let label: String
}

struct PortfolioPoint: Codable, Hashable, Identifiable {
    var id: String { date }
    /// The server's calendar day, "yyyy-MM-dd". Kept as decoded so existing
    /// callers (`Dates.shortDay(m.latest.date)`) keep compiling.
    let date: String
    let value: Double
    /// `date` parsed ONCE, at decode time, to local midnight of that day, so
    /// charts plot on a real time axis (`.value("Day", day, unit: .day)`)
    /// rather than a categorical String axis. A string the parser does not
    /// know falls back to the distant past rather than failing the decode.
    let day: Date

    /// Compatibility alias for the raw server string.
    var dateString: String { date }

    private enum CodingKeys: String, CodingKey { case date, value }

    init(date: String, value: Double) {
        self.date = date
        self.value = value
        self.day = Dates.parse(date) ?? .distantPast
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.init(date: try c.decode(String.self, forKey: .date),
                  value: try c.decode(Double.self, forKey: .value))
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(date, forKey: .date)
        try c.encode(value, forKey: .value)
    }

    static func == (a: Self, b: Self) -> Bool { a.date == b.date && a.value == b.value }
    func hash(into h: inout Hasher) { h.combine(date); h.combine(value) }
}

struct PortfolioMetric: Codable, Hashable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
    /// The unit to print after a figure. Empty for a duration (sleep),
    /// whose figure already carries its units ("6 hr, 24 min"), so no
    /// caller can print "6 hr, 24 min h". The server's unit is `wireUnit`.
    let unit: String
    /// The unit exactly as the server sent it ("h" for sleep).
    let wireUnit: String
    let latest: PortfolioPoint
    let series: [PortfolioPoint]
    let daysWithData: Int

    private enum CodingKeys: String, CodingKey {
        case key, label, unit, latest, series, daysWithData
    }

    init(key: String, label: String, unit: String, latest: PortfolioPoint,
         series: [PortfolioPoint], daysWithData: Int) {
        self.key = key
        self.label = label
        self.wireUnit = unit
        self.unit = Self.durationKeys.contains(key) ? "" : unit
        self.latest = latest
        self.series = series
        self.daysWithData = daysWithData
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.init(key: try c.decode(String.self, forKey: .key),
                  label: try c.decode(String.self, forKey: .label),
                  unit: try c.decode(String.self, forKey: .unit),
                  latest: try c.decode(PortfolioPoint.self, forKey: .latest),
                  series: try c.decode([PortfolioPoint].self, forKey: .series),
                  daysWithData: try c.decode(Int.self, forKey: .daysWithData))
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(key, forKey: .key)
        try c.encode(label, forKey: .label)
        try c.encode(wireUnit, forKey: .unit)
        try c.encode(latest, forKey: .latest)
        try c.encode(series, forKey: .series)
        try c.encode(daysWithData, forKey: .daysWithData)
    }

    /// Metrics sent in hours and shown as a duration.
    private static let durationKeys: Set<String> = ["sleep_duration"]
    /// Metrics that are whole counts: grouped ("4,820"), never a decimal.
    private static let countKeys: Set<String> = [
        "steps", "active_energy", "exercise_session", "bp_systolic", "bp_diastolic", "blood_glucose",
    ]

    /// True when the figure spells its own units, so no unit label follows it.
    var hideUnit: Bool { Self.durationKeys.contains(key) }

    var latestText: String { text(for: latest.value) }

    /// Any value of this metric in the same form as `latestText` (the Health
    /// scrub readout, the average label and the chart's values use it).
    /// Steps read "4,820"; sleep reads "6 hr, 24 min".
    func text(for value: Double) -> String {
        if Self.durationKeys.contains(key) { return Self.duration(hours: value, width: .abbreviated) }
        if Self.countKeys.contains(key) { return Int(value.rounded()).formatted() }
        return value == value.rounded()
            ? Int(value).formatted()
            : value.formatted(.number.precision(.fractionLength(1)))
    }

    /// The same value for VoiceOver, with units spelled out
    /// ("6 hours, 24 minutes", "4,820 steps").
    func spokenText(for value: Double) -> String {
        if Self.durationKeys.contains(key) { return Self.duration(hours: value, width: .wide) }
        return "\(text(for: value)) \(unit)"
    }

    /// A short axis label: "6 hr" for sleep, the grouped number otherwise.
    func axisText(for value: Double) -> String {
        if Self.durationKeys.contains(key) {
            return Duration.seconds(Int(value.rounded()) * 3600)
                .formatted(.units(allowed: [.hours], width: .abbreviated))
        }
        return value == value.rounded() ? Int(value).formatted() : value.formatted(.number.precision(.fractionLength(1)))
    }

    /// Hours to "6 hr, 24 min", rounded to the minute first so the style
    /// never has to round (and 6.999 h reads "7 hr", not "6 hr, 60 min").
    private static func duration(hours: Double, width: Duration.UnitsFormatStyle.UnitWidth) -> String {
        let minutes = Int((hours * 60).rounded())
        return Duration.seconds(minutes * 60)
            .formatted(.units(allowed: [.hours, .minutes], width: width))
    }

    /// Daily totals chart as bars from zero; sampled measurements as a line
    /// on a domain that does not include zero (resting HR 60-65 must not be
    /// flattened against a 0-75 axis).
    var isDailyTotal: Bool {
        ["steps", "active_energy", "exercise_session"].contains(key)
    }

    /// The series' mean, for the chart's dashed average rule.
    var average: Double? {
        series.isEmpty ? nil : series.map(\.value).reduce(0, +) / Double(series.count)
    }
}

// MARK: - The patient's own metrics (GET /api/mobile/metrics)

/// How far a metric is from its first reading, in the units it counts.
struct MetricReadiness: Codable, Hashable {
    let ready: Bool
    let stage: String          // collecting | provisional | established
    let have: Int
    let need: Int
    let firm: Int
    let left: Int
    let firmLeft: Int
    let unit: String
    let note: String?

    /// "Needs 5 days of steps; you have 3." for the info sheet.
    var sentence: String? {
        let what = note.map { " of \($0)" } ?? ""
        if ready {
            if stage == "provisional", firmLeft > 0 {
                return "Showing from \(have) \(unitWord(have))\(what); settles after \(firm)."
            }
            return nil
        }
        return "Needs \(need) \(unitWord(need))\(what); you have \(have)."
    }

    private func unitWord(_ n: Int) -> String {
        if n == 1, unit.hasSuffix("s") { return String(unit.dropLast()) }
        return unit
    }
}

/// Plain-words explanation of one metric, for the patient.
struct MetricExplain: Codable, Hashable {
    let title: String
    let what: String
    let why: String
    let help: String
}

struct MetricChartPoint: Codable, Hashable {
    let x: Double
    let y: Double
}

struct PatientMetricChart: Codable, Hashable {
    let kind: String   // line | bars
    let points: [MetricChartPoint]
    let xLabel: String?
}

/// One care metric as the patient sees it: a title in their words, a state
/// that never carries a verdict, a sentence, and the countdown until it shows.
struct PatientMetric: Codable, Identifiable, Hashable {
    let id: String
    let key: String?
    let title: String
    let state: String         // good | watch | reviewing | waiting
    let stateLabel: String
    let headline: String
    let value: String?
    let unit: String?
    let readiness: MetricReadiness?
    let daysLeftText: String?
    let explain: MetricExplain?
    let chart: PatientMetricChart?

    var isWaiting: Bool { state == "waiting" }
}

/// One wearable signal as the patient sees it (steps, sleep, heart rate...).
struct PatientSignal: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let title: String
    let state: String
    let stateLabel: String
    let headline: String
    let latest: PortfolioPoint?
    let unit: String?
    let readiness: MetricReadiness?
    let daysLeftText: String?
    let explain: MetricExplain?
    let series: [PortfolioPoint]?
}

struct PatientMetricOverall: Codable {
    let blurb: String?
    let daysUntilFullPicture: Int?
    let showing: Int
    let waiting: Int
}

struct PatientMetricTrajectory: Codable {
    let state: String?
    let pct: Double?
    let readiness: MetricReadiness?
    let daysLeftText: String?
    let explain: MetricExplain?
}

struct PatientMetricsResponse: Codable {
    let postopDay: Int?
    let mode: String
    let overall: PatientMetricOverall
    let trajectory: PatientMetricTrajectory?
    let metrics: [PatientMetric]
    let signals: [PatientSignal]

    func signal(for key: String) -> PatientSignal? { signals.first { $0.key == key } }
}

/// The tone a patient-facing state takes. `reviewing` is sage, not clay:
/// "your care team is taking a look" is reassurance, never an alarm.
extension MP {
    static func tone(forMetricState state: String) -> Tone {
        switch state {
        case "good": return .low
        case "watch": return .med
        case "reviewing": return .brand
        default: return .missing
        }
    }
}

struct PortfolioResponse: Codable {
    let days: Int
    let since: String
    let metrics: [PortfolioMetric]
}

struct CareTeamMember: Codable, Hashable {
    let name: String
    let role: String
}

struct Recovery: Codable {
    let level: String
    let label: String
    let blurb: String
    let trajectory: Trajectory
    let daysWithData: Int?
    /// Days of data until every metric has shown; nil when nothing is
    /// waiting (or the server predates the field).
    let daysUntilFullPicture: Int?
    let computedAt: String?
}

struct Trajectory: Codable {
    let state: String
    let pct: Double?
}

struct WearableSummary: Codable {
    let aggregatorConfigured: Bool
    let connectionStatus: String?
    let appleHealth: AppleHealthStatus
    let devices: [WearableDevice]
    let lastDataAt: String?
}

struct AppleHealthStatus: Codable {
    let connected: Bool
    let lastSyncAt: String?
}

struct WearableDevice: Codable, Identifiable, Hashable {
    var id: String { provider + model }
    let provider: String
    let model: String
    let status: String
    let lastSyncAt: String?
}

struct Features: Codable {
    let sms: Bool
    let appleHealth: Bool
    let deepLinkScheme: String
    /// The whole app is a beta while this is true; onboarding and Profile say so.
    let beta: Bool?
    let consentVersion: String?

    var isBeta: Bool { beta ?? true }
}

/// The beta consent on file for this account, as `/me` reports it.
struct ConsentStatus: Codable, Hashable {
    let version: String?
    let acceptedAt: String?
    let scopes: [String: Bool]?
    let currentVersion: String
    let needsConsent: Bool
}

struct Question: Codable, Identifiable, Hashable {
    let id: String
    let prompt: String
    let kind: String  // scale | yes_no | choice | text | number
    let options: [String]?
    let min: Int?
    let max: Int?
}

struct RecoveryTask: Codable, Identifiable, Hashable {
    let id: Int
    let kind: String
    let kindLabel: String
    let title: String
    let why: String
    let status: String
    let createdAt: String?
    let dueAt: String?
    let sentAt: String?
    let completedAt: String?
    let completedVia: String?
    let questions: [Question]
    let inSmsConversation: Bool
    /// A care-plan task the patient does again tomorrow (daily, weekly,
    /// ongoing) rather than a one-off. The server reports `status` as the
    /// patient's state for today, so a recurring task that was answered
    /// yesterday arrives as "pending" again.
    let recurring: Bool?
    let schedule: String?
    let lastDoneOn: String?

    var isOpen: Bool { status == "pending" || status == "sent" }

    /// "Daily", "Twice a day"… shown beside the kind. Nil for a one-off.
    var scheduleLabel: String? {
        guard recurring == true else { return nil }
        switch schedule {
        case "daily": return "Daily"
        case "am_pm": return "Twice a day"
        case "weekly": return "Weekly"
        case "ongoing": return "Ongoing"
        default: return nil
        }
    }
}

struct TasksResponse: Codable, Equatable {
    let open: [RecoveryTask]
    let recent: [RecoveryTask]
}

struct CompleteResponse: Codable {
    let ok: Bool
    let task: RecoveryTask
}

/// A button the server asks the app to draw under one message.
///
/// A text message cannot carry a button — no carrier renders one — so the
/// affordance travels as data on the row instead. The care team texts "your
/// check-in is ready"; in the app that same line grows one tap straight into
/// the check-in. Nil on a line that is only words, which is nearly all of them.
struct MessageAction: Codable, Hashable {
    /// Only "open_task" so far. Unknown kinds are ignored rather than drawn,
    /// so a newer server cannot make an older app render a dead button.
    let kind: String
    let taskId: Int?
    let label: String

    var opensTask: Int? { kind == "open_task" ? taskId : nil }
}

/// A photo or file on a thread line.
///
/// No URL here. A link to the bytes is minted per request and lives
/// minutes, because a link that outlives its request outlives the check
/// that authorised it — so one is asked for when the file is about to be
/// shown, not when the thread is decoded.
struct ChatAttachment: Codable, Identifiable, Hashable {
    let id: Int
    let contentType: String
    let byteSize: Int
    /// What the sender called it. Nil for a photo, which needs no name.
    let filename: String?
    let kind: String            // image | video | audio | file
    /// Content hash: the bytes are the same wherever the link points, so
    /// this is what an image cache keys on.
    let sha256: String?
    let uploadedBy: String      // patient | care_team | copilot
    let source: String          // app | console | sms
    let createdAt: String?
    /// Taken back by whoever sent it. The bytes are gone; the line stays,
    /// so a reply to it does not end up referring to nothing.
    let withdrawn: Bool?

    var isImage: Bool { kind == "image" }
    var isVideo: Bool { kind == "video" }
    var isAudio: Bool { kind == "audio" }
    var isWithdrawn: Bool { withdrawn == true }

    /// The glyph for a composer chip or a strip placeholder.
    var symbol: String {
        switch kind {
        case "image": return "photo"
        case "video": return "video"
        case "audio": return "waveform"
        default: return "doc"
        }
    }

    /// "photo", "video", "recording" or "file", for a sentence.
    var noun: String {
        switch kind {
        case "image": return "photo"
        case "video": return "video"
        case "audio": return "recording"
        default: return "file"
        }
    }

    var sizeLabel: String {
        if byteSize >= 1_048_576 {
            return String(format: "%.1f MB", Double(byteSize) / 1_048_576)
        }
        if byteSize >= 1024 { return "\(byteSize / 1024) KB" }
        return "\(byteSize) B"
    }

    var displayName: String {
        if let filename { return filename }
        return isAudio ? "Voice note" : noun.prefix(1).uppercased() + noun.dropFirst()
    }
}

struct ChatMessage: Codable, Identifiable, Hashable {
    let id: Int
    let sender: String   // patient | care_team | copilot
    /// Who stands behind the message: "care_team" when a clinician wrote,
    /// approved or triggered it, "ai" when the app answered for itself.
    /// Older rows omit it, and untagged is the right default for those.
    let authoredBy: String?
    /// The clinician's name, when one is behind it. Nil for the copilot.
    let authorName: String?
    let channel: String
    let text: String
    let createdAt: String?
    let deliveryStatus: String?
    /// The button this line offers, when it offers one. Absent from an older
    /// server's response, which decodes to nil and simply draws no button.
    let action: MessageAction?
    /// Photos and files on this line. Absent from an older server's
    /// response, and empty on most lines.
    let attachments: [ChatAttachment]?
    let read: Bool

    var fromClinician: Bool { authoredBy == "care_team" }
    var files: [ChatAttachment] { attachments ?? [] }
}

struct MessagesResponse: Codable { let messages: [ChatMessage] }
struct SentMessageResponse: Codable { let ok: Bool; let message: ChatMessage }

struct AgentResponse: Codable {
    let reply: String
    let flagged: Bool
    let provider: String
    let tasksOpen: Int
}

struct AppleSession: Codable {
    let signInToken: String
    let userId: String
    let environment: String
    let region: String
}

struct LinkResponse: Codable {
    let linkUrl: String
    let expiresAt: String?
}

struct WearablesResponse: Codable {
    let summary: WearableSummary
    let refreshError: String?
}

struct ProgressDay: Codable, Identifiable, Hashable {
    var id: String { date }
    let date: String
    let postopDay: Int
    let steps: Int?
    let sleepHours: Double?
}

struct ProgressResponse: Codable { let days: [ProgressDay] }

struct GaitPoint: Encodable {
    let metricType: String
    let date: String
    let value: Double
}

struct GaitUpload: Encodable {
    let points: [GaitPoint]
    let deviceModel: String?
}

struct GaitUploadResponse: Codable {
    let ingested: Int
    let updated: Int
    let duplicates: Int
    let skippedOutOfWindow: Int
    let droppedImplausible: Int
    let rejected: Int
}

struct OKResponse: Codable { let ok: Bool }

// MARK: - MedPull's own measurements (backend app/api/mobility)

/// One recorded walk, as the server's mobility engine wants it: device-frame
/// samples in SI units, timestamps as seconds from the start.
struct MotionWindowUpload: Encodable {
    let startedAt: String          // ISO 8601 with offset (Dates.iso)
    let sampleRateHz: Double
    let accel: [[Double]]
    let gyro: [[Double]]?
    let gravity: [[Double]]?
    let timestamps: [Double]?
    let altitude: [[Double]]?
    let gpsDistanceM: Double?
    let gpsAccuracyM: Double?
    let pedometerSteps: Int?
    let pedometerDistanceM: Double?
    let pocketSide: String?
    let context: String
}

struct MotionUpload: Encodable {
    let windows: [MotionWindowUpload]
    let heightCm: Double?
    let deviceModel: String?
}

/// What the engine found in one window; the app shows it straight back.
struct MotionWindowSummary: Decodable {
    let durationS: Double
    let walkingS: Double
    let bouts: Int
    let steps: Int
    let cadenceSpm: Double?
    let walkingSpeedMps: Double?
    let stepLengthM: Double?
    let asymmetryPct: Double?
    let doubleSupportPct: Double?
    let steadiness: Double?
    let notes: [String]
}

struct MotionUploadResponse: Decodable {
    let windows: [MotionWindowSummary]
    let ingested: Int
    let updated: Int
    let duplicates: Int
}

struct SixMinuteWalkUpload: Encodable {
    let startedAt: String
    let durationS: Double
    let steps: Int?
    let pedometerDistanceM: Double?
    let gpsDistanceM: Double?
    let gpsAccuracyM: Double?
    let minuteSteps: [Int]?
    let heightCm: Double?
    let deviceModel: String?
    let motion: MotionWindowUpload?
}

struct SixMinuteWalkResponse: Decodable {
    let distanceM: Double
    let method: String
    let steps: Int?
    let cadenceSpm: Double?
    let fadePct: Double?
    let motion: MotionWindowSummary?
}

struct RangeOfMotionUpload: Encodable {
    let recordedAt: String
    let protocolName: String
    let side: String
    let reference: [[Double]]
    let movement: [[Double]]
    let deviceModel: String?

    enum CodingKeys: String, CodingKey {
        case recordedAt, side, reference, movement, deviceModel
        case protocolName = "protocol"
    }
}

struct RangeOfMotionResponse: Decodable {
    let joint: String
    let movement: String
    let side: String
    let angleDeg: Double
    let steady: Bool
}

enum Dates {
    private static let withFraction: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        return f
    }()
    private static let plain: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f
    }()
    private static let day: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    static func parse(_ raw: String?) -> Date? {
        guard let raw else { return nil }
        return withFraction.date(from: raw) ?? plain.date(from: raw) ?? day.date(from: raw)
    }

    static func dayString(_ date: Date) -> String { day.string(from: date) }
    /// ISO 8601 with the local offset, for the measurement uploads.
    static func iso(_ date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        f.timeZone = .current
        return f.string(from: date)
    }

    static func relative(_ raw: String?) -> String {
        guard let date = parse(raw) else { return "" }
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .short
        return f.localizedString(for: date, relativeTo: Date())
    }

    static func shortDay(_ raw: String) -> String {
        guard let d = parse(raw) else { return raw }
        let f = DateFormatter()
        f.dateFormat = "EEE"
        return f.string(from: d)
    }
}
