import Observation
import SwiftUI
import UIKit

// The guided session behind Start: the exercise as one step at a time, each
// a full screen with one primary button, the way a workout app walks a
// person through a set. Start (the pain right now) → your watch, unless the
// therapist turned it off → set up your phone → do it (her clip looping, the
// sets counted, the rests and holds timed) → record the attempt, unless she
// turned that off → the clip uploading → how it went and what was actually
// done → done.
//
// It covers the whole screen, tab bar included, and leaving asks first: a
// stray tap must not throw away a set count or a recorded clip. The screen
// stays awake while it is up, and the phone taps at every change of step,
// set, rest and hold.
//
// Two things here are stand-ins on the demo and say so on screen: the watch
// (no demo person's watch is paired with this phone) and, where offered, the
// sample clip. Nothing looks at the movement: the clip is uploaded, and the
// screen that waits for it calls it an upload.

// MARK: - The session's state

@Observable
@MainActor
final class SessionModel {
    enum Stage: String, Hashable {
        case start, watch, setup, exercise, record, upload, finish, done

        var title: String {
            switch self {
            case .start: return "Start"
            case .watch: return "Your watch"
            case .setup: return "Set up your phone"
            case .exercise: return "Do the exercise"
            case .record: return "Record your attempt"
            case .upload: return "Sending your clip"
            case .finish: return "How did it go?"
            case .done: return "Done"
            }
        }
    }

    /// The row as it was when the session opened: the title, the dose and
    /// the steps every stage draws from.
    let a: ExerciseAssignment
    let unit: LoadUnit
    /// The stages this exercise needs, fixed when the session opens. A
    /// requirement the therapist changes while it runs does not move the
    /// person's place; the server still has the last word when they send.
    let stages: [Stage]
    private(set) var index = 0
    /// Bumped at every change the person should feel in the hand.
    private(set) var transitions = 0

    var startedAt: Date?
    var endedAt: Date?
    var painBefore: Int?
    /// Whether the watch is on: nil until the watch stage has answered.
    var worn: Bool?
    /// The sets counted while the exercise ran.
    var setsCounted = 0
    let clip = AttemptClip()
    /// True while the completion is being sent.
    var sending = false
    /// The row as the server has it once the session is sent.
    var updated: ExerciseAssignment?

    init(a: ExerciseAssignment, unit: LoadUnit) {
        self.a = a
        self.unit = unit
        var stages: [Stage] = [.start]
        if a.wearableRequirement != .off { stages.append(.watch) }
        stages += [.setup, .exercise]
        if a.videoRequirement != .off { stages += [.record, .upload] }
        stages += [.finish, .done]
        self.stages = stages
    }

    var stage: Stage { stages[index] }
    /// "Step 3 of 7": the done screen is not a step.
    var step: Int { index + 1 }
    var stepCount: Int { stages.count - 1 }
    var therapist: String { ExerciseWords.therapist(a.assignedByName) }

    func advance() {
        index = min(stages.count - 1, index + 1)
        transitions += 1
    }

    /// Forward to a later stage (skipping an optional recording).
    func jump(to stage: Stage) {
        guard let target = stages.firstIndex(of: stage), target > index else { return }
        index = target
        transitions += 1
    }

    /// A change inside a stage: the next set, a rest ending, a hold ending.
    func tick() { transitions += 1 }

    #if DEBUG
    /// Simulator verification (`-MP_EX_STAGE`): open at a stage, as if the
    /// ones before it had been walked.
    var debugPhase: String?

    func debugOpen(at stage: Stage) {
        guard let target = stages.firstIndex(of: stage) else { return }
        if target > 0 { startedAt = Date().addingTimeInterval(-95) }
        if target > (stages.firstIndex(of: .exercise) ?? 0) {
            endedAt = Date()
            setsCounted = max(1, a.sets ?? 1)
        }
        if stages.contains(.watch), target > (stages.firstIndex(of: .watch) ?? 0) { worn = true }
        index = target
    }

    /// Simulator verification (`-MP_EX_AUTO <seconds>`): every stage takes
    /// its own primary action after this long, so one launch walks the whole
    /// session through the real calls.
    static let autopilot: Double? = AppConfig.debugFlag("MP_EX_AUTO").map { max(0.3, Double($0) ?? 1.5) }
    #endif
}

// MARK: - The cover

struct GuidedSession: View {
    let id: Int
    @Environment(ExerciseStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var model: SessionModel?

    var body: some View {
        NavigationStack {
            Group {
                if let model {
                    SessionStages(model: model) { dismiss() }
                } else {
                    ProgressView().tint(MP.brand)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .ambientScreen(height: 300)
                }
            }
        }
        // Leaving goes through the Leave button, which asks first.
        .interactiveDismissDisabled()
        .task {
            guard model == nil else { return }
            guard let a = store.assignment(id) else {
                dismiss()
                return
            }
            let session = SessionModel(a: a, unit: store.unit)
            #if DEBUG
            if let raw = AppConfig.debugFlag("MP_EX_STAGE") {
                let parts = raw.split(separator: ":").map(String.init)
                if let stage = SessionModel.Stage(rawValue: parts[0]) { session.debugOpen(at: stage) }
                session.debugPhase = parts.count > 1 ? parts[1] : nil
            }
            #endif
            model = session
        }
        // A workout is not a moment for the screen to dim and lock.
        .onAppear { UIApplication.shared.isIdleTimerDisabled = true }
        .onDisappear { UIApplication.shared.isIdleTimerDisabled = false }
    }
}

private struct SessionStages: View {
    @Bindable var model: SessionModel
    let close: () -> Void
    @Environment(ExerciseStore.self) private var store
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var confirmLeave = false

