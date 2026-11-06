import CoreMotion
import Observation
import SwiftUI

/// The phone as the instrument: device motion at 100 Hz for a jump (total
/// acceleration, gravity included, so flight reads as weightlessness), the
/// gravity vector for a balance hold or a joint angle. Nothing is computed
/// here beyond a live readout; the server turns samples into numbers so
/// every phone yields the same result by the same rule.
@Observable
@MainActor
final class SportsMotionRecorder {
    enum State: Equatable { case idle, recording, finished }

    static let rate = 100.0

    private(set) var state: State = .idle
    private(set) var accel: [[Double]] = []
    private(set) var gravity: [[Double]] = []
    private(set) var elapsed: TimeInterval = 0
    private(set) var liveMagnitude: Double = 9.81
    private(set) var liveTilt: Double = 0
    private(set) var unavailable: String?

    private let motion = CMMotionManager()
    private var started: Date?
    private var ticker: Task<Void, Never>?

    var isAvailable: Bool { motion.isDeviceMotionAvailable }

    func start(seconds: TimeInterval, hz: Double = SportsMotionRecorder.rate) {
        guard state != .recording else { return }
        guard motion.isDeviceMotionAvailable else {
            unavailable = "This device has no motion sensors."
            return
        }
        accel = []
        gravity = []
        elapsed = 0
        started = Date()
        state = .recording
        motion.deviceMotionUpdateInterval = 1.0 / hz
        motion.startDeviceMotionUpdates(using: .xArbitraryZVertical, to: .main) { [weak self] data, _ in
            guard let self, let d = data, self.state == .recording else { return }
            let g = d.gravity, u = d.userAcceleration
            let k = 9.80665
            let ax = (u.x + g.x) * k, ay = (u.y + g.y) * k, az = (u.z + g.z) * k
            self.accel.append([Self.r3(ax), Self.r3(ay), Self.r3(az)])
            self.gravity.append([Self.r3(g.x), Self.r3(g.y), Self.r3(g.z)])
            self.liveMagnitude = (ax * ax + ay * ay + az * az).squareRoot()
            self.liveTilt = atan2(-g.y, -g.z) * 180 / .pi
        }
        ticker = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(50))
                guard let self, self.state == .recording, let s = self.started else { return }
                self.elapsed = Date().timeIntervalSince(s)
                if self.elapsed >= seconds {
                    self.stop()
                    return
                }
            }
        }
    }

    func stop() {
        guard state == .recording else { return }
        motion.stopDeviceMotionUpdates()
        ticker?.cancel()
        ticker = nil
        if let s = started { elapsed = Date().timeIntervalSince(s) }
        state = .finished
    }

    func reset() {
        if state == .recording { stop() }
        state = .idle
        accel = []
        gravity = []
        elapsed = 0
        started = nil
        liveMagnitude = 9.81
    }

    /// The mean tilt of the phone's long axis from horizontal over the last
    /// `seconds` of the recording, in degrees. The hold a joint angle reads.
    func meanTilt(seconds: Double) -> Double? {
        let n = min(gravity.count, Int(seconds * Self.rate))
        guard n >= 10 else { return nil }
        let tail = gravity.suffix(n)
        var sx = 0.0, sy = 0.0
        for g in tail {
            let t = atan2(-g[1], -g[2])
            sx += cos(t)
            sy += sin(t)
        }
        return atan2(sy, sx) * 180 / .pi
    }

    private nonisolated static func r3(_ v: Double) -> Double { (v * 1000).rounded() / 1000 }
}

// MARK: - Which test

enum PhoneTest: Identifiable, Hashable {
    case jump(testKey: String, side: String?)
    case balance
    case reaction
    case angle(measureKey: String?, injuryId: Int?)

    var id: String {
        switch self {
        case .jump(let k, let s): return "jump:\(k):\(s ?? "")"
        case .balance: return "balance"
        case .reaction: return "reaction"
        case .angle(let m, let i): return "angle:\(m ?? ""):\(i.map(String.init) ?? "")"
        }
    }
}

