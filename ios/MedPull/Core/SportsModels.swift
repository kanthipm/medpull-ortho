import Foundation

// Wire types for MedPull Sports (/api/mobile/sports). Keys are snake_case
// on the wire; the decoder converts. The readiness panels reuse `Panel`
// from the personal tier: the server computes them with the same engine.

// MARK: - Organisations

struct SportsOrg: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let shortName: String
    let kind: String          // college | pro | club | academy
    let city: String
    let state: String
    let conference: String?
    let level: String
    let levelLabel: String
    let requiresCode: Bool
    let teams: [SportsTeam]

    var kindLabel: String {
        switch kind {
        case "college": return "College"
        case "pro": return "Professional"
        case "academy": return "Academy"
        default: return "Club"
        }
    }
}

struct SportsTeam: Codable, Identifiable, Hashable {
    let id: String
    let orgId: String
    let name: String
    let sport: String
    let sportLabel: String
    let sex: String?
    let season: String
    let phase: String
    /// Only on the staff listing; absent elsewhere.
    let roster: Int?
}

struct SportsStaffMember: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let role: String
    let roleLabel: String
    let athleteFacing: Bool
}

/// The athlete behind the account, as `/me.sports` and `/profile` carry it.
struct SportsProfile: Codable, Hashable {
    let sport: String
    let sportLabel: String
    let org: SportsOrg?
    let team: SportsTeam?
    let coachLinked: Bool
    let position: String?
    let jersey: String?
    let classYear: String?
    let level: String
    let levelLabel: String
    let heightCm: Double?
    let weightKg: Double?
    let wingspanCm: Double?
    let standingReachCm: Double?
    let dominantSide: String?
    let status: String          // available | modified | out
    let statusLabel: String
    let statusNote: String?
    let units: String
    let cycleTracking: Bool
    let sex: String?
    let age: Int?
    let staff: [SportsStaffMember]

    var isImperial: Bool { units == "imperial" }
    var teamLine: String? {
        guard let org else { return nil }
        if let team { return "\(org.shortName) \(team.name)" }
        return org.shortName
    }
}

// MARK: - The catalog

struct SportsCategory: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let symbol: String
    let family: String
}

struct TestSpec: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let category: String
    let unit: String
    let higherIsBetter: Bool
    let protocol_: String
    let why: String
    let sports: [String]
    let sided: Bool
    let decimals: Int
    let devices: [String]
    let phone: Bool
    let asymmetryFlagPct: Double?
    let core: Bool
    let benchmarkNote: String

    private enum CodingKeys: String, CodingKey {
        case key, label, category, unit, higherIsBetter, why, sports, sided, decimals, devices, phone,
             asymmetryFlagPct, core, benchmarkNote
        case protocol_ = "protocol"
    }
}

struct InjurySummary: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let bodyRegion: String
    let symbol: String
    let summary: String
    let sports: [String]
    let surgical: Bool
    let grafts: [String]
    let grades: [String]
    let typicalReturnWeeks: [Int]
    let reinjuryNote: String
    let sources: [String]
    let measures: [String]
    let retest: [String]
    let sidelines: Bool?
}

struct MeasureSpec: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let unit: String
    let higherIsBetter: Bool
    let protocol_: String
    let why: String
    let sided: Bool
    let kind: String       // number | grade | score | yes_no
    let lo: Double?
    let hi: Double?
    let decimals: Int
    let phone: Bool
    let devices: [String]
    let symbol: String
    let testKey: String?
    let mdc: Double?

    private enum CodingKeys: String, CodingKey {
        case key, label, unit, higherIsBetter, why, sided, kind, lo, hi, decimals, phone, devices, symbol, testKey, mdc
        case protocol_ = "protocol"
    }
}

struct WellnessSpec: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let prompt: String
    let low: String
    let high: String
    let direction: String   // good | bad
    let daily: Bool
    let symbol: String
    let hooper: Bool
    let femaleOnly: Bool
    let kind: String        // scale | choice | number | yes_no | text
    let options: [String]
    let unit: String
}

