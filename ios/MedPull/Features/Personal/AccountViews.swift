import SwiftUI

/// A subscriber's account: the login, the morning reminder, the consent
/// they signed and the research switch inside it, and the way out. Every
/// row here is something a student athlete will look for on day one or
/// the day they leave, so it sits in Profile rather than behind a menu.
struct AccountCard: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismissProfile
    @State private var changingPassword = false
    @State private var readingConsent = false
    @State private var confirmingDelete = false
    @State private var deleting = false
    @State private var error: String?
    @State private var research = false
    @State private var loaded = false
    @State private var reminderOn = false
    @State private var reminderHour = 7

    private var reminders: Reminders { app.reminders }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    CardHeader("Account")
                    if let email = app.me?.patient.email {
                        row("Email", email, icon: "envelope.fill", family: .blue)
                        InsetDivider()
                    }
                    Button { changingPassword = true } label: {
                        actionLabel("Change password", icon: "key.fill", family: .indigo)
                    }
                    .buttonStyle(.mpRow)
                    InsetDivider()
                    Toggle(isOn: $reminderOn) {
                        HStack(spacing: 14) {
                            IconTile("sunrise.fill", family: .teal)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Morning reminder").mpFont(.copyLarge).foregroundStyle(MP.ink)
                                Text(reminders.denied
                                     ? "Notifications are off for MedPull in Settings."
                                     : "A nudge when last night is scored.")
                                    .mpFont(.label).foregroundStyle(MP.muted)
                            }
                        }
                    }
                    .tint(MP.brand)
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    .onChange(of: reminderOn) { _, on in
                        guard loaded else { return }
                        Task {
                            if on {
                                let ok = await reminders.enable(hour: reminderHour)
                                if !ok { reminderOn = false }
                            } else {
                                reminders.disable()
                            }
                        }
                    }
                    if reminderOn {
                        Picker("Reminder time", selection: $reminderHour) {
                            ForEach([5, 6, 7, 8, 9, 10], id: \.self) { h in
                                Text(Self.hourLabel(h)).tag(h)
                            }
                        }
                        .pickerStyle(.segmented)
                        .labelsHidden()
                        .padding(.horizontal, 16).padding(.bottom, 12)
                        .onChange(of: reminderHour) { _, h in
                            guard loaded, reminderOn else { return }
                            Task { await reminders.enable(hour: h) }
                        }
                        .mpSelectionFeedback(reminderHour)
                    }
                    InsetDivider()
                    Button { readingConsent = true } label: {
                        HStack(spacing: 14) {
                            IconTile("doc.text.fill", family: .violet)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Beta consent").mpFont(.copyLarge).foregroundStyle(MP.ink)
                                if let at = app.me?.consent?.acceptedAt {
                                    Text("Accepted \(ProfileView.displayDate(at))").mpFont(.label).foregroundStyle(MP.muted)
                                }
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                                .accessibilityHidden(true)
                        }
                        .padding(.horizontal, 16).frame(minHeight: 48)
                    }
                    .buttonStyle(.mpRow)
                    InsetDivider()
                    Toggle(isOn: $research) {
                        HStack(spacing: 14) {
                            IconTile("flask.fill", family: .indigo)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Help improve the readouts").mpFont(.copyLarge).foregroundStyle(MP.ink)
                                Text("De-identified data may be used in research. Optional.")
                                    .mpFont(.label).foregroundStyle(MP.muted)
                            }
                        }
                    }
                    .tint(MP.brand)
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    .onChange(of: research) { _, on in
                        guard loaded else { return }
                        Task {
                            do {
                                _ = try await app.api.setResearchUse(on)
                                await app.refreshMe(surface: false)
                            } catch {
                                self.error = AppModel.message(for: error)
                                research = !on
                            }
                        }
                    }
                    InsetDivider()
                    Button { confirmingDelete = true } label: {
                        HStack(spacing: 14) {
                            IconTile("trash.fill", family: .violet)
                            Text("Delete my account").mpFont(.copyLargeMedium).foregroundStyle(MP.riskHigh)
                            Spacer()
                            if deleting { ProgressView().controlSize(.small) }
                        }
                        .padding(.horizontal, 16).frame(minHeight: 48)
                    }
                    .buttonStyle(.mpRow)
                    .disabled(deleting)
                }
                .padding(.bottom, 4)
            }
            .clipShape(MP.surfaceShape)
            if let error { ErrorBanner(text: error) }
            Text("Deleting removes your login, readouts, log, consent record and files from MedPull’s storage. A paired hospital record, if you have one, is not touched. Cancel the subscription itself in the App Store.")
                .mpFont(.label).foregroundStyle(MP.muted)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 16)
        }
        .onAppear {
            research = app.me?.consent?.scopes?["research_use"] ?? false
            reminderOn = reminders.isOn
            reminderHour = reminders.hour ?? 7
            loaded = true
        }
        .sheet(isPresented: $changingPassword) { ChangePasswordSheet() }
        .sheet(isPresented: $readingConsent) { ConsentReadView() }
        .confirmationDialog("Delete your MedPull Personal account?", isPresented: $confirmingDelete,
                            titleVisibility: .visible) {
            Button("Delete everything", role: .destructive) { deleteAccount() }
            Button("Keep my account", role: .cancel) {}
        } message: {
            Text("This cannot be undone. Your readouts, log and files are removed from MedPull’s storage.")
        }
        .mpErrorFeedback(error)
    }

    private func deleteAccount() {
        deleting = true
        error = nil
        Task {
            defer { deleting = false }
            do {
                try await app.api.deletePersonalAccount()
                reminders.disable()
                await app.signOut()
                dismissProfile()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }

    private static func hourLabel(_ h: Int) -> String {
        var c = DateComponents(); c.hour = h
        let d = Calendar.current.date(from: c) ?? Date()
        return d.formatted(.dateTime.hour())
    }

    private func row(_ label: String, _ value: String, icon: String, family: MP.Category) -> some View {
        HStack(spacing: 14) {
            IconTile(icon, family: family)
            Text(label).mpFont(.copyLarge).foregroundStyle(MP.ink)
            Spacer(minLength: 12)
            Text(value).mpFont(.copy).foregroundStyle(MP.muted).lineLimit(1).minimumScaleFactor(0.7)
        }
        .padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 48)
        .accessibilityElement(children: .combine)
    }

    private func actionLabel(_ title: String, icon: String, family: MP.Category) -> some View {
        HStack(spacing: 14) {
            IconTile(icon, family: family)
            Text(title).mpFont(.copyLarge).foregroundStyle(MP.ink)
            Spacer()
            Image(systemName: "chevron.right")
                .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                .accessibilityHidden(true)
        }
        .padding(.horizontal, 16).frame(minHeight: 48)
    }
}

