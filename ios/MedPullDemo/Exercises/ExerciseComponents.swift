import SwiftUI

// The pieces the exercise screens share: a row, the state as a dot and a
// word, the two 0-to-10 answers, the "what you did" fields, and the card that
// says what went back to the therapist. All of it in the app's own
// vocabulary (UI/Rows.swift, UI/Components.swift): monochrome glyphs on tint
// discs, state as a dot and a word, no gradient outside a screen's hero.

// MARK: - Scrolling

/// The scroll view the exercise screens use. In a debug build a launch
/// argument can open it scrolled (`-MP_EX_SCROLL bottom` or `middle`), so a
/// simulator screenshot can show what is below the fold; otherwise it is a
/// plain `ScrollView`.
struct ExerciseScroll<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        #if DEBUG
        ScrollViewReader { proxy in
            ScrollView {
                content()
                    .overlay(alignment: .center) { Color.clear.frame(height: 1).id("exercise-scroll-middle") }
                    .overlay(alignment: .bottom) { Color.clear.frame(height: 1).id("exercise-scroll-bottom") }
            }
            .task {
                guard let place = AppConfig.debugFlag("MP_EX_SCROLL") else { return }
                try? await Task.sleep(for: .seconds(1.6))
                proxy.scrollTo("exercise-scroll-\(place)", anchor: place == "middle" ? .center : .bottom)
            }
        }
        #else
        ScrollView { content() }
        #endif
    }
}

// MARK: - State

extension ExerciseState {
    /// The word, and the colour its dot and text take. Hue says the state
    /// the same way everywhere else in the app: green is done, amber wants a
    /// look, the hollow periwinkle dot is "nothing yet".
    func label(painAfter: Int? = nil) -> (text: String, color: Color, hollow: Bool) {
        switch self {
        case .due: return ("To do", MP.riskMissing, true)
        case .upcoming: return ("Planned", MP.riskMissing, true)
        case .inProgress: return ("In progress", MP.brandInk, false)
        case .done:
            return (painAfter.map { "Done\(MP.dot)pain \($0)/10" } ?? "Done", MP.riskLow, false)
        case .skipped: return ("Skipped", MP.muted, false)
        case .missed: return ("Missed", MP.riskMed, false)
        }
    }
}

/// A state as a dot and a word, as `StateLabel` draws one, for the states a
/// risk tone does not name (skipped is neither good nor bad).
struct ExerciseStateLabel: View {
    let state: ExerciseState
    var painAfter: Int? = nil

    var body: some View {
        let label = state.label(painAfter: painAfter)
        HStack(spacing: 5) {
            Group {
                if label.hollow {
                    Circle().strokeBorder(label.color, lineWidth: 1.5)
                } else {
                    Circle().fill(label.color)
                }
            }
            .frame(width: 6, height: 6)
            .accessibilityHidden(true)
            Text(label.text).mpFont(.label).foregroundStyle(label.color).lineLimit(1)
        }
    }
}

/// What the therapist asked for with an exercise, as small marks: a clip of
/// the attempt, the watch on. Only what is required is marked; what is
/// optional is offered on the exercise itself.
struct RequirementMarks: View {
    let a: ExerciseAssignment

    var body: some View {
        if a.videoRequirement == .required { mark("video.fill", "Clip") }
        if a.wearableRequirement == .required { mark("applewatch", "Watch") }
    }

    private func mark(_ symbol: String, _ word: String) -> some View {
        HStack(spacing: 3) {
            Image(systemName: symbol).font(.system(size: 10, weight: .medium)).accessibilityHidden(true)
            Text(word).mpFont(.label)
        }
        .foregroundStyle(MP.body)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(word == "Clip" ? "a clip is asked for" : "with your watch on")
    }
}

// MARK: - Row

