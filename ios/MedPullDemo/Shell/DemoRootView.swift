import SwiftUI

/// The demo app's root. `AppModel.phase` means the same as in the real app,
/// except that "onboarding" here is the picker: with nobody signed in the
/// only thing to do is choose who to be.
struct DemoRootView: View {
    @Environment(AppModel.self) private var app
    @Environment(DemoShell.self) private var shell

    var body: some View {
        @Bindable var shell = shell
        Group {
            switch app.phase {
            case .launching:
                LaunchOrbitView(sport: app.launchSport)
            case .onboarding:
                PersonaPicker()
            case .home:
                // Keyed by the person: becoming someone else rebuilds every
                // tab, so nothing one person opened, typed or loaded is
                // still on screen for the next.
                DemoTabs().id(app.me?.patient.id ?? "")
            }
        }
        .overlay(alignment: .top) {
            if shell.openingLink { OpeningLinkBadge().padding(.top, 6) }
        }
        .animation(MPMotion.state, value: shell.openingLink)
        .sheet(item: $shell.linkFailure) { failure in LinkFailureSheet(failure: failure) }
    }
}

/// The tabs of each version, as the real app's RootView composes them, with
/// the Calendar a clinic person gets here and without the two covers the
/// demo never needs: no demo person is asked to pay or to sign the consent
/// (every persona has it on file).
struct DemoTabs: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        @Bindable var app = app
        Group {
            if app.me == nil && app.lastError == nil {
                // The account kind decides which tabs mount, so the loading
                // screen stays until /me has answered or failed.
                LaunchOrbitView(sport: app.launchSport, caption: "Reading your signals")
            } else {
                TabView(selection: $app.selectedTab) {
                    if app.isSports {
                        SportsHomeView()
                            .tabItem { Label("Today", systemImage: "sun.max.fill") }
                            .tag(AppModel.Tab.today)
                            .badge(app.tasks.open.count)
                        PerformanceView()
                            .tabItem { Label("Stats", systemImage: "chart.bar.xaxis") }
                            .tag(AppModel.Tab.progress)
                        RecoveryView()
                            .tabItem { Label("Recovery", systemImage: "bed.double.fill") }
                            .tag(AppModel.Tab.recovery)
                        RehabView()
                            .tabItem { Label("Injury", systemImage: "cross.case.fill") }
                            .tag(AppModel.Tab.rehab)
                        CareView()
                            .tabItem { Label("Coach", systemImage: "waveform") }
                            .tag(AppModel.Tab.care)
                            .badge(app.me?.unreadMessages ?? 0)
                    } else if app.isPersonal {
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
                        CalendarTab()
                            .tabItem { Label("Calendar", systemImage: "calendar") }
                            .tag(AppModel.Tab.calendar)
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
                .mpTabBarMinimizeOnScroll()
            }
        }
        // The selected tab is ink, as in the real app.
        .tint(MP.ink)
    }
}

/// Shown at the top of the screen while a texted link is being exchanged
/// for a session: the app may be about to become someone else.
private struct OpeningLinkBadge: View {
    var body: some View {
        HStack(spacing: 8) {
            ProgressView().controlSize(.small).tint(MP.brand)
            Text("Opening your link").mpFont(.copyMedium).foregroundStyle(MP.ink)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .glassSurface(MP.capsuleShape, solid: true)
        .transition(.move(edge: .top).combined(with: .opacity))
        .accessibilityElement(children: .combine)
    }
}

/// A link that did not open, and why, in the server's own sentence.
struct LinkFailureSheet: View {
    let failure: DemoShell.LinkFailure
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            IconTile("link", family: .violet, size: 44)
            Text(failure.title)
                .title(MPSize.displayS)
                .accessibilityAddTraits(.isHeader)
            Text(failure.message)
                .mpFont(.copyLarge).foregroundStyle(MP.body).lineSpacing(2)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            PrimaryButton(title: "OK") { dismiss() }
        }
        .padding(.horizontal, 22)
        .padding(.top, 28)
        .padding(.bottom, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .screen()
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }
}
