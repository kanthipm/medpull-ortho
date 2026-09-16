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

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Talk to MedPull").title(MPSize.displayS)
                                Text("Say things like “my pain is a 4”, “I did my exercises”, or “tell my nurse the swelling is down”.")
                                    .font(.copy).foregroundStyle(MP.muted)
                            }
                            .padding(.top, 8)
                            ForEach(turns) { t in
                                VStack(alignment: t.who == "you" ? .trailing : .leading, spacing: 3) {
                                    // Opaque, like the Messages bubble: a turn
                                    // is a repeating list cell and glass is
                                    // barred from those. 16pt / 400 — 15 is not
                                    // a rung and this is copy a patient reads.
                                    Text(t.text)
                                        .font(.copyLarge)
                                        .foregroundStyle(t.who == "you" ? MP.onBrand : MP.ink)
                                        .padding(.horizontal, 14).padding(.vertical, 10)
                                        .background(MP.surfaceShape
                                            .fill(t.who == "you" ? MP.brand : t.flagged ? MP.riskHighBg : MP.panel))
                                        // The flagged edge is SOLID `riskHigh`
                                        // (4.83:1 on its own tint light, 5.70:1
                                        // dark). At 0.5 alpha it was a wash whose
                                        // real ratio depended on which ground
                                        // showed through, and it is the cue that
                                        // a turn was escalated.
                                        .overlay(MP.surfaceShape
                                            .strokeBorder(t.who == "you" ? .clear : t.flagged ? MP.riskHigh : MP.line, lineWidth: 1))
                                }
                                .frame(maxWidth: .infinity, alignment: t.who == "you" ? .trailing : .leading)
                                .id(t.id)
                            }
                            if speech.isListening && !speech.transcript.isEmpty {
                                // NO `.italic()`. Instrument Sans ships no
                                // italic file, so SwiftUI would shear the
                                // roman — synthetic obliquing, the same defect
                                // class as synthetic bold. What is being heard
                                // right now is already distinguished from what
                                // has been sent three ways over: `muted`
                                // instead of `onBrand`, no bubble fill and no
                                // edge, and the live "Listening… tap to send"
                                // label directly below the mic.
                                Text(speech.transcript).font(.copyLarge).foregroundStyle(MP.muted)
                                    .frame(maxWidth: .infinity, alignment: .trailing)
                            }
                            if thinking { ProgressView().frame(maxWidth: .infinity, alignment: .leading) }
                            if let error { ErrorBanner(text: error) }
                            if let e = speech.errorText { ErrorBanner(text: e) }
                        }
                        .padding(.horizontal, 18).padding(.bottom, 12)
                    }
                    .onChange(of: turns.count) { _, _ in
                        guard let last = turns.last else { return }
                        withAnimation(MPMotion.gated(MPMotion.enter, reduceMotion: reduceMotion)) {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
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
                    // THE GLOW IS GONE, DELIBERATELY. It was
                    // `.shadow(color: brand.opacity(0.35), radius: 18, y: 6)`
                    // — a 0.35-alpha coloured halo, which is neither of the two
                    // things a shadow is allowed to be here. The ambient shadow
                    // belongs to floating overlays (modal, popover, toast) and
                    // this is a control pinned in the bottom bar; and a brand-
                    // tinted bloom is decoration borrowing the language of
                    // elevation. An 84pt disc of solid Medical Blue on `panel`
                    // is already the loudest element on the screen — the halo
                    // added no information and, in the listening state, put a
                    // red bloom around the stop button.
                    Circle().fill(speech.isListening ? MP.riskHigh : MP.brand).frame(width: 84, height: 84)
                    // `onRiskHigh` for the listening fill: white on #C62828 is
                    // 5.62:1 but white on the dark half #FF8A87 is 2.27:1, so
                    // dark flips to n-950 (8.08:1). White on `brand` is 4.60:1
                    // in both modes.
                    Image(systemName: speech.isListening ? "stop.fill" : "mic.fill")
                        .font(.displayS)
                        .foregroundStyle(speech.isListening ? MP.onRiskHigh : MP.onBrand)
                }
                .scaleEffect(speech.isListening ? 1.06 : 1)
                // 240ms ease-out, and it snaps instead under Reduce Motion —
                // the scale is a state cue, so it stays, but the travel does
                // not. `.spring(duration: 0.3)` was neither eased-out nor
                // gated.
                .animation(MPMotion.gated(MPMotion.enter, reduceMotion: reduceMotion), value: speech.isListening)
            }
            .buttonStyle(.plain)
            .disabled(thinking)
            Text(speech.isListening ? "Listening… tap to send" : speech.isSpeaking ? "Speaking…" : "Tap to talk")
                .font(.copyMedium).foregroundStyle(MP.muted)
            HStack(spacing: 8) {
                // Explicit prompt, for the reason spelled out in
                // MessagesView's composer: SwiftUI's own placeholder colour is
                // 1.72:1 on light panel and 2.47:1 on dark, and a placeholder
                // is text. `muted` is the placeholder tier.
                TextField("Or type it", text: $typed,
                          prompt: Text("Or type it").foregroundStyle(MP.muted))
                    .textFieldStyle(FieldStyle())
                    .submitLabel(.send)
                    .onSubmit { sendTyped() }
                Button { sendTyped() } label: {
                    // Same disabled pair as the Messages composer: a white
                    // arrow on `faint` was 2.60:1. `disabledInk` on
                    // `disabledFill` is 4.75:1 light / 4.58:1 dark, with the
                    // `lineStrong` edge because that fill is 1.06:1 against the
                    // panel behind it.
                    Image(systemName: "arrow.up").font(.copyLargeMedium)
                        .foregroundStyle(canSendTyped ? MP.onBrand : MP.disabledInk)
                        .frame(width: 44, height: 44)
                        .background(Circle().fill(canSendTyped ? MP.brand : MP.disabledFill))
                        .overlay {
                            if !canSendTyped { Circle().strokeBorder(MP.lineStrong, lineWidth: 1) }
                        }
                }
                .disabled(!canSendTyped || thinking)
            }
        }
        .padding(.horizontal, 18).padding(.top, 12).padding(.bottom, 10)
        .background(MP.panel.overlay(Divider().overlay(MP.line), alignment: .top))
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