    /// The therapist logged it (or it was sent from another device) while
    /// this was open.
    private var settledElsewhere: ExerciseAssignment? {
        guard model.stage != .done, model.updated == nil, !model.sending,
              let live = store.assignment(model.a.id), !live.isOpen else { return nil }
        return live
    }

    var body: some View {
        Group {
            if let settled = settledElsewhere {
                AlreadySettled(a: settled, unit: model.unit, close: close)
            } else {
                switch model.stage {
                case .start: StartStage(model: model)
                case .watch: WatchStage(model: model)
                case .setup: SetupStage(model: model)
                case .exercise: ExerciseStage(model: model)
                case .record: RecordStage(model: model)
                case .upload: UploadStage(model: model)
                case .finish: FinishStage(model: model)
                case .done: DoneStage(model: model, close: close)
                }
            }
        }
        .ambientScreen(height: 300)
        // Settled from somewhere else, the bar stops naming a step the
        // person is no longer on.
        .navigationTitle(settledElsewhere.map { $0.isSkipped ? "Skipped" : "Done" } ?? model.stage.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if model.stage != .done && settledElsewhere == nil {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Leave") { confirmLeave = true }
                }
            }
        }
        .confirmationDialog("Leave this exercise?", isPresented: $confirmLeave, titleVisibility: .visible) {
            Button("Leave", role: .destructive) { close() }
            Button("Keep going", role: .cancel) {}
        } message: {
            Text(model.startedAt == nil
                 ? "Nothing has been sent. You can start it again from the exercise."
                 : "The clock stops and what you’ve done so far isn’t sent. You can start again from the exercise.")
        }
        .animation(MPMotion.gated(MPMotion.step, reduceMotion: reduceMotion), value: model.stage)
        // One tap in the hand at every change of step, set, rest and hold.
        .sensoryFeedback(.impact(weight: .medium, intensity: 1), trigger: model.transitions)
        .exerciseWatch()
        #if DEBUG
        .task {
            // Simulator verification: `-MP_EX_STAGE setup:leave` asks to leave.
            guard model.debugPhase == "leave" else { return }
            try? await Task.sleep(for: .seconds(1.5))
            confirmLeave = true
        }
        #endif
    }
}

// MARK: - The frame every stage shares

/// A stage: "Step 3 of 7" and its dots, the body, and the stage's buttons
/// pinned at the bottom.
private struct StageFrame<Content: View, Bottom: View>: View {
    let model: SessionModel
    var strip = true
    var spacing: CGFloat = 18
    @ViewBuilder var content: () -> Content
    @ViewBuilder var bottom: () -> Bottom

    var body: some View {
        ExerciseScroll {
            VStack(alignment: .leading, spacing: spacing) {
                if strip { StepStrip(step: model.step, of: model.stepCount) }
                content()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 20).padding(.top, 6).padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
        .safeAreaInset(edge: .bottom, spacing: 0) { SheetControls { bottom() } }
    }
}

/// "Step 3 of 7" and one dot per step: reached, or not yet.
private struct StepStrip: View {
    let step: Int
    let of: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Step \(step) of \(of)")
                .font(.figures(MPSize.copy, weight: .medium)).foregroundStyle(MP.muted)
            HStack(spacing: 6) {
                ForEach(0..<max(of, 1), id: \.self) { i in
                    MP.capsuleShape.fill(i < step ? MP.stateFill : MP.track).frame(height: 6)
                }
            }
            .accessibilityHidden(true)
        }
        .accessibilityElement(children: .combine)
    }
}

