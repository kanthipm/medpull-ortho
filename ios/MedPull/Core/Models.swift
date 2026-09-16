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
}

struct PatientProfile: Codable {
    let id: String
    let name: String
    let firstName: String
    let initials: String
    /// "recovery" (had surgery, followed along a curve) or "general" (joined
    /// the hospital's programme; no operation).
    let mode: String
    let procedureDisplay: String
    let surgeryDate: String?
    let joinedDate: String
    let postopDay: Int?
    let daysEnrolled: Int
    let carePathway: String?
    let phoneMasked: String?
    let hospital: Hospital?
    let careTeam: [CareTeamMember]

    var isRecovery: Bool { mode == "recovery" }
}

struct Procedure: Codable, Identifiable, Hashable {
    let id: String
    let label: String
}

struct PortfolioPoint: Codable, Hashable, Identifiable {
    var id: String { date }
    let date: String
    let value: Double
}

struct PortfolioMetric: Codable, Hashable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
    let unit: String
    let latest: PortfolioPoint
    let series: [PortfolioPoint]
    let daysWithData: Int

    var latestText: String {
        switch key {
        case "steps", "active_energy", "exercise_session", "bp_systolic", "bp_diastolic", "blood_glucose":
            return String(Int(latest.value.rounded()))
        case "sleep_duration":
            let h = Int(latest.value); let m = Int(((latest.value - Double(h)) * 60).rounded())
            return "\(h)h \(String(format: "%02d", m))"
        default:
            return latest.value == latest.value.rounded() ? String(Int(latest.value)) : String(format: "%.1f", latest.value)
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
    let kind: String            // image | file
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
    var isWithdrawn: Bool { withdrawn == true }

    var sizeLabel: String {
        if byteSize >= 1_048_576 {
            return String(format: "%.1f MB", Double(byteSize) / 1_048_576)
        }
        if byteSize >= 1024 { return "\(byteSize / 1024) KB" }
        return "\(byteSize) B"
    }

    var displayName: String { filename ?? (isImage ? "Photo" : "File") }
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
