import SwiftUI

struct HomeView: View {
    @Environment(AppModel.self) private var app
    @State private var showProfile = false
    @State private var openTask: RecoveryTask?

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        let part = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"
        return "\(part), \(app.me?.patient.firstName ?? "there")."
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    header
                    if let me = app.me { recoveryCard(me) }
                    portfolioCard
                    todayCard
                    quickRow
                    if let me = app.me, !me.wearables.appleHealth.connected, me.features.appleHealth {
                        healthNudge
                    }
                    if let error = app.lastError { ErrorBanner(text: error) }
                    // Legal copy, so it is TEXT and `faint` is out: 2.41:1 on
                    // canvas in light. `muted` is 5.03:1 light / 5.24:1 dark.
                    Text("Monitoring signals for your care team — not a diagnosis.")
                        .font(.label).foregroundStyle(MP.muted).padding(.top, 6)
                }
                .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 24)
            }
            .refreshable { await app.refreshAll() }
            // The minimizing glass tab bar sits over this list; clinical
            // numbers stop at a hard edge instead of fading under it.
            .mpHardScrollEdge()
            .screen()
            .toolbar(.hidden, for: .navigationBar)
            .sheet(isPresented: $showProfile) { ProfileView() }
            .navigationDestination(item: $openTask) { task in TaskDetailView(task: task) }
        }
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text("MedPull Recovery").eyebrow()
                Text(greeting).title(MPSize.displayS)
                if let me = app.me {
                    Text(me.patient.isRecovery
                         ? "Day \(me.patient.postopDay ?? 0)\(MP.dot)\(me.patient.procedureDisplay)"
                         : "\(me.patient.hospital?.name ?? "Your hospital")\(MP.dot)\(me.patient.daysEnrolled == 0 ? "joined today" : "member for \(me.patient.daysEnrolled) days")")
                        .font(.copyMedium).foregroundStyle(MP.muted)
                }
            }
            Spacer()
            Button { showProfile = true } label: {
                Initials(text: app.me?.patient.initials ?? "··", size: 40,
                         tone: MP.tone(for: app.me?.recovery.level ?? ""))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Profile")
        }
        .padding(.top, 10)
    }

    private func recoveryCard(_ me: Me) -> some View {
        let tone = MP.tone(for: me.recovery.level)
        return Card(tint: true) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(me.patient.isRecovery ? "Your recovery" : "Your signals")
                        .font(.labelMedium).foregroundStyle(MP.muted)
                    Spacer()
                    StatusPill(text: me.recovery.label, tone: tone)
                }
                Text(me.recovery.blurb).font(.copyLargeMedium).foregroundStyle(MP.ink).lineSpacing(2)
                HStack(spacing: 18) {
                    if let day = me.patient.postopDay, me.patient.isRecovery {
                        stat("Post-op day", "D\(day)")
                    } else {
                        stat("Sources", "\(sourceCount(me))")
                    }
                    if let pct = me.recovery.trajectory.pct, me.recovery.trajectory.state != "unknown" {
                        stat(me.patient.isRecovery ? "Vs. expected" : "Vs. baseline",
                             String(format: "%@%.0f%%", pct >= 0 ? "+" : "", pct))
                    }
                    if let days = me.recovery.daysWithData {
                        stat("Days of data", "\(days)")
                    }
                }
                .padding(.top, 2)
            }
        }
    }

    private func sourceCount(_ me: Me) -> Int {
        (me.wearables.appleHealth.connected ? 1 : 0) + me.wearables.devices.count
    }

    private var portfolioCard: some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("Your portfolio").font(.labelMedium).foregroundStyle(MP.muted)
                    Spacer()
                    Button("Details") { app.selectedTab = .health }
                        .font(.copyMedium).foregroundStyle(MP.brandInk)
                }
                .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 10)
                if app.portfolio.isEmpty {
                    EmptyRow(icon: "square.grid.2x2", title: "Nothing here yet",
                             detail: "Connect Apple Health or a wearable and your steps, sleep, heart and more fill in on their own.")
                } else {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                        ForEach(Array(app.portfolio.prefix(6))) { m in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(m.label).font(.labelMedium).foregroundStyle(MP.muted)
                                    .lineLimit(1).minimumScaleFactor(0.8)
                                HStack(alignment: .firstTextBaseline, spacing: 3) {
                                    Text(m.latestText).font(.monoLede).foregroundStyle(MP.ink)
                                    Text(m.unit).font(.label).foregroundStyle(MP.muted)
                                }
                                Text(Dates.shortDay(m.latest.date)).font(.label).foregroundStyle(MP.muted)
                            }
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(MP.controlShape.fill(MP.soft))
                        }
                    }
                    .padding(.horizontal, 12).padding(.bottom, 12)
                }
            }
        }
    }

    private func stat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.labelMedium).foregroundStyle(MP.muted)
            Text(value).font(.monoCopyLarge).foregroundStyle(MP.ink)
        }
    }

    private var todayCard: some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("Today").font(.labelMedium).foregroundStyle(MP.muted)
                    Spacer()
                    if !app.tasks.open.isEmpty {
                        Button("All tasks") { app.selectedTab = .tasks }
                            .font(.copyMedium).foregroundStyle(MP.brandInk)
                    }
                }
                .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 6)
                if app.tasks.open.isEmpty {
                    EmptyRow(icon: "checkmark.circle", title: "All caught up",
                             detail: "New tasks arrive by text and show up here.")
                } else {
                    ForEach(Array(app.tasks.open.prefix(3))) { t in
                        Button { openTask = t } label: { TaskRow(task: t) }
                            .buttonStyle(.plain)
                        if t.id != app.tasks.open.prefix(3).last?.id { Divider().overlay(MP.line).padding(.leading, 56) }
                    }
                }
            }
        }
    }

    private var quickRow: some View {
        HStack(spacing: 10) {
            quick("Talk to MedPull", "waveform", subtitle: "Log pain or a task by voice") { app.selectedTab = .talk }
            quick("Care team", "bubble.left.and.bubble.right.fill",
                  subtitle: (app.me?.unreadMessages ?? 0) > 0 ? "\(app.me!.unreadMessages) new" : "Send a message") {
                app.selectedTab = .messages
            }
        }
    }

    private func quick(_ title: String, _ icon: String, subtitle: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Card(padding: 14) {
                VStack(alignment: .leading, spacing: 8) {
                    Image(systemName: icon).font(.ledeMedium).foregroundStyle(MP.brandInk)
                    Text(title).font(.copyMedium).foregroundStyle(MP.ink)
                    Text(subtitle).font(.label).foregroundStyle(MP.muted)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private var healthNudge: some View {
        Button { app.selectedTab = .health } label: {
            Card {
                HStack(spacing: 12) {
                    Image(systemName: "heart.fill").font(.subhead).foregroundStyle(MP.riskHigh)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Connect Apple Health").font(.copyMedium).foregroundStyle(MP.ink)
                        Text("One tap, and your steps, sleep and heart data build your portfolio on their own.")
                            .font(.label).foregroundStyle(MP.muted)
                    }
                    Spacer()
                    Image(systemName: "chevron.right").font(.copyMedium).foregroundStyle(MP.muted)
                }
            }
        }
        .buttonStyle(.plain)
    }
}

struct TaskRow: View {
    let task: RecoveryTask

    private var icon: String {
        switch task.kind {
        case "checkin": return "text.bubble.fill"
        case "exercise": return "figure.strengthtraining.functional"
        case "walk": return "figure.walk"
        case "medication": return "pills.fill"
        case "wound_check": return "bandage.fill"
        default: return "checklist"
        }
    }

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: icon).font(.copyLargeMedium).foregroundStyle(MP.brandInk)
                .frame(width: 30, height: 30)
                .background(MP.controlShape.fill(MP.brandTint))
            VStack(alignment: .leading, spacing: 2) {
                Text(task.title).font(.copyLargeMedium).foregroundStyle(MP.ink)
                    .strikethrough(task.status == "done", color: MP.muted)
                HStack(spacing: 6) {
                    Text(task.kindLabel).font(.label).foregroundStyle(MP.muted)
                    if task.status == "done", let via = task.completedVia {
                        Text("\(MP.dotLead)done by \(via)").font(.label).foregroundStyle(MP.muted)
                    } else if task.inSmsConversation {
                        Text("\(MP.dotLead)in progress by text").font(.label).foregroundStyle(MP.riskMed)
                    } else if let due = task.dueAt {
                        Text("\(MP.dotLead)due \(Dates.relative(due))").font(.label).foregroundStyle(MP.muted)
                    }
                }
            }
            Spacer()
            if task.isOpen {
                Image(systemName: "chevron.right").font(.copyMedium).foregroundStyle(MP.muted)
            } else {
                Image(systemName: task.status == "done" ? "checkmark.circle.fill" : "minus.circle")
                    .font(.copyLarge)
                    .foregroundStyle(task.status == "done" ? MP.riskLow : MP.muted)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .contentShape(Rectangle())
    }
}