/// One exercise as a row: the glyph, the title, the dose, then the state
/// with what the therapist asked for. A chevron while there is something to
/// open it for; the state's own glyph once it is settled.
struct ExerciseRow: View {
    let a: ExerciseAssignment
    let today: String
    /// "Monday", for a row from an earlier day on Today's list.
    var dayLabel: String? = nil
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let state = a.state(on: today)
        HStack(alignment: .center, spacing: 12) {
            Glyph(systemName: "figure.strengthtraining.functional", family: .teal)
            VStack(alignment: .leading, spacing: 3) {
                Text(a.title.typeset).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    .strikethrough(state == .done, color: MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
                Text([dayLabel, ExerciseWords.typeset(a.dose)].compactMap { $0 }.filter { !$0.isEmpty }
                    .joined(separator: MP.dot))
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 2)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
                HStack(spacing: 10) {
                    ExerciseStateLabel(state: state, painAfter: a.completion?.painAfter)
                    if a.isOpen { RequirementMarks(a: a) }
                }
                .padding(.top, 1)
            }
            Spacer(minLength: 8)
            switch state {
            case .done:
                Image(systemName: "checkmark.circle.fill").font(.copyLarge).foregroundStyle(MP.riskLow)
                    .accessibilityHidden(true)
            case .skipped:
                Image(systemName: "minus.circle").font(.copyLarge).foregroundStyle(MP.muted)
                    .accessibilityHidden(true)
            default:
                Image(systemName: "chevron.right")
                    .font(.systemGlyphs(13, weight: .semibold))
                    .foregroundStyle(MP.faint)
                    .accessibilityHidden(true)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 11)
        .frame(minHeight: 60)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Small pieces

/// The sage pill the task screens use for a schedule ("Daily"): here the
/// day, and what was asked for.
struct ExercisePill: View {
    let text: String
    var symbol: String? = nil

    var body: some View {
        HStack(spacing: 4) {
            if let symbol {
                Image(systemName: symbol).font(.system(size: 10, weight: .medium)).accessibilityHidden(true)
            }
            Text(text).mpFont(.labelMedium)
        }
        .foregroundStyle(MP.brandInk)
        .padding(.horizontal, 10).padding(.vertical, 4)
        .background(MP.capsuleShape.fill(MP.brandTint))
    }
}

/// The therapist's note, in her words, under her initials.
struct TherapistNote: View {
    let a: ExerciseAssignment

    var body: some View {
        Card(tint: true) {
            HStack(alignment: .top, spacing: 12) {
                Initials(text: TeamAvatars.initials(a.assignedByName ?? ""), size: 34, tone: .low, style: .soft)
                VStack(alignment: .leading, spacing: 3) {
                    Text("\(ExerciseWords.therapist(a.assignedByName)) says").mpFont(.labelMedium).mpSecondary()
                    Text(a.clinicianInstructions.typeset)
                        .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

/// The ceiling the therapist put on a dose, in the sentence the server
/// built from it ("Stop at RPE 8 · do not exceed 30 lb"), wherever the dose
/// is shown. It is her limit in her words, so it is set like the rest of
/// what she says (sage on the sage tint) and never as a warning. Draws
/// nothing when she set none.
struct DoseCeiling: View {
    let a: ExerciseAssignment

    var body: some View {
        if a.hasCeiling {
            HStack(alignment: .firstTextBaseline, spacing: 7) {
                Image(systemName: "arrow.up.to.line")
                    .font(.system(size: 11, weight: .semibold))
                    .accessibilityHidden(true)
                Text(ExerciseWords.typeset(a.ceiling)).mpFont(.copyMedium)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
            }
            .foregroundStyle(MP.brandInk)
            .padding(.horizontal, 12).padding(.vertical, 7)
            .background(MP.thumbShape.fill(MP.brandTint))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(spoken)
        }
    }

    /// "Dr. Gregg’s limit: Stop at RPE 8 · do not exceed 30 lb".
    private var spoken: String {
        let whose = ExerciseWords.therapist(a.assignedByName)
        return "\(whose.prefix(1).uppercased())\(whose.dropFirst())’s limit: \(a.ceiling)"
    }
}

// MARK: - Visits and rest days

/// The two things the clinic puts on a day besides exercises: a visit to
/// the clinic and a rest day set on purpose. One symbol each, wherever they
/// are drawn (Today's card, the calendar's strip, its day card).
enum DayFact {
    static let visitSymbol = "calendar"
    static let restSymbol = "moon.fill"
}

/// One quiet line about a day inside a card: a small sage symbol, the
/// fact's name in ink and what follows it in the muted ink ("Next visit ·
/// Test day · Sat, Nov 14 · 9:30 AM", "Rest day · Deload.").
struct DayFactLine: View {
    let symbol: String
    let lead: String
    var facts: [String] = []

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 7) {
            Image(systemName: symbol)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(MP.brandInk)
                .frame(width: 14)
                .accessibilityHidden(true)
            (Text(lead).font(.labelMedium).foregroundStyle(MP.ink)
                + Text(facts.map { MP.dot + $0 }.joined()).foregroundStyle(MP.muted))
                .mpFont(.label)
                .fixedSize(horizontal: false, vertical: true)
                .multilineTextAlignment(.leading)
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }
}

/// The steps, numbered, as the library wrote them.
struct StepsCard: View {
    let a: ExerciseAssignment
    var titled = true

    var body: some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                if titled {
                    CardTitleRow("How to do it", note: a.equipment.isEmpty ? nil : "Needs \(a.equipment.lowercased())")
                }
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(Array(a.steps.enumerated()), id: \.offset) { index, step in
                        HStack(alignment: .firstTextBaseline, spacing: 12) {
                            Text("\(index + 1)")
                                .font(.figuresLabel).foregroundStyle(MP.brandInk)
                                .frame(width: 22, height: 22)
                                .background(Circle().fill(MP.brandTint))
                                .accessibilityHidden(true)
                            Text(step.typeset)
                                .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .accessibilityElement(children: .combine)
                        .accessibilityLabel("Step \(index + 1). \(step)")
                    }
                }
                .padding(.horizontal, 16).padding(.top, titled ? 6 : 16).padding(.bottom, 16)
            }
        }
    }
}

/// The done mark: a sage gradient disc with a white check and a lime halo,
/// as the check-in's.
struct ExerciseSeal: View {
    var size: CGFloat = 84
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var landed = false

    var body: some View {
        ZStack {
            Circle().fill(MP.lime.opacity(0.35))
                .frame(width: size * 1.24, height: size * 1.24)
                .scaleEffect(landed || reduceMotion ? 1 : 0.6)
            ZStack {
                GradientFill(gradient: .sage)
                Image(systemName: "checkmark")
                    .font(.system(size: size * 0.4, weight: .semibold))
                    .foregroundStyle(.white)
            }
            .frame(width: size, height: size)
            .clipShape(Circle())
            .shadow(color: Color(red: 74 / 255, green: 102 / 255, blue: 62 / 255).opacity(0.5), radius: 14, y: 8)
            .scaleEffect(landed || reduceMotion ? 1 : 0.4)
        }
        .animation(MPMotion.gated(.spring(response: 0.5, dampingFraction: 0.6), reduceMotion: reduceMotion), value: landed)
        .accessibilityHidden(true)
        .task {
            try? await Task.sleep(for: .milliseconds(120))
            landed = true
        }
    }
}

// MARK: - The two answers

/// Pain, 0 to 10, on the check-in's own slider.
struct PainAnswer: View {
    @Binding var value: Int?

    var body: some View {
        ScaleAnswer(value: Binding(get: { value.map(AnswerValue.int) },
                                   set: { value = $0?.intValue }),
                    painting: true)
    }
}

/// How hard it was, 0 to 10, on the same slider with the lifter's words
/// under the thumb: "Easy" at one end, "All out" at the other.
struct EffortAnswer: View {
    @Binding var value: Int?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var number: Int { value ?? 0 }

    var body: some View {
        VStack(spacing: 14) {
            ZStack {
                if value == nil {
                    Text("Drag to answer").mpFont(.copyLargeMedium).foregroundStyle(MP.muted)
                } else {
                    VStack(spacing: 0) {
                        Text("\(number)")
                            .font(.figuresDisplay(MPSize.displayXL))
                            .foregroundStyle(MP.brandInk)
                            .contentTransition(.numericText(value: Double(number)))
                            .animation(MPMotion.gated(MPMotion.state, reduceMotion: reduceMotion), value: number)
                            .lineLimit(1).minimumScaleFactor(0.7)
                        Text(ExerciseWords.effort(number)).mpFont(.copyMedium).foregroundStyle(MP.muted)
                    }
                }
            }
            .frame(maxWidth: .infinity, minHeight: 84)

            Slider(value: Binding(get: { Double(number) }, set: { value = Int($0.rounded()) }),
                   in: 0...10, step: 1)
                .tint(value == nil ? MP.track : MP.brand)
                .accessibilityLabel("How hard it was, 0 to 10")
                .accessibilityValue(Text(value == nil ? "Not answered" : "\(number), \(ExerciseWords.effort(number))"))
                .sensoryFeedback(trigger: number) { old, new in new > old ? .increase : .decrease }

            HStack {
                Text("Easy").mpFont(.label).foregroundStyle(MP.muted)
                Spacer()
                Text("All out").mpFont(.label).foregroundStyle(MP.muted)
            }
        }
    }
}

// MARK: - What you did

/// What the person says they actually did: sets, reps and load, filled in
/// from the dose and theirs to change. Lifters at this clinic often do more
/// than was prescribed, and the therapist reads the true numbers.
struct DoneCounts: Equatable {
    var sets: Double?
    var reps: Double?
    /// In the clinic's own unit, as shown.
    var load: Double?

    /// The dose as prescribed, with the sets counted in a session when
    /// there was one.
    init(_ a: ExerciseAssignment, unit: LoadUnit, setsCounted: Int? = nil) {
        sets = (setsCounted ?? a.sets).map(Double.init)
        reps = a.holdIsUnit ? nil : a.reps.map(Double.init)
        load = a.loadKg.map(unit.shown(kg:))
    }

    var setsDone: Int? { sets.map { Int($0.rounded()) } }
    var repsDone: Int? { reps.map { Int($0.rounded()) } }
    func loadDoneKg(unit: LoadUnit) -> Double? { load.map(unit.kilograms(from:)) }
}

/// Sets, reps and load as three rows, each a number that can be typed over
/// or nudged with a minus and a plus (one thumb, mid-workout).
struct DoneCountsCard: View {
    @Binding var counts: DoneCounts
    let a: ExerciseAssignment
    let unit: LoadUnit

    var body: some View {
        Card(padding: 0) {
            VStack(spacing: 0) {
                QuantityRow(title: "Sets", value: $counts.sets, step: 1, range: 0...999, whole: true)
                if !a.holdIsUnit {
                    InsetDivider(leading: 16)
                    QuantityRow(title: "Reps", value: $counts.reps, step: 1, range: 0...999, whole: true)
                }
                InsetDivider(leading: 16)
                QuantityRow(title: "Load", unit: unit.rawValue, value: $counts.load, step: unit.step,
                            range: 0...unit.shown(kg: 500), whole: false)
            }
        }
    }
}

/// One number with a minus and a plus beside it. Empty means "not said".
private struct QuantityRow: View {
    let title: String
    var unit: String? = nil
    @Binding var value: Double?
    let step: Double
    let range: ClosedRange<Double>
    let whole: Bool
    @State private var text = ""
    @FocusState private var focused: Bool

    var body: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 0) {
                Text(title).mpFont(.copyLarge).foregroundStyle(MP.ink)
                if let unit { Text(unit).mpFont(.label).foregroundStyle(MP.muted) }
            }
            Spacer(minLength: 8)
            nudge("minus", "Less") { move(-step) }
                .disabled((value ?? 0) <= range.lowerBound)
            TextField(title, text: $text, prompt: Text("–").foregroundColor(MP.muted))
                .font(.figuresLede)
                .foregroundStyle(MP.ink)
                .multilineTextAlignment(.center)
                .keyboardType(whole ? .numberPad : .decimalPad)
                .focused($focused)
                .frame(width: 76, height: 44)
                .background(MP.thumbShape.fill(MP.panel.opacity(0.8)))
                .overlay(MP.thumbShape.strokeBorder(MP.lineStrong.opacity(0.75), lineWidth: 1))
                .accessibilityLabel(unit.map { "\(title), in \($0)" } ?? title)
            nudge("plus", "More") { move(step) }
                .disabled((value ?? 0) >= range.upperBound)
        }
        .padding(.horizontal, 16).padding(.vertical, 8)
        .frame(minHeight: 60)
        .onAppear { text = value.map(LoadUnit.plain) ?? "" }
        .onChange(of: text) { _, new in
            let parsed = Self.number(new)
            if parsed != value { value = parsed.map { min(range.upperBound, max(range.lowerBound, $0)) } }
        }
        .onChange(of: value) { _, new in
            // A nudge, or a number pulled back into range.
            if Self.number(text) != new { text = new.map(LoadUnit.plain) ?? "" }
        }
    }

