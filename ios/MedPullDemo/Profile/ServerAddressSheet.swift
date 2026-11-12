import SwiftUI

/// Which server the demo app asks for its people. Built against the demo
/// stack; a presenter running the API on a laptop points it there instead.
/// Reached from the picker before anyone is signed in, and from the profile
/// sheet afterwards.
struct ServerAddressSheet: View {
    @Environment(DemoShell.self) private var shell
    @Environment(\.dismiss) private var dismiss
    @State private var address = AppConfig.baseURL.absoluteString
    @State private var problem: String?
    @FocusState private var focused: Bool

    /// True when an address saved on this phone is in use rather than the
    /// one the app was built with.
    private var overridden: Bool { AppConfig.baseURL != AppConfig.builtInBaseURL }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Where this app finds the demo’s people and their data. For a laptop running the API, use its address on your network, for example http://192.168.1.20:8000.")
                        .mpFont(.copyLarge).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    // The placeholder goes through `prompt:` so it lands on
                    // `MP.muted`, as in the real Profile.
                    TextField("Server address", text: $address,
                              prompt: Text(AppConfig.builtInBaseURL.absoluteString).foregroundColor(MP.muted))
                        .textFieldStyle(FieldStyle())
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .focused($focused)
                        .onSubmit { save() }
                        .accessibilityLabel("Server address")
                    if let problem { ErrorBanner(text: problem) }
                    PrimaryButton(title: "Use this server") { save() }
                    if overridden {
                        Button("Go back to \(AppConfig.builtInBaseURL.host ?? "the built-in server")") {
                            apply(nil)
                        }
                        .buttonStyle(MPButtonStyle(kind: .plain, fullWidth: true))
                    }
                    Text("Built in: \(AppConfig.builtInBaseURL.absoluteString). Changing the server signs the app out of anyone the new server does not know.")
                        .mpFont(.label).foregroundStyle(MP.muted)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 4)
                }
                .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
            }
            .scrollDismissesKeyboard(.interactively)
            .ambientScreen(height: 300)
            .navigationTitle("Server address")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if #available(iOS 26, *) {
                        Button(role: .close) { dismiss() }
                    } else {
                        Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium)
                    }
                }
            }
            .mpErrorFeedback(problem)
        }
        .presentationDetents([.large])
    }

    private func save() {
        let trimmed = address.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed), let scheme = url.scheme?.lowercased(),
              scheme == "https" || scheme == "http", url.host != nil else {
            problem = "That isn’t a server address. It starts with https:// or http://."
            return
        }
        apply(url)
    }

    /// `nil` goes back to the address the app was built with.
    private func apply(_ url: URL?) {
        problem = nil
        shell.useServer(url)
        dismiss()
    }
}
