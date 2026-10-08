import SwiftUI

/// MedPull's own measurements, taken with the phone and computed on the
/// server the same way for every patient: a guided walk (gait), the
/// six-minute walk (endurance) and a joint range-of-motion test (the phone
/// as an inclinometer). The Measure tab (MeasureTab.swift) lists them.
enum MeasureFlow: String, CaseIterable, Identifiable {
    case guidedWalk, sixMinuteWalk, rangeOfMotion
    var id: String { rawValue }
    var title: String {
        switch self {
        case .guidedWalk: return "Guided walk"
        case .sixMinuteWalk: return "Six-minute walk"
        case .rangeOfMotion: return "Range of motion"
        }
    }
    var subtitle: String {
        switch self {
        case .guidedWalk: return "3 minutes, phone in your front pocket"
        case .sixMinuteWalk: return "How far you can walk in six minutes"
        case .rangeOfMotion: return "Phone on the limb, two short holds"
        }
    }
    var symbol: String {
        switch self {
        case .guidedWalk: return "figure.walk"
        case .sixMinuteWalk: return "timer"
        case .rangeOfMotion: return "angle"
        }
    }
}

// MARK: - Stature (the step-length model needs it once)

enum Stature {
    private static let key = "stature_cm"
    static var storedCm: Double? {
        let v = UserDefaults.standard.double(forKey: key)
        return v > 0 ? v : nil
    }
    static func store(_ cm: Double) { UserDefaults.standard.set(cm, forKey: key) }
}

private struct StatureField: View {
    @Binding var heightCm: Double?
    @State private var text = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Your height, in cm").mpFont(.label).mpSecondary()
            TextField("e.g. 172", text: $text)
                .keyboardType(.numberPad)
                .textFieldStyle(FieldStyle())
                .onChange(of: text) { _, new in
                    if let v = Double(new), (100...250).contains(v) {
                        heightCm = v
                        Stature.store(v)
                    } else {
                        heightCm = nil
                    }
                }
            Text("Step length and walking speed are worked out from your height; Health did not have it.")
                .mpFont(.label).mpSecondary()
        }
    }
}

// MARK: - Guided walk / six-minute walk

struct GuidedWalkView: View {
    let sixMinute: Bool
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var capture = MotionCapture()
    @State private var pocket = "left"
    @State private var outdoors = false
    @State private var heightCm: Double?
    @State private var uploading = false
    @State private var error: String?
    @State private var walkResult: MotionWindowSummary?
    @State private var testResult: SixMinuteWalkResponse?

