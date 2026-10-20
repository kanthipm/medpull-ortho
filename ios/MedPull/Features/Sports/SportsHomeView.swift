import SwiftUI

/// An athlete's day, readable in ten seconds: the verdict and readiness on
/// the gradient tile with the brief's one line, today's schedule, the plan
/// with the wellness check-in one tap away, the numbers that decided the
/// day, what to do about it, the injury plan when there is one, and the
/// rest a tab away. The server writes the plan and the brief when the app
/// opens (`refreshSports(startDay:)`), so this screen never has to.
struct SportsHomeView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var showProfile = false
    @State private var showWellness = false
    @State private var loggingSession = false
    @State private var showBrief = false
    @State private var showHistory = false
    @State private var openTask: RecoveryTask?
    @State private var openPanel: Panel?
    @State private var greetingGone = false

    private var home: SportsHome? { app.sportsHome }

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        let part = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"
        return "\(part),\n\(app.me?.patient.firstName ?? "there")."
    }

    var body: some View {
        @Bindable var app = app
        NavigationStack {
            ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header.mpRise(0)
                    verdictTile.mpRise(1)
                    if let home {
                        if home.verdict.kind == "learning" { learningCard.mpRise(2) }
                        if !home.schedule.today.isEmpty || home.schedule.nextGame != nil { scheduleCard(home).mpRise(2).id("schedule") }
                        planCard(home).mpRise(3).id("plan")
                        numbersCard(home).mpRise(4).id("numbers")
                        if !home.injuries.isEmpty { injuryCard(home).mpRise(5).id("injury") }
                        if !home.suggestions.isEmpty { suggestionsCard(home).mpRise(5).id("suggestions") }
                        if home.neuromuscular.hasData { neuroCard(home).mpRise(6).id("neuro") }
                        briefCard(home).mpRise(6).id("brief")
                        quickRow(home).mpRise(7).id("quick")
                        if home.devicesConnected <= 1 || !(app.me?.wearables.appleHealth.connected ?? false) {
                            devicesNudge(home)
                        }
                    }
                    if let error = app.lastError { ErrorBanner(text: error) }
                    SportsGuardrail()
                }
                .padding(.horizontal, 18).padding(.top, 2).padding(.bottom, 28)
            }
            .refreshable {
                await app.refreshSports(startDay: true)
                await app.refreshTasks(surface: false)
                await app.refreshMe(surface: false)
            }
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
                BrandLockupItem(hidden: greetingGone, badge: "Sports")
                AvatarItem(initials: app.me?.patient.initials ?? "··") { showProfile = true }
            }
            .animation(MPMotion.gated(MPMotion.state, reduceMotion: reduceMotion), value: greetingGone)
            .sheet(isPresented: $showProfile) { ProfileView() }
            .sheet(isPresented: $app.showConnections) { SportsDevicesView() }
            .sheet(isPresented: $showWellness) { WellnessSheet() }
            .sheet(isPresented: $loggingSession) { SportsSessionSheet() }
            .sheet(isPresented: $showBrief) { SportsBriefSheet() }
            .navigationDestination(isPresented: $showHistory) { TaskHistoryView() }
            .navigationDestination(item: $openTask) { task in SportsTaskDestination(task: task) }
            .navigationDestination(item: $openPanel) { panel in PanelDetailView(panel: panel) }
            .task {
                if app.sportsHome == nil { await app.refreshSports(startDay: true) }
                #if DEBUG
                if AppConfig.debugFlag("MP_SHOW") == "wellness" { showWellness = true }
                if AppConfig.debugFlag("MP_SHOW") == "session" { loggingSession = true }
                if AppConfig.debugFlag("MP_SHOW") == "profile" { showProfile = true }
                if AppConfig.debugFlag("MP_SHOW") == "devices" { app.showConnections = true }
                if AppConfig.debugFlag("MP_SHOW") == "brief" { showBrief = true }
                if let target = AppConfig.debugFlag("MP_SCROLL") {
                    try? await Task.sleep(for: .seconds(1.5))
                    withAnimation(nil) { proxy.scrollTo(target, anchor: .top) }
                }
                #endif
            }
            }
        }
    }

    // MARK: Greeting

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(greeting).title(MPSize.displayM).accessibilityAddTraits(.isHeader)
            if let p = home?.profile ?? app.me?.sports {
                HStack(spacing: 8) {
                    Text([p.teamLine ?? p.sportLabel, p.position, p.jersey.map { "#\($0)" }]
                        .compactMap { $0 }.joined(separator: MP.dot))
                        .mpFont(.copyLarge).foregroundStyle(MP.body).lineLimit(2)
                    if let home, home.availability != "available" {
                        AvailabilityPill(status: home.availability)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 6).padding(.bottom, 6)
        .onGeometryChange(for: Bool.self) { proxy in
            proxy.frame(in: .scrollView).maxY < 8
        } action: { gone in
            if gone != greetingGone { greetingGone = gone }
        }
    }

    // MARK: Verdict

    @ViewBuilder private var verdictTile: some View {
        if let home {
            let verdict = home.verdict
            let score = verdict.score
            let values = home.readiness.series.map(\.value)
            let headline = home.brief?.headline
            Button { app.selectedTab = .recovery } label: {
                GradientTile(verdict.gradient,
                             kicker: home.schedule.gameToday != nil ? "Game day" : "Today",
                             value: score.map { String(format: "%.0f", $0) } ?? "—",
                             unit: score == nil ? "learning you" : "readiness",
                             side: (home.readiness.statusText, "overnight")) {
                    if values.count > 1 {
                        CurveArt(points: unitPoints(values), height: 92)
                    } else {
                        ArtGrid().frame(height: 92)
                    }
                } caption: {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 8) {
                            Image(systemName: verdict.symbol)
                                .font(.systemGlyphs(15, weight: .medium))
                                .foregroundStyle(MP.foreground(verdict.tone))
                                .accessibilityHidden(true)
                            StatusPill(text: verdict.title, tone: verdict.tone)
                            Spacer()
                            Text("Recovery").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                            Image(systemName: "chevron.right")
                                .font(.systemGlyphs(11, weight: .semibold)).foregroundStyle(MP.brandInk)
                                .accessibilityHidden(true)
                        }
                        Text((headline.flatMap { $0.isEmpty ? nil : $0 } ?? verdict.reason).typeset)
                            .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                            .multilineTextAlignment(.leading)
                        Text(verdict.detail.typeset)
                            .mpFont(.copy).foregroundStyle(MP.body)
                            .fixedSize(horizontal: false, vertical: true)
                            .multilineTextAlignment(.leading)
                    }
                }
            }
            .buttonStyle(CardTapStyle())
            .accessibilityElement(children: .contain)
        } else {
            LoadingCard()
        }
    }

    private var learningCard: some View {
        let days = home?.daysWithData ?? 0
        let steps: [(String, Int, String)] = [
            ("Readiness", 5, "five nights of HRV, resting heart rate and sleep"),
            ("Wellness baseline", 5, "five mornings of answers"),
            ("Weekly load", 14, "two weeks of logged sessions"),
        ]
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader("Learning you")
                Text(days == 0
                     ? "Nothing has arrived yet. Connect your watch, answer the morning questions, log tonight's practice, and open the app tomorrow."
                     : "Every readout compares you with your own baseline, so the first days are for listening.")
                    .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16).padding(.bottom, 12)
                ForEach(steps, id: \.0) { name, need, what in
                    let done = min(days, need)
                    VStack(alignment: .leading, spacing: 5) {
                        HStack {
                            Text(name).mpFont(.copyMedium).foregroundStyle(MP.ink)
                            Spacer()
                            Text(done >= need ? "Ready" : "\(done) of \(need) days")
                                .font(.figuresLabel).foregroundStyle(done >= need ? MP.riskLow : MP.muted)
                        }
                        GeometryReader { proxy in
                            ZStack(alignment: .leading) {
                                MP.capsuleShape.fill(MP.track)
                                MP.capsuleShape.fill(done >= need ? MP.riskLow : MP.brand)
                                    .frame(width: proxy.size.width * CGFloat(done) / CGFloat(need))
                            }
                        }
                        .frame(height: 6)
                        Text(what).mpFont(.label).foregroundStyle(MP.muted)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 8)
                    .accessibilityElement(children: .combine)
                }
            }
            .padding(.bottom, 8)
        }
    }

    // MARK: Schedule

    private func scheduleCard(_ home: SportsHome) -> some View {
        let s = home.schedule
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardTitleRow("Schedule", note: s.density == "heavy" ? "heavy week" : nil)
                if s.today.isEmpty, let next = s.nextGame {
                    EventRow(event: next)
                    Text(s.finding.typeset).mpFont(.label).foregroundStyle(MP.muted)
                        .padding(.horizontal, 16).padding(.bottom, 12)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    ForEach(s.today) { e in
                        EventRow(event: e, highlight: e.isGame)
                        if e.id != s.today.last?.id { InsetDivider(leading: 16) }
                    }
                    if let next = s.nextGame, !s.today.contains(where: \.isGame) {
                        InsetDivider(leading: 16)
                        HStack {
                            Text("Next game").mpFont(.label).foregroundStyle(MP.muted)
                            Spacer()
                            Text("\(next.title)\(next.opponent.map { " vs \($0)" } ?? "")\(MP.dot)\(Dates.monthDay(next.date))")
                                .mpFont(.label).foregroundStyle(MP.body)
                        }
                        .padding(.horizontal, 16).padding(.vertical, 10)
                    }
                }
            }
            .clipShape(MP.surfaceShape)
        }
    }

    // MARK: Plan

    private func planCard(_ home: SportsHome) -> some View {
        let open = Array(app.tasks.open.prefix(4))
        let checkin = app.tasks.open.first { $0.kind == "checkin" }
        let answered = home.wellness.answeredToday > 0
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader("Your plan", actionTitle: "All") { showHistory = true }
                if !answered {
                    VStack(alignment: .leading, spacing: 8) {
                        PrimaryButton(title: "Morning check-in", icon: "face.smiling") { showWellness = true }
                        Text("Six quick questions, read beside your overnight numbers. About a minute.")
                            .mpFont(.label).foregroundStyle(MP.muted).padding(.horizontal, 4)
                    }
                    .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 12)
                    if !open.filter({ $0.kind != "checkin" }).isEmpty { InsetDivider(leading: 16) }
                } else {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.circle.fill").foregroundStyle(MP.riskLow)
                        Text("Checked in").mpFont(.copyMedium).foregroundStyle(MP.ink)
                        Text(home.wellness.statusText).mpFont(.label).foregroundStyle(MP.foreground(home.wellness.tone))
                        Spacer()
                        Button("Edit") { showWellness = true }.buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    if !open.filter({ $0.kind != "checkin" }).isEmpty { InsetDivider(leading: 16) }
                }
                let rest = open.filter { $0.id != checkin?.id }
                if rest.isEmpty && answered {
                    EmptyRow(icon: "checkmark", title: "All done for today",
                             detail: "Tomorrow's plan is written in the morning from tonight's numbers.")
                }
                ForEach(rest) { t in
                    Button { openTask = t } label: { PlanRow(task: t) }
                        .buttonStyle(.mpRow)
                    if t.id != rest.last?.id { InsetDivider() }
                }
            }
            .clipShape(MP.surfaceShape)
        }
    }

    // MARK: Numbers

    private var gridColumns: [GridItem] {
        let n = dynamicTypeSize.isAccessibilitySize ? 1 : 2
        return Array(repeating: GridItem(.flexible(), spacing: 10, alignment: .top), count: n)
    }

    private func numbersCard(_ home: SportsHome) -> some View {
        let panels = [home.sleep, home.hrv, home.restingHr].compactMap { $0 }
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader("Why today", actionTitle: "All readouts") { app.selectedTab = .recovery }
                LazyVGrid(columns: gridColumns, spacing: 10) {
                    ForEach(panels, id: \.key) { p in
                        Button { openPanel = p } label: { MiniStatTile(panel: p) }
                            .buttonStyle(.plain)
                            .accessibilityHint("Opens this readout in full")
                    }
                    Button { app.selectedTab = .recovery } label: { loadTile(home.load) }
                        .buttonStyle(.plain)
                }
                .padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 12)
            }
        }
    }

    private func loadTile(_ load: LoadRead) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center, spacing: 6) {
                IconTile("flame.fill", family: .teal, size: 22)
                Spacer(minLength: 4)
                Circle().fill(MP.foreground(load.tone)).frame(width: 7, height: 7).accessibilityHidden(true)
            }
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(load.weekLoad >= 1000 ? String(format: "%.1fk", load.weekLoad / 1000) : String(format: "%.0f", load.weekLoad))
                    .font(.figuresDisplay(MPSize.displayS)).kerning(-0.9).foregroundStyle(MP.ink)
                    .lineLimit(1).minimumScaleFactor(0.6)
                Text("AU this week").mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
            }
            Text("Load").mpFont(.labelMedium).foregroundStyle(MP.muted).lineLimit(1)
            Text(load.changePct.map { String(format: "%@%.0f%% vs recent", $0 >= 0 ? "+" : "−", abs($0)) } ?? load.statusText)
                .mpFont(.label).foregroundStyle(MP.foreground(load.tone)).lineLimit(1).minimumScaleFactor(0.8)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MP.controlShape.fill(MP.fill))
        .accessibilityElement(children: .combine)
    }

    // MARK: Injury

    private func injuryCard(_ home: SportsHome) -> some View {
        Button { app.selectedTab = .rehab } label: {
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(home.injuries) { inj in
                        HStack(alignment: .top, spacing: 12) {
                            Glyph(systemName: inj.symbol, family: .violet, size: 36)
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(alignment: .firstTextBaseline) {
                                    Text(inj.side.map { "\(inj.label), \($0)" } ?? inj.label)
                                        .mpFont(.copyLargeMedium).foregroundStyle(MP.ink).lineLimit(2)
                                        .multilineTextAlignment(.leading)
                                    Spacer()
                                    AvailabilityPill(status: home.availability)
                                }
                                if let ph = inj.phase {
                                    Text("Phase \(ph.number) of \(ph.of)\(MP.dot)\(ph.name)\(MP.dot)\(ph.met) of \(ph.total) gates")
                                        .mpFont(.label).foregroundStyle(MP.muted)
                                }
                                if let rts = inj.rts, let met = rts.met, let total = rts.total {
                                    HStack(spacing: 8) {
                                        GeometryReader { proxy in
                                            ZStack(alignment: .leading) {
                                                MP.capsuleShape.fill(MP.track)
                                                MP.capsuleShape.fill(MP.brand)
                                                    .frame(width: proxy.size.width * CGFloat(met) / CGFloat(max(total, 1)))
                                            }
                                        }
                                        .frame(height: 6)
                                        Text("\(met)/\(total) return criteria").font(.figuresLabel).foregroundStyle(MP.body)
                                            .fixedSize()
                                    }
                                }
                                if let focus = inj.focus.first {
                                    Text("This week: \(focus.title)").mpFont(.copy).foregroundStyle(MP.body)
                                        .multilineTextAlignment(.leading)
                                }
                            }
                        }
                        .padding(16)
                        if inj.id != home.injuries.last?.id { InsetDivider(leading: 16) }
                    }
                }
            }
        }
        .buttonStyle(CardTapStyle())
    }

    // MARK: Suggestions

    private func suggestionsCard(_ home: SportsHome) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("What to do about it",
                         note: home.suggestionCount > home.suggestions.count ? "\(home.suggestionCount) today" : nil,
                         actionTitle: "All") { app.selectedTab = .recovery }
            ForEach(home.suggestions.prefix(2)) { s in
                SuggestionCard(suggestion: s, expanded: s.id == home.suggestions.first?.id)
            }
        }
    }

    // MARK: Neuromuscular

    private func neuroCard(_ home: SportsHome) -> some View {
        Button { app.selectedTab = .progress } label: {
            Card {
                HStack(alignment: .top, spacing: 14) {
                    Glyph(systemName: "figure.jumprope", family: .teal, size: 36)
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text("Jump test").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            Spacer()
                            StatusPill(text: home.neuromuscular.statusText, tone: home.neuromuscular.tone)
                        }
                        Text(home.neuromuscular.finding.typeset).mpFont(.copy).mpSecondary().lineSpacing(2)
                            .lineLimit(3).multilineTextAlignment(.leading)
                    }
                }
            }
        }
        .buttonStyle(CardTapStyle())
    }

    // MARK: Brief

    @ViewBuilder private func briefCard(_ home: SportsHome) -> some View {
        if let brief = home.brief {
            Button { showBrief = true } label: {
                Card(tint: true) {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 10) {
                            IconTile("sparkles", family: .indigo)
                            Text("Your brief").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                .accessibilityAddTraits(.isHeader)
                            Spacer()
                            if let at = brief.generatedAt {
                                Text(Dates.relative(at)).mpFont(.label).mpSecondary()
                            }
                        }
                        Text(brief.brief.typeset)
                            .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(3)
                            .lineLimit(4).multilineTextAlignment(.leading)
                        HStack(spacing: 4) {
                            Text("Read it all").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                            Image(systemName: "chevron.right")
                                .font(.systemGlyphs(11, weight: .semibold)).foregroundStyle(MP.brandInk)
                        }
                    }
                }
            }
            .buttonStyle(CardTapStyle())
        }
    }

    // MARK: Shortcuts

    private func quickRow(_ home: SportsHome) -> some View {
        let unread = app.me?.unreadMessages ?? 0
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(spacing: 10))
            : AnyLayout(HStackLayout(alignment: .top, spacing: 10))
        return layout {
            quick("Log a session", "figure.basketball", family: .teal,
                  subtitle: home.schedule.today.first.map { "Today: \($0.title.lowercased())" } ?? "Minutes, RPE and jumps") {
                loggingSession = true
            }
            quick("Ask your coach", "waveform", family: .indigo,
                  subtitle: unread > 0 ? "\(unread) new" : "Why is my readiness \(readinessWord(home))?") {
                app.selectedTab = .care
            }
        }
    }

    private func readinessWord(_ home: SportsHome) -> String {
        guard let s = home.verdict.score else { return "low" }
        return s >= 67 ? "high" : s >= 34 ? "steady" : "low"
    }

    private func quick(_ title: String, _ icon: String, family: MP.Category, subtitle: String,
                       action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Card(padding: 14) {
                VStack(alignment: .leading, spacing: 10) {
                    Glyph(systemName: icon, family: family, size: 36)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text(subtitle).mpFont(.label).mpSecondary().lineLimit(2).multilineTextAlignment(.leading)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .buttonStyle(CardTapStyle())
    }

    private func devicesNudge(_ home: SportsHome) -> some View {
        Button { app.showConnections = true } label: {
            Card {
                HStack(spacing: 14) {
                    Glyph(systemName: "applewatch.radiowaves.left.and.right", family: .violet, size: 36)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Connect your devices").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text("Apple Health, your ring or band, and the team's force plates and trackers, all in one place.")
                            .mpFont(.label).mpSecondary().multilineTextAlignment(.leading)
                    }
                    Spacer(minLength: 4)
                    Image(systemName: "chevron.right")
                        .font(.systemGlyphs(MPSize.copy, weight: .semibold))
                        .foregroundStyle(MP.muted)
                        .accessibilityHidden(true)
                }
            }
        }
        .buttonStyle(CardTapStyle())
    }
}

