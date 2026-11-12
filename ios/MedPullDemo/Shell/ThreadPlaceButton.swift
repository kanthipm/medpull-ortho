import SwiftUI

/// The button under a thread line that a text carried with a link: it opens
/// the place the link names, the way a tap on the link in Messages does.
/// The shared `Bubble` draws it in the demo target only (`#if DEMO_APP` in
/// ios/MedPull/Features/Care/Conversation.swift); the real app has no
/// navigator for these places and draws the line as words.
struct ThreadPlaceButton: View {
    @Environment(DemoShell.self) private var shell
    let label: String
    let target: AppLinkTarget

    var body: some View {
        Button { shell.go(to: target) } label: {
            Label(label, systemImage: "arrow.right.circle.fill")
        }
        .buttonStyle(.mpFilled)
        .padding(.top, 2)
    }
}
