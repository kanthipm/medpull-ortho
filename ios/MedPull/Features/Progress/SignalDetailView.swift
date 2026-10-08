import Charts
import SwiftUI

/// One signal in full: the latest reading, its state in the care team's
/// words, the two-week chart you can scrub, the numbers behind it, and the
/// explanation the server wrote for it. Everything in ink on a card: a
/// clinical number never sits on a gradient.
struct SignalDetailView: View {
    let metric: PortfolioMetric
    var signal: PatientSignal? = nil
    @State private var picked: Date?
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var pickedPoint: PortfolioPoint? {
        guard let picked else { return nil }
        let cal = Calendar.current
        return metric.series.first { cal.isDate($0.day, inSameDayAs: picked) }
            ?? metric.series.min { abs($0.day.timeIntervalSince(picked)) < abs($1.day.timeIntervalSince(picked)) }
    }

    private var shown: PortfolioPoint { pickedPoint ?? metric.latest }

    private var range: String? {
        guard let first = metric.series.first?.day, let last = metric.series.last?.day,
              first != .distantPast else { return nil }
        let f = Date.FormatStyle.dateTime.month(.abbreviated).day()
        return "\(first.formatted(f)) – \(last.formatted(f))"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                headline
                Card(padding: 0) {
                    VStack(alignment: .leading, spacing: 0) {
                        SeriesChart(metric: metric, picked: $picked)
                            .padding(.horizontal, 12).padding(.top, 16)
                        stats
                    }
                }
                if let signal, let explain = signal.explain {
                    explainCard(explain, readiness: signal.readiness, countdown: signal.daysLeftText)
                }
                if metric.isMeasured {
                    Text("Measured by MedPull from your phone’s motion sensors, the same way for every patient, so week-to-week changes are yours and not the device’s.")
                        .mpFont(.label).foregroundStyle(MP.muted)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 4)
                }
                Text("Monitoring signals for your care team — not a diagnosis.")
                    .mpFont(.label).foregroundStyle(MP.muted).padding(.horizontal, 4)
            }
            .padding(.horizontal, 18).padding(.top, 4).padding(.bottom, 28)
        }
        .mpHardScrollEdge()
        .ambientScreen(height: 300)
        .navigationTitle(metric.displayLabel)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var headline: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                if metric.hideUnit {
                    BigFigure(value: metric.text(for: shown.value))
                } else {
                    BigFigure(value: metric.text(for: shown.value), unit: metric.unit)
                }
                Spacer(minLength: 8)
                Text(pickedPoint == nil ? "Latest\(MP.dot)\(Dates.monthDay(shown.date))" : Dates.monthDay(shown.date))
                    .font(.figuresLabel).foregroundStyle(MP.muted)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(Text("\(metric.displayLabel), \(metric.spokenText(for: shown.value)), \(Dates.monthDay(shown.date))"))
            if let signal, signal.state != "waiting" {
                VStack(alignment: .leading, spacing: 6) {
                    StatusPill(text: signal.stateLabel, tone: MP.tone(forMetricState: signal.state))
                    Text(signal.headline.typeset)
                        .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else if let signal, let c = signal.daysLeftText {
                Text(c.hasPrefix("waiting") ? "Waiting on new data from your watch or phone."
                     : "Your care team’s read on this shows after \(c) of data.")
                    .mpFont(.copy).foregroundStyle(MP.body)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 4)
    }

    private var stats: some View {
        let values = metric.series.map(\.value)
        let items: [(String, String)] = [
            ("Average", metric.average.map { metric.text(for: $0) } ?? "—"),
            ("Low", values.min().map { metric.text(for: $0) } ?? "—"),
            ("High", values.max().map { metric.text(for: $0) } ?? "—"),
            ("Days", "\(metric.daysWithData)"),
        ]
        let columns = dynamicTypeSize.isAccessibilitySize
            ? [GridItem(.flexible(), alignment: .leading), GridItem(.flexible(), alignment: .leading)]
            : Array(repeating: GridItem(.flexible(), alignment: .leading), count: 4)
        return VStack(alignment: .leading, spacing: 8) {
            LazyVGrid(columns: columns, alignment: .leading, spacing: 10) {
                ForEach(items, id: \.0) { label, value in
                    VStack(alignment: .leading, spacing: 1) {
                        Text(label).mpFont(.label).foregroundStyle(MP.muted)
                        Text(value).font(.figuresLede).foregroundStyle(MP.ink)
                            .lineLimit(1).minimumScaleFactor(0.7)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
            if let range {
                Text("\(range)\(MP.dot)last two weeks").mpFont(.label).foregroundStyle(MP.muted)
            }
        }
        .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 16)
    }

    private func explainCard(_ explain: MetricExplain, readiness: MetricReadiness?, countdown: String?) -> some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                ExplainBlock("What it is", explain.what)
                InsetDivider(leading: 16)
                ExplainBlock("Why it matters", explain.why)
                InsetDivider(leading: 16)
                ExplainBlock("How to help it show", explain.help)
                if let line = readiness?.sentence {
                    InsetDivider(leading: 16)
                    ExplainBlock("Where it stands", line)
                }
            }
            .padding(.vertical, 4)
        }
    }
}

/// A label and a paragraph, one block of an explanation card.
struct ExplainBlock: View {
    let label: String
    let text: String

