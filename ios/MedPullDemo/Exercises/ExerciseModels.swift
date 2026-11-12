import Foundation

// Wire types for the patient's side of the exercise calendar
// (`/api/mobile/exercises…`, backend/app/api/exercises.py and
// app/hep/schedule.py). The real iPhone app has no exercise screens yet; the
// patient web app does, and these are its types (patient-web/src/core/
// models.ts, "The exercise schedule") in Swift. Keys are snake_case on the
// wire; APIClient's decoder converts.
//
// Each type decodes by hand and insists only on what a screen cannot be
// drawn without (a row's id and status, a day's date). A key this build has
// never heard of is ignored, a missing one gets its default, and one field of
// an unexpected type does not sink the row: the calendar's server side is
// still growing (a `state` on every row, `series_id`, the clinic's
// `load_unit`).

// MARK: - What the therapist asks for

/// A clip of the attempt, the watch on: each is off, optional or required.
/// A row from a server that does not send the setting reads as optional,
/// which is the server's own default.
enum Requirement: String, Hashable {
    case off, optional, required

    init(wire: String?) {
        self = wire == "off" ? .off : wire == "required" ? .required : .optional
    }
}

// MARK: - Loads

/// The unit a clinic reads loads in. Kilograms are what every row stores and
/// what the app sends; a clinic that works in pounds says so
/// (`clinic.load_unit`) and the app converts for the eye, with the factor
/// and the rounding the server uses for the strings it builds
/// (app/hep/service.py `load_text`): pounds to a tenth, so 25 lb typed comes
/// back as 25 lb.
enum LoadUnit: String, Hashable {
    case kg, lb

    static let poundsPerKilogram = 2.20462

    init(wire: String?) { self = wire == "lb" ? .lb : .kg }

    /// A stored load as this clinic reads it: 10 kg is 10, or 22 (lb).
    func shown(kg: Double) -> Double {
        switch self {
        case .kg: return (kg * 100).rounded() / 100
        case .lb: return (kg * Self.poundsPerKilogram * 10).rounded() / 10
        }
    }

    /// What is sent for a number typed in this unit: kilograms, to the two
    /// decimals a row keeps.
    func kilograms(from shown: Double) -> Double {
        switch self {
        case .kg: return (shown * 100).rounded() / 100
        case .lb: return (shown / Self.poundsPerKilogram * 100).rounded() / 100
        }
    }

    /// "10 kg", "22 lb", "12.5 kg": no trailing zeros.
    func text(kg: Double) -> String { "\(Self.plain(shown(kg: kg))) \(rawValue)" }

    /// The step a plus or minus button moves a load by: a pair of small
    /// plates in either unit.
    var step: Double { self == .kg ? 2.5 : 5 }

    /// A number without trailing zeros ("10", "12.5", "11.34"), with a
    /// point whatever the phone's region: the server's own strings use one.
    static func plain(_ value: Double) -> String {
        var text = String(format: "%.2f", locale: Locale(identifier: "en_US_POSIX"), value)
        while text.hasSuffix("0") { text.removeLast() }
        if text.hasSuffix(".") { text.removeLast() }
        return text
    }
}

// MARK: - Clips

/// The therapist's demonstration of an exercise: the clinic's own clip when
/// it has one, else the library's. `url` is good for minutes (a presigned
/// link on AWS) or is a path into this API that needs the session (a
/// laptop), so it is read again from the feed whenever a clip is about to
/// be fetched and never kept.
struct ExerciseVideo: Decodable, Hashable {
    let id: Int
    /// "clinic" or "library".
    let source: String
    let url: String?
    let posterUrl: String?
    let contentType: String
    let uploadedByName: String?

    private enum CodingKeys: String, CodingKey { case id, source, url, posterUrl, contentType, uploadedByName }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        source = c.lenient(String.self, .source) ?? "library"
        url = c.lenient(String.self, .url)
        posterUrl = c.lenient(String.self, .posterUrl)
        contentType = c.lenient(String.self, .contentType) ?? "video/mp4"
        uploadedByName = c.lenient(String.self, .uploadedByName)
    }

    /// The same clip, whatever link it arrived with this time: the link of
    /// a presigned clip changes on every read.
    static func == (a: Self, b: Self) -> Bool { a.id == b.id && (a.url == nil) == (b.url == nil) }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

/// The clip the person sent back with a completion: a thread attachment.
struct ExerciseClip: Decodable, Hashable {
    let id: Int
    let contentType: String
    let byteSize: Int
    let filename: String?
    let withdrawn: Bool

