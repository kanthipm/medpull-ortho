import Charts
import SwiftUI

/// The athlete's numbers: the weekly jump read, where the core battery
/// sits against the level, left against right, and every test the sport
/// measures, logged by the staff's systems or by the phone itself.
struct PerformanceView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var board: PerformanceBoard?
    @State private var error: String?
    @State private var logging: LogTestTarget?
    @State private var phoneTest: PhoneTest?
    @State private var openCard: TestCard?
    @State private var filter = "all"

    private var catalog: SportsCatalog? { app.sportsCatalog }

    private var levelLine: String {
        let level = app.me?.sports?.levelLabel ?? "your level"
        let sex = app.me?.sports?.sex == "F" ? "women" : app.me?.sports?.sex == "M" ? "men" : nil
        return [level, sex].compactMap { $0 }.joined(separator: MP.dot)
    }

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let board {
                        heroTile(board).mpRise(0)
                        if board.neuromuscular.hasData { neuroCard(board).mpRise(1).id("neuro") }
                        if !board.asymmetries.isEmpty { asymmetryCard(board.asymmetries).mpRise(2).id("asymmetry") }
                        coreCard(board).mpRise(3).id("core")
                        filterRow(board).mpRise(4).id("categories")
                        ForEach(board.categories.filter { filter == "all" || $0.key == filter }) { cat in
                            categorySection(cat).id("cat-\(cat.key)")
                        }
                        phoneCard.mpRise(6).id("phone")
                    } else if let error {
                        ErrorBanner(text: error)
                        SecondaryButton(title: "Try again", icon: "arrow.clockwise") { Task { await load() } }
                    } else {
                        LoadingCard(text: "Reading your tests…")
                    }
                    SportsGuardrail()
                }
                .padding(.horizontal, 18).padding(.top, 2).padding(.bottom, 28)
            }
            .refreshable { await load() }
            .mpHardScrollEdge()
            .ambientScreen()
            .mpNavigationTitle("Stats")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button { logging = LogTestTarget() } label: {
                            Label("Log a test result", systemImage: "square.and.pencil")
                        }
                        Button { phoneTest = .jump(testKey: "phone_jump_height", side: nil) } label: {
                            Label("Phone jump test", systemImage: "figure.jumprope")
                        }
                        Button { phoneTest = .balance } label: {
                            Label("Single-leg balance", systemImage: "figure.stand")
                        }
                        Button { phoneTest = .reaction } label: {
                            Label("Reaction time", systemImage: "bolt.fill")
                        }
                    } label: {
                        Image(systemName: "plus")
                            .font(.systemGlyphs(17, weight: .medium))
                            .foregroundStyle(MP.ink)
                            .frame(width: 44, height: 44)
                            .contentShape(Rectangle())
                    }
                    .accessibilityLabel("Log a test")
                }
            }
            .sheet(item: $logging) { target in
                LogTestSheet(target: target) { board = $0 }
            }
            .sheet(item: $phoneTest) { test in
                PhoneTestHost(test: test) { Task { await load() } }
            }
            .navigationDestination(item: $openCard) { card in
                TestDetailView(card: card, onLogged: { board = $0 }, onPhone: { phoneTest = $0 })
            }
            .task {
                if board == nil { await load() }
                #if DEBUG
                if AppConfig.debugFlag("MP_SHOW") == "logtest" { logging = LogTestTarget() }
                if AppConfig.debugFlag("MP_SHOW") == "jump" { phoneTest = .jump(testKey: "phone_jump_height", side: nil) }
                if let key = AppConfig.debugFlag("MP_OPEN_TEST"), let card = board?.cards[key] { openCard = card }
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
            board = try await app.api.sportsPerformance()
            error = nil
        } catch {
            if board == nil { self.error = AppModel.message(for: error) }
        }
    }

    // MARK: Hero

    private func heroTile(_ board: PerformanceBoard) -> some View {
        let pct = board.overallPercentile
        let bars = board.headline.compactMap { $0.band.map { Double($0.percentile) } }
        return GradientTile(pct == nil ? .lilac : pct! >= 75 ? .sage : .meadow,
                            kicker: "Core battery",
                            value: pct.map { String($0) } ?? "—",
                            unit: pct != nil ? "percentile" : "not yet",
                            side: ("\(board.logged)", "tests on file")) {
            if bars.count > 1 {
                BarsArt(values: bars, height: 92)
            } else {
                ArtGrid().frame(height: 92)
            }
        } caption: {
            VStack(alignment: .leading, spacing: 6) {
                Text(pct.map { "Your logged core tests sit at the \(ordinal($0)) percentile for \(levelLine)." }
                     ?? "Log the core battery and this reads where you sit for \(levelLine).")
                    .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                if !board.recentBests.isEmpty {
                    Text("New best: " + board.recentBests.prefix(2).map { "\($0.label) \($0.latestText) \($0.unit)" }
                            .joined(separator: MP.dot))
                        .mpFont(.label).foregroundStyle(MP.brandInk)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .accessibilityElement(children: .contain)
    }

    private func ordinal(_ n: Int) -> String {
        let suffix: String
        switch n % 100 {
        case 11, 12, 13: suffix = "th"
        default:
            switch n % 10 {
            case 1: suffix = "st"
            case 2: suffix = "nd"
            case 3: suffix = "rd"
            default: suffix = "th"
            }
        }
        return "\(n)\(suffix)"
    }

    // MARK: Jump read

    private func neuroCard(_ board: PerformanceBoard) -> some View {
        let n = board.neuromuscular
        return Button {
            if let card = board.cards["cmj_height"] ?? board.cards["phone_jump_height"] { openCard = card }
        } label: {
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 12) {
                        Glyph(systemName: "figure.jumprope", family: .teal, size: 36)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Weekly jump").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            Text([n.source == "phone" ? "Phone" : "Force plate", n.latestDate.map(Dates.monthDay)]
                                .compactMap { $0 }.joined(separator: MP.dot))
                                .mpFont(.label).foregroundStyle(MP.muted)
                        }
                        Spacer(minLength: 8)
                        StatusPill(text: n.statusText, tone: n.tone)
                    }
                    .padding(16)
                    if !n.signals.isEmpty {
                        InsetDivider(leading: 16)
                        HStack(alignment: .top, spacing: 0) {
                            ForEach(n.signals) { s in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(s.label).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1).minimumScaleFactor(0.8)
                                    Text(s.value).font(.figuresCopyLarge).foregroundStyle(MP.ink).lineLimit(1).minimumScaleFactor(0.7)
                                    Text(String(format: "%@%.0f%% vs %@", s.pct >= 0 ? "+" : "−", abs(s.pct), s.baseline))
                                        .mpFont(.label)
                                        .foregroundStyle(signalColor(s))
                                        .lineLimit(1).minimumScaleFactor(0.8)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .accessibilityElement(children: .combine)
                            }
                        }
                        .padding(.horizontal, 16).padding(.vertical, 12)
                    }
                    if !n.finding.isEmpty {
                        Text(n.finding.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                            .multilineTextAlignment(.leading)
                            .padding(.horizontal, 16).padding(.bottom, 14)
                    }
                }
            }
        }
        .buttonStyle(CardTapStyle())
    }

    private func signalColor(_ s: NeuroSignal) -> Color {
        // Time to takeoff rising is the bad direction; everything else falling.
        let bad = s.label.lowercased().contains("takeoff") ? s.pct >= 8 : s.pct <= -5
        let good = s.label.lowercased().contains("takeoff") ? s.pct <= -5 : s.pct >= 5
        return bad ? MP.riskMed : good ? MP.riskLow : MP.muted
    }

    // MARK: Asymmetry

    private func asymmetryCard(_ flags: [AsymmetryFlag]) -> some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardTitleRow("Left against right", note: "over the flag line")
                ForEach(flags) { f in
                    Button {
                        if let card = board?.cards[f.key] { openCard = card }
                    } label: {
                        HStack(spacing: 12) {
                            Glyph(systemName: "arrow.left.arrow.right", family: .violet)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(f.label).mpFont(.copyLargeMedium).foregroundStyle(MP.ink).lineLimit(1)
                                Text("\(f.asymmetry.weaker.capitalized) weaker\(MP.dot)LSI \(String(format: "%.0f", f.asymmetry.lsi))%")
                                    .mpFont(.label).foregroundStyle(MP.muted)
                            }
                            Spacer(minLength: 8)
                            Text(String(format: "%.0f%%", f.asymmetry.pct))
                                .font(.figuresCopyLarge).foregroundStyle(f.status == "flag" ? MP.riskHigh : MP.riskMed)
                            Image(systemName: "chevron.right")
                                .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                                .accessibilityHidden(true)
                        }
                        .padding(.horizontal, 16).padding(.vertical, 10)
                    }
                    .buttonStyle(.mpRow)
                    if f.id != flags.last?.id { InsetDivider(leading: 16 + 32 + 12) }
                }
            }
            .padding(.bottom, 6)
            .clipShape(MP.surfaceShape)
        }
    }

    // MARK: Core battery

    private func coreCard(_ board: PerformanceBoard) -> some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardTitleRow("Core battery", note: levelLine)
                ForEach(board.headline) { h in
                    Button {
                        if h.logged, let card = board.cards[h.key] {
                            openCard = card
                        } else {
                            logging = LogTestTarget(testKey: h.key)
                        }
                    } label: {
                        HStack(spacing: 12) {
                            Glyph(systemName: categorySymbol(for: h.key), family: categoryFamily(for: h.key))
                            VStack(alignment: .leading, spacing: 3) {
                                Text(h.label).mpFont(.copyLargeMedium).foregroundStyle(MP.ink).lineLimit(1)
                                if h.logged, let band = h.band {
                                    HStack(spacing: 6) {
                                        Text("\(band.word)\(MP.dot)\(ordinal(band.percentile))")
                                            .mpFont(.label).foregroundStyle(MP.muted)
                                        if let t = TrendText.line(h.trend, higherIsBetter: true) {
                                            Text(t.0).mpFont(.label).foregroundStyle(t.1)
                                        }
                                    }
                                } else if h.logged {
                                    Text(h.daysAgo.map { $0 == 0 ? "Today" : "\($0) days ago" } ?? "Logged")
                                        .mpFont(.label).foregroundStyle(MP.muted)
                                } else {
                                    Text(h.phone ? "Not logged\(MP.dot)phone test available" : "Not logged yet")
                                        .mpFont(.label).foregroundStyle(MP.muted)
                                }
                            }
                            Spacer(minLength: 8)
                            if h.logged, let v = h.latestText {
                                RowFigure(value: v, unit: h.unit)
                            } else {
                                Text("Log").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                            }
                            Image(systemName: "chevron.right")
                                .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                                .accessibilityHidden(true)
                        }
                        .padding(.horizontal, 16).padding(.vertical, 10)
                    }
                    .buttonStyle(.mpRow)
                    if h.id != board.headline.last?.id { InsetDivider(leading: 16 + 32 + 12) }
                }
            }
            .padding(.bottom, 6)
            .clipShape(MP.surfaceShape)
        }
    }

    private func categorySymbol(for key: String) -> String {
        guard let cat = catalog?.test(key)?.category else { return "chart.bar.xaxis" }
        return catalog?.categories.first { $0.key == cat }?.symbol ?? "chart.bar.xaxis"
    }

    private func categoryFamily(for key: String) -> MP.Category {
        guard let cat = catalog?.test(key)?.category,
              let f = catalog?.categories.first(where: { $0.key == cat })?.family else { return .teal }
        return family(f)
    }

    private func family(_ s: String) -> MP.Category {
        switch s {
        case "blue": return .blue
        case "indigo": return .indigo
        case "violet": return .violet
        default: return .teal
        }
    }

    // MARK: Categories

    private func filterRow(_ board: PerformanceBoard) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Chip(label: "All", selected: filter == "all") { filter = "all" }
                ForEach(board.categories) { c in
                    Chip(label: c.cards.isEmpty ? c.label : "\(c.label) \(c.cards.count)", selected: filter == c.key) {
                        filter = filter == c.key ? "all" : c.key
                    }
                }
            }
            .padding(.horizontal, 4).padding(.vertical, 2)
        }
        .scrollClipDisabled()
    }

    private func categorySection(_ cat: PerformanceCategory) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle(cat.label, note: cat.cards.isEmpty ? "nothing logged" : "\(cat.cards.count) logged",
                         actionTitle: cat.available.isEmpty ? nil : "Log") {
                logging = LogTestTarget(category: cat.key)
            }
            if cat.cards.isEmpty {
                Card {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Tests in this group").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        Text(cat.available.map(\.label).joined(separator: MP.dot))
                            .mpFont(.copy).foregroundStyle(MP.body)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            } else {
                Card(padding: 0) {
                    VStack(spacing: 0) {
                        ForEach(cat.cards) { card in
                            Button { openCard = card } label: { TestRow(card: card, symbol: cat.symbol, family: cat.categoryFamily) }
                                .buttonStyle(.mpRow)
                            if card.id != cat.cards.last?.id { InsetDivider(leading: 16 + 32 + 12) }
                        }
                        if !cat.available.isEmpty {
                            InsetDivider(leading: 16)
                            Button { logging = LogTestTarget(category: cat.key) } label: {
                                HStack {
                                    Text("\(cat.available.count) more to log").mpFont(.label).foregroundStyle(MP.muted)
                                    Spacer()
                                    Text("Log one").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                                }
                                .padding(.horizontal, 16).padding(.vertical, 10)
                            }
                            .buttonStyle(.mpRow)
                        }
                    }
                    .clipShape(MP.surfaceShape)
                }
            }
        }
    }

    // MARK: Phone tests

    private var phoneCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Tests on the phone", note: "no equipment")
            Card(padding: 0) {
                VStack(spacing: 0) {
                    phoneRow("Jump height", "Hold the phone to your chest and jump. Flight time gives the height.",
                             symbol: "figure.jumprope", family: .teal) {
                        phoneTest = .jump(testKey: "phone_jump_height", side: nil)
                    }
                    InsetDivider(leading: 16 + 32 + 12)
                    phoneRow("Single-leg balance", "Stand on one leg, phone at your chest. Sway and seconds, each side.",
                             symbol: "figure.stand", family: .violet) { phoneTest = .balance }
                    InsetDivider(leading: 16 + 32 + 12)
                    phoneRow("Reaction time", "Tap when the screen turns. Five goes, the median counts.",
                             symbol: "bolt.fill", family: .blue) { phoneTest = .reaction }
                    InsetDivider(leading: 16 + 32 + 12)
                    phoneRow("Joint angle", "Knee, hip or ankle range with the phone on the limb, each side.",
                             symbol: "figure.flexibility", family: .indigo) { phoneTest = .angle(measureKey: nil, injuryId: nil) }
                }
                .clipShape(MP.surfaceShape)
            }
        }
    }

    private func phoneRow(_ title: String, _ detail: String, symbol: String, family: MP.Category,
                          action: @escaping () -> Void) -> some View {
        Button(action: action) {
            ListRow(title, subtitle: detail, symbol: symbol, family: family) { EmptyView() }
        }
        .buttonStyle(.mpRow)
    }
}

