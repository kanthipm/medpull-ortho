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
                    Text("Health").title(28).padding(.top, 8)
                    appleCard
                    wearablesCard
                    progressCard
                    if let error { ErrorBanner(text: error) }
                }
                .padding(.horizontal, 18).padding(.bottom, 24)
            }
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
                    Label("Apple Health", systemImage: "heart.fill").font(.system(size: 15, weight: .semibold)).foregroundStyle(MP.ink)
                    Spacer()
                    StatusPill(text: appleConnected ? "Connected" : "Not connected", tone: appleConnected ? .low : .missing)
                }
                if appleConnected {
                    if !app.health.syncLine.isEmpty {
                        Text(app.health.syncLine).font(.system(size: 13)).foregroundStyle(MP.muted)
                    } else if let last = app.wearables?.appleHealth.lastSyncAt {
                        Text("Last data \(Dates.relative(last))").font(.system(size: 13)).foregroundStyle(MP.muted)
                    } else {
                        Text("Syncing in the background. Data appears on your care team's console as it arrives.")
                            .font(.system(size: 13)).foregroundStyle(MP.muted)
                    }
                    if let g = app.health.lastGaitUpload {
                        Text(g).font(.system(size: 12.5)).foregroundStyle(MP.faint)
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
                        .font(.system(size: 14)).foregroundStyle(MP.body)
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
                    Label("Wearables", systemImage: "applewatch.radiowaves.left.and.right").font(.system(size: 15, weight: .semibold)).foregroundStyle(MP.ink)
                    Spacer()
                }
                let devices = app.wearables?.devices ?? []
                if devices.isEmpty {
                    Text("Oura, Garmin, WHOOP, Fitbit, Withings, Polar — sign in once on their page and it syncs on its own.")
                        .font(.system(size: 14)).foregroundStyle(MP.body)
                } else {
                    ForEach(devices) { d in
                        HStack {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(d.model).font(.system(size: 14.5, weight: .semibold)).foregroundStyle(MP.ink)
                                Text(d.lastSyncAt.map { "Synced \(Dates.relative($0))" } ?? "Waiting for first sync")
                                    .font(.system(size: 12.5)).foregroundStyle(MP.muted)
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
                    Text("Your portfolio · last two weeks").eyebrow()
                    Spacer()
                    if !app.portfolio.isEmpty {
                        Text("\(app.portfolio.count) signals").font(.system(size: 11.5, weight: .medium)).foregroundStyle(MP.faint)
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

    private var isBar: Bool {
        ["steps", "active_energy", "exercise_session"].contains(metric.key)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(metric.label).font(.system(size: 13.5, weight: .semibold)).foregroundStyle(MP.ink)
                Spacer()
                Text(metric.latestText).font(.system(size: 15, weight: .semibold, design: .monospaced)).foregroundStyle(MP.ink)
                Text(metric.unit).font(.system(size: 11)).foregroundStyle(MP.faint)
            }
            Chart(metric.series) { pt in
                if isBar {
                    BarMark(x: .value("Day", pt.date), y: .value(metric.label, pt.value))
                        .foregroundStyle(MP.brand).cornerRadius(3)
                } else {
                    LineMark(x: .value("Day", pt.date), y: .value(metric.label, pt.value))
                        .foregroundStyle(MP.cyan).interpolationMethod(.monotone)
                    PointMark(x: .value("Day", pt.date), y: .value(metric.label, pt.value))
                        .foregroundStyle(MP.cyan).symbolSize(18)
                }
            }
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 4)) { value in
                    AxisValueLabel {
                        if let raw = value.as(String.self) { Text(Dates.shortDay(raw)).font(.system(size: 9)) }
                    }
                }
            }
            .chartYAxis { AxisMarks(position: .leading) { AxisGridLine(); AxisValueLabel().font(.system(size: 9)) } }
            .frame(height: 96)
        }
    }
}
