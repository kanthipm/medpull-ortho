import SwiftUI

/// Injury recovery: the phase the athlete is in, the gates to the next one,
/// the return-to-sport criteria, what to work on this week, every measure
/// over time with left against right, and the phone tests that feed them.
/// With no injury on file: report one, read what is coming back from past
/// ones, and the prevention work that keeps it that way.
struct RehabView: View {
    @Environment(AppModel.self) private var app
    @State private var board: RehabBoard?
    @State private var error: String?
    @State private var reporting = false
    @State private var openInjury: InjuryBoard?
    @State private var phoneTest: PhoneTest?

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let board {
                        if board.active.isEmpty {
                            noInjury(board).mpRise(0)
                        } else if board.active.count == 1, let inj = board.active.first {
                            InjuryDetail(injury: inj, availability: board.availability, inline: true) { changed in
                                if let changed { replace(changed) } else { Task { await load() } }
                            }
                        } else {
                            activeList(board).mpRise(0)
                        }
                        if !board.past.isEmpty { pastCard(board.past).mpRise(2) }
                        preventionCard.mpRise(3)
                    } else if let error {
                        ErrorBanner(text: error)
                        SecondaryButton(title: "Try again", icon: "arrow.clockwise") { Task { await load() } }
                    } else {
                        LoadingCard(text: "Reading your plan…")
                    }
                    SportsGuardrail()
                }
                .padding(.horizontal, 18).padding(.top, 2).padding(.bottom, 28)
            }
            .refreshable { await load() }
            .mpHardScrollEdge()
            .ambientScreen()
            .mpNavigationTitle("Injury")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { reporting = true } label: {
                        Image(systemName: "plus")
                            .font(.systemGlyphs(17, weight: .medium)).foregroundStyle(MP.ink)
                            .frame(width: 44, height: 44).contentShape(Rectangle())
                    }
                    .accessibilityLabel("Report an injury")
                }
            }
            .sheet(isPresented: $reporting) {
                ReportInjurySheet { newBoard in
                    board = newBoard
                    Task { await app.refreshSports(startDay: false) }
                }
            }
            .sheet(item: $phoneTest) { test in PhoneTestHost(test: test) { Task { await load() } } }
            .navigationDestination(item: $openInjury) { inj in
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        InjuryDetail(injury: inj, availability: board?.availability ?? "available", inline: false) { changed in
                            if let changed { replace(changed) } else { Task { await load() } }
                        }
                        SportsGuardrail()
                    }
                    .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
                }
                .ambientScreen()
                .mpNavigationTitle(inj.title, short: "Injury")
                .navigationBarTitleDisplayMode(.inline)
            }
            .task {
                if board == nil { await load() }
                #if DEBUG
                if AppConfig.debugFlag("MP_SHOW") == "report" { reporting = true }
                if let target = AppConfig.debugFlag("MP_SCROLL") {
                    try? await Task.sleep(for: .seconds(1.5))
                    withAnimation(nil) { proxy.scrollTo(target, anchor: .top) }
                }
                #endif
            }
            .mpErrorFeedback(error)
            }
        }
    }

    private func load() async {
        do {
            board = try await app.api.sportsRehab()
            error = nil
        } catch {
            if board == nil { self.error = AppModel.message(for: error) }
        }
    }

    private func replace(_ inj: InjuryBoard) {
        guard let b = board else { return }
        let active = b.active.map { $0.id == inj.id ? inj : $0 }
        board = RehabBoard(active: active, past: b.past, availability: b.availability, asOf: b.asOf, catalog: b.catalog)
        if let open = openInjury, open.id == inj.id { openInjury = inj }
    }

    // MARK: No injury

    private func noInjury(_ board: RehabBoard) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            GradientTile(.sage, kicker: "Injury", value: "Clear", unit: nil, side: (Availability.label(board.availability), "status")) {
                ArtGrid().frame(height: 44)
            } caption: {
                VStack(alignment: .leading, spacing: 8) {
                    Text("No active injury on file.").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    Text("Report one here the day it happens and the plan starts from the right phase, with the gates your staff use. Knee, ankle, hamstring, groin, back, concussion and more.")
                        .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .multilineTextAlignment(.leading)
                    SecondaryButton(title: "Report an injury", icon: "cross.case.fill") { reporting = true }
                }
            }
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle("Screens on the phone", note: "knee and ankle health")
                Card(padding: 0) {
                    VStack(spacing: 0) {
                        screenRow("Single-leg balance", "Each leg, phone at the chest. A side more than a quarter weaker is worth a look.",
                                  symbol: "figure.stand", family: .violet) { phoneTest = .balance }
                        InsetDivider(leading: 16 + 32 + 12)
                        screenRow("Single-leg jump", "Each leg. Under 90% symmetry is the number that predicts the next injury.",
                                  symbol: "figure.jumprope", family: .teal) { phoneTest = .jump(testKey: "single_leg_cmj", side: "left") }
                        InsetDivider(leading: 16 + 32 + 12)
                        screenRow("Hip and hamstring range", "Hip rotation and hamstring length, each side, with the phone on the shin.",
                                  symbol: "figure.flexibility", family: .indigo) { phoneTest = .angle(measureKey: nil, injuryId: nil) }
                    }
                    .clipShape(MP.surfaceShape)
                }
            }
        }
    }

    private func screenRow(_ title: String, _ detail: String, symbol: String, family: MP.Category,
                           action: @escaping () -> Void) -> some View {
        Button(action: action) {
            ListRow(title, subtitle: detail, symbol: symbol, family: family) { EmptyView() }
        }
        .buttonStyle(.mpRow)
    }

    private func activeList(_ board: RehabBoard) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Active", note: "\(board.active.count) injuries")
            ForEach(board.active) { inj in
                Button { openInjury = inj } label: {
                    Card {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack(alignment: .top, spacing: 12) {
                                Glyph(systemName: inj.symbol, family: .violet, size: 36)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(inj.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                        .multilineTextAlignment(.leading)
                                    Text("\(inj.weeksText) since \(inj.anchor)").mpFont(.label).foregroundStyle(MP.muted)
                                }
                                Spacer(minLength: 0)
                                Image(systemName: "chevron.right")
                                    .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                                    .accessibilityHidden(true)
                            }
                            if let ph = inj.phase, !inj.phases.isEmpty {
                                PhaseStepper(phases: inj.phases, current: ph.number, total: ph.of)
                            }
                        }
                    }
                }
                .buttonStyle(CardTapStyle())
            }
        }
    }

    private func pastCard(_ past: [InjuryBoard]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("History", note: "\(past.count) cleared")
            Card(padding: 0) {
                VStack(spacing: 0) {
                    ForEach(past) { inj in
                        Button { openInjury = inj } label: {
                            ListRow(inj.title,
                                    subtitle: [Dates.monthDay(inj.dateOfInjury), inj.clearedAt.map { "cleared \(Dates.monthDay($0))" }]
                                        .compactMap { $0 }.joined(separator: MP.dot),
                                    symbol: inj.symbol, family: .violet) { EmptyView() }
                        }
                        .buttonStyle(.mpRow)
                        if inj.id != past.last?.id { InsetDivider(leading: 16 + 32 + 12) }
                    }
                }
                .clipShape(MP.surfaceShape)
            }
        }
    }

    private var preventionCard: some View {
        let sport = app.me?.sports?.sport ?? "basketball"
        let lines: [(String, String)] = sport == "soccer"
            ? [("Nordic hamstring curls", "Twice a week in season. The single best-evidenced hamstring protector: about half the strains."),
               ("Copenhagen adduction", "Three sets, twice a week. Groin injuries down by around 40% in the trials."),
               ("Landing and cutting mechanics", "Knee over toes, hips back, soft landings. The ACL prevention programmes (FIFA 11+) run on this.")]
            : sport == "tennis"
            ? [("Shoulder external rotation", "Band work three times a week; keep ER to IR strength above two thirds."),
               ("Hip and trunk rotation", "Range on both sides, and the rotational medicine-ball work that loads it."),
               ("Jump and landing mechanics", "Soft two-foot landings and single-leg control on the serve.")]
            : [("Landing mechanics", "Soft, knee-over-toe, hips back: the ACL prevention programmes cut non-contact tears by about half."),
               ("Nordic hamstring curls", "Twice a week. The best-evidenced hamstring protector there is."),
               ("Ankle balance work", "Single-leg balance and hops on a wobble surface: half the recurrent sprains in the trials."),
               ("Calf and tendon capacity", "Heavy slow calf raises, twice a week. Jumper's knee and Achilles pain start with a capacity gap.")]
        return VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Prevention", note: "what the evidence backs")
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(lines.enumerated()), id: \.offset) { i, line in
                        HStack(alignment: .top, spacing: 12) {
                            Glyph(systemName: "shield.lefthalf.filled", family: .teal)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(line.0).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                Text(line.1.typeset).mpFont(.label).foregroundStyle(MP.muted)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .padding(.horizontal, 16).padding(.vertical, 10)
                        if i < lines.count - 1 { InsetDivider(leading: 16 + 32 + 12) }
                    }
                    HStack(spacing: 8) {
                        EvidencePill(grade: "A")
                        Text("Meta-analyses of neuromuscular prevention programmes.").mpFont(.label).foregroundStyle(MP.muted)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12)
                }
            }
        }
    }
}

