import Observation
import SwiftUI

/// Light, dark, or whatever the phone is set to.
///
/// Every color in `MP` is already a light/dark pair, so nothing here picks
/// colors — it only decides which half of each pair the app renders. The
/// provider console has the same switch (frontend/src/lib/theme.tsx) with two
/// states; on iOS "System" is the default people expect, so this is that
/// switch plus a passthrough.
enum AppearanceMode: String, CaseIterable, Identifiable {
    case system, light, dark

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

    init() {
        mode = AppearanceMode(rawValue: UserDefaults.standard.string(forKey: Self.key) ?? "") ?? .system
    }
}
