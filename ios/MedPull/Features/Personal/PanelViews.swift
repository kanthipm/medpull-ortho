import Charts
import SwiftUI

/// The pieces the personal screens are built from: a readiness ring, a
/// panel card with its chart, stat strip and method, a mini tile for the
/// home grid, and the verdict's look. The server owns every number and
/// every sentence; these draw them in the medpull.org language.

enum PersonalCopy {
    static let guardrail = "Guidance for training and recovery — not medical advice."
}

extension Verdict {
    var gradient: MPGradient {
        switch kind {
        case "push": return .sage
        case "steady": return .meadow
        case "easy": return .amber
        case "rest": return .clay
        default: return .lilac
        }
    }

    var tone: MP.Tone {
        switch kind {
        case "push": return .low
        case "steady": return .brand
        case "easy": return .med
        case "rest": return .high
        default: return .missing
        }
    }

    var symbol: String {
        switch kind {
        case "push": return "bolt.fill"
        case "steady": return "equal.circle.fill"
        case "easy": return "tortoise.fill"
        case "rest": return "bed.double.fill"
        default: return "hourglass"
        }
    }
}

extension Panel {
    var symbol: String {
        switch key {
        case "readiness": return "gauge.with.dots.needle.67percent"
        case "hrv": return "waveform.path.ecg"
        case "resting_hr": return "heart.fill"
        case "sleep": return "bed.double.fill"
        case "load": return "flame.fill"
        case "fitness": return "lungs.fill"
        case "body": return "thermometer.medium"
        case "activity": return "figure.walk"
        case "rhythm": return "clock.fill"
        case "subjective": return "face.smiling"
        default: return "chart.xyaxis.line"
        }
    }

    /// Hue is the category, never the state: recovery signals clay, sleep
    /// and rhythm lilac, training sage, the rest amber.
    var family: MP.Category {
        switch key {
        case "hrv", "resting_hr", "body", "fitness": return .violet
        case "sleep", "rhythm": return .indigo
        case "load", "activity", "readiness": return .teal
        default: return .blue
        }
    }

    var isBar: Bool { key == "load" || key == "activity" }

    var confidenceLabel: String {
        switch confidence {
        case "high": return "High confidence"
        case "med": return "Fair confidence"
        default: return "Low confidence"
        }
    }

    /// The dashed reference for the chart: the person's own baseline, where
    /// the panel has one.
    var reference: Double? { number("baseline_mean") }
}

// MARK: - Readiness ring

/// The score as a ring: the arc is the score out of 100 in the band's
/// status colour, the number sits inside in the display face. Grey and
/// empty with no score.
struct ReadinessRing: View {
    let score: Double?
    let band: String?
    var size: CGFloat = 132
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var drawn = false

    private var color: Color {
        switch band {
        case "green": return MP.riskLow
        case "amber": return MP.riskMed
        case "red": return MP.riskHigh
        default: return MP.faint
        }
    }

    var body: some View {
        ZStack {
            Circle().stroke(MP.track, lineWidth: 10)
            if let score {
                Circle()
                    .trim(from: 0, to: drawn || reduceMotion ? CGFloat(score / 100) : 0)
                    .stroke(color, style: StrokeStyle(lineWidth: 10, lineCap: .round))
                    .rotationEffect(.degrees(-90))
            }
            VStack(spacing: 0) {
                Text(score.map { String(format: "%.0f", $0) } ?? "—")
                    .font(.figuresDisplay(size * 0.33))
                    .kerning(-size * 0.012)
                    .foregroundStyle(MP.ink)
                    .lineLimit(1).minimumScaleFactor(0.6)
                Text("readiness").mpFont(.label).foregroundStyle(MP.muted)
            }
        }
        .frame(width: size, height: size)
        .onAppear {
            guard !drawn else { return }
            withAnimation(MPMotion.ease(1.0).delay(0.1)) { drawn = true }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Readiness"))
        .accessibilityValue(Text(score.map { String(format: "%.0f out of 100", $0) } ?? "no score yet"))
    }
}

// MARK: - Charts

/// One panel's 28 days: bars for a daily total, a line for a nightly
/// reading, the personal baseline dashed, and for HRV the smallest
/// worthwhile change band. Ink on the card, so it reads in both modes.
struct PanelChart: View {
    let panel: Panel
    var height: CGFloat = 112
    @State private var picked: Date?

    private var lastID: String? { panel.series.last?.id }

    private var pickedPoint: PanelPoint? {
        guard let picked else { return nil }
        let cal = Calendar.current
        return panel.series.first { cal.isDate($0.day, inSameDayAs: picked) }
            ?? panel.series.min { abs($0.day.timeIntervalSince(picked)) < abs($1.day.timeIntervalSince(picked)) }
    }