private struct StageHeading: View {
    var pill: String? = nil
    let title: String
    var sub: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let pill { ExercisePill(text: pill) }
            Text(title).title(MPSize.displayS)
                .accessibilityAddTraits(.isHeader)
            if let sub {
                Text(sub).mpFont(.copyLarge).foregroundStyle(MP.body).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// A quiet second action under a stage's primary button.
private struct QuietAction: View {
    let title: String
    let action: () -> Void

    var body: some View {
        Button(title, action: action)
            .buttonStyle(MPButtonStyle(kind: .plain, fullWidth: true))
    }
}

// MARK: - 1. Start

/// What there is to do, her note, the pain right now in one drag, and Start,
/// which opens the session on the server.
private struct StartStage: View {
    @Bindable var model: SessionModel
    @Environment(ExerciseStore.self) private var store
    @State private var starting = false
    @State private var error: String?

    var body: some View {
        let a = model.a
        StageFrame(model: model) {
            StageHeading(pill: "You have this to do", title: a.title.typeset, sub: ExerciseWords.typeset(a.dose))
            if let target = a.rpeTarget {
                Text("Aim for effort \(target)/10\(MP.dot)\(ExerciseWords.effort(target).lowercased())")
                    .mpFont(.copy).foregroundStyle(MP.muted)
            }
            // Her ceiling on the dose, before the first set.
            if a.hasCeiling { DoseCeiling(a: a) }
            if !a.clinicianInstructions.isEmpty { TherapistNote(a: a) }
            Card {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Pain right now?").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    PainAnswer(value: $model.painBefore)
                    Text("One drag. Leave it if you’d rather.").mpFont(.label).foregroundStyle(MP.muted)
                }
            }
        } bottom: {
            if let error { ErrorBanner(text: error) }
            PrimaryButton(title: "Start", icon: "play.fill", loading: starting) { start() }
        }
        .mpErrorFeedback(error)
        #if DEBUG
        .task {
            guard let wait = SessionModel.autopilot else { return }
            try? await Task.sleep(for: .seconds(wait))
            model.painBefore = 2
            try? await Task.sleep(for: .seconds(wait / 2))
            start()
        }
        #endif
    }

    private func start() {
        guard !starting else { return }
        let began = Date()
        starting = true
        error = nil
        Task {
            defer { starting = false }
            do {
                // The watch is asked on its own stage; the start carries the
                // pain.
                try await store.start(model.a, painBefore: model.painBefore, wearableWorn: nil)
                model.startedAt = began
                model.advance()
            } catch {
                self.error = ExerciseStore.sentence(for: error)
            }
        }
    }
}

// MARK: - 2. Your watch

/// Looks for the watch, then Continue. No demo person's watch is paired
/// with this phone, so the looking is a stand-in that finds one after two
/// seconds, and the stage says so. The person can always say they are not
/// wearing one: then an exercise that requires it waits, and one that does
/// not goes on without it.
private struct WatchStage: View {
    @Bindable var model: SessionModel
    @Environment(AppModel.self) private var app

    private enum Finding: Equatable { case looking, found, none }
    @State private var finding: Finding = .looking
    @State private var attempt = 0

    private var required: Bool { model.a.wearableRequirement == .required }
    /// The persona's own device, when the server lists one.
    private var device: String? { app.me?.wearables.devices.first?.model }

    var body: some View {
        StageFrame(model: model) {
            StageHeading(title: required ? "Wear your watch for this one." : "Wearing your watch?",
                         sub: required ? "\(model.therapist) wants your heart rate with it."
                            : "Your heart rate comes along with the exercise when you are.")
            Card(tint: finding == .found) {
                VStack(spacing: 12) {
                    switch finding {
                    case .looking:
                        ProgressView().controlSize(.large).tint(MP.brand)
                        Text("Looking for your watch").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text("Keep it on your wrist and close to the phone.").mpFont(.copy).mpSecondary()
                            .multilineTextAlignment(.center)
                    case .found:
                        ExerciseSeal(size: 64)
                        Text(device.map { "Detected\(MP.dot)\($0)" } ?? "Detected")
                            .mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    case .none:
                        Image(systemName: "applewatch.slash")
                            .font(.system(size: 34)).foregroundStyle(MP.riskMed)
                            .accessibilityHidden(true)
                        Text("No watch").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text(required ? "Put your watch on, then look again." : "You can carry on without it.")
                            .mpFont(.copy).mpSecondary().multilineTextAlignment(.center)
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 150)
                .padding(.vertical, 8)
                .accessibilityElement(children: .combine)
            }
            // The stand-in, named where it happens.
            Text("Simulated for this demo")
                .mpFont(.label).foregroundStyle(MP.muted)
                .frame(maxWidth: .infinity, alignment: .center)
            if finding == .none && required {
                Text("\(model.therapist) asked for this one with your watch on, so the exercise waits for it.")
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: .infinity)
            }
        } bottom: {
            switch finding {
            case .looking:
                PrimaryButton(title: "Looking…", disabled: true) {}
            case .found:
                PrimaryButton(title: "Continue") { proceed(worn: true) }
                QuietAction(title: "I’m not wearing a watch") { finding = .none }
            case .none:
                if required {
                    PrimaryButton(title: "Look again", icon: "arrow.clockwise") { attempt += 1 }
                } else {
                    PrimaryButton(title: "Continue without it") { proceed(worn: false) }
                    QuietAction(title: "Look again") { attempt += 1 }
                }
            }
        }
        .task(id: attempt) {
            #if DEBUG
            if attempt == 0, model.debugPhase == "none" {
                finding = .none
                return
            }
            if model.debugPhase == "looking" { return }
            #endif
            finding = .looking
            try? await Task.sleep(for: .seconds(2))
            guard !Task.isCancelled else { return }
            finding = .found
            model.tick()
            #if DEBUG
            if let wait = SessionModel.autopilot {
                try? await Task.sleep(for: .seconds(wait))
                proceed(worn: true)
            }
            #endif
        }
    }

    private func proceed(worn: Bool) {
        model.worn = worn
        model.advance()
    }
}

// MARK: - 3. Set up your phone

private struct SetupStage: View {
    @Bindable var model: SessionModel

    /// Whether a clip of the attempt may be recorded after the sets.
    private var records: Bool { model.stages.contains(.record) }

