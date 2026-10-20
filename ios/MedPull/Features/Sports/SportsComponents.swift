import Charts
import SwiftUI

/// The pieces the sports screens share: an availability pill, a benchmark
/// bar, a left-right symmetry bar, a phase stepper, a criterion row, an
/// evidence grade, a suggestion card and a schedule row. All in the
/// medpull.org language; nothing here invents a colour or a size.

enum SportsCopy {
    static let guardrail = "Performance and recovery guidance — return-to-play is your medical staff's call."
}

struct SportsGuardrail: View {
    var body: some View {
        Text(SportsCopy.guardrail)
            .mpFont(.label).foregroundStyle(MP.muted).padding(.top, 4)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - Availability

struct AvailabilityPill: View {
    let status: String
    var body: some View {
        StatusPill(text: Availability.label(status), tone: Availability.tone(status))
    }
}

// MARK: - Evidence grade

/// The grade behind a suggestion: A (consensus or meta-analysis), B (cohort
/// or small trial), C (expert convention). Words, not colour alone.
struct EvidencePill: View {
    let grade: String
    var body: some View {
        Text("Evidence \(grade)")
            .mpFont(.labelMedium)
            .foregroundStyle(grade == "A" ? MP.riskLow : grade == "B" ? MP.brandInk : MP.muted)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(MP.capsuleShape.fill(grade == "A" ? MP.riskLowBg : grade == "B" ? MP.brandTint : MP.soft))
    }
}

// MARK: - Benchmark bar

/// Where a value sits against the level: a track with the 25/50/75/90
/// marks and the athlete's dot. The word beside it carries the reading.
struct BenchmarkBar: View {
    let band: Benchmark
    var compact: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            GeometryReader { proxy in
                let w = proxy.size.width
                let x = w * CGFloat(min(max(band.percentile, 2), 98)) / 100
                ZStack(alignment: .leading) {
                    MP.capsuleShape.fill(MP.track)
                    MP.capsuleShape
                        .fill(LinearGradient(colors: [MP.chartSeq[1], MP.chartSeq[3]], startPoint: .leading, endPoint: .trailing))
                        .frame(width: x)
                    ForEach([25, 50, 75, 90], id: \.self) { p in
                        Rectangle().fill(MP.panel.opacity(0.9)).frame(width: 1.5)
                            .offset(x: w * CGFloat(p) / 100)
                    }
                    Circle().fill(MP.lime).frame(width: 10, height: 10)
                        .overlay(Circle().strokeBorder(MP.ink.opacity(0.25), lineWidth: 1))
                        .offset(x: x - 5)
                }
            }
            .frame(height: 8)
            if !compact {
                HStack {
                    Text("25th").mpFont(.label).foregroundStyle(MP.muted)
                    Spacer()
                    Text("50th").mpFont(.label).foregroundStyle(MP.muted)
                    Spacer()
                    Text("75th").mpFont(.label).foregroundStyle(MP.muted)
                    Spacer()
                    Text("90th").mpFont(.label).foregroundStyle(MP.muted)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("\(band.word), around the \(band.percentile)th percentile for the level"))
    }
}

// MARK: - Symmetry bar

/// Left against right: two bars from the centre, the weaker side shorter,
/// the percentage between them. For a sided test or a rehab measure.
struct SymmetryBar: View {
    let left: Double?
    let right: Double?
    var leftLabel = "Left"
    var rightLabel = "Right"
    var unit = ""
    var decimals = 0
    var higherIsBetter = true
    var flagPct: Double? = nil

    private var pct: Double? {
        guard let left, let right, left > 0, right > 0 else { return nil }
        let a = max(left, right), b = min(left, right)
        return (a - b) / a * 100
    }

    private var weakerIsLeft: Bool {
        guard let left, let right else { return false }
        return higherIsBetter ? left < right : left > right
    }

    var body: some View {
        let top = max(left ?? 0, right ?? 0, 0.0001)
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(leftLabel).mpFont(.label).foregroundStyle(MP.muted).frame(width: 64, alignment: .leading)
                GeometryReader { proxy in
                    let half = proxy.size.width / 2
                    ZStack {
                        MP.capsuleShape.fill(MP.track)
                        HStack(spacing: 0) {
                            Spacer(minLength: 0)
                            MP.capsuleShape.fill(weakerIsLeft && flagged ? MP.riskMed : MP.brand)
                                .frame(width: half * CGFloat((left ?? 0) / top))
                            Rectangle().fill(MP.panel).frame(width: 2)
                            MP.capsuleShape.fill(!weakerIsLeft && flagged ? MP.riskMed : MP.brand)
                                .frame(width: half * CGFloat((right ?? 0) / top))
                            Spacer(minLength: 0)
                        }
                    }
                }
                .frame(height: 10)
                Text(rightLabel).mpFont(.label).foregroundStyle(MP.muted).frame(width: 64, alignment: .trailing)
            }
            HStack {
                Text(left.map { fmt($0) } ?? "—").font(.figuresCopy).foregroundStyle(MP.ink)
                Spacer()
                if let pct {
                    Text(String(format: "%.0f%% apart", pct))
                        .mpFont(.labelMedium).foregroundStyle(flagged ? MP.riskMed : MP.muted)
                } else {
                    Text("Log both sides").mpFont(.label).foregroundStyle(MP.muted)
                }
                Spacer()
                Text(right.map { fmt($0) } ?? "—").font(.figuresCopy).foregroundStyle(MP.ink)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var flagged: Bool {
        guard let pct, let flagPct else { return false }
        return pct >= flagPct
    }

    private func fmt(_ v: Double) -> String {
        let s = decimals == 0 ? String(format: "%.0f", v) : String(format: "%.\(decimals)f", v)
        return unit.isEmpty ? s : "\(s) \(unit)"
    }
}

// MARK: - Phase stepper

/// The phases of a return: done in sage, the current one long, the rest
/// quiet. The word under it names the current phase.
struct PhaseStepper: View {
    let phases: [RehabPhase]
    let current: Int
    var total: Int? = nil
    /// The "Phase n of m · name · window" line under the bars; off when the
    /// card above already says it.
    var showsCaption: Bool = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var count: Int { max(total ?? 0, phases.count, current) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 5) {
                ForEach(1...max(count, 1), id: \.self) { n in
                    MP.capsuleShape
                        .fill(n < current ? MP.stateFill : n == current ? MP.ink : MP.track)
                        .frame(height: 8)
                        .frame(maxWidth: n == current ? .infinity : nil)
                        .frame(minWidth: n == current ? 48 : 22)
                }
            }
            .animation(MPMotion.gated(MPMotion.layout, reduceMotion: reduceMotion), value: current)
            if showsCaption, let p = phases.first(where: { $0.number == current }) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text("Phase \(p.number) of \(count)").mpFont(.labelMedium).foregroundStyle(MP.muted)
                    Text(MP.dotLead + p.name).mpFont(.label).foregroundStyle(MP.body)
                    Spacer()
                    Text(p.window).mpFont(.label).foregroundStyle(MP.muted)
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text("Phase \(current) of \(count)"))
    }
}

// MARK: - Criterion row

/// One gate: a check, the label, the value against the target.
struct CriterionRow: View {
    let criterion: Criterion

