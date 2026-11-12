import SwiftUI

/// "Text my phone": bind the presenter's own number to the person the app
/// is being, so the texts the demo sends to that person arrive on a real
/// phone (`GET | POST | DELETE /api/demo/phone`, authorised by the
/// persona's session).
///
/// The demo's text line is on Sendblue's free plan, which cannot start a
/// conversation: a number is reachable only after it has texted the line
/// once. So after binding, the sheet may ask for that one text (the words
/// are already written), then polls until the server has seen it, as the
/// real app's verification step does.
struct TextMyPhoneSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    private enum Stage: Equatable {
        case loading
        /// The route is missing on this server (404), or the first read failed.
        case unavailable(String)
        case ready
    }

    @State private var stage: Stage = .loading
    @State private var phone: DemoPhoneState?
    @State private var number = ""
    @State private var working = false
    @State private var problem: String?
    @FocusState private var focused: Bool

    private var firstName: String { app.me?.patient.firstName ?? "this person" }
    private var waitingForText: Bool { (phone?.isBound ?? false) && !(phone?.reachable ?? false) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    switch stage {
                    case .loading:
                        LoadingCard(text: "Checking this person’s phone…")
                    case .unavailable(let message):
                        unavailable(message)
                    case .ready:
                        if let phone, phone.isBound {
                            if phone.reachable { connected(phone) } else { textFirst(phone) }
                        } else {
                            form
                        }
                    }
                    if let problem { ErrorBanner(text: problem) }
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .scrollDismissesKeyboard(.interactively)
            .ambientScreen(height: 300)
            .navigationTitle("Text my phone")
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
            .task {
                await load()
                #if DEBUG
                // Simulator verification: `-MP_PHONE <number>` types the
                // number and presses "Use this number".
                if stage == .ready, !(phone?.isBound ?? false), let typed = AppConfig.debugFlag("MP_PHONE") {
                    number = typed
                    try? await Task.sleep(for: .seconds(1.5))
                    bind()
                }
                #endif
            }
            // While the server waits for the first text: ask every three
            // seconds, so the sheet moves on without another tap.
            .task(id: waitingForText) {
                while !Task.isCancelled && waitingForText {
                    try? await Task.sleep(for: .seconds(3))
                    guard !Task.isCancelled else { return }
                    if let latest = try? await app.api.demoPhone() { phone = latest }
                }
            }
            .mpErrorFeedback(problem)
            .mpCompletionFeedback(phone?.reachable ?? false)
        }
        .presentationDetents([.large])
    }

    // MARK: Enter a number

    private var form: some View {
        VStack(alignment: .leading, spacing: 14) {
            heading("Send \(firstName)’s texts\nto your phone",
                    "Enter your own mobile number. The texts this demo sends to \(firstName) will arrive on it, with links that open this app at the right screen.")
            // `FieldStyle` sets the font and colours.
            TextField("Mobile number", text: $number,
                      prompt: Text("(713) 555-0142").foregroundColor(MP.muted))
                .textFieldStyle(FieldStyle())
                .keyboardType(.phonePad).textContentType(.telephoneNumber)
                .focused($focused)
                .accessibilityLabel("Mobile number")
            PrimaryButton(title: "Use this number", loading: working,
                          disabled: PhoneNumber.normalized(number) == nil) { bind() }
            Text("The number is kept on the demo server, on \(firstName)’s fictional chart, until you remove it here. Binding it takes it off any other demo person.")
                .mpFont(.label).foregroundStyle(MP.muted)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 4)
        }
    }

    // MARK: Text us first

    private func textFirst(_ state: DemoPhoneState) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            heading("Text us first",
                    "Before the demo can text \(PhoneNumber.display(state.phone)), send it one message from that phone. Tap below (the text is already written), send it, then come back here.")
            if let line = state.textTo, !line.isEmpty {
                Card {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Text “\(state.textBody ?? "Hi MedPull")” to")
                            .mpFont(.label).mpSecondary()
                        Text(PhoneNumber.display(line))
                            .mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            .textSelection(.enabled)
                        HStack(spacing: 8) {
                            ProgressView().controlSize(.small).tint(MP.brand)
                            Text("Waiting for your text. This screen moves on by itself.")
                                .mpFont(.copy).foregroundStyle(MP.body)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(.top, 4)
                    }
                }
                PrimaryButton(title: "Open Messages", icon: "message.fill") {
                    if let url = PhoneNumber.smsURL(to: line, body: state.textBody ?? "Hi MedPull") { openURL(url) }
                }
                SecondaryButton(title: "I’ve sent it", loading: working) { check() }
            } else {
                ErrorBanner(text: (state.detail ?? "This server has no text line set up, so it can’t reach a phone yet.").typeset)
            }
            Button("Use a different number") { unbind() }
                .buttonStyle(MPButtonStyle(kind: .plain, fullWidth: true))
                .disabled(working)
        }
    }

    // MARK: Connected

    private func connected(_ state: DemoPhoneState) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            IconTile("checkmark", family: .teal, size: 44)
            heading("You’re connected",
                    "Texts from this demo now reach this phone.")
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    ListRow("Your phone", subtitle: "Bound to \(app.me?.patient.name ?? firstName)",
                            symbol: "iphone", family: .blue, chevron: false) {
                        Text(PhoneNumber.display(state.phone))
                            .mpFont(.copyLarge).foregroundStyle(MP.muted)
                    }
                    InsetDivider(leading: 16)
                    ListRow(state.sent ? "A welcome text is on its way" : "Nothing sent yet",
                            subtitle: sentLine(state),
                            symbol: state.sent ? "paperplane.fill" : "tray", family: .teal, chevron: false)
                }
            }
            .clipShape(MP.surfaceShape)
            PrimaryButton(title: "Done") { dismiss() }
            Button("Stop sending to this phone") { unbind() }
                .buttonStyle(MPButtonStyle(kind: .plain, fullWidth: true))
                .disabled(working)
        }
    }

    /// What went out, in the server's words when it gave any.
    private func sentLine(_ state: DemoPhoneState) -> String {
        if let detail = state.detail, !detail.isEmpty { return detail.typeset }
        return state.sent
            ? "It carries a link that opens this app as \(firstName)."
            : "The next text this demo sends to \(firstName) arrives on this phone."
    }

    // MARK: Not on this server

    private func unavailable(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Card {
                EmptyRow(icon: "message.badge.waveform", title: "Texting isn’t available here", detail: message)
            }
            SecondaryButton(title: "Try again", icon: "arrow.clockwise", loading: working) {
                Task { await load() }
            }
        }
    }

    private func heading(_ title: String, _ lede: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).title(MPSize.displayS)
                .accessibilityAddTraits(.isHeader)
            Text(lede).mpFont(.copyLarge).foregroundStyle(MP.body).lineSpacing(2)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 6)
    }

    // MARK: Calls

    private func load() async {
        working = true
        defer { working = false }
        do {
            phone = try await app.api.demoPhone()
            problem = nil
            stage = .ready
        } catch {
            if let e = error as? APIError, e.isUnauthorized {
                // The session is gone: AppModel signs out and the picker
                // takes over.
                app.note(error)
                dismiss()
                return
            }
            guard let sentence = Self.sentence(for: error) else { return }
            stage = .unavailable(sentence)
        }
    }

    private func bind() {
        guard let value = PhoneNumber.normalized(number) else { return }
        run { try await app.api.demoBindPhone(value) }
    }

    private func unbind() {
        run {
            let cleared = try await app.api.demoUnbindPhone()
            number = ""
            return cleared
        }
    }

    /// "I've sent it": ask now rather than at the next poll.
    private func check() {
        run {
            let latest = try await app.api.demoPhone()
            if !latest.reachable {
                problem = "We haven’t got your text yet. Give it a moment, or send it again."
            }
            return latest
        }
    }

    private func run(_ call: @escaping () async throws -> DemoPhoneState) {
        guard !working else { return }
        working = true
        problem = nil
        focused = false
        Task {
            defer { working = false }
            do {
                phone = try await call()
            } catch {
                if let e = error as? APIError, e.isUnauthorized {
                    app.note(error)
                    dismiss()
                    return
                }
                problem = Self.sentence(for: error)
            }
        }
    }

    /// The two refusals this sheet expects, in plain words; anything else
    /// in the server's own.
    private static func sentence(for error: Error) -> String? {
        if let e = error as? APIError {
            let generic = HTTPURLResponse.localizedString(forStatusCode: e.status)
            let bare = e.detail.caseInsensitiveCompare(generic) == .orderedSame
                || e.detail.caseInsensitiveCompare("Not Found") == .orderedSame
            switch e.status {
            case 404 where bare:
                return "This server can’t bind a phone to a demo person. It needs a demo server with its text line set up."
            case 409 where bare:
                return "That number already belongs to someone else on this server. Use a different one."
            case 422:
                return "That doesn’t look like a mobile number. Include the area code."
            default:
                break
            }
        }
        return DemoShell.sentence(for: error, notFound: "This server can’t bind a phone to a demo person.")
    }
}

