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

struct MainTabs: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        @Bindable var app = app
        TabView(selection: $app.selectedTab) {
            if app.isPersonal {
                // A subscriber's space: their day, their readouts, their
                // plan, their coach. No care team, so no Messages tab — the
                // coach's thread (the morning brief lives there) opens from
                // Home. Health (devices and the raw portfolio) is reached
                // from Stats.
                PersonalHomeView()
                    .tabItem { Label("Today", systemImage: "sun.max.fill") }
                    .tag(AppModel.Tab.home)
                StatsView()
                    .tabItem { Label("Stats", systemImage: "chart.xyaxis.line") }
                    .tag(AppModel.Tab.stats)
                TasksView()
                    .tabItem { Label("Plan", systemImage: "checklist") }
                    .tag(AppModel.Tab.tasks)
                    .badge(app.tasks.open.count)
                VoiceView()
                    .tabItem { Label("Coach", systemImage: "waveform") }
                    .tag(AppModel.Tab.talk)
                HealthView()
                    .tabItem { Label("Devices", systemImage: "applewatch") }
                    .tag(AppModel.Tab.health)
            } else {
                HomeView()
                    .tabItem { Label("Home", systemImage: "house.fill") }
                    .tag(AppModel.Tab.home)
                TasksView()
                    .tabItem { Label("Tasks", systemImage: "checklist") }
                    .tag(AppModel.Tab.tasks)
                    .badge(app.tasks.open.count)
                VoiceView()
                    .tabItem { Label("Talk", systemImage: "waveform") }
                    .tag(AppModel.Tab.talk)
                MessagesView()
                    .tabItem { Label("Messages", systemImage: "bubble.left.and.bubble.right.fill") }
                    .tag(AppModel.Tab.messages)
                    .badge(app.me?.unreadMessages ?? 0)
                HealthView()
                    .tabItem { Label("Health", systemImage: "heart.fill") }
                    .tag(AppModel.Tab.health)
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
        // up, handing a whole bar's height back to the content. iOS 26 only;
        // below that the helper is a passthrough and the bar stays put — see
        // UI/Glass.swift for why the app does not fake it by hiding the bar.
        //
        // NO floating glass action bar belongs here. This view owns the tab
        // bar, which is already one blurred surface; a bar stacked on it would
        // be glass-on-glass. A screen's action bar goes in that screen, with
        // `.mpGlassActionBar { }`.
        .mpTabBarMinimizeOnScroll()
        // The selected tab is ink, like the current item in the site's nav
        // capsule: monochrome chrome, colour kept for content.
        .tint(MP.ink)
    }
}
