import SwiftUI

/// Every source in one place: Apple Health first, then the watches, rings,
/// straps and beds the athlete wears, then the team systems (force plates,
/// trackers, timing gates, shooting and video) the staff connect. Each one
/// says how it reaches MedPull and what it gives.
struct SportsDevicesView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var board: DevicesBoard?
    @State private var error: String?
    @State private var connecting = false
    @State private var picked: DeviceSpec?
    @State private var link: URL?
    @State private var filter = "all"

    private var appleConnected: Bool {
        app.health.isConnected || (board?.appleHealth?.connected ?? false) || (app.me?.wearables.appleHealth.connected ?? false)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    appleCard
                    if let board {
                        filterRow(board)
                        ForEach(board.groups.filter { filter == "all" || ($0.devices.first?.team ?? false) == (filter == "team") }) { group in
                            groupCard(group)
                        }
                        Text("Watches and rings read through Apple Health or their own cloud account. Team systems connect through your program; until the credential is keyed, they run on sample data and say so.")
                            .mpFont(.label).foregroundStyle(MP.muted).padding(.horizontal, 4)
                            .fixedSize(horizontal: false, vertical: true)
                    } else if let error {
                        ErrorBanner(text: error)
                    } else {
                        LoadingCard(text: "Listing your devices…")
                    }
                }
                .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
            }
            .refreshable { await load() }
            .ambientScreen(height: 300)
            .navigationTitle("Devices")
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
            .sheet(item: $picked) { d in DeviceSheet(device: d) { Task { await load() } } }
            .sheet(item: $link) { url in SafariView(url: url).ignoresSafeArea() }
            .task { await load() }
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

    private var appleCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    Glyph(systemName: "heart.fill", family: .violet, size: 40)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Apple Health").mpFont(.ledeMedium).foregroundStyle(MP.ink).accessibilityAddTraits(.isHeader)
                        StateLabel(text: appleConnected ? "Connected" : "Not connected", tone: appleConnected ? .low : .missing)
                    }
                    Spacer(minLength: 0)
                    if let n = board?.connected, n > 0 {
                        Text("\(n) connected").mpFont(.label).foregroundStyle(MP.muted)
                    }
                }
                if appleConnected {
                    Text(app.health.syncLine.isEmpty
                         ? (board?.appleHealth?.lastSyncAt.map { "Last data \(Dates.relative($0))" } ?? "Sleep, HRV, resting heart rate and workouts flow in overnight.")
                         : app.health.syncLine)
                        .mpFont(.copy).foregroundStyle(MP.body)
                    SecondaryButton(title: "Sync now", icon: "arrow.triangle.2.circlepath") {
                        app.health.syncNow()
                        Task { await app.refreshWearables(force: true, surface: false); await load() }
                    }
                } else {
                    Text("Apple Watch and anything that writes to Health: one tap, and sleep, HRV, resting heart rate, workouts and wrist temperature read in overnight.")
                        .mpFont(.copy).foregroundStyle(MP.body)
                        .fixedSize(horizontal: false, vertical: true)
                    if case .failed(let m) = app.health.state { ErrorBanner(text: m) }
                    PrimaryButton(title: "Connect Apple Health", icon: "heart.fill", loading: connecting) {
                        connecting = true
                        Task {
                            _ = await app.connectAppleHealth()
                            connecting = false
                            await load()
                        }
                    }
                }
            }
        }
        .mpCompletionFeedback(appleConnected)
    }

    private func filterRow(_ board: DevicesBoard) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Chip(label: "All", selected: filter == "all") { filter = "all" }
                Chip(label: "What I wear", selected: filter == "mine") { filter = "mine" }
                Chip(label: "Team systems", selected: filter == "team") { filter = "team" }
            }
            .padding(.horizontal, 4).padding(.vertical, 2)
        }
        .scrollClipDisabled()
    }

    private func groupCard(_ group: DeviceGroup) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(group.label).mpFont(.labelMedium).foregroundStyle(MP.muted).padding(.horizontal, 4)
            Card(padding: 0) {
                VStack(spacing: 0) {
                    ForEach(group.devices) { d in
                        Button { picked = d } label: { DeviceRow(device: d) }
                            .buttonStyle(.mpRow)
                        if d.id != group.devices.last?.id { InsetDivider(leading: 16 + 32 + 12) }
                    }
                }
                .clipShape(MP.surfaceShape)
            }
        }
    }
}

struct DeviceRow: View {
    let device: DeviceSpec

    static func tone(_ state: String?) -> MP.Tone {
        switch state {
        case "connected": return .low
        case "sample": return .brand
        case "linking": return .med
        case "unavailable": return .missing
        default: return .missing
        }
    }