    var body: some View {
        StageFrame(model: model) {
            StageHeading(title: records ? "Prop your phone up." : "Put your phone where you can see it.",
                         sub: records
                            ? "Against something about knee height, two metres away, so a clip can show your whole body."
                            : model.a.demonstration != nil
                                ? "The sets are counted here, and the clip plays while you work."
                                : "The sets are counted here while you work.")
            Card { SetupArt(measured: records).frame(height: 170) }
            Text("A chair leg or a bag works. The screen stays on, and the phone taps at each change of set.")
                .mpFont(.label).foregroundStyle(MP.muted)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
        } bottom: {
            PrimaryButton(title: "Ready") { model.advance() }
        }
        #if DEBUG
        .task {
            guard let wait = SessionModel.autopilot else { return }
            try? await Task.sleep(for: .seconds(wait))
            model.advance()
        }
        #endif
    }
}

/// The phone propped at knee height, the person two metres away, in the
/// app's ink and sage. Drawn on a 320 by 180 grid and scaled to fit.
private struct SetupArt: View {
    /// Whether to draw the two metres: only a recording needs the distance.
    var measured = true

    var body: some View {
        Canvas { context, size in
            let scale = min(size.width / 320, size.height / 180)
            let origin = CGPoint(x: (size.width - 320 * scale) / 2, y: (size.height - 180 * scale) / 2)
            func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: origin.x + x * scale, y: origin.y + y * scale) }
            let ink = GraphicsContext.Shading.color(MP.ink)
            let quiet = GraphicsContext.Shading.color(MP.muted)
            let line = StrokeStyle(lineWidth: 2.4 * scale, lineCap: .round, lineJoin: .round)
            let thin = StrokeStyle(lineWidth: 1.2 * scale, lineCap: .round)

            // The floor.
            var floor = Path()
            floor.move(to: p(12, 150))
            floor.addLine(to: p(308, 150))
            context.stroke(floor, with: .color(MP.lineStrong), style: thin)

            // The phone, leaning on its prop.
            var phone = context
            phone.translateBy(x: p(84, 138).x, y: p(84, 138).y)
            phone.rotate(by: .degrees(-14))
            let body = CGRect(x: -11 * scale, y: -40 * scale, width: 22 * scale, height: 40 * scale)
            phone.fill(Path(roundedRect: body, cornerRadius: 4 * scale), with: .color(MP.brand))
            phone.fill(Path(roundedRect: body.insetBy(dx: 3 * scale, dy: 5 * scale), cornerRadius: 2 * scale),
                       with: .color(MP.brandTint))
            var prop = Path()
            prop.move(to: p(98, 150))
            prop.addLine(to: p(106, 122))
            context.stroke(prop, with: quiet, style: line)

            // The person.
            context.fill(Path(ellipseIn: CGRect(x: p(238, 40).x, y: p(238, 40).y, width: 24 * scale, height: 24 * scale)),
                         with: ink)
            var figure = Path()
            figure.move(to: p(250, 66)); figure.addLine(to: p(250, 104))
            figure.move(to: p(250, 76)); figure.addLine(to: p(228, 94))
            figure.move(to: p(250, 76)); figure.addLine(to: p(272, 94))
            figure.move(to: p(250, 104)); figure.addLine(to: p(234, 148))
            figure.move(to: p(250, 104)); figure.addLine(to: p(266, 148))
            context.stroke(figure, with: ink, style: line)

            // The height the phone sits at and, for a recording, the distance.
            let label = Font.custom(MPFont.regular, size: 11 * scale)
            context.draw(Text("knee height").font(label).foregroundStyle(MP.muted), at: p(84, 84), anchor: .center)
            if measured {
                var measure = Path()
                measure.move(to: p(112, 164)); measure.addLine(to: p(232, 164))
                measure.move(to: p(112, 158)); measure.addLine(to: p(112, 170))
                measure.move(to: p(232, 158)); measure.addLine(to: p(232, 170))
                context.stroke(measure, with: quiet, style: thin)
                context.draw(Text("about 2 m").font(label).foregroundStyle(MP.muted), at: p(172, 176), anchor: .center)
            }
        }
        .accessibilityLabel(measured ? "A phone propped at knee height, about two metres from where you stand"
                            : "A phone propped at knee height, facing where you stand")
    }
}

// MARK: - 4. Do the exercise

/// Her clip looping, the sets counted, a rest between them that can be
/// skipped, a countdown when a set is one timed hold, and the clock running
/// from Start. The primary button moves the set on; "stop here" is there at
/// any point.
private struct ExerciseStage: View {
    @Bindable var model: SessionModel

    private enum Phase: Equatable {
        case work(set: Int)
        case rest(next: Int, endsAt: Date)
        case hold(set: Int, endsAt: Date)
        case all
    }

    /// The rest between sets of a counted exercise. The dose carries no
    /// rest of its own; a minute is what a loading programme usually asks.
    private static let restSeconds: Double = 60

    @State private var phase: Phase = .work(set: 1)