    private func nudge(_ symbol: String, _ word: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 15, weight: .semibold))
                .frame(width: 44, height: 44)
                .contentShape(Circle())
        }
        .buttonStyle(NudgeStyle())
        .accessibilityLabel("\(word) \(title.lowercased())")
    }

    private func move(_ by: Double) {
        let next = min(range.upperBound, max(range.lowerBound, (value ?? 0) + by))
        value = whole ? next.rounded() : next
    }

    /// A field's number, or nil when it is empty or not one.
    static func number(_ text: String) -> Double? {
        let clean = text.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: ".")
        guard !clean.isEmpty, let n = Double(clean), n.isFinite, n >= 0 else { return nil }
        return n
    }
}

/// The round minus and plus beside a number: a warm disc, ink glyph.
private struct NudgeStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(isEnabled ? MP.ink : MP.disabledInk)
            .background(Circle().fill(configuration.isPressed ? MP.fillStrong : MP.fill).padding(4))
            .scaleEffect(MPMotion.pressScale(configuration.isPressed, reduceMotion: reduceMotion))
            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion), value: configuration.isPressed)
    }
}

// MARK: - What came back

/// Done: "Sent to Dr. Gregg", the pain (before and after when both are
/// known), the effort and how long it ran side by side, what was done
/// against what was prescribed, the note, the clip that went with it, and
/// the therapist's reply once she has looked. Skipped: the reason.
struct OutcomeCard: View {
    let a: ExerciseAssignment
    let unit: LoadUnit

