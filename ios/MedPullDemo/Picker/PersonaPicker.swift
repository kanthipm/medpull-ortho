import SwiftUI

/// A place the picker can be: the three versions, or the people in one.
/// The first launch walks both; the profile sheet pushes either.
enum DemoRoute: Hashable {
    case versions
    case people(DemoVersion)
}

/// "Who do you want to be?": the demo app's first screen, and the only one
/// with nobody signed in. There is no account anywhere: the server lists
/// its fictional people (`GET /api/demo/personas`), and choosing one asks
/// for a session as them (`POST /api/demo/session`).
struct PersonaPicker: View {
    @Environment(DemoShell.self) private var shell
    @State private var path: [DemoRoute] = []

    var body: some View {
        NavigationStack(path: $path) {
            VersionsScreen(welcome: true)
                .toolbar(.hidden, for: .navigationBar)
                .navigationDestination(for: DemoRoute.self) { route in
                    switch route {
                    case .versions: VersionsScreen(welcome: false)
                    case .people(let version): PeopleScreen(version: version)
                    }
                }
        }
        .tint(MP.brandInk)
        #if DEBUG
        // Simulator screenshots: `-MP_SHOW people` opens on the people of
        // the remembered version (or of `-MP_DEMO_VERSION`).
        .onAppear {
            if AppConfig.debugFlag("MP_SHOW") == "people", path.isEmpty { path = [.people(shell.version)] }
        }
        #endif
    }
}

// MARK: - Versions