    private var a: ExerciseAssignment { model.a }
    private var sets: Int { max(1, a.sets ?? 1) }
    private var hold: Int { a.holdSeconds ?? 0 }
    private var began: Date { model.startedAt ?? Date() }

    private var doneSets: Int {
        switch phase {
        case .work(let set), .hold(let set, _): return set - 1
        case .rest(let next, _): return next - 1
        case .all: return sets
        }
    }

    private var currentSet: Int? {
        switch phase {
        case .work(let set), .hold(let set, _): return set
        default: return nil
        }
    }

    /// "10 reps · 10 kg · Left": the dose without its sets, which the
    /// counter carries.
    private var doseLine: String {
        var bits: [String] = []
        if !a.holdIsUnit, let reps = a.reps { bits.append("\(reps) reps") }
        if !a.holdIsUnit, hold > 0 { bits.append("hold \(hold) s each") }
        if let load = a.loadKg { bits.append(model.unit.text(kg: load)) }
        if a.hasSide { bits.append(a.sideLabel) }
        return bits.isEmpty ? ExerciseWords.typeset(a.dose) : bits.joined(separator: MP.dot)
    }

    var body: some View {
        StageFrame(model: model, spacing: 14) {
            if let clip = a.demonstration {
                ClipTile(source: clip, label: "\(a.title), demonstration")
            }
            TimelineView(.periodic(from: .now, by: 0.5)) { timeline in
                counter(now: timeline.date)
            }
            if !a.steps.isEmpty { StepsCard(a: a, titled: false) }
        } bottom: {
            primary
            if stopsEarly {
                QuietAction(title: "I’m done, stop here") { finish(doneSets) }
            }
        }
        // A rest or a hold that runs out moves the session on by itself.
        .task(id: phase) {
            let ends: Date
            switch phase {
            case .rest(_, let at), .hold(_, let at): ends = at
            default: return
            }
            try? await Task.sleep(for: .seconds(max(0, ends.timeIntervalSinceNow)))
            guard !Task.isCancelled else { return }
            timerRanOut()
        }
        #if DEBUG
        .task {
            switch model.debugPhase {
            case "rest": phase = .rest(next: min(sets, 2), endsAt: Date().addingTimeInterval(47))
            case "hold": phase = .hold(set: 1, endsAt: Date().addingTimeInterval(Double(max(hold, 30)) - 9))
            case "all": phase = .all
            case "last": phase = .work(set: sets)
            default: break
            }
            guard let wait = SessionModel.autopilot else { return }
            // Press the primary button until the stage is over.
            while !Task.isCancelled, model.stage == .exercise {
                try? await Task.sleep(for: .seconds(wait))
                guard !Task.isCancelled, model.stage == .exercise else { return }
                pressPrimary()
            }
        }
        #endif
    }

    // MARK: The counter