struct DeviceSpec: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let name: String
    let maker: String
    let category: String
    let categoryLabel: String
    let path: String        // healthkit | junction | partner | import | ble | none
    let pathLabel: String
    let provides: [String]
    let symbol: String
    let sports: [String]
    let blurb: String
    let team: Bool
    let scores: [String]
    let note: String
    let junctionSlug: String?
    let popular: Bool
    /// Only on /devices.
    let state: String?      // connected | sample | available | unavailable | linking
    let detail: String?
}

struct SportsCatalog: Codable {
    struct Keyed: Codable, Hashable { let key: String; let label: String }
    let sport: String
    let sportLabel: String
    let sports: [Keyed]
    let positions: [String]
    let classYears: [String]
    let levels: [Keyed]
    let statuses: [Keyed]
    let categories: [SportsCategory]
    let tests: [TestSpec]
    let injuries: [InjurySummary]
    let measures: [String: MeasureSpec]
    let wellness: [WellnessSpec]
    let devices: [DeviceSpec]
    let deviceCategories: [String: String]
    let devicePaths: [String: String]

    func test(_ key: String) -> TestSpec? { tests.first { $0.key == key } }
    func injury(_ key: String) -> InjurySummary? { injuries.first { $0.key == key } }
}

// MARK: - Recovery

struct SportsVerdict: Codable, Hashable {
    let kind: String        // push | steady | modify | rest | rehab | learning | game | game_prime
    let title: String
    let score: Double?
    let reason: String
    let detail: String
    let reasons: [String]
}

struct WellnessItem: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let value: Double
    let date: String
    let z: Double?
    let direction: String
    let symbol: String
    let state: String       // ok | watch | flag
    let series: [PanelPoint]
}

struct WellnessPanel: Codable, Hashable {
    let key: String
    let title: String
    let status: String
    let statusText: String
    let compositeZ: Double?
    let hooper: Double?
    let answeredToday: Int
    let latestDate: String?
    let items: [WellnessItem]
    let finding: String
    let method: String
    let notes: [WellnessNote]

    var tone: MP.Tone {
        switch status {
        case "ok": return .low
        case "watch": return .med
        case "flag": return .high
        default: return .missing
        }
    }
}

struct WellnessNote: Codable, Hashable {
    let date: String
    let text: String
}

struct HRVVariability: Codable, Hashable {
    let cvWeek: Double
    let cvPrior: Double
    let meanState: String
    let cvState: String
    let read: String
    let status: String
    let saturation: Bool
    let swcLn: Double
}

struct LoadRead: Codable, Hashable {
    let source: String?
    let weekLoad: Double
    let priorWeekLoad: Double?
    let priorMeanLoad: Double?
    let changePct: Double?
    let minutesWeek: Double
    let sessionsWeek: Int
    let gamesWeek: Int
    let byKind: [String: Double]
    let monotony: Double?
    let strain: Double?
    let acwr: Double?
    let status: String
    let statusText: String
    let finding: String
    let lastSession: String?
    let series: [PanelPoint]
    let method: String

    var tone: MP.Tone {
        switch status {
        case "ok": return .low
        case "watch": return .med
        case "flag": return .high
        default: return .missing
        }
    }
}

struct SportsEvent: Codable, Identifiable, Hashable {
    let id: Int
    let date: String
    let startTime: String?
    let kind: String        // practice | game | lift | travel | off | shootaround | conditioning
    let title: String
    let opponent: String?
    let home: Bool?
    let location: String?
    let note: String?

    var day: Date { Dates.parse(date) ?? .distantPast }
    var isGame: Bool { kind == "game" || kind == "match" }
    var symbol: String {
        switch kind {
        case "game", "match": return "trophy.fill"
        case "lift": return "dumbbell.fill"
        case "travel": return "airplane"
        case "shootaround": return "basketball.fill"
        case "conditioning": return "flame.fill"
        case "off": return "zzz"
        default: return "figure.basketball"
        }
    }
    var line: String {
        var parts: [String] = []
        if let opponent { parts.append("vs \(opponent)") }
        if let home { parts.append(home ? "Home" : "Away") }
        if let startTime { parts.append(Self.clock(startTime)) }
        return parts.joined(separator: MP.dot)
    }
    static func clock(_ hhmm: String) -> String {
        let bits = hhmm.split(separator: ":")
        guard bits.count == 2, let h = Int(bits[0]), let m = Int(bits[1]) else { return hhmm }
        let suffix = h >= 12 ? "pm" : "am"
        let h12 = h % 12 == 0 ? 12 : h % 12
        return m == 0 ? "\(h12) \(suffix)" : String(format: "%d:%02d %@", h12, m, suffix)
    }
}