    private var seconds: TimeInterval { sixMinute ? 360 : 180 }
    private var title: String { sixMinute ? "Six-minute walk" : "Guided walk" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                switch capture.state {
                case .idle: intro
                case .recording: recording
                case .finished: finished
                }
                if let error { ErrorBanner(text: error) }
            }
            .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 24)
        }
        .mpNavigationTitle(title)
        .toolbarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button(capture.state == .recording ? "Stop" : "Close") {
                    if capture.state == .recording { capture.stop() } else { dismiss() }
                }
            }
        }
        .ambientScreen()
        .mpErrorFeedback(error)
        .task {
            if let stored = Stature.storedCm {
                heightCm = stored
            } else if let cm = await MotionCapture.healthHeightCm() {
                heightCm = cm
                Stature.store(cm)
            }
        }
        .onDisappear { if capture.state == .recording { capture.stop() } }
    }

    private var intro: some View {
        Card {
            VStack(alignment: .leading, spacing: 14) {
                Text(sixMinute
                     ? "Walk as far as you can in six minutes at a steady pace, turning around as needed. Stop and rest if you need to; the timer keeps going."
                     : "Walk for three minutes at your usual pace, on level ground, without stopping. The phone reads your steps, rhythm and balance.")
                    .mpFont(.copy).foregroundStyle(MP.body)
                Text("Put the phone in a FRONT trouser pocket, top end up, then start.")
                    .mpFont(.copyMedium).foregroundStyle(MP.ink)
                VStack(alignment: .leading, spacing: 6) {
                    Text("Which pocket?").mpFont(.label).mpSecondary()
                    HStack(spacing: 10) {
                        Chip(label: "Left", selected: pocket == "left") { pocket = "left" }
                        Chip(label: "Right", selected: pocket == "right") { pocket = "right" }
                    }
                }
                Toggle(isOn: $outdoors) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Outdoors").mpFont(.copyMedium).foregroundStyle(MP.ink)
                        Text("Uses your location to measure the distance").mpFont(.label).mpSecondary()
                    }
                }
                .tint(MP.brand)
                if heightCm == nil { StatureField(heightCm: $heightCm) }
                if let u = capture.unavailable { ErrorBanner(text: u) }
                PrimaryButton(title: "Start", icon: "play.fill", disabled: !capture.isAvailable) {
                    error = nil
                    capture.start(seconds: seconds, outdoors: outdoors)
                }
            }
        }
    }

    private var recording: some View {
        Card(tint: true) {
            VStack(alignment: .leading, spacing: 12) {
                Text("Recording").mpFont(.label).mpSecondary()
                Text(clock(seconds - capture.elapsed))
                    .font(.figuresDisplay(56))
                    .foregroundStyle(MP.ink)
                    .monospacedDigit()
                    .accessibilityLabel(Text("\(Int(seconds - capture.elapsed)) seconds left"))
                HStack(spacing: 18) {
                    stat("\(capture.steps)", "steps")
                    if outdoors { stat(String(format: "%.0f m", capture.gpsDistance), "by GPS") }
                    else if let d = capture.pedometerDistance { stat(String(format: "%.0f m", d), "distance") }
                }
                Text("Keep walking. The phone stops on its own at \(clock(seconds)).")
                    .mpFont(.copy).mpSecondary()
                SecondaryButton(title: "Stop early", icon: "stop.fill") { capture.stop() }
            }
        }
    }

    private var finished: some View {
        VStack(alignment: .leading, spacing: 14) {
            Card {
                VStack(alignment: .leading, spacing: 12) {
                    if let r = walkResult, !sixMinute {
                        Text("Your walk").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        resultGrid([
                            (r.cadenceSpm.map { String(format: "%.0f", $0) } ?? "—", "steps / min"),
                            (r.walkingSpeedMps.map { String(format: "%.2f", $0) } ?? "—", "m/s"),
                            (r.stepLengthM.map { String(format: "%.2f", $0) } ?? "—", "m per step"),
                            (r.asymmetryPct.map { String(format: "%.0f%%", $0) } ?? "—", "asymmetry"),
                            (r.doubleSupportPct.map { String(format: "%.0f%%", $0) } ?? "—", "double support"),
                            (r.steadiness.map { String(format: "%.0f", $0) } ?? "—", "steadiness"),
                        ])
                        if r.bouts == 0 {
                            Text("No steady walking was found in the recording. Try again with the phone in a front pocket.")
                                .mpFont(.copy).mpSecondary()
                        }
                        ForEach(r.notes, id: \.self) { Text($0).mpFont(.label).mpSecondary() }
                    } else if let t = testResult {
                        Text("Six-minute walk").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        resultGrid([
                            (String(format: "%.0f", t.distanceM), "metres"),
                            (t.steps.map(String.init) ?? "—", "steps"),
                            (t.cadenceSpm.map { String(format: "%.0f", $0) } ?? "—", "steps / min"),
                            (t.fadePct.map { String(format: "%+.0f%%", $0) } ?? "—", "last vs first minute"),
                        ])
                        Text("Distance by \(t.method.replacingOccurrences(of: "_", with: " ")).")
                            .mpFont(.label).mpSecondary()
                    } else {
                        Text("Recorded \(clock(capture.elapsed)) · \(capture.steps) steps")
                            .mpFont(.copyMedium).foregroundStyle(MP.ink)
                        Text("Send it and the server works out your walking numbers.")
                            .mpFont(.copy).mpSecondary()
                        if heightCm == nil { StatureField(heightCm: $heightCm) }
                        PrimaryButton(title: "Send", icon: "arrow.up.circle.fill", loading: uploading) { send() }
                    }
                }
            }
            if walkResult != nil || testResult != nil {
                PrimaryButton(title: "Done") { dismiss() }
            } else {
                SecondaryButton(title: "Discard and retry") { capture.reset() }
            }
        }
    }

    private func send() {
        guard let window = capture.window(context: sixMinute ? "six_minute_walk" : "guided_walk",
                                          pocketSide: pocket) else {
            error = "The recording was too short to use."
            return
        }
        uploading = true
        error = nil
        Task {
            defer { uploading = false }
            do {
                if sixMinute {
                    let r = try await app.api.sixMinuteWalk(SixMinuteWalkUpload(
                        startedAt: window.startedAt, durationS: capture.elapsed, steps: capture.steps,
                        pedometerDistanceM: capture.pedometerDistance,
                        gpsDistanceM: outdoors && capture.gpsDistance > 0 ? capture.gpsDistance : nil,
                        gpsAccuracyM: outdoors ? capture.gpsAccuracy : nil,
                        minuteSteps: capture.minuteStepCounts.isEmpty ? nil : capture.minuteStepCounts,
                        heightCm: heightCm, deviceModel: UIKitDeviceName.name, motion: window
                    ))
                    testResult = r
                } else {
                    let r = try await app.api.uploadMotion(MotionUpload(
                        windows: [window], heightCm: heightCm, deviceModel: UIKitDeviceName.name
                    ))
                    walkResult = r.windows.first
                }
                await app.refreshPortfolio()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }

    private func stat(_ value: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value).font(.figures(MPSize.copy, weight: .medium)).foregroundStyle(MP.ink)
            Text(label).mpFont(.label).mpSecondary()
        }
    }

    private func resultGrid(_ items: [(String, String)]) -> some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())],
                  alignment: .leading, spacing: 12) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in stat(item.0, item.1) }
        }
    }

    private func clock(_ t: TimeInterval) -> String {
        let s = max(0, Int(t.rounded()))
        return String(format: "%d:%02d", s / 60, s % 60)
    }
}

