import SwiftUI

/// The beta consent form: the words the server publishes, one switch per
/// permission (the required ones locked on, the research one a real
/// choice), a typed name as signature, and Agree. Used in onboarding before
/// any account exists, and as a gate over the app for an account that
/// predates the form or meets a new version.
struct ConsentForm: View {
    let document: ConsentDocument
    /// What the person has agreed to so far. Nil until they tap Agree.
    var onAgree: (ConsentAcceptance) -> Void
    var busy: Bool = false
    var error: String? = nil
    @State private var scopes: [String: Bool] = [:]
    @State private var signature = ""
    @State private var readAll = false
    @FocusState private var signing: Bool

    private var requiredMet: Bool {
        document.scopes.filter(\.required).allSatisfy { scopes[$0.key] == true }
    }
    private var canAgree: Bool {
        requiredMet && signature.trimmingCharacters(in: .whitespaces).count >= 2 && !busy
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 8) {
                StatusPill(text: "Beta", tone: .med)
                Text("Version \(document.version)").mpFont(.label).foregroundStyle(MP.muted)
            }
            Text("Before we start")
                .title(MPSize.displayS)
                .accessibilityAddTraits(.isHeader)
            Text("MedPull is a beta. Please read what we collect, where it goes and what you can do about it, then tick what you agree to and sign with your name.")
                .mpFont(.copyLarge).foregroundStyle(MP.body).lineSpacing(2)
                .fixedSize(horizontal: false, vertical: true)

            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    CardHeader("The form")
                    ForEach(Array(paragraphs.enumerated()), id: \.offset) { i, para in
                        if i < (readAll ? paragraphs.count : 3) {
                            Text(para.typeset)
                                .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(3)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(.horizontal, 16).padding(.bottom, 10)
                        }
                    }
                    if paragraphs.count > 3 {
                        Button(readAll ? "Show less" : "Read the whole form") { readAll.toggle() }
                            .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                            .padding(.horizontal, 16).padding(.bottom, 12)
                    }
                }
            }

            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    CardHeader("What you agree to")
                    ForEach(Array(document.scopes.enumerated()), id: \.element.key) { i, scope in
                        Toggle(isOn: Binding(
                            get: { scopes[scope.key] ?? false },
                            set: { scopes[scope.key] = $0 }
                        )) {
                            VStack(alignment: .leading, spacing: 3) {
                                HStack(spacing: 6) {
                                    Text(scope.label.typeset).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                Text(scope.detail.typeset).mpFont(.label).foregroundStyle(MP.muted)
                                    .fixedSize(horizontal: false, vertical: true)
                                if scope.required {
                                    Text("Needed to use MedPull").mpFont(.label).foregroundStyle(MP.brandInk)
                                } else {
                                    Text("Your choice. Change it later in Profile.").mpFont(.label).foregroundStyle(MP.muted)
                                }
                            }
                            .padding(.trailing, 8)
                        }
                        .tint(MP.brand)
                        .padding(.horizontal, 16).padding(.vertical, 12)
                        if i < document.scopes.count - 1 { InsetDivider(leading: 16) }
                    }
                }
                .padding(.bottom, 4)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Sign with your full name").mpFont(.labelMedium).foregroundStyle(MP.muted)
                TextField("Full name", text: $signature,
                          prompt: Text("Full name").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle())
                    .textContentType(.name).autocorrectionDisabled()
                    .focused($signing)
            }
            if let error { ErrorBanner(text: error) }
            PrimaryButton(title: "Agree and continue", icon: "checkmark", loading: busy, disabled: !canAgree) {
                let accepted = ConsentAcceptance(
                    version: document.version,
                    scopes: Dictionary(uniqueKeysWithValues: document.scopes.map { ($0.key, scopes[$0.key] ?? false) }),
                    signature: signature.trimmingCharacters(in: .whitespaces))
                onAgree(accepted)
            }
            Text("Guidance for training and recovery — not medical advice. Questions: hello@medpull.org.")
                .mpFont(.label).foregroundStyle(MP.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .onAppear {
            if scopes.isEmpty {
                // Every permission starts on, including the optional one:
                // the choice is presented, and the row says it can be
                // turned off here or later.
                scopes = Dictionary(uniqueKeysWithValues: document.scopes.map { ($0.key, true) })
            }
        }
    }

    private var paragraphs: [String] {
        document.text.components(separatedBy: "\n\n").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }
}

/// Loads the form and shows it. The onboarding step and the gate both use it.
struct ConsentLoader<Footer: View>: View {
    @Environment(AppModel.self) private var app
    let onAgree: (ConsentAcceptance) async throws -> Void
    @ViewBuilder var footer: () -> Footer
    @State private var document: ConsentDocument?
    @State private var loadError: String?
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let document {
                    ConsentForm(document: document, onAgree: { accepted in
                        busy = true
                        error = nil
                        Task {
                            defer { busy = false }
                            do { try await onAgree(accepted) } catch { self.error = AppModel.message(for: error) }
                        }
                    }, busy: busy, error: error)
                } else if let loadError {
                    ErrorBanner(text: loadError)
                    SecondaryButton(title: "Try again", icon: "arrow.clockwise") { Task { await load() } }
                } else {
                    HStack(spacing: 12) {
                        ProgressView().tint(MP.brand)
                        Text("Loading the form…").mpFont(.copyLarge).foregroundStyle(MP.body)
                    }
                    .padding(.top, 24)
                }
                footer()
            }
            .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
        .task { await load() }
    }

    private func load() async {
        loadError = nil
        do { document = try await app.api.consentDocument() } catch { loadError = AppModel.message(for: error) }
    }
}

/// The gate: an account signed in without a current consent sees the form
/// and nothing else until it agrees. Signing out is the only other door.
struct ConsentGate: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        NavigationStack {
            ConsentLoader(onAgree: { accepted in
                try await app.acceptConsent(accepted)
            }) {
                Button("Sign out instead") { Task { await app.signOut() } }
                    .buttonStyle(MPButtonStyle(kind: .plain, fullWidth: true))
            }
            .ambientScreen()
            .navigationTitle("Consent")
            .navigationBarTitleDisplayMode(.inline)
            .interactiveDismissDisabled()
        }
        .tint(MP.brandInk)
    }
}

/// The consent, read back from Profile.
struct ConsentReadView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var document: ConsentDocument?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if let status = app.me?.consent, let at = status.acceptedAt {
                        Card(tint: true) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Accepted \(ProfileView.displayDate(at))").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                Text("Version \(status.version ?? "—")").mpFont(.label).mpSecondary()
                            }
                        }
                    }
                    if let document {
                        ForEach(Array(document.text.components(separatedBy: "\n\n").enumerated()), id: \.offset) { _, para in
                            Text(para.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(3)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    } else {
                        ProgressView().tint(MP.brand)
                    }
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .ambientScreen()
            .navigationTitle("Consent")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }.mpFont(.copyLargeMedium)
                }
            }
            .task { document = try? await app.api.consentDocument() }
        }
    }
}
