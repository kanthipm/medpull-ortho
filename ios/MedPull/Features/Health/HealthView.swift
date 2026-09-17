import Charts
import SwiftUI

struct HealthView: View {
    @Environment(AppModel.self) private var app
    @State private var connecting = false
    @State private var uploading = false
    @State private var linking = false
    @State private var link: URL?
    @State private var error: String?
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    /// Accessibility text sizes stack every tile-title-pill row, so a title
    /// is never broken by character and a pill never splits.
    private var stacked: Bool { dynamicTypeSize.isAccessibilitySize }

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
    /// At accessibility sizes: tile, then title, then the trailing view, each
    /// on its own line at the card's leading edge.
    @ViewBuilder
    private func cardTitle<Trailing: View>(_ title: String, symbol: String, family: MP.Category,
                                           @ViewBuilder trailing: () -> Trailing) -> some View {
        let titleText = Text(title)
            .mpFont(.copyLargeMedium)
            .foregroundStyle(MP.ink)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityAddTraits(.isHeader)
        if stacked {
            VStack(alignment: .leading, spacing: 8) {
                IconTile(symbol, family: family)
                titleText
                trailing()
            }
        } else {
            HStack(spacing: 14) {
                IconTile(symbol, family: family)
                titleText
                Spacer(minLength: 8)
                trailing()
            }
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
                            Text("Syncing in the background. Data appears on your care team’s console as it arrives.")
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
                    Text("One tap connects steps, sleep, heart rate, workouts and Apple’s walking metrics. Nothing is written to Health.")
                        .mpFont(.copy).foregroundStyle(MP.body)
                    if !junctionReady {
                        ErrorBanner(text: "This server isn’t connected to Junction yet, so there is nowhere for Health data to go.")
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
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
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
                        rowDivider
                        deviceRow(d)
                    }
                    rowDivider
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

    /// Every divider in the Wearables card starts at the same place as the
    /// row text: past the tile normally, at the card inset when stacked.
    private var rowDivider: some View {
        InsetDivider(leading: stacked ? 16 : nil)
    }

    @ViewBuilder
    private func deviceRow(_ d: WearableDevice) -> some View {
        let tile = IconTile("dot.radiowaves.left.and.right", family: .blue)
        let text = VStack(alignment: .leading, spacing: 2) {
            Text(d.model).mpFont(.copyMedium).foregroundStyle(MP.ink)
                .fixedSize(horizontal: false, vertical: true)
            Text(d.lastSyncAt.map { "Synced \(Dates.relative($0))" } ?? "Waiting for first sync")
                .mpFont(.label).mpSecondary()
                .fixedSize(horizontal: false, vertical: true)
        }
        let pill = StatusPill(text: d.status.capitalized,
                              tone: d.status == "connected" ? .low : d.status == "error" ? .high : .missing)
        Group {
            if stacked {
                VStack(alignment: .leading, spacing: 8) {
                    tile
                    text
                    pill
                }
            } else {
                HStack(spacing: 14) {
                    tile
                    text
                    Spacer(minLength: 8)
                    pill
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .frame(minHeight: 44)
        .accessibilityElement(children: .combine)
    }

    /// Apple Health's "Highlights" shape: a section title above the cards,
    /// then one card per signal, each led by its category tile.
    private var portfolioSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            // A section header on the canvas, like the site's: the title in
            // 20/500 ink, the count in `body`.
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    portfolioTitle
                    Spacer(minLength: 8)
                    portfolioMeta
                }
                VStack(alignment: .leading, spacing: 2) {
                    portfolioTitle
                    portfolioMeta
                }
            }
            .padding(.top, 14)
            .padding(.horizontal, 4)

            if app.portfolio.isEmpty {
                Card {
                    EmptyRow(icon: "chart.bar", title: "No data yet",
                             detail: "Connect Apple Health or a wearable and every signal it provides charts here.")
                }
            } else {
                ForEach(Array(app.portfolio.enumerated()), id: \.element.id) { i, m in
                    MetricChart(metric: m).mpRise(i)
                }
            }
        }
    }

    private var portfolioTitle: some View {
        Text("Your portfolio")
            .mpFont(.subheadMedium)
            .foregroundStyle(MP.ink)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityAddTraits(.isHeader)
    }

    private var portfolioMeta: some View {
        Text(app.portfolio.isEmpty ? "Last two weeks"
             : "\(app.portfolio.count) signals\(MP.dot)two weeks")
            .mpFont(.copy)
            .foregroundStyle(MP.body)
            .fixedSize(horizontal: false, vertical: true)
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

    /// The tile family (and so the gradient): activity sage, sleep lilac,
    /// heart and vitals clay, body and everything else amber. Hue is the
    /// category, never the state.
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

/// One signal as the site's gradient tile: the name and the reading in
/// white over the dark top of the gradient, the last two weeks as white
/// marks (bars grow in; the newest is lime), and the average and range on a
/// solid-glass caption. Scrubbing the chart shows that day's value on an
/// opaque capsule and in the tile's number.
struct MetricChart: View {
    let metric: PortfolioMetric
    @State private var picked: Date?
    @State private var grown = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private static let barCap: CGFloat = 3
    private static let averageDash: [CGFloat] = [3, 5]

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

    /// The scrubbed day while dragging, otherwise the latest value.
    private var shown: PortfolioPoint { pickedPoint ?? metric.latest }

    private var sideDay: String {
        let date = shown.day
        if date == .distantPast { return shown.date }
        return date.formatted(.dateTime.month(.abbreviated).day())
    }

    private var range: String? {
        guard let first = metric.series.first?.day, let last = metric.series.last?.day,
              first != .distantPast else { return nil }
        let f = Date.FormatStyle.dateTime.month(.abbreviated).day()
        return "\(first.formatted(f)) – \(last.formatted(f))"
    }

    var body: some View {
        GradientTile(MP.categoryGradient(metric.tileFamily),
                     kicker: metric.label,
                     value: metric.text(for: shown.value),
                     unit: metric.hideUnit ? nil : metric.unit,
                     side: (sideDay, pickedPoint == nil ? "latest" : "selected")) {
            chart
        } caption: {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                if let avg = metric.average, metric.series.count > 1 {
                    Text("Avg \(metric.text(for: avg))")
                        .mpFont(.copyMedium).foregroundStyle(MP.ink)
                }
                Text([range, "\(metric.daysWithData) days of data"].compactMap { $0 }
                        .joined(separator: MP.dot))
                    .mpFont(.label).foregroundStyle(MP.body)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("\(metric.label), \(pickedPoint == nil ? "latest" : sideDay)"))
        .accessibilityValue(Text(metric.spokenText(for: shown.value)))
        .onAppear {
            guard !grown else { return }
            if reduceMotion { grown = true } else {
                withAnimation(MPMotion.ease(0.9).delay(0.2)) { grown = true }
            }
        }
    }

    // TWO SERIES, AND THAT IS THE CAP. The data is white (bars for daily
    // totals, a line for samples); the newest mark is lime. The 14-day
    // average is a dashed rule with a direct label on an opaque capsule.
    // No axes: the range and the average are in the caption, and a scrub
    // puts any day's value on an opaque capsule.
    private var chart: some View {
        let lastID = metric.series.last?.id
        return Chart {
            ForEach(metric.series) { pt in
                if isBar {
                    BarMark(x: .value("Day", pt.day, unit: .day),
                            y: .value(metric.label, grown ? pt.value : 0))
                        .foregroundStyle(pt.id == lastID ? MP.lime : Color.white.opacity(0.9))
                        .cornerRadius(Self.barCap)
                        .opacity(pickedPoint == nil || pickedPoint?.id == pt.id ? 1 : 0.4)
                } else {
                    LineMark(x: .value("Day", pt.day, unit: .day),
                             y: .value(metric.label, pt.value))
                        .foregroundStyle(Color.white)
                        .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                        .interpolationMethod(.monotone)
                    PointMark(x: .value("Day", pt.day, unit: .day),
                              y: .value(metric.label, pt.value))
                        .foregroundStyle(pt.id == lastID ? MP.lime : Color.white)
                        .symbolSize(pt.id == lastID ? 90 : (pickedPoint?.id == pt.id ? 60 : 16))
                }
            }

            if pickedPoint == nil, let avg = metric.average, metric.series.count > 1 {
                RuleMark(y: .value("Average", avg))
                    .foregroundStyle(Color.white.opacity(0.7))
                    .lineStyle(StrokeStyle(lineWidth: 1.5, lineCap: .round, dash: Self.averageDash))
                    .accessibilityHidden(true)
            }

            if let p = pickedPoint {
                RuleMark(x: .value("Day", p.day, unit: .day))
                    .foregroundStyle(Color.white.opacity(0.8))
                    .lineStyle(StrokeStyle(lineWidth: 1))
                    .zIndex(-1)
                    .annotation(position: .top, spacing: 4,
                                overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        // A clinical number sits on an OPAQUE fill.
                        HStack(spacing: 4) {
                            Text(metric.text(for: p.value))
                                .font(.figures(MPSize.copy, weight: .medium))
                                .foregroundStyle(MP.ink)
                            Text(p.day.formatted(.dateTime.month(.abbreviated).day()))
                                .font(.figuresLabel)
                                .foregroundStyle(MP.body)
                        }
                        .padding(.horizontal, 9)
                        .padding(.vertical, 5)
                        .background(MP.panel, in: MP.capsuleShape)
                    }
                    .accessibilityHidden(true)
            }
        }
        .chartXSelection(value: $picked)
        .chartYScale(domain: .automatic(includesZero: isBar))
        .chartXAxis(.hidden)
        .chartYAxis {
            AxisMarks(values: .automatic(desiredCount: 3)) { _ in
                AxisGridLine().foregroundStyle(Color.white.opacity(0.2))
            }
        }
        .frame(height: 124)
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