    private func counter(now: Date) -> some View {
        let elapsed = max(0, Int(now.timeIntervalSince(began)))
        let left: Int? = {
            switch phase {
            case .rest(_, let at), .hold(_, let at): return max(0, Int(at.timeIntervalSince(now).rounded(.up)))
            default: return nil
            }
        }()
        return Card(tint: true) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .firstTextBaseline) {
                    Text(eyebrow).mpFont(.labelMedium).mpSecondary()
                    Spacer()
                    HStack(spacing: 4) {
                        Image(systemName: "timer").font(.system(size: 11, weight: .medium))
                        Text(ExerciseWords.clock(elapsed)).font(.figuresLabel)
                    }
                    .foregroundStyle(MP.onTintSecondary)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(ExerciseWords.clock(elapsed)) on the clock")
                }
                readout(left: left, elapsed: elapsed)
                HStack(spacing: 6) {
                    ForEach(1...sets, id: \.self) { set in
                        MP.capsuleShape
                            .fill(set <= doneSets ? MP.stateFill : set == currentSet ? MP.ink : MP.track)
                            .frame(height: 6)
                    }
                }
                .accessibilityHidden(true)
                Text(line).mpFont(.copyLarge).foregroundStyle(MP.ink)
                    .fixedSize(horizontal: false, vertical: true)
                // Her ceiling stays under the dose through every set, rest
                // and hold: this is where the person is deciding how hard
                // to go.
                if a.hasCeiling { DoseCeiling(a: a) }
            }
        }
    }

    /// The one big figure: the set while working, the seconds left while
    /// resting or holding, the clock once every set is done.
    @ViewBuilder private func readout(left: Int?, elapsed: Int) -> some View {
        switch phase {
        case .work(let set):
            if a.holdIsUnit {
                BigFigure(value: ExerciseWords.clock(hold), unit: "to hold", size: MPSize.displayXL)
                    .accessibilityLabel("Set \(set) of \(sets): hold for \(hold) seconds")
            } else {
                BigFigure(value: "\(set)", unit: "of \(sets)", size: MPSize.displayXL)
                    .accessibilityLabel("Set \(set) of \(sets)")
            }
        case .rest, .hold:
            BigFigure(value: ExerciseWords.clock(left ?? 0), unit: "left", size: MPSize.displayXL)
                .accessibilityLabel("\(left ?? 0) seconds left")
        case .all:
            BigFigure(value: ExerciseWords.clock(elapsed), unit: "on the clock", size: MPSize.displayXL)
        }
    }

    private var eyebrow: String {
        switch phase {
        case .work: return a.title.typeset
        case .rest: return "Rest"
        case .hold(let set, _): return "Set \(set) of \(sets)\(MP.dot)holding"
        case .all: return "All sets done"
        }
    }

    private var line: String {
        switch phase {
        case .work: return a.holdIsUnit ? [doseLine, "Start the hold when you’re in position."].joined(separator: MP.dot) : doseLine
        case .rest(let next, _): return "Next up: set \(next) of \(sets)\(MP.dot)\(doseLine)"
        case .hold: return "Keep it steady. The next set comes up on its own."
        case .all: return "All \(sets) \(sets == 1 ? "set" : "sets") done."
        }
    }

    // MARK: Buttons

    @ViewBuilder private var primary: some View {
        switch phase {
        case .work(let set):
            if a.holdIsUnit {
                PrimaryButton(title: "Start the hold", icon: "play.fill") { pressPrimary() }
            } else if set < sets {
                PrimaryButton(title: "Next set", icon: "arrow.right") { pressPrimary() }
            } else {
                PrimaryButton(title: "I’m done", icon: "checkmark") { pressPrimary() }
            }
        case .rest:
            PrimaryButton(title: "Skip the rest", icon: "forward.end.fill") { pressPrimary() }
        case .hold:
            PrimaryButton(title: "Stop the hold early", icon: "stop.fill") { pressPrimary() }
        case .all:
            PrimaryButton(title: "I’m done", icon: "checkmark") { pressPrimary() }
        }
    }

    /// "Stop here" is offered whenever the primary button is not already
    /// the way out.
    private var stopsEarly: Bool {
        switch phase {
        case .all: return false
        case .work(let set): return a.holdIsUnit || set < sets
        default: return true
        }
    }

    private func pressPrimary() {
        switch phase {
        case .work(let set):
            if a.holdIsUnit {
                move(to: .hold(set: set, endsAt: Date().addingTimeInterval(Double(hold))))
            } else if set < sets {
                move(to: .rest(next: set + 1, endsAt: Date().addingTimeInterval(Self.restSeconds)))
            } else {
                finish(sets)
            }
        case .rest(let next, _):
            move(to: .work(set: next))
        case .hold(let set, _):
            move(to: set < sets ? .work(set: set + 1) : .all)
        case .all:
            finish(sets)
        }
    }

    private func timerRanOut() {
        switch phase {
        case .rest(let next, _): move(to: .work(set: next))
        case .hold(let set, _): move(to: set < sets ? .work(set: set + 1) : .all)
        default: break
        }
    }

    private func move(to next: Phase) {
        phase = next
        model.tick()
    }

    private func finish(_ setsDone: Int) {
        model.setsCounted = setsDone
        model.endedAt = Date()
        model.advance()
    }
}

// MARK: - 5. Record your attempt

/// A clip of the attempt: the system camera, a video already on the phone
/// or, on a demo server, a sample. Then a look at it before it is used.
/// "Skip recording" is there only when the therapist left the clip optional.
private struct RecordStage: View {
    @Bindable var model: SessionModel
    @Environment(AppModel.self) private var app
    @Environment(DemoShell.self) private var shell
    @Environment(ExerciseStore.self) private var store

    private var required: Bool { model.a.videoRequirement == .required }
    private var clip: AttemptClip { model.clip }

    var body: some View {
        StageFrame(model: model, spacing: 14) {
            StageHeading(title: required ? "\(model.therapist) asked for a clip of this one."
                            : "Show \(model.therapist) your form.",
                         sub: "A few seconds of one set is plenty. It goes to your care team only.")
            switch clip.phase {
            case .taken(let take), .uploading(let take, _), .staged(let take, _):
                ClipTile(source: .file(take.preview), loop: false, label: take.isSample ? "Sample clip" : "Your clip",
                         maxHeight: 300)
                Text(take.isSample
                     ? "Sample clip\(MP.dot)\(AttemptChip.size(take.data.count)). It stands in for your own recording on this demo."
                     : "Your clip\(MP.dot)\(AttemptChip.size(take.data.count))")
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
            case .preparing:
                LoadingCard(text: "Getting your clip ready…")
            case .none, .failed:
                Card {
                    HStack(alignment: .top, spacing: 12) {
                        Glyph(systemName: "video.fill", family: .teal, size: 40)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Film one set").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            Text("From the side, with your whole body in the picture. The camera opens here and brings the clip back.")
                                .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 0)
                    }
                }
                if case .failed(let message, _) = clip.phase { ErrorBanner(text: message) }
            }
        } bottom: {
            switch clip.phase {
            case .taken, .uploading, .staged:
                PrimaryButton(title: "Use this clip", icon: "checkmark") { model.advance() }
                SecondaryButton(title: "Choose another", icon: "arrow.counterclockwise") { clip.remove() }
            case .preparing:
                PrimaryButton(title: "One moment…", disabled: true) {}
            case .none, .failed:
                AttemptSources(a: model.a, clip: clip)
                if !required {
                    QuietAction(title: "Skip recording") { model.jump(to: .finish) }
                }
            }
        }
        #if DEBUG
        .task {
            if model.debugPhase == "taken", clip.phase == .none {
                await clip.useSample(for: model.a, store: store, api: app.api)
            }
            guard let wait = SessionModel.autopilot else { return }
            try? await Task.sleep(for: .seconds(wait))
            if clip.take == nil { await clip.useSample(for: model.a, store: store, api: app.api) }
            try? await Task.sleep(for: .seconds(wait))
            guard !Task.isCancelled, model.stage == .record, clip.take != nil else { return }
            model.advance()
        }
        #endif
    }
}

