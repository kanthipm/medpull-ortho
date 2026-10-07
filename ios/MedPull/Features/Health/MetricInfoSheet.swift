import Charts
import SwiftUI

/// The "i" behind every metric: what it is, why it matters, what helps it
/// show, and how far along its data is. Served word for word by the server
/// (`explain` on each metric), so the app never invents a clinical line.
///
/// Contrast: labels are `muted` on the sheet's canvas (5.025 / 5.243),
/// bodies `ink`; the state pill carries its own tint. Nothing here is
/// `faint`, which carries no text.
struct MetricInfoSheet: View {
    let title: String
    let state: String
    let stateLabel: String
    let headline: String
    let readiness: MetricReadiness?
    let daysLeftText: String?
    let explain: MetricExplain?
    @Environment(\.dismiss) private var dismiss

    init(metric m: PatientMetric) {
        title = m.title; state = m.state; stateLabel = m.stateLabel; headline = m.headline
        readiness = m.readiness; daysLeftText = m.daysLeftText; explain = m.explain
    }

    init(signal s: PatientSignal) {
        title = s.title; state = s.state; stateLabel = s.stateLabel; headline = s.headline
        readiness = s.readiness; daysLeftText = s.daysLeftText; explain = s.explain
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 10) {
                        StatusPill(text: stateLabel, tone: MP.tone(forMetricState: state))
                        Text(headline)
                            .mpFont(.copyLarge).foregroundStyle(MP.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        if let line = readiness?.sentence ?? daysLeftText.map(Self.countdownLine) {
                            Text(line)
                                .mpFont(.label).foregroundStyle(MP.muted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(.top, 4)

                    if let explain {
                        Card(padding: 0) {
                            VStack(alignment: .leading, spacing: 0) {
                                block("What it is", explain.what)
                                InsetDivider(leading: 16)
                                block("Why it matters", explain.why)
                                InsetDivider(leading: 16)
                                block("How to help it show", explain.help)
                            }
                        }
                    }

                    // Legal copy, so it is text: `muted` on canvas.
                    Text("Monitoring signals for your care team — not a diagnosis.")
                        .mpFont(.label).foregroundStyle(MP.muted)
                }
                .padding(.horizontal, 18).padding(.bottom, 24)
            }
            .screen()
            .mpNavigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }

    private func block(_ label: String, _ text: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).mpFont(.labelMedium).mpSecondary()
            Text(text).mpFont(.copy).foregroundStyle(MP.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16).padding(.vertical, 12)
        .accessibilityElement(children: .combine)
    }

    /// "2 more days" -> "Shows after 2 more days of data."
    static func countdownLine(_ text: String) -> String {
        if text.hasPrefix("early read") { return "An early read; it " + text.dropFirst("early read · ".count) + "." }
        if text.hasPrefix("waiting") { return "Waiting on new data from your watch or phone." }
        return "Shows after \(text) of data."
    }
}

/// A row in a metrics card: category tile, title + state pill, the headline,
/// a countdown when the metric is still collecting, and the "i" that opens
/// the sheet. The row combines for VoiceOver; the info button stays its own
/// element so it can be reached.
struct MetricRow: View {
    let metric: PatientMetric
    var onInfo: () -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var stacked: Bool { dynamicTypeSize.isAccessibilitySize }

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            IconTile(metric.symbol, family: metric.family)
            VStack(alignment: .leading, spacing: 4) {
                if stacked {
                    Text(metric.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    StatusPill(text: metric.stateLabel, tone: MP.tone(forMetricState: metric.state))
                } else {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(metric.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 4)
                        StatusPill(text: metric.stateLabel, tone: MP.tone(forMetricState: metric.state))
                    }
                }
                Text(metric.headline).mpFont(.label).mpSecondary()
                    .fixedSize(horizontal: false, vertical: true)
                if let left = metric.daysLeftText {
                    Text(MetricRow.caption(left))
                        .mpFont(.labelMedium)
                        .foregroundStyle(metric.isWaiting ? MP.muted : MP.riskMed)
                }
            }
            .accessibilityElement(children: .combine)
            Button(action: onInfo) {
                Image(systemName: "info.circle")
                    .font(.systemGlyphs(MPSize.copyLarge, weight: .regular))
                    .foregroundStyle(MP.brandInk)
                    .frame(width: 44, height: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("About \(metric.title)")
            .padding(.top, -8).padding(.trailing, -8)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 44)
    }

    /// "2 more days" -> "Shows in 2 more days"; "early read · firms up in 1
    /// day" -> "Early read · firms up in 1 day".
    static func caption(_ text: String) -> String {
        if text.hasPrefix("early read") { return "Early read" + text.dropFirst("early read".count) }
        if text.hasPrefix("waiting") { return "Waiting on new data" }
        return "Shows in \(text)"
    }
}

extension PatientMetric {
    /// SF Symbol per metric id; the family is the metric's category (hue
    /// names a category, never a state).
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
}

/// A metric's small chart on the Health tab: the series in ink on the warm
/// inset fill (bars for daily totals, a line otherwise), no axes — the card
/// already states the value and the sentence. A waiting metric shows its
/// countdown as the figure instead.
struct MetricMiniChart: View {
    let metric: PatientMetric

    var body: some View {
        Group {
            if metric.isWaiting {
                countdown
            } else if let chart = metric.chart, !chart.points.isEmpty {
                plot(chart)
            } else if let value = metric.value {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(value).font(.figuresDisplay(MPSize.displayS)).kerning(-0.9).foregroundStyle(MP.ink)
                    if let unit = metric.unit, !unit.isEmpty {
                        Text(unit).mpFont(.label).foregroundStyle(MP.muted)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MP.controlShape.fill(MP.fill))
        .padding(.horizontal, 16).padding(.bottom, 12)
        .accessibilityElement(children: .combine)
    }

    private var countdown: some View {
        let left = metric.readiness?.left ?? 0
        return HStack(alignment: .firstTextBaseline, spacing: 6) {
            if left > 0 {
                Text("\(left)").font(.figuresDisplay(MPSize.displayS)).kerning(-0.9).foregroundStyle(MP.ink)
                Text("more \(unitWord(left))").mpFont(.copy).foregroundStyle(MP.muted)
            } else {
                Text("Not showing yet").mpFont(.copyMedium).foregroundStyle(MP.muted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func unitWord(_ n: Int) -> String {
        let unit = metric.readiness?.unit ?? "days"
        return n == 1 && unit.hasSuffix("s") ? String(unit.dropLast()) : unit
    }

    private func plot(_ chart: PatientMetricChart) -> some View {
        let last = chart.points.last
        return Chart {
            ForEach(Array(chart.points.enumerated()), id: \.offset) { _, p in
                if chart.kind == "bars" {
                    BarMark(x: .value("Day", p.x), y: .value(metric.title, p.y))
                        .foregroundStyle(p == last ? MP.lime : MP.ink.opacity(0.75))
                        .cornerRadius(2)
                } else {
                    LineMark(x: .value("Day", p.x), y: .value(metric.title, p.y))
                        .foregroundStyle(MP.ink)
                        .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                        .interpolationMethod(.monotone)
                    if p == last {
                        PointMark(x: .value("Day", p.x), y: .value(metric.title, p.y))
                            .foregroundStyle(MP.lime)
                            .symbolSize(70)
                    }
                }
            }
        }
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartYScale(domain: .automatic(includesZero: chart.kind == "bars"))
        .frame(height: 72)
        .accessibilityLabel(Text("\(metric.title), \(chart.points.count) days"))
    }
}
