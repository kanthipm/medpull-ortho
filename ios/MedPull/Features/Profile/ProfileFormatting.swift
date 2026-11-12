import Foundation

/// The two formatters other screens borrow from Profile. They live in their
/// own file because the demo app (ios/MedPullDemo) has a different
/// `ProfileView` and compiles the screens that call these: both targets
/// build this file against their own type.
extension ProfileView {
    /// "1.0 (20261029)", as the App Store and TestFlight print it.
    static var versionLine: String {
        let info = Bundle.main.infoDictionary ?? [:]
        let short = info["CFBundleShortVersionString"] as? String ?? "?"
        let build = info["CFBundleVersion"] as? String ?? "?"
        return "\(short) (\(build))"
    }

    /// "2026-08-28" -> "Aug 28, 2026" in the reader's locale. A string that
    /// is not an ISO day comes back unchanged.
    static func displayDate(_ iso: String) -> String {
        let parser = DateFormatter()
        parser.calendar = Calendar(identifier: .gregorian)
        parser.locale = Locale(identifier: "en_US_POSIX")
        parser.timeZone = .current
        parser.dateFormat = "yyyy-MM-dd"
        guard let date = parser.date(from: String(iso.prefix(10))) else { return iso }
        return date.formatted(.dateTime.month(.abbreviated).day().year())
    }
}
