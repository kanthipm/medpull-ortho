import Observation
import SwiftUI

/// Light, dark, or whatever the phone is set to.
///
/// Every color in `MP` is already a light/dark pair, so nothing here picks
/// colors — it only decides which half of each pair the app renders. Like
/// the provider console (frontend/src/lib/theme.tsx), MedPull is designed
/// light-first: Light is the default, and Dark or System apply only once the
/// patient picks them.
enum AppearanceMode: String, CaseIterable, Identifiable {
    case light, dark, system

    var id: String { rawValue }

    var label: String {
        switch self {
        case .system: return "System"
        case .light: return "Light"
        case .dark: return "Dark"
        }
    }

    /// `nil` hands the choice back to Display & Brightness.
    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
}

/// The chosen mode, kept on device like the server URL in `AppConfig`.
/// One instance lives in the environment; the Profile screen writes it and
/// the app root reads it into `preferredColorScheme`.
@Observable
@MainActor
final class Appearance {
    private static let key = "appearance_mode"

    var mode: AppearanceMode {
        didSet { UserDefaults.standard.set(mode.rawValue, forKey: Self.key) }
    }

    /// Only a patient's own choice is ever stored (`didSet` runs on a change,
    /// not on this assignment), so an absent key means "never chose": light.
    init() {
        mode = AppearanceMode(rawValue: UserDefaults.standard.string(forKey: Self.key) ?? "") ?? .light
    }
}