struct ScheduleRead: Codable, Hashable {
    let gameToday: SportsEvent?
    let gameYesterday: Bool
    let backToBack: Bool
    let threeInFour: Bool
    let nextGame: SportsEvent?
    let daysToNextGame: Int?
    let gamesLast7: Int
    let density: String
    let travel: Bool
    let awayRecent: Bool
    let today: [SportsEvent]
    let upcoming: [SportsEvent]
    let finding: String
    let lastGame: SportsEvent?
}

struct IllnessWatch: Codable, Hashable {
    let status: String
    let signals: [String]
    let finding: String
}

struct HydrationRead: Codable, Hashable {
    let status: String
    let urine: Double?
    let massDropPct: Double?
    let finding: String
}

struct CycleRead: Codable, Hashable {
    let phase: String?
    let day: Int?
    let cycleLength: Int?
    let flags: [String]
    let note: String
}

struct NeuroSignal: Codable, Hashable, Identifiable {
    var id: String { label }
    let label: String
    let pct: Double
    let value: String
    let baseline: String
}

struct NeuromuscularRead: Codable, Hashable {
    let status: String      // ok | watch | flag | nodata
    let statusText: String
    let finding: String
    let signals: [NeuroSignal]
    let latestDate: String?
    let source: String?

    var hasData: Bool { status != "nodata" }
    var tone: MP.Tone {
        switch status {
        case "ok": return .low
        case "watch": return .med
        case "flag": return .high
        default: return .missing
        }
    }
}

struct JumpLoad: Codable, Hashable {
    let week: Double
    let priorWeek: Double?
    let changePct: Double?
    let today: Double
    let meanSession: Double?
    let status: String
    let text: String
    let series: [PanelPoint]
}

struct Suggestion: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let title: String
    let why: String
    let actions: [String]
    let evidence: String    // A | B | C
    let priority: Int
    let category: String    // recovery | sleep | load | nutrition | travel | hydration | illness | health
    let source: String

    var symbol: String {
        switch category {
        case "sleep": return "bed.double.fill"
        case "load": return "flame.fill"
        case "nutrition": return "fork.knife"
        case "travel": return "airplane"
        case "hydration": return "drop.fill"
        case "illness": return "thermometer.medium"
        case "health": return "heart.text.square.fill"
        default: return "leaf.fill"
        }
    }
    var family: MP.Category {
        switch category {
        case "sleep": return .indigo
        case "load": return .teal
        case "nutrition", "hydration": return .blue
        case "illness", "health": return .violet
        default: return .teal
        }
    }
}

struct RecoveryBoard: Codable {
    let asOf: String
    let daysWithData: Int
    let verdict: SportsVerdict
    let readiness: Panel
    let panels: [String: Panel]
    let sections: [String]
    let wellness: WellnessPanel
    let hrvCv: HRVVariability?
    let load: LoadRead
    let schedule: ScheduleRead
    let illness: IllnessWatch
    let hydration: HydrationRead
    let cycle: CycleRead?
    let neuromuscular: NeuromuscularRead
    let jumps: JumpLoad?
    let suggestions: [Suggestion]
    let trends: [String: Trend]?
    let week: WeekReview?
    let availability: String?

    func panel(_ key: String) -> Panel? { panels[key] }
}

// MARK: - Performance

struct Benchmark: Codable, Hashable {
    let percentile: Int
    let word: String
    let reference: String
    let p25: Double
    let p50: Double
    let p75: Double
    let p90: Double
}

struct TestTrend: Codable, Hashable {
    let pct: Double
    let better: Bool?
}

struct TestBaseline: Codable, Hashable {
    let baselineMean: Double
    let baselineSd: Double
    let pct: Double
    let z: Double
    let swc: Double?
    let n: Int
}

