import SwiftUI

struct HomeView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var showProfile = false
    @State private var openTask: RecoveryTask?
    /// True once the two-line greeting has scrolled under the bar. Until
    /// then the bar has no background and no title (R6); after, the bar
    /// material (or the iOS 26 hard edge) comes in with an inline "Home".
    @State private var greetingGone = false

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        let part = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"
        // Always two lines, broken after the comma (R6): "Good afternoon," /
        // "Marcus.". A literal newline, so no width ever joins them.
        return "\(part),\n\(app.me?.patient.firstName ?? "there")."
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header.mpRise(0)
                    if let me = app.me { recoveryCard(me).mpRise(1) }
                    portfolioCard.mpRise(2)
                    todayCard.mpRise(3)
                    quickRow.mpRise(4)
                    if let me = app.me, !me.wearables.appleHealth.connected, me.features.appleHealth {
                        healthNudge
                    }
                    if let error = app.lastError { ErrorBanner(text: error) }
                    // Legal copy, so it is TEXT and `faint` is out. `muted` is
                    // 5.025:1 light / 5.243:1 dark on canvas.
                    Text("Monitoring signals for your care team — not a diagnosis.")
                        .mpFont(.label).foregroundStyle(MP.muted).padding(.top, 4)
                }
                .padding(.horizontal, 18).padding(.top, 2).padding(.bottom, 28)
            }
            .refreshable { await app.refreshAll() }
            // The minimizing glass tab bar sits over this list; clinical
            // numbers stop at a hard edge instead of fading under it (R13).
            .mpHardScrollEdge()
            .ambientScreen()
            // The title exists for the back button ("Home") and VoiceOver; the
            // principal item below decides when it is drawn.
            .navigationTitle("Home")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(greetingGone ? .visible : .hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text("Home")
                        .font(.mp(17, weight: .medium, relativeTo: .headline))
                        .dynamicTypeSize(...DynamicTypeSize.accessibility1)
                        .foregroundStyle(MP.ink)
                        .opacity(greetingGone ? 1 : 0)
                        .accessibilityHidden(!greetingGone)
                }
                brandItem
                avatarItem
            }
            .animation(MPMotion.gated(MPMotion.state, reduceMotion: reduceMotion), value: greetingGone)
            .sheet(isPresented: $showProfile) { ProfileView() }
            // Same router as Tasks, so a check-in opens CheckinView from either tab.
            .navigationDestination(item: $openTask) { task in TaskDestination(task: task) }
        }
    }

    // MARK: Toolbar avatar

    @ToolbarContentBuilder private var avatarItem: some ToolbarContent {
        if #available(iOS 26, *) {
            // The brand disc is its own shape; glass around it would box it.
            ToolbarItem(placement: .topBarTrailing) { avatarButton }
                .sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: .topBarTrailing) { avatarButton }
        }
    }

    /// The MedPull lockup on the leading side of the same row as the avatar,
    /// so the bar reads as one row (mark, wordmark ... avatar): the site's
    /// white app-icon tile with the mark, then the wordmark in `ink`.
    @ToolbarContentBuilder private var brandItem: some ToolbarContent {
        if #available(iOS 26, *) {
            ToolbarItem(placement: .topBarLeading) { brandLockup }
                .sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: .topBarLeading) { brandLockup }
        }
    }

    private var brandLockup: some View {
        HStack(spacing: 9) {
            // The site's app-icon tile: the mark on white.
            Image("MedPullMark")
                .resizable()
                .scaledToFit()
                .frame(width: 21, height: 21)
                .frame(width: 30, height: 30)
                .background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(.white)
                    .shadow(color: .black.opacity(0.08), radius: 1, y: 1))
                .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .strokeBorder(Color.black.opacity(0.08), lineWidth: 0.5))
            Text("MedPull")
                .font(.mp(19, weight: .medium, relativeTo: .headline))
                .kerning(-0.5)
                .dynamicTypeSize(...DynamicTypeSize.accessibility1)
                .foregroundStyle(MP.ink)
                .fixedSize()
        }
        // The principal "Home" takes over once the greeting is gone; the
        // wordmark steps aside so the two never crowd each other.
        .opacity(greetingGone ? 0 : 1)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("MedPull")
        .accessibilityHidden(greetingGone)
    }

    private var avatarButton: some View {
        Button { showProfile = true } label: {
            // The gradient avatar; `.high` is the clay disc.
            Initials(text: app.me?.patient.initials ?? "··", size: 36,
                     tone: avatarTone)
                .frame(width: 44, height: 44)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Profile")
    }

    private var avatarTone: MP.Tone {
        let tone = MP.tone(for: app.me?.recovery.level ?? "")
        return tone == .high ? .high : .brand
    }

    // MARK: Greeting

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            // The site's display type: large and light, two lines (R6).
            Text(greeting)
                .title(MPSize.displayM)
                .accessibilityAddTraits(.isHeader)
            if let me = app.me {
                // `body` on the fog: 5.0 or better at its strongest point.
                Text(me.patient.isRecovery
                     ? "Day \(me.patient.postopDay ?? 0)\(MP.dot)\(me.patient.procedureDisplay)"
                     : "\(me.patient.hospital?.name ?? "Your hospital")\(MP.dot)\(me.patient.daysEnrolled == 0 ? "joined today" : "member for \(me.patient.daysEnrolled) days")")
                    .mpFont(.copyLarge).foregroundStyle(MP.body)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 6)
        .padding(.bottom, 6)
        .onGeometryChange(for: Bool.self) { proxy in
            // Gone once its last line is behind the (transparent) bar.
            proxy.frame(in: .scrollView).maxY < 8
        } action: { gone in
            if gone != greetingGone { greetingGone = gone }
        }
    }

    // MARK: Recovery

    /// The recovery tile: the site's sage gradient with the patient's
    /// trajectory drawn as white line art, the big light number, and the
    /// summary on a solid-glass caption with the state pill and the stats.
    private func recoveryCard(_ me: Me) -> some View {
        let tone = MP.tone(for: me.recovery.level)
        let traj = me.recovery.trajectory
        let pct = traj.state != "unknown" ? traj.pct : nil
        let recovery = me.patient.isRecovery
        let value: String = {
            if let pct { return (pct >= 0 ? "+" : "\u{2212}") + String(format: "%.0f%%", abs(pct)) }
            if let day = me.patient.postopDay, recovery { return "D\(day)" }
            return "\(me.recovery.daysWithData ?? 0)"
        }()
        let unitLabel: String = pct != nil ? (recovery ? "vs expected" : "vs baseline")
            : (recovery && me.patient.postopDay != nil ? "post-op day" : "days of data")
        return GradientTile(.sage,
                            kicker: recovery ? "Your recovery" : "Your signals",
                            value: value, unit: unitLabel,
                            side: recovery ? me.patient.postopDay.map { ("Day \($0)", "since surgery") } : nil) {
            RecoveryCurveArt(pct: pct)
                .padding(.top, 6)
        } caption: {
            VStack(alignment: .leading, spacing: 10) {
                StatusPill(text: me.recovery.label, tone: tone)
                Text(me.recovery.blurb)
                    .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 22) { stats(me) }
                    VStack(alignment: .leading, spacing: 10) { stats(me) }
                }
                .padding(.top, 2)
            }
        }
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder private func stats(_ me: Me) -> some View {
        if let day = me.patient.postopDay, me.patient.isRecovery {
            stat("Post-op day", "D\(day)", value: Double(day))
        } else {
            let n = sourceCount(me)
            stat("Sources", "\(n)", value: Double(n))
        }
        if let pct = me.recovery.trajectory.pct, me.recovery.trajectory.state != "unknown" {
            stat(me.patient.isRecovery ? "Vs. expected" : "Vs. baseline",
                 (pct >= 0 ? "+" : "\u{2212}") + String(format: "%.0f%%", abs(pct)),
                 value: pct)
        }
        if let days = me.recovery.daysWithData {
            stat("Days of data", "\(days)", value: Double(days))
        }
    }

    private func stat(_ label: String, _ text: String, value: Double) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(label).mpFont(.label).foregroundStyle(MP.body)
            Text(text)
                .font(.figuresDisplay(MPSize.displayS))
                .kerning(-1.1)
                .foregroundStyle(MP.ink)
                .lineLimit(1).minimumScaleFactor(0.7)
                .contentTransition(reduceMotion ? .identity : .numericText(value: value))
                .animation(MPMotion.gated(MPMotion.state, reduceMotion: reduceMotion), value: value)
        }
        .accessibilityElement(children: .combine)
    }

    private func sourceCount(_ me: Me) -> Int {
        (me.wearables.appleHealth.connected ? 1 : 0) + me.wearables.devices.count
    }

    // MARK: Portfolio

    private var portfolioColumns: [GridItem] {
        let n = dynamicTypeSize.isAccessibilitySize ? 1 : (dynamicTypeSize >= .xxxLarge ? 2 : 3)
        return Array(repeating: GridItem(.flexible(), spacing: 10, alignment: .top), count: n)
    }

    private var portfolioCard: some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader("Your portfolio", actionTitle: "Details") { app.selectedTab = .health }
                if app.portfolio.isEmpty {
                    EmptyRow(icon: "square.grid.2x2", title: "Nothing here yet",
                             detail: "Connect Apple Health or a wearable and your steps, sleep, heart and more fill in on their own.")
                } else {
                    LazyVGrid(columns: portfolioColumns, spacing: 10) {
                        ForEach(Array(app.portfolio.prefix(6))) { m in
                            PortfolioTile(metric: m)
                        }
                    }
                    .padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 12)
                }
            }
        }
    }

    // MARK: Today

    private var todayCard: some View {
        let open = Array(app.tasks.open.prefix(3))
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                if open.isEmpty {
                    CardHeader("Today")
                    EmptyRow(icon: "checkmark.circle", title: "All caught up",
                             detail: "New tasks arrive by text and show up here.")
                } else {
                    CardHeader("Today", actionTitle: "All tasks") { app.selectedTab = .tasks }
                    ForEach(open) { t in
                        Button { openTask = t } label: { TaskRow(task: t) }
                            .buttonStyle(.mpRow)
                        if t.id != open.last?.id { InsetDivider() }
                    }
                }
            }
            // The pressed row fill follows the card's corners.
            .clipShape(MP.surfaceShape)
        }
    }

    // MARK: Shortcuts

    private var quickRow: some View {
        let unread = app.me?.unreadMessages ?? 0
        // Side by side until the text is accessibility-sized, then stacked.
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(spacing: 10))
            : AnyLayout(HStackLayout(alignment: .top, spacing: 10))
        return layout { quickCards(unread: unread) }
    }

    @ViewBuilder private func quickCards(unread: Int) -> some View {
        quick("Talk to MedPull", "waveform", family: .indigo,
              subtitle: "Log pain or a task by voice") { app.selectedTab = .talk }
        quick("Care team", "bubble.left.and.bubble.right.fill", family: .blue,
              subtitle: unread > 0 ? "\(unread) new" : "Send a message") {
            app.selectedTab = .messages
        }
    }

    private func quick(_ title: String, _ icon: String, family: MP.Category, subtitle: String,
                       action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Card(padding: 14) {
                VStack(alignment: .leading, spacing: 10) {
                    IconTile(icon, family: family, size: 34)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text(subtitle).mpFont(.label).mpSecondary()
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .buttonStyle(HomeCardPressStyle())
    }

    private var healthNudge: some View {
        Button { app.selectedTab = .health } label: {
            Card {
                HStack(spacing: 14) {
                    IconTile("heart.fill", family: .violet, size: 34)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Connect Apple Health").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text("One tap, and your steps, sleep and heart data build your portfolio on their own.")
                            .mpFont(.label).mpSecondary()
                    }
                    Spacer(minLength: 4)
                    Image(systemName: "chevron.right")
                        .font(.systemGlyphs(MPSize.copy, weight: .semibold))
                        .foregroundStyle(MP.muted)
                        .accessibilityHidden(true)
                }
            }
        }
        .buttonStyle(HomeCardPressStyle())
    }
}

