import SwiftUI

/// A subscriber's day, readable in ten seconds: the verdict and readiness
/// on the gradient tile with the coach's one line under it, the plan with
/// the check-in one tap away, the four numbers that decided the day, then
/// the brief in full for anyone who wants it. The server writes the plan
/// and the brief when the app opens (`refreshDashboard(startDay:)`), so
/// this screen never has to.
struct PersonalHomeView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var showProfile = false
    @State private var showThread = false
    @State private var showBrief = false
    @State private var loggingSession = false
    @State private var openTask: RecoveryTask?
    @State private var greetingGone = false

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        let part = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"
        return "\(part),\n\(app.me?.patient.firstName ?? "there")."
    }

    private var board: Dashboard? { app.dashboard?.dashboard }
    private var checkin: RecoveryTask? { app.tasks.open.first { $0.kind == "checkin" } }
    private var learning: Bool { (board?.panel("readiness")?.hasData ?? false) == false }

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header.mpRise(0)
                    verdictTile.mpRise(1)
                    if learning, board != nil { learningCard.mpRise(2) }
                    todayCard.mpRise(3).id("plan")
                    numbersCard.mpRise(4).id("numbers")
                    if let over = board?.panel("overreach"), over.status == "flag" {
                        alertCard(over, title: "Overreach watch").mpRise(5)
                    } else if let body = board?.panel("body"), body.status == "watch" || body.status == "flag" {
                        alertCard(body, title: "Body signals").mpRise(5)
                    }
                    briefCard.mpRise(6).id("brief")
                    quickRow.mpRise(7).id("quick")
                    if let me = app.me, !me.wearables.appleHealth.connected, me.wearables.devices.isEmpty,
                       me.features.appleHealth {
                        healthNudge
                    }
                    if let error = app.lastError { ErrorBanner(text: error) }
                    PersonalGuardrail()
                }
                .padding(.horizontal, 18).padding(.top, 2).padding(.bottom, 28)
            }
            .refreshable {
                await app.refreshDashboard(startDay: true)
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
                brandItem
                avatarItem
            }
            .animation(MPMotion.gated(MPMotion.state, reduceMotion: reduceMotion), value: greetingGone)
            .sheet(isPresented: $showProfile) { ProfileView() }
            .sheet(isPresented: $showThread) { MessagesView() }
            .sheet(isPresented: $showBrief) { BriefSheet() }
            .sheet(isPresented: $loggingSession) { LogSessionSheet() }
            .navigationDestination(item: $openTask) { task in TaskDestination(task: task) }
            .task {
                if app.dashboard == nil { await app.refreshDashboard(startDay: true) }
                #if DEBUG
                if AppConfig.debugFlag("MP_SHOW") == "profile" { showProfile = true }
                if AppConfig.debugFlag("MP_SHOW") == "session" { loggingSession = true }
                if AppConfig.debugFlag("MP_SHOW") == "brief" { showBrief = true }
                if let target = AppConfig.debugFlag("MP_SCROLL") {
                    try? await Task.sleep(for: .seconds(2))
                    proxy.scrollTo(target, anchor: .top)
                }
                #endif
            }
            }
        }
    }

    // MARK: Toolbar

    @ToolbarContentBuilder private var avatarItem: some ToolbarContent {
        if #available(iOS 26, *) {
            ToolbarItem(placement: .topBarTrailing) { avatarButton }
                .sharedBackgroundVisibility(.hidden)
        } else {
            ToolbarItem(placement: .topBarTrailing) { avatarButton }
        }
    }

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
                Text("Personal beta")
                    .mpFont(.labelMedium)
                    .foregroundStyle(MP.brandInk)
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    .background(MP.capsuleShape.fill(MP.brandTint))
            }
            .dynamicTypeSize(...DynamicTypeSize.accessibility1)
            .fixedSize()
        }
        .opacity(greetingGone ? 0 : 1)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("MedPull Personal beta")
        .accessibilityHidden(greetingGone)
    }

    private var avatarButton: some View {
        Button { showProfile = true } label: {
            Initials(text: app.me?.patient.initials ?? "··", size: 36)
                .frame(width: 44, height: 44)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Profile")
    }

    // MARK: Greeting

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(greeting).title(MPSize.displayM).accessibilityAddTraits(.isHeader)
            if let profile = app.dashboard?.profile {
                Text([profile.goalLabel, profile.sport?.capitalized,
                      board.map { "\($0.daysWithData) days of data" }]
                    .compactMap { $0 }.joined(separator: MP.dot))
                    .mpFont(.copyLarge).foregroundStyle(MP.body)
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
        if let board {
            let verdict = board.verdict
            let readiness = board.panel("readiness")
            let score = readiness?.number("score")
            let values = readiness?.series.map(\.value) ?? []
            let headline = app.dashboard?.brief.headline
            Button { app.selectedTab = .stats } label: {
                GradientTile(verdict.gradient,
                             kicker: "Today",
                             value: score.map { String(format: "%.0f", $0) } ?? "—",
                             unit: score == nil ? "learning you" : "readiness",
                             side: (readiness?.statusText ?? "Learning", "recovery state")) {
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
                            Text("Stats").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                            Image(systemName: "chevron.right")
                                .font(.systemGlyphs(11, weight: .semibold)).foregroundStyle(MP.brandInk)
                                .accessibilityHidden(true)
                        }
                        // The coach's one line when there is one, else the
                        // verdict's reason: what decided today, in a breath.
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
            Card {
                HStack(spacing: 14) {
                    ProgressView().tint(MP.brand)
                    Text("Reading your signals…").mpFont(.copyLarge).foregroundStyle(MP.body)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    /// The first days: what each readout needs before it can speak.
    private var learningCard: some View {
        let days = board?.daysWithData ?? 0
        let steps: [(String, Int, String)] = [
            ("Readiness", 5, "five nights of HRV, resting heart rate and sleep"),
            ("Training load", 14, "two weeks of activity"),
            ("Acute:chronic ratio", 28, "four weeks of activity"),
        ]
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader("Learning you")
                Text(days == 0
                     ? "Nothing has arrived yet. Connect Apple Health or a wearable, wear it tonight, and open the app tomorrow."
                     : "Every readout compares you with your own baseline, so the first days are for listening. Wear your watch overnight and it fills in on its own.")
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

    // MARK: Plan

    private var todayCard: some View {
        let open = Array(app.tasks.open.prefix(3))
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                if open.isEmpty {
                    CardHeader("Your plan")
                    EmptyRow(icon: "checkmark.circle", title: "All done for today",
                             detail: "Tomorrow’s plan is written in the morning from tonight’s numbers.")
                } else {
                    CardHeader("Your plan", actionTitle: "All") { app.selectedTab = .tasks }
                    ForEach(open) { t in
                        Button { openTask = t } label: { TaskRow(task: t) }
                            .buttonStyle(.mpRow)
                        if t.id != open.last?.id { InsetDivider() }
                    }
                    if let checkin {
                        InsetDivider(leading: 16)
                        Button { openTask = checkin } label: {
                            HStack(spacing: 8) {
                                Image(systemName: "text.bubble.fill")
                                Text("Start today’s check-in")
                                Spacer()
                                Text("2 min").mpFont(.label).foregroundStyle(MP.muted)
                            }
                            .mpFont(.copyLargeMedium)
                            .foregroundStyle(MP.brandInk)
                            .padding(.horizontal, 16).padding(.vertical, 12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .buttonStyle(.mpRow)
                    }
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

    @ViewBuilder private var numbersCard: some View {
        if let board {
            let keys = board.sections.filter { !["readiness", "care", "subjective", "body", "overreach", "rhythm"].contains($0) }
            let panels = keys.compactMap { board.panel($0) }.prefix(4)
            if !panels.isEmpty {
                Card(padding: 0) {
                    VStack(alignment: .leading, spacing: 0) {
                        CardHeader("Your numbers", actionTitle: "All stats") { app.selectedTab = .stats }
                        LazyVGrid(columns: gridColumns, spacing: 10) {
                            ForEach(Array(panels), id: \.key) { p in
                                Button { app.selectedTab = .stats } label: { MiniStatTile(panel: p) }
                                    .buttonStyle(.plain)
                            }
                        }
                        .padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 12)
                    }
                }
            }
        }
    }

    private func alertCard(_ panel: Panel, title: String) -> some View {
        Button { app.selectedTab = .stats } label: {
            Card {
                HStack(alignment: .top, spacing: 14) {
                    IconTile(panel.symbol, family: panel.family, size: 34)
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            Spacer()
                            StatusPill(text: panel.statusText == title
                                       ? (panel.status == "flag" ? "Flagged" : "Watch") : panel.statusText,
                                       tone: panel.tone)
                        }
                        Text(panel.finding.typeset).mpFont(.copy).mpSecondary().lineSpacing(2)
                            .lineLimit(3)
                            .multilineTextAlignment(.leading)
                    }
                }
            }
        }
        .buttonStyle(CardTapStyle())
    }

    // MARK: Brief

    @ViewBuilder private var briefCard: some View {
        if let brief = app.dashboard?.brief {
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
                            .lineLimit(4)
                            .multilineTextAlignment(.leading)
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

    private var quickRow: some View {
        let unread = app.me?.unreadMessages ?? 0
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(spacing: 10))
            : AnyLayout(HStackLayout(alignment: .top, spacing: 10))
        return layout {
            quick("Log a session", "figure.run", family: .teal,
                  subtitle: "Minutes and how hard") { loggingSession = true }
            quick("Ask your coach", "waveform", family: .indigo,
                  subtitle: unread > 0 ? "\(unread) new" : "Why is my readiness \(readinessWord)?") {
                app.selectedTab = .talk
            }
        }
    }

    private var readinessWord: String {
        guard let s = board?.panel("readiness")?.number("score") else { return "low" }
        return s >= 67 ? "high" : s >= 34 ? "steady" : "low"
    }

    private func quick(_ title: String, _ icon: String, family: MP.Category, subtitle: String,
                       action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Card(padding: 14) {
                VStack(alignment: .leading, spacing: 10) {
                    IconTile(icon, family: family, size: 34)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text(subtitle).mpFont(.label).mpSecondary().lineLimit(2)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .buttonStyle(CardTapStyle())
    }

    private var healthNudge: some View {
        Button { app.selectedTab = .health } label: {
            Card {
                HStack(spacing: 14) {
                    IconTile("heart.fill", family: .violet, size: 34)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Connect Apple Health").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text("Readiness needs overnight HRV, resting heart rate and sleep. One tap.")
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
        .buttonStyle(CardTapStyle())
    }
}

/// The brief in full, with the coach's longer reads a tap away.
struct BriefSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var dive: DeepDive?
    @State private var loading: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let brief = app.dashboard?.brief {
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
                    Text("Go deeper").mpFont(.labelMedium).foregroundStyle(MP.muted).padding(.top, 6)
                    ForEach([("recovery", "Recovery", "waveform.path.ecg"), ("training", "Training", "flame.fill"),
                             ("sleep", "Sleep", "bed.double.fill"), ("weekly", "The week", "calendar")], id: \.0) { domain, label, symbol in
                        Button {
                            loading = domain
                            Task {
                                defer { loading = nil }
                                dive = try? await app.api.deepDive(domain)
                            }
                        } label: {
                            HStack(spacing: 12) {
                                IconTile(symbol, family: .indigo)
                                Text(label).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                Spacer()
                                if loading == domain { ProgressView().controlSize(.small) }
                                else { Image(systemName: "chevron.right").font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted) }
                            }
                            .padding(14)
                            .glassSurface(MP.surfaceShape, solid: true)
                            .contentShape(MP.surfaceShape)
                        }
                        .buttonStyle(CardTapStyle())
                        .disabled(loading != nil)
                    }
                    PersonalGuardrail()
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
            .sheet(item: $dive) { d in DeepDiveSheet(dive: d) }
        }
        .presentationDetents([.large])
    }
}

/// Log a session: minutes and RPE (Foster's session load), a note. The
/// readouts switch to session-RPE load once enough sessions are logged.
struct LogSessionSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var minutes = 45
    @State private var rpe: AnswerValue? = .int(6)
    @State private var note = ""
    @State private var saving = false
    @State private var error: String?
    @State private var saved = false

    private var rpeWord: String {
        switch rpe?.intValue ?? 0 {
        case 0...2: return "Very easy"
        case 3...4: return "Easy"
        case 5...6: return "Moderate"
        case 7...8: return "Hard"
        default: return "Maximal"
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("How long, and how hard?").title(MPSize.displayS)
                    Text("Minutes times effort is your session load (Foster’s session RPE). Log every session and your acute:chronic ratio runs on it.")
                        .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    Card(padding: 0) {
                        Stepper(value: $minutes, in: 5...600, step: 5) {
                            HStack {
                                Text("Minutes").mpFont(.copyLarge).foregroundStyle(MP.ink)
                                Spacer()
                                Text("\(minutes)").font(.figuresCopyLarge).foregroundStyle(MP.ink)
                            }
                        }
                        .tint(MP.brand)
                        .padding(.horizontal, 16).padding(.vertical, 10)
                        .mpSelectionFeedback(minutes)
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text("Effort, 0 to 10").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            Spacer()
                            Text(rpeWord).mpFont(.label).foregroundStyle(MP.muted)
                        }
                        ScaleAnswer(value: $rpe, painting: false)
                    }
                    TextField("Anything worth noting (optional)", text: $note,
                              prompt: Text("Anything worth noting (optional)").foregroundColor(MP.muted), axis: .vertical)
                        .lineLimit(2...5)
                        .textFieldStyle(FieldStyle())
                    if let error { ErrorBanner(text: error) }
                    if saved {
                        Card(tint: true) {
                            HStack(spacing: 10) {
                                Image(systemName: "checkmark.seal.fill").foregroundStyle(MP.riskLow)
                                Text("Logged. Load \(minutes * (rpe?.intValue ?? 0)) AU.").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            }
                        }
                    } else {
                        PrimaryButton(title: "Log session", icon: "checkmark", loading: saving,
                                      disabled: rpe?.intValue == nil) { save() }
                    }
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .scrollDismissesKeyboard(.interactively)
            .ambientScreen()
            .navigationTitle("Log a session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium)
                }
            }
            .mpCompletionFeedback(saved)
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    private func save() {
        guard let effort = rpe?.intValue else { return }
        saving = true
        error = nil
        Task {
            defer { saving = false }
            do {
                try await app.api.personalLog(key: "session_minutes", value: Double(minutes))
                try await app.api.personalLog(key: "rpe", value: Double(effort))
                let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty { try await app.api.personalLog(key: "note", text: trimmed) }
                saved = true
                await app.refreshDashboard(startDay: true)
                try? await Task.sleep(for: .seconds(1.2))
                dismiss()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}
