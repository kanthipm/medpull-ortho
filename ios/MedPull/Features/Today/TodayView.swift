import SwiftUI

/// A hospital patient's day, in the order they ask about it: how am I doing
/// (the recovery hero), what do I do now (the plan, with its one primary
/// action), is a measurement due, and has my care team said anything. Each
/// row opens the tab that owns it; nothing here repeats a tab in miniature.
struct TodayView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var showProfile = false
    @State private var openTask: RecoveryTask?
    @State private var showHistory = false
    @State private var showDone = false
    @State private var quickDone = 0
    @State private var quickError: String?
    @State private var greetingGone = false

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        let part = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"
        return "\(part),\n\(app.me?.patient.firstName ?? "there")."
    }

    private var checkin: RecoveryTask? { app.tasks.open.first { $0.kind == "checkin" } }
    private var otherOpen: [RecoveryTask] { app.tasks.open.filter { $0.id != checkin?.id } }
    private var doneToday: [RecoveryTask] {
        app.tasks.recent.filter { t in
            guard let at = Dates.parse(t.completedAt) else { return false }
            return Calendar.current.isDateInToday(at)
        }
    }

    var body: some View {
        @Bindable var app = app
        NavigationStack {
            ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header.mpRise(0)
                    if let me = app.me { RecoveryHero(me: me) { app.selectedTab = .progress }.mpRise(1) }
                    planCard.mpRise(2).id("plan")
                    measureRow.mpRise(3).id("measure")
                    careRow.mpRise(4).id("care")
                    if let me = app.me, !me.wearables.appleHealth.connected, me.wearables.devices.isEmpty,
                       me.features.appleHealth {
                        connectRow.mpRise(5)
                    }
                    if let quickError { ErrorBanner(text: quickError) }
                    if let error = app.lastError { ErrorBanner(text: error) }
                    Text("Monitoring signals for your care team — not a diagnosis.")
                        .mpFont(.label).foregroundStyle(MP.muted).padding(.top, 2)
                }
                .padding(.horizontal, 18).padding(.top, 2).padding(.bottom, 28)
            }
            .refreshable { await app.refreshAll() }
            .mpHardScrollEdge()
            .ambientScreen()
            .navigationTitle("Today")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(greetingGone ? .visible : .hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text("Today")
                        .font(.mp(17, weight: .medium, relativeTo: .headline))
                        .dynamicTypeSize(...DynamicTypeSize.accessibility1)
                        .foregroundStyle(MP.ink)
                        .opacity(greetingGone ? 1 : 0)
                        .accessibilityHidden(!greetingGone)
                }
                BrandLockupItem(hidden: greetingGone)
                AvatarItem(initials: app.me?.patient.initials ?? "··") { showProfile = true }
            }
            .animation(MPMotion.gated(MPMotion.state, reduceMotion: reduceMotion), value: greetingGone)
            .sheet(isPresented: $showProfile) { ProfileView() }
            .sheet(isPresented: $app.showConnections) { ConnectionsView() }
            .navigationDestination(item: $openTask) { task in TaskDestination(task: task) }
            .navigationDestination(isPresented: $showHistory) { TaskHistoryView() }
            .onChange(of: app.pendingTaskId, initial: true) { _, id in openPending(id) }
            .onChange(of: app.tasks) { _, _ in openPending(app.pendingTaskId) }
            .mpCompletionFeedback(count: quickDone)
            .mpErrorFeedback(quickError)
            .task {
                #if DEBUG
                if let target = AppConfig.debugFlag("MP_SCROLL") {
                    try? await Task.sleep(for: .seconds(2))
                    proxy.scrollTo(target, anchor: .top)
                }
                if AppConfig.debugFlag("MP_SHOW") == "profile" { showProfile = true }
                if AppConfig.debugFlag("MP_SHOW") == "history" { showHistory = true }
                if AppConfig.debugFlag("MP_SHOW") == "checkin", let c = checkin { openTask = c }
                #endif
            }
            }
        }
    }

    private func openPending(_ id: Int?) {
        guard let id, let task = (app.tasks.open + app.tasks.recent).first(where: { $0.id == id }) else { return }
        app.pendingTaskId = nil
        openTask = task
    }

    // MARK: Greeting

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(greeting)
                .title(MPSize.displayM)
                .accessibilityAddTraits(.isHeader)
            if let me = app.me {
                Text(me.patient.isRecovery
                     ? "Day \(me.patient.postopDay ?? 0)\(MP.dot)\(me.patient.procedureDisplay)"
                     : "\(me.patient.hospital?.name ?? "Your hospital")\(MP.dot)\(me.patient.daysEnrolled == 0 ? "joined today" : "\(me.patient.daysEnrolled) days in")")
                    .mpFont(.copyLarge).foregroundStyle(MP.body)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 6)
        .onGeometryChange(for: Bool.self) { proxy in
            proxy.frame(in: .scrollView).maxY < 8
        } action: { gone in
            if gone != greetingGone { greetingGone = gone }
        }
    }

    // MARK: Plan

    /// Today's plan: the check-in as the one primary action, every other
    /// open task as a row, what is already done folded away underneath.
    private var planCard: some View {
        let open = app.tasks.open
        let done = doneToday
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardTitleRow("Today’s plan",
                             note: open.isEmpty && done.isEmpty ? nil
                                : "\(done.count) of \(open.count + done.count) done",
                             actionTitle: "All tasks") { showHistory = true }
                if open.isEmpty {
                    EmptyRow(icon: "checkmark", title: done.isEmpty ? "Nothing waiting" : "All done for today",
                             detail: done.isEmpty ? "New tasks from your care team show up here."
                                : "Your care team will see what you did with their next review.")
                        .padding(.bottom, 4)
                } else {
                    if let checkin {
                        VStack(alignment: .leading, spacing: 8) {
                            PrimaryButton(title: "Start today’s check-in", icon: "text.bubble.fill") {
                                openTask = checkin
                            }
                            Text(checkin.inSmsConversation
                                 ? "You started this by text. Finishing it here is fine."
                                 : "About two minutes. Every question can be skipped.")
                                .mpFont(.label).foregroundStyle(MP.muted)
                                .padding(.horizontal, 4)
                        }
                        .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, otherOpen.isEmpty ? 16 : 12)
                    }
                    if !otherOpen.isEmpty {
                        if checkin != nil { InsetDivider(leading: 16) }
                        ForEach(otherOpen) { t in
                            Button { openTask = t } label: { PlanRow(task: t) }
                                .buttonStyle(.mpRow)
                                .contextMenu {
                                    Button { openTask = t } label: { Label("Open", systemImage: "arrow.up.forward.app") }
                                    if t.questions.isEmpty && t.kind != "checkin" {
                                        Button { markDone(t) } label: { Label("Mark done", systemImage: "checkmark.circle") }
                                    }
                                }
                            if t.id != otherOpen.last?.id { RowDivider() }
                        }
                    }
                }
                if !done.isEmpty {
                    InsetDivider(leading: 16)
                    Button {
                        withAnimation(MPMotion.gated(MPMotion.layout, reduceMotion: reduceMotion)) { showDone.toggle() }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "checkmark.circle.fill").foregroundStyle(MP.riskLow)
                            Text("Done today").foregroundStyle(MP.ink)
                            Text("\(done.count)").foregroundStyle(MP.muted)
                            Spacer()
                            Image(systemName: "chevron.down")
                                .font(.systemGlyphs(12, weight: .semibold))
                                .foregroundStyle(MP.muted)
                                .rotationEffect(.degrees(showDone ? 180 : 0))
                        }
                        .mpFont(.copyMedium)
                        .padding(.horizontal, 16).padding(.vertical, 12)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.mpRow)
                    .accessibilityHint(showDone ? "Collapse" : "Expand")
                    if showDone {
                        ForEach(done) { t in
                            RowDivider()
                            PlanRow(task: t)
                        }
                    }
                }
            }
            .padding(.bottom, done.isEmpty ? 4 : 0)
            .clipShape(MP.surfaceShape)
        }
    }

    private func markDone(_ t: RecoveryTask) {
        quickError = nil
        Task {
            do {
                try await app.complete(t, answers: [:])
                quickDone += 1
            } catch {
                quickError = AppModel.message(for: error)
            }
        }
    }

    // MARK: Measure

    /// The one line about MedPull's own measurements: what is due, or when
    /// the next one is. Opens the Measure tab.
    private var measureRow: some View {
        let statuses = MeasureFlow.allCases.map { MeasureStatus.status(for: $0, in: app.portfolio) }
        let due = statuses.filter(\.isDue)
        let subtitle: String = {
            if let first = due.first {
                let names = due.map { $0.flow.title.lowercased() }
                let list = names.count == 1 ? names[0]
                    : names.dropLast().joined(separator: ", ") + " and " + names.last!
                return first.lastDate == nil && due.count == statuses.count
                    ? "Three short tests with your phone. Start with a guided walk."
                    : "\(list.prefix(1).uppercased() + list.dropFirst()) \(due.count == 1 ? "is" : "are") due."
            }
            let next = statuses.min { ($0.cadenceDays - ($0.daysSince ?? 0)) < ($1.cadenceDays - ($1.daysSince ?? 0)) }
            return "All caught up. \(next.map { "\($0.flow.title) \($0.dueLabel.lowercased())." } ?? "")"
        }()
        return Button { app.selectedTab = .measure } label: {
            Card(padding: 0) {
                ListRow("Measure", subtitle: subtitle, symbol: "figure.walk.motion", family: .teal) {
                    if !due.isEmpty { StateLabel(text: "Due", tone: .med) }
                }
            }
        }
        .buttonStyle(CardTapStyle())
    }

    // MARK: Care

    private var careRow: some View {
        let unread = app.me?.unreadMessages ?? 0
        let team = app.me?.patient.careTeam ?? []
        let last = app.messages.last { $0.sender != "patient" }
        let subtitle: String = {
            if let last, !last.text.isEmpty { return last.text }
            if !team.isEmpty { return team.map(\.name).joined(separator: ", ") }
            return "Write to your care team, or tell MedPull how you feel."
        }()
        return Button { app.selectedTab = .care } label: {
            Card(padding: 0) {
                HStack(spacing: 12) {
                    TeamAvatars(team: team)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Care team").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text(subtitle).mpFont(.label).foregroundStyle(MP.muted).lineLimit(2)
                            .multilineTextAlignment(.leading)
                    }
                    Spacer(minLength: 8)
                    if unread > 0 {
                        Text("\(unread)")
                            .font(.figuresLabel).foregroundStyle(MP.onAction)
                            .padding(.horizontal, 8).padding(.vertical, 3)
                            .background(MP.capsuleShape.fill(MP.action))
                            .accessibilityLabel("\(unread) unread")
                    }
                    Image(systemName: "chevron.right")
                        .font(.systemGlyphs(13, weight: .semibold))
                        .foregroundStyle(MP.faint)
                        .accessibilityHidden(true)
                }
                .padding(.horizontal, 16).padding(.vertical, 12)
            }
        }
        .buttonStyle(CardTapStyle())
    }

    private var connectRow: some View {
        Button { app.showConnections = true } label: {
            Card(padding: 0) {
                ListRow("Connect Apple Health",
                        subtitle: "Steps, sleep and heart data fill in on their own.",
                        symbol: "heart.fill", family: .violet)
            }
        }
        .buttonStyle(CardTapStyle())
    }
}