/// One sheet for every phone test: a NavigationStack around the flow.
struct PhoneTestHost: View {
    let test: PhoneTest
    var onDone: () -> Void

    var body: some View {
        NavigationStack {
            Group {
                switch test {
                case .jump(let key, let side): PhoneJumpView(testKey: key, side: side, onDone: onDone)
                case .balance: PhoneBalanceView(onDone: onDone)
                case .reaction: ReactionTimeView(onDone: onDone)
                case .angle(let key, let injuryId): PhoneAngleView(measureKey: key, injuryId: injuryId, onDone: onDone)
                }
            }
            .ambientScreen()
        }
        .presentationDetents([.large])
        .interactiveDismissDisabled(false)
    }
}

// MARK: - Shared pieces

/// A big countdown numeral, then the recording ring with the seconds.
private struct CountdownView: View {
    let number: Int
    var body: some View {
        Text("\(number)")
            .font(.figuresDisplay(96, weight: .light))
            .foregroundStyle(MP.ink)
            .contentTransition(.numericText(countsDown: true))
            .frame(maxWidth: .infinity, minHeight: 180)
            .accessibilityLabel(Text("Starting in \(number)"))
    }
}

private struct RecordingRing: View {
    let progress: Double
    let label: String
    let detail: String
    var body: some View {
        ZStack {
            Circle().stroke(MP.track, lineWidth: 10)
            Circle().trim(from: 0, to: CGFloat(min(max(progress, 0), 1)))
                .stroke(MP.brand, style: StrokeStyle(lineWidth: 10, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.linear(duration: 0.05), value: progress)
            VStack(spacing: 2) {
                Text(label).font(.figuresDisplay(MPSize.displayM)).foregroundStyle(MP.ink)
                Text(detail).mpFont(.label).foregroundStyle(MP.muted)
            }
        }
        .frame(width: 160, height: 160)
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }
}

private struct SideChips: View {
    @Binding var side: String
    var body: some View {
        WrapChips(options: ["left", "right"], labels: ["left": "Left leg", "right": "Right leg"],
                  value: Binding(get: { .string(side) }, set: { if let s = $0?.stringValue { side = s } }))
    }
}

private struct StepLine: View {
    let number: Int
    let text: String
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text("\(number)").font(.figuresLabel).foregroundStyle(MP.brandInk)
                .frame(width: 22, height: 22)
                .background(Circle().fill(MP.brandTint))
            Text(text).mpFont(.copy).foregroundStyle(MP.ink).lineSpacing(2)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - Jump

/// Countermovement jump by flight time. Hold the phone flat against the
/// sternum with both hands, jump for height, land softly on both feet.
struct PhoneJumpView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let testKey: String
    @State var side: String?
    var onDone: () -> Void

    private enum Phase: Equatable { case setup, countdown, recording, sending, result }
    @State private var recorder = SportsMotionRecorder()
    @State private var phase: Phase = .setup
    @State private var count = 3
    @State private var attempts: [PhoneJumpResponse] = []
    @State private var latest: PhoneJumpResponse?
    @State private var error: String?
    @State private var legSide = "left"

