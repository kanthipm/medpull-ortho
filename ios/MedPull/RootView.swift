import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        switch app.phase {
        case .launching:
            ProgressView().screen()
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
    }
}