// MARK: - Range of motion

struct RangeOfMotionView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var capture = MotionCapture()
    @State private var protocolKey = "knee_flexion_supine"
    @State private var side = "left"
    @State private var step = 0            // 0 setup · 1 reference hold · 2 movement hold · 3 result
    @State private var holding = false
    @State private var reference: [[Double]] = []
    @State private var movement: [[Double]] = []
    @State private var uploading = false
    @State private var error: String?
    @State private var result: RangeOfMotionResponse?

    private static let protocols: [(String, String, String, String)] = [
        // key, title, reference instruction, movement instruction
        ("knee_flexion_supine", "Knee: bend",
         "Lie on your back, leg straight. Rest the phone’s long edge on your shin, top end toward the knee, screen up.",
         "Slide your heel toward you and bend the knee as far as you comfortably can. Hold."),
        ("knee_extension_supine", "Knee: straighten",
         "Lie on your back. Rest the phone on the bed beside you, screen up, top end toward your head.",
         "Rest the phone on your shin, heel propped on a towel, and press the knee down as straight as it goes. Hold."),
        ("hip_flexion_supine", "Hip: bend",
         "Lie on your back, leg straight. Rest the phone on the front of your thigh, top end toward the hip.",
         "Bring the knee toward your chest as far as you comfortably can. Hold."),
        ("shoulder_flexion_standing", "Shoulder: raise forward",
         "Stand, arm hanging. Hold the phone against the outside of your upper arm, top end toward the shoulder.",
         "Raise the arm forward and up as far as you comfortably can. Hold."),
        ("shoulder_abduction_standing", "Shoulder: raise sideways",
         "Stand, arm hanging. Hold the phone against the outside of your upper arm, top end toward the shoulder.",
         "Raise the arm out to the side and up as far as you comfortably can. Hold."),
    ]
    private var current: (String, String, String, String) {
        Self.protocols.first { $0.0 == protocolKey } ?? Self.protocols[0]
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if step == 0 { setup } else if step == 3 { done } else { hold }
                if let error { ErrorBanner(text: error) }
            }
            .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 24)
        }
        .mpNavigationTitle("Range of motion")
        .toolbarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
        .ambientScreen()
        .mpErrorFeedback(error)
        .onDisappear { if capture.state == .recording { capture.stop() } }
    }

    private var setup: some View {
        Card {
            VStack(alignment: .leading, spacing: 14) {
                Text("The phone is the goniometer: two short holds, and the server reads the angle between them.")
                    .mpFont(.copy).foregroundStyle(MP.body)
                VStack(alignment: .leading, spacing: 6) {
                    Text("Movement").mpFont(.label).mpSecondary()
                    ForEach(Self.protocols, id: \.0) { p in
                        Chip(label: p.1, selected: protocolKey == p.0) { protocolKey = p.0 }
                    }
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("Side").mpFont(.label).mpSecondary()
                    HStack(spacing: 10) {
                        Chip(label: "Left", selected: side == "left") { side = "left" }
                        Chip(label: "Right", selected: side == "right") { side = "right" }
                    }
                }
                if let u = capture.unavailable { ErrorBanner(text: u) }
                PrimaryButton(title: "Begin", icon: "angle", disabled: !capture.isAvailable) {
                    error = nil
                    reference = []; movement = []
                    step = 1
                }
            }
        }
    }

    private var hold: some View {
        Card(tint: holding) {
            VStack(alignment: .leading, spacing: 12) {
                Text(step == 1 ? "1 of 2 · Starting position" : "2 of 2 · As far as it goes")
                    .mpFont(.label).mpSecondary()
                Text(step == 1 ? current.2 : current.3)
                    .mpFont(.copy).foregroundStyle(MP.body)
                if capture.state == .recording {
                    Text(String(format: "%.0f°", capture.liveTiltDegrees))
                        .font(.figuresDisplay(56)).foregroundStyle(MP.ink).monospacedDigit()
                    Text(holding ? "Hold still…" : "Live tilt").mpFont(.label).mpSecondary()
                }
                if !holding {
                    PrimaryButton(title: capture.state == .recording ? "Capture this position" : "Ready",
                                  icon: capture.state == .recording ? "checkmark.circle.fill" : "play.fill") {
                        if capture.state != .recording {
                            capture.start(seconds: 600, outdoors: false)
                        } else {
                            captureHold()
                        }
                    }
                }
            }
        }
    }

    private func captureHold() {
        holding = true
        Task {
            try? await Task.sleep(for: .seconds(2))
            let samples = capture.recentGravity(seconds: 2)
            holding = false
            if step == 1 {
                reference = samples
                step = 2
            } else {
                movement = samples
                capture.stop()
                send()
            }
        }
    }

    private var done: some View {
        VStack(alignment: .leading, spacing: 14) {
            Card {
                VStack(alignment: .leading, spacing: 10) {
                    if let r = result {
                        Text(current.1).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text(String(format: "%.0f°", r.angleDeg))
                            .font(.figuresDisplay(56)).foregroundStyle(MP.ink)
                        Text("\(r.joint.capitalized) \(r.movement), \(r.side) side" + (r.steady ? "" : " · the phone moved during a hold; consider repeating"))
                            .mpFont(.copy).mpSecondary()
                    } else if uploading {
                        HStack(spacing: 10) { ProgressView(); Text("Working out the angle…").mpFont(.copy).mpSecondary() }
                    }
                }
            }
            if result != nil {
                PrimaryButton(title: "Done") { dismiss() }
                SecondaryButton(title: "Measure again") { result = nil; capture.reset(); step = 0 }
            } else if !uploading {
                SecondaryButton(title: "Try again") { capture.reset(); step = 0 }
            }
        }
    }

    private func send() {
        step = 3
        uploading = true
        error = nil
        Task {
            defer { uploading = false }
            do {
                result = try await app.api.rangeOfMotion(RangeOfMotionUpload(
                    recordedAt: Dates.iso(Date()), protocolName: protocolKey, side: side,
                    reference: reference, movement: movement, deviceModel: UIKitDeviceName.name
                ))
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}