struct TestPoint: Codable, Hashable, Identifiable {
    var id: String { date + (source ?? "") + String(value) }
    let date: String
    let value: Double
    let source: String?
    let device: String?
    var day: Date { Dates.parse(date) ?? .distantPast }
}

struct SideSeries: Codable, Hashable {
    let latest: Double?
    let series: [TestPoint]
}

struct Asymmetry: Codable, Hashable {
    let pct: Double
    let weaker: String
    let lsi: Double
}

struct TestCard: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let category: String
    let unit: String
    let higherIsBetter: Bool
    let sided: Bool
    let decimals: Int
    let core: Bool
    let phone: Bool
    let left: SideSeries?
    let right: SideSeries?
    let asymmetry: Asymmetry?
    let asymmetryStatus: String?
    let latest: Double
    let latestText: String
    let latestDate: String?
    let daysAgo: Int?
    let best: Double?
    let bestText: String?
    let isBest: Bool
    let series: [TestPoint]
    let count: Int
    let trend: TestTrend?
    let baseline: TestBaseline?
    let band: Benchmark?
    let source: String?
    let device: String?
}

struct AvailableTest: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let unit: String
    let core: Bool
    let phone: Bool
    let sided: Bool
}

struct PerformanceCategory: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let symbol: String
    let family: String
    let cards: [TestCard]
    let available: [AvailableTest]

    var categoryFamily: MP.Category {
        switch family {
        case "blue": return .blue
        case "indigo": return .indigo
        case "violet": return .violet
        default: return .teal
        }
    }
}

struct HeadlineTest: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let unit: String
    let logged: Bool
    let latestText: String?
    let band: Benchmark?
    let trend: TestTrend?
    let daysAgo: Int?
    let phone: Bool
    let sided: Bool
}

struct AsymmetryFlag: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let asymmetry: Asymmetry
    let status: String
}

struct RecentBest: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let latestText: String
    let unit: String
    let date: String?
}

struct PerformanceBoard: Codable {
    let asOf: String
    let sport: String
    let level: String
    let sex: String?
    let logged: Int
    let available: Int
    let overallPercentile: Int?
    let neuromuscular: NeuromuscularRead
    let asymmetries: [AsymmetryFlag]
    let recentBests: [RecentBest]
    let headline: [HeadlineTest]
    let categories: [PerformanceCategory]
    let cards: [String: TestCard]
    let jumps: JumpLoad?
}

// MARK: - Rehab

struct Criterion: Codable, Identifiable, Hashable {
    var id: String { measureKey + label }
    let measureKey: String
    let label: String
    let op: String
    let target: Double
    let use: String         // value | lsi | diff | days
    let met: Bool?
    let value: Double?
    let valueText: String?
    let rts: Bool
    let measureLabel: String
    let unit: String
    let date: String?
    let note: String?
}

struct RehabPhase: Codable, Identifiable, Hashable {
    var id: Int { number }
    let number: Int
    let name: String
    let window: String
    let goals: [String]
    let focus: [String]
    let avoid: [String]
    let weeksMin: Int
    let state: String       // done | current | ahead
    let criteria: [Criterion]
    let met: Int
    let total: Int
}

struct CurrentPhase: Codable, Hashable {
    let number: Int
    let name: String
    let window: String
    let of: Int
    let goals: [String]
    let avoid: [String]
    let criteria: [Criterion]
    let met: Int
    let total: Int
    let override: Int?
}

struct RTSRead: Codable, Hashable {
    let criteria: [Criterion]
    let met: Int
    let total: Int
    let known: Int
    let pct: Int
    let projected: String
    let window: [String]
    let typicalWeeks: [Int]
    let reinjuryNote: String
}

struct MeasureHistory: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let unit: String
    let sided: Bool
    let kind: String
    let phone: Bool
    let higherIsBetter: Bool
    let lo: Double?
    let hi: Double?
    let decimals: Int
    let logged: Bool
    let involved: [TestPoint]
    let uninvolved: [TestPoint]
    let latest: Double?
    let latestDate: String?
    let uninvolvedLatest: Double?
    let lsi: Double?
    let protocol_: String
    let why: String
    let symbol: String
    let testKey: String?

    private enum CodingKeys: String, CodingKey {
        case key, label, unit, sided, kind, phone, higherIsBetter, lo, hi, decimals, logged, involved, uninvolved,
             latest, latestDate, uninvolvedLatest, lsi, why, symbol, testKey
        case protocol_ = "protocol"
    }
}

