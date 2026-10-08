import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        switch app.phase {
        case .launching:
            // The launch spinner takes the brand FILL explicitly (R10): the
            // root tint is `brandInk`, a text colour.
            ProgressView().tint(MP.brand).ambientScreen()
        case .onboarding:
            OnboardingFlow()
        case .home:
            MainTabs()
        }
    }
}

/// Four tabs for a hospital record, three for a personal space. Each tab
/// owns one question: Today (what now), Progress / Trends (am I getting
/// better), Measure (MedPull's own tests), Care / Coach (the thread).
/// Devices and settings live behind the avatar.
struct MainTabs: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        @Bindable var app = app
        TabView(selection: $app.selectedTab) {
            if app.isPersonal {
                PersonalHomeView()
                    .tabItem { Label("Today", systemImage: "sun.max.fill") }
                    .tag(AppModel.Tab.today)
                    .badge(app.tasks.open.count)
                StatsView()
                    .tabItem { Label("Trends", systemImage: "chart.xyaxis.line") }
                    .tag(AppModel.Tab.progress)
                CareView()
                    .tabItem { Label("Coach", systemImage: "waveform") }
                    .tag(AppModel.Tab.care)
                    .badge(app.me?.unreadMessages ?? 0)
            } else {
                TodayView()
                    .tabItem { Label("Today", systemImage: "sun.max.fill") }
                    .tag(AppModel.Tab.today)
                    .badge(app.tasks.open.count)
                ProgressTab()
                    .tabItem { Label("Progress", systemImage: "chart.line.uptrend.xyaxis") }
                    .tag(AppModel.Tab.progress)
                MeasureTab()
                    .tabItem { Label("Measure", systemImage: "figure.walk.motion") }
                    .tag(AppModel.Tab.measure)
                CareView()
                    .tabItem { Label("Care", systemImage: "bubble.left.and.bubble.right.fill") }
                    .tag(AppModel.Tab.care)
                    .badge(app.me?.unreadMessages ?? 0)
            }
        }
        // The paywall covers the personal screens when access has lapsed; the
        // hospital record (if there is one) is a switch away inside it.
        .fullScreenCover(isPresented: Binding(
            get: { app.isPersonal && app.paywall != nil && !(app.me?.needsConsent ?? false) },
            set: { if !$0 { app.paywall = nil } }
        )) {
            PaywallView(mode: .lapsed)
                .environment(app)
        }
        // The beta consent, for an account that has never accepted it or
        // met a new version: nothing else is usable until it is read.
        .fullScreenCover(isPresented: Binding(
            get: { app.me?.needsConsent ?? false },
            set: { _ in }
        )) {
            ConsentGate()
                .environment(app)
        }
        // The system's own Liquid Glass, and the only glass in this file: the
        // tab bar collapses to a pill on scroll down and comes back on scroll
        // up. iOS 26 only; below that the helper is a passthrough.
        .mpTabBarMinimizeOnScroll()
        // The selected tab is ink, like the current item in the site's nav
        // capsule: monochrome chrome, colour kept for content.
        .tint(MP.ink)
    }
}
