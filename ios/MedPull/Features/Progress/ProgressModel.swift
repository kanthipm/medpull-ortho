import Foundation

/// How the Progress tab sorts every signal the server can send: four
/// groups a patient recognises, each with a glyph family. Hue is the
/// category, never the state.
enum SignalGroup: String, CaseIterable, Identifiable {
    case movement, activity, rest, body

    var id: String { rawValue }

    var title: String {
        switch self {
        case .movement: return "Movement"
        case .activity: return "Activity"
        case .rest: return "Rest"
        case .body: return "Body"
        }
    }

    var blurb: String {
        switch self {
        case .movement: return "How you walk and move. Measured by your phone and watch."
        case .activity: return "How much you move each day."
        case .rest: return "How you sleep and recover overnight."
        case .body: return "Vitals and other readings."
        }
    }

    var family: MP.Category {
        switch self {
        case .movement: return .teal
        case .activity: return .blue
        case .rest: return .indigo
        case .body: return .violet
        }
    }

    static func group(for key: String) -> SignalGroup {
        switch key {
        case "walking_speed", "step_length", "cadence", "walking_asymmetry_pct", "double_support_pct",
             "walking_steadiness", "stair_speed_up", "stair_speed_down", "six_min_walk",
             "rom_flexion", "rom_extension", "rom_abduction":
            return .movement
        case "steps", "exercise_session", "active_energy", "calories":
            return .activity
        case "sleep_duration", "hrv_rmssd", "hrv_sdnn", "resting_hr", "stress_index", "respiratory_rate":
            return .rest
        default:
            return .body
        }
    }

    /// The order rows take inside a group: the reading a patient asks about
    /// first comes first.
    static let order: [String] = [
        "walking_speed", "six_min_walk", "step_length", "cadence", "walking_steadiness",
        "walking_asymmetry_pct", "double_support_pct", "stair_speed_up", "stair_speed_down",
        "rom_flexion", "rom_extension", "rom_abduction",
        "steps", "exercise_session", "active_energy", "calories",
        "sleep_duration", "resting_hr", "hrv_rmssd", "hrv_sdnn", "stress_index", "respiratory_rate",
        "skin_temp", "skin_temp_delta", "spo2", "pain_nrs", "body_weight", "bp_systolic", "bp_diastolic",
        "blood_glucose", "vo2_max", "hr_recovery_1min",
    ]

    static func rank(_ key: String) -> Int { order.firstIndex(of: key) ?? order.count }
}

/// The signals MedPull measures itself with the phone (backend
/// app/engine/mobility), as the Measure tab lists them.
enum MeasuredSignals {
    static let guidedWalk = ["walking_speed", "step_length", "cadence", "walking_asymmetry_pct",
                             "double_support_pct", "walking_steadiness"]
    static let sixMinuteWalk = ["six_min_walk"]
    static let rangeOfMotion = ["rom_flexion", "rom_extension", "rom_abduction"]
    static var all: [String] { guidedWalk + sixMinuteWalk + rangeOfMotion }
}

extension PortfolioMetric {
    var group: SignalGroup { SignalGroup.group(for: key) }

    /// The SF Symbol for this signal's glyph.
    var symbol: String {
        switch key {
        case "steps": return "figure.walk"
        case "walking_speed": return "figure.walk.motion"
        case "step_length": return "ruler"
        case "cadence": return "metronome"
        case "walking_asymmetry_pct", "double_support_pct": return "figure.walk.arrival"
        case "walking_steadiness": return "figure.stand"
        case "stair_speed_up", "stair_speed_down": return "stairs"
        case "six_min_walk": return "timer"
        case "rom_flexion", "rom_extension", "rom_abduction": return "angle"
        case "exercise_session": return "figure.run"
        case "active_energy", "calories": return "flame.fill"
        case "sleep_duration": return "bed.double.fill"
        case "resting_hr": return "heart.fill"
        case "hrv_rmssd", "hrv_sdnn": return "waveform.path.ecg"
        case "stress_index": return "wind"
        case "spo2": return "lungs.fill"
        case "respiratory_rate": return "wind"
        case "bp_systolic", "bp_diastolic": return "heart.text.square.fill"
        case "blood_glucose": return "drop.fill"
        case "body_weight": return "scalemass.fill"
        case "pain_nrs": return "bandage.fill"
        case "skin_temp", "skin_temp_delta": return "thermometer.medium"
        case "vo2_max": return "lungs.fill"
        case "hr_recovery_1min": return "arrow.down.heart.fill"
        default: return "chart.xyaxis.line"
        }
    }