    private var therapist: String { ExerciseWords.therapist(a.assignedByName) }

    var body: some View {
        if a.isSkipped { skipped } else { done }
    }

    private var skipped: some View {
        Card(tint: true) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "minus.circle").font(.subhead).foregroundStyle(MP.muted)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Skipped").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    if let reason = a.skipReason, !reason.isEmpty {
                        Text("“\(reason.typeset)”").mpFont(.copy).foregroundStyle(MP.ink).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Text("\(therapist) can see this with the rest of your week.").mpFont(.copy).mpSecondary()
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
        }
    }

    private var done: some View {
        let c = a.completion
        let byTherapist = c?.source == "console"
        let when = ExerciseWords.ago(c?.completedAt)
        let sub = c?.review != nil || byTherapist ? when
            : [when, "They’ll see it with their next review."].filter { !$0.isEmpty }.joined(separator: MP.dot)
        return Card(tint: true) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: "checkmark.seal.fill")
                        .symbolRenderingMode(.hierarchical)
                        .font(.subheadSemibold).foregroundStyle(MP.riskLow)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(byTherapist ? "Logged by \(therapist)" : "Sent to \(therapist)")
                            .mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        if !sub.isEmpty {
                            Text(sub).mpFont(.copy).mpSecondary().fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    Spacer(minLength: 0)
                }
                stats
                facts
                if let note = c?.note, !note.isEmpty {
                    Text("“\(note.typeset)”").mpFont(.copy).foregroundStyle(MP.ink).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let clip = c?.video, !clip.withdrawn {
                    ClipTile(source: .attachment(id: clip.id), loop: false, label: "Your clip", maxHeight: 300)
                }
                if let review = c?.review {
                    ReviewBox(review: review, fallbackName: a.assignedByName)
                } else if a.awaitingReview {
                    Text("\(therapist) hasn’t looked at your clip yet.").mpFont(.label).mpSecondary()
                }
            }
        }
    }

    /// Pain, effort and the clock, side by side.
    private var stats: some View {
        let before = a.session?.painBefore
        let after = a.completion?.painAfter
        let pain = after.map { after in before.map { "\($0) → \(after)" } ?? "\(after)" } ?? "–"
        return HStack(alignment: .top, spacing: 12) {
            OutcomeStat(value: pain, label: before != nil && after != nil ? "pain, before → after" : "pain, out of 10")
            if let effort = a.completion?.effort {
                OutcomeStat(value: "\(effort)", label: "effort\(MP.dot)\(ExerciseWords.effort(effort).lowercased())")
            }
            if let seconds = a.sessionSeconds, seconds > 0, let clock = ExerciseWords.duration(seconds) {
                OutcomeStat(value: clock, label: "on the clock")
            }
        }
    }

    /// What the watch added to the record, in words.
    private var watchFacts: [String] {
        var facts: [String] = []
        if a.session?.wearableWorn == true { facts.append("watch on") }
        if let avg = a.session?.hrAvg {
            facts.append("heart rate \(avg) avg" + (a.session?.hrMax.map { ", \($0) max" } ?? ""))
        }
        return facts
    }

    /// What was done, set against what was prescribed when they differ, and
    /// what the watch added.
    @ViewBuilder private var facts: some View {
        let did = a.doneLine(unit: unit)
        let asked = a.prescribedLine(unit: unit)
        let extras = watchFacts
        if did != nil || !extras.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                if let did {
                    Text("Did \(did)").mpFont(.copyMedium).foregroundStyle(MP.ink)
                    if let asked, asked != did {
                        Text("Prescribed \(asked)").mpFont(.label).mpSecondary()
                    }
                }
                if !extras.isEmpty {
                    Text(extras.joined(separator: MP.dot)).mpFont(.label).mpSecondary()
                }
            }
        }
    }
}