/// Phone numbers as the sheet shows and sends them.
enum PhoneNumber {
    /// What the server is sent: "+1XXXXXXXXXX" for ten US digits, the
    /// digits behind a "+" for a number typed with its country code, or nil
    /// when there are too few digits to be a number.
    static func normalized(_ raw: String) -> String? {
        let digits = raw.filter(\.isNumber)
        if raw.trimmingCharacters(in: .whitespaces).hasPrefix("+") {
            return (8...15).contains(digits.count) ? "+\(digits)" : nil
        }
        if digits.count == 10 { return "+1\(digits)" }
        if digits.count == 11, digits.hasPrefix("1") { return "+\(digits)" }
        return nil
    }

    /// "+15049081262" as "(504) 908-1262" for a US number; anything else as
    /// it is.
    static func display(_ raw: String?) -> String {
        guard let raw, !raw.isEmpty else { return "your number" }
        let digits = raw.filter(\.isNumber)
        guard digits.count == 11, digits.hasPrefix("1") else { return raw }
        let d = Array(digits.dropFirst())
        return "(\(String(d[0..<3]))) \(String(d[3..<6]))-\(String(d[6..<10]))"
    }

    /// The `sms:` URL that opens Messages with the first text already
    /// written.
    static func smsURL(to number: String, body: String) -> URL? {
        let encoded = body.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? "Hi%20MedPull"
        return URL(string: "sms:\(number)&body=\(encoded)")
    }
}