    static func word(_ state: String?) -> String {
        switch state {
        case "connected": return "Connected"
        case "sample": return "Sample data"
        case "linking": return "Linking"
        case "unavailable": return "Not on iPhone"
        default: return "Available"
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            Glyph(systemName: device.symbol, family: device.team ? .blue : .indigo)
            VStack(alignment: .leading, spacing: 2) {
                Text(device.name).mpFont(.copyLargeMedium).foregroundStyle(MP.ink).lineLimit(1)
                Text(device.detail ?? device.pathLabel).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
            }
            Spacer(minLength: 8)
            if device.state == "available" || device.state == nil {
                Text("Add").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
            } else {
                StateLabel(text: Self.word(device.state), tone: Self.tone(device.state))
            }
            Image(systemName: "chevron.right")
                .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                .accessibilityHidden(true)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }
}

/// One device: what it gives, how it reaches MedPull, and the connect or
/// disconnect action.
struct DeviceSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let device: DeviceSpec
    var onChange: () -> Void
    @State private var working = false
    @State private var error: String?
    @State private var state: String?
    @State private var detail: String?
    @State private var link: URL?

    private var connected: Bool { state == "connected" || state == "sample" }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(spacing: 14) {
                        Glyph(systemName: device.symbol, family: device.team ? .blue : .indigo, size: 48)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(device.name).mpFont(.subheadMedium).foregroundStyle(MP.ink)
                            Text("\(device.maker)\(MP.dot)\(device.categoryLabel)").mpFont(.label).foregroundStyle(MP.muted)
                        }
                        Spacer()
                        StateLabel(text: DeviceRow.word(state), tone: DeviceRow.tone(state))
                    }
                    Text(device.blurb.typeset).mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    if let detail, !detail.isEmpty {
                        Text(detail.typeset).mpFont(.copy).foregroundStyle(MP.body)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Card(padding: 0) {
                        VStack(alignment: .leading, spacing: 0) {
                            CardHeader("What it gives")
                            ForEach(Array(device.provides.enumerated()), id: \.offset) { i, p in
                                HStack(alignment: .top, spacing: 8) {
                                    LimeDot(size: 6).padding(.top, 7)
                                    Text(p).mpFont(.copy).foregroundStyle(MP.ink)
                                }
                                .padding(.horizontal, 16).padding(.vertical, 5)
                            }
                            if !device.scores.isEmpty {
                                Text("Its own scores (\(device.scores.joined(separator: ", "))) are shown as the device reports them, beside MedPull's readiness, never blended into it.")
                                    .mpFont(.label).foregroundStyle(MP.muted)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .padding(.horizontal, 16).padding(.top, 8)
                            }
                            Spacer().frame(height: 12)
                        }
                    }
                    Card {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("How it connects").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            Text(pathExplanation).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                                .fixedSize(horizontal: false, vertical: true)
                            if !device.note.isEmpty {
                                Text(device.note.typeset).mpFont(.label).foregroundStyle(MP.muted)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    if let error { ErrorBanner(text: error) }
                    actions
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .ambientScreen(height: 300)
            .navigationTitle(device.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.mpFont(.copyLargeMedium) }
            }
            .sheet(item: $link) { url in SafariView(url: url).ignoresSafeArea() }
            .onAppear { state = device.state; detail = device.detail }
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    private var pathExplanation: String {
        switch device.path {
        case "healthkit": return "It writes to Apple Health on your phone, and MedPull reads Health. Connect Apple Health once and this flows in with no other sign-in."
        case "junction": return "A cloud account. Sign in once on the maker's page and the data syncs on its own, every night."
        case "partner": return "A team system. Your program's performance staff connect it on their side; your own numbers appear here under your name."
        case "import": return "An export file from the maker's app or portal, dropped into MedPull by you or your staff."
        case "ble": return "Bluetooth, straight to the phone during a session."
        default: return "This device keeps its data inside its own app and offers no way to read it on iPhone."
        }
    }

    @ViewBuilder private var actions: some View {
        switch device.path {
        case "healthkit":
            if app.health.isConnected || (app.me?.wearables.appleHealth.connected ?? false) {
                Text("Apple Health is connected, so this device's data already reads through.").mpFont(.label).foregroundStyle(MP.riskLow)
            } else {
                PrimaryButton(title: "Connect Apple Health", icon: "heart.fill", loading: working) {
                    working = true
                    Task { _ = await app.connectAppleHealth(); working = false; onChange() }
                }
            }
        case "junction":
            if connected {
                SecondaryButton(title: "Disconnect", icon: "xmark", loading: working) { disconnect() }
            } else {
                PrimaryButton(title: "Sign in and link", icon: "link", loading: working) { connect(mode: "link") }
            }
        case "partner", "import", "ble":
            if connected {
                SecondaryButton(title: "Disconnect", icon: "xmark", loading: working) { disconnect() }
            } else {
                PrimaryButton(title: device.path == "import" ? "Set up import" : "Connect through my program", icon: "link", loading: working) {
                    connect(mode: device.path == "import" ? "import" : "sample")
                }
            }
        default:
            EmptyView()
        }
    }

    private func connect(mode: String) {
        working = true
        error = nil
        Task {
            defer { working = false }
            do {
                let r = try await app.api.sportsConnectDevice(key: device.key, mode: mode)
                if let raw = r.linkUrl, let url = URL(string: raw) {
                    link = url
                    state = "linking"
                } else {
                    state = r.state
                    detail = r.detail
                }
                onChange()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }

    private func disconnect() {
        working = true
        error = nil
        Task {
            defer { working = false }
            do {
                try await app.api.sportsDisconnectDevice(key: device.key)
                state = "available"
                detail = nil
                onChange()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}