/// A figure and its word, for the done card's row of three.
private struct OutcomeStat: View {
    let value: String
    let label: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value).font(.figuresSubhead).foregroundStyle(MP.ink).lineLimit(1).minimumScaleFactor(0.7)
            Text(label).mpFont(.label).mpSecondary().fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

/// What the therapist said about it, in her words, under her initials. The
/// same note reaches the Care thread.
private struct ReviewBox: View {
    let review: ExerciseReview
    let fallbackName: String?

    var body: some View {
        let name = review.byName ?? fallbackName
        let when = ExerciseWords.ago(review.at)
        HStack(alignment: .top, spacing: 10) {
            Initials(text: TeamAvatars.initials(name ?? ""), size: 30, tone: .low, style: .soft)
            VStack(alignment: .leading, spacing: 3) {
                Text([ExerciseWords.therapist(name), when].filter { !$0.isEmpty }.joined(separator: MP.dot))
                    .mpFont(.labelMedium).foregroundStyle(MP.ink)
                if review.note.isEmpty {
                    Text("Has seen it. Nothing to change.").mpFont(.copy).mpSecondary()
                } else {
                    Text(review.note.typeset).mpFont(.copy).foregroundStyle(MP.ink).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MP.controlShape.fill(MP.panel))
        .accessibilityElement(children: .combine)
    }
}