struct RehabFocus: Codable, Identifiable, Hashable {
    var id: String { kind + title }
    let kind: String        // measure | time | block
    let title: String
    let why: String
    let actions: [String]
    let measureKey: String?
    let missing: Bool?
}

struct PainRead: Codable, Hashable {
    let value: Double
    let date: String
}

struct InjuryBoard: Codable, Identifiable, Hashable {
    let id: Int
    let injuryKey: String
    let label: String
    let side: String?
    let bodyRegion: String
    let dateOfInjury: String
    let dateOfSurgery: String?
    let graft: String?
    let grade: String?
    let mechanism: String?
    let status: String
    let days: Int
    let weeks: Double
    let anchor: String      // surgery | injury
    let targetReturnDate: String?
    let clearedAt: String?
    let clinician: String?
    let note: String?
    let symbol: String
    let known: Bool
    let summary: String?
    let surgical: Bool?
    let phase: CurrentPhase?
    let phases: [RehabPhase]
    let rts: RTSRead?
    let measures: [MeasureHistory]
    let focus: [RehabFocus]
    let sportProgression: [String]?
    let sources: [String]?
    let retest: [String]?
    let pain: PainRead?
    let lastMeasure: String?

    var sideLabel: String? { side.map { $0.capitalized } }
    var title: String { side.map { "\(label), \($0)" } ?? label }
    var weeksText: String { weeks >= 8 ? String(format: "%.1f months", weeks / 4.345) : String(format: "%.0f weeks", weeks) }
}

struct RehabBoard: Codable {
    let active: [InjuryBoard]
    let past: [InjuryBoard]
    let availability: String
    let asOf: String
    let catalog: [InjurySummary]?
}

// MARK: - Home

struct InjuryGlance: Codable, Identifiable, Hashable {
    let id: Int
    let label: String
    let side: String?
    let status: String
    let days: Int
    let weeks: Double
    let symbol: String
    let bodyRegion: String
    let phase: CurrentPhase?
    let rts: RTSGlance?
    let focus: [RehabFocus]
}

struct RTSGlance: Codable, Hashable {
    let met: Int?
    let total: Int?
    let pct: Int?
    let projected: String?
}

struct SportsHome: Codable {
    let asOf: String
    let profile: SportsProfile
    let availability: String
    let availabilityLabel: String
    let verdict: SportsVerdict
    let brief: Brief?
    let readiness: Panel
    let daysWithData: Int
    let wellness: WellnessPanel
    let schedule: ScheduleRead
    let suggestions: [Suggestion]
    let suggestionCount: Int
    let neuromuscular: NeuromuscularRead
    let jumps: JumpLoad?
    let load: LoadRead
    let sleep: Panel?
    let hrv: Panel?
    let restingHr: Panel?
    let performanceHeadline: [HeadlineTest]
    let performanceLogged: Int
    let overallPercentile: Int?
    let asymmetries: [AsymmetryFlag]
    let injuries: [InjuryGlance]
    let tasks: [RecoveryTask]
    let devicesConnected: Int
    let guardrail: String
}

// MARK: - Devices

struct DeviceGroup: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let label: String
    let devices: [DeviceSpec]
}

struct DevicesBoard: Codable {
    let appleHealth: AppleHealthStatus?
    let aggregatorConfigured: Bool?
    let connected: Int
    let groups: [DeviceGroup]
    let paths: [String: String]
}

// MARK: - Sessions

struct SportsSession: Codable, Identifiable, Hashable {
    let id: Int
    let date: String
    let kind: String
    let minutes: Double
    let rpe: Double?
    let loadAu: Double?
    let jumps: Int?
    let playerLoad: Double?
    let distanceM: Double?
    let highSpeedM: Double?
    let maxSpeedKmh: Double?
    let averageHr: Double?
    let source: String
    let note: String?
}

// MARK: - Responses

