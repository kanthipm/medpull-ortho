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
                    Text("Health").title(MPSize.displayS).padding(.top, 8)
                    appleCard
                    wearablesCard
                    progressCard
                    if let error { ErrorBanner(text: error) }
                }
                .padding(.horizontal, 18).padding(.bottom, 24)
            }
            // Hard, not the default soft, edge: the charts' latest values and
            // axis labels stop at a definite line under the status bar and
            // the minimizing tab bar instead of washing out under them. The
            // one scroll edge effect in this view. Passthrough below iOS 26.
            .mpHardScrollEdge()
            .refreshable {
                await app.refreshWearables(force: true)
                await app.refreshPortfolio()
            }
            .screen()
            .toolbar(.hidden, for: .navigationBar)
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

    private var appleCard: some View {
        Card(tint: appleConnected) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Label("Apple Health", systemImage: "heart.fill").font(.copyLargeMedium).foregroundStyle(MP.ink)
                    Spacer()
                    StatusPill(text: appleConnected ? "Connected" : "Not connected", tone: appleConnected ? .low : .missing)
                }
                // EVERY LINE IN THIS BRANCH IS ON `brandTint`, NOT `panel` —
                // `Card(tint: appleConnected)` above means the connected card
                // is the tinted one, and `muted` measures 4.07:1 on the dark
                // brandTint. That is an AA failure, so the secondary copy in
                // here is `body` (6.24:1 light / 5.51:1 dark on brandTint),
                // which is also what the not-connected branch below uses. The
                // hierarchy is carried by size — 14 for the sync line, 12 for
                // the upload receipt — because there is no compliant tier
                // between `body` and `ink` on this ground.
                if appleConnected {
                    if !app.health.syncLine.isEmpty {
                        Text(app.health.syncLine).font(.copy).foregroundStyle(MP.body)
                    } else if let last = app.wearables?.appleHealth.lastSyncAt {
                        Text("Last data \(Dates.relative(last))").font(.copy).foregroundStyle(MP.body)
                    } else {
                        Text("Syncing in the background. Data appears on your care team's console as it arrives.")
                            .font(.copy).foregroundStyle(MP.body)
                    }
                    if let g = app.health.lastGaitUpload {
                        Text(g).font(.label).foregroundStyle(MP.body)
                    }
                    HStack(spacing: 10) {
                        SecondaryButton(title: "Sync now", icon: "arrow.triangle.2.circlepath") {
                            app.health.syncNow()
                            Task { await app.refreshWearables(force: true) }
                        }
                        SecondaryButton(title: "Send walking data", icon: "figure.walk", loading: uploading) {
                            uploading = true
                            Task {
                                defer { uploading = false }
                                do { _ = try await app.health.uploadGait(api: app.api) }
                                catch { self.error = AppModel.message(for: error) }
                            }
                        }
                    }
                } else {
                    Text("One tap connects steps, sleep, heart rate, workouts and Apple's walking metrics. Nothing is written to Health.")
                        .font(.copy).foregroundStyle(MP.body)
                    if !(app.me?.features.appleHealth ?? false) {
                        ErrorBanner(text: "This server isn't connected to Junction yet, so there is nowhere for Health data to go.")
                    }
                    if case .failed(let m) = app.health.state { ErrorBanner(text: m) }
                    PrimaryButton(title: "Connect Apple Health", icon: "heart.fill", loading: connecting,
                                  disabled: !(app.me?.features.appleHealth ?? false)) {
                        connecting = true
                        Task {
                            _ = await app.connectAppleHealth()
                            connecting = false
                        }
                    }
                }
            }
        }
    }

    private var wearablesCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Label("Wearables", systemImage: "applewatch.radiowaves.left.and.right").font(.copyLargeMedium).foregroundStyle(MP.ink)
                    Spacer()
                }
                let devices = app.wearables?.devices ?? []
                if devices.isEmpty {
                    Text("Oura, Garmin, WHOOP, Fitbit, Withings, Polar — sign in once on their page and it syncs on its own.")
                        .font(.copy).foregroundStyle(MP.body)
                } else {
                    ForEach(devices) { d in
                        HStack {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(d.model).font(.copyMedium).foregroundStyle(MP.ink)
                                Text(d.lastSyncAt.map { "Synced \(Dates.relative($0))" } ?? "Waiting for first sync")
                                    .font(.label).foregroundStyle(MP.muted)
                            }
                            Spacer()
                            StatusPill(text: d.status.capitalized, tone: d.status == "connected" ? .low : d.status == "error" ? .high : .missing)
                        }
                        .padding(.vertical, 4)
                    }
                }
                SecondaryButton(title: devices.isEmpty ? "Add a wearable" : "Add another", icon: "link", loading: linking) {
                    linking = true
                    Task {
                        defer { linking = false }
                        do { link = URL(string: try await app.api.wearableLink().linkUrl) }
                        catch { self.error = AppModel.message(for: error) }
                    }
                }
                .disabled(!(app.me?.features.appleHealth ?? false))
            }
        }
    }

    private var progressCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Your portfolio\(MP.dot)last two weeks").eyebrow()
                    Spacer()
                    if !app.portfolio.isEmpty {
                        Text("\(app.portfolio.count) signals").font(.labelMedium).foregroundStyle(MP.muted)
                    }
                }
                if app.portfolio.isEmpty {
                    EmptyRow(icon: "chart.bar", title: "No data yet",
                             detail: "Connect Apple Health or a wearable and every signal it provides charts here.")
                } else {
                    ForEach(app.portfolio) { m in
                        MetricChart(metric: m)
                    }
                }
            }
        }
    }
}