    private var symbol: String {
        switch criterion.met {
        case .some(true): return "checkmark.circle.fill"
        case .some(false): return "circle"
        case .none: return "questionmark.circle"
        }
    }

    private var color: Color {
        switch criterion.met {
        case .some(true): return MP.riskLow
        case .some(false): return MP.lineStrong
        case .none: return MP.faint
        }
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: symbol)
                .font(.systemGlyphs(18, weight: .regular))
                .foregroundStyle(color)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(criterion.label).mpFont(.copy).foregroundStyle(MP.ink)
                    .strikethrough(false)
                    .fixedSize(horizontal: false, vertical: true)
                if let note = criterion.note {
                    Text(note.capitalized).mpFont(.label).foregroundStyle(MP.muted)
                }
            }
            Spacer(minLength: 8)
            Text(criterion.valueText ?? "—")
                .font(.figuresCopy)
                .foregroundStyle(criterion.met == true ? MP.riskLow : criterion.met == false ? MP.ink : MP.muted)
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
        .accessibilityValue(Text(criterion.met == true ? "met" : criterion.met == false ? "not yet" : "not measured"))
    }
}

// MARK: - Suggestion card

struct SuggestionCard: View {
    let suggestion: Suggestion
    var expanded: Bool = true

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .top, spacing: 12) {
                    Glyph(systemName: suggestion.symbol, family: suggestion.family, size: 36)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(suggestion.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(suggestion.why.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 0)
                }
                if expanded {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(suggestion.actions.enumerated()), id: \.offset) { _, line in
                            HStack(alignment: .top, spacing: 8) {
                                LimeDot(size: 6).padding(.top, 7)
                                Text(line.typeset).mpFont(.copy).foregroundStyle(MP.ink)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    HStack(spacing: 8) {
                        EvidencePill(grade: suggestion.evidence)
                        if !suggestion.source.isEmpty {
                            Text(suggestion.source).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
                        }
                    }
                }
            }
        }
    }
}