struct SportsJoinResponse: Codable {
    let status: String
    let verified: Bool
    let sessionToken: String
    let me: Me
}

struct WellnessLogResponse: Codable {
    let ok: Bool
    let written: Int
    let wellness: WellnessPanel
    let verdict: SportsVerdict
    let suggestions: [Suggestion]
}

struct SessionLogResponse: Codable {
    let ok: Bool
    let id: Int
    let loadAu: Double?
}

struct TestsLogResponse: Codable {
    let ok: Bool
    let ids: [Int]
    let performance: PerformanceBoard
}

struct PhoneJumpResponse: Codable {
    let ok: Bool
    let id: Int?
    let heightCm: Double
    let flightTimeMs: Double
    let takeoffPeakMs2: Double
    let landingPeakMs2: Double
    let confidence: String
    let method: String
    let heightIn: Double
}

struct PhoneBalanceResponse: Codable {
    let ok: Bool
    let id: Int?
    let seconds: Double
    let swayDegMean: Double
    let swayDegMax: Double
    let pathDeg: Double
    let steadiness: Double
}

struct InjuryReportResponse: Codable {
    let ok: Bool
    let id: Int
    let rehab: RehabBoard
}

struct InjuryPatchResponse: Codable {
    let ok: Bool
    let rehab: RehabBoard
}

struct MeasuresLogResponse: Codable {
    let ok: Bool
    let injury: InjuryBoard?
}

struct SportsProfileResponse: Codable {
    let profile: SportsProfile
    let me: Me?
}

struct DeviceConnectResponse: Codable {
    let ok: Bool
    let linkUrl: String?
    let state: String?
    let detail: String?
}

struct OrgsResponse: Codable { let orgs: [SportsOrg] }
struct SessionsResponse: Codable { let sessions: [SportsSession] }

// MARK: - Looks

extension SportsVerdict {
    var gradient: MPGradient {
        switch kind {
        case "push", "game": return .sage
        case "steady": return .meadow
        case "modify", "game_prime": return .amber
        case "rest": return .clay
        case "rehab": return .dusk
        default: return .lilac
        }
    }
    var tone: MP.Tone {
        switch kind {
        case "push", "game": return .low
        case "steady": return .brand
        case "modify", "game_prime": return .med
        case "rest": return .high
        case "rehab": return .brand
        default: return .missing
        }
    }
    var symbol: String {
        switch kind {
        case "push": return "bolt.fill"
        case "game": return "trophy.fill"
        case "game_prime": return "trophy"
        case "steady": return "equal.circle.fill"
        case "modify": return "slider.horizontal.3"
        case "rest": return "bed.double.fill"
        case "rehab": return "cross.case.fill"
        default: return "hourglass"
        }
    }
}

enum Availability {
    static func tone(_ status: String) -> MP.Tone {
        switch status {
        case "available": return .low
        case "modified": return .med
        case "out": return .high
        default: return .missing
        }
    }
    static func label(_ status: String) -> String {
        switch status {
        case "available": return "Available"
        case "modified": return "Modified"
        case "out": return "Out"
        default: return status.capitalized
        }
    }
}

extension String {
    /// "ok" / "watch" / "flag" / "nodata" to a tone.
    var statusTone: MP.Tone {
        switch self {
        case "ok": return .low
        case "watch": return .med
        case "flag": return .high
        default: return .missing
        }
    }
}

enum SportsUnits {
    static func height(cm: Double?, imperial: Bool) -> String? {
        guard let cm else { return nil }
        if imperial {
            let inches = cm / 2.54
            let ft = Int(inches / 12)
            let rem = Int((inches - Double(ft) * 12).rounded())
            return "\(ft)′\(rem)″"
        }
        return String(format: "%.0f cm", cm)
    }
    static func length(cm: Double?, imperial: Bool) -> String? {
        guard let cm else { return nil }
        return imperial ? String(format: "%.1f in", cm / 2.54) : String(format: "%.0f cm", cm)
    }
    static func weight(kg: Double?, imperial: Bool) -> String? {
        guard let kg else { return nil }
        return imperial ? String(format: "%.0f lb", kg / 0.4536) : String(format: "%.1f kg", kg)
    }
}
