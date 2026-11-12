import SwiftUI

/// MedPull Demo: the showcase's phone. It has no accounts. It asks the demo
/// server who its fictional people are, signs in as whichever one the
/// presenter picks, and then shows that person the same screens the real
/// app would (the shared files under ios/MedPull), with a switcher where the
/// real app has a profile.
@main
struct MedPullDemoApp: App {
    final class Delegate: NSObject, UIApplicationDelegate {
        func application(
            _ application: UIApplication,
            didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
        ) -> Bool {
            // UIKit's bars and titles take the typeface from these proxies
            // (see MedPullApp); the demo has no Health SDK to configure.
            MPFont.startObservingAccessibility()
            return true
        }
    }

    /// True inside the unit tests' host process. The tests only decode JSON
    /// and parse links, so the app shows nothing and calls no server while
    /// they run.
    private static let isUnderTest =
        ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
        || NSClassFromString("XCTestCase") != nil

    @UIApplicationDelegateAdaptor private var delegate: Delegate
    @State private var app: AppModel
    @State private var shell: DemoShell
    @State private var exercises: ExerciseStore
    @State private var appearance = Appearance()

    init() {
        let app = AppModel()
        let exercises = ExerciseStore(app: app)
        _app = State(initialValue: app)
        _exercises = State(initialValue: exercises)
        _shell = State(initialValue: DemoShell(app: app, exercises: exercises))
    }

    var body: some Scene {
        WindowGroup {
            if Self.isUnderTest {
                Color.clear
            } else {
                DemoRootView()
                    .environment(app)
                    .environment(shell)
                    .environment(exercises)
                    .environment(appearance)
                    // The sage text colour, for the same reason as MedPullApp.
                    .tint(MP.brandInk)
                    .mpLegibilityBridge()
                    .preferredColorScheme(appearance.mode.colorScheme)
                    .task { await shell.bootstrap() }
                    // A texted link reaches the app either way: as a
                    // universal link (https://<host>/a/<token>) or through
                    // the app's own scheme (medpulldemo://a/<token>).
                    .onOpenURL { url in shell.handle(url: url) }
                    .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                        if let url = activity.webpageURL { shell.handle(url: url) }
                    }
            }
        }
    }
}
