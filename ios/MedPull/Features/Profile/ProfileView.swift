import SwiftUI
import UIKit

/// The profile sheet, on the same bordered cards as Home, Tasks and Health:
/// one `Card(padding: 0)` per group, a quiet `CardHeader` inside it, rows
/// split by `InsetDivider`s, and footers as muted text under the card.
///
/// Contrast (computed): rows are `panel` on a `canvas` sheet. Row labels are
/// `ink` (18.377 / 17.194 on panel), values and card headers `muted` (5.393 /
/// 4.906), footers `muted` on canvas (5.025 / 5.243) — SF's secondaryLabel
/// measures 3.29:1 there, so nothing here uses it. Buttons are `brandInk`
/// (5.746 / 6.783); Sign out is `riskHigh` (5.622 / 7.563), because system red
/// on white is 3.55:1.
struct ProfileView: View {
    private var voice: SpokenVoice { SpokenVoice.shared }
    @Environment(AppModel.self) private var app
    @Environment(Appearance.self) private var appearance
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var serverURL = AppConfig.baseURL.absoluteString
    @State private var signingOut = false

    var body: some View {
        @Bindable var appearance = appearance
        return NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    if let me = app.me {
                        aboutCard(me)
                        if !me.patient.careTeam.isEmpty {
                            group("Care team") {
                                ForEach(Array(me.patient.careTeam.enumerated()), id: \.offset) { i, m in
                                    if i > 0 { InsetDivider(leading: 16) }
                                    row(m.role.capitalized, m.name)
                                }
                            }
                        }
                        group("Connections",
                              footer: "Task texts come from your care team's MedPull number. Reply 1 to any of them to do the task by text, or open it here.") {
                            row("Texts from MedPull", me.features.sms ? "On" : "Not set up on this server",
                                icon: "message.fill", family: .blue)
                            InsetDivider()
                            row("Apple Health",
                                app.health.isConnected || me.wearables.appleHealth.connected ? "Connected" : "Not connected",
                                icon: "heart.fill", family: .violet)
                        }
                    }

                    group("Appearance", footer: "System follows your iPhone's Display & Brightness setting.") {
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

                    // No API can download a voice, so the footer has to say so
                    // and say exactly where it is.
                    group("Voice", footer: voice.advice) {
                        // Read through the observable so this row updates the
                        // moment the voice changes — the person is coming
                        // straight back from Settings having just downloaded
                        // one, and a stale label here looks like a failure.
                        row("Spoken replies", voice.label, icon: "waveform", family: .indigo)
                        if !voice.hasWantedVoice {
                            InsetDivider()
                            actionRow("Open Settings") {
                                if let url = URL(string: UIApplication.openSettingsURLString) {
                                    UIApplication.shared.open(url)
                                }
                            }
                        }
                    }

                    group("Developer",
                          footer: "Where this app talks to. On a phone running against `make dev`, use your Mac's address, e.g. http://192.168.1.20:8000. Built-in: \(AppConfig.builtInBaseURL.absoluteString)") {
                        // The placeholder goes through `prompt:` so it lands on
                        // `MP.muted` (5.39:1) instead of the system tertiary
                        // label, which measures 1.72:1 — a placeholder is text.
                        TextField("Server URL", text: $serverURL,
                                  prompt: Text("Server URL").foregroundColor(MP.muted))
                            .mpFont(.copyLarge)
                            .foregroundStyle(MP.ink)
                            .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                            .onSubmit { saveServer() }
                            .padding(.horizontal, 16)
                            .frame(minHeight: 48)
                        InsetDivider(leading: 16)
                        actionRow("Save server") { saveServer() }
                    }

                    group(nil) {
                        Button {
                            signingOut = true
                            Task { await app.signOut(); dismiss() }
                        } label: {
                            HStack {
                                Text("Sign out").mpFont(.copyLargeMedium)
                                Spacer()
                                if signingOut { ProgressView().tint(MP.muted) }
                            }
                            .foregroundStyle(MP.riskHigh)
                            .padding(.horizontal, 16)
                            .frame(minHeight: 50)
                        }
                        .buttonStyle(.mpRow)
                        .disabled(signingOut)
                    }
                }
                .padding(.horizontal, 18)
                .padding(.top, 8)
                .padding(.bottom, 28)
            }
            .screen()
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
        // Large only: a medium detent put the sheet over the dimmed Home at
        // 2.99:1.
        .presentationDetents([.large])
    }

    // MARK: Pieces

    /// Identity on top, then the facts about this patient's enrolment, in one
    /// card.
    private func aboutCard(_ me: Me) -> some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 14) {
                    Initials(text: me.patient.initials, size: 56)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(me.patient.name)
                            .mpFont(.subheadSemibold).foregroundStyle(MP.ink)
                        Text(me.patient.procedureDisplay)
                            .mpFont(.copy).foregroundStyle(MP.muted)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                }
                .padding(16)
                .accessibilityElement(children: .combine)

                InsetDivider(leading: 16)
                if me.patient.isRecovery, let surgery = me.patient.surgeryDate {
                    row("Surgery", Self.displayDate(surgery))
                    InsetDivider(leading: 16)
                    row("Post-op day", "\(me.patient.postopDay ?? 0)")
                } else {
                    row("Joined", Self.displayDate(me.patient.joinedDate))
                }
                if let h = me.patient.hospital {
                    InsetDivider(leading: 16)
                    row("Hospital", h.name)
                }
                if let p = me.patient.phoneMasked {
                    InsetDivider(leading: 16)
                    row("Mobile", p)
                }
            }
            .padding(.bottom, 4)
        }
        .clipShape(MP.surfaceShape)
    }

    /// A titled card with an optional footer under it.
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
            // Row press fills stop at the card's corners.
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

    private func row(_ label: String, _ value: String,
                     icon: String? = nil, family: MP.Category = .blue) -> some View {
        let labelView = HStack(spacing: 14) {
            if let icon { IconTile(icon, family: family) }
            Text(label)
                .mpFont(.copyLarge)
                .foregroundStyle(MP.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
        let valueView = Text(value)
            .mpFont(.copyLarge)
            .foregroundStyle(MP.muted)
            .fixedSize(horizontal: false, vertical: true)
        return Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 4) {
                    labelView
                    valueView
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                HStack(spacing: 12) {
                    labelView
                    Spacer(minLength: 12)
                    valueView.multilineTextAlignment(.trailing)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .frame(minHeight: 48)
        .accessibilityElement(children: .combine)
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

    /// "2026-08-28" -> "Aug 28, 2026" in the reader's locale. A string that
    /// is not an ISO day comes back unchanged.
    static func displayDate(_ iso: String) -> String {
        let parser = DateFormatter()
        parser.calendar = Calendar(identifier: .gregorian)
        parser.locale = Locale(identifier: "en_US_POSIX")
        parser.timeZone = .current
        parser.dateFormat = "yyyy-MM-dd"
        guard let date = parser.date(from: String(iso.prefix(10))) else { return iso }
        return date.formatted(.dateTime.month(.abbreviated).day().year())
    }

    private func saveServer() {
        if let url = URL(string: serverURL.trimmingCharacters(in: .whitespaces)), url.scheme != nil {
            AppConfig.baseURL = url
            Task { await app.refreshAll() }
        }
    }
}