    var body: some View {
        Chart {
            if panel.key == "hrv", let lo = panel.number("swc_low"), let hi = panel.number("swc_high") {
                RectangleMark(yStart: .value("Low", lo), yEnd: .value("High", hi))
                    .foregroundStyle(MP.brand.opacity(0.12))
                    .accessibilityHidden(true)
            }
            ForEach(panel.series) { pt in
                if panel.isBar {
                    BarMark(x: .value("Day", pt.day, unit: .day), y: .value(panel.title, pt.value))
                        .foregroundStyle(pt.id == lastID ? MP.brand : MP.chartS1.opacity(0.55))
                        .cornerRadius(3)
                        .opacity(pickedPoint == nil || pickedPoint?.id == pt.id ? 1 : 0.4)
                } else {
                    LineMark(x: .value("Day", pt.day, unit: .day), y: .value(panel.title, pt.value))
                        .foregroundStyle(MP.chartS1)
                        .lineStyle(StrokeStyle(lineWidth: 2.2, lineCap: .round, lineJoin: .round))
                        .interpolationMethod(.monotone)
                    PointMark(x: .value("Day", pt.day, unit: .day), y: .value(panel.title, pt.value))
                        .foregroundStyle(pt.id == lastID ? MP.lime : MP.chartS1)
                        .symbolSize(pt.id == lastID ? 70 : (pickedPoint?.id == pt.id ? 50 : 12))
                }
            }
            if let ref = panel.reference, pickedPoint == nil {
                RuleMark(y: .value("Baseline", ref))
                    .foregroundStyle(MP.chartRefLine)
                    .lineStyle(StrokeStyle(lineWidth: 1.2, dash: [3, 5]))
                    .accessibilityHidden(true)
            }
            if let p = pickedPoint {
                RuleMark(x: .value("Day", p.day, unit: .day))
                    .foregroundStyle(MP.lineStrong)
                    .lineStyle(StrokeStyle(lineWidth: 1))
                    .zIndex(-1)
                    .annotation(position: .top, spacing: 4,
                                overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        HStack(spacing: 4) {
                            Text(Self.format(p.value, panel: panel))
                                .font(.figures(MPSize.copy, weight: .medium)).foregroundStyle(MP.ink)
                            Text(p.day.formatted(.dateTime.month(.abbreviated).day()))
                                .font(.figuresLabel).foregroundStyle(MP.body)
                        }
                        .padding(.horizontal, 9).padding(.vertical, 5)
                        .background(MP.panel, in: MP.capsuleShape)
                        .overlay(MP.capsuleShape.strokeBorder(MP.line, lineWidth: 1))
                    }
                    .accessibilityHidden(true)
            }
        }
        .chartXSelection(value: $picked)
        .chartYScale(domain: .automatic(includesZero: panel.isBar))
        .chartXAxis(.hidden)
        .chartYAxis {
            AxisMarks(values: .automatic(desiredCount: 3)) { value in
                AxisGridLine().foregroundStyle(MP.chartGrid)
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(Self.axis(v, panel: panel)).font(.axis).foregroundStyle(MP.chartAxisLabel)
                    }
                }
            }
        }
        .frame(height: height)
        .mpSelectionFeedback(pickedPoint?.id)
    }

    static func format(_ v: Double, panel: Panel) -> String {
        if panel.key == "sleep" {
            let minutes = Int((v * 60).rounded())
            return "\(minutes / 60) h \(String(format: "%02d", minutes % 60))"
        }
        if v == v.rounded() || abs(v) >= 100 { return Int(v.rounded()).formatted() }
        return v.formatted(.number.precision(.fractionLength(1)))
    }

    static func axis(_ v: Double, panel: Panel) -> String {
        if panel.key == "sleep" { return "\(Int(v.rounded()))h" }
        if abs(v) >= 1000 { return "\(Int((v / 1000).rounded()))k" }
        return v == v.rounded() ? Int(v).formatted() : v.formatted(.number.precision(.fractionLength(1)))
    }

    /// A plain number for a trend readout: whole above 100, one decimal below.
    static func axisNumber(_ v: Double) -> String {
        if abs(v) >= 100 { return Int(v.rounded()).formatted() }
        return v == v.rounded() ? Int(v).formatted() : v.formatted(.number.precision(.fractionLength(1)))
    }
}

/// Fitness, fatigue and form over 28 days (Banister), for the load panel.
struct FormChart: View {
    let points: [JSONValue]
    var height: CGFloat = 112

