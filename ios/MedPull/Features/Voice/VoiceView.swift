import SwiftUI

struct VoiceView: View {
    @Environment(AppModel.self) private var app
    @State private var speech = SpeechController()
    @State private var turns: [Turn] = []
    @State private var thinking = false
    @State private var typed = ""
    @State private var error: String?
    /// SwiftUI does not honour Reduce Motion for explicit animations, so the
    /// two animated moments on this screen read it themselves.
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    struct Turn: Identifiable {
        let id = UUID()
        let who: String  // you | medpull
        let text: String
        var flagged = false
    }

    @FocusState private var typing: Bool

    /// Starters that FILL the field, never send it. A tapped "my pain is a
    /// 4" that went straight to the chart would be a pain score nobody gave.
    private let starters = ["My pain is a 4", "I did my exercises", "Tell my nurse the swelling is down"]

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if turns.isEmpty && !speech.isListening { intro }
                        ForEach(turns) { t in
                            turnView(t).id(t.id)
                        }
                        if speech.isListening && !speech.transcript.isEmpty {
                            // NO `.italic()`: Instrument Sans ships no italic,
                            // so SwiftUI would shear the roman. What is being
                            // heard is set apart by `muted` (5.03 / 5.24 on
                            // canvas), no bubble, and the live label by the mic.
                            Text(speech.transcript).font(.copyLarge).foregroundStyle(MP.muted)
                                .frame(maxWidth: .infinity, alignment: .trailing)
                        }
                        if thinking {
                            ProgressView().tint(MP.brand)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .accessibilityLabel("MedPull is thinking")
                        }
                        if let error { ErrorBanner(text: error) }
                        if let e = speech.errorText { ErrorBanner(text: e) }
                    }
                    .padding(.horizontal, 16).padding(.bottom, 12)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: turns.count) { _, _ in
                    guard let last = turns.last else { return }
                    withAnimation(MPMotion.gated(MPMotion.enter, reduceMotion: reduceMotion)) {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
                .mpComposerBar { controls }
            }
            .ambientScreen()
            .navigationTitle("Talk")
            .navigationBarTitleDisplayMode(.inline)
            .mpErrorFeedback(error)
        }
    }

    /// The empty state: what this screen is for, and three ways to start.
    private var intro: some View {
        VStack(spacing: 14) {
            IconTile("waveform", family: .blue, size: 56)
            VStack(spacing: 6) {
                Text("Talk to MedPull").mpFont(.subheadSemibold).foregroundStyle(MP.ink)
                // `body` on the ambient wash: 6.37:1 light / 6.52:1 dark at
                // its densest.
                Text("Tap the mic and say how you're doing. We'll log it, and pass anything important to your care team.")
                    .mpFont(.copy).foregroundStyle(MP.body)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            VStack(spacing: 8) {
                ForEach(starters, id: \.self) { phrase in
                    Button {
                        typed = phrase
                        typing = true
                    } label: {
                        Text("\u{201C}\(phrase)\u{201D}")
                    }
                    .buttonStyle(.mpGray)
                    .controlSize(.small)
                    .accessibilityHint("Puts this in the message field")
                }
            }
            .padding(.top, 4)
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 12)
        .padding(.top, 32)
    }

    private func turnView(_ t: Turn) -> some View {
        let mine = t.who == "you"
        return VStack(alignment: mine ? .trailing : .leading, spacing: 4) {
            // Opaque, like the Messages bubble: a turn is a repeating list
            // cell and glass is barred from those.
            Text(t.text)
                .font(.copyLarge)
                .foregroundStyle(mine ? MP.onBrand : MP.ink)
                .padding(.horizontal, 14).padding(.vertical, 10)
                .background(BubbleShape(mine: mine)
                    .fill(mine ? MP.brand : t.flagged ? MP.riskHighBg : MP.panel))
                // The flagged edge is SOLID `riskHigh` (4.83:1 on its tint
                // light, 5.70:1 dark).
                .overlay(BubbleShape(mine: mine)
                    .strokeBorder(mine ? .clear : t.flagged ? MP.riskHigh : MP.line, lineWidth: 1))
            if t.flagged {
                // Never colour alone: the escalation is also said in words.
                // `riskHigh` on canvas is 5.24:1 light / 8.08:1 dark.
                Label("Passed to your care team", systemImage: "exclamationmark.bubble.fill")
                    .mpFont(.labelMedium)
                    .foregroundStyle(MP.riskHigh)
            }
        }
        .frame(maxWidth: .infinity, alignment: mine ? .trailing : .leading)
        .padding(mine ? .leading : .trailing, 40)
    }

    private var statusText: String {
        speech.isListening ? "Listening… tap to send" : speech.isSpeaking ? "Speaking…" : "Tap to talk"
    }

    private var controls: some View {
        VStack(spacing: 10) {
            Button {
                toggleMic()
            } label: {
                MicDisc(listening: speech.isListening)
            }
            .buttonStyle(MicButtonStyle())
            .disabled(thinking)
            .accessibilityLabel(speech.isListening ? "Stop and send" : "Start talking")
            .accessibilityHint(speech.isListening ? "Sends what you said" : "Speak to MedPull")
            // A start tick when listening begins, a stop tick when it ends.
            .sensoryFeedback(trigger: speech.isListening) { _, on in on ? .start : .stop }

            // A static waveform glyph beside the words while listening — no
            // variableColor loop: a repeating effect is a dizziness risk.
            HStack(spacing: 6) {
                if speech.isListening {
                    Image(systemName: "waveform").accessibilityHidden(true)
                }
                Text(statusText)
            }
            .mpFont(.copyMedium)
            // `body`, not `muted`: on iOS 26 this line floats over the thread
            // behind the scroll-edge effect, so it takes the stronger tier
            // (6.73 / 7.11 on canvas).
            .foregroundStyle(speech.isListening ? MP.riskHigh : MP.body)
            .padding(.horizontal, 12).padding(.vertical, 4)
            .background(MP.pillShape.fill(MP.canvas))
            .accessibilityAddTraits(.updatesFrequently)

            ComposerField(placeholder: "Or type it",
                          text: $typed,
                          canSend: canSendTyped && !thinking,
                          busy: false,
                          multiline: false,
                          focused: $typing,
                          send: sendTyped)
        }
    }

    /// The same predicate the send button's `.disabled` already used,
    /// named once so the fill, the ink and the edge cannot drift from it.
    private var canSendTyped: Bool {
        !typed.trimmingCharacters(in: .whitespaces).isEmpty
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

/// The mic: a bold 84pt disc. Idle, Medical Blue with a white mic (4.60:1)
/// inside a soft brand-tint ring; listening, `riskHigh` with a stop glyph
/// (`onRiskHigh`: 5.62 light / 8.08 dark) and a solid ring. The glyph swaps
/// with the system's replace transition. Nothing repeats.
private struct MicDisc: View {
    let listening: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isEnabled) private var isEnabled
    @ScaledMetric(relativeTo: .title) private var side: CGFloat = 84

    var body: some View {
        let d = min(side, 120)
        ZStack {
            // The halo is a flat tint ring, not a glow: no shadow, no blur.
            Circle()
                .fill(listening ? MP.riskHighBg : MP.brandTint)
                .frame(width: d + 20, height: d + 20)
            if listening {
                Circle().strokeBorder(MP.riskHigh, lineWidth: 2)
                    .frame(width: d + 20, height: d + 20)
            }
            Circle()
                .fill(isEnabled ? (listening ? MP.riskHigh : MP.brand) : MP.disabledFill)
                .frame(width: d, height: d)
            Image(systemName: listening ? "stop.fill" : "mic.fill")
                .font(.system(size: (d * 0.36).rounded(), weight: .semibold))
                .foregroundStyle(isEnabled ? (listening ? MP.onRiskHigh : MP.onBrand) : MP.disabledInk)
                .contentTransition(reduceMotion ? .identity : .symbolEffect(.replace))
        }
        .animation(MPMotion.gated(MPMotion.state, reduceMotion: reduceMotion), value: listening)
    }
}

private struct MicButtonStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .contentShape(Circle())
            .scaleEffect(reduceMotion ? 1 : (configuration.isPressed ? 0.94 : 1))
            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion),
                       value: configuration.isPressed)
    }
}
