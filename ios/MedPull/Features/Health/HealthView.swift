import Charts
import SwiftUI

struct HealthView: View {
    @Environment(AppModel.self) private var app
    @State private var connecting = false
    @State private var uploading = false
    @State private var linking = false
    @State private var link: URL?
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    appleCard
                    wearablesCard
                    portfolioSection
                    if let error { ErrorBanner(text: error) }
                }
                .padding(.horizontal, 18).padding(.top, 4).padding(.bottom, 24)
            }
            // A real large title at 600 (the face and weight come from
            // MPFont.applyUIKitAppearance). It collapses to an inline title
            // on scroll, which is why the hard edge below stays (R13): the
            // metric figures pass under that collapsed bar and must stop at a
            // definite line instead of washing out under a soft fade.
            .mpNavigationTitle("Health")
            .toolbarTitleDisplayMode(.large)
            .mpHardScrollEdge()
            .refreshable {
                await app.refreshWearables(force: true)
                await app.refreshPortfolio()
            }
            .ambientScreen()
            .mpErrorFeedback(error)
            .task {
                await app.refreshWearables()
                await app.refreshPortfolio()
            }
            .sheet(item: $link) { url in SafariView(url: url).ignoresSafeArea() }
        }
    }

    private var appleConnected: Bool {
        app.health.isConnected || (app.wearables?.appleHealth.connected ?? false)
    }

    private var junctionReady: Bool { app.me?.features.appleHealth ?? false }

    /// A card's title row: tile, 16/500 ink title, optional trailing view.
    private func cardTitle<Trailing: View>(_ title: String, symbol: String, family: MP.Category,
                                           @ViewBuilder trailing: () -> Trailing) -> some View {
        HStack(spacing: 14) {
            IconTile(symbol, family: family)
            Text(title)
                .mpFont(.copyLargeMedium)
                .foregroundStyle(MP.ink)
                .accessibilityAddTraits(.isHeader)
            Spacer(minLength: 8)
            trailing()
        }
    }

    private var appleCard: some View {
        // Connected is the tinted card. Everything secondary inside uses
        // `.mpSecondary()`, which is `body` there (5.51:1 dark on brandTint;
        // `muted` would be 4.07:1) and the buttons take a panel fill (R1/R8).
        // Violet, not red, for the heart: red is a MedPull risk colour.
        Card(tint: appleConnected) {
            VStack(alignment: .leading, spacing: 12) {
                cardTitle("Apple Health", symbol: "heart.fill", family: .violet) {
                    StatusPill(text: appleConnected ? "Connected" : "Not connected",
                               tone: appleConnected ? .low : .missing)
                }
                if appleConnected {
                    Group {
                        if !app.health.syncLine.isEmpty {
                            Text(app.health.syncLine)
                        } else if let last = app.wearables?.appleHealth.lastSyncAt {
                            Text("Last data \(Dates.relative(last))")
                        } else {
                            Text("Syncing in the background. Data appears on your care team's console as it arrives.")
                        }
                    }
                    .mpFont(.copy).mpSecondary()
                    if let g = app.health.lastGaitUpload {
                        Text(g).mpFont(.label).mpSecondary()
                    }
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 10) { syncButton; gaitButton }
                        VStack(spacing: 10) { syncButton; gaitButton }
                    }
                } else {
                    Text("One tap connects steps, sleep, heart rate, workouts and Apple's walking metrics. Nothing is written to Health.")
                        .mpFont(.copy).foregroundStyle(MP.body)
                    if !junctionReady {
                        ErrorBanner(text: "This server isn't connected to Junction yet, so there is nowhere for Health data to go.")
                    }
                    if case .failed(let m) = app.health.state { ErrorBanner(text: m) }
                    PrimaryButton(title: "Connect Apple Health", icon: "heart.fill", loading: connecting,
                                  disabled: !junctionReady) {
                        connecting = true
                        Task {
                            _ = await app.connectAppleHealth()
                            connecting = false
                        }
                    }
                }
            }
        }
        .mpCompletionFeedback(appleConnected)
    }

    private var syncButton: some View {
        SecondaryButton(title: "Sync now", icon: "arrow.triangle.2.circlepath") {
            app.health.syncNow()
            Task { await app.refreshWearables(force: true) }
        }
    }

    private var gaitButton: some View {
        SecondaryButton(title: "Send walking data", icon: "figure.walk", loading: uploading) {
            uploading = true
            Task {
                defer { uploading = false }
                do { _ = try await app.health.uploadGait(api: app.api) }
                catch { self.error = AppModel.message(for: error) }
            }
        }
    }

    private var wearablesCard: some View {
        let devices = app.wearables?.devices ?? []
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                cardTitle("Wearables", symbol: "applewatch", family: .blue) {
                    if !devices.isEmpty {
                        Text("\(devices.count) linked").mpFont(.label).mpSecondary()
                    }
                }
                .padding(16)
                if devices.isEmpty {
                    Text("Oura, Garmin, WHOOP, Fitbit, Withings, Polar. Sign in once on their page and it syncs on its own.")
                        .mpFont(.copy).foregroundStyle(MP.body)
                        .padding(.horizontal, 16)
                        .padding(.bottom, 14)
                } else {
                    ForEach(devices) { d in
                        InsetDivider()
                        HStack(spacing: 14) {
                            IconTile("dot.radiowaves.left.and.right", family: .blue)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(d.model).mpFont(.copyMedium).foregroundStyle(MP.ink)
                                Text(d.lastSyncAt.map { "Synced \(Dates.relative($0))" } ?? "Waiting for first sync")
                                    .mpFont(.label).mpSecondary()
                            }
                            Spacer(minLength: 8)
                            StatusPill(text: d.status.capitalized,
                                       tone: d.status == "connected" ? .low : d.status == "error" ? .high : .missing)
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .frame(minHeight: 44)
                        .accessibilityElement(children: .combine)
                    }
                    InsetDivider(leading: 16)
                }
                SecondaryButton(title: devices.isEmpty ? "Add a wearable" : "Add another", icon: "link", loading: linking) {
                    linking = true
                    Task {
                        defer { linking = false }
                        do { link = URL(string: try await app.api.wearableLink().linkUrl) }
                        catch { self.error = AppModel.message(for: error) }
                    }
                }
                .disabled(!junctionReady)
                .padding(16)
            }
        }
    }

    /// Apple Health's "Highlights" shape: a section title above the cards,
    /// then one card per signal, each led by its category tile.
    private var portfolioSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text("Your portfolio")
                    .mpFont(.subheadSemibold)
                    .foregroundStyle(MP.ink)
                    .accessibilityAddTraits(.isHeader)
                Spacer(minLength: 8)
                Text(app.portfolio.isEmpty ? "Last two weeks"
                     : "\(app.portfolio.count) signals\(MP.dot)two weeks")
                    .mpFont(.labelMedium)
                    // `body`, not `muted`: this line can sit on the ambient
                    // brand wash, where dark `muted` drops to ~4.07:1.
                    .foregroundStyle(MP.body)
            }
            .padding(.top, 10)
            .padding(.horizontal, 2)

            if app.portfolio.isEmpty {
                Card {
                    EmptyRow(icon: "chart.bar", title: "No data yet",
                             detail: "Connect Apple Health or a wearable and every signal it provides charts here.")
                }
            } else {
                ForEach(app.portfolio) { m in
                    Card { MetricChart(metric: m) }
                }
            }
        }
    }
}