/// The three versions as three large cards. `welcome` is the first-launch
/// screen (the fog, the lockup, the question); without it this is the same
/// list pushed inside the profile sheet.
struct VersionsScreen: View {
    let welcome: Bool
    @Environment(DemoShell.self) private var shell
    @State private var showServer = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if welcome {
                    lockup.padding(.top, 28).mpRise(0)
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Who do you want\nto be?")
                            .title(MPSize.displayM)
                            .accessibilityAddTraits(.isHeader)
                        Text("Everyone here is fictional. Pick a version of MedPull, then a person, and the app opens as them.")
                            .mpFont(.lede).foregroundStyle(MP.body).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.top, 26)
                    .mpRise(1)
                } else {
                    Text("The same demo, seen three ways. Pick a version, then a person.")
                        .mpFont(.copyLarge).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 4)
                }
                // A sign-in that did not happen at launch (`-MP_DEMO_PERSONA`,
                // or a link for someone this server does not know).
                if welcome, let error = shell.signInError {
                    ErrorBanner(text: error).padding(.top, 18)
                }
                VStack(spacing: 12) {
                    ForEach(Array(DemoVersion.allCases.enumerated()), id: \.element) { index, version in
                        versionCard(version).mpRise(index + 2)
                    }
                }
                .padding(.top, welcome ? 26 : 16)
                if case .failed(let message) = shell.rosterState {
                    RosterFailureCard(message: message) { showServer = true }
                        .padding(.top, 14)
                }
                if welcome {
                    serverLine.padding(.top, 22)
                }
            }
            .padding(.horizontal, welcome ? 22 : 18)
            .padding(.bottom, 28)
        }
        .refreshable { await shell.loadRoster() }
        // The site's hero canvas on first launch (taller, as on the real
        // app's Welcome); the usual sheet fog when pushed from the profile.
        .background { FogBackground(height: welcome ? 760 : 300) }
        .navigationTitle(welcome ? "Versions" : "Switch version")
        .navigationBarTitleDisplayMode(.inline)
        .task { await shell.loadRoster() }
        .sheet(isPresented: $showServer) { ServerAddressSheet() }
        .mpErrorFeedback(failure)
    }

    private var failure: String? {
        if case .failed(let message) = shell.rosterState { return message }
        return nil
    }

    /// The mark on its white tile, the wordmark, and the word that tells
    /// this app from the real one.
    private var lockup: some View {
        HStack(spacing: 12) {
            Image("MedPullMark")
                .resizable().scaledToFit()
                .padding(10)
                .frame(width: 56, height: 56)
                .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(.white)
                    .shadow(color: .black.opacity(0.18), radius: 14, y: 8))
                .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(Color.black.opacity(0.08), lineWidth: 0.5))
                .accessibilityHidden(true)
            Text("MedPull").mpFont(.subheadMedium).kerning(-0.6).foregroundStyle(MP.ink)
            HStack(spacing: 6) {
                LimeDot(size: 6)
                Text("Demo").mpFont(.labelMedium).foregroundStyle(MP.ink)
            }
            .padding(.horizontal, 10).padding(.vertical, 5)
            .glassSurface(MP.capsuleShape, solid: true, elevated: false)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("MedPull Demo")
    }

    private func versionCard(_ version: DemoVersion) -> some View {
        let group = shell.roster?.group(version)
        return NavigationLink(value: DemoRoute.people(version)) {
            Card {
                HStack(alignment: .top, spacing: 14) {
                    IconTile(version.symbol, family: version.family, size: 44)
                    VStack(alignment: .leading, spacing: 4) {
                        Text((Self.text(group?.label) ?? version.label).demoTypeset)
                            .mpFont(.ledeMedium).foregroundStyle(MP.ink)
                        Text((Self.text(group?.blurb) ?? version.blurb).demoTypeset)
                            .mpFont(.copy).mpSecondary().lineSpacing(2)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                        countLine(group).padding(.top, 4)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right")
                        .font(.systemGlyphs(13, weight: .semibold))
                        .foregroundStyle(MP.muted)
                        .padding(.top, 14)
                        .accessibilityHidden(true)
                }
            }
            .contentShape(MP.surfaceShape)
        }
        .buttonStyle(CardTapStyle())
        .accessibilityElement(children: .combine)
    }

    /// How many people the version has, or that the list is still coming.
    @ViewBuilder private func countLine(_ group: DemoVersionGroup?) -> some View {
        switch shell.rosterState {
        case .idle, .loading:
            HStack(spacing: 6) {
                ProgressView().controlSize(.mini).tint(MP.muted)
                Text("Finding people").mpFont(.label).foregroundStyle(MP.muted)
            }
        case .loaded:
            let n = group?.personaCount ?? 0
            StateLabel(text: n == 0 ? "Nobody yet" : n == 1 ? "1 person" : "\(n) people",
                       tone: n == 0 ? .missing : .brand)
        case .failed:
            EmptyView()
        }
    }

    /// Which server the list comes from, and the way to change it before
    /// anyone is signed in (afterwards it is in the profile sheet).
    private var serverLine: some View {
        HStack(spacing: 6) {
            Text("Server\(MP.dot)\(AppConfig.baseURL.host ?? AppConfig.baseURL.absoluteString)")
                .mpFont(.label).foregroundStyle(MP.body)
                .lineLimit(1).truncationMode(.middle)
            Button("Change") { showServer = true }
                .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                .controlSize(.small)
        }
        .frame(maxWidth: .infinity)
    }

    /// A label or blurb worth showing: not empty, and not a lone ellipsis.
    static func text(_ raw: String?) -> String? {
        guard let value = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty, value != "…", value != "..." else { return nil }
        return value
    }
}

/// The list could not be read: the sentence, a retry, and the server
/// address, which is the usual reason.
struct RosterFailureCard: View {
    let message: String
    var changeServer: (() -> Void)? = nil
    @Environment(DemoShell.self) private var shell
    @State private var retrying = false

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top, spacing: 12) {
                    Glyph(systemName: "wifi.exclamationmark", family: .blue, size: 40)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Can’t load the demo’s people")
                            .mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text(message)
                            .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 0)
                }
                PrimaryButton(title: "Try again", icon: "arrow.clockwise", loading: retrying) {
                    retrying = true
                    Task {
                        await shell.loadRoster()
                        retrying = false
                    }
                }
                if let changeServer {
                    Button("Change server", action: changeServer)
                        .buttonStyle(MPButtonStyle(kind: .plain, fullWidth: true))
                }
            }
        }
        .accessibilityElement(children: .contain)
    }
}

// MARK: - People