    private var sided: Bool { testKey == "single_leg_cmj" }
    private var imperial: Bool { app.me?.sports?.isImperial ?? true }
    private var title: String { sided ? "Single-leg jump" : "Jump height" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                switch phase {
                case .setup: setup
                case .countdown: CountdownView(number: count)
                case .recording: recording
                case .sending: LoadingCard(text: "Reading the flight…")
                case .result: result
                }
                if let error { ErrorBanner(text: error) }
                if let u = recorder.unavailable { ErrorBanner(text: u) }
                SportsGuardrail()
            }
            .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
        }
        .mpNavigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button(phase == .result ? "Done" : "Cancel") { finish() }.mpFont(.copyLargeMedium)
            }
        }
        .onDisappear { recorder.reset() }
        .onChange(of: recorder.state) { _, s in if s == .finished && phase == .recording { send() } }
        .mpErrorFeedback(error)
        .mpCompletionFeedback(phase == .result && error == nil)
    }

    private var setup: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(sided ? "One leg, phone to your chest." : "Phone to your chest. Jump.").title(MPSize.displayS)
            Card {
                VStack(alignment: .leading, spacing: 12) {
                    StepLine(number: 1, text: "Hold the phone flat against your breastbone with both hands, screen facing in.")
                    StepLine(number: 2, text: sided
                             ? "Stand on the \(legSide) leg. After the count, jump as high as you can and land on the same leg, softly."
                             : "After the count, dip and jump as high as you can. Land on both feet with soft knees, the same way you took off.")
                    StepLine(number: 3, text: "Keep still for a second after landing. The phone listens for six seconds.")
                }
            }
            if sided { SideChips(side: $legSide) }
            Text("Flight-time heights run a few centimetres high against a force plate and depend on landing the way you took off, so this compares with your own phone jumps, not the plate.")
                .mpFont(.label).foregroundStyle(MP.muted)
                .fixedSize(horizontal: false, vertical: true)
            PrimaryButton(title: "Start the count", icon: "figure.jumprope", disabled: !recorder.isAvailable) { begin() }
        }
    }

    private var recording: some View {
        VStack(spacing: 16) {
            RecordingRing(progress: recorder.elapsed / 6, label: String(format: "%.1f", max(0, 6 - recorder.elapsed)), detail: "jump now")
            Text(recorder.liveMagnitude < 3 ? "In the air" : recorder.liveMagnitude > 14 ? "Push" : "Listening")
                .mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                .frame(maxWidth: .infinity)
                .accessibilityHidden(true)
            SecondaryButton(title: "Stop early", icon: "stop.fill") { recorder.stop() }
        }
    }

    private var result: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let r = latest {
                Card(tint: true) {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            BigFigure(value: imperial ? String(format: "%.1f", r.heightIn) : String(format: "%.1f", r.heightCm),
                                      unit: imperial ? "in" : "cm", size: MPSize.displayL)
                            Spacer()
                            StatusPill(text: r.confidence == "high" ? "Clean" : r.confidence == "med" ? "Fair read" : "Rough read",
                                       tone: r.confidence == "high" ? .low : r.confidence == "med" ? .med : .missing)
                        }
                        Text(imperial ? String(format: "%.1f cm", r.heightCm) : String(format: "%.1f in", r.heightIn))
                            .mpFont(.copy).mpSecondary()
                        HStack(spacing: 14) {
                            Stat(label: "Flight", value: String(format: "%.0f", r.flightTimeMs), unit: "ms")
                            Stat(label: "Takeoff", value: String(format: "%.1f", r.takeoffPeakMs2 / 9.80665), unit: "g")
                            Stat(label: "Landing", value: String(format: "%.1f", r.landingPeakMs2 / 9.80665), unit: "g")
                        }
                        Text(r.id == nil ? "Not saved." : sided ? "Saved as a \(legSide)-leg jump." : "Saved to your tests.")
                            .mpFont(.label).mpSecondary()
                    }
                }
            }
            if attempts.count > 1 {
                Card(padding: 0) {
                    VStack(spacing: 0) {
                        CardTitleRow("This session", note: "best \(String(format: "%.1f", attempts.map(\.heightCm).max() ?? 0)) cm")
                        ForEach(Array(attempts.enumerated()), id: \.offset) { i, a in
                            HStack {
                                Text("Jump \(i + 1)").mpFont(.copyLarge).foregroundStyle(MP.ink)
                                Spacer()
                                RowFigure(value: imperial ? String(format: "%.1f", a.heightIn) : String(format: "%.1f", a.heightCm),
                                          unit: imperial ? "in" : "cm")
                            }
                            .padding(.horizontal, 16).padding(.vertical, 8)
                            if i < attempts.count - 1 { InsetDivider(leading: 16) }
                        }
                    }
                    .padding(.bottom, 8)
                }
            }
            PrimaryButton(title: "Jump again", icon: "arrow.counterclockwise") { phase = .setup; error = nil }
            if sided {
                SecondaryButton(title: "Other leg", icon: "arrow.left.arrow.right") {
                    legSide = legSide == "left" ? "right" : "left"
                    phase = .setup
                }
            }
        }
    }

    private func begin() {
        error = nil
        phase = .countdown
        count = 3
        Task {
            for n in stride(from: 3, through: 1, by: -1) {
                count = n
                try? await Task.sleep(for: .seconds(1))
            }
            recorder.reset()
            recorder.start(seconds: 6)
            phase = .recording
        }
    }

    private func send() {
        phase = .sending
        let body = APIClient.JumpBody(accel: recorder.accel, sampleRateHz: SportsMotionRecorder.rate, testKey: testKey,
                                      side: sided ? legSide : nil, recordedAt: Dates.iso(Date()),
                                      deviceModel: UIDeviceName.current, save: true)
        Task {
            do {
                let r = try await app.api.sportsPhoneJump(body)
                latest = r
                attempts.append(r)
                phase = .result
            } catch {
                self.error = AppModel.message(for: error)
                phase = .setup
            }
        }
    }

    private func finish() {
        recorder.reset()
        if !attempts.isEmpty { onDone() }
        dismiss()
    }
}

