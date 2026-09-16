import AVFoundation
import Foundation
import Observation
import UIKit

/// Which voice the app speaks with, resolved live.
///
/// Two things this has to get right, and the previous one-shot `static let`
/// got both wrong.
///
/// **It cannot download Ava.** There is no public API for that, and the SDK is
/// explicit about whose job it is — `voiceWithIdentifier:` "returns nil if the
/// identifier is valid, but the voice is not available on device (i.e. not yet
/// downloaded by the user)". `requestPersonalVoiceAuthorization` is for the
/// user's *own* recorded Personal Voice, not for Apple's premium voices. So the
/// most an app can do is ask for Ava, notice the moment it appears, and say
/// plainly where to get it until then.
///
/// **It must notice.** Resolving once per process meant a voice downloaded
/// while the app was running was ignored until a force-quit — so the Profile
/// screen's promise that "MedPull uses it automatically" was not true. This
/// re-resolves on `availableVoicesDidChangeNotification` (which fires exactly
/// when the system's voice list changes) and again on foreground, because the
/// download happens in Settings with this app in the background.
@Observable
@MainActor
final class SpokenVoice {
    static let shared = SpokenVoice()

    /// The voice to speak with, or nil when the system has nothing usable.
    private(set) var voice: AVSpeechSynthesisVoice?

    private var observers: [NSObjectProtocol] = []

    private init() {
        voice = Self.resolve()
        let reresolve: (Notification) -> Void = { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
        var names: [Notification.Name] = [UIApplication.didBecomeActiveNotification]
        if #available(iOS 17.0, *) {
            names.append(AVSpeechSynthesizer.availableVoicesDidChangeNotification)
        }
        observers = names.map {
            NotificationCenter.default.addObserver(forName: $0, object: nil, queue: .main, using: reresolve)
        }
    }

    /// Re-pick the voice. Cheap, and assigning only on a real change keeps
    /// SwiftUI from redrawing the Profile screen on every foreground.
    func refresh() {
        let next = Self.resolve()
        if next?.identifier != voice?.identifier { voice = next }
    }

    // MARK: what to say it with

    /// The voice Steve asked for, best quality first. Matched by name rather
    /// than only by identifier: the documented spelling is
    /// `com.apple.voice.premium.en-US.Ava`, but the identifier layout is
    /// Apple's to change and the name is what a person actually picked in
    /// Settings.
    static let wantedName = "Ava"

    /// Voices that are worse than the compact default, or that Apple does not
    /// let a third-party app use.
    ///
    /// `com.apple.siri.` is the one that matters and the one the old list
    /// missed: it only excluded `com.apple.ttsbundle.siri`, but the Siri
    /// voices on a current OS are `com.apple.siri.natural.Damon` and friends.
    /// They are the only quality-2 voices on a phone with nothing downloaded,
    /// so the ranking below picked one every time — a Siri voice, chosen by
    /// the branch that exists to avoid Siri voices.
    private static let unusablePrefixes = [
        "com.apple.eloquence",               // formant voices; robotic by design
        "com.apple.speech.synthesis.voice",  // novelty (Albert, Bells, Bad News)
        "com.apple.ttsbundle.siri",          // older Siri bundles
        "com.apple.siri.",                   // current Siri voices
    ]

    /// Best first: highest quality, then a known-good name so a phone with two
    /// premium voices installed picks the same one every launch.
    private static let preferredNames = ["Ava", "Evan", "Zoe", "Nathan", "Joelle", "Samantha"]

    private static func usableVoices() -> [AVSpeechSynthesisVoice] {
        AVSpeechSynthesisVoice.speechVoices().filter { voice in
            !unusablePrefixes.contains { voice.identifier.hasPrefix($0) }
                && !voice.traitsIsNovelty
        }
    }

    private static func resolve() -> AVSpeechSynthesisVoice? {
        let usable = usableVoices()

        // 1. Ava, if she is installed at a quality worth having. Deliberately
        //    not Ava-at-any-quality: a compact Ava sounds worse than a premium
        //    Evan, and the point of the request was how it sounds.
        let ava = usable
            .filter { $0.name == wantedName && $0.quality.rawValue > AVSpeechSynthesisVoiceQuality.default.rawValue }
            .max { $0.quality.rawValue < $1.quality.rawValue }
        if let ava { return ava }

        // 2. Otherwise the best thing on the phone, English first.
        let english = usable.filter { $0.language.hasPrefix("en") }
        let enUS = usable.filter { $0.language == "en-US" }
        let pool = enUS.isEmpty ? (english.isEmpty ? usable : english) : enUS
        return pool.min { rank($0) < rank($1) }
    }

    private static func rank(_ voice: AVSpeechSynthesisVoice) -> (Int, Int, String) {
        (-voice.quality.rawValue,
         preferredNames.firstIndex(of: voice.name) ?? preferredNames.count,
         voice.name)
    }

    // MARK: what to tell the person

    /// What the phone will actually speak with, for the Profile screen.
    var label: String {
        guard let voice else { return "No usable voice installed" }
        switch voice.quality {
        case .premium: return "\(voice.name) (Premium)"
        case .enhanced: return "\(voice.name) (Enhanced)"
        default: return voice.name
        }
    }

    /// False when only the compact voice is installed, which is when the
    /// spoken replies sound like a 2011 satnav.
    var isNatural: Bool {
        (voice?.quality.rawValue ?? 0) > AVSpeechSynthesisVoiceQuality.default.rawValue
    }

    /// True once the requested voice is actually the one being used.
    var hasWantedVoice: Bool { voice?.name == Self.wantedName && isNatural }

    /// The sentence under the Profile row. It has to carry the one thing the
    /// app cannot do for them.
    var advice: String {
        if hasWantedVoice {
            return "MedPull is speaking with Ava. This is the voice on the Talk tab."
        }
        if isNatural {
            return "MedPull is using the best voice on this iPhone. For Ava, go to "
                + "Settings → Accessibility → Spoken Content → Voices → English and download "
                + "Ava (Premium) — MedPull switches to it as soon as it finishes, no restart."
        }
        return "This iPhone only has Apple's basic voice, which sounds flat. Apple does not let "
            + "an app download a voice, so it has to be done once by hand: Settings → "
            + "Accessibility → Spoken Content → Voices → English → Ava (Premium). MedPull picks "
            + "it up the moment it lands."
    }
}

private extension AVSpeechSynthesisVoice {
    /// Novelty voices self-identify from iOS 17; before that the identifier
    /// prefixes above are the only signal.
    var traitsIsNovelty: Bool {
        if #available(iOS 17.0, *) { return voiceTraits.contains(.isNoveltyVoice) }
        return false
    }
}
