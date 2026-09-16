import SwiftUI
import VitalCore
import VitalHealthKit

@main
struct MedPullApp: App {
    final class Delegate: NSObject, UIApplicationDelegate {
        func application(
            _ application: UIApplication,
            didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
        ) -> Bool {
            // Navigation titles, the tab bar and anything else UIKit draws
            // ignore SwiftUI's font, so the typeface is set on those proxies
            // before the first screen appears.
            MPFont.applyUIKitAppearance()
            // Restores the Health SDK's stored configuration so background
            // delivery keeps running across launches without re-asking.
            VitalHealthKitClient.automaticConfiguration()
            return true
        }
    }

    @UIApplicationDelegateAdaptor private var delegate: Delegate
    @State private var app = AppModel()
    @State private var appearance = Appearance()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(app)
                .environment(appearance)
                .tint(MP.brand)
                // Set here, on the window's root, so sheets, the tab bar and
                // the keyboard follow the choice too.
                .preferredColorScheme(appearance.mode.colorScheme)
                .task { await app.bootstrap() }
                .onOpenURL { url in app.handle(url: url) }
        }
    }
}
