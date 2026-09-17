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
            // before the first screen appears. This also seeds the Bold Text
            // state and re-applies both whenever Bold Text or the text size
            // changes in Settings (MPFont.startObservingAccessibility).
            MPFont.startObservingAccessibility()
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
                // brandInk, not brand: the tint is what native back buttons,
                // "Done", "Cancel" and toolbar text draw in, so it is the
                // sage TEXT colour (7.0 / 12.2 on canvas). A control whose
                // FILL should be the sage fill (Toggle, Slider) passes
                // `.tint(MP.brand)` itself.
                .tint(MP.brandInk)
                // Publishes @Environment(\.legibilityWeight) to every font
                // rung, so Bold Text re-renders text in place — no `.id`,
                // no lost check-in answers.
                .mpLegibilityBridge()
                // Set here, on the window's root, so sheets, the tab bar and
                // the keyboard follow the choice too.
                .preferredColorScheme(appearance.mode.colorScheme)
                .task { await app.bootstrap() }
                .onOpenURL { url in app.handle(url: url) }
        }
    }
}
