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
    }
}