    private enum CodingKeys: String, CodingKey { case id, contentType, byteSize, filename, withdrawn }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        contentType = c.lenient(String.self, .contentType) ?? "video/mp4"
        byteSize = c.lenient(Int.self, .byteSize) ?? 0
        filename = c.lenient(String.self, .filename)
        withdrawn = c.lenient(Bool.self, .withdrawn) ?? false
    }
}

// MARK: - What happened

/// The session around an attempt: when it ran, the pain before it, whether
/// the watch was on and what it saw. Nil until the person starts.
struct ExerciseSession: Decodable, Hashable {
    let startedAt: String?
    let endedAt: String?
    let durationS: Int?
    let painBefore: Int?
    let wearableWorn: Bool?
    let hrAvg: Int?
    let hrMax: Int?

    private enum CodingKeys: String, CodingKey {
        case startedAt, endedAt, durationS, painBefore, wearableWorn, hrAvg, hrMax
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        startedAt = c.lenient(String.self, .startedAt)
        endedAt = c.lenient(String.self, .endedAt)
        durationS = c.lenientInt(.durationS)
        painBefore = c.lenientInt(.painBefore)
        wearableWorn = c.lenient(Bool.self, .wearableWorn)
        hrAvg = c.lenientInt(.hrAvg)
        hrMax = c.lenientInt(.hrMax)
    }
}

/// The therapist's look at a completion: when, who, what she said.
struct ExerciseReview: Decodable, Hashable {
    let at: String?
    let byName: String?
    let note: String

    private enum CodingKeys: String, CodingKey { case at, byName, note }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        at = c.lenient(String.self, .at)
        byName = c.lenient(String.self, .byName)
        note = c.lenient(String.self, .note) ?? ""
    }
}

struct ExerciseCompletion: Decodable, Hashable {
    let completedAt: String?
    let painAfter: Int?
    let note: String
    /// "app" (the person) or "console" (the therapist logged it).
    let source: String
    let video: ExerciseClip?
    /// How hard it was, 0 to 10 (`ExerciseWords.effort`).
    let effort: Int?
    let setsDone: Int?
    let repsDone: Int?
    let loadDoneKg: Double?
    /// Nil until the therapist has looked at it.
    let review: ExerciseReview?

    private enum CodingKeys: String, CodingKey {
        case completedAt, painAfter, note, source, video, effort, setsDone, repsDone, loadDoneKg, review
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        completedAt = c.lenient(String.self, .completedAt)
        painAfter = c.lenientInt(.painAfter)
        note = c.lenient(String.self, .note) ?? ""
        source = c.lenient(String.self, .source) ?? "app"
        video = c.lenient(ExerciseClip.self, .video)
        effort = c.lenientInt(.effort)
        setsDone = c.lenientInt(.setsDone)
        repsDone = c.lenientInt(.repsDone)
        loadDoneKg = c.lenient(Double.self, .loadDoneKg)
        review = c.lenient(ExerciseReview.self, .review)
    }
}

// MARK: - One exercise on one day

/// Where a row stands on a given day. The server stores three of these
/// (`status`: assigned, done, skipped); the rest are read off the day and
/// the session, by the rule the console uses (app/hep/schedule.py
/// `state_of`): an open row started today is in progress, one whose day has
/// passed is missed, one on today is due, and the rest are still ahead.
enum ExerciseState: Hashable {
    case due, inProgress, done, skipped, missed, upcoming
}

struct ExerciseAssignment: Decodable, Identifiable, Hashable {
    let id: Int
    let exerciseId: Int?
    let title: String
    let steps: [String]
    let equipment: String
    let precautions: String
    /// "yyyy-MM-dd".
    let scheduledFor: String
    let sortOrder: Int
    let sets: Int?
    let reps: Int?
    let holdSeconds: Int?
    let side: String
    let sideLabel: String
    /// "3 sets × 10 reps · 10 kg · Left", built by the server in the
    /// clinic's own unit.
    let dose: String
    /// The therapist's note to the person, in her words.
    let clinicianInstructions: String
    let assignedByName: String?
    /// assigned | done | skipped
    let status: String
    let video: ExerciseVideo?
    let completion: ExerciseCompletion?
    let skipReason: String?
    let loadKg: Double?
    /// The effort she is aiming for, 0 to 10.
    let rpeTarget: Int?
    let videoRequirement: Requirement
    let wearableRequirement: Requirement
    let session: ExerciseSession?