// MARK: - Metric presentation

extension PortfolioMetric {
    /// The SF Symbol for this signal's category tile.
    var tileSymbol: String {
        switch key {
        case "steps": return "figure.walk"
        case "walking_speed", "walking_steadiness": return "figure.walk.motion"
        case "exercise_session": return "figure.run"
        case "active_energy": return "flame.fill"
        case "sleep_duration": return "bed.double.fill"
        case "resting_hr": return "heart.fill"
        case "hrv_rmssd", "hrv_sdnn": return "waveform.path.ecg"
        case "spo2": return "lungs.fill"
        case "respiratory_rate": return "wind"
        case "bp_systolic", "bp_diastolic": return "heart.text.square.fill"
        case "blood_glucose": return "drop.fill"
        case "body_weight": return "scalemass.fill"
        case "pain_nrs": return "bandage.fill"
        default: return "chart.xyaxis.line"
        }
    }

    /// The tile family: activity is teal, sleep indigo, heart and vitals
    /// violet, body and everything else blue. Never red/amber/green — those
    /// are risk colours (spec doNotCopy).
    var tileFamily: MP.Category {
        switch key {
        case "steps", "walking_speed", "walking_steadiness", "exercise_session", "active_energy":
            return .teal
        case "sleep_duration":
            return .indigo
        case "resting_hr", "hrv_rmssd", "hrv_sdnn", "spo2", "respiratory_rate",
             "bp_systolic", "bp_diastolic", "blood_glucose":
            return .violet
        default:
            return .blue
        }
    }
}

