import SwiftUI

// The shared Today screens open `ConnectionsView()` (a clinic or personal
// space) and `SportsDevicesView()` (an athlete) for Apple Health and
// wearables. In the real app those connect this phone. A demo person has no
// phone of their own: their readings are written by the demo server. So
// these two say that plainly and list what the server reports as connected
// for the person, read-only, from calls the real screens already make.

/// The note both screens lead with.
private struct SimulatedNote: View {
    let firstName: String

    var body: some View {
        Card(tint: true) {
            HStack(alignment: .top, spacing: 12) {
                IconTile("wand.and.stars", family: .indigo, size: 40)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Simulated for the demo")
                        .mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        .accessibilityAddTraits(.isHeader)
                    Text("\(firstName) is fictional, so no watch or Health account is paired with this phone. The demo server writes their readings to look like weeks of real wear. In the real app, this is where a person connects Apple Health and their wearable.")
                        .mpFont(.copy).mpSecondary().lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
        }
    }
}

private struct CloseItem: ToolbarContent {
    let dismiss: DismissAction

    var body: some ToolbarContent {
        ToolbarItem(placement: .cancellationAction) {
            if #available(iOS 26, *) {
                Button(role: .close) { dismiss() }
            } else {
                Button("Done") { dismiss() }.mpFont(.copyLargeMedium)
            }
        }
    }
}

/// A clinic or personal demo person's sources, from `/api/mobile/wearables`.
struct ConnectionsView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss

    private var summary: WearableSummary? { app.wearables ?? app.me?.wearables }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    SimulatedNote(firstName: app.me?.patient.firstName ?? "This person")
                    if let summary {
                        sources(summary)
                    } else {
                        LoadingCard(text: "Reading what is connected…")
                    }
                }
                .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
            }
            .refreshable { await app.refreshWearables(surface: false) }
            .ambientScreen(height: 300)
            .task { await app.refreshWearables(surface: false) }
            .navigationTitle("Connections")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { CloseItem(dismiss: dismiss) }
        }
        .presentationDetents([.large])
    }

    private func sources(_ summary: WearableSummary) -> some View {
        let apple = summary.appleHealth
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader("What the server shows as connected")
                ListRow("Apple Health",
                        subtitle: apple.connected
                            ? (apple.lastSyncAt.map { "Last data \(Dates.relative($0))" } ?? "Connected")
                            : "No Health data on this chart",
                        symbol: "heart.fill", family: .violet, chevron: false) {
                    StateLabel(text: apple.connected ? "Connected" : "Not connected",
                               tone: apple.connected ? .low : .missing)
                }
                ForEach(summary.devices) { device in
                    RowDivider()
                    ListRow(device.model,
                            subtitle: device.lastSyncAt.map { "Synced \(Dates.relative($0))" } ?? device.provider.capitalized,
                            symbol: "applewatch", family: .blue, chevron: false) {
                        StateLabel(text: device.status.capitalized,
                                   tone: device.status == "connected" ? .low : device.status == "error" ? .high : .missing)
                    }
                }
                if !apple.connected && summary.devices.isEmpty {
                    RowDivider()
                    Text("This person’s chart is built from what they report: check-ins, exercises and messages.")
                        .mpFont(.copy).foregroundStyle(MP.body)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16).padding(.vertical, 12)
                }
            }
            .padding(.bottom, 4)
        }
        .clipShape(MP.surfaceShape)
    }
}

/// A demo athlete's sources, from `/api/mobile/sports/devices`: the ones the
/// server reports as connected or running on sample data.
struct SportsDevicesView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var board: DevicesBoard?
    @State private var error: String?

    /// A device counts as in use when the server has data for it, whether
    /// from a keyed credential or from its sample feed.
    private var active: [DeviceSpec] {
        (board?.groups ?? []).flatMap(\.devices).filter { $0.state == "connected" || $0.state == "sample" }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    SimulatedNote(firstName: app.me?.patient.firstName ?? "This athlete")
                    if let board {
                        sources(board)
                    } else if let error {
                        ErrorBanner(text: error)
                    } else {
                        LoadingCard(text: "Listing what is connected…")
                    }
                }
                .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
            }
            .refreshable { await load() }
            .ambientScreen(height: 300)
            .task { await load() }
            .navigationTitle("Devices")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { CloseItem(dismiss: dismiss) }
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    private func load() async {
        do {
            board = try await app.api.sportsDevices()
            error = nil
        } catch {
            if board == nil { self.error = AppModel.message(for: error) }
        }
    }

    private func sources(_ board: DevicesBoard) -> some View {
        let appleConnected = board.appleHealth?.connected ?? app.me?.wearables.appleHealth.connected ?? false
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader("What the server shows as connected")
                ListRow("Apple Health",
                        subtitle: appleConnected
                            ? (board.appleHealth?.lastSyncAt.map { "Last data \(Dates.relative($0))" } ?? "Connected")
                            : "No Health data on this athlete",
                        symbol: "heart.fill", family: .violet, chevron: false) {
                    StateLabel(text: appleConnected ? "Connected" : "Not connected",
                               tone: appleConnected ? .low : .missing)
                }
                ForEach(active) { device in
                    RowDivider()
                    ListRow(device.name,
                            subtitle: [device.maker, device.pathLabel].filter { !$0.isEmpty }.joined(separator: MP.dot),
                            symbol: device.symbol, family: device.team ? .blue : .teal, chevron: false) {
                        StateLabel(text: device.state == "sample" ? "Sample data" : "Connected",
                                   tone: device.state == "sample" ? .med : .low)
                    }
                }
                if active.isEmpty {
                    RowDivider()
                    Text("No watch, ring or team system is connected for this athlete.")
                        .mpFont(.copy).foregroundStyle(MP.body)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16).padding(.vertical, 12)
                }
            }
            .padding(.bottom, 4)
        }
        .clipShape(MP.surfaceShape)
    }
}
