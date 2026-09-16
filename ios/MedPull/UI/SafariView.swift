import SafariServices
import SwiftUI

/// Junction's hosted Link page, in-app.
struct SafariView: UIViewControllerRepresentable {
    let url: URL
    @Environment(\.colorScheme) private var scheme

    func makeUIViewController(context: Context) -> SFSafariViewController {
        let config = SFSafariViewController.Configuration()
        config.barCollapsingEnabled = true
        let vc = SFSafariViewController(url: url, configuration: config)
        vc.dismissButtonStyle = .done
        apply(to: vc)
        return vc
    }

    func updateUIViewController(_ uiViewController: SFSafariViewController, context: Context) {
        apply(to: uiViewController)
    }

    /// Safari would otherwise follow Display & Brightness, which reads as a
    /// flash of the wrong theme when the app is pinned to light or dark. The
    /// override also tells UIKit which half of the `MP` pairs to resolve.
    private func apply(to vc: SFSafariViewController) {
        vc.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        vc.preferredControlTintColor = UIColor(MP.brand)
        vc.preferredBarTintColor = UIColor(MP.panel)
    }
}