    private enum CodingKeys: String, CodingKey {
        case id, exerciseId, title, steps, equipment, precautions, scheduledFor, sortOrder
        case sets, reps, holdSeconds, side, sideLabel, dose, clinicianInstructions, assignedByName
        case status, video, completion, skipReason, loadKg, rpeTarget
        case videoRequirement, wearableRequirement, session
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        status = try c.decode(String.self, forKey: .status)
        exerciseId = c.lenientInt(.exerciseId)
        title = c.lenient(String.self, .title) ?? "Exercise"
        steps = c.lenientList(String.self, .steps)
        equipment = c.lenient(String.self, .equipment) ?? ""
        precautions = c.lenient(String.self, .precautions) ?? ""
        scheduledFor = c.lenient(String.self, .scheduledFor) ?? ""
        sortOrder = c.lenientInt(.sortOrder) ?? 0
        sets = c.lenientInt(.sets)
        reps = c.lenientInt(.reps)
        holdSeconds = c.lenientInt(.holdSeconds)
        side = c.lenient(String.self, .side) ?? "not_applicable"
        sideLabel = c.lenient(String.self, .sideLabel) ?? ""
        dose = c.lenient(String.self, .dose) ?? ""
        clinicianInstructions = c.lenient(String.self, .clinicianInstructions) ?? ""
        assignedByName = c.lenient(String.self, .assignedByName)
        video = c.lenient(ExerciseVideo.self, .video)
        completion = c.lenient(ExerciseCompletion.self, .completion)
        skipReason = c.lenient(String.self, .skipReason)
        loadKg = c.lenient(Double.self, .loadKg)
        rpeTarget = c.lenientInt(.rpeTarget)
        videoRequirement = Requirement(wire: c.lenient(String.self, .videoRequirement))
        wearableRequirement = Requirement(wire: c.lenient(String.self, .wearableRequirement))
        session = c.lenient(ExerciseSession.self, .session)
    }

    var isOpen: Bool { status == "assigned" }
    var isDone: Bool { status == "done" }
    var isSkipped: Bool { status == "skipped" }
    var hasSide: Bool { !sideLabel.isEmpty && side != "not_applicable" }

    /// Whether a set is one timed hold (Wall Sits, 3 × 30 s) rather than a
    /// count of reps: the session then times the hold and has no rest
    /// between sets. Reps with a hold on each ("10 reps, hold 5 s") count
    /// reps.
    var holdIsUnit: Bool { (holdSeconds ?? 0) > 0 && !((reps ?? 0) > 0) }

    /// Done, with a clip the therapist has not looked at yet.
    var awaitingReview: Bool {
        guard isDone, let clip = completion?.video, !clip.withdrawn else { return false }
        return completion?.review == nil
    }

    /// The session's length in seconds: the server's figure, else the clock.
    var sessionSeconds: Int? {
        guard let session else { return nil }
        if let seconds = session.durationS { return seconds }
        guard let from = Dates.parse(session.startedAt), let to = Dates.parse(session.endedAt) else { return nil }
        return max(0, Int(to.timeIntervalSince(from).rounded()))
    }

    /// Where the row stands on `today` ("yyyy-MM-dd", the phone's own day).
    func state(on today: String) -> ExerciseState {
        if isDone { return .done }
        if isSkipped { return .skipped }
        if let started = session?.startedAt, started.hasPrefix(today) { return .inProgress }
        if scheduledFor < today { return .missed }
        return scheduledFor == today ? .due : .upcoming
    }

    /// "3 × 10 · 16 kg": what was done, from the completion when it says,
    /// else the dose. Nil when neither names a count.
    func doneLine(unit: LoadUnit) -> String? {
        ExerciseWords.counts(sets: completion?.setsDone ?? sets, reps: completion?.repsDone ?? reps,
                             loadKg: completion?.loadDoneKg ?? loadKg, unit: unit)
    }

    /// "3 × 10 · 10 kg": what was asked for.
    func prescribedLine(unit: LoadUnit) -> String? {
        ExerciseWords.counts(sets: sets, reps: reps, loadKg: loadKg, unit: unit)
    }
}

// MARK: - The feeds

/// One day of the week strip around the day asked for.
struct ExerciseDay: Decodable, Hashable {
    let date: String
    var assigned: Int
    var done: Int
    var skipped: Int