/// The people in one version, grouped by organisation, the one to open
/// first leading each group. Tapping a person signs in as them.
struct PeopleScreen: View {
    let version: DemoVersion
    /// Called when a session for the chosen person is in hand, just before
    /// the app becomes them (the profile sheet closes itself; the
    /// first-launch picker is simply replaced).
    var onPicked: () -> Void = {}
    @Environment(DemoShell.self) private var shell
    @Environment(AppModel.self) private var app
    @State private var showServer = false

    private var group: DemoVersionGroup? { shell.roster?.group(version) }
    private var orgs: [DemoOrg] { (group?.orgs ?? []).filter { !$0.personas.isEmpty } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text((VersionsScreen.text(group?.blurb) ?? version.blurb).demoTypeset)
                    .mpFont(.copyLarge).foregroundStyle(MP.body).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
                if let error = shell.signInError { ErrorBanner(text: error) }
                content
                Text("These people are made up for the demo. Their readings, messages and exercises are written by the demo server each morning.")
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
            }
            .padding(.horizontal, 18).padding(.top, 4).padding(.bottom, 28)
        }
        .refreshable { await shell.loadRoster() }
        .ambientScreen(height: 300)
        .mpNavigationTitle(VersionsScreen.text(group?.label) ?? version.label)
        .toolbarTitleDisplayMode(.large)
        .task { await shell.loadRoster() }
        .onAppear { shell.version = version }
        .sheet(isPresented: $showServer) { ServerAddressSheet() }
        .mpErrorFeedback(shell.signInError)
        #if DEBUG
        // Simulator verification: `-MP_PICK <persona id>` chooses that person
        // once the list is here, through the same call a tap on their row
        // makes.
        .task(id: shell.rosterState) {
            guard shell.rosterState == .loaded, !Self.debugPicked,
                  let id = AppConfig.debugFlag("MP_PICK"),
                  let persona = shell.roster?.persona(id), app.me?.patient.id != id else { return }
            Self.debugPicked = true
            try? await Task.sleep(for: .seconds(Double(AppConfig.debugFlag("MP_PICK_AFTER") ?? "") ?? 2))
            pick(persona)
        }
        #endif
    }

    #if DEBUG
    private static var debugPicked = false
    #endif

    @ViewBuilder private var content: some View {
        switch shell.rosterState {
        case .idle, .loading:
            LoadingCard(text: "Finding who’s on this demo…")
        case .failed(let message):
            RosterFailureCard(message: message) { showServer = true }
        case .loaded:
            if orgs.isEmpty {
                Card {
                    EmptyRow(icon: "person.2.fill", title: "Nobody here yet",
                             detail: "This demo has nobody in this version yet.")
                }
            } else {
                ForEach(orgs) { org in
                    orgSection(org)
                }
            }
        }
    }

    private func orgSection(_ org: DemoOrg) -> some View {
        let people = org.ordered
        let hero = people.first { $0.hero }
        let rest = people.filter { $0.id != hero?.id }
        return VStack(alignment: .leading, spacing: 10) {
            SectionTitle(org.name.demoTypeset, note: people.count == 1 ? "1 person" : "\(people.count) people")
                .padding(.top, 4)
            if let hero {
                Button { pick(hero) } label: { HeroPersonaCard(persona: hero, state: state(of: hero)) }
                    .buttonStyle(CardTapStyle())
                    .disabled(shell.signingIn != nil)
            }
            if !rest.isEmpty {
                Card(padding: 0) {
                    VStack(spacing: 0) {
                        ForEach(rest) { persona in
                            Button { pick(persona) } label: {
                                PersonaRow(persona: persona, state: state(of: persona))
                            }
                            .buttonStyle(.mpRow)
                            .disabled(shell.signingIn != nil)
                            if persona.id != rest.last?.id { InsetDivider(leading: 16 + 40 + 12) }
                        }
                    }
                }
                .clipShape(MP.surfaceShape)
            }
        }
    }

    private func state(of persona: DemoPersona) -> PersonaRowState {
        if shell.signingIn == persona.id { return .signingIn }
        if app.phase == .home, app.me?.patient.id == persona.id { return .current }
        return .idle
    }

    private func pick(_ persona: DemoPersona) {
        Task {
            guard let answer = await shell.session(for: persona) else { return }
            // In the profile sheet this closes it, and it is asked to close
            // while the screen it was opened from still exists: becoming
            // someone else rebuilds every tab under it.
            onPicked()
            shell.adopt(token: answer.sessionToken, me: answer.me)
        }
    }
}

