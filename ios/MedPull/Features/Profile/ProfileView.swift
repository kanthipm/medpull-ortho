import SwiftUI
import UIKit

/// The profile sheet: a native inset-grouped list on the app's own grounds.
///
/// Contrast (computed): rows are `panel` on a `canvas` list. Row labels are
/// `ink` (18.377 / 17.194 on panel), values `muted` (5.393 / 4.906), section
/// headers and footers `muted` on canvas (5.025 / 5.243) — SF's
/// secondaryLabel measures 3.29:1 there, so nothing here uses it. Buttons are
/// `brandInk` (5.746 / 6.783); Sign out is `riskHigh` (5.622 / 7.563), because
/// system red on white is 3.55:1.
struct ProfileView: View {
    private var voice: SpokenVoice { SpokenVoice.shared }
    @Environment(AppModel.self) private var app
    @Environment(Appearance.self) private var appearance
    @Environment(\.dismiss) private var dismiss
    @State private var serverURL = AppConfig.baseURL.absoluteString
    @State private var signingOut = false

    var body: some View {
        @Bindable var appearance = appearance
        return NavigationStack {
            List {
                if let me = app.me {
                    Section {
                        identity(me)
                        if me.patient.isRecovery, let surgery = me.patient.surgeryDate {
                            row("Surgery", surgery)
                            row("Post-op day", "\(me.patient.postopDay ?? 0)")
                        } else {
                            row("Joined", me.patient.joinedDate)
                        }
                        if let h = me.patient.hospital { row("Hospital", h.name) }
                        if let p = me.patient.phoneMasked { row("Mobile", p) }
                    }
                    if !me.patient.careTeam.isEmpty {
                        Section {
                            ForEach(me.patient.careTeam, id: \.self) { m in
                                row(m.role.capitalized, m.name)
                            }
                        } header: {
                            header("Care team")
                        }
                    }
                    Section {
                        row("Texts from MedPull", me.features.sms ? "On" : "Not set up on this server",
                            icon: "message.fill", family: .blue)
                        row("Apple Health",
                            app.health.isConnected || me.wearables.appleHealth.connected ? "Connected" : "Not connected",
                            icon: "heart.fill", family: .violet)
                    } header: {
                        header("Connections")
                    } footer: {
                        footer("Task texts come from your care team's MedPull number. Reply 1 to any of them to do the task by text, or open it here.")
                    }
                }
                Section {
                    Picker("Appearance", selection: $appearance.mode) {
                        ForEach(AppearanceMode.allCases) { mode in
                            Text(mode.label).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                    .mpSelectionFeedback(appearance.mode)
                    .listRowBackground(MP.panel)
                } header: {
                    header("Appearance")
                } footer: {
                    footer("System follows your iPhone's Display & Brightness setting.")
                }
                Section {
                    // Read through the observable so this row updates the
                    // moment the voice changes — the person is coming straight
                    // back from Settings having just downloaded one, and a
                    // stale label here is what makes it look like it failed.
                    row("Spoken replies", voice.label, icon: "waveform", family: .indigo)
                    if !voice.hasWantedVoice {
                        Button("Open Settings") {
                            if let url = URL(string: UIApplication.openSettingsURLString) {
                                UIApplication.shared.open(url)
                            }
                        }
                        .mpFont(.copyLarge)
                        .listRowBackground(MP.panel)
                    }
                } header: {
                    header("Voice")
                } footer: {
                    // No API can download a voice, so the copy has to say so
                    // and say exactly where it is.
                    footer(voice.advice)
                }
                Section {
                    // The placeholder goes through `prompt:` so it lands on
                    // `MP.muted` (5.39:1) instead of the system tertiary
                    // label, which measures 1.72:1 — a placeholder is text.
                    TextField("Server URL", text: $serverURL,
                              prompt: Text("Server URL").foregroundColor(MP.muted))
                        .mpFont(.copyLarge)
                        .foregroundStyle(MP.ink)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .onSubmit { saveServer() }
                        .listRowBackground(MP.panel)
                    Button("Save server") { saveServer() }
                        .mpFont(.copyLarge)
                        .listRowBackground(MP.panel)
                } header: {
                    header("Developer")
                } footer: {
                    footer("Where this app talks to. On a phone running against `make dev`, use your Mac's address, e.g. http://192.168.1.20:8000. Built-in: \(AppConfig.builtInBaseURL.absoluteString)")
                }
                Section {
                    Button(role: .destructive) {
                        signingOut = true
                        Task { await app.signOut(); dismiss() }
                    } label: {
                        HStack {
                            Text("Sign out").mpFont(.copyLarge)
                            Spacer()
                            if signingOut { ProgressView().tint(MP.muted) }
                        }
                        .foregroundStyle(MP.riskHigh)
                        .frame(maxWidth: .infinity)
                    }
                    .disabled(signingOut)
                    .listRowBackground(MP.panel)
                }
            }
            .listStyle(.insetGrouped)
            .scrollContentBackground(.hidden)
            .background(MP.canvas.ignoresSafeArea())
            .listRowSeparatorTint(MP.hairline)
            .tint(MP.brandInk)
            .mpNavigationTitle("Profile")
            .navigationBarTitleDisplayMode(.inline)
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
        }
        // Large only: a medium detent put the list over the dimmed Home at
        // 2.99:1.
        .presentationDetents([.large])
    }

    // MARK: Pieces

    private func identity(_ me: Me) -> some View {
        HStack(spacing: 14) {
            Initials(text: me.patient.initials, size: 56)
            VStack(alignment: .leading, spacing: 2) {
                Text(me.patient.name)
                    .mpFont(.subheadSemibold).foregroundStyle(MP.ink)
                    .alignmentGuide(.listRowSeparatorLeading) { d in d[.leading] }
                Text(me.patient.procedureDisplay)
                    .mpFont(.copy).foregroundStyle(MP.muted)
            }
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
        .listRowBackground(MP.panel)
    }

    private func header(_ text: String) -> some View {
        Text(text)
            .mpFont(.labelMedium)
            .foregroundStyle(MP.muted)
            .textCase(nil)
    }

    private func footer(_ text: String) -> some View {
        Text(text)
            .mpFont(.label)
            .foregroundStyle(MP.muted)
    }

    private func row(_ label: String, _ value: String,
                     icon: String? = nil, family: MP.Category = .blue) -> some View {
        LabeledContent {
            Text(value)
                .mpFont(.copyLarge)
                .foregroundStyle(MP.muted)
                .multilineTextAlignment(.trailing)
        } label: {
            HStack(spacing: 12) {
                if let icon { IconTile(icon, family: family, size: 28) }
                Text(label)
                    .mpFont(.copyLarge)
                    .foregroundStyle(MP.ink)
                    .alignmentGuide(.listRowSeparatorLeading) { d in d[.leading] }
            }
        }
        .accessibilityElement(children: .combine)
        .listRowBackground(MP.panel)
    }

    private func saveServer() {
        if let url = URL(string: serverURL.trimmingCharacters(in: .whitespaces)), url.scheme != nil {
            AppConfig.baseURL = url
            Task { await app.refreshAll() }
        }
    }
}