    private enum CodingKeys: String, CodingKey { case date, assigned, done, skipped }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        date = try c.decode(String.self, forKey: .date)
        assigned = c.lenientInt(.assigned) ?? 0
        done = c.lenientInt(.done) ?? 0
        skipped = c.lenientInt(.skipped) ?? 0
    }
}

/// Whose calendar it is, and the unit that clinic reads loads in.
struct ExerciseClinic: Decodable, Hashable {
    let id: String?
    let name: String?
    let loadUnit: LoadUnit

    private enum CodingKeys: String, CodingKey { case id, name, loadUnit }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = c.lenient(String.self, .id)
        name = c.lenient(String.self, .name)
        loadUnit = LoadUnit(wire: c.lenient(String.self, .loadUnit))
    }
}

/// `GET /api/mobile/exercises?date=`: the day's exercises in order, the ones
/// still open from the week before it, and a seven-day strip around it.
struct ExercisesResponse: Decodable, Equatable {
    let date: String
    var items: [ExerciseAssignment]
    /// Earlier days this week whose exercises are still to do.
    var overdue: [ExerciseAssignment]
    var week: [ExerciseDay]
    let clinic: ExerciseClinic?

    private enum CodingKeys: String, CodingKey { case date, items, overdue, week, clinic }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        date = try c.decode(String.self, forKey: .date)
        items = c.lenientList(ExerciseAssignment.self, .items)
        overdue = c.lenientList(ExerciseAssignment.self, .overdue)
        week = c.lenientList(ExerciseDay.self, .week)
        clinic = c.lenient(ExerciseClinic.self, .clinic)
    }

    /// Whether Today shows the schedule at all: a person with no schedule
    /// never sees an empty card. A rest day inside a scheduled week does
    /// show, so the person knows nothing is missing.
    var hasSchedule: Bool {
        !items.isEmpty || !overdue.isEmpty || week.contains { $0.assigned > 0 }
    }
}

/// One day of the program: its exercises and the counts the dots draw.
/// `assigned` is every row on the day; `missed` the ones still to do once
/// the day has passed.
struct ProgramDay: Decodable, Identifiable, Equatable {
    let date: String
    var items: [ExerciseAssignment]
    var assigned: Int
    var done: Int
    var skipped: Int
    var missed: Int

    var id: String { date }

    private enum CodingKeys: String, CodingKey { case date, items, assigned, done, skipped, missed }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        date = try c.decode(String.self, forKey: .date)
        items = c.lenientList(ExerciseAssignment.self, .items)
        assigned = c.lenientInt(.assigned) ?? items.count
        done = c.lenientInt(.done) ?? items.filter(\.isDone).count
        skipped = c.lenientInt(.skipped) ?? items.filter(\.isSkipped).count
        missed = c.lenientInt(.missed) ?? 0
    }
}

/// `GET /api/mobile/exercises/program?start=&days=`.
struct ProgramResponse: Decodable, Equatable {
    let start: String
    var days: [ProgramDay]
    let clinic: ExerciseClinic?

    private enum CodingKeys: String, CodingKey { case start, days, clinic }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        start = c.lenient(String.self, .start) ?? ""
        days = c.lenientList(ProgramDay.self, .days)
        clinic = c.lenient(ExerciseClinic.self, .clinic)
    }

    /// Whether there is a program to show: any exercise on any of the days.
    var hasProgram: Bool { days.contains { !$0.items.isEmpty || $0.assigned > 0 } }
}

/// The start, complete and skip routes answer `{"assignment": {…}}`; a bare
/// row is read too.
struct AssignmentAnswer: Decodable {
    let assignment: ExerciseAssignment

    private enum CodingKeys: String, CodingKey { case assignment }

    init(from decoder: Decoder) throws {
        if let c = try? decoder.container(keyedBy: CodingKeys.self), c.contains(.assignment) {
            assignment = try c.decode(ExerciseAssignment.self, forKey: .assignment)
        } else {
            assignment = try ExerciseAssignment(from: decoder)
        }
    }
}

// MARK: - What the app sends

/// A clip that reached storage and waits for the completion that gives it
/// meaning. With an object store the bytes went to the key the ticket
/// minted (`storageKey`); without one they went through the API, which
/// confirmed a row as it stored them (`attachmentId`). Exactly one is set.
struct StagedClip: Encodable, Equatable {
    let storageKey: String?
    let attachmentId: Int?
    let contentType: String
    let byteSize: Int
    let filename: String?
}