// MARK: - Schedule row

struct EventRow: View {
    let event: SportsEvent
    var highlight = false

    var body: some View {
        HStack(spacing: 12) {
            VStack(spacing: 0) {
                Text(Dates.shortDay(event.date)).mpFont(.labelMedium).foregroundStyle(highlight ? MP.brandInk : MP.muted)
                Text(Dates.monthDay(event.date).components(separatedBy: " ").last ?? "")
                    .font(.figures(MPSize.lede, weight: .medium)).foregroundStyle(MP.ink)
            }
            .frame(width: 40)
            Glyph(systemName: event.symbol, family: event.isGame ? .blue : event.kind == "lift" ? .violet : .teal)
            VStack(alignment: .leading, spacing: 2) {
                Text(event.isGame ? (event.title + (event.opponent.map { " vs \($0)" } ?? "")) : event.title)
                    .mpFont(.copyLargeMedium).foregroundStyle(MP.ink).lineLimit(1)
                Text([event.home.map { $0 ? "Home" : "Away" }, event.startTime.map(SportsEvent.clock), event.location]
                    .compactMap { $0 }.joined(separator: MP.dot))
                    .mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
            }
            Spacer(minLength: 0)
            if highlight { StatusPill(text: "Today", tone: .brand) }
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Small stat

/// A label over a figure, for strips of three or four numbers.
struct Stat: View {
    let label: String
    let value: String
    var unit: String? = nil
    var tone: MP.Tone? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1).minimumScaleFactor(0.8)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(value).font(.figuresLede).foregroundStyle(tone.map { MP.foreground($0) } ?? MP.ink)
                    .lineLimit(1).minimumScaleFactor(0.7)
                if let unit, !unit.isEmpty {
                    Text(unit).mpFont(.label).foregroundStyle(MP.muted)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Trend text

enum TrendText {
    static func line(_ trend: TestTrend?, higherIsBetter: Bool) -> (String, Color)? {
        guard let trend else { return nil }
        let arrow = trend.pct >= 0 ? "+" : "−"
        let text = "\(arrow)\(String(format: "%.0f", abs(trend.pct)))% vs earlier"
        guard let better = trend.better else { return (text, MP.muted) }
        return (text, better ? MP.riskLow : MP.riskMed)
    }
}

// MARK: - A chart of one test over time

struct TestSeriesChart: View {
    let points: [TestPoint]
    var second: [TestPoint] = []
    var secondLabel: String = "Other side"
    var unit: String = ""
    var reference: Double? = nil
    var height: CGFloat = 120

    var body: some View {
        Chart {
            if let reference {
                RuleMark(y: .value("Baseline", reference))
                    .foregroundStyle(MP.chartRefLine)
                    .lineStyle(StrokeStyle(lineWidth: 1.2, dash: [3, 5]))
            }
            ForEach(points) { p in
                LineMark(x: .value("Day", p.day, unit: .day), y: .value("Value", p.value), series: .value("S", "main"))
                    .foregroundStyle(MP.chartS1).interpolationMethod(.monotone)
                    .lineStyle(StrokeStyle(lineWidth: 2.2, lineCap: .round))
                PointMark(x: .value("Day", p.day, unit: .day), y: .value("Value", p.value))
                    .foregroundStyle(p.id == points.last?.id ? MP.lime : MP.chartS1)
                    .symbolSize(p.id == points.last?.id ? 70 : 18)
            }
            ForEach(second) { p in
                LineMark(x: .value("Day", p.day, unit: .day), y: .value(secondLabel, p.value), series: .value("S", "second"))
                    .foregroundStyle(MP.chartS2).interpolationMethod(.monotone)
                    .lineStyle(StrokeStyle(lineWidth: 2, dash: [4, 4]))
            }
        }
        .chartYScale(domain: .automatic(includesZero: false))
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                AxisValueLabel(format: .dateTime.month(.abbreviated).day()).font(.axis).foregroundStyle(MP.chartAxisLabel)
            }
        }
        .chartYAxis {
            AxisMarks(values: .automatic(desiredCount: 3)) { value in
                AxisGridLine().foregroundStyle(MP.chartGrid)
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(PanelChart.axisNumber(v)).font(.axis).foregroundStyle(MP.chartAxisLabel)
                    }
                }
            }
        }
        .frame(height: height)
    }
}