// MARK: - 6. Sending your clip

/// The clip going to storage, with how much of it has gone. This is an
/// upload and is called one: nothing here looks at the movement. A failed
/// upload says so in the server's words and offers to try again.
private struct UploadStage: View {
    @Bindable var model: SessionModel
    @Environment(AppModel.self) private var app
    @Environment(ExerciseStore.self) private var store

    private var clip: AttemptClip { model.clip }
    private var required: Bool { model.a.videoRequirement == .required }

    var body: some View {
        StageFrame(model: model) {
            switch clip.phase {
            case .staged(let take, _):
                StageHeading(title: "Your clip is uploaded.",
                             sub: "\(model.therapist) gets it with your answers.")
                Card(tint: true) {
                    VStack(spacing: 12) {
                        ExerciseSeal(size: 64)
                        Text("Uploaded\(MP.dot)\(AttemptChip.size(take.data.count))")
                            .mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        if take.isSample {
                            Text("A sample clip, for this demo.").mpFont(.label).mpSecondary()
                        }
                    }
                    .frame(maxWidth: .infinity, minHeight: 150)
                    .accessibilityElement(children: .combine)
                }
            case .failed(let message, _):
                StageHeading(title: "That didn’t go through.")
                Card {
                    VStack(spacing: 12) {
                        Image(systemName: "video.slash").font(.system(size: 34)).foregroundStyle(MP.riskMed)
                            .accessibilityHidden(true)
                        Text("The clip didn’t upload").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text(message).mpFont(.copy).mpSecondary().multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, minHeight: 150)
                    .accessibilityElement(children: .combine)
                }
            default:
                StageHeading(title: "Sending your clip.", sub: "Keep the app open until it has gone.")
                Card {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(alignment: .firstTextBaseline) {
                            BigFigure(value: "\(Int((fraction * 100).rounded()))", unit: "%", size: MPSize.displayL)
                            Spacer()
                            if let take = clip.take {
                                Text(AttemptChip.size(take.data.count)).font(.figuresLabel).foregroundStyle(MP.muted)
                            }
                        }
                        UploadLine(fraction: fraction)
                        Text("Uploading your clip").mpFont(.copy).foregroundStyle(MP.body)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        } bottom: {
            switch clip.phase {
            case .staged:
                PrimaryButton(title: "Continue") { model.advance() }
            case .failed(_, let take):
                if take != nil {
                    PrimaryButton(title: "Try again", icon: "arrow.clockwise") { send() }
                }
                if !required {
                    QuietAction(title: "Carry on without the clip") {
                        clip.remove()
                        model.advance()
                    }
                }
            default:
                PrimaryButton(title: "Uploading…", disabled: true) {}
            }
        }
        .mpCompletionFeedback(clip.staged != nil)
        .task {
            #if DEBUG
            if clip.phase == .none, model.debugPhase != nil || SessionModel.autopilot != nil {
                // Opened straight at this stage: take the sample first.
                await clip.useSample(for: model.a, store: store, api: app.api)
            }
            switch model.debugPhase {
            case "hold":
                clip.debugHold(uploading: 0.42)
                return
            case "failed":
                clip.debugHold(failure: "Can’t reach MedPull right now. Check your connection.")
                return
            default: break
            }
            #endif
            if case .taken = clip.phase { await clip.upload(api: app.api) }
            #if DEBUG
            if let wait = SessionModel.autopilot, clip.staged != nil {
                try? await Task.sleep(for: .seconds(wait))
                guard !Task.isCancelled, model.stage == .upload else { return }
                model.advance()
            }
            #endif
        }
    }

    private var fraction: Double {
        if case .uploading(_, let fraction) = clip.phase { return fraction }
        return 0
    }

    private func send() {
        Task { await clip.upload(api: app.api) }
    }
}

// MARK: - 7. How did it go?

/// The pain now, how hard it was, what was actually done, and a note. Sets,
/// reps and load come filled in from the dose (the sets from the count the
/// session kept) and are the person's to change: the therapist reads what
/// was really done. Send is the completion, with the clip and the clock.
private struct FinishStage: View {
    @Bindable var model: SessionModel
    @Environment(ExerciseStore.self) private var store
    @State private var pain: Int?
    @State private var effort: Int?
    @State private var counts: DoneCounts
    @State private var note = ""
    @State private var error: String?
    @FocusState private var typing: Bool

    init(model: SessionModel) {
        self.model = model
        _counts = State(initialValue: DoneCounts(model.a, unit: model.unit,
                                                 setsCounted: model.setsCounted > 0 ? model.setsCounted : nil))
    }

    var body: some View {
        let a = model.a
        StageFrame(model: model, spacing: 26) {
            StageHeading(pill: a.title, title: "Nice work. How’s the pain now?",
                         sub: "\(model.therapist) sees your answers with the rest of your week.")
            PainAnswer(value: $pain)
            VStack(alignment: .leading, spacing: 10) {
                Text("How hard was it?").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    .accessibilityAddTraits(.isHeader)
                if let target = a.rpeTarget {
                    Text("\(model.therapist) suggested around \(target)\(MP.dot)\(ExerciseWords.effort(target).lowercased()).")
                        .mpFont(.label).foregroundStyle(MP.muted)
                }
                EffortAnswer(value: $effort)
            }
            VStack(alignment: .leading, spacing: 10) {
                Text("What you actually did").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    .accessibilityAddTraits(.isHeader)
                DoneCountsCard(counts: $counts, a: a, unit: model.unit)
                Text("Filled in from \(model.therapist)’s dose. Change it to what you really did.")
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            VStack(alignment: .leading, spacing: 10) {
                Text("Anything to add?").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    .accessibilityAddTraits(.isHeader)
                TextField("A note for your therapist", text: $note,
                          prompt: Text("Optional: how it felt, what was hard").foregroundColor(MP.muted),
                          axis: .vertical)
                    .lineLimit(3...6).textFieldStyle(FieldStyle()).focused($typing)
            }
        } bottom: {
            if let error { ErrorBanner(text: error) }
            PrimaryButton(title: "Send to \(model.therapist)", loading: model.sending) { send() }
        }
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") {
                    typing = false
                    UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder),
                                                    to: nil, from: nil, for: nil)
                }
            }
        }
        .mpErrorFeedback(error)
        #if DEBUG
        .task {
            guard let wait = SessionModel.autopilot else { return }
            // What a lifter who did more than the dose would enter.
            try? await Task.sleep(for: .seconds(wait))
            pain = 3
            effort = 6
            if let reps = counts.reps { counts.reps = reps + 2 }
            if let load = counts.load { counts.load = load + model.unit.step * 2 }
            note = "Felt strong, added a little."
            try? await Task.sleep(for: .seconds(wait))
            guard !Task.isCancelled, model.stage == .finish else { return }
            send()
        }
        #endif
    }

    private func send() {
        guard !model.sending else { return }
        let a = model.a
        typing = false
        error = nil
        var body = ExerciseCompletionBody()
        body.painAfter = pain
        body.note = note.trimmingCharacters(in: .whitespacesAndNewlines)
        body.video = model.clip.staged
        body.effort = effort
        body.setsDone = counts.setsDone
        body.repsDone = a.holdIsUnit ? nil : counts.repsDone
        body.loadDoneKg = counts.loadDoneKg(unit: model.unit)
        body.wearableWorn = a.wearableRequirement == .off ? nil : (model.worn == true)
        body.startedAt = model.startedAt.map(Dates.iso)
        body.endedAt = model.endedAt.map(Dates.iso)
        model.sending = true
        Task {
            do {
                let updated = try await store.complete(a, body: body)
                model.updated = updated
                model.sending = false
                model.advance()
            } catch {
                model.sending = false
                // A refusal (a clip she required, the watch, a day already
                // done) is the server's own sentence, at the step that sends.
                self.error = ExerciseStore.sentence(for: error)
            }
        }
    }
}