/// Current password, new password twice. The server checks the current one
/// and the minimum length; this only stops the obvious mistakes early.
struct ChangePasswordSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var current = ""
    @State private var new = ""
    @State private var again = ""
    @State private var show = false
    @State private var saving = false
    @State private var done = false
    @State private var error: String?
    @FocusState private var focus: Field?

    private enum Field { case current, new, again }

    private var problem: String? {
        if new.count < 8 { return "New password needs at least 8 characters." }
        if new != again { return "The two new passwords don’t match." }
        if new == current { return "Choose a password you haven’t used here." }
        return nil
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Change your password").title(MPSize.displayS)
                    field("Current password", text: $current, content: .password, field: .current) { focus = .new }
                    field("New password (8+ characters)", text: $new, content: .newPassword, field: .new) { focus = .again }
                    field("New password again", text: $again, content: .newPassword, field: .again) { save() }
                    Toggle("Show passwords", isOn: $show).tint(MP.brand)
                        .mpFont(.copy).foregroundStyle(MP.body)
                    if let error { ErrorBanner(text: error) }
                    if done {
                        Card(tint: true) {
                            HStack(spacing: 10) {
                                Image(systemName: "checkmark.seal.fill").foregroundStyle(MP.riskLow)
                                Text("Password changed.").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            }
                        }
                    } else {
                        if !new.isEmpty || !again.isEmpty, let problem {
                            Text(problem).mpFont(.label).foregroundStyle(MP.muted)
                        }
                        PrimaryButton(title: "Save new password", icon: "checkmark", loading: saving,
                                      disabled: current.isEmpty || problem != nil) { save() }
                    }
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .scrollDismissesKeyboard(.interactively)
            .ambientScreen()
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium)
                }
            }
            .onAppear { focus = .current }
            .mpCompletionFeedback(done)
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    @ViewBuilder
    private func field(_ title: String, text: Binding<String>, content: UITextContentType, field: Field,
                       onSubmit: @escaping () -> Void) -> some View {
        Group {
            if show {
                TextField(title, text: text, prompt: Text(title).foregroundColor(MP.muted))
            } else {
                SecureField(title, text: text, prompt: Text(title).foregroundColor(MP.muted))
            }
        }
        .textFieldStyle(FieldStyle())
        .textContentType(content)
        .textInputAutocapitalization(.never).autocorrectionDisabled()
        .focused($focus, equals: field)
        .submitLabel(field == .again ? .done : .next)
        .onSubmit(onSubmit)
    }

    private func save() {
        guard !current.isEmpty, problem == nil else { return }
        saving = true
        error = nil
        Task {
            defer { saving = false }
            do {
                try await app.api.changePassword(current: current, new: new)
                done = true
                try? await Task.sleep(for: .seconds(1.2))
                dismiss()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

/// For a hospital record: the consent they accepted, readable any time.
struct ConsentRow: View {
    @Environment(AppModel.self) private var app
    @State private var reading = false

    var body: some View {
        Button { reading = true } label: {
            HStack(spacing: 14) {
                IconTile("doc.text.fill", family: .violet)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Beta consent").mpFont(.copyLarge).foregroundStyle(MP.ink)
                    if let at = app.me?.consent?.acceptedAt {
                        Text("Accepted \(ProfileView.displayDate(at))").mpFont(.label).foregroundStyle(MP.muted)
                    }
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                    .accessibilityHidden(true)
            }
            .padding(.horizontal, 16).frame(minHeight: 48)
        }
        .buttonStyle(.mpRow)
        .sheet(isPresented: $reading) { ConsentReadView() }
    }
}
