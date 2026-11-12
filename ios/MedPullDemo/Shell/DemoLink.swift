import Foundation

/// What a URL handed to the app asks for.
///
/// A demo text carries `https://<host>/a/<token>`. On a phone with this app
/// installed (and the host's association file naming it) that opens the app
/// as a universal link; the browser page for the same link offers
/// `medpulldemo://a/<token>`. Both mean the same thing. The token names a
/// person and a place and, on the demo stack, may sign the app in as that
/// person (`DemoShell.open`).
enum DemoLink: Equatable {
    /// `/a/<token>`: a link from a demo text.
    case token(String)
    /// `/t/<token>`: the older task link. It names a task and signs nobody
    /// in, so it opens only for the person already signed in.
    case taskToken(String)
    /// `medpulldemo://tasks/<id>`, as the real app answers `medpull://tasks/<id>`.
    case task(Int)
    /// `medpulldemo://exercises/<id>`: one assigned exercise.
    case exercise(Int)

    static let scheme = "medpulldemo"

    init?(url: URL) {
        let parts = url.pathComponents.filter { $0 != "/" }
        switch url.scheme?.lowercased() {
        case Self.scheme:
            // medpulldemo://a/<token>: the host is the first segment.
            guard let host = url.host?.lowercased(), let value = parts.first, parts.count == 1 else { return nil }
            switch host {
            case "a": self = .token(value)
            case "t": self = .taskToken(value)
            case "tasks":
                guard let id = Int(value) else { return nil }
                self = .task(id)
            case "exercises":
                guard let id = Int(value) else { return nil }
                self = .exercise(id)
            default: return nil
            }
        case "https", "http":
            guard parts.count == 2 else { return nil }
            switch parts[0] {
            case "a": self = .token(parts[1])
            case "t": self = .taskToken(parts[1])
            default: return nil
            }
        default:
            return nil
        }
    }
}