// MARK: - Balance

/// Single-leg balance: how long the stance holds and how much the trunk
/// sways, each leg. Phone at the chest; eyes open; stop when the other
/// foot touches down.
struct PhoneBalanceView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    var onDone: () -> Void

    private enum Phase: Equatable { case setup, countdown, recording, sending, result }
    @State private var recorder = SportsMotionRecorder()
    @State private var phase: Phase = .setup
    @State private var count = 3
    @State private var side = "left"
    @State private var results: [String: PhoneBalanceResponse] = [:]
    @State private var error: String?

    private static let limit = 30.0

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                switch phase {
                case .setup: setup
                case .countdown: CountdownView(number: count)
                case .recording: recording
                case .sending: LoadingCard(text: "Reading the sway…")
                case .result: result
                }
                if let error { ErrorBanner(text: error) }
                if let u = recorder.unavailable { ErrorBanner(text: u) }
                SportsGuardrail()
            }
            .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
        }
        .mpNavigationTitle("Single-leg balance")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button(phase == .result ? "Done" : "Cancel") { recorder.reset(); if !results.isEmpty { onDone() }; dismiss() }
                    .mpFont(.copyLargeMedium)
            }
        }
        .onDisappear { recorder.reset() }
        .onChange(of: recorder.state) { _, s in if s == .finished && phase == .recording { send() } }
        .mpErrorFeedback(error)
    }

    private var setup: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Stand on one leg.\nHold still.").title(MPSize.displayS)
            Card {
                VStack(alignment: .leading, spacing: 12) {
                    StepLine(number: 1, text: "Phone flat against your chest, both hands. Eyes open, looking straight ahead.")
                    StepLine(number: 2, text: "After the count, lift the other foot and hold as still as you can, up to 30 seconds.")
                    StepLine(number: 3, text: "The moment the other foot touches down, tap Stop. Both legs, one after the other.")
                }
            }
            SideChips(side: $side)
            if !results.isEmpty { comparison }
            PrimaryButton(title: "Start the count", icon: "figure.stand", disabled: !recorder.isAvailable) { begin() }
        }
    }

    private var recording: some View {
        VStack(spacing: 16) {
            RecordingRing(progress: recorder.elapsed / Self.limit, label: String(format: "%.0f", recorder.elapsed), detail: "seconds")
            Text(String(format: "Sway %.1f°", abs(recorder.liveTilt)))
                .font(.figuresCopyLarge).foregroundStyle(MP.muted)
                .frame(maxWidth: .infinity)
                .accessibilityHidden(true)
            PrimaryButton(title: "Stop, foot down", icon: "stop.fill") { recorder.stop() }
        }
    }

    private var result: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let r = results[side] {
                Card(tint: true) {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .firstTextBaseline) {
                            BigFigure(value: String(format: "%.0f", r.seconds), unit: "s", size: MPSize.displayL)
                            Spacer()
                            Text("\(side.capitalized) leg").mpFont(.copyMedium).foregroundStyle(MP.ink)
                        }
                        HStack(spacing: 14) {
                            Stat(label: "Mean sway", value: String(format: "%.1f", r.swayDegMean), unit: "°")
                            Stat(label: "Max sway", value: String(format: "%.1f", r.swayDegMax), unit: "°")
                            Stat(label: "Steadiness", value: String(format: "%.0f", r.steadiness), unit: "/100")
                        }
                        Text(r.id == nil ? "Not saved." : "Saved to your tests, and to your injury plan if one is active.")
                            .mpFont(.label).mpSecondary()
                    }
                }
            }
            comparison
            if results.count < 2 {
                PrimaryButton(title: "Now the \(side == "left" ? "right" : "left") leg", icon: "arrow.left.arrow.right") {
                    side = side == "left" ? "right" : "left"
                    phase = .setup
                }
            }
            SecondaryButton(title: "Again on this leg", icon: "arrow.counterclockwise") { phase = .setup }
        }
    }

    @ViewBuilder private var comparison: some View {
        if results.count == 2, let l = results["left"], let r = results["right"] {
            Card {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Left against right").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    SymmetryBar(left: l.seconds, right: r.seconds, unit: "s", decimals: 0, higherIsBetter: true, flagPct: 25)
                    SymmetryBar(left: l.swayDegMean, right: r.swayDegMean, leftLabel: "Sway L", rightLabel: "Sway R",
                                unit: "°", decimals: 1, higherIsBetter: false, flagPct: 30)
                }
            }
        }
    }

    private func begin() {
        error = nil
        phase = .countdown
        Task {
            for n in stride(from: 3, through: 1, by: -1) {
                count = n
                try? await Task.sleep(for: .seconds(1))
            }
            recorder.reset()
            recorder.start(seconds: Self.limit, hz: 50)
            phase = .recording
        }
    }

    private func send() {
        phase = .sending
        let held = recorder.elapsed
        let body = APIClient.BalanceBody(gravity: recorder.gravity, sampleRateHz: 50, side: side,
                                         secondsHeld: (held * 10).rounded() / 10, save: true)
        Task {
            do {
                results[side] = try await app.api.sportsPhoneBalance(body)
                phase = .result
            } catch {
                self.error = AppModel.message(for: error)
                phase = .setup
            }
        }
    }
}