    private struct Row: Identifiable {
        let id: String
        let day: Date
        let fitness: Double
        let fatigue: Double
        let form: Double
    }

    private var rows: [Row] {
        points.compactMap { p in
            guard let d = p["date"]?.string, let day = Dates.parse(d),
                  let fit = p["fitness"]?.number, let fat = p["fatigue"]?.number,
                  let form = p["form"]?.number else { return nil }
            return Row(id: d, day: day, fitness: fit, fatigue: fat, form: form)
        }
    }

    var body: some View {
        let data = rows
        if data.count >= 3 {
            VStack(alignment: .leading, spacing: 6) {
                Chart {
                    ForEach(data) { r in
                        LineMark(x: .value("Day", r.day, unit: .day), y: .value("Fitness", r.fitness),
                                 series: .value("Series", "Fitness"))
                            .foregroundStyle(MP.chartS1)
                            .lineStyle(StrokeStyle(lineWidth: 2))
                            .interpolationMethod(.monotone)
                        LineMark(x: .value("Day", r.day, unit: .day), y: .value("Fatigue", r.fatigue),
                                 series: .value("Series", "Fatigue"))
                            .foregroundStyle(MP.chartS2)
                            .lineStyle(StrokeStyle(lineWidth: 2, dash: [4, 4]))
                            .interpolationMethod(.monotone)
                    }
                }
                .chartXAxis(.hidden)
                .chartYAxis {
                    AxisMarks(values: .automatic(desiredCount: 3)) { _ in
                        AxisGridLine().foregroundStyle(MP.chartGrid)
                        AxisValueLabel().font(.axis).foregroundStyle(MP.chartAxisLabel)
                    }
                }
                .frame(height: height)
                HStack(spacing: 14) {
                    legend("Fitness", MP.chartS1, dashed: false)
                    legend("Fatigue", MP.chartS2, dashed: true)
                    Spacer()
                }
            }
        }
    }

    private func legend(_ label: String, _ color: Color, dashed: Bool) -> some View {
        HStack(spacing: 6) {
            Rectangle().fill(color).frame(width: 14, height: 2)
                .overlay { if dashed { Rectangle().fill(MP.panel).frame(width: 4, height: 2) } }
            Text(label).mpFont(.label).foregroundStyle(MP.muted)
        }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Stat strip

/// The numbers under a chart: label in 12 muted, value in figures.
struct StatStrip: View {
    let stats: [PanelStat]
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let columns = dynamicTypeSize.isAccessibilitySize
            ? [GridItem(.flexible(), alignment: .leading)]
            : [GridItem(.flexible(), alignment: .leading), GridItem(.flexible(), alignment: .leading),
               GridItem(.flexible(), alignment: .leading)]
        LazyVGrid(columns: columns, alignment: .leading, spacing: 10) {
            ForEach(stats) { s in
                VStack(alignment: .leading, spacing: 1) {
                    Text(s.label).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
                    HStack(alignment: .firstTextBaseline, spacing: 3) {
                        Text(s.value).font(.figuresLede).foregroundStyle(MP.ink)
                            .lineLimit(1).minimumScaleFactor(0.7)
                        if !s.unit.isEmpty {
                            Text(s.unit).mpFont(.label).foregroundStyle(MP.muted)
                        }
                    }
                }
                .accessibilityElement(children: .combine)
            }
        }
    }
}

// MARK: - Panel card

/// One readout as a card: tile, title and state; the headline figure and
/// its line; the chart; the stats; the finding; and, folded away, how it
/// was computed with its confidence and coverage.
struct PanelCard: View {
    let panel: Panel
    var showChart: Bool = true
    /// Closed, the card is one row: tile, title, figure, state, and two
    /// lines of the finding. Open, everything. Nil means always open.
    var expanded: Binding<Bool>? = nil
    @State private var showMethod = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var isOpen: Bool { expanded?.wrappedValue ?? true }