// MARK: - The injury in full

struct InjuryDetail: View {
    @Environment(AppModel.self) private var app
    let injury: InjuryBoard
    let availability: String
    var inline: Bool
    var onChange: (InjuryBoard?) -> Void

    @State private var logging: LogMeasureTarget?
    @State private var phoneTest: PhoneTest?
    @State private var openMeasure: MeasureHistory?
    @State private var showRTS = false
    @State private var showSources = false
    @State private var confirmClear = false
    @State private var settingTarget = false
    @State private var target = Date()
    @State private var working = false
    @State private var error: String?

    private var isActive: Bool { injury.status == "active" }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            headerCard.mpRise(0)
            if let read = injury.read, isActive { readCard(read).mpRise(1).id("read") }
            if let ph = injury.phase, !injury.phases.isEmpty { phaseCard(ph).mpRise(1).id("phase") }
            if let rts = injury.rts { rtsCard(rts).mpRise(2).id("rts") }
            if isActive && !injury.focus.isEmpty { focusCard.mpRise(3).id("focus") }
            measuresCard.mpRise(4).id("measures")
            if let pain = injury.pain { painCard(pain).mpRise(5).id("pain") }
            if let prog = injury.sportProgression, !prog.isEmpty { progressionCard(prog).mpRise(6).id("progression") }
            if injury.sources?.isEmpty == false { sourcesCard.mpRise(7).id("sources") }
            if let error { ErrorBanner(text: error) }
        }
        .sheet(item: $logging) { target in
            LogMeasureSheet(injury: injury, target: target) { updated in if let updated { onChange(updated) } }
        }
        .sheet(item: $phoneTest) { test in PhoneTestHost(test: test) { onChange(nil) } }
        .sheet(isPresented: $settingTarget) { targetSheet }
        .navigationDestination(item: $openMeasure) { m in
            MeasureDetailView(injury: injury, measure: m, onLogged: { if let u = $0 { onChange(u) } }, onPhone: { phoneTest = $0 })
        }
        .confirmationDialog("Mark this injury cleared?", isPresented: $confirmClear, titleVisibility: .visible) {
            Button("Mark cleared") { patch(.init(status: "cleared")) }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Your staff decide return-to-play. This closes the plan here and keeps the history.")
        }
        .mpErrorFeedback(error)
    }

    // MARK: Header

    private var headerCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top, spacing: 14) {
                    Glyph(systemName: injury.symbol, family: .violet, size: 44)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(injury.title).mpFont(.ledeMedium).foregroundStyle(MP.ink)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityAddTraits(.isHeader)
                        Text([injury.graft, injury.grade].compactMap { $0 }.joined(separator: MP.dot))
                            .mpFont(.label).foregroundStyle(MP.muted)
                    }
                    Spacer(minLength: 0)
                    if isActive { AvailabilityPill(status: availability) } else { StatusPill(text: "Cleared", tone: .low) }
                }
                HStack(spacing: 12) {
                    Stat(label: injury.anchor == "surgery" ? "Since surgery" : "Since injury", value: injury.weeksText)
                    Stat(label: "Day", value: "\(injury.days)")
                    if let t = injury.targetReturnDate {
                        Stat(label: "Target", value: Dates.monthDay(t))
                    } else if let c = injury.clearedAt {
                        Stat(label: "Cleared", value: Dates.monthDay(c))
                    }
                }
                if let s = injury.summary {
                    Text(s.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let n = injury.note, !n.isEmpty {
                    Text("“\(n)”").mpFont(.copy).foregroundStyle(MP.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let c = injury.clinician, !c.isEmpty {
                    Text("Under \(c)").mpFont(.label).foregroundStyle(MP.muted)
                }
                if isActive {
                    HStack(spacing: 10) {
                        Button { target = injury.targetReturnDate.flatMap(Dates.parse) ?? Date(); settingTarget = true } label: {
                            Label(injury.targetReturnDate == nil ? "Set a target date" : "Change target", systemImage: "calendar")
                        }
                        .buttonStyle(MPButtonStyle(kind: .gray)).controlSize(.small)
                        Button { confirmClear = true } label: { Label("Mark cleared", systemImage: "checkmark.seal") }
                            .buttonStyle(MPButtonStyle(kind: .gray)).controlSize(.small)
                        if working { ProgressView().controlSize(.small) }
                    }
                }
            }
        }
    }

    private var targetSheet: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 16) {
                Text("When are you aiming to be back?").title(MPSize.displayS)
                Text("A target, not a promise: the gates still decide. Your staff see it on the roster.")
                    .mpFont(.copy).foregroundStyle(MP.body)
                DatePicker("Target return", selection: $target, in: Date()..., displayedComponents: .date)
                    .datePickerStyle(.graphical).tint(MP.brand)
                PrimaryButton(title: "Save target", icon: "checkmark") {
                    settingTarget = false
                    patch(.init(targetReturnDate: Dates.dayString(target)))
                }
                Spacer()
            }
            .padding(.horizontal, 22).padding(.top, 8)
            .ambientScreen()
            .navigationTitle("Target date")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { settingTarget = false }.mpFont(.copyLargeMedium) }
            }
        }
        .presentationDetents([.large])
    }

    private func patch(_ body: APIClient.InjuryPatch) {
        working = true
        error = nil
        Task {
            defer { working = false }
            do {
                let r = try await app.api.sportsUpdateInjury(id: injury.id, body)
                if let updated = (r.rehab.active + r.rehab.past).first(where: { $0.id == injury.id }) {
                    onChange(updated)
                }
                onChange(nil)
                await app.refreshSports(startDay: false)
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }

    // MARK: The read

    /// The coach's read of the plan: the phase, the gate that matters, this week.
    private func readCard(_ read: InjuryRead) -> some View {
        Card(tint: true) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    IconTile("sparkles", family: .indigo)
                    Text("Where this stands").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        .accessibilityAddTraits(.isHeader)
                    Spacer()
                    Text(read.provider == nil || read.provider == "fallback" ? "from your numbers" : "your coach")
                        .mpFont(.label).mpSecondary()
                }
                Text(read.headline.typeset).mpFont(.ledeMedium).foregroundStyle(MP.ink).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                Text(read.read.typeset).mpFont(.copy).foregroundStyle(MP.ink).lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: Phase

    private func phaseCard(_ ph: CurrentPhase) -> some View {
        let final = ph.number >= ph.of
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Phase \(ph.number) of \(ph.of)").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                .accessibilityAddTraits(.isHeader)
                            Text("\(ph.name)\(MP.dot)\(ph.window)").mpFont(.label).foregroundStyle(MP.muted)
                        }
                        Spacer()
                        if ph.override != nil {
                            Text("Set by staff").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                        } else if ph.total > 0 {
                            Text("\(ph.met) of \(ph.total) gates").font(.figuresLabel)
                                .foregroundStyle(ph.met == ph.total ? MP.riskLow : MP.ink)
                        }
                    }
                    PhaseStepper(phases: injury.phases, current: ph.number, total: ph.of, showsCaption: false)
                }
                .padding(16)
                if !ph.goals.isEmpty {
                    InsetDivider(leading: 16)
                    VStack(alignment: .leading, spacing: 6) {
                        Text(final ? "The work from here" : "What this phase is for").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        ForEach(Array(ph.goals.enumerated()), id: \.offset) { _, g in
                            HStack(alignment: .top, spacing: 8) {
                                LimeDot(size: 6).padding(.top, 7)
                                Text(g.typeset).mpFont(.copy).foregroundStyle(MP.ink)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12)
                }
                if !ph.avoid.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Hold off on").mpFont(.labelMedium).foregroundStyle(MP.riskMed)
                        FlowTags(ph.avoid)
                    }
                    .padding(.horizontal, 16).padding(.bottom, 12)
                }
                if !ph.criteria.isEmpty {
                    InsetDivider(leading: 16)
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(ph.number < ph.of ? "To move to phase \(ph.number + 1)" : "To be cleared")
                                .mpFont(.labelMedium).foregroundStyle(MP.muted)
                            Spacer()
                            Text("\(ph.met) of \(ph.total) met").font(.figuresLabel).foregroundStyle(ph.met == ph.total ? MP.riskLow : MP.ink)
                        }
                        Text(ph.met == ph.total ? "Every gate for this phase is met. The time floor and your staff decide the step."
                             : "Each gate is a measurement against a published cut-off; log the measure and it re-reads.")
                            .mpFont(.label).foregroundStyle(MP.muted).padding(.bottom, 4)
                            .fixedSize(horizontal: false, vertical: true)
                        ForEach(ph.criteria) { c in
                            Button {
                                if c.measureKey != "__days", let m = injury.measures.first(where: { $0.key == c.measureKey }) {
                                    openMeasure = m
                                }
                            } label: { CriterionRow(criterion: c) }
                                .buttonStyle(.plain)
                                .disabled(c.measureKey == "__days")
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12)
                } else if final {
                    InsetDivider(leading: 16)
                    Text("No gates are left in this phase. The work now is keeping the next one from happening.")
                        .mpFont(.label).foregroundStyle(MP.muted)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16).padding(.vertical, 12)
                }
            }
        }
    }

    // MARK: Return to sport

    private func rtsCard(_ rts: RTSRead) -> some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("Return to sport").mpFont(.copyLargeMedium).foregroundStyle(MP.ink).accessibilityAddTraits(.isHeader)
                        Spacer()
                        Text("\(rts.met) of \(rts.total) criteria").font(.figuresLabel).foregroundStyle(MP.body)
                    }
                    GeometryReader { proxy in
                        ZStack(alignment: .leading) {
                            MP.capsuleShape.fill(MP.track)
                            MP.capsuleShape.fill(rts.met == rts.total ? MP.riskLow : MP.brand)
                                .frame(width: proxy.size.width * CGFloat(rts.met) / CGFloat(max(rts.total, 1)))
                        }
                    }
                    .frame(height: 8)
                    .accessibilityHidden(true)
                    Text(rts.total > 0 && rts.met == rts.total
                         ? "Every return criterion is met. Clearance and minutes are your staff's call."
                         : injury.targetReturnDate != nil
                         ? "Target \(ProfileView.displayDate(rts.projected)), set by you or your staff."
                         : "Projected \(ProfileView.displayDate(rts.projected)), from the typical window and the criteria met so far.")
                        .mpFont(.copy).foregroundStyle(MP.ink).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    if rts.window.count == 2 {
                        Text("Typical window \(Dates.monthDay(rts.window[0])) to \(Dates.monthDay(rts.window[1])) (\(rts.typicalWeeks.first ?? 0) to \(rts.typicalWeeks.last ?? 0) weeks).")
                            .mpFont(.label).foregroundStyle(MP.muted)
                    }
                    if rts.known < rts.total {
                        Text("\(rts.total - rts.known) of the criteria have no measurement yet.")
                            .mpFont(.label).foregroundStyle(MP.muted)
                    }
                }
                .padding(16)
                Button { withAnimation(MPMotion.layout) { showRTS.toggle() } } label: {
                    HStack(spacing: 6) {
                        Text(showRTS ? "Hide the criteria" : "See the criteria").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                        Image(systemName: "chevron.down").font(.systemGlyphs(10, weight: .semibold)).foregroundStyle(MP.brandInk)
                            .rotationEffect(.degrees(showRTS ? 180 : 0))
                    }
                    .padding(.horizontal, 16).padding(.bottom, 12)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                if showRTS {
                    InsetDivider(leading: 16)
                    VStack(spacing: 0) {
                        ForEach(rts.criteria) { c in
                            Button {
                                if let m = injury.measures.first(where: { $0.key == c.measureKey }) { openMeasure = m }
                            } label: { CriterionRow(criterion: c) }
                                .buttonStyle(.plain)
                                .disabled(c.measureKey == "__days")
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 8)
                    if !rts.reinjuryNote.isEmpty {
                        Text(rts.reinjuryNote.typeset).mpFont(.label).foregroundStyle(MP.muted).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 16).padding(.bottom, 14)
                    }
                }
            }
        }
    }

    // MARK: Focus

    private var focusCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("This week", note: (injury.phase.map { $0.number >= $0.of } ?? false) ? "the prevention block" : "what moves the next gate")
            ForEach(injury.focus) { f in
                Card {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .top, spacing: 12) {
                            Glyph(systemName: f.kind == "time" ? "clock" : f.kind == "block" ? "hand.raised" : "target", family: .teal, size: 36)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(f.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                    .fixedSize(horizontal: false, vertical: true)
                                Text(f.why.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer(minLength: 0)
                        }
                        ForEach(Array(f.actions.enumerated()), id: \.offset) { _, a in
                            HStack(alignment: .top, spacing: 8) {
                                LimeDot(size: 6).padding(.top, 7)
                                Text(a.typeset).mpFont(.copy).foregroundStyle(MP.ink)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        if let key = f.measureKey, f.kind == "measure" {
                            Button { logging = LogMeasureTarget(measureKey: key) } label: {
                                Label(f.missing == true ? "Log it" : "Log a new result", systemImage: "square.and.pencil")
                            }
                            .buttonStyle(MPButtonStyle(kind: .gray)).controlSize(.small)
                        }
                    }
                }
            }
        }
    }

    // MARK: Measures

    private var measuresCard: some View {
        let logged = injury.measures.filter(\.logged)
        let unlogged = injury.measures.filter { !$0.logged }
        return VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Measures", note: "\(logged.count) of \(injury.measures.count) logged",
                         actionTitle: isActive ? "Log" : nil) { logging = LogMeasureTarget() }
            Card(padding: 0) {
                VStack(spacing: 0) {
                    ForEach(logged) { m in
                        Button { openMeasure = m } label: { MeasureRow(measure: m) }
                            .buttonStyle(.mpRow)
                        if m.id != logged.last?.id { InsetDivider(leading: 16 + 32 + 12) }
                    }
                    if logged.isEmpty {
                        EmptyRow(icon: "ruler", title: "Nothing measured yet",
                                 detail: "Your staff's numbers land here; a few you can do on the phone.")
                    }
                    if !unlogged.isEmpty && isActive {
                        InsetDivider(leading: 16)
                        Button { logging = LogMeasureTarget() } label: {
                            HStack {
                                Text("\(unlogged.count) not yet measured: " + unlogged.prefix(3).map(\.label).joined(separator: ", ") + (unlogged.count > 3 ? "…" : ""))
                                    .mpFont(.label).foregroundStyle(MP.muted).lineLimit(2).multilineTextAlignment(.leading)
                                Spacer()
                                Text("Log").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                            }
                            .padding(.horizontal, 16).padding(.vertical, 10)
                        }
                        .buttonStyle(.mpRow)
                    }
                }
                .clipShape(MP.surfaceShape)
            }
            if isActive {
                let phones = injury.measures.filter(\.phone)
                if !phones.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            Text("On the phone").mpFont(.labelMedium).foregroundStyle(MP.muted)
                            ForEach(phones) { m in
                                Button(m.label) { phoneTest = phoneFlow(for: m) }
                                    .buttonStyle(MPButtonStyle(kind: .gray)).controlSize(.small)
                                    .disabled(phoneFlow(for: m) == nil)
                            }
                        }
                        .padding(.horizontal, 4)
                    }
                    .scrollClipDisabled()
                }
            }
        }
    }

    private func phoneFlow(for m: MeasureHistory) -> PhoneTest? {
        switch m.key {
        case "single_leg_cmj": return .jump(testKey: "single_leg_cmj", side: injury.side ?? "left")
        case "single_leg_balance_s": return .balance
        case "reaction_time": return .reaction
        case "knee_flexion", "knee_extension_deficit", "hamstring_ake", "hip_ir_rom", "thomas_test", "shoulder_ir":
            return .angle(measureKey: m.key, injuryId: injury.id)
        default: return nil
        }
    }

    private func painCard(_ pain: PainRead) -> some View {
        Card {
            HStack(alignment: .top, spacing: 12) {
                Glyph(systemName: "bolt.heart", family: .violet, size: 36)
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Pain").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Spacer()
                        Text("\(String(format: "%.0f", pain.value))/10").font(.figuresCopyLarge)
                            .foregroundStyle(pain.value > 5 ? MP.riskHigh : pain.value > 2 ? MP.riskMed : MP.riskLow)
                    }
                    Text("Logged \(Dates.agoWords(pain.date)). The rule for loading a sore tendon or joint: up to 2 during, up to 5 after, back to usual by the next morning. Above that, the session was too much.")
                        .mpFont(.label).foregroundStyle(MP.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func progressionCard(_ steps: [String]) -> some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardTitleRow("Back to the sport, in order", note: "each step earned")
                ForEach(Array(steps.enumerated()), id: \.offset) { i, s in
                    HStack(alignment: .top, spacing: 12) {
                        Text("\(i + 1)").font(.figuresLabel).foregroundStyle(MP.brandInk)
                            .frame(width: 22, height: 22).background(Circle().fill(MP.brandTint))
                        Text(s.typeset).mpFont(.copy).foregroundStyle(MP.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 6)
                }
                Spacer().frame(height: 10)
            }
        }
    }

    private var sourcesCard: some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                Button { withAnimation(MPMotion.layout) { showSources.toggle() } } label: {
                    HStack {
                        Text("Where the gates come from").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Spacer()
                        Image(systemName: "chevron.down").font(.systemGlyphs(12, weight: .semibold)).foregroundStyle(MP.muted)
                            .rotationEffect(.degrees(showSources ? 180 : 0))
                    }
                    .padding(16).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                if showSources {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array((injury.sources ?? []).enumerated()), id: \.offset) { _, s in
                            Text(s.typeset).mpFont(.label).foregroundStyle(MP.muted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if let retest = injury.retest, !retest.isEmpty {
                            Text("Retest after clearance: " + retest.joined(separator: ", "))
                                .mpFont(.label).foregroundStyle(MP.muted).padding(.top, 4)
                        }
                    }
                    .padding(.horizontal, 16).padding(.bottom, 16)
                }
            }
        }
    }
}

