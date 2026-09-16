import SwiftUI

/// The daily check-in, as its own flow rather than one long form.
///
/// Every other task kind stays on ``TaskDetailView``: a scrolling list of
/// questions is the right shape for "did you get through the set?". The
/// check-in is different because it is the one a patient does every single
/// day, often one-handed, often sore, and a six-question wall is what makes
/// them stop doing it by the second week. So it asks one thing at a time,
/// says how much is left, and never blocks on an answer — every question can
/// be passed over, and the care team would rather have four answers than
/// none.
///
/// Answers are the same `[String: AnswerValue]` the generic form sends, so
/// the server, the transcript and the adherence record see no difference
/// between a check-in done here, by text, on the web page or by voice.
struct CheckinView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let task: RecoveryTask

    @State private var step = 0
    @State private var answers: [String: AnswerValue] = [:]
    @State private var sending = false
    @State private var error: String?
    @State private var done = false
    @FocusState private var typing: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var questions: [Question] { task.questions }
    private var isReview: Bool { step >= questions.count }
    private var current: Question? { isReview ? nil : questions[step] }
    private var answered: Int { answers.count }

    var body: some View {
        Group {
            if done {
                CheckinDoneView()
            } else {
                VStack(spacing: 0) {
                    progress
                    // Still a ScrollView — the note question plus a keyboard
                    // can outgrow the screen — but short content is centred
                    // rather than stranded at the top of an empty phone.
                    GeometryReader { proxy in
                        ScrollView {
                            Group {
                                if let q = current { question(q) } else { review }
                            }
                            .frame(maxWidth: .infinity, minHeight: proxy.size.height,
                                   alignment: isReview ? .top : .center)
                        }
                        .scrollDismissesKeyboard(.interactively)
                    }
                    controls
                }
            }
        }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
        .animation(stepMotion, value: step)
        .animation(doneMotion, value: done)
    }

    // MARK: motion
    //
    /// Both durations sit in the 150-300ms band and both are `easeOut`, which
    /// is the entering curve; `easeInOut` was decelerating into a step that
    /// only ever arrives. They return nil under Reduce Motion, because
    /// SwiftUI does NOT honour that setting for explicit animations — an
    /// `.animation(_:value:)` or a `withAnimation` block runs regardless, so
    /// the check has to be here. Every animation on this screen goes through
    /// these two properties; nothing calls `withAnimation` bare.
    private var stepMotion: Animation? { MPMotion.gated(MPMotion.step, reduceMotion: reduceMotion) }
    private var doneMotion: Animation? { MPMotion.gated(MPMotion.settle, reduceMotion: reduceMotion) }

    // MARK: progress

    /// Dots rather than a bar: six of them read as "this is nearly nothing",
    /// which is the honest and the useful thing to say about a check-in.
    private var progress: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text("Daily check-in")
                    .font(.subheadMedium).foregroundStyle(MP.ink)
                Spacer()
                Text(isReview ? "Review" : "\(step + 1) of \(questions.count)")
                    .font(.copyMedium).foregroundStyle(MP.muted)
                    .monospacedDigit()
            }
            // TWO states, both solid tokens. It was three, and the middle
            // one was `brand.opacity(0.45)` — an alpha wash whose real
            // contrast depends on which ground shows through (it composites
            // to #92BDE8 on the light canvas and #13436E on the dark one),
            // which is the same defect the tinted Card's gradient was. There
            // is no solid token between `brand` and `track` to put there:
            // `brandTintStrong` is 1.19:1 against `track` in light, i.e.
            // invisible. So the current step now counts as reached, which
            // also makes the dots agree with the "N of M" label beside them
            // instead of showing N-1 filled and one half-filled.
            HStack(spacing: 6) {
                ForEach(questions.indices, id: \.self) { i in
                    MP.pillShape
                        .fill(i <= step || isReview ? MP.brand : MP.track)
                        .frame(height: 4)
                }
            }
        }
        .padding(.horizontal, 20).padding(.top, 8).padding(.bottom, 14)
    }

    // MARK: one question

    @ViewBuilder
    private func question(_ q: Question) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            // 24 is not a rung and nothing exists between 20 and 28, so the
            // one question on the screen goes UP, into the display band, via
            // `title()` — which is `ink`, wraps freely and is the same
            // treatment every other screen title gets. It also scales from
            // `.largeTitle` rather than `.body`, so at AX5 a long prompt
            // grows 1.69x instead of 2.81x: the sore patient this screen was
            // designed for is exactly the one who has Larger Text on.
            Text(q.prompt)
                .title(MPSize.displayS)

            switch q.kind {
            case "scale":
                ScaleAnswer(value: binding(for: q.id), painting: q.id == "pain")
            case "yes_no", "choice":
                ChoiceAnswer(options: q.options ?? ["yes", "no"], value: binding(for: q.id))
            case "number":
                TextField(q.id == "minutes" ? "Minutes" : "Number",
                          text: Binding(get: { answers[q.id]?.intValue.map(String.init) ?? "" },
                                        set: { answers[q.id] = Int($0).map(AnswerValue.int) }),
                          prompt: Text(q.id == "minutes" ? "Minutes" : "Number").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle()).keyboardType(.numberPad).focused($typing)
            default:
                TextField("Optional — anything at all",
                          text: Binding(get: { answers[q.id]?.stringValue ?? "" },
                                        set: { v in
                                            let t = v.trimmingCharacters(in: .whitespacesAndNewlines)
                                            if t.isEmpty { answers.removeValue(forKey: q.id) }
                                            else { answers[q.id] = .string(v) }
                                        }),
                          prompt: Text("Optional — anything at all").foregroundColor(MP.muted),
                          axis: .vertical)
                    .lineLimit(4...8).textFieldStyle(FieldStyle()).focused($typing)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20).padding(.top, 4).padding(.bottom, 24)
        .id(q.id)  // a fresh identity per question, so the transition reads as a step
        .transition(.opacity)
    }

    // MARK: review

    private var review: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(answered == 0 ? "Nothing answered yet" : "Here's what goes to your care team")
                .font(.subheadMedium).foregroundStyle(MP.ink)
            if answered == 0 {
                Text("Tap any question to answer it, or send nothing and do it later.")
                    .font(.copy).foregroundStyle(MP.muted)
            }
            Card(padding: 0) {
                VStack(spacing: 0) {
                    ForEach(questions) { q in
                        Button { withAnimation(stepMotion) { step = index(of: q) } } label: {
                            HStack(alignment: .top, spacing: 12) {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(q.prompt)
                                        .font(.copy).foregroundStyle(MP.muted)
                                        .multilineTextAlignment(.leading)
                                    // "Not answered" is TEXT, so the
                                    // unanswered state is `muted` (5.39:1 on
                                    // panel), not `faint` (2.59:1). An
                                    // unanswered row is the one a patient most
                                    // needs to be able to read.
                                    Text(spoken(q))
                                        .font(.copyLargeMedium)
                                        .foregroundStyle(answers[q.id] == nil ? MP.muted : MP.ink)
                                        .multilineTextAlignment(.leading)
                                }
                                Spacer(minLength: 8)
                                Image(systemName: "pencil").font(.labelMedium)
                                    .foregroundStyle(MP.brandInk)
                            }
                            .padding(.horizontal, 16).padding(.vertical, 12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        if q.id != questions.last?.id { Divider().overlay(MP.line).padding(.leading, 16) }
                    }
                }
            }
        }
        .padding(.horizontal, 20).padding(.bottom, 24)
    }

    /// The answer in the patient's own words, matching what the care team
    /// will read on the transcript, so the review is a true preview and not
    /// a second vocabulary for the same thing.
    private func spoken(_ q: Question) -> String {
        guard let value = answers[q.id] else { return "Not answered" }
        if let n = value.intValue {
            return q.id == "pain" ? "\(n) out of 10 — \(Pain.word(n))" : "\(n)"
        }
        guard let raw = value.stringValue else { return "Not answered" }
        return ChoiceAnswer.labels[raw] ?? raw
    }

    private func index(of q: Question) -> Int {
        questions.firstIndex(where: { $0.id == q.id }) ?? 0
    }

    // MARK: controls

    private var controls: some View {
        VStack(spacing: 8) {
            if let error { ErrorBanner(text: error) }
            PrimaryButton(title: isReview ? sendTitle : "Next", loading: sending) {
                if isReview { submit() } else { withAnimation(stepMotion) { typing = false; step += 1 } }
            }
            HStack {
                if step > 0 {
                    Button("Back") { withAnimation(stepMotion) { typing = false; step -= 1 } }
                        .font(.copyMedium).foregroundStyle(MP.muted)
                }
                Spacer()
                if !isReview {
                    // Skipping is a real answer to "I can't face this right
                    // now", and a check-in that demands all six is one a sore
                    // patient abandons instead.
                    Button(answers[current?.id ?? ""] == nil ? "Skip this one" : "Clear") {
                        if let id = current?.id { answers.removeValue(forKey: id) }
                        withAnimation(stepMotion) { typing = false; step += 1 }
                    }
                    .font(.copyMedium).foregroundStyle(MP.muted)
                }
            }
            .frame(minHeight: 22)
        }
        .padding(.horizontal, 20).padding(.top, 10).padding(.bottom, 14)
        .background(MP.panel.overlay(Divider().overlay(MP.line), alignment: .top))
    }

    private var sendTitle: String {
        answered == 0 ? "Send nothing for now" : "Send to my care team"
    }

    private func submit() {
        sending = true
        error = nil
        Task {
            defer { sending = false }
            do {
                if answers.isEmpty {
                    try await app.skip(task)
                } else {
                    try await app.complete(task, answers: answers)
                }
                done = true
                try? await Task.sleep(for: .seconds(1.4))
                dismiss()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

// MARK: - answer controls

/// 0 to 10 on a slider rather than eleven chips.
///
/// The chips were accurate and unusable: eleven 44pt targets do not fit a
/// phone without shrinking below the tap minimum, and picking "4" from a grid
/// is a search task. A slider is one gesture, and the number and the word
/// under the thumb say what was chosen without needing to read the scale.
private struct ScaleAnswer: View {
    @Binding var value: AnswerValue?
    var painting: Bool

    private var number: Int { value?.intValue ?? 0 }

    var body: some View {
        VStack(spacing: 14) {
            // A fixed-height readout so the layout does not jump the moment
            // the first value lands, and nothing numeral-shaped before then:
            // an unanswered pain question must not look like a reported 0.
            ZStack {
                if value == nil {
                    Text("Drag to answer")
                        .font(.copyLargeMedium).foregroundStyle(MP.muted)
                } else {
                    VStack(spacing: 0) {
                        // A DELIBERATE SYSTEM-FACE ESCAPE, now named as
                        // one: `monoDisplay(MPSize.displayXL)` is the
                        // display-band monospace rung, so the readout reads as
                        // intentional rather than as a leak. Three things
                        // changed and none of them is the escape itself. 58 ->
                        // 54, which is the `displayXL` rung. `.rounded` ->
                        // `.monospaced`, because SF Rounded was a third
                        // typeface mid-screen and because a readout that
                        // changes on every drag needs equal digit advances or
                        // it shifts under the thumb. `.semibold` -> the 500
                        // ceiling, which `Font.figures` clamps: `.system(weight:)`
                        // is the one path that can still draw a real San
                        // Francisco Semibold, since MPFont.name(for:) only
                        // protects `.mp`. It stays fixed-size rather than
                        // fluid: `.system(size:)` has no `relativeTo`, and a
                        // tabular readout that grows is a readout that clips.
                        Text("\(number)")
                            .font(.figuresDisplay(MPSize.displayXL))
                            .monospacedDigit()
                            .foregroundStyle(readoutInk)
                            .contentTransition(.numericText())
                            .lineLimit(1)
                        Text(painting ? Pain.word(number) : "out of 10")
                            .font(.copyMedium).foregroundStyle(MP.muted)
                    }
                }
            }
            .frame(maxWidth: .infinity, minHeight: 84)

            Slider(
                value: Binding(get: { Double(number) },
                               set: { value = .int(Int($0.rounded())) }),
                in: 0...10, step: 1
            )
            .tint(sliderTint)

            HStack {
                Text(painting ? "No pain" : "0").font(.label).foregroundStyle(MP.muted)
                Spacer()
                Text(painting ? "Worst imaginable" : "10").font(.label).foregroundStyle(MP.muted)
            }
        }
    }

    /// Green through amber to red as the number climbs — the same risk tones
    /// the rest of the app uses, so a patient who has seen their own chart
    /// reads the colour the same way their care team does. The three risk
    /// tokens are already the ink cuts (`riskHighBg` and friends are the
    /// fills), so the same value serves both jobs below.
    ///
    /// Colour is never the only carrier here: the word under the number
    /// ("Mild", "Moderate", "Bad", "Severe") says the same thing in text.
    private var riskInk: Color? {
        guard painting else { return nil }
        switch number {
        case 0...3: return MP.riskLow
        case 4...6: return MP.riskMed
        default: return MP.riskHigh
        }
    }

    /// The slider's fill. A FILL is exactly what Medical Blue is for, so the
    /// non-pain case keeps `brand`; an untouched slider stays on `track`.
    private var sliderTint: Color {
        guard value != nil else { return MP.track }
        return riskInk ?? MP.brand
    }

    /// The readout is TEXT, so the non-pain case is `brandInk`, not `brand`:
    /// #1976D2 as text is 3.74:1 on the dark panel and `brandInk` is 6.78:1.
    /// This is the one place the two jobs of the brand split apart.
    private var readoutInk: Color { riskInk ?? MP.brandInk }
}

/// Yes/no and the named choices, as full-width rows.
///
/// Full width because it is one thumb, often the non-dominant one, and a row
/// is a far larger target than a chip; and because a stack reads top to
/// bottom in the order the options were written rather than wrapping
/// unpredictably at the edge of the screen.
private struct ChoiceAnswer: View {
    let options: [String]
    @Binding var value: AnswerValue?

    static let labels: [String: String] = [
        "yes": "Yes", "no": "No", "well": "Well", "rough": "Rough night",
        "all": "All of them", "some": "Some", "none": "Not today",
    ]

    var body: some View {
        VStack(spacing: 10) {
            ForEach(options, id: \.self) { opt in
                let selected = value == .string(opt)
                Button {
                    value = selected ? nil : .string(opt)
                } label: {
                    HStack(spacing: 12) {
                        // The unselected ring was `line` — 1.55:1 on the
                        // light panel, i.e. the state of a control conveyed at
                        // a ratio 1.4.11 asks 3:1 for. `lineStrong` is 3.83:1
                        // light / 5.67:1 dark. Selected goes to `brandInk`,
                        // because a glyph is a foreground.
                        Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                            .font(.subhead)
                            .foregroundStyle(selected ? MP.brandInk : MP.lineStrong)
                        Text(Self.labels[opt] ?? opt.capitalized)
                            .font(.copyLargeMedium)
                            .foregroundStyle(MP.ink)
                        Spacer()
                    }
                    .padding(.horizontal, 16).frame(minHeight: 56)
                    // `MP.controlShape` — the deprecated `buttonRadius`
                    // literal resolved to the same 10pt, but the shape is the
                    // vocabulary and it carries `.continuous` with it. One
                    // fill and one hairline, which is the sanctioned pairing
                    // (a row's fill is 1.13:1 on canvas, so the edge is the
                    // only thing that says the control is there); never a
                    // second edge and never a shadow.
                    .background(MP.controlShape.fill(selected ? MP.brandTint : MP.panel))
                    .overlay(MP.controlShape
                        .strokeBorder(selected ? MP.brand : MP.lineStrong, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
        }
    }
}

private enum Pain {
    /// The words a patient would use, not a clinical scale's labels — the
    /// number is what gets recorded and scored; this only confirms that the
    /// slider landed where they meant it to.
    static func word(_ n: Int) -> String {
        switch n {
        case 0: return "No pain"
        case 1...3: return "Mild"
        case 4...6: return "Moderate"
        case 7...8: return "Bad"
        default: return "Severe"
        }
    }
}

private struct CheckinDoneView: View {
    var body: some View {
        VStack(spacing: 14) {
            Spacer()
            // 54pt on the DISPLAY curve, not the UI curve: the old 54 literal scaled
            // from `.body` (2.81x at AX5 = 152pt, which takes the screen with
            // it); `displayXL` scales from `.largeTitle` (1.69x = 91pt).
            Image(systemName: "checkmark.seal.fill")
                .font(.displayXL).foregroundStyle(MP.riskLow)
            Text("Sent to your care team")
                .font(.subheadMedium).foregroundStyle(MP.ink)
            Text("That's today done. They'll see it with their next review.")
                .font(.copy).foregroundStyle(MP.muted)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .padding(.horizontal, 32)
        .frame(maxWidth: .infinity)
        .transition(.opacity)
    }
}

private extension CheckinView {
    func binding(for id: String) -> Binding<AnswerValue?> {
        Binding(get: { answers[id] },
                set: { new in
                    if let new { answers[id] = new } else { answers.removeValue(forKey: id) }
                })
    }
}
