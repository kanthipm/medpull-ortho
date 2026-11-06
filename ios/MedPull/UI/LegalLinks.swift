import SwiftUI

/// Where the policy and the terms live. Both pages are on the marketing
/// site, so a change to either needs no app release.
enum Legal {
    static let privacy = URL(string: "https://medpull.app/privacy")!
    static let terms = URL(string: "https://medpull.app/terms")!
}

/// "Privacy Policy · Terms of Use" in label type. The App Store wants both
/// next to any subscription offer; the consent form owes them to everyone,
/// and Profile keeps them a tap away afterwards.
struct LegalLinks: View {
    var body: some View {
        HStack(spacing: 6) {
            Link("Privacy Policy", destination: Legal.privacy)
            Text(MP.dot).foregroundStyle(MP.muted)
            Link("Terms of Use", destination: Legal.terms)
        }
        .mpFont(.labelMedium)
        .foregroundStyle(MP.brandInk)
        .tint(MP.brandInk)
    }
}