/// Wrapping tags for the "not yet" list.
struct FlowTags: View {
    let items: [String]
    init(_ items: [String]) { self.items = items }
    var body: some View {
        FlowChipsStatic(items: items)
    }
}

private struct FlowChipsStatic: View {
    let items: [String]
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 6) { tags }
            VStack(alignment: .leading, spacing: 6) { tags }
        }
    }
    private var tags: some View {
        ForEach(items, id: \.self) { t in
            Text(t).mpFont(.label).foregroundStyle(MP.body)
                .padding(.horizontal, 10).padding(.vertical, 5)
                .background(MP.capsuleShape.fill(MP.panel))
                .overlay(MP.capsuleShape.strokeBorder(MP.line, lineWidth: 1))
        }
    }
}

/// One measure in the list: glyph, label, the involved side's latest against
/// the other, the symmetry, the date.
struct MeasureRow: View {
    let measure: MeasureHistory

    var body: some View {
        HStack(spacing: 12) {
            Glyph(systemName: measure.symbol, family: measure.phone ? .teal : .violet)
            VStack(alignment: .leading, spacing: 3) {
                Text(measure.label).mpFont(.copyLargeMedium).foregroundStyle(MP.ink).lineLimit(1)
                HStack(spacing: 6) {
                    if let d = measure.latestDate { Text(Dates.agoWords(d).sentenceCased).mpFont(.label).foregroundStyle(MP.muted) }
                    if let lsi = measure.lsi {
                        Text("LSI \(String(format: "%.0f", lsi))%").mpFont(.label)
                            .foregroundStyle(lsi >= 90 ? MP.riskLow : lsi >= 80 ? MP.riskMed : MP.riskHigh)
                    }
                    if measure.phone { Text("phone").mpFont(.label).foregroundStyle(MP.brandInk) }
                }
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 2) {
                RowFigure(value: measure.latest.map { fmt($0) } ?? "—", unit: measure.unit)
                if measure.sided, let u = measure.uninvolvedLatest {
                    Text("other \(fmt(u))").mpFont(.label).foregroundStyle(MP.muted)
                }
            }
            Image(systemName: "chevron.right")
                .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                .accessibilityHidden(true)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    private func fmt(_ v: Double) -> String { String(format: "%.\(measure.decimals)f", v) }
}

// MARK: - Measure detail

struct MeasureDetailView: View {
    @Environment(AppModel.self) private var app
    let injury: InjuryBoard
    let measure: MeasureHistory
    var onLogged: (InjuryBoard?) -> Void
    var onPhone: (PhoneTest) -> Void
    @State private var logging: LogMeasureTarget?

    private var spec: MeasureSpec? { app.sportsCatalog?.measures[measure.key] }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Card {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .firstTextBaseline) {
                            BigFigure(value: measure.latest.map { fmt($0) } ?? "—", unit: measure.unit, size: MPSize.displayM)
                            Spacer()
                            if let lsi = measure.lsi {
                                StatusPill(text: "LSI \(String(format: "%.0f", lsi))%", tone: lsi >= 90 ? .low : lsi >= 80 ? .med : .high)
                            }
                        }
                        Text([measure.latestDate.map { "Logged \(Dates.agoWords($0))" }, measure.sided ? "involved side" : nil]
                            .compactMap { $0 }.joined(separator: MP.dot))
                            .mpFont(.label).foregroundStyle(MP.muted)
                        if let mdc = spec?.mdc {
                            Text("A change smaller than \(fmt(mdc)) \(measure.unit) is inside measurement error.")
                                .mpFont(.label).foregroundStyle(MP.muted)
                        }
                    }
                }
                if measure.sided {
                    Card {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Involved against uninvolved").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            SymmetryBar(left: measure.latest, right: measure.uninvolvedLatest, leftLabel: "Involved", rightLabel: "Other",
                                        unit: measure.unit, decimals: measure.decimals, higherIsBetter: measure.higherIsBetter, flagPct: 10)
                            Text("The limb symmetry index is the involved side as a share of the other. 90% is the usual return gate; some gates ask more.")
                                .mpFont(.label).foregroundStyle(MP.muted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                if measure.involved.count > 1 || measure.uninvolved.count > 1 {
                    Card {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Text("Over time").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                Spacer()
                                if measure.sided {
                                    HStack(spacing: 10) {
                                        legend("Involved", MP.chartS1)
                                        legend("Other", MP.chartS2)
                                    }
                                }
                            }
                            TestSeriesChart(points: measure.involved, second: measure.sided ? measure.uninvolved : [],
                                            secondLabel: "Other", unit: measure.unit)
                        }
                    }
                }
                Card {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("How it is measured").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text(measure.protocol_.typeset).mpFont(.copy).foregroundStyle(MP.ink).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Why it matters").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        Text(measure.why.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                if injury.status == "active" {
                    VStack(spacing: 10) {
                        PrimaryButton(title: "Log a result", icon: "square.and.pencil") { logging = LogMeasureTarget(measureKey: measure.key) }
                        if measure.phone, let flow = phoneFlow {
                            SecondaryButton(title: "Do it on the phone", icon: "iphone") { onPhone(flow) }
                        }
                    }
                }
                SportsGuardrail()
            }
            .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
        }
        .ambientScreen()
        .mpNavigationTitle(measure.label, short: "Measure")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $logging) { target in LogMeasureSheet(injury: injury, target: target, onSaved: onLogged) }
    }

    private var phoneFlow: PhoneTest? {
        switch measure.key {
        case "single_leg_cmj": return .jump(testKey: "single_leg_cmj", side: injury.side ?? "left")
        case "single_leg_balance_s": return .balance
        case "reaction_time": return .reaction
        case "knee_flexion", "knee_extension_deficit", "hamstring_ake", "hip_ir_rom", "thomas_test", "shoulder_ir":
            return .angle(measureKey: measure.key, injuryId: injury.id)
        default: return nil
        }
    }

    private func legend(_ text: String, _ color: Color) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(text).mpFont(.label).foregroundStyle(MP.muted)
        }
        .accessibilityHidden(true)
    }

    private func fmt(_ v: Double) -> String { String(format: "%.\(measure.decimals)f", v) }
}