// MARK: - Hero

/// The recovery tile: the one gradient on the screen. The typical curve
/// dashed, the patient's own in white, the headline figure (how they sit
/// against expected, or the post-op day), and the care team's sentence on
/// the solid-glass caption.
struct RecoveryHero: View {
    let me: Me
    var action: () -> Void

    var body: some View {
        let tone = MP.tone(for: me.recovery.level)
        let traj = me.recovery.trajectory
        let pct = traj.state != "unknown" ? traj.pct : nil
        let recovery = me.patient.isRecovery
        let value: String = {
            if let pct { return (pct >= 0 ? "+" : "\u{2212}") + String(format: "%.0f%%", abs(pct)) }
            if let day = me.patient.postopDay, recovery { return "Day \(day)" }
            return "\(me.recovery.daysWithData ?? 0)"
        }()
        let unit: String = pct != nil ? (recovery ? "vs expected" : "vs your baseline")
            : (recovery && me.patient.postopDay != nil ? "of recovery" : "days of data")
        let side: (String, String)? = {
            if pct != nil, recovery, let day = me.patient.postopDay { return ("Day \(day)", "of recovery") }
            if let days = me.recovery.daysWithData, pct != nil { return ("\(days)", "days of data") }
            return nil
        }()
        Button(action: action) {
            GradientTile(.sage, kicker: recovery ? "Your recovery" : "Your signals",
                         value: value, unit: unit, side: side) {
                RecoveryCurveArt(pct: pct).padding(.top, 4)
            } caption: {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        StatusPill(text: me.recovery.label, tone: tone)
                        Spacer()
                        HStack(spacing: 4) {
                            Text("Progress").mpFont(.labelMedium)
                            Image(systemName: "chevron.right").font(.systemGlyphs(11, weight: .semibold))
                        }
                        .foregroundStyle(MP.brandInk)
                    }
                    Text(me.recovery.blurb.typeset)
                        .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .multilineTextAlignment(.leading)
                }
            }
        }
        .buttonStyle(CardTapStyle())
        .accessibilityElement(children: .contain)
    }
}