    var body: some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                header
                if isOpen {
                    if panel.hasData {
                        figure
                        if showChart { chart.padding(.horizontal, 16).padding(.top, 10) }
                        if !panel.stats.isEmpty {
                            StatStrip(stats: panel.stats).padding(.horizontal, 16).padding(.top, 12)
                        }
                    }
                    Text(panel.finding.typeset)
                        .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16).padding(.top, 12)
                    method
                } else {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(panel.statusText).mpFont(.labelMedium).foregroundStyle(MP.foreground(panel.tone))
                        Text(panel.finding.typeset)
                            .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                            .lineLimit(2)
                    }
                    .padding(.horizontal, 16).padding(.top, 8)
                }
            }
            .padding(.bottom, 14)
        }
        .clipShape(MP.surfaceShape)
        .accessibilityElement(children: .contain)
        .animation(MPMotion.gated(MPMotion.layout, reduceMotion: reduceMotion), value: isOpen)
    }

    private var header: some View {
        let stacked = dynamicTypeSize.isAccessibilitySize
        let compactFigure = !isOpen && panel.hasData && panel.key != "readiness"
        return Button {
            guard let expanded else { return }
            expanded.wrappedValue.toggle()
        } label: {
            Group {
                if stacked {
                    VStack(alignment: .leading, spacing: 8) {
                        IconTile(panel.symbol, family: panel.family)
                        Text(panel.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        if compactFigure { compactValue }
                        StatusPill(text: panel.statusText, tone: panel.tone)
                    }
                } else {
                    HStack(spacing: 12) {
                        IconTile(panel.symbol, family: panel.family)
                        Text(panel.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            .lineLimit(isOpen ? 2 : 1).minimumScaleFactor(0.8)
                            .accessibilityAddTraits(.isHeader)
                        Spacer(minLength: 8)
                        if compactFigure { compactValue }
                        if isOpen {
                            StatusPill(text: panel.statusText, tone: panel.tone)
                        } else {
                            Circle().fill(MP.foreground(panel.tone)).frame(width: 8, height: 8)
                                .accessibilityLabel(Text(panel.statusText))
                        }
                        if expanded != nil {
                            Image(systemName: "chevron.down")
                                .font(.systemGlyphs(12, weight: .semibold))
                                .foregroundStyle(MP.muted)
                                .rotationEffect(.degrees(isOpen ? 180 : 0))
                                .accessibilityHidden(true)
                        }
                    }
                }
            }
            .padding(.horizontal, 16).padding(.top, 14)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(expanded == nil)
        .accessibilityHint(expanded == nil ? Text("") : Text(isOpen ? "Collapse" : "Expand"))
    }

    private var compactValue: some View {
        HStack(alignment: .firstTextBaseline, spacing: 2) {
            Text(panel.key == "readiness" ? String(format: "%.0f", panel.number("score") ?? 0) : panel.headline)
                .font(.figuresCopyLarge).foregroundStyle(MP.ink).lineLimit(1).minimumScaleFactor(0.7)
            if !panel.unit.isEmpty {
                Text(panel.unit).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
            }
        }
    }

    @ViewBuilder private var figure: some View {
        if panel.key == "readiness" {
            HStack(alignment: .center, spacing: 18) {
                ReadinessRing(score: panel.number("score"), band: panel.string("band"), size: 118)
                componentBars
            }
            .padding(.horizontal, 16).padding(.top, 12)
        } else {
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Text(panel.headline)
                    .font(.figuresDisplay(MPSize.displayM)).kerning(-1.4).foregroundStyle(MP.ink)
                    .lineLimit(1).minimumScaleFactor(0.6)
                    .contentTransition(reduceMotion ? .identity : .numericText())
                if !panel.unit.isEmpty {
                    Text(panel.unit).mpFont(.copyMedium).foregroundStyle(MP.muted)
                }
                Spacer(minLength: 8)
                Text(panel.sub).mpFont(.label).foregroundStyle(MP.muted)
                    .multilineTextAlignment(.trailing)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 16).padding(.top, 10)
        }
    }

    /// Readiness: what pulled the score up or down, as signed bars.
    private var componentBars: some View {
        VStack(alignment: .leading, spacing: 7) {
            ForEach(Array(panel.array("components").enumerated()), id: \.offset) { _, c in
                if let label = c["label"]?.string {
                    let z = c["z"]?.number
                    HStack(spacing: 8) {
                        Text(label).mpFont(.label).foregroundStyle(MP.body)
                            .frame(width: 92, alignment: .leading).lineLimit(1)
                        GeometryReader { proxy in
                            let mid = proxy.size.width / 2
                            ZStack(alignment: .leading) {
                                MP.capsuleShape.fill(MP.track)
                                Rectangle().fill(MP.lineStrong).frame(width: 1).offset(x: mid)
                                if let z {
                                    let w = min(mid, abs(CGFloat(z)) / 3 * mid)
                                    MP.capsuleShape
                                        .fill(z >= 0 ? MP.riskLow : MP.riskHigh)
                                        .frame(width: max(3, w))
                                        .offset(x: z >= 0 ? mid : mid - w)
                                }
                            }
                        }
                        .frame(height: 8)
                        Text(c["value"]?.string ?? "—").font(.figuresLabel).foregroundStyle(MP.muted)
                            .frame(width: 58, alignment: .trailing).lineLimit(1).minimumScaleFactor(0.7)
                    }
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(Text(label))
                    .accessibilityValue(Text(z.map { String(format: "%.1f standard deviations", $0) } ?? "no reading"))
                }
            }
        }
    }

    @ViewBuilder private var chart: some View {
        switch panel.key {
        case "load":
            PanelChart(panel: panel)
            FormChart(points: panel.array("form_series")).padding(.top, 8)
        case "body":
            bodySignals
        case "readiness", "subjective", "rhythm":
            if !panel.series.isEmpty { PanelChart(panel: panel) }
        default:
            if !panel.series.isEmpty { PanelChart(panel: panel) }
        }
    }

    /// Body signals: each with its latest reading against its baseline.
    private var bodySignals: some View {
        VStack(spacing: 0) {
            ForEach(Array(panel.array("signals").enumerated()), id: \.offset) { i, s in
                if let label = s["label"]?.string, let latest = s["latest"]?.number {
                    let unit = s["unit"]?.string ?? ""
                    let base = s["baseline"]?.number
                    let z = s["z"]?.number
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text(label).mpFont(.copy).foregroundStyle(MP.ink)
                        Spacer()
                        Text("\(latest.formatted(.number.precision(.fractionLength(unit == "°C" ? 2 : 1)))) \(unit)")
                            .font(.figuresCopyLarge).foregroundStyle(MP.ink)
                        if let base {
                            Text("vs \(base.formatted(.number.precision(.fractionLength(1))))")
                                .mpFont(.label).foregroundStyle(MP.muted)
                        }
                        if let z {
                            StatusPill(text: String(format: "%+.1f SD", z),
                                       tone: abs(z) >= 2 ? .high : abs(z) >= 1 ? .med : .low)
                        }
                    }
                    .padding(.vertical, 8)
                    if i < panel.array("signals").count - 1 { InsetDivider(leading: 0) }
                }
            }
        }
    }

    private var method: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                withAnimation(MPMotion.gated(MPMotion.layout, reduceMotion: reduceMotion)) {
                    showMethod.toggle()
                }
            } label: {
                HStack(spacing: 6) {
                    Text("How this is computed")
                    Image(systemName: "chevron.down")
                        .font(.systemGlyphs(11, weight: .semibold))
                        .rotationEffect(.degrees(showMethod ? 180 : 0))
                }
                .mpFont(.labelMedium)
            }
            .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
            .padding(.horizontal, 16)
            if showMethod {
                VStack(alignment: .leading, spacing: 6) {
                    Text(panel.method.typeset).mpFont(.label).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("\(panel.confidenceLabel)\(MP.dot)\(panel.coverage)")
                        .mpFont(.label).foregroundStyle(MP.muted)
                }
                .padding(.horizontal, 16)
                .transition(.opacity)
            }
        }
        .padding(.top, 8)
    }
}