/// One test in a category list: the glyph, the label, where it sits, the
/// figure. A sided test shows the two sides and the gap.
struct TestRow: View {
    let card: TestCard
    var symbol: String
    var family: MP.Category

    var body: some View {
        HStack(spacing: 12) {
            Glyph(systemName: symbol, family: family)
            VStack(alignment: .leading, spacing: 3) {
                Text(card.label).mpFont(.copyLargeMedium).foregroundStyle(MP.ink).lineLimit(1)
                HStack(spacing: 6) {
                    if let band = card.band {
                        Text(band.word).mpFont(.label).foregroundStyle(MP.muted)
                    } else if card.sided, let a = card.asymmetry {
                        Text("\(String(format: "%.0f", a.pct))% apart")
                            .mpFont(.label).foregroundStyle(card.asymmetryStatus == "ok" ? MP.muted : MP.riskMed)
                    } else if let d = card.daysAgo {
                        Text(d == 0 ? "Today" : d == 1 ? "Yesterday" : "\(d) days ago").mpFont(.label).foregroundStyle(MP.muted)
                    }
                    if let t = TrendText.line(card.trend, higherIsBetter: card.higherIsBetter) {
                        Text(t.0).mpFont(.label).foregroundStyle(t.1)
                    }
                    if card.isBest {
                        Text("Best").mpFont(.labelMedium).foregroundStyle(MP.brandInk)
                    }
                }
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 2) {
                RowFigure(value: card.latestText, unit: card.unit)
                if card.sided, let l = card.left?.latest, let r = card.right?.latest {
                    Text("L \(fmt(l))\(MP.dot)R \(fmt(r))").mpFont(.label).foregroundStyle(MP.muted)
                } else if card.series.count > 2 {
                    Sparkline(values: card.series.suffix(12).map(\.value), width: 52, height: 16)
                }
            }
            Image(systemName: "chevron.right")
                .font(.systemGlyphs(13, weight: .semibold)).foregroundStyle(MP.muted)
                .accessibilityHidden(true)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    private func fmt(_ v: Double) -> String { String(format: "%.\(card.decimals)f", v) }
}

// MARK: - Detail

/// One test in full: the figure and its date, the band against the level,
/// the series with the athlete's own baseline, left against right, how it
/// is measured, and the way to log the next one.
struct TestDetailView: View {
    @Environment(AppModel.self) private var app
    let card: TestCard
    var onLogged: (PerformanceBoard) -> Void
    var onPhone: (PhoneTest) -> Void
    @State private var logging: LogTestTarget?
    @State private var showProtocol = false

    private var spec: TestSpec? { app.sportsCatalog?.test(card.key) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                headerCard
                if let band = card.band { bandCard(band) }
                if card.series.count > 1 || (card.left?.series.count ?? 0) > 1 { chartCard }
                if card.sided { sidesCard }
                if let base = card.baseline { baselineCard(base) }
                if let spec { aboutCard(spec) }
                VStack(spacing: 10) {
                    PrimaryButton(title: "Log a result", icon: "square.and.pencil") { logging = LogTestTarget(testKey: card.key) }
                    if card.phone, let test = phoneFlow {
                        SecondaryButton(title: "Do it on the phone", icon: "iphone") { onPhone(test) }
                    }
                }
                SportsGuardrail()
            }
            .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
        }
        .ambientScreen()
        .mpNavigationTitle(card.label, short: "Test")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $logging) { target in LogTestSheet(target: target, onSaved: onLogged) }
    }

    private var phoneFlow: PhoneTest? {
        switch card.key {
        case "phone_jump_height": return .jump(testKey: card.key, side: nil)
        case "single_leg_cmj": return .jump(testKey: card.key, side: "left")
        case "single_leg_balance": return .balance
        case "reaction_time": return .reaction
        case "hamstring_ake", "hip_internal_rotation", "ankle_dorsiflexion_ktw": return .angle(measureKey: nil, injuryId: nil)
        default: return nil
        }
    }

    private var headerCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .top) {
                    BigFigure(value: card.latestText, unit: card.unit, size: MPSize.displayM)
                    Spacer()
                    if let band = card.band {
                        StatusPill(text: band.word, tone: band.percentile >= 75 ? .low : band.percentile >= 40 ? .brand : .med)
                    } else if card.isBest {
                        StatusPill(text: "Personal best", tone: .low)
                    }
                }
                Text([card.latestDate.map { "Logged \(Dates.agoWords($0))" },
                      card.device ?? card.source.map { $0.replacingOccurrences(of: "_", with: " ").capitalized }]
                    .compactMap { $0 }.joined(separator: MP.dot))
                    .mpFont(.label).foregroundStyle(MP.muted)
                HStack(spacing: 16) {
                    if let best = card.bestText {
                        Stat(label: "Best", value: best, unit: card.unit)
                    }
                    Stat(label: "Logged", value: "\(card.count)", unit: card.count == 1 ? "time" : "times")
                    if let t = TrendText.line(card.trend, higherIsBetter: card.higherIsBetter) {
                        Stat(label: "Trend", value: t.0.components(separatedBy: " ").first ?? "", tone: t.1 == MP.riskLow ? .low : t.1 == MP.riskMed ? .med : nil)
                    }
                }
            }
        }
    }

    private func bandCard(_ band: Benchmark) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Against the level").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    Spacer()
                    Text("\(band.percentile)th percentile").font(.figuresLabel).foregroundStyle(MP.body)
                }
                BenchmarkBar(band: band)
                Text("Marks are the 25th, 50th, 75th and 90th percentiles for \(referenceLabel(band.reference)): \(fmt(band.p25)), \(fmt(band.p50)), \(fmt(band.p75)) and \(fmt(band.p90)) \(card.unit).")
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
                if let note = spec?.benchmarkNote, !note.isEmpty {
                    Text(note.typeset).mpFont(.label).foregroundStyle(MP.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func referenceLabel(_ ref: String) -> String {
        let bits = ref.split(separator: ":")
        let level = app.sportsCatalog?.levels.first { $0.key == String(bits.first ?? "") }?.label ?? String(bits.first ?? "")
        let sex = bits.count > 1 ? (bits[1] == "F" ? "women" : "men") : nil
        return [level, sex].compactMap { $0 }.joined(separator: " ")
    }

    private var chartCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Over time").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    Spacer()
                    if card.sided {
                        HStack(spacing: 10) {
                            legend("Left", MP.chartS1)
                            legend("Right", MP.chartS2)
                        }
                    } else if card.baseline != nil {
                        legend("Baseline", MP.chartRefLine)
                    }
                }
                if card.sided {
                    TestSeriesChart(points: card.left?.series ?? [], second: card.right?.series ?? [],
                                    secondLabel: "Right", unit: card.unit)
                } else {
                    TestSeriesChart(points: card.series, unit: card.unit, reference: card.baseline?.baselineMean)
                }
            }
        }
    }

    private func legend(_ text: String, _ color: Color) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(text).mpFont(.label).foregroundStyle(MP.muted)
        }
        .accessibilityHidden(true)
    }

    private var sidesCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Left against right").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    Spacer()
                    if let a = card.asymmetry {
                        StatusPill(text: "LSI \(String(format: "%.0f", a.lsi))%",
                                   tone: card.asymmetryStatus == "ok" ? .low : card.asymmetryStatus == "flag" ? .high : .med)
                    }
                }
                SymmetryBar(left: card.left?.latest, right: card.right?.latest, unit: card.unit, decimals: card.decimals,
                            higherIsBetter: card.higherIsBetter, flagPct: spec?.asymmetryFlagPct)
                if let flag = spec?.asymmetryFlagPct {
                    Text("The flag line for this test is \(String(format: "%.0f", flag))% apart. Below it, the difference is inside normal day-to-day variation.")
                        .mpFont(.label).foregroundStyle(MP.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func baselineCard(_ base: TestBaseline) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 10) {
                Text("Against your own baseline").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                HStack(spacing: 12) {
                    Stat(label: "Baseline", value: fmt(base.baselineMean), unit: card.unit)
                    Stat(label: "Latest", value: String(format: "%@%.1f%%", base.pct >= 0 ? "+" : "−", abs(base.pct)),
                         tone: base.pct <= -(spec?.asymmetryFlagPct ?? 10) / 2 ? .med : base.pct >= 5 ? .low : nil)
                    Stat(label: "z", value: String(format: "%.1f", base.z))
                    if let swc = base.swc { Stat(label: "SWC", value: fmt(swc), unit: card.unit) }
                }
                Text("The baseline is your mean over the six weeks before the latest test (\(base.n) tests). SWC is the smallest worthwhile change, half a standard deviation: a move inside it is noise.")
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func aboutCard(_ spec: TestSpec) -> some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                Button { withAnimation(MPMotion.layout) { showProtocol.toggle() } } label: {
                    HStack {
                        Text("How it is measured").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Spacer()
                        Image(systemName: "chevron.down")
                            .font(.systemGlyphs(12, weight: .semibold)).foregroundStyle(MP.muted)
                            .rotationEffect(.degrees(showProtocol ? 180 : 0))
                            .accessibilityHidden(true)
                    }
                    .padding(16)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityHint(showProtocol ? "Collapse" : "Expand")
                if showProtocol {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(spec.protocol_.typeset).mpFont(.copy).foregroundStyle(MP.ink).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Why it matters").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        Text(spec.why.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                        if !spec.devices.isEmpty {
                            Text("Usually from: " + spec.devices.joined(separator: ", "))
                                .mpFont(.label).foregroundStyle(MP.muted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(.horizontal, 16).padding(.bottom, 16)
                }
            }
        }
    }

    private func fmt(_ v: Double) -> String { String(format: "%.\(card.decimals)f", v) }
}