/// A plan item opens the task; the wellness check-in opens the sheet.
struct SportsTaskDestination: View {
    let task: RecoveryTask
    @State private var showWellness = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        if task.kind == "checkin" {
            WellnessSheet(embedded: true)
        } else {
            TaskDetailView(task: task)
        }
    }
}

/// The brief in full.
struct SportsBriefSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let brief = app.sportsHome?.brief {
                        if let headline = brief.headline, !headline.isEmpty {
                            Text(headline.typeset).title(MPSize.displayS).accessibilityAddTraits(.isHeader)
                        }
                        Text(brief.brief.typeset)
                            .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(4)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(brief.provider == "fallback" || brief.provider == nil
                             ? "Written from your numbers." : "Written by your coach from your numbers.")
                            .mpFont(.label).foregroundStyle(MP.muted)
                    }
                    if let v = app.sportsHome?.verdict, case let others = v.reasons.filter({ $0 != v.reason }), !others.isEmpty {
                        Text("What decided it").mpFont(.labelMedium).foregroundStyle(MP.muted).padding(.top, 6)
                        Card(padding: 0) {
                            VStack(alignment: .leading, spacing: 0) {
                                ForEach(Array(others.enumerated()), id: \.offset) { i, r in
                                    HStack(alignment: .top, spacing: 8) {
                                        LimeDot(size: 6).padding(.top, 7)
                                        Text(r.typeset).mpFont(.copy).foregroundStyle(MP.ink)
                                            .fixedSize(horizontal: false, vertical: true)
                                    }
                                    .padding(.horizontal, 16).padding(.vertical, 8)
                                    if i < others.count - 1 { InsetDivider(leading: 16) }
                                }
                            }
                            .padding(.vertical, 6)
                        }
                    }
                    SportsGuardrail()
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .ambientScreen()
            .navigationTitle("Your brief")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }.mpFont(.copyLargeMedium)
                }
            }
        }
        .presentationDetents([.large])
    }
}