/// A whole card as a button: the gated 0.97 press scale, nothing else.
private struct HomeCardPressStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .contentShape(MP.surfaceShape)
            .scaleEffect(MPMotion.pressScale(configuration.isPressed, reduceMotion: reduceMotion))
            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion),
                       value: configuration.isPressed)
    }
}

/// One tile in the portfolio grid, the site's inset metric: category glyph
/// and date on top, the reading in big light figures, then its name, on the
/// warm inset fill.
private struct PortfolioTile: View {
    let metric: PortfolioMetric
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// Same symbol and family as the Health tab (HealthView.swift's
    /// `PortfolioMetric.tileSymbol` / `tileFamily`), so a signal looks the
    /// same on both screens.
    private var glyph: (String, MP.Category) { (metric.tileSymbol, metric.tileFamily) }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center, spacing: 6) {
                IconTile(glyph.0, family: glyph.1, size: 22)
                Spacer(minLength: 4)
                Text(Dates.shortDay(metric.latest.date))
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .lineLimit(1)
            }
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                if metric.hideUnit {
                    // A duration reads as the site's big numbers with small
                    // units: "6 h 24 min".
                    let minutes = Int((metric.latest.value * 60).rounded())
                    figure("\(minutes / 60)", value: metric.latest.value)
                    unitText("h")
                    if minutes % 60 > 0 {
                        figure("\(minutes % 60)", value: metric.latest.value)
                        unitText("min")
                    }
                } else {
                    figure(metric.latestText, value: metric.latest.value)
                    unitText(metric.unit)
                }
            }
            .lineLimit(1).minimumScaleFactor(0.6)
            .accessibilityLabel(Text(metric.spokenText(for: metric.latest.value)))
            Text(metric.label)
                .mpFont(.labelMedium).foregroundStyle(MP.muted)
                .lineLimit(2).minimumScaleFactor(0.85)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MP.controlShape.fill(MP.fill))
        .accessibilityElement(children: .combine)
    }

    private func figure(_ text: String, value: Double) -> some View {
        Text(text)
            .font(.figuresDisplay(MPSize.displayS)).kerning(-0.9).foregroundStyle(MP.ink)
            .contentTransition(reduceMotion ? .identity : .numericText(value: value))
            .animation(MPMotion.gated(MPMotion.state, reduceMotion: reduceMotion), value: value)
    }

    private func unitText(_ text: String) -> some View {
        Text(text).mpFont(.label).foregroundStyle(MP.muted)
    }
}

