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
                // "Done", "Cancel" and toolbar text draw in, and #1976D2 is
                // 3.99:1 on dark canvas. brandInk is 5.35 / 7.25 on canvas.
                // A control whose FILL must stay #1976D2 (Toggle, Slider,
                // ProgressView) passes `.tint(MP.brand)` itself.
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