// MARK: - Plan row

/// One task as a row: a category glyph, the title, one meta line, and a
/// chevron (open) or the state glyph (done / skipped).
struct PlanRow: View {
    let task: RecoveryTask
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var isDone: Bool { task.status == "done" }

    static func symbol(for kind: String) -> String {
        switch kind {
        case "checkin": return "text.bubble.fill"
        case "exercise": return "figure.strengthtraining.functional"
        case "walk": return "figure.walk"
        case "medication": return "pills.fill"
        case "wound_check": return "bandage.fill"
        case "sleep": return "bed.double.fill"
        default: return "checklist"
        }
    }

    static func family(for kind: String) -> MP.Category {
        switch kind {
        case "exercise", "walk": return .teal
        case "medication", "wound_check": return .violet
        case "sleep": return .indigo
        default: return .blue
        }
    }

    /// The state after the kind, or nil. The words carry the state.
    private var status: (String, Color)? {
        if isDone, let via = task.completedVia { return ("done by \(via)", MP.muted) }
        if task.inSmsConversation { return ("in progress by text", MP.riskMed) }
        if let due = task.dueAt { return ("due \(Dates.relative(due))", MP.muted) }
        if let schedule = task.scheduleLabel { return (schedule, MP.muted) }
        return nil
    }