struct MetricChart: View {
    let metric: PortfolioMetric
    @State private var picked: Date?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// A bar's end cap. Mark geometry, not a surface radius: every radius
    /// token is wider than a 14-day bar, and a bar capped at one would stop
    /// reading as a bar.
    private static let barCap: CGFloat = 3
    /// The average rule's dash. It is the chart's second series, so the 4-2
    /// dash plus its direct label are what separate it from the data, not hue.
    private static let averageDash: [CGFloat] = [4, 2]

    private var isBar: Bool { metric.isDailyTotal }

    /// The point under the scrub, snapped to its calendar day.
    private var pickedPoint: PortfolioPoint? {
        guard let picked else { return nil }
        let cal = Calendar.current
        if let same = metric.series.first(where: { cal.isDate($0.day, inSameDayAs: picked) }) {
            return same
        }
        return metric.series.min { abs($0.day.timeIntervalSince(picked)) < abs($1.day.timeIntervalSince(picked)) }
    }

    /// What the header reads: the scrubbed day while dragging, otherwise the
    /// latest value. The latest is always on screen without a gesture.
    private var shown: PortfolioPoint { pickedPoint ?? metric.latest }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                IconTile(metric.tileSymbol, family: metric.tileFamily)
                Text(metric.label)
                    .mpFont(.copyMedium)
                    .foregroundStyle(MP.ink)
                    .lineLimit(2)
                Spacer(minLength: 8)
                Text(dayCaption)
                    .mpFont(.label)
                    .foregroundStyle(MP.muted)
                    .monospacedDigit()
                    .lineLimit(1)
            }

            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(metric.text(for: shown.value))
                    .font(.figures(MPSize.displayS, weight: .semibold, relativeTo: .title))
                    .foregroundStyle(MP.ink)
                    .contentTransition(.numericText())
                    .animation(MPMotion.gated(MPMotion.state, reduceMotion: reduceMotion), value: shown.value)
                if !metric.hideUnit {
                    Text(metric.unit)
                        .mpFont(.copyMedium)
                        .foregroundStyle(MP.muted)
                }
            }
            .lineLimit(1)
            .minimumScaleFactor(0.7)
            .accessibilityElement(children: .combine)
            .accessibilityLabel(Text("\(metric.label), \(pickedPoint == nil ? "latest" : dayCaption)"))
            .accessibilityValue(Text(metric.spokenText(for: shown.value)))

            chart
        }
    }

    private var dayCaption: String {
        let date = shown.day
        if date == .distantPast { return pickedPoint == nil ? "Latest" : shown.date }
        let text = date.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day())
        return pickedPoint == nil ? "Latest\(MP.dot)\(text)" : text
    }

    // TWO SERIES, AND THAT IS THE CAP. The data is series 1: daily totals as
    // bars on `chartS1`, sampled measurements as a line on `chartS2` (the teal
    // graphic cut, 5.02:1; the old `cyan` fill was 2.74:1 as a stroke). The
    // 14-day average is series 2: a 4-2 DASHED rule with a DIRECT label, in
    // the axis-label grey, so it separates from the data by dash and label
    // rather than hue. The data line itself is never dashed — a dashed line
    // through a patient's own heart rate reads as projected data. There is no
    // series 3 here; `chartSeq` is not reached.
    private var chart: some View {
        Chart {
            ForEach(metric.series) { pt in
                if isBar {
                    BarMark(x: .value("Day", pt.day, unit: .day),
                            y: .value(metric.label, pt.value))
                        .foregroundStyle(MP.chartS1)
                        .cornerRadius(Self.barCap)
                        .opacity(pickedPoint == nil || pickedPoint?.id == pt.id ? 1 : 0.45)
                } else {
                    LineMark(x: .value("Day", pt.day, unit: .day),
                             y: .value(metric.label, pt.value))
                        .foregroundStyle(MP.chartS2)
                        .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                        .interpolationMethod(.monotone)
                    PointMark(x: .value("Day", pt.day, unit: .day),
                              y: .value(metric.label, pt.value))
                        .foregroundStyle(MP.chartS2)
                        .symbolSize(pickedPoint?.id == pt.id ? 60 : 18)
                }
            }

            if pickedPoint == nil, let avg = metric.average, metric.series.count > 1 {
                RuleMark(y: .value("Average", avg))
                    .foregroundStyle(MP.chartAxisLabel)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: Self.averageDash))
                    .annotation(position: .top, alignment: .leading, spacing: 2) {
                        Text("Avg \(metric.text(for: avg))")
                            .font(.axis)
                            .foregroundStyle(MP.chartAxisLabel)
                            .padding(.horizontal, 3)
                            .background(MP.panel, in: MP.capsuleShape)
                    }
                    .accessibilityHidden(true)
            }

            if let p = pickedPoint {
                RuleMark(x: .value("Day", p.day, unit: .day))
                    .foregroundStyle(MP.chartAxisLabel)
                    .lineStyle(StrokeStyle(lineWidth: 1))
                    .zIndex(-1)
                    .annotation(position: .top, spacing: 4,
                                overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        // A clinical number sits on an OPAQUE fill.
                        HStack(spacing: 4) {
                            Text(metric.text(for: p.value))
                                .font(.figures(MPSize.copy, weight: .semibold))
                                .foregroundStyle(MP.ink)
                            Text(p.day.formatted(.dateTime.month(.abbreviated).day()))
                                .font(.figuresLabel)
                                .foregroundStyle(MP.body)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(MP.soft, in: MP.capsuleShape)
                    }
                    .accessibilityHidden(true)
            }
        }
        .chartXSelection(value: $picked)
        .chartYScale(domain: .automatic(includesZero: isBar))
        // 11pt (`MPSize.axis`, the app's floor) in `chartAxisLabel`
        // (5.39:1 light / 4.91:1 dark on panel) — never `faint`.
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4)) { value in
                AxisTick().foregroundStyle(MP.chartGrid)
                AxisValueLabel {
                    if let d = value.as(Date.self) {
                        Text(d, format: .dateTime.month(.abbreviated).day())
                            .font(.axis)
                            .foregroundStyle(MP.chartAxisLabel)
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 3)) { value in
                AxisGridLine().foregroundStyle(MP.chartGrid)
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(metric.axisText(for: v))
                            .font(.axis)
                            .foregroundStyle(MP.chartAxisLabel)
                    }
                }
            }
        }
        .frame(height: 132)
        .mpSelectionFeedback(pickedPoint?.id)
        .accessibilityChartDescriptor(MetricChartDescriptor(metric: metric))
    }
}

