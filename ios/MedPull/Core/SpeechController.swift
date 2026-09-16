import AVFoundation
import Foundation
import Observation
import Speech

/// On-device speech in, spoken replies out. The transcript goes to the
/// backend copilot; nothing is recorded or kept.
@Observable
@MainActor
final class SpeechController {
    private(set) var transcript = ""
    private(set) var isListening = false
    private(set) var isSpeaking = false
    private(set) var authorized = false
    private(set) var errorText: String?

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private let synthesizer = AVSpeechSynthesizer()
    private let synthDelegate = SynthDelegate()

    /// Which voice to speak with lives in `SpokenVoice`, which re-resolves
    /// itself when the system's voice list changes. It used to be a one-shot
    /// `static let` here, which meant a voice downloaded while the app was
    /// running was never picked up.
    static var voiceLabel: String { SpokenVoice.shared.label }
    static var hasNaturalVoice: Bool { SpokenVoice.shared.isNatural }

    init() {
        synthesizer.delegate = synthDelegate
        synthDelegate.onFinish = { [weak self] in
            Task { @MainActor in self?.isSpeaking = false }
        }
    }

    var isAvailable: Bool { recognizer?.isAvailable ?? false }

    func requestAuthorization() async -> Bool {
        let speech = await withCheckedContinuation { (c: CheckedContinuation<SFSpeechRecognizerAuthorizationStatus, Never>) in
            SFSpeechRecognizer.requestAuthorization { c.resume(returning: $0) }
        }
        let mic = await AVAudioApplication.requestRecordPermission()
        authorized = speech == .authorized && mic
        if !authorized {
            errorText = "Allow the microphone and speech recognition in Settings to talk to MedPull."
        }
        return authorized
    }

    func startListening() {
        guard !isListening else { return }
        stopSpeaking()
        errorText = nil
        transcript = ""
        guard let recognizer, recognizer.isAvailable else {
            errorText = "Speech recognition isn't available right now."
            return
        }
        do {
            let audio = AVAudioSession.sharedInstance()
            try audio.setCategory(.playAndRecord, mode: .measurement, options: [.duckOthers, .defaultToSpeaker])
            try audio.setActive(true, options: .notifyOthersOnDeactivation)

            let request = SFSpeechAudioBufferRecognitionRequest()
            request.shouldReportPartialResults = true
            if recognizer.supportsOnDeviceRecognition {
                request.requiresOnDeviceRecognition = true
            }
            self.request = request

            let input = engine.inputNode
            let format = input.outputFormat(forBus: 0)
            input.removeTap(onBus: 0)
            input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
                request.append(buffer)
            }
            engine.prepare()
            try engine.start()
            isListening = true

            task = recognizer.recognitionTask(with: request) { [weak self] result, error in
                Task { @MainActor in
                    guard let self else { return }
                    if let result {
                        self.transcript = result.bestTranscription.formattedString
                    }
                    if error != nil || (result?.isFinal ?? false) {
                        self.tearDownAudio()
                    }
                }
            }
        } catch {
            errorText = "Couldn't start the microphone: \(error.localizedDescription)"
            tearDownAudio()
        }
    }

    /// Stops the microphone and returns what was heard.
    func stopListening() -> String {
        request?.endAudio()
        tearDownAudio()
        return transcript.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func tearDownAudio() {
        if engine.isRunning {
            engine.stop()
            engine.inputNode.removeTap(onBus: 0)
        }
        task?.cancel()
        task = nil
        request = nil
        isListening = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    func speak(_ text: String) {
        guard !text.isEmpty else { return }
        stopSpeaking()

        // Listening leaves the session in .playAndRecord with mode
        // .measurement, and .measurement deliberately strips output
        // processing and gain — speaking through it is thin and quiet rather
        // than absent, which is exactly what "the voice doesn't work" sounds
        // like. Every utterance therefore puts the session back to playback
        // first. The failure is reported instead of being swallowed by `try?`:
        // an unexplained silence is the worst version of this bug.
        let audio = AVAudioSession.sharedInstance()
        do {
            try audio.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            try audio.setActive(true)
        } catch {
            errorText = "Couldn't switch to playback audio: \(error.localizedDescription)"
            // Fall through and speak anyway — a quiet reply beats none.
        }

        let utterance = AVSpeechUtterance(string: text)
        // `voiceWithLanguage` is the fallback, not the default: it hands back
        // the compact voice, which is the flat one this all started with.
        utterance.voice = SpokenVoice.shared.voice ?? AVSpeechSynthesisVoice(language: "en-US")
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.95
        isSpeaking = true
        synthesizer.speak(utterance)
    }

    func stopSpeaking() {
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
        isSpeaking = false
    }
}

private final class SynthDelegate: NSObject, AVSpeechSynthesizerDelegate {
    var onFinish: (() -> Void)?

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        onFinish?()
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        onFinish?()
    }
}