// MARK: - Logging a measure

struct LogMeasureTarget: Identifiable {
    let id = UUID()
    var measureKey: String? = nil
}

/// Type a measure: both sides for a sided one, a grade or a yes/no for the
/// scored ones, a number for the rest.
struct LogMeasureSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let injury: InjuryBoard
    let target: LogMeasureTarget
    var onSaved: (InjuryBoard?) -> Void

    @State private var picked: MeasureHistory?
    @State private var involved = ""
    @State private var uninvolved = ""
    @State private var value = ""
    @State private var choice: AnswerValue?
    @State private var date = Date()
    @State private var saving = false
    @State private var saved = false
    @State private var error: String?
    @FocusState private var focus: Bool

    private var spec: MeasureSpec? { picked.flatMap { app.sportsCatalog?.measures[$0.key] } }

    private var canSave: Bool {
        guard let picked, !saving else { return false }
        switch picked.kind {
        case "yes_no", "grade": return choice != nil
        default:
            if picked.sided { return Double(involved) != nil || Double(uninvolved) != nil }
            return Double(value) != nil
        }
    }

    var body: some View {
        NavigationStack {
            Group {
                if let picked { form(picked) } else { picker }
            }
            .ambientScreen()
            .navigationTitle(picked == nil ? "Which measure?" : "Log a measure")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium) }
                if picked != nil && !saved && target.measureKey == nil {
                    ToolbarItem(placement: .topBarTrailing) { Button("Change") { picked = nil }.mpFont(.copyLargeMedium) }
                }
            }
            .onAppear {
                if let key = target.measureKey { picked = injury.measures.first { $0.key == key } }
            }
            .mpCompletionFeedback(saved)
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    private var picker: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Card(padding: 0) {
                    VStack(spacing: 0) {
                        ForEach(injury.measures) { m in
                            Button { picked = m; focus = true } label: {
                                HStack(spacing: 12) {
                                    Glyph(systemName: m.symbol, family: m.phone ? .teal : .violet)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(m.label).mpFont(.copyLargeMedium).foregroundStyle(MP.ink).multilineTextAlignment(.leading)
                                        Text([m.unit.isEmpty ? nil : m.unit, m.sided ? "each side" : nil, m.logged ? "logged" : "not yet"]
                                            .compactMap { $0 }.joined(separator: MP.dot))
                                            .mpFont(.label).foregroundStyle(MP.muted)
                                    }
                                    Spacer(minLength: 8)
                                    Image(systemName: "chevron.right")
                                        .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                                        .accessibilityHidden(true)
                                }
                                .padding(.horizontal, 16).padding(.vertical, 10)
                            }
                            .buttonStyle(.mpRow)
                            if m.id != injury.measures.last?.id { InsetDivider(leading: 16 + 32 + 12) }
                        }
                    }
                    .clipShape(MP.surfaceShape)
                }
            }
            .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
        }
    }

    private func form(_ m: MeasureHistory) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(m.label).title(MPSize.displayS)
                Text(m.protocol_.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                if saved {
                    Card(tint: true) {
                        HStack(spacing: 10) {
                            Image(systemName: "checkmark.seal.fill").foregroundStyle(MP.riskLow)
                            Text("Logged. The gates re-read.").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        }
                    }
                    PrimaryButton(title: "Done") { dismiss() }
                } else {
                    switch m.kind {
                    case "yes_no":
                        WrapChips(options: ["1", "0"], labels: ["1": "Yes", "0": "No"], value: $choice)
                    case "grade":
                        let lo = Int(m.lo ?? 0), hi = Int(m.hi ?? 4)
                        WrapChips(options: (lo...hi).map(String.init),
                                  labels: Dictionary(uniqueKeysWithValues: (lo...hi).map { (String($0), "Grade \($0)") }), value: $choice)
                    default:
                        if m.sided {
                            HStack(spacing: 10) {
                                numberField("Involved\(injury.side.map { " (\($0))" } ?? "")", text: $involved, unit: m.unit)
                                numberField("Other side", text: $uninvolved, unit: m.unit)
                            }
                        } else {
                            numberField("Result", text: $value, unit: m.unit)
                        }
                        if let lo = m.lo, let hi = m.hi {
                            Text("Usually between \(fmt(lo, m)) and \(fmt(hi, m)) \(m.unit).").mpFont(.label).foregroundStyle(MP.muted)
                        }
                    }
                    Card(padding: 0) {
                        DatePicker("Day", selection: $date, in: ...Date(), displayedComponents: .date)
                            .datePickerStyle(.compact)
                            .mpFont(.copyLarge).foregroundStyle(MP.ink)
                            .padding(.horizontal, 16).padding(.vertical, 6)
                    }
                    if let error { ErrorBanner(text: error) }
                    PrimaryButton(title: "Save", icon: "checkmark", loading: saving, disabled: !canSave) { save(m) }
                }
            }
            .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func fmt(_ v: Double, _ m: MeasureHistory) -> String { String(format: "%.\(m.decimals)f", v) }

    private func numberField(_ label: String, text: Binding<String>, unit: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).mpFont(.labelMedium).foregroundStyle(MP.muted).lineLimit(1)
            HStack(spacing: 8) {
                TextField(label, text: text, prompt: Text("0").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle()).keyboardType(.decimalPad).focused($focus)
                Text(unit).mpFont(.copyMedium).foregroundStyle(MP.muted).frame(minWidth: 24)
            }
        }
    }

    private func save(_ m: MeasureHistory) {
        saving = true
        error = nil
        let day = Dates.dayString(date)
        var entries: [APIClient.MeasureEntry] = []
        switch m.kind {
        case "yes_no", "grade":
            if let c = choice?.stringValue, let v = Double(c) {
                entries.append(.init(measureKey: m.key, value: v, side: m.sided ? "involved" : nil, date: day, source: "app", note: nil))
            }
        default:
            if m.sided {
                if let v = Double(involved) { entries.append(.init(measureKey: m.key, value: v, side: "involved", date: day, source: "app", note: nil)) }
                if let v = Double(uninvolved) { entries.append(.init(measureKey: m.key, value: v, side: "uninvolved", date: day, source: "app", note: nil)) }
            } else if let v = Double(value) {
                entries.append(.init(measureKey: m.key, value: v, side: nil, date: day, source: "app", note: nil))
            }
        }
        Task {
            defer { saving = false }
            do {
                let r = try await app.api.sportsLogMeasures(injuryId: injury.id, entries)
                onSaved(r.injury)
                saved = true
                await app.refreshSports(startDay: false)
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

// MARK: - Reporting an injury

/// Pick the injury from the sport's list, say which side and when, and the
/// plan starts from the right phase.
struct ReportInjurySheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    var onSaved: (RehabBoard) -> Void

    @State private var query = ""
    @State private var picked: InjurySummary?
    @State private var side = "none"
    @State private var dateOfInjury = Date()
    @State private var surgical = false
    @State private var dateOfSurgery = Date()
    @State private var graft: AnswerValue?
    @State private var grade: AnswerValue?
    @State private var mechanism = ""
    @State private var clinician = ""
    @State private var note = ""
    @State private var saving = false
    @State private var error: String?

    private var injuries: [InjurySummary] {
        let all = app.sportsCatalog?.injuries ?? []
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        return q.isEmpty ? all : all.filter { $0.label.lowercased().contains(q) || $0.bodyRegion.contains(q) }
    }

    private static let regionOrder = ["knee", "ankle", "hamstring", "groin", "hip", "thigh", "calf", "foot", "shin", "back", "shoulder", "elbow", "wrist", "hand", "head", "core"]

    private var grouped: [(String, [InjurySummary])] {
        let regions = Array(Set(injuries.map(\.bodyRegion))).sorted {
            (Self.regionOrder.firstIndex(of: $0) ?? 99) < (Self.regionOrder.firstIndex(of: $1) ?? 99)
        }
        return regions.map { r in (r, injuries.filter { $0.bodyRegion == r }) }
    }

    var body: some View {
        NavigationStack {
            Group {
                if let picked { form(picked) } else { picker }
            }
            .ambientScreen()
            .navigationTitle(picked == nil ? "What happened?" : "Report an injury")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium) }
                if picked != nil {
                    ToolbarItem(placement: .topBarTrailing) { Button("Change") { picked = nil }.mpFont(.copyLargeMedium) }
                }
            }
            .task {
                if app.sportsCatalog == nil, let sport = app.me?.sports?.sport {
                    app.sportsCatalog = try? await app.api.sportsCatalog(sport: sport)
                }
            }
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    private var picker: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                SportsSearchField(text: $query, placeholder: "Search injuries")
                ForEach(grouped, id: \.0) { region, items in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(region.capitalized).mpFont(.labelMedium).foregroundStyle(MP.muted).padding(.horizontal, 4)
                        Card(padding: 0) {
                            VStack(spacing: 0) {
                                ForEach(items) { inj in
                                    Button {
                                        picked = inj
                                        surgical = inj.surgical && inj.grafts.isEmpty == false
                                        side = "none"
                                        graft = nil
                                        grade = nil
                                    } label: {
                                        HStack(spacing: 12) {
                                            Glyph(systemName: inj.symbol, family: .violet)
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(inj.label).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                                    .multilineTextAlignment(.leading)
                                                Text("Typically \(inj.typicalReturnWeeks.first ?? 0) to \(inj.typicalReturnWeeks.last ?? 0) weeks")
                                                    .mpFont(.label).foregroundStyle(MP.muted)
                                            }
                                            Spacer(minLength: 8)
                                            Image(systemName: "chevron.right")
                                                .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                                                .accessibilityHidden(true)
                                        }
                                        .padding(.horizontal, 16).padding(.vertical, 10)
                                    }
                                    .buttonStyle(.mpRow)
                                    if inj.id != items.last?.id { InsetDivider(leading: 16 + 32 + 12) }
                                }
                            }
                            .clipShape(MP.surfaceShape)
                        }
                    }
                }
                if grouped.isEmpty {
                    Card { EmptyRow(icon: "magnifyingglass", title: "No injury matches", detail: "Try the body part.") }
                }
            }
            .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func form(_ inj: InjurySummary) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(inj.label).title(MPSize.displayS)
                Text(inj.summary.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                VStack(alignment: .leading, spacing: 8) {
                    Text("Which side").mpFont(.labelMedium).foregroundStyle(MP.muted)
                    WrapChips(options: ["left", "right", "none"], labels: ["left": "Left", "right": "Right", "none": "Not sided"],
                              value: Binding(get: { .string(side) }, set: { if let s = $0?.stringValue { side = s } }))
                }
                Card(padding: 0) {
                    VStack(spacing: 0) {
                        DatePicker("When it happened", selection: $dateOfInjury, in: ...Date(), displayedComponents: .date)
                            .datePickerStyle(.compact).mpFont(.copyLarge).foregroundStyle(MP.ink)
                            .padding(.horizontal, 16).padding(.vertical, 6)
                        if inj.surgical {
                            InsetDivider(leading: 16)
                            Toggle(isOn: $surgical) {
                                Text("Had surgery").mpFont(.copyLarge).foregroundStyle(MP.ink)
                            }
                            .tint(MP.brand)
                            .padding(.horizontal, 16).padding(.vertical, 10)
                            if surgical {
                                InsetDivider(leading: 16)
                                DatePicker("Surgery date", selection: $dateOfSurgery, in: ...Date(), displayedComponents: .date)
                                    .datePickerStyle(.compact).mpFont(.copyLarge).foregroundStyle(MP.ink)
                                    .padding(.horizontal, 16).padding(.vertical, 6)
                            }
                        }
                    }
                }
                if surgical && !inj.grafts.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Graft").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        WrapChips(options: inj.grafts, labels: Dictionary(uniqueKeysWithValues: inj.grafts.map { ($0, $0) }), value: $graft)
                    }
                }
                if !inj.grades.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Grade").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        WrapChips(options: inj.grades, labels: Dictionary(uniqueKeysWithValues: inj.grades.map { ($0, $0) }), value: $grade)
                    }
                }
                TextField("How it happened (optional)", text: $mechanism, prompt: Text("How it happened (optional)").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle())
                TextField("Treating clinician (optional)", text: $clinician, prompt: Text("Treating clinician (optional)").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle()).textContentType(.name)
                TextField("Note (optional)", text: $note, prompt: Text("Note (optional)").foregroundColor(MP.muted), axis: .vertical)
                    .lineLimit(1...4).textFieldStyle(FieldStyle())
                if let error { ErrorBanner(text: error) }
                PrimaryButton(title: "Start the plan", icon: "cross.case.fill", loading: saving) { save(inj) }
                Text(inj.reinjuryNote.typeset).mpFont(.label).foregroundStyle(MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func save(_ inj: InjurySummary) {
        saving = true
        error = nil
        let body = APIClient.InjuryBody(
            injuryKey: inj.key, side: side == "none" ? nil : side, dateOfInjury: Dates.dayString(dateOfInjury),
            dateOfSurgery: surgical ? Dates.dayString(dateOfSurgery) : nil,
            graft: graft?.stringValue, grade: grade?.stringValue,
            mechanism: mechanism.isEmpty ? nil : mechanism, clinician: clinician.isEmpty ? nil : clinician,
            note: note.isEmpty ? nil : note, targetReturnDate: nil)
        Task {
            defer { saving = false }
            do {
                let r = try await app.api.sportsReportInjury(body)
                onSaved(r.rehab)
                dismiss()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}