// MARK: - Reaction time

/// Simple visual reaction time: the screen turns lime after a random wait,
/// the athlete taps, five goes, the median is logged. A false start is a
/// retry, not a number.
struct ReactionTimeView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    var onDone: () -> Void

    private enum Phase: Equatable { case intro, waiting, go, tooSoon, done }
    @State private var phase: Phase = .intro
    @State private var times: [Double] = []
    @State private var goAt: Date?
    @State private var waiter: Task<Void, Never>?
    @State private var saving = false
    @State private var saved = false
    @State private var error: String?

    private static let trials = 5
    private var median: Double? {
        guard !times.isEmpty else { return nil }
        let s = times.sorted()
        return s.count % 2 == 1 ? s[s.count / 2] : (s[s.count / 2 - 1] + s[s.count / 2]) / 2
    }

    var body: some View {
        VStack(spacing: 16) {
            if phase == .intro {
                intro
            } else if phase == .done {
                done
            } else {
                pad
            }
        }
        .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
        .mpNavigationTitle("Reaction time")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button(phase == .done ? "Done" : "Cancel") { waiter?.cancel(); if saved { onDone() }; dismiss() }
                    .mpFont(.copyLargeMedium)
            }
        }
        .onDisappear { waiter?.cancel() }
        .mpErrorFeedback(error)
        .mpCompletionFeedback(saved)
    }

    private var intro: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Tap the moment\nit turns green.").title(MPSize.displayS)
            Card {
                VStack(alignment: .leading, spacing: 12) {
                    StepLine(number: 1, text: "Hold the phone in both thumbs' reach and watch the grey panel.")
                    StepLine(number: 2, text: "It turns green after one to four seconds. Tap it as fast as you can.")
                    StepLine(number: 3, text: "Five goes. Tapping early does not count; the median is your number.")
                }
            }
            Text("Simple reaction time sits around 200 to 250 ms for most athletes, and slows with fatigue, poor sleep and concussion. Compare it with your own.")
                .mpFont(.label).foregroundStyle(MP.muted)
                .fixedSize(horizontal: false, vertical: true)
            Spacer()
            PrimaryButton(title: "Start", icon: "bolt.fill") { arm() }
        }
    }

    private var pad: some View {
        VStack(spacing: 14) {
            HStack {
                Text("Go \(times.count + 1) of \(Self.trials)").mpFont(.labelMedium).foregroundStyle(MP.muted)
                Spacer()
                if let last = times.last { Text(String(format: "Last %.0f ms", last)).font(.figuresLabel).foregroundStyle(MP.ink) }
            }
            Button { tapped() } label: {
                ZStack {
                    MP.surfaceShape.fill(phase == .go ? MP.lime : phase == .tooSoon ? MP.riskHighBg : MP.soft)
                    VStack(spacing: 6) {
                        Text(phase == .go ? "TAP" : phase == .tooSoon ? "Too soon" : "Wait…")
                            .font(.figuresDisplay(MPSize.displayM, weight: .medium))
                            .foregroundStyle(phase == .go ? MP.ink : phase == .tooSoon ? MP.riskHigh : MP.muted)
                        if phase == .tooSoon {
                            Text("Tap to go again").mpFont(.copy).foregroundStyle(MP.body)
                        }
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 360)
                .contentShape(MP.surfaceShape)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(Text(phase == .go ? "Tap now" : "Wait for green"))
            .sensoryFeedback(.impact(weight: .heavy), trigger: phase == .go)
            Spacer()
        }
    }

    private var done: some View {
        VStack(alignment: .leading, spacing: 14) {
            Card(tint: true) {
                VStack(alignment: .leading, spacing: 10) {
                    BigFigure(value: median.map { String(format: "%.0f", $0) } ?? "—", unit: "ms median", size: MPSize.displayL)
                    Text(times.map { String(format: "%.0f", $0) }.joined(separator: MP.dot) + " ms")
                        .font(.figuresCopy).mpSecondary()
                    Text(saved ? "Saved to your tests." : saving ? "Saving…" : "")
                        .mpFont(.label).mpSecondary()
                }
            }
            if let error { ErrorBanner(text: error) }
            Spacer()
            PrimaryButton(title: "Again", icon: "arrow.counterclockwise") { times = []; saved = false; arm() }
        }
    }

    private func arm() {
        phase = .waiting
        goAt = nil
        waiter?.cancel()
        waiter = Task {
            let wait = Double.random(in: 1.5...4.0)
            try? await Task.sleep(for: .seconds(wait))
            guard !Task.isCancelled, phase == .waiting else { return }
            goAt = Date()
            phase = .go
        }
    }

    private func tapped() {
        switch phase {
        case .waiting:
            waiter?.cancel()
            phase = .tooSoon
        case .tooSoon:
            arm()
        case .go:
            guard let at = goAt else { return }
            let ms = Date().timeIntervalSince(at) * 1000
            times.append((ms * 10).rounded() / 10)
            if times.count >= Self.trials {
                phase = .done
                save()
            } else {
                arm()
            }
        default:
            break
        }
    }

    private func save() {
        guard let m = median else { return }
        saving = true
        Task {
            defer { saving = false }
            do {
                _ = try await app.api.sportsLogTests([.init(testKey: "reaction_time", value: (m).rounded(), side: nil,
                                                            date: Dates.dayString(Date()), source: "phone",
                                                            device: UIDeviceName.current, note: nil)])
                saved = true
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

// MARK: - Joint angle

/// A joint angle from two holds: the phone's tilt in the reference
/// position, then in the moved position; the difference is the range. Lands
/// on the injury plan as a measure, or on Stats as a test when there is no
/// plan to attach it to.
struct PhoneAngleView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    var measureKey: String?
    var injuryId: Int?
    var onDone: () -> Void

    struct Protocol_: Identifiable {
        var id: String { key }
        let key: String
        let title: String
        let reference: String
        let movement: String
        let sided: Bool
        let testKey: String?
        let deficit: Bool
    }

    static let protocols: [Protocol_] = [
        Protocol_(key: "knee_flexion", title: "Knee bend",
                  reference: "Lie on your back, leg straight. Rest the phone's long edge along the shin, screen up, top toward the knee.",
                  movement: "Slide the heel toward you and bend the knee as far as it comfortably goes. Hold.", sided: true, testKey: nil, deficit: false),
        Protocol_(key: "knee_extension_deficit", title: "Knee straightening",
                  reference: "Lie on your back. Rest the phone flat on the bed beside the leg, screen up, top toward your head.",
                  movement: "Heel on a rolled towel, phone along the shin, press the knee as straight as it goes. Hold.", sided: true, testKey: nil, deficit: true),
        Protocol_(key: "hamstring_ake", title: "Hamstring (active knee extension)",
                  reference: "Lie on your back, hip and knee at 90°. Rest the phone along the shin, top toward the knee, foot relaxed.",
                  movement: "Straighten the knee as far as it goes without the thigh moving. Hold.", sided: true, testKey: "hamstring_ake", deficit: false),
        Protocol_(key: "hip_ir_rom", title: "Hip internal rotation",
                  reference: "Sit on a table, knees bent over the edge. Phone along the shin, top toward the knee, shin vertical.",
                  movement: "Swing the foot outward so the hip rotates inward, as far as it goes without lifting. Hold.", sided: true, testKey: "hip_internal_rotation", deficit: false),
        Protocol_(key: "thomas_test", title: "Hip flexor (Thomas)",
                  reference: "Lie at the end of a table, both knees to the chest. Phone flat on the table beside you.",
                  movement: "Let the test leg hang. Phone along the thigh, top toward the hip. Hold.", sided: true, testKey: nil, deficit: true),
        Protocol_(key: "shoulder_ir", title: "Shoulder internal rotation",
                  reference: "Lie on your back, arm out to the side, elbow at 90°, forearm vertical. Phone along the forearm, top toward the hand.",
                  movement: "Let the forearm fall toward the hip as far as it goes with the shoulder blade down. Hold.", sided: true, testKey: "shoulder_ir_rom", deficit: false),
    ]

    private enum Phase: Equatable { case setup, reference, movement, result }
    @State private var recorder = SportsMotionRecorder()
    @State private var phase: Phase = .setup
    @State private var picked: Protocol_ = PhoneAngleView.protocols[0]
    @State private var side = "left"
    @State private var referenceTilt: Double?
    @State private var angle: Double?
    @State private var holding = false
    @State private var saving = false
    @State private var saved = false
    @State private var error: String?

    private static let hold = 3.0

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                switch phase {
                case .setup: setup
                case .reference, .movement: holdView
                case .result: result
                }
                if let error { ErrorBanner(text: error) }
                if let u = recorder.unavailable { ErrorBanner(text: u) }
                SportsGuardrail()
            }
            .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
        }
        .mpNavigationTitle("Joint angle")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button(phase == .result ? "Done" : "Cancel") { recorder.reset(); if saved { onDone() }; dismiss() }
                    .mpFont(.copyLargeMedium)
            }
        }
        .onAppear {
            if let key = measureKey, let p = Self.protocols.first(where: { $0.key == key }) { picked = p }
        }
        .onDisappear { recorder.reset() }
        .onChange(of: recorder.state) { _, s in if s == .finished && holding { captured() } }
        .mpErrorFeedback(error)
        .mpCompletionFeedback(saved)
    }

    private var setup: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Two holds, three seconds each.").title(MPSize.displayS)
            if measureKey == nil {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Which joint").mpFont(.labelMedium).foregroundStyle(MP.muted)
                    WrapChips(options: Self.protocols.map(\.key),
                              labels: Dictionary(uniqueKeysWithValues: Self.protocols.map { ($0.key, $0.title) }),
                              value: Binding(get: { .string(picked.key) },
                                             set: { if let k = $0?.stringValue, let p = Self.protocols.first(where: { $0.key == k }) { picked = p } }))
                }
            } else {
                Text(picked.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
            }
            if picked.sided { SideChips(side: $side) }
            Card {
                VStack(alignment: .leading, spacing: 12) {
                    StepLine(number: 1, text: picked.reference)
                    StepLine(number: 2, text: picked.movement)
                    StepLine(number: 3, text: "The phone reads its own tilt in each hold. The difference is the angle.")
                }
            }
            PrimaryButton(title: "Start the reference hold", icon: "figure.flexibility", disabled: !recorder.isAvailable) {
                referenceTilt = nil
                angle = nil
                error = nil
                phase = .reference
                startHold()
            }
        }
    }

    private var holdView: some View {
        VStack(spacing: 16) {
            Text(phase == .reference ? "Reference hold" : "Now the movement").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
            Text(phase == .reference ? picked.reference : picked.movement)
                .mpFont(.copy).foregroundStyle(MP.body).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            RecordingRing(progress: recorder.elapsed / Self.hold,
                          label: String(format: "%.0f°", abs(recorder.liveTilt)), detail: "hold still")
            if !holding {
                PrimaryButton(title: "Hold now, 3 seconds", icon: "hand.raised.fill") { startHold() }
            }
        }
    }

    private var result: some View {
        VStack(alignment: .leading, spacing: 14) {
            Card(tint: true) {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .firstTextBaseline) {
                        BigFigure(value: angle.map { String(format: "%.0f", $0) } ?? "—", unit: "°", size: MPSize.displayL)
                        Spacer()
                        Text(picked.sided ? "\(picked.title), \(side)" : picked.title).mpFont(.copyMedium).foregroundStyle(MP.ink)
                            .multilineTextAlignment(.trailing)
                    }
                    Text(picked.deficit ? "The deficit from straight. Zero is full extension." : "The range between the two holds.")
                        .mpFont(.label).mpSecondary()
                    Text(saved ? (injuryId != nil ? "Saved to your injury plan." : "Saved to your tests.")
                         : saving ? "Saving…" : injuryId == nil && picked.testKey == nil ? "Shown only: there is no active injury plan to attach it to." : "")
                        .mpFont(.label).mpSecondary()
                }
            }
            if picked.sided {
                SecondaryButton(title: "Other side", icon: "arrow.left.arrow.right") {
                    side = side == "left" ? "right" : "left"
                    saved = false
                    phase = .setup
                }
            }
            SecondaryButton(title: "Measure again", icon: "arrow.counterclockwise") { saved = false; phase = .setup }
        }
    }

    private func startHold() {
        holding = true
        recorder.reset()
        recorder.start(seconds: Self.hold, hz: 50)
    }

    private func captured() {
        holding = false
        guard let tilt = recorder.meanTilt(seconds: 2) else {
            error = "The hold was too short to read. Try again."
            return
        }
        if phase == .reference {
            referenceTilt = tilt
            phase = .movement
        } else if phase == .movement, let ref = referenceTilt {
            var a = abs(tilt - ref)
            if a > 180 { a = 360 - a }
            angle = (a * 10).rounded() / 10
            phase = .result
            save()
        }
    }

    private func save() {
        guard let angle else { return }
        saving = true
        Task {
            defer { saving = false }
            do {
                if let injuryId {
                    _ = try await app.api.sportsLogMeasures(injuryId: injuryId, [
                        .init(measureKey: picked.key, value: angle, side: picked.sided ? side : nil,
                              date: Dates.dayString(Date()), source: "phone", note: nil)])
                    saved = true
                } else if let testKey = picked.testKey {
                    _ = try await app.api.sportsLogTests([
                        .init(testKey: testKey, value: angle, side: picked.sided ? side : nil, date: Dates.dayString(Date()),
                              source: "phone", device: UIDeviceName.current, note: nil)])
                    saved = true
                }
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}