/// VoiceOver's chart summary and Audio Graph for one metric.
private struct MetricChartDescriptor: AXChartDescriptorRepresentable {
    let metric: PortfolioMetric

    func makeChartDescriptor() -> AXChartDescriptor {
        let points = metric.series
        let xs = points.map { $0.day.timeIntervalSince1970 }
        let ys = points.map(\.value)
        let xMin = xs.min() ?? 0, xMax = xs.max() ?? 1
        let yLo = metric.isDailyTotal ? 0 : (ys.min() ?? 0)
        let yHi = ys.max() ?? 1
        let format: (Double) -> String = { [metric] v in metric.spokenText(for: v) }

        let xAxis = AXNumericDataAxisDescriptor(
            title: "Day",
            range: xMin...max(xMax, xMin + 1),
            gridlinePositions: []
        ) { value in
            Date(timeIntervalSince1970: value).formatted(.dateTime.weekday(.wide).month(.wide).day())
        }
        let yAxis = AXNumericDataAxisDescriptor(
            title: metric.unit.isEmpty ? metric.label : "\(metric.label) (\(metric.unit))",
            range: yLo...max(yHi, yLo + 1),
            gridlinePositions: [],
            valueDescriptionProvider: format
        )
        let series = AXDataSeriesDescriptor(
            name: metric.label,
            isContinuous: !metric.isDailyTotal,
            dataPoints: points.map { AXDataPoint(x: $0.day.timeIntervalSince1970, y: $0.value) }
        )
        var summary = "\(points.count) days. Latest \(format(metric.latest.value))."
        if let avg = metric.average { summary += " Average \(format(avg))." }
        return AXChartDescriptor(
            title: "\(metric.label), last two weeks",
            summary: summary,
            xAxis: xAxis,
            yAxis: yAxis,
            additionalAxes: [],
            series: [series]
        )
    }
}