// MARK: - Logging a result

struct LogTestTarget: Identifiable {
    let id = UUID()
    var testKey: String? = nil
    var category: String? = nil
}

/// Pick a test, type the number. A sided test takes both sides at once;
/// the date defaults to today; the source says where the number came from.
struct LogTestSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let target: LogTestTarget
    var onSaved: (PerformanceBoard) -> Void

    @State private var query = ""
    @State private var picked: TestSpec?
    @State private var value = ""
    @State private var left = ""
    @State private var right = ""
    @State private var sidesMode = "both"     // both | left | right
    @State private var date = Date()
    @State private var source = "manual"
    @State private var device = ""
    @State private var note = ""
    @State private var saving = false
    @State private var error: String?
    @State private var saved = false
    @FocusState private var focus: Bool

    private var catalog: SportsCatalog? { app.sportsCatalog }

    private var tests: [TestSpec] {
        let all = catalog?.tests ?? []
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        var list = all
        if let cat = target.category, q.isEmpty { list = list.filter { $0.category == cat } }
        if !q.isEmpty { list = list.filter { $0.label.lowercased().contains(q) || $0.category.contains(q) } }
        return list
    }

    private var grouped: [(SportsCategory, [TestSpec])] {
        (catalog?.categories ?? []).compactMap { c in
            let items = tests.filter { $0.category == c.key }
            return items.isEmpty ? nil : (c, items)
        }
    }

    private var sources: [(String, String)] {
        [("manual", "Typed in"), ("staff", "Staff"), ("force_plate", "Force plate"), ("timing_gates", "Timing gates"),
         ("dynamometer", "Dynamometer"), ("tracker", "Tracker")]
    }

    private var canSave: Bool {
        guard let picked, !saving else { return false }
        if picked.sided {
            switch sidesMode {
            case "left": return Double(left) != nil
            case "right": return Double(right) != nil
            default: return Double(left) != nil && Double(right) != nil
            }
        }
        return Double(value) != nil
    }

    var body: some View {
        NavigationStack {
            Group {
                if let picked { form(picked) } else { picker }
            }
            .ambientScreen()
            .navigationTitle(picked == nil ? "Which test?" : "Log a result")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.mpFont(.copyLargeMedium)
                }
                if picked != nil && !saved && target.testKey == nil {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Change") { picked = nil }.mpFont(.copyLargeMedium)
                    }
                }
            }
            .task {
                if catalog == nil, let sport = app.me?.sports?.sport {
                    app.sportsCatalog = try? await app.api.sportsCatalog(sport: sport)
                }
                if let key = target.testKey, let spec = catalog?.test(key) ?? app.sportsCatalog?.test(key) { picked = spec }
            }
            .mpCompletionFeedback(saved)
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
    }

    private var picker: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                SportsSearchField(text: $query, placeholder: "Search tests")
                if grouped.isEmpty {
                    Card { EmptyRow(icon: "magnifyingglass", title: "No test matches", detail: "Try part of the name.") }
                }
                ForEach(grouped, id: \.0.key) { cat, items in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(cat.label).mpFont(.labelMedium).foregroundStyle(MP.muted).padding(.horizontal, 4)
                        Card(padding: 0) {
                            VStack(spacing: 0) {
                                ForEach(items) { t in
                                    Button { picked = t; focus = true } label: {
                                        HStack(spacing: 12) {
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(t.label).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                                    .multilineTextAlignment(.leading)
                                                Text([t.unit.isEmpty ? nil : t.unit, t.sided ? "each side" : nil, t.phone ? "phone" : nil, t.core ? "core" : nil]
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
                                    if t.id != items.last?.id { InsetDivider(leading: 16) }
                                }
                            }
                            .clipShape(MP.surfaceShape)
                        }
                    }
                }
            }
            .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func form(_ spec: TestSpec) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(spec.label).title(MPSize.displayS)
                Text(spec.protocol_.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                if saved {
                    Card(tint: true) {
                        HStack(spacing: 10) {
                            Image(systemName: "checkmark.seal.fill").foregroundStyle(MP.riskLow)
                            Text("Logged.").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        }
                    }
                    PrimaryButton(title: "Done") { dismiss() }
                } else {
                    if spec.sided {
                        WrapChips(options: ["both", "left", "right"],
                                  labels: ["both": "Both sides", "left": "Left only", "right": "Right only"],
                                  value: Binding(get: { .string(sidesMode) }, set: { if let s = $0?.stringValue { sidesMode = s } }))
                        HStack(spacing: 10) {
                            if sidesMode != "right" { numberField("Left", text: $left, unit: spec.unit) }
                            if sidesMode != "left" { numberField("Right", text: $right, unit: spec.unit) }
                        }
                    } else {
                        numberField("Result", text: $value, unit: spec.unit)
                    }
                    Card(padding: 0) {
                        VStack(spacing: 0) {
                            DatePicker("Day", selection: $date, in: ...Date(), displayedComponents: .date)
                                .datePickerStyle(.compact)
                                .mpFont(.copyLarge).foregroundStyle(MP.ink)
                                .padding(.horizontal, 16).padding(.vertical, 6)
                        }
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Where it came from").mpFont(.labelMedium).foregroundStyle(MP.muted)
                        WrapChips(options: sources.map(\.0), labels: Dictionary(uniqueKeysWithValues: sources),
                                  value: Binding(get: { .string(source) }, set: { if let s = $0?.stringValue { source = s } }))
                        if source != "manual" {
                            TextField("Device (optional)", text: $device,
                                      prompt: Text(spec.devices.first.map { "Device, e.g. \($0)" } ?? "Device (optional)").foregroundColor(MP.muted))
                                .textFieldStyle(FieldStyle()).autocorrectionDisabled()
                        }
                    }
                    TextField("Note (optional)", text: $note, prompt: Text("Note (optional)").foregroundColor(MP.muted), axis: .vertical)
                        .lineLimit(1...4).textFieldStyle(FieldStyle())
                    if let error { ErrorBanner(text: error) }
                    PrimaryButton(title: "Save", icon: "checkmark", loading: saving, disabled: !canSave) { save(spec) }
                }
            }
            .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func numberField(_ label: String, text: Binding<String>, unit: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).mpFont(.labelMedium).foregroundStyle(MP.muted)
            HStack(spacing: 8) {
                TextField(label, text: text, prompt: Text("0").foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle())
                    .keyboardType(.decimalPad)
                    .focused($focus)
                Text(unit).mpFont(.copyMedium).foregroundStyle(MP.muted).frame(minWidth: 28)
            }
        }
    }

    private func save(_ spec: TestSpec) {
        saving = true
        error = nil
        var entries: [APIClient.TestEntry] = []
        let day = Dates.dayString(date)
        let dev = device.trimmingCharacters(in: .whitespaces)
        let n = note.trimmingCharacters(in: .whitespacesAndNewlines)
        func entry(_ v: Double, side: String?) -> APIClient.TestEntry {
            .init(testKey: spec.key, value: v, side: side, date: day, source: source,
                  device: dev.isEmpty ? nil : dev, note: n.isEmpty ? nil : n)
        }
        if spec.sided {
            if sidesMode != "right", let l = Double(left) { entries.append(entry(l, side: "left")) }
            if sidesMode != "left", let r = Double(right) { entries.append(entry(r, side: "right")) }
        } else if let v = Double(value) {
            entries.append(entry(v, side: nil))
        }
        Task {
            defer { saving = false }
            do {
                let r = try await app.api.sportsLogTests(entries)
                onSaved(r.performance)
                saved = true
                await app.refreshSports(startDay: false)
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }
}

/// A capsule search field in the sports screens (the onboarding one is
/// private to its file).
struct SportsSearchField: View {
    @Binding var text: String
    let placeholder: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.systemGlyphs(15, weight: .medium)).foregroundStyle(MP.muted)
                .accessibilityHidden(true)
            TextField(placeholder, text: $text, prompt: Text(placeholder).foregroundStyle(MP.muted))
                .mpFont(.copyLarge).foregroundStyle(MP.ink)
                .autocorrectionDisabled()
                .submitLabel(.search)
            if !text.isEmpty {
                Button { text = "" } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.systemGlyphs(17)).foregroundStyle(MP.muted)
                        .frame(width: 44, height: 44).contentShape(Rectangle())
                }
                .accessibilityLabel("Clear search")
                .padding(.trailing, -12)
            }
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 48)
        .background(MP.capsuleShape.fill(MP.panel))
        .overlay(MP.capsuleShape.strokeBorder(MP.lineStrong, lineWidth: 1))
    }
}