    init(_ label: String, _ text: String) {
        self.label = label
        self.text = text
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).mpFont(.labelMedium).foregroundStyle(MP.muted)
            Text(text.typeset).mpFont(.copy).foregroundStyle(MP.ink).lineSpacing(2)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16).padding(.vertical, 12)
        .accessibilityElement(children: .combine)
    }
}

/// The two-week series in ink: bars for a daily total, a line for a
/// sampled reading; the newest mark in the brand fill; the average as a
/// dashed rule; a scrub shows any day's value on an opaque capsule.
struct SeriesChart: View {
    let metric: PortfolioMetric
    @Binding var picked: Date?
    var height: CGFloat = 160
    @State private var grown = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var isBar: Bool { metric.isDailyTotal }
    private var lastID: String? { metric.series.last?.id }

    private var pickedPoint: PortfolioPoint? {
        guard let picked else { return nil }
        let cal = Calendar.current
        return metric.series.first { cal.isDate($0.day, inSameDayAs: picked) }
            ?? metric.series.min { abs($0.day.timeIntervalSince(picked)) < abs($1.day.timeIntervalSince(picked)) }
    }

    var body: some View {
        Chart {
            ForEach(metric.series) { pt in
                if isBar {
                    BarMark(x: .value("Day", pt.day, unit: .day),
                            y: .value(metric.label, grown || reduceMotion ? pt.value : 0))
                        .foregroundStyle(pt.id == lastID ? MP.brand : MP.chartS1.opacity(0.5))
                        .cornerRadius(3)
                        .opacity(pickedPoint == nil || pickedPoint?.id == pt.id ? 1 : 0.4)
                } else {
                    LineMark(x: .value("Day", pt.day, unit: .day), y: .value(metric.label, pt.value))
                        .foregroundStyle(MP.chartS1)
                        .lineStyle(StrokeStyle(lineWidth: 2.2, lineCap: .round, lineJoin: .round))
                        .interpolationMethod(.monotone)
                    PointMark(x: .value("Day", pt.day, unit: .day), y: .value(metric.label, pt.value))
                        .foregroundStyle(pt.id == lastID ? MP.brand : MP.chartS1)
                        .symbolSize(pt.id == lastID ? 70 : (pickedPoint?.id == pt.id ? 50 : 14))
                }
            }
            if pickedPoint == nil, let avg = metric.average, metric.series.count > 1 {
                RuleMark(y: .value("Average", avg))
                    .foregroundStyle(MP.chartRefLine)
                    .lineStyle(StrokeStyle(lineWidth: 1.2, dash: [3, 5]))
                    .annotation(position: .top, alignment: .trailing, spacing: 2) {
                        Text("avg").font(.axis).foregroundStyle(MP.chartAxisLabel)
                    }
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
                            Text(metric.text(for: p.value))
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
        .chartYScale(domain: .automatic(includesZero: isBar))
        .chartXAxis {
            AxisMarks(values: .stride(by: .day, count: metric.series.count > 8 ? 4 : 2)) { value in
                AxisValueLabel {
                    if let d = value.as(Date.self) {
                        Text(d.formatted(.dateTime.month(.abbreviated).day())).font(.axis).foregroundStyle(MP.chartAxisLabel)
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(values: .automatic(desiredCount: 3)) { value in
                AxisGridLine().foregroundStyle(MP.chartGrid)
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(metric.axisText(for: v)).font(.axis).foregroundStyle(MP.chartAxisLabel)
                    }
                }
            }
        }
        .frame(height: height)
        .mpSelectionFeedback(pickedPoint?.id)
        .accessibilityChartDescriptor(SeriesChartDescriptor(metric: metric))
        .onAppear {
            guard !grown else { return }
            if reduceMotion { grown = true } else {
                withAnimation(MPMotion.ease(0.8).delay(0.1)) { grown = true }
            }
        }
    }
}

/// VoiceOver's chart summary and Audio Graph for one signal.
private struct SeriesChartDescriptor: AXChartDescriptorRepresentable {
    let metric: PortfolioMetric

    func makeChartDescriptor() -> AXChartDescriptor {
        let points = metric.series
        let xs = points.map { $0.day.timeIntervalSince1970 }
        let ys = points.map(\.value)
        let xMin = xs.min() ?? 0, xMax = xs.max() ?? 1
        let yLo = metric.isDailyTotal ? 0 : (ys.min() ?? 0)
        let yHi = ys.max() ?? 1
        let format: (Double) -> String = { [metric] v in metric.spokenText(for: v) }
        let xAxis = AXNumericDataAxisDescriptor(title: "Day", range: xMin...max(xMax, xMin + 1),
                                                gridlinePositions: []) { value in
            Date(timeIntervalSince1970: value).formatted(.dateTime.weekday(.wide).month(.wide).day())
        }
        let yAxis = AXNumericDataAxisDescriptor(
            title: metric.unit.isEmpty ? metric.label : "\(metric.label) (\(metric.unit))",
            range: yLo...max(yHi, yLo + 1), gridlinePositions: [], valueDescriptionProvider: format)
        let series = AXDataSeriesDescriptor(
            name: metric.label, isContinuous: !metric.isDailyTotal,
            dataPoints: points.map { AXDataPoint(x: $0.day.timeIntervalSince1970, y: $0.value) })
        var summary = "\(points.count) days. Latest \(format(metric.latest.value))."
        if let avg = metric.average { summary += " Average \(format(avg))." }
        return AXChartDescriptor(title: "\(metric.label), last two weeks", summary: summary,
                                 xAxis: xAxis, yAxis: yAxis, additionalAxes: [], series: [series])
    }
}
