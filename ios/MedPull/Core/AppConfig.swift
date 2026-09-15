import Foundation

enum AppConfig {
    static let scheme = "medpull"

    /// The base URL the app was built with (MEDPULL_API_BASE_URL in project.yml).
    static let builtInBaseURL: URL = {
        if let raw = Bundle.main.object(forInfoDictionaryKey: "MedPullAPIBaseURL") as? String,
           !raw.isEmpty, let url = URL(string: raw) {
            return url
        }
        return URL(string: "http://localhost:8000")!
    }()

    /// The base URL in use: the one saved on the Profile screen, else the built-in.
    static var baseURL: URL {
        get {
            if let raw = UserDefaults.standard.string(forKey: "api_base_url"), let url = URL(string: raw) {
                return url
            }
            return builtInBaseURL
        }
        set { UserDefaults.standard.set(newValue.absoluteString, forKey: "api_base_url") }
    }

    static var appVersion: String {
        (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "1.0"
    }
}