// MARK: - Loading and empty

struct LoadingCard: View {
    var text = "Reading your signals…"
    var body: some View {
        Card {
            HStack(spacing: 14) {
                ProgressView().tint(MP.brand)
                Text(text).mpFont(.copyLarge).foregroundStyle(MP.body)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

/// A 0–10 slider row for the wellness questions: label, the anchors, the
/// figure. Compact enough to stack six of them.
struct ScaleRow: View {
    let spec: WellnessSpec
    @Binding var value: Double?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                HStack(spacing: 8) {
                    Image(systemName: spec.symbol).font(.systemGlyphs(14, weight: .medium)).foregroundStyle(MP.brandInk)
                        .accessibilityHidden(true)
                    Text(spec.prompt).mpFont(.copyMedium).foregroundStyle(MP.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 8)
                Text(value.map { String(format: "%.0f", $0) } ?? "—")
                    .font(.figuresSubhead).foregroundStyle(value == nil ? MP.muted : MP.ink)
                    .frame(minWidth: 28, alignment: .trailing)
            }
            Slider(value: Binding(get: { value ?? 5 }, set: { value = $0.rounded() }), in: 0...10, step: 1)
                .tint(value == nil ? MP.track : MP.brand)
                .accessibilityLabel(Text(spec.label))
                .accessibilityValue(Text(value.map { String(format: "%.0f", $0) } ?? "Not answered"))
            HStack {
                Text(spec.low).mpFont(.label).foregroundStyle(MP.muted)
                Spacer()
                Text(spec.high).mpFont(.label).foregroundStyle(MP.muted)
            }
        }
        .padding(.vertical, 6)
    }
}

/// Chips that wrap onto as many rows as they need: the same contract as
/// `FlowChips`, for the long lists (session kinds, levels, positions).
struct WrapChips: View {
    let options: [String]
    let labels: [String: String]
    @Binding var value: AnswerValue?

    var body: some View {
        BrandFlow(spacing: 8) {
            ForEach(options, id: \.self) { opt in
                Chip(label: labels[opt] ?? opt.capitalized, selected: value == .string(opt)) {
                    value = (value == .string(opt)) ? nil : .string(opt)
                }
            }
        }
    }
}

extension String {
    /// "3 days ago" -> "3 days ago", "today" -> "Today": only the first letter.
    var sentenceCased: String {
        guard let first = first else { return self }
        return first.uppercased() + dropFirst()
    }
}