    private var meta: Text {
        let kind = Text(task.kindLabel).foregroundStyle(MP.muted)
        if let status {
            return Text("\(kind)\(Text(MP.dot).foregroundStyle(MP.muted))\(Text(status.0).foregroundStyle(status.1))")
        }
        return kind
    }

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Glyph(systemName: Self.symbol(for: task.kind), family: Self.family(for: task.kind))
            VStack(alignment: .leading, spacing: 2) {
                Text(task.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    .strikethrough(isDone, color: MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
                meta.mpFont(.label)
                    .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 2)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
            }
            Spacer(minLength: 8)
            if task.isOpen {
                Image(systemName: "chevron.right")
                    .font(.systemGlyphs(13, weight: .semibold))
                    .foregroundStyle(MP.faint)
                    .accessibilityHidden(true)
            } else {
                Image(systemName: isDone ? "checkmark.circle.fill" : "minus.circle")
                    .font(.copyLarge)
                    .foregroundStyle(isDone ? MP.riskLow : MP.muted)
                    .accessibilityHidden(true)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 11)
        .frame(minHeight: 52)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityValue(Text(isDone ? "Done" : task.isOpen ? "" : "Skipped"))
    }
}

// MARK: - Toolbar pieces (Today and the personal Today share them)

/// The MedPull lockup on the leading edge of the bar: the mark on its white
/// tile, then the wordmark in ink. Hidden once the greeting has scrolled off.
struct BrandLockupItem: ToolbarContent {
    let hidden: Bool
    var badge: String? = nil

    var body: some ToolbarContent {
        if #available(iOS 26, *) {
            ToolbarItem(placement: .topBarLeading) { lockup }
                .sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: .topBarLeading) { lockup }
        }
    }

    private var lockup: some View {
        HStack(spacing: 9) {
            Image("MedPullMark")
                .resizable().scaledToFit()
                .frame(width: 21, height: 21)
                .frame(width: 30, height: 30)
                .background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(.white)
                    .shadow(color: .black.opacity(0.08), radius: 1, y: 1))
                .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .strokeBorder(Color.black.opacity(0.08), lineWidth: 0.5))
            HStack(spacing: 6) {
                Text("MedPull")
                    .font(.mp(19, weight: .medium, relativeTo: .headline))
                    .kerning(-0.5)
                    .foregroundStyle(MP.ink)
                if let badge {
                    Text(badge)
                        .mpFont(.labelMedium)
                        .foregroundStyle(MP.brandInk)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(MP.capsuleShape.fill(MP.brandTint))
                }
            }
            .dynamicTypeSize(...DynamicTypeSize.accessibility1)
            .fixedSize()
        }
        .opacity(hidden ? 0 : 1)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(badge.map { "MedPull \($0)" } ?? "MedPull")
        .accessibilityHidden(hidden)
    }
}

/// The avatar on the trailing edge of the bar; opens Profile.
struct AvatarItem: ToolbarContent {
    let initials: String
    var action: () -> Void

    var body: some ToolbarContent {
        if #available(iOS 26, *) {
            ToolbarItem(placement: .topBarTrailing) { button }
                .sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: .topBarTrailing) { button }
        }
    }

    private var button: some View {
        Button(action: action) {
            Initials(text: initials, size: 36)
                .frame(width: 44, height: 44)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Profile")
    }
}

/// The care team as overlapping soft discs.
struct TeamAvatars: View {
    let team: [CareTeamMember]

    var body: some View {
        if team.isEmpty {
            Glyph(systemName: "bubble.left.and.bubble.right.fill", family: .blue, size: 36)
        } else {
            HStack(spacing: -10) {
                ForEach(Array(team.prefix(3).enumerated()), id: \.offset) { _, member in
                    Initials(text: Self.initials(member.name), size: 34, style: .soft)
                        .padding(2)
                        .background(Circle().fill(MP.panel))
                }
            }
            .accessibilityHidden(true)
        }
    }

    static func initials(_ name: String) -> String {
        // "Dr. Priya Shah" -> "PS": honorifics end in a period.
        let words = name.split(separator: " ").filter { !$0.hasSuffix(".") }
        let letters = [words.first, words.count > 1 ? words.last : nil].compactMap { $0?.first }
        return String(letters).uppercased()
    }
}