// MARK: - 8. Done

private struct DoneStage: View {
    let model: SessionModel
    let close: () -> Void

    var body: some View {
        let a = model.updated ?? model.a
        // The server's length first, so this line and the card under it
        // never disagree by a second; the phone's own clock when it sent none.
        let seconds: Int? = a.sessionSeconds ?? {
            guard let from = model.startedAt, let to = model.endedAt else { return nil }
            return max(0, Int(to.timeIntervalSince(from).rounded()))
        }()
        let line = ["Sent to \(model.therapist)",
                    a.completion?.painAfter.map { "pain \($0)/10" },
                    a.completion?.effort.map { "effort \($0)/10" },
                    seconds.map(ExerciseWords.clock)]
            .compactMap { $0 }.joined(separator: MP.dot)
        StageFrame(model: model, strip: false) {
            VStack(spacing: 12) {
                ExerciseSeal()
                Text("That’s one done.").title(MPSize.displayS)
                    .accessibilityAddTraits(.isHeader)
                Text(line).mpFont(.copyLarge).foregroundStyle(MP.body)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 22).padding(.bottom, 4)
            OutcomeCard(a: a, unit: model.unit)
        } bottom: {
            PrimaryButton(title: "Done") { close() }
        }
    }
}

/// The session's screen when the row was settled from somewhere else while
/// it was open.
private struct AlreadySettled: View {
    let a: ExerciseAssignment
    let unit: LoadUnit
    let close: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                StageHeading(pill: a.title, title: a.isSkipped ? "This one was skipped." : "This one’s already done.")
                OutcomeCard(a: a, unit: unit)
            }
            .padding(.horizontal, 20).padding(.top, 6).padding(.bottom, 28)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            SheetControls { PrimaryButton(title: "Back to the exercise") { close() } }
        }
    }
}
