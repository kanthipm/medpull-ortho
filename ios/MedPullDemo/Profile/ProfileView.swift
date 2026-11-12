import SwiftUI
import UIKit

/// The demo app's profile sheet, behind the avatar at the top right of
/// Today. The shared screens present `ProfileView()` there; in the real app
/// that is a patient's profile, and in this target it is the presenter's
/// switcher: who the app is being, the way to become someone else, and the
/// demo's own controls.
///
/// Same cards and rows as the real Profile (one `Card(padding: 0)` per
/// group, a quiet header, footers as muted text under the card), so the
/// contrast figures recorded there hold here.
struct ProfileView: View {
    @Environment(AppModel.self) private var app
    @Environment(DemoShell.self) private var shell
    @Environment(Appearance.self) private var appearance
    @Environment(\.dismiss) private var dismiss
    @State private var path: [DemoRoute] = []
    @State private var showPhone = false
    @State private var showDevices = false
    @State private var showServer = false
    @State private var confirmReset = false
    @State private var resetting = false
    @State private var resetResult: String?
    @State private var resetError: String?
    @State private var phone: DemoPhoneState?
    @State private var phoneUnavailable = false
    @State private var startingOver = false

    private var version: DemoVersion { app.me.map(DemoVersion.init(me:)) ?? shell.version }
    private var firstName: String { app.me?.patient.firstName ?? "this person" }