/// `POST /api/mobile/exercises/{id}/complete`. A field the person did not
/// answer is left out, which the server reads as "not said".
struct ExerciseCompletionBody: Encodable {
    var painAfter: Int?
    var note: String = ""
    var video: StagedClip?
    var effort: Int?
    var setsDone: Int?
    var repsDone: Int?
    var loadDoneKg: Double?
    var wearableWorn: Bool?
    /// ISO 8601 with the local offset (`Dates.iso`); nil when the exercise
    /// was marked done without a session.
    var startedAt: String?
    var endedAt: String?
}

// MARK: - Words

/// The schedule's phrases, shared by every exercise screen.
enum ExerciseWords {
    private static let effortWords = [
        "Nothing", "Very easy", "Easy", "Light", "Some effort", "Hard", "Harder", "Very hard", "Really hard",
        "Almost all out", "All out",
    ]

    /// How hard it was, in the words a lifter would use, from nothing to
    /// all out. The therapist's target is on the same ladder.
    static func effort(_ n: Int) -> String { effortWords[max(0, min(10, n))] }

    /// "Dr. Ashley Gregg" becomes "Dr. Gregg"; "Ashley Gregg" becomes
    /// "Ashley": the way a person says their therapist's name.
    static func therapist(_ name: String?) -> String {
        let words = (name ?? "").split(separator: " ").map(String.init)
        guard let first = words.first else { return "your therapist" }
        if words.count == 1 { return first }
        if first.hasSuffix("."), let last = words.last { return "\(first) \(last)" }
        return first
    }

    /// "3 × 10 · 16 kg", or nil when nothing names a count.
    static func counts(sets: Int?, reps: Int?, loadKg: Double?, unit: LoadUnit) -> String? {
        var parts: [String] = []
        if let sets, let reps {
            parts.append("\(sets) × \(reps)")
        } else if let sets {
            parts.append("\(sets) \(sets == 1 ? "set" : "sets")")
        }
        if let loadKg { parts.append(unit.text(kg: loadKg)) }
        return parts.isEmpty ? nil : parts.joined(separator: MP.dot)
    }

    /// "11 min", "45 s": how long a session ran.
    static func duration(_ seconds: Int?) -> String? {
        guard let seconds, seconds >= 0 else { return nil }
        return seconds < 60 ? "\(seconds) s" : "\(Int((Double(seconds) / 60).rounded())) min"
    }

    /// "4:12" from seconds.
    static func clock(_ seconds: Int) -> String {
        let s = max(0, seconds)
        return "\(s / 60):" + String(format: "%02d", s % 60)
    }

    /// "just now", "5 min. ago": a server timestamp against the phone's
    /// clock. Inside the first minute the system's own wording is "in 0
    /// sec.", which is not something to say to a person.
    static func ago(_ raw: String?) -> String {
        guard let date = Dates.parse(raw) else { return "" }
        if abs(date.timeIntervalSinceNow) < 60 { return "just now" }
        return Dates.relative(raw)
    }

    /// "Monday" for a server day; "Nov 13" style is `Dates.monthDay`.
    static func weekday(_ day: String) -> String {
        guard let date = Dates.parse(day) else { return day }
        return date.formatted(.dateTime.weekday(.wide))
    }

    /// "Today", "Yesterday", "Tomorrow", else the weekday.
    static func dayTitle(_ day: String, today: String) -> String {
        if day == today { return "Today" }
        switch Dates.daysAgo(day) {
        case 1: return "Yesterday"
        case -1: return "Tomorrow"
        default: return weekday(day)
        }
    }

    /// The same, for the middle of a sentence: "tomorrow", "Friday".
    static func dayInSentence(_ day: String, today: String) -> String {
        let title = dayTitle(day, today: today)
        return ["Today", "Yesterday", "Tomorrow"].contains(title) ? title.lowercased() : title
    }

    /// A server sentence set for the screen: the middle dots the server
    /// writes between facts get the thin spaces Outfit needs around them
    /// (`MP.dot`), and straight apostrophes are curled.
    static func typeset(_ text: String) -> String { text.demoTypeset }
}

extension KeyedDecodingContainer {
    /// A whole number that may arrive as 3, 3.0 or "3".
    func lenientInt(_ key: Key) -> Int? {
        if let n = lenient(Int.self, key) { return n }
        if let d = lenient(Double.self, key), d.isFinite { return Int(d.rounded()) }
        if let s = lenient(String.self, key) { return Int(s) }
        return nil
    }
}