/// A task row: category tile, title, a meta line and a trailing state glyph.
/// Home's Today card; the Tasks tab has its own `TaskListRow`.
struct TaskRow: View {
    let task: RecoveryTask

    private var icon: String {
        switch task.kind {
        case "checkin": return "text.bubble.fill"
        case "exercise": return "figure.strengthtraining.functional"
        case "walk": return "figure.walk"
        case "medication": return "pills.fill"
        case "wound_check": return "bandage.fill"
        case "sleep": return "bed.double.fill"
        default: return "checklist"
        }
    }

    private var family: MP.Category {
        switch task.kind {
        case "checkin": return .blue
        case "exercise", "walk": return .teal
        case "medication", "wound_check": return .violet
        case "sleep": return .indigo
        default: return .blue
        }
    }

    var body: some View {
        HStack(spacing: 14) {
            IconTile(icon, family: family)
            VStack(alignment: .leading, spacing: 2) {
                Text(task.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    .strikethrough(task.status == "done", color: MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 0) {
                    Text(task.kindLabel).foregroundStyle(MP.muted)
                    if task.status == "done", let via = task.completedVia {
                        Text("\(MP.dot)done by \(via)").foregroundStyle(MP.muted)
                    } else if task.inSmsConversation {
                        // riskMed on panel: 5.815 / 9.641.
                        Text("\(MP.dot)in progress by text").foregroundStyle(MP.riskMed)
                    } else if let due = task.dueAt {
                        Text("\(MP.dot)due \(Dates.relative(due))").foregroundStyle(MP.muted)
                    }
                }
                .mpFont(.label)
            }
            Spacer(minLength: 4)
            Group {
                if task.isOpen {
                    Image(systemName: "chevron.right")
                        .font(.systemGlyphs(MPSize.copy, weight: .semibold))
                        .foregroundStyle(MP.muted)
                        .accessibilityHidden(true)
                } else {
                    // Solid, not hierarchical: the disc is the state mark
                    // and must keep its full colour.
                    Image(systemName: task.status == "done" ? "checkmark.circle.fill" : "minus.circle")
                        .font(.copyLarge)
                        .foregroundStyle(task.status == "done" ? MP.riskLow : MP.muted)
                        .contentTransition(.symbolEffect(.replace))
                        .accessibilityLabel(task.status == "done" ? "Done" : "Skipped")
                }
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .contentShape(Rectangle())
    }
}
