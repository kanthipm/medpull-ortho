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
                    Text("Monitoring signals for your care team — not a diagnosis.")
                        .font(.mp(12)).foregroundStyle(MP.faint).padding(.top, 6)
                }
                .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 24)
            }
            .refreshable { await app.refreshAll() }
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
                Text(greeting).title(26)
                if let me = app.me {
                    Text(me.patient.isRecovery
                         ? "Day \(me.patient.postopDay ?? 0) · \(me.patient.procedureDisplay)"
                         : "\(me.patient.hospital?.name ?? "Your hospital") · \(me.patient.daysEnrolled == 0 ? "joined today" : "member for \(me.patient.daysEnrolled) days")")
                        .font(.mp(13.5, weight: .medium)).foregroundStyle(MP.muted)
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
                    Text(me.patient.isRecovery ? "Your recovery" : "Your signals").eyebrow()
                    Spacer()
                    StatusPill(text: me.recovery.label, tone: tone)
                }
                Text(me.recovery.blurb).font(.mp(15, weight: .medium)).foregroundStyle(MP.ink).lineSpacing(2)
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
                    Text("Your portfolio").eyebrow()
                    Spacer()
                    Button("Details") { app.selectedTab = .health }
                        .font(.mp(13, weight: .semibold)).foregroundStyle(MP.brand)
                }
                .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 10)
                if app.portfolio.isEmpty {
                    EmptyRow(icon: "square.grid.2x2", title: "Nothing here yet",
                             detail: "Connect Apple Health or a wearable and your steps, sleep, heart and more fill in on their own.")
                } else {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                        ForEach(Array(app.portfolio.prefix(6))) { m in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(m.label).font(.mp(11, weight: .medium)).foregroundStyle(MP.muted)
                                    .lineLimit(1).minimumScaleFactor(0.8)
                                HStack(alignment: .firstTextBaseline, spacing: 3) {
                                    Text(m.latestText).font(.system(size: 18, weight: .semibold, design: .monospaced)).foregroundStyle(MP.ink)
                                    Text(m.unit).font(.mp(10.5)).foregroundStyle(MP.faint)
                                }
                                Text(Dates.shortDay(m.latest.date)).font(.mp(10.5)).foregroundStyle(MP.faint)
                            }
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(MP.soft))
                        }
                    }
                    .padding(.horizontal, 12).padding(.bottom, 12)
                }
            }
        }
    }

    private func stat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.mp(11, weight: .medium)).foregroundStyle(MP.muted)
            Text(value).font(.system(size: 17, weight: .semibold, design: .monospaced)).foregroundStyle(MP.ink)
        }
    }

    private var todayCard: some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("Today").eyebrow()
                    Spacer()
                    if !app.tasks.open.isEmpty {
                        Button("All tasks") { app.selectedTab = .tasks }
                            .font(.mp(13, weight: .semibold)).foregroundStyle(MP.brand)
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
                    Image(systemName: icon).font(.mp(18, weight: .semibold)).foregroundStyle(MP.brand)
                    Text(title).font(.mp(14.5, weight: .semibold)).foregroundStyle(MP.ink)
                    Text(subtitle).font(.mp(12.5)).foregroundStyle(MP.muted)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private var healthNudge: some View {
        Button { app.selectedTab = .health } label: {
            Card {
                HStack(spacing: 12) {
                    Image(systemName: "heart.fill").font(.mp(20)).foregroundStyle(MP.riskHigh)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Connect Apple Health").font(.mp(14.5, weight: .semibold)).foregroundStyle(MP.ink)
                        Text("One tap, and your steps, sleep and heart data build your portfolio on their own.")
                            .font(.mp(12.5)).foregroundStyle(MP.muted)
                    }
                    Spacer()
                    Image(systemName: "chevron.right").foregroundStyle(MP.faint)
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
            Image(systemName: icon).font(.mp(16, weight: .semibold)).foregroundStyle(MP.brand)
                .frame(width: 30, height: 30)
                .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(MP.brandTint))
            VStack(alignment: .leading, spacing: 2) {
                Text(task.title).font(.mp(15, weight: .semibold)).foregroundStyle(MP.ink)
                    .strikethrough(task.status == "done", color: MP.faint)
                HStack(spacing: 6) {
                    Text(task.kindLabel).font(.mp(12.5)).foregroundStyle(MP.muted)
                    if task.status == "done", let via = task.completedVia {
                        Text("· done by \(via)").font(.mp(12.5)).foregroundStyle(MP.muted)
                    } else if task.inSmsConversation {
                        Text("· in progress by text").font(.mp(12.5)).foregroundStyle(MP.riskMed)
                    } else if let due = task.dueAt {
                        Text("· due \(Dates.relative(due))").font(.mp(12.5)).foregroundStyle(MP.muted)
                    }
                }
            }
            Spacer()
            if task.isOpen {
                Image(systemName: "chevron.right").font(.mp(13, weight: .semibold)).foregroundStyle(MP.faint)
            } else {
                Image(systemName: task.status == "done" ? "checkmark.circle.fill" : "minus.circle")
                    .foregroundStyle(task.status == "done" ? MP.riskLow : MP.faint)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .contentShape(Rectangle())
    }
}