    var family: MP.Category { group.family }

    /// Whether MedPull's own engine produces this signal.
    var isMeasured: Bool { MeasuredSignals.all.contains(key) }

    /// "Walking speed" rather than "Flexion": the Measure tab's name for the
    /// ROM signals says which joint movement they are.
    var displayLabel: String {
        switch key {
        case "rom_flexion": return "Bend"
        case "rom_extension": return "Straightening"
        case "rom_abduction": return "Arm lift"
        default: return label
        }
    }
}

extension PatientMetric {
    /// SF Symbol per metric id.
    var symbol: String {
        switch id {
        case "M1": return "figure.walk"
        case "M2": return "bandage.fill"
        case "M3": return "figure.walk.motion"
        case "M4": return "gauge.with.needle"
        case "M5": return "timer"
        case "M6": return "chair"
        case "M7": return "speedometer"
        case "M8": return "stairs"
        case "M9": return "moon.fill"
        case "M10": return "waveform.path.ecg"
        case "M11": return "sun.horizon.fill"
        case "M12": return "heart.text.square.fill"
        case "M13": return "thermometer.medium"
        case "M14": return "checklist"
        case "M17": return "chart.line.uptrend.xyaxis"
        case "M18": return "arrow.triangle.branch"
        case "C1": return "scalemass.fill"
        case "C2": return "lungs.fill"
        case "C3": return "drop.fill"
        case "C4": return "heart.fill"
        case "C5": return "stethoscope"
        case "C6": return "chair"
        default: return "chart.xyaxis.line"
        }
    }

    var family: MP.Category {
        switch id {
        case "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "C6": return .teal
        case "M9", "M10", "M11", "M17", "M18": return .indigo
        case "M12", "M13", "C1", "C2", "C3", "C4", "C5": return .violet
        default: return .blue
        }
    }

    var tone: MP.Tone { MP.tone(forMetricState: state) }

    /// "Shows in 2 more days" / "Early read · firms up in 1 day" / nil.
    var countdown: String? {
        guard let text = daysLeftText else { return nil }
        if text.hasPrefix("early read") { return "Early read" + text.dropFirst("early read".count) }
        if text.hasPrefix("waiting") { return "Waiting on new data" }
        return "Shows in \(text)"
    }
}

/// What the Measure tab says about each test: when it was last done, from
/// the portfolio, and whether it is due.
struct MeasureStatus {
    let flow: MeasureFlow
    /// The latest reading of the test's headline signal, if any.
    let latest: PortfolioMetric?
    let lastDate: String?
    let daysSince: Int?

    /// How often the care plan expects it: the six-minute walk weekly, a
    /// joint test every three days, a guided walk every other day.
    var cadenceDays: Int {
        switch flow {
        case .guidedWalk: return 2
        case .sixMinuteWalk: return 7
        case .rangeOfMotion: return 3
        }
    }

    var isDue: Bool {
        guard let daysSince else { return true }
        return daysSince >= cadenceDays
    }

    /// "Due today", "Due in 2 days", "Not done yet".
    var dueLabel: String {
        guard let daysSince else { return "Not done yet" }
        let left = cadenceDays - daysSince
        if left <= 0 { return "Due today" }
        return left == 1 ? "Due tomorrow" : "Due in \(left) days"
    }

    /// "412 m · 8 days ago" or nil.
    var lastLine: String? {
        guard let latest, let lastDate else { return nil }
        let value = latest.hideUnit ? latest.latestText : "\(latest.latestText) \(latest.unit)"
        return "\(value)\(MP.dot)\(Dates.agoWords(lastDate))"
    }

    static func status(for flow: MeasureFlow, in portfolio: [PortfolioMetric]) -> MeasureStatus {
        let keys: [String]
        switch flow {
        case .guidedWalk: keys = ["cadence", "walking_steadiness", "step_length", "walking_speed"]
        case .sixMinuteWalk: keys = MeasuredSignals.sixMinuteWalk
        case .rangeOfMotion: keys = MeasuredSignals.rangeOfMotion
        }
        // The most recently measured of the test's signals decides "last".
        let candidates = keys.compactMap { k in portfolio.first { $0.key == k } }
        let newest = candidates.max { ($0.latest.day) < ($1.latest.day) }
        let headline = keys.compactMap { k in candidates.first { $0.key == k } }.first ?? newest
        return MeasureStatus(flow: flow,
                             latest: flow == .guidedWalk ? headline : newest,
                             lastDate: newest?.latest.date,
                             daysSince: newest.flatMap { Dates.daysAgo($0.latest.date) })
    }
}
