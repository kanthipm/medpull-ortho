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

    /// Voices that are worse than the compact default, or that Apple doesn't
    /// let a third-party app use at all.
    private static let unusableVoicePrefixes = [
        "com.apple.eloquence",               // formant voices; robotic by design
        "com.apple.speech.synthesis.voice",  // novelty (Albert, Bells, Bad News)
        "com.apple.ttsbundle.siri",          // Siri's voices are off-limits to us
    ]

    /// The best voice installed on this phone, resolved once.
    ///
    /// `AVSpeechSynthesisVoice(language:)` hands back the *compact* voice — the
    /// flat, robotic one — even when something far better is installed. iOS 16
    /// added enhanced and premium (neural) voices: free, but over 100MB each, so
    /// the phone only has them once someone downloads them in Settings →
    /// Accessibility → Spoken Content → Voices. Prefer the best available and
    /// fall back gracefully, since we can't trigger that download ourselves.
    static let bestVoice: AVSpeechSynthesisVoice? = {
        let usable = AVSpeechSynthesisVoice.speechVoices().filter { voice in
            !unusableVoicePrefixes.contains { voice.identifier.hasPrefix($0) }
        }
        let enUS = usable.filter { $0.language == "en-US" }
        return (enUS.isEmpty ? usable : enUS).min { rank($0) < rank($1) }
    }()

    /// Best first: highest quality, then a known-good name so a phone with two
    /// premium voices installed picks the same one every launch.
    private static let preferredNames = ["Ava", "Evan", "Zoe", "Nathan", "Joelle", "Samantha"]

    private static func rank(_ voice: AVSpeechSynthesisVoice) -> (Int, Int, String) {
        (-voice.quality.rawValue,
         preferredNames.firstIndex(of: voice.name) ?? preferredNames.count,
         voice.name)
    }

    /// What the phone will actually speak with, for the Profile screen.
    static var voiceLabel: String {
        guard let voice = bestVoice else { return "System default" }
        switch voice.quality {
        case .premium: return "\(voice.name) (Premium)"
        case .enhanced: return "\(voice.name) (Enhanced)"
        default: return voice.name
        }
    }

    /// False when only the compact voice is installed, which is when the
    /// spoken replies sound like a 2011 satnav.
    static var hasNaturalVoice: Bool {
        (bestVoice?.quality.rawValue ?? 0) > AVSpeechSynthesisVoiceQuality.default.rawValue
    }

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
        let audio = AVAudioSession.sharedInstance()
        try? audio.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
        try? audio.setActive(true)
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = Self.bestVoice ?? AVSpeechSynthesisVoice(language: "en-US")
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
