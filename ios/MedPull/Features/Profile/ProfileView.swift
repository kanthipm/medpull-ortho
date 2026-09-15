import SwiftUI

struct ProfileView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var serverURL = AppConfig.baseURL.absoluteString
    @State private var signingOut = false

    var body: some View {
        NavigationStack {
            List {
                if let me = app.me {
                    Section {
                        HStack(spacing: 14) {
                            Initials(text: me.patient.initials, size: 48)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(me.patient.name).font(.system(size: 17, weight: .semibold))
                                Text(me.patient.procedureDisplay).font(.system(size: 13)).foregroundStyle(MP.muted)
                            }
                        }
                        .padding(.vertical, 4)
                        if me.patient.isRecovery, let surgery = me.patient.surgeryDate {
                            row("Surgery", surgery)
                            row("Post-op day", "\(me.patient.postopDay ?? 0)")
                        } else {
                            row("Joined", me.patient.joinedDate)
                        }
                        if let h = me.patient.hospital { row("Hospital", h.name) }
                        if let p = me.patient.phoneMasked { row("Mobile", p) }
                    }
                    Section("Care team") {
                        ForEach(me.patient.careTeam, id: \.self) { m in
                            row(m.role.capitalized, m.name)
                        }
                    }
                    Section {
                        row("Texts from MedPull", me.features.sms ? "On" : "Not set up on this server")
                        row("Apple Health", app.health.isConnected || me.wearables.appleHealth.connected ? "Connected" : "Not connected")
                    } footer: {
                        Text("Task texts come from your care team's MedPull number. Reply 1 to any of them to do the task by text, or open it here.")
                    }
                }
                Section {
                    TextField("Server URL", text: $serverURL)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .onSubmit { saveServer() }
                    Button("Save server") { saveServer() }
                } header: {
                    Text("Developer")
                } footer: {
                    Text("Where this app talks to. On a phone running against `make dev`, use your Mac's address, e.g. http://192.168.1.20:8000. Built-in: \(AppConfig.builtInBaseURL.absoluteString)")
                }
                Section {
                    Button(role: .destructive) {
                        signingOut = true
                        Task { await app.signOut(); dismiss() }
                    } label: {
                        HStack { Text("Sign out"); if signingOut { Spacer(); ProgressView() } }
                    }
                }
            }
            .navigationTitle("Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).foregroundStyle(MP.muted)
            Spacer()
            Text(value).foregroundStyle(MP.ink).multilineTextAlignment(.trailing)
        }
        .font(.system(size: 15))
    }

    private func saveServer() {
        if let url = URL(string: serverURL.trimmingCharacters(in: .whitespaces)), url.scheme != nil {
            AppConfig.baseURL = url
            Task { await app.refreshAll() }
        }
    }
}