enum PersonaRowState { case idle, signingIn, current }

/// What a demo person comes with, as three small glyphs: a wearable's
/// readings, assigned exercises, a message thread.
private struct PersonaHas: View {
    let has: DemoPersona.Has

    private var items: [(String, String)] {
        var list: [(String, String)] = []
        if has.wearable { list.append(("applewatch", "Wearable data")) }
        if has.exercises { list.append(("figure.strengthtraining.functional", "Exercises")) }
        if has.thread { list.append(("bubble.left.and.bubble.right.fill", "Messages")) }
        return list
    }

    var body: some View {
        if !items.isEmpty {
            HStack(spacing: 10) {
                ForEach(items, id: \.0) { item in
                    Label(item.1, systemImage: item.0)
                        .labelStyle(.titleAndIcon)
                        .mpFont(.label)
                        .foregroundStyle(MP.muted)
                        .lineLimit(1)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Has " + items.map(\.1).joined(separator: ", ").lowercased())
        }
    }
}

/// The trailing edge of a person: a spinner while their session is being
/// requested, "You" for whoever is signed in, otherwise the chevron.
private struct PersonaTrailing: View {
    let state: PersonaRowState

    var body: some View {
        switch state {
        case .signingIn:
            ProgressView().tint(MP.brand)
        case .current:
            StateLabel(text: "You now", tone: .brand)
        case .idle:
            Image(systemName: "chevron.right")
                .font(.systemGlyphs(13, weight: .semibold))
                .foregroundStyle(MP.faint)
                .accessibilityHidden(true)
        }
    }
}

/// The person to open first in an organisation: their own card, with the
/// day's story as a sentence.
private struct HeroPersonaCard: View {
    let persona: DemoPersona
    let state: PersonaRowState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .center, spacing: 14) {
                    Initials(text: persona.initials, size: 52,
                             tone: persona.chip?.tone == .high ? .high : .brand)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(persona.name).mpFont(.ledeMedium).foregroundStyle(MP.ink)
                            .multilineTextAlignment(.leading)
                        if !persona.tagline.isEmpty {
                            Text(persona.tagline.demoTypeset).mpFont(.copy).mpSecondary()
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    Spacer(minLength: 0)
                    PersonaTrailing(state: state)
                }
                if !persona.detail.isEmpty {
                    Text(persona.detail.demoTypeset)
                        .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(2)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 10) {
                        if let chip = persona.chip { StatusPill(text: chip.text, tone: chip.tone) }
                        PersonaHas(has: persona.has)
                        Spacer(minLength: 0)
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        if let chip = persona.chip { StatusPill(text: chip.text, tone: chip.tone) }
                        PersonaHas(has: persona.has)
                    }
                }
            }
        }
        .contentShape(MP.surfaceShape)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityHint("Opens the app as \(persona.name)")
    }
}

/// Everyone else in the organisation, as rows in one card.
private struct PersonaRow: View {
    let persona: DemoPersona
    let state: PersonaRowState

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Initials(text: persona.initials, size: 40,
                     tone: persona.chip?.tone == .high ? .high : .brand)
            VStack(alignment: .leading, spacing: 2) {
                Text(persona.name).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    .multilineTextAlignment(.leading)
                if !persona.tagline.isEmpty {
                    Text(persona.tagline.demoTypeset).mpFont(.label).foregroundStyle(MP.muted)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if !persona.detail.isEmpty {
                    Text(persona.detail.demoTypeset).mpFont(.label).foregroundStyle(MP.body)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let chip = persona.chip {
                    StateLabel(text: chip.text, tone: chip.tone).padding(.top, 2)
                }
            }
            Spacer(minLength: 8)
            PersonaTrailing(state: state)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 60)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint("Opens the app as \(persona.name)")
    }
}
