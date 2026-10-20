import Charts
import SwiftUI

/// Game recovery, not injury: readiness and why, how the athlete says they
/// feel against their own month, what to do about it, the overnight
/// readouts, the training load, the schedule, and the health watches.
struct RecoveryView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var board: RecoveryBoard?
    @State private var error: String?
    @State private var expanded: Set<String> = ["readiness"]
    @State private var showWellness = false
    @State private var loggingSession = false
    @State private var showLoadMethod = false

    private static let overnight = ["sleep", "hrv", "resting_hr", "body", "rhythm"]
    private static let training = ["fitness", "activity"]

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let board {
                        verdictCard(board).mpRise(0)
                        wellnessCard(board.wellness).mpRise(1).id("wellness")
                        if !board.suggestions.isEmpty { suggestions(board.suggestions).mpRise(2).id("suggestions") }
                        overnight(board).mpRise(3).id("overnight")
                        training(board).mpRise(4).id("training")
                        scheduleCard(board.schedule).mpRise(5).id("schedule")
                        healthWatches(board).mpRise(6).id("health")
                    } else if let error {
                        ErrorBanner(text: error)
                        SecondaryButton(title: "Try again", icon: "arrow.clockwise") { Task { await load() } }
                    } else {
                        LoadingCard()
                    }
                    SportsGuardrail()
                }
                .padding(.horizontal, 18).padding(.top, 2).padding(.bottom, 28)
            }
            .refreshable { await load() }
            .mpHardScrollEdge()
            .ambientScreen()
            .mpNavigationTitle("Recovery")
            .navigationBarTitleDisplayMode(.inline)
            .sheet(isPresented: $showWellness) { WellnessSheet() }
            .sheet(isPresented: $loggingSession) { SportsSessionSheet() }
            .onChange(of: showWellness) { _, on in if !on { Task { await load() } } }
            .onChange(of: loggingSession) { _, on in if !on { Task { await load() } } }
            .task {
                if board == nil { await load() }
                #if DEBUG
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
            board = try await app.api.sportsRecovery()
            error = nil
        } catch {
            if board == nil { self.error = AppModel.message(for: error) }
        }
    }

    private func binding(for key: String) -> Binding<Bool> {
        Binding(get: { expanded.contains(key) },
                set: { on in if on { expanded.insert(key) } else { expanded.remove(key) } })
    }

    // MARK: Verdict

    private func verdictCard(_ board: RecoveryBoard) -> some View {
        let v = board.verdict
        return Card {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .center, spacing: 18) {
                    ReadinessRing(score: v.score, band: board.readiness.string("band"), size: 112)
                    VStack(alignment: .leading, spacing: 8) {
                        StatusPill(text: v.title, tone: v.tone)
                        Text(v.reason.typeset).mpFont(.copyLargeMedium).foregroundStyle(MP.ink).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(v.detail.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                let others = v.reasons.filter { $0 != v.reason }
                if !others.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("What decided it").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        ForEach(Array(others.enumerated()), id: \.offset) { _, r in
                            HStack(alignment: .top, spacing: 8) {
                                LimeDot(size: 6).padding(.top, 7)
                                Text(r.typeset).mpFont(.copy).foregroundStyle(MP.ink)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
                if let avail = board.availability, avail != "available" {
                    HStack(spacing: 8) {
                        AvailabilityPill(status: avail)
                        Text("Your staff's status. The readiness read is still yours.").mpFont(.label).foregroundStyle(MP.muted)
                    }
                }
            }
        }
    }

    // MARK: Wellness

    private func wellnessCard(_ w: WellnessPanel) -> some View {
        let columns = dynamicTypeSize.isAccessibilitySize
            ? [GridItem(.flexible(), spacing: 8)]
            : [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)]
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 12) {
                    IconTile("face.smiling", family: .blue)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("How you feel").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            .accessibilityAddTraits(.isHeader)
                        Text(w.answeredToday > 0 ? "Today\(MP.dot)\(w.answeredToday) answers" :
                                w.latestDate.map { "Last \(Dates.agoWords($0))" } ?? "Nothing yet")
                            .mpFont(.label).foregroundStyle(MP.muted)
                    }
                    Spacer(minLength: 8)
                    StatusPill(text: w.statusText, tone: w.tone)
                }
                .padding(16)
                if w.answeredToday == 0 {
                    VStack(alignment: .leading, spacing: 8) {
                        PrimaryButton(title: "Morning check-in", icon: "face.smiling") { showWellness = true }
                        Text("Six sliders, a minute. Each answer is scored against your own four weeks.")
                            .mpFont(.label).foregroundStyle(MP.muted)
                    }
                    .padding(.horizontal, 16).padding(.bottom, 14)
                }
                if !w.items.isEmpty {
                    LazyVGrid(columns: columns, spacing: 8) {
                        ForEach(w.items) { item in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 5) {
                                    Image(systemName: item.symbol).font(.systemGlyphs(11, weight: .medium))
                                        .foregroundStyle(MP.muted).accessibilityHidden(true)
                                    Text(item.label).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1).minimumScaleFactor(0.75)
                                    Spacer(minLength: 0)
                                    Circle().fill(MP.foreground(item.state.statusTone)).frame(width: 6, height: 6)
                                        .accessibilityHidden(true)
                                }
                                HStack(alignment: .firstTextBaseline, spacing: 2) {
                                    Text(String(format: "%.0f", item.value)).font(.figuresLede).foregroundStyle(MP.ink)
                                    Text("/10").mpFont(.label).foregroundStyle(MP.muted)
                                    Spacer(minLength: 4)
                                    if item.series.count > 2 {
                                        Sparkline(values: item.series.suffix(14).map(\.value), width: 40, height: 14)
                                    }
                                }
                                if let z = item.z {
                                    Text(String(format: "%@%.1f SD", z >= 0 ? "+" : "−", abs(z)))
                                        .mpFont(.label).foregroundStyle(MP.foreground(item.state.statusTone))
                                }
                            }
                            .padding(10)
                            .background(MP.controlShape.fill(MP.fill))
                            .accessibilityElement(children: .combine)
                            .accessibilityLabel(Text("\(item.label) \(String(format: "%.0f", item.value)) out of 10, \(item.state == "ok" ? "usual" : item.state == "watch" ? "worth noting" : "well off")"))
                        }
                    }
                    .padding(.horizontal, 12).padding(.bottom, 12)
                }
                if !w.finding.isEmpty {
                    Text(w.finding.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16).padding(.bottom, 12)
                }
                if let h = w.hooper {
                    HStack(spacing: 6) {
                        Text("Hooper index").mpFont(.label).foregroundStyle(MP.muted)
                        Text(String(format: "%.0f", h)).font(.figuresLabel).foregroundStyle(MP.ink)
                        Text("(4 best, 28 worst)").mpFont(.label).foregroundStyle(MP.muted)
                        Spacer()
                        if w.answeredToday > 0 {
                            Button("Edit answers") { showWellness = true }.buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                        }
                    }
                    .padding(.horizontal, 16).padding(.bottom, 12)
                }
                if !w.notes.isEmpty {
                    InsetDivider(leading: 16)
                    ForEach(Array(w.notes.prefix(2).enumerated()), id: \.offset) { _, n in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "quote.opening").font(.systemGlyphs(11)).foregroundStyle(MP.muted)
                                .accessibilityHidden(true)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(n.text.typeset).mpFont(.copy).foregroundStyle(MP.ink)
                                    .fixedSize(horizontal: false, vertical: true)
                                Text(Dates.monthDay(n.date)).mpFont(.label).foregroundStyle(MP.muted)
                            }
                        }
                        .padding(.horizontal, 16).padding(.vertical, 8)
                    }
                    Spacer().frame(height: 6)
                }
            }
        }
    }

    // MARK: Suggestions

    private func suggestions(_ list: [Suggestion]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("What to do about it", note: "\(list.count) today")
            ForEach(list) { s in SuggestionCard(suggestion: s) }
        }
    }

    // MARK: Overnight

    private func overnight(_ board: RecoveryBoard) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Overnight", note: "against your baseline")
            PanelCard(panel: board.readiness, expanded: binding(for: "readiness"))
            ForEach(Self.overnight, id: \.self) { key in
                if let p = board.panel(key) {
                    PanelCard(panel: p, expanded: binding(for: key))
                    if key == "hrv", let cv = board.hrvCv { hrvCvCard(cv) }
                }
            }
        }
    }

    private func hrvCvCard(_ cv: HRVVariability) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("HRV, week to week").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    Spacer()
                    StatusPill(text: cv.status == "ok" ? "Stable" : cv.status == "watch" ? "Shifting" : "Strained",
                               tone: cv.status.statusTone)
                }
                HStack(spacing: 12) {
                    Stat(label: "CV this week", value: String(format: "%.1f", cv.cvWeek), unit: "%")
                    Stat(label: "CV before", value: String(format: "%.1f", cv.cvPrior), unit: "%")
                    Stat(label: "Mean", value: cv.meanState.capitalized)
                    Stat(label: "Spread", value: cv.cvState.capitalized)
                }
                Text(cv.read.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                if cv.saturation {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "info.circle").foregroundStyle(MP.brandInk).accessibilityHidden(true)
                        Text("HRV is high while your heart rate is low: parasympathetic saturation. A further rise is not more recovery, so this read leans on resting heart rate.")
                            .mpFont(.label).foregroundStyle(MP.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Text("The coefficient of variation of nightly ln-RMSSD over 7 days: a widening spread with a falling mean is strain, a tightening spread with a rising mean is adaptation (Flatt and Esco).")
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: Training

    private func training(_ board: RecoveryBoard) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Training load", note: board.load.source ?? "session RPE", actionTitle: "Log") { loggingSession = true }
            loadCard(board.load)
            if let jumps = board.jumps, jumps.week > 0 { jumpsCard(jumps) }
            ForEach(Self.training, id: \.self) { key in
                if let p = board.panel(key) { PanelCard(panel: p, expanded: binding(for: key)) }
            }
        }
    }

    private func loadCard(_ load: LoadRead) -> some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 12) {
                    IconTile("flame.fill", family: .teal)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("This week").mpFont(.copyLargeMedium).foregroundStyle(MP.ink).accessibilityAddTraits(.isHeader)
                        Text(load.lastSession.map { "Last session \(Dates.agoWords($0))" } ?? "No sessions logged")
                            .mpFont(.label).foregroundStyle(MP.muted)
                    }
                    Spacer(minLength: 8)
                    StatusPill(text: load.statusText, tone: load.tone)
                }
                .padding(16)
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(String(format: "%.0f", load.weekLoad))
                        .font(.figuresDisplay(MPSize.displayM)).kerning(-1.4).foregroundStyle(MP.ink)
                        .lineLimit(1).minimumScaleFactor(0.6)
                    Text("AU").mpFont(.copyMedium).foregroundStyle(MP.muted)
                    Spacer(minLength: 8)
                    if let c = load.changePct {
                        Text(String(format: "%@%.0f%% vs your recent weeks", c >= 0 ? "+" : "−", abs(c)))
                            .mpFont(.label).foregroundStyle(MP.foreground(load.tone))
                            .multilineTextAlignment(.trailing)
                    }
                }
                .padding(.horizontal, 16)
                if load.series.count > 1 {
                    Chart(load.series.suffix(28)) { p in
                        BarMark(x: .value("Day", p.day, unit: .day), y: .value("Load", p.value))
                            .foregroundStyle(p.id == load.series.last?.id ? MP.lime : MP.chartS1)
                            .cornerRadius(2)
                    }
                    .chartXAxis {
                        AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                            AxisValueLabel(format: .dateTime.month(.abbreviated).day()).font(.axis).foregroundStyle(MP.chartAxisLabel)
                        }
                    }
                    .chartYAxis {
                        AxisMarks(values: .automatic(desiredCount: 3)) { value in
                            AxisGridLine().foregroundStyle(MP.chartGrid)
                            AxisValueLabel {
                                if let v = value.as(Double.self) {
                                    Text(PanelChart.axisNumber(v)).font(.axis).foregroundStyle(MP.chartAxisLabel)
                                }
                            }
                        }
                    }
                    .frame(height: 96)
                    .padding(.horizontal, 16).padding(.top, 10)
                    .accessibilityHidden(true)
                }
                HStack(spacing: 10) {
                    Stat(label: "Minutes", value: String(format: "%.0f", load.minutesWeek))
                    Stat(label: "Sessions", value: "\(load.sessionsWeek)")
                    Stat(label: "Games", value: "\(load.gamesWeek)")
                    if let m = load.monotony { Stat(label: "Monotony", value: String(format: "%.1f", m), tone: m >= 2 ? .med : nil) }
                    if let a = load.acwr { Stat(label: "A:C", value: String(format: "%.2f", a)) }
                }
                .padding(.horizontal, 16).padding(.top, 12)
                if !load.byKind.isEmpty { kindBar(load.byKind).padding(.horizontal, 16).padding(.top, 10) }
                Text(load.finding.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16).padding(.top, 12)
                Button { withAnimation(MPMotion.layout) { showLoadMethod.toggle() } } label: {
                    HStack(spacing: 6) {
                        Text("How it is computed").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                        Image(systemName: "chevron.down").font(.systemGlyphs(10, weight: .semibold)).foregroundStyle(MP.brandInk)
                            .rotationEffect(.degrees(showLoadMethod ? 180 : 0))
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                if showLoadMethod {
                    Text(load.method.typeset).mpFont(.label).foregroundStyle(MP.muted).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16).padding(.bottom, 12)
                }
            }
            .padding(.bottom, 6)
        }
    }

    private func kindBar(_ byKind: [String: Double]) -> some View {
        let order = ["practice", "game", "match", "lift", "conditioning", "shootaround", "individual", "rehab"]
        let items = order.compactMap { k in byKind[k].map { (k, $0) } } + byKind.filter { !order.contains($0.key) }.map { ($0.key, $0.value) }
        let total = max(items.map(\.1).reduce(0, +), 1)
        let colors = [MP.chartS1, MP.chartS2, MP.catBlue, MP.catViolet, MP.tealGraphic, MP.riskMed, MP.faint, MP.lineStrong]
        return VStack(alignment: .leading, spacing: 6) {
            GeometryReader { proxy in
                HStack(spacing: 2) {
                    ForEach(Array(items.enumerated()), id: \.offset) { i, item in
                        Rectangle().fill(colors[i % colors.count])
                            .frame(width: max(2, proxy.size.width * CGFloat(item.1 / total)))
                    }
                }
                .clipShape(MP.capsuleShape)
            }
            .frame(height: 8)
            HStack(spacing: 10) {
                ForEach(Array(items.prefix(4).enumerated()), id: \.offset) { i, item in
                    HStack(spacing: 4) {
                        Circle().fill(colors[i % colors.count]).frame(width: 6, height: 6)
                        Text("\(item.0.capitalized) \(String(format: "%.0f", item.1 / total * 100))%")
                            .mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
                    }
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text("Load by session kind: " + items.map { "\($0.0) \(String(format: "%.0f", $0.1))" }.joined(separator: ", ")))
    }

    private func jumpsCard(_ j: JumpLoad) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Jump load").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    Spacer()
                    StatusPill(text: j.status == "ok" ? "In range" : j.status == "watch" ? "Rising" : "Spike", tone: j.status.statusTone)
                }
                HStack(spacing: 12) {
                    Stat(label: "This week", value: String(format: "%.0f", j.week), unit: "jumps")
                    if let p = j.priorWeek { Stat(label: "Last week", value: String(format: "%.0f", p)) }
                    if let c = j.changePct { Stat(label: "Change", value: String(format: "%@%.0f%%", c >= 0 ? "+" : "−", abs(c))) }
                    if let m = j.meanSession { Stat(label: "Per session", value: String(format: "%.0f", m)) }
                }
                Text(j.text.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: Schedule

    private func scheduleCard(_ s: ScheduleRead) -> some View {
        let today = Dates.dayString(Date())
        let upcoming = Array(s.upcoming.prefix(8))
        return VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Schedule", note: s.density == "heavy" ? "heavy stretch" : s.density == "light" ? "light stretch" : nil)
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    if !flags(s).isEmpty {
                        HStack(spacing: 6) {
                            ForEach(flags(s), id: \.self) { f in
                                Text(f).mpFont(.labelMedium).foregroundStyle(MP.riskMed)
                                    .padding(.horizontal, 8).padding(.vertical, 3)
                                    .background(MP.capsuleShape.fill(MP.riskMedBg))
                            }
                        }
                        .padding(.horizontal, 16).padding(.top, 14)
                    }
                    if upcoming.isEmpty {
                        EmptyRow(icon: "calendar", title: "Nothing on the calendar",
                                 detail: "Your team's schedule appears here once your staff add it.")
                    }
                    ForEach(upcoming) { e in
                        EventRow(event: e, highlight: e.date == today)
                        if e.id != upcoming.last?.id { InsetDivider(leading: 16) }
                    }
                    if !s.finding.isEmpty {
                        Text(s.finding.typeset).mpFont(.label).foregroundStyle(MP.muted)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 12)
                    } else {
                        Spacer().frame(height: 6)
                    }
                }
            }
        }
    }

    private func flags(_ s: ScheduleRead) -> [String] {
        var out: [String] = []
        if s.gameToday != nil { out.append("Game day") }
        if s.backToBack { out.append("Back-to-back") }
        if s.threeInFour { out.append("3 in 4") }
        if s.travel { out.append("Travel") }
        if s.gameYesterday && s.gameToday == nil { out.append("Day after a game") }
        return out
    }

    // MARK: Health watches

    private func healthWatches(_ board: RecoveryBoard) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Health", note: "quiet until something moves")
            watchCard("Illness watch", symbol: "thermometer.medium", family: .violet,
                      status: board.illness.status, finding: board.illness.finding, lines: board.illness.signals)
            watchCard("Hydration", symbol: "drop.fill", family: .blue,
                      status: board.hydration.status, finding: board.hydration.finding,
                      lines: [board.hydration.urine.map { "Urine shade \(String(format: "%.0f", $0)) of 8 this morning" },
                              board.hydration.massDropPct.map { String(format: "Body mass %.1f%% below your usual", $0) }].compactMap { $0 })
            if let c = board.cycle {
                watchCard("Cycle", symbol: "circle.dotted.and.circle", family: .indigo,
                          status: c.flags.isEmpty ? "ok" : "watch", finding: c.note,
                          lines: [c.phase.map { "\($0.capitalized) phase" + (c.day.map { ", day \($0)" } ?? "") }].compactMap { $0 } + c.flags)
            }
            if let over = board.panel("overreach") { PanelCard(panel: over, expanded: binding(for: "overreach")) }
        }
    }

    private func watchCard(_ title: String, symbol: String, family: MP.Category, status: String, finding: String,
                           lines: [String]) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 12) {
                    Glyph(systemName: symbol, family: family, size: 36)
                    Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink).accessibilityAddTraits(.isHeader)
                    Spacer(minLength: 8)
                    StatusPill(text: status == "ok" ? "Clear" : status == "watch" ? "Watch" : status == "flag" ? "Flag" : "No data",
                               tone: status.statusTone)
                }
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    HStack(alignment: .top, spacing: 8) {
                        LimeDot(size: 6).padding(.top, 7)
                        Text(line.typeset).mpFont(.copy).foregroundStyle(MP.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                if !finding.isEmpty {
                    Text(finding.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}