struct MetricChart: View {
    let metric: PortfolioMetric

    /// A bar's end cap. Mark geometry, not a surface radius — `radiusSurface`
    /// (12) and `radiusControl` (10) are both larger than a 14-day bar is
    /// wide, and a capped bar at either would stop reading as a bar. Named
    /// rather than typed inline so it is not mistaken for a radius token.
    private static let barCap: CGFloat = 3

    private var isBar: Bool {
        ["steps", "active_energy", "exercise_session"].contains(metric.key)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(metric.label).font(.copyMedium).foregroundStyle(MP.ink)
                Spacer()
                Text(metric.latestText).font(.figuresCopyLarge).foregroundStyle(MP.ink)
                Text(metric.unit).font(.label).foregroundStyle(MP.muted)
            }
            // TWO SERIES TOKENS, AND THAT IS THE CAP. Daily totals are bars
            // on `chartS1`; sampled measurements are a line on `chartS2`. That
            // is the whole categorical vocabulary — there is never a series 3
            // here, and `chartSeq` (which is what 3+ series takes) is not
            // reached. It replaces `MP.brand` on the bars and `MP.cyan` on the
            // line: `cyan` is the retired alias for the 172,193 teal FILL, and
            // as a 1pt stroke it measured 2.74:1 on the light panel, under the
            // 3:1 stroke floor. `chartS2` is the teal graphic cut at 5.02:1.
            //
            // NO DASH, DELIBERATELY. `chartS2`'s contract makes the 4-2 dash
            // mandatory because s1-vs-s2 is only 1.26:1 light / 1.60:1 dark —
            // but that is a rule about telling two series apart INSIDE one
            // plot, and each MetricChart draws exactly one series (one
            // `PortfolioMetric`, one `series` array). There is no s1 in a line
            // plot for the dash to separate it from, and a dashed line through
            // real measurements reads as interpolated or projected data, which
            // on a patient's own heart rate is a clinical misread rather than
            // decoration. Across the card it is mark SHAPE, not hue, that
            // separates the two families, and shape needs no contrast ratio.
            // The direct label the contract asks for is already present and
            // better placed than an end-of-line annotation on a 96pt plot: the
            // header row above states `metric.latestText` and the unit in
            // text, so the number is never read off an axis.
            Chart(metric.series) { pt in
                if isBar {
                    BarMark(x: .value("Day", pt.date), y: .value(metric.label, pt.value))
                        .foregroundStyle(MP.chartS1).cornerRadius(Self.barCap)
                } else {
                    LineMark(x: .value("Day", pt.date), y: .value(metric.label, pt.value))
                        .foregroundStyle(MP.chartS2).interpolationMethod(.monotone)
                    PointMark(x: .value("Day", pt.date), y: .value(metric.label, pt.value))
                        .foregroundStyle(MP.chartS2).symbolSize(18)
                }
            }
            // 11pt — `MPSize.axis`, the one size allowed under 12 and the
            // floor for the whole app. These were 9pt, which is under Apple's
            // documented minimum in any face and renders an apparent 4.6pt
            // x-height in Instrument Sans. An axis label is text, so it takes
            // `chartAxisLabel` (5.39:1 light / 4.91:1 dark on panel) and never
            // `faint`, which was 2.59:1 under it.
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 4)) { value in
                    AxisValueLabel {
                        if let raw = value.as(String.self) {
                            Text(Dates.shortDay(raw))
                                .font(.axis)
                                .foregroundStyle(MP.chartAxisLabel)
                        }
                    }
                }
            }
            .chartYAxis {
                AxisMarks(position: .leading) {
                    AxisGridLine().foregroundStyle(MP.chartGrid)
                    AxisValueLabel().font(.axis).foregroundStyle(MP.chartAxisLabel)
                }
            }
            .frame(height: 96)
        }
    }
}