    var body: some View {
        @Bindable var appearance = appearance
        return NavigationStack(path: $path) {
            ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    identityCard

                    group("This demo", footer: "Texts the demo sends to \(firstName) go to whichever phone is bound to them.") {
                        Button { showPhone = true } label: {
                            ListRow("Text my phone", subtitle: phoneLine,
                                    symbol: "message.fill", family: .blue)
                        }
                        .buttonStyle(.mpRow)
                        if version == .clinic, app.me != nil {
                            InsetDivider(leading: 16 + 32 + 12)
                            Button { confirmReset = true } label: {
                                ListRow("Reset today",
                                        subtitle: "Reopen today’s exercises and clear what today’s demo added to the thread.",
                                        symbol: "arrow.counterclockwise", family: .violet, chevron: false) {
                                    if resetting { ProgressView().tint(MP.muted) }
                                }
                            }
                            .buttonStyle(.mpRow)
                            .disabled(resetting)
                        }
                        if app.me != nil {
                            InsetDivider(leading: 16 + 32 + 12)
                            Button { showDevices = true } label: {
                                ListRow(version == .sports ? "Devices" : "Apple Health and wearables",
                                        subtitle: "Simulated for this person",
                                        symbol: "applewatch", family: .indigo)
                            }
                            .buttonStyle(.mpRow)
                        }
                    }
                    .id("demo")
                    if let resetResult {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Image(systemName: "checkmark.circle.fill").foregroundStyle(MP.riskLow)
                                .accessibilityHidden(true)
                            Text(resetResult).mpFont(.copyMedium).foregroundStyle(MP.ink)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(MP.controlShape.fill(MP.riskLowBg))
                        .padding(.top, -10)
                    }
                    if let resetError { ErrorBanner(text: resetError).padding(.top, -10) }

                    group("Appearance", footer: "Light is the default. System follows your iPhone’s Display & Brightness setting.") {
                        Picker("Appearance", selection: $appearance.mode) {
                            ForEach(AppearanceMode.allCases) { mode in
                                Text(mode.label).tag(mode)
                            }
                        }
                        .pickerStyle(.segmented)
                        .labelsHidden()
                        .mpSelectionFeedback(appearance.mode)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                    }

                    group("Server", footer: "Where this app finds the demo. Built in: \(AppConfig.builtInBaseURL.absoluteString)") {
                        Button { showServer = true } label: {
                            ListRow("Server address",
                                    subtitle: AppConfig.baseURL.absoluteString,
                                    symbol: "network", family: .teal)
                        }
                        .buttonStyle(.mpRow)
                        InsetDivider(leading: 16 + 32 + 12)
                        serverRow
                    }
                    .id("server")

                    group("About", footer: "MedPull Demo \(Self.versionLine). Everyone in this app is fictional. Questions: hello@medpull.org.") {
                        actionRow("Privacy policy") { UIApplication.shared.open(Legal.privacy) }
                        InsetDivider(leading: 16)
                        actionRow("Terms of use") { UIApplication.shared.open(Legal.terms) }
                    }

                    group(nil) {
                        Button {
                            startingOver = true
                            Task {
                                await shell.startOver()
                                dismiss()
                            }
                        } label: {
                            HStack {
                                Text("Start over").mpFont(.copyLargeMedium)
                                Spacer()
                                if startingOver { ProgressView().tint(MP.muted) }
                            }
                            .foregroundStyle(MP.riskHigh)
                            .padding(.horizontal, 16)
                            .frame(minHeight: 50)
                        }
                        .buttonStyle(.mpRow)
                        .disabled(startingOver)
                        .accessibilityHint("Signs out and goes back to Who do you want to be")
                    }
                }
                .padding(.horizontal, 18)
                .padding(.top, 8)
                .padding(.bottom, 28)
            }
            .ambientScreen()
            .tint(MP.brandInk)
            .mpNavigationTitle("Demo")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: DemoRoute.self) { route in
                switch route {
                case .versions:
                    VersionsScreen(welcome: false)
                case .people(let version):
                    // Becoming someone rebuilds the tabs under this sheet,
                    // so it closes itself first.
                    PeopleScreen(version: version) { dismiss() }
                }
            }
            .sheet(isPresented: $showPhone, onDismiss: { Task { await loadPhone() } }) { TextMyPhoneSheet() }
            .sheet(isPresented: $showDevices) {
                if app.isSports { SportsDevicesView() } else { ConnectionsView() }
            }
            .sheet(isPresented: $showServer) { ServerAddressSheet() }
            .confirmationDialog("Reset \(firstName)’s day?", isPresented: $confirmReset, titleVisibility: .visible) {
                Button("Reset today", role: .destructive) { reset() }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Today’s exercises go back to not done, and the lines today’s demo added to the thread are removed. Earlier days stay as they are.")
            }
            .task {
                await shell.loadRoster()
            }
            .task {
                await shell.checkServer()
            }
            .task {
                await loadPhone()
                #if DEBUG
                // Simulator screenshots: `-MP_SHOW profile -MP_PROFILE
                // people|versions|phone|devices|server|reset`, and
                // `-MP_SCROLL_PROFILE demo|server` as in the real Profile.
                // Once per launch: becoming someone else builds a new
                // Today, which opens this sheet again for `-MP_SHOW profile`.
                let wanted = Self.debugOpened ? nil : AppConfig.debugFlag("MP_PROFILE")
                Self.debugOpened = true
                switch wanted {
                case "people": path = [.people(version)]
                case "versions": path = [.versions]
                case "phone": showPhone = true
                case "devices": showDevices = true
                case "server": showServer = true
                case "reset": confirmReset = true
                case "resetnow": reset()
                case "startover":
                    startingOver = true
                    await shell.startOver()
                    dismiss()
                default: break
                }
                if let target = AppConfig.debugFlag("MP_SCROLL_PROFILE") {
                    try? await Task.sleep(for: .seconds(1.5))
                    proxy.scrollTo(target, anchor: .top)
                }
                #endif
            }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if #available(iOS 26, *) {
                        Button(role: .close) { dismiss() }
                    } else {
                        Button("Done") { dismiss() }
                            .mpFont(.copyLargeMedium)
                    }
                }
            }
            .mpErrorFeedback(resetError)
            .mpCompletionFeedback(resetResult != nil)
            }
        }
        .presentationDetents([.large])
    }

    // MARK: Who the app is being

    private var identityCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    if let me = app.me {
                        HStack(spacing: 14) {
                            Initials(text: me.patient.initials, size: 56)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(me.patient.name)
                                    .mpFont(.subheadSemibold).foregroundStyle(MP.ink)
                                Text([version.label, shell.organisation?.demoTypeset].compactMap { $0 }
                                    .joined(separator: MP.dot))
                                    .mpFont(.copy).foregroundStyle(MP.body)
                                if let line = storyLine(me), !line.isEmpty {
                                    Text(line.demoTypeset).mpFont(.copy).foregroundStyle(MP.muted)
                                }
                            }
                            .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 0)
                        }
                        .padding(16)
                        .accessibilityElement(children: .combine)
                    } else {
                        ListRow("Nobody is loaded",
                                subtitle: "The app couldn’t read this person from the server. Pick someone again, or check the server address.",
                                symbol: "person.fill.questionmark", family: .blue, chevron: false)
                    }
                    InsetDivider(leading: 16)
                    NavigationLink(value: DemoRoute.people(version)) {
                        ListRow("Switch person", subtitle: "Someone else in \(version.label)",
                                symbol: "person.2.fill", family: .teal)
                    }
                    .buttonStyle(.mpRow)
                    InsetDivider(leading: 16 + 32 + 12)
                    NavigationLink(value: DemoRoute.versions) {
                        ListRow("Switch version", subtitle: "Clinic, Personal or Sports",
                                symbol: "square.stack.3d.up.fill", family: .indigo)
                    }
                    .buttonStyle(.mpRow)
                }
                .padding(.bottom, 4)
            }
            .clipShape(MP.surfaceShape)
            Text("A fictional person on the MedPull demo. Nothing here is anyone’s real record.")
                .mpFont(.label).foregroundStyle(MP.muted)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 16)
        }
    }

    /// One line about the person: the demo's own tagline for them when the
    /// persona list is loaded, else what `/me` says about their program.
    private func storyLine(_ me: Me) -> String? {
        if let tagline = shell.roster?.persona(me.patient.id)?.tagline, !tagline.isEmpty { return tagline }
        if me.isSports { return me.sports?.levelLabel }
        if me.isPersonal { return app.dashboard?.profile.goalLabel }
        return me.patient.procedureDisplay
    }

    // MARK: Text my phone

    private var phoneLine: String {
        if phoneUnavailable { return "Not available on this server" }
        guard let phone, phone.isBound else { return "Send this demo’s texts to your own phone" }
        return phone.reachable
            ? "Texts reach \(PhoneNumber.display(phone.phone))"
            : "Waiting for a first text from \(PhoneNumber.display(phone.phone))"
    }

    private func loadPhone() async {
        guard app.me != nil else { return }
        do {
            phone = try await app.api.demoPhone()
            phoneUnavailable = false
        } catch let error as APIError where error.status == 404 {
            phoneUnavailable = true
        } catch {
            // The row keeps its invitation; the sheet itself says what failed.
        }
    }

    #if DEBUG
    private static var debugOpened = false
    #endif

    // MARK: The server

    /// Whether the server at that address is a demo, from `GET /api/health`.
    /// The persona list, the links and the texts exist on a demo only.
    @ViewBuilder private var serverRow: some View {
        let host = AppConfig.baseURL.host ?? AppConfig.baseURL.absoluteString
        switch shell.serverState {
        case .unknown, .checking:
            ListRow("Checking this server", subtitle: host, symbol: "server.rack", family: .teal, chevron: false) {
                ProgressView().tint(MP.muted)
            }
        case .known(let demo, let filledOn):
            if demo {
                ListRow("A MedPull demo",
                        subtitle: filledOn.map { "Its people were brought up to \(Dates.monthDay($0))." }
                            ?? "Everyone on it is fictional.",
                        symbol: "server.rack", family: .teal, chevron: false) {
                    StateLabel(text: "Demo", tone: .low)
                }
            } else {
                ListRow("Not a demo server",
                        subtitle: "The demo’s people, links and texts need a demo server.",
                        symbol: "server.rack", family: .teal, chevron: false) {
                    StateLabel(text: "Not a demo", tone: .med)
                }
            }
        case .unreachable:
            ListRow("No answer", subtitle: "Can’t reach \(host). Check the address.",
                    symbol: "server.rack", family: .teal, chevron: false) {
                StateLabel(text: "Unreachable", tone: .high)
            }
        }
    }

    // MARK: Reset today

    private func reset() {
        resetting = true
        resetResult = nil
        resetError = nil
        Task {
            defer { resetting = false }
            do {
                resetResult = try await shell.resetDay().sentence
            } catch {
                resetError = DemoShell.sentence(
                    for: error,
                    notFound: "This server can’t reset a day. It needs a MedPull demo server."
                )
            }
        }
    }

    // MARK: Pieces

    /// A titled card with an optional footer under it, as in the real Profile.
    private func group<Content: View>(_ title: String?, footer: String? = nil,
                                      @ViewBuilder content: () -> Content) -> some View {
        let rows = content()
        return VStack(alignment: .leading, spacing: 8) {
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    if let title { CardHeader(title) }
                    rows
                }
                .padding(.bottom, title == nil ? 0 : 4)
            }
            .clipShape(MP.surfaceShape)
            if let footer {
                Text(footer)
                    .mpFont(.label)
                    .foregroundStyle(MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16)
            }
        }
    }

    private func actionRow(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .mpFont(.copyLargeMedium)
                .foregroundStyle(MP.brandInk)
                .padding(.horizontal, 16)
                .frame(minHeight: 48)
        }
        .buttonStyle(.mpRow)
    }
}
