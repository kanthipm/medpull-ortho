import SwiftUI

struct VoiceView: View {
    @Environment(AppModel.self) private var app
    @State private var speech = SpeechController()
    @State private var turns: [Turn] = []
    @State private var thinking = false
    @State private var typed = ""
    @State private var error: String?

    struct Turn: Identifiable {
        let id = UUID()
        let who: String  // you | medpull
        let text: String
        var flagged = false
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Talk to MedPull").title(28)
                                Text("Say things like “my pain is a 4”, “I did my exercises”, or “tell my nurse the swelling is down”.")
                                    .font(.system(size: 14)).foregroundStyle(MP.muted)
                            }
                            .padding(.top, 8)
                            ForEach(turns) { t in
                                VStack(alignment: t.who == "you" ? .trailing : .leading, spacing: 3) {
                                    Text(t.text)
                                        .font(.system(size: 15))
                                        .foregroundStyle(t.who == "you" ? .white : MP.ink)
                                        .padding(.horizontal, 14).padding(.vertical, 10)
                                        .background(RoundedRectangle(cornerRadius: 16, style: .continuous)
                                            .fill(t.who == "you" ? MP.brand : t.flagged ? MP.riskHighBg : MP.panel))
                                        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                                            .strokeBorder(t.who == "you" ? .clear : t.flagged ? MP.riskHigh.opacity(0.5) : MP.line))
                                }
                                .frame(maxWidth: .infinity, alignment: t.who == "you" ? .trailing : .leading)
                                .id(t.id)
                            }
                            if speech.isListening && !speech.transcript.isEmpty {
                                Text(speech.transcript).font(.system(size: 15)).foregroundStyle(MP.muted).italic()
                                    .frame(maxWidth: .infinity, alignment: .trailing)
                            }
                            if thinking { ProgressView().frame(maxWidth: .infinity, alignment: .leading) }
                            if let error { ErrorBanner(text: error) }
                            if let e = speech.errorText { ErrorBanner(text: e) }
                        }
                        .padding(.horizontal, 18).padding(.bottom, 12)
                    }
                    .onChange(of: turns.count) { _, _ in
                        if let last = turns.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
                    }
                }
                controls
            }
            .screen()
            .toolbar(.hidden, for: .navigationBar)
        }
    }

    private var controls: some View {
        VStack(spacing: 12) {
            Button {
                toggleMic()
            } label: {
                ZStack {
                    Circle().fill(speech.isListening ? MP.riskHigh : MP.brand).frame(width: 84, height: 84)
                        .shadow(color: (speech.isListening ? MP.riskHigh : MP.brand).opacity(0.35), radius: 18, y: 6)
                    Image(systemName: speech.isListening ? "stop.fill" : "mic.fill")
                        .font(.system(size: 30, weight: .semibold)).foregroundStyle(.white)
                }
                .scaleEffect(speech.isListening ? 1.06 : 1)
                .animation(.spring(duration: 0.3), value: speech.isListening)
            }
            .buttonStyle(.plain)
            .disabled(thinking)
            Text(speech.isListening ? "Listening… tap to send" : speech.isSpeaking ? "Speaking…" : "Tap to talk")
                .font(.system(size: 13, weight: .medium)).foregroundStyle(MP.muted)
            HStack(spacing: 8) {
                TextField("Or type it", text: $typed)
                    .textFieldStyle(FieldStyle())
                    .submitLabel(.send)
                    .onSubmit { sendTyped() }
                Button { sendTyped() } label: {
                    Image(systemName: "arrow.up").font(.system(size: 16, weight: .bold)).foregroundStyle(.white)
                        .frame(width: 44, height: 44)
                        .background(Circle().fill(typed.trimmingCharacters(in: .whitespaces).isEmpty ? MP.faint : MP.brand))
                }
                .disabled(typed.trimmingCharacters(in: .whitespaces).isEmpty || thinking)
            }
        }
        .padding(.horizontal, 18).padding(.top, 12).padding(.bottom, 10)
        .background(MP.panel.overlay(Divider().overlay(MP.line), alignment: .top))
    }

    private func toggleMic() {
        if speech.isListening {
            let heard = speech.stopListening()
            if !heard.isEmpty { send(heard, channel: "voice", speak: true) }
        } else {
            Task {
                if !speech.authorized {
                    guard await speech.requestAuthorization() else { return }
                }
                speech.startListening()
            }
        }
    }

    private func sendTyped() {
        let text = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        typed = ""
        send(text, channel: "app", speak: false)
    }

    private func send(_ text: String, channel: String, speak: Bool) {
        turns.append(Turn(who: "you", text: text))
        thinking = true
        error = nil
        Task {
            defer { thinking = false }
            do {
                let r = try await app.ask(text, channel: channel)
                turns.append(Turn(who: "medpull", text: r.reply, flagged: r.flagged))
                if speak { speech.speak(r.reply) }
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}