// MARK: - Mini tile

/// A readout in the home grid: glyph and state on top, the figure in big
/// light numbers, the name under it, on the warm inset fill.
struct MiniStatTile: View {
    let panel: Panel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center, spacing: 6) {
                IconTile(panel.symbol, family: panel.family, size: 22)
                Spacer(minLength: 4)
                Circle().fill(MP.foreground(panel.tone)).frame(width: 7, height: 7)
                    .accessibilityHidden(true)
            }
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(panel.hasData ? panel.headline : "—")
                    .font(.figuresDisplay(MPSize.displayS)).kerning(-0.9).foregroundStyle(MP.ink)
                    .lineLimit(1).minimumScaleFactor(0.6)
                    .contentTransition(reduceMotion ? .identity : .numericText())
                if panel.hasData, !panel.unit.isEmpty {
                    Text(panel.unit).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
                }
            }
            Text(panel.title).mpFont(.labelMedium).foregroundStyle(MP.muted).lineLimit(1)
            Text(panel.statusText).mpFont(.label).foregroundStyle(MP.foreground(panel.tone))
                .lineLimit(1).minimumScaleFactor(0.8)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MP.controlShape.fill(MP.fill))
        .accessibilityElement(children: .combine)
    }
}

/// The guardrail line under every personal screen: text, so `muted`.
struct PersonalGuardrail: View {
    var body: some View {
        Text(PersonalCopy.guardrail)
            .mpFont(.label).foregroundStyle(MP.muted).padding(.top, 4)
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// A whole card as a button: the gated 0.97 press scale, nothing else.
struct CardTapStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .contentShape(MP.surfaceShape)
            .scaleEffect(MPMotion.pressScale(configuration.isPressed, reduceMotion: reduceMotion))
            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion),
                       value: configuration.isPressed)
    }
}
