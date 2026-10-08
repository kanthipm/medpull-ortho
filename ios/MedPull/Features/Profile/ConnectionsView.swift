import SwiftUI

/// Where the data comes from: Apple Health and any linked wearable. A
/// settings screen, reached from Profile, the Today nudge and a
/// `medpull://wearables` link, rather than a tab: once connected, a source
/// needs no daily attention.
struct ConnectionsView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var connecting = false
    @State private var uploading = false
    @State private var linking = false
    @State private var link: URL?
    @State private var error: String?

    private var appleConnected: Bool {
        app.health.isConnected || (app.wearables?.appleHealth.connected ?? false)
    }

    private var junctionReady: Bool { app.me?.features.appleHealth ?? false }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    appleCard
                    wearablesCard
                    if let error { ErrorBanner(text: error) }
                    Text("Nothing is written to Health. Turn any type off in the Health app and MedPull simply won’t read it.")
                        .mpFont(.label).foregroundStyle(MP.muted).padding(.horizontal, 4)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
            }
            .refreshable { await app.refreshWearables(force: true) }
            .ambientScreen(height: 300)
            .mpErrorFeedback(error)
            .task { await app.refreshWearables(surface: false) }
            .sheet(item: $link) { url in SafariView(url: url).ignoresSafeArea() }
            .navigationTitle("Connections")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if #available(iOS 26, *) {
                        Button(role: .close) { dismiss() }
                    } else {
                        Button("Done") { dismiss() }.mpFont(.copyLargeMedium)
                    }
                }
            }
        }
        .presentationDetents([.large])
    }

    private var appleCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    Glyph(systemName: "heart.fill", family: .violet, size: 40)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Apple Health").mpFont(.ledeMedium).foregroundStyle(MP.ink)
                            .accessibilityAddTraits(.isHeader)
                        StateLabel(text: appleConnected ? "Connected" : "Not connected",
                                   tone: appleConnected ? .low : .missing)
                    }
                    Spacer(minLength: 0)
                }
                if appleConnected {
                    Group {
                        if !app.health.syncLine.isEmpty {
                            Text(app.health.syncLine)
                        } else if let last = app.wearables?.appleHealth.lastSyncAt {
                            Text("Last data \(Dates.relative(last))")
                        } else {
                            Text("Syncing in the background. Data reaches your care team as it arrives.")
                        }
                    }
                    .mpFont(.copy).foregroundStyle(MP.body)
                    if let g = app.health.lastGaitUpload {
                        Text(g).mpFont(.label).foregroundStyle(MP.muted)
                    }
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 10) { syncButton; gaitButton }
                        VStack(spacing: 10) { syncButton; gaitButton }
                    }
                } else {
                    Text("One tap connects steps, sleep, heart rate, workouts and Apple’s walking metrics.")
                        .mpFont(.copy).foregroundStyle(MP.body)
                        .fixedSize(horizontal: false, vertical: true)
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
                HStack(spacing: 12) {
                    Glyph(systemName: "applewatch", family: .blue, size: 40)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Wearables").mpFont(.ledeMedium).foregroundStyle(MP.ink)
                            .accessibilityAddTraits(.isHeader)
                        Text(devices.isEmpty ? "Oura, Garmin, WHOOP, Fitbit, Withings, Polar."
                             : "\(devices.count) linked")
                            .mpFont(.label).foregroundStyle(MP.muted)
                    }
                    Spacer(minLength: 0)
                }
                .padding(16)
                if devices.isEmpty {
                    Text("Sign in once on their page and it syncs on its own.")
                        .mpFont(.copy).foregroundStyle(MP.body)
                        .padding(.horizontal, 16).padding(.bottom, 14)
                } else {
                    ForEach(devices) { d in
                        InsetDivider(leading: 16)
                        ListRow(d.model,
                                subtitle: d.lastSyncAt.map { "Synced \(Dates.relative($0))" } ?? "Waiting for first sync",
                                chevron: false) {
                            StateLabel(text: d.status.capitalized,
                                       tone: d.status == "connected" ? .low : d.status == "error" ? .high : .missing)
                        }
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
}
