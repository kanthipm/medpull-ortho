import SwiftUI

/// "Am I getting better?" First what the care team reads, in the patient's
/// words; then every signal, grouped the way a patient thinks about them
/// (movement, activity, rest, body) as quiet rows with a sparkline. A row
/// opens the whole chart with the explanation behind it.
struct ProgressTab: View {
    @Environment(AppModel.self) private var app
    @State private var showAllMetrics = false
    @State private var path = NavigationPath()
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var grouped: [(SignalGroup, [PortfolioMetric])] {
        SignalGroup.allCases.compactMap { g in
            let rows = app.portfolio.filter { $0.group == g }
                .sorted { SignalGroup.rank($0.key) < SignalGroup.rank($1.key) }
            return rows.isEmpty ? nil : (g, rows)
        }
    }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if let me = app.me { subtitle(me) }
                    if !app.isPersonal { careRead }
                    if app.portfolio.isEmpty {
                        emptyState
                    } else {
                        ForEach(Array(grouped.enumerated()), id: \.element.0) { i, entry in
                            section(entry.0, entry.1).mpRise(i + 1).id(entry.0.rawValue)
                        }
                    }
                    Text("Monitoring signals for your care team — not a diagnosis.")
                        .mpFont(.label).foregroundStyle(MP.muted).padding(.top, 2)
                }
                .padding(.horizontal, 18).padding(.top, 2).padding(.bottom, 28)
            }
            .mpNavigationTitle("Progress")
            .toolbarTitleDisplayMode(.large)
            .mpHardScrollEdge()
            .refreshable {
                await app.refreshPortfolio()
                await app.refreshMetrics()
                await app.refreshMe(surface: false)
            }
            .ambientScreen(height: 360)
            .task {
                if app.portfolio.isEmpty { await app.refreshPortfolio(surface: false) }
                if app.metrics == nil { await app.refreshMetrics(surface: false) }
                #if DEBUG
                // Simulator verification: `-MP_SCROLL rest` scrolls to a group,
                // `-MP_OPEN steps` pushes a signal, `-MP_OPEN M3` a care metric.
                if let target = AppConfig.debugFlag("MP_SCROLL") {
                    try? await Task.sleep(for: .seconds(2))
                    proxy.scrollTo(target, anchor: .top)
                }
                if let key = AppConfig.debugFlag("MP_OPEN") {
                    try? await Task.sleep(for: .seconds(2))
                    if let m = app.portfolio.first(where: { $0.key == key }) { path.append(m) }
                    else if let m = app.metrics?.metrics.first(where: { $0.id == key }) { path.append(m) }
                }
                #endif
            }
            .navigationDestination(for: PortfolioMetric.self) { m in
                SignalDetailView(metric: m, signal: app.metrics?.signal(for: m.key))
            }
            .navigationDestination(for: PatientMetric.self) { m in CareMetricDetailView(metric: m) }
            }
        }
    }

    private func subtitle(_ me: Me) -> some View {
        let days = me.recovery.daysWithData ?? 0
        let parts: [String] = [
            me.patient.isRecovery ? me.patient.postopDay.map { "Day \($0)" } : nil,
            days > 0 ? "\(days) days of data" : "No data yet",
            me.recovery.daysUntilFullPicture.flatMap { $0 > 0 ? "full picture in \($0) \($0 == 1 ? "day" : "days")" : nil },
        ].compactMap { $0 }
        return Text(parts.joined(separator: MP.dot))
            .mpFont(.copyLarge).foregroundStyle(MP.body)
            .padding(.horizontal, 4)
    }

    // MARK: Care team's read

    /// The care metrics the pathway leads with, each a row with its state in
    /// words. The rest fold out. The overall sentence sits on top.
    @ViewBuilder private var careRead: some View {
        let metrics = app.metrics?.metrics ?? []
        let shown = showAllMetrics ? metrics : Array(metrics.prefix(3))
        if !metrics.isEmpty {
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    CardTitleRow("What your care team sees",
                                 note: (app.metrics?.overall.waiting ?? 0) > 0
                                    ? "\(app.metrics?.overall.waiting ?? 0) on the way" : nil)
                    if let blurb = app.metrics?.overall.blurb {
                        Text(blurb.typeset)
                            .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 16).padding(.bottom, 10)
                    }
                    InsetDivider(leading: 16)
                    ForEach(shown) { m in
                        NavigationLink(value: m) { CareMetricRow(metric: m) }
                            .buttonStyle(.mpRow)
                        if m.id != shown.last?.id { RowDivider() }
                    }
                    if metrics.count > 3 {
                        InsetDivider(leading: 16)
                        Button(showAllMetrics ? "Show fewer" : "Show all \(metrics.count)") {
                            withAnimation(MPMotion.gated(MPMotion.layout, reduceMotion: reduceMotion)) {
                                showAllMetrics.toggle()
                            }
                        }
                        .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                        .padding(.horizontal, 16).padding(.vertical, 10)
                    }
                }
                .padding(.bottom, metrics.count > 3 ? 0 : 4)
                .clipShape(MP.surfaceShape)
            }
            .mpRise(0)
        }
    }

    // MARK: Signals

    private func section(_ group: SignalGroup, _ rows: [PortfolioMetric]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle(group.title, note: group == .movement && rows.contains(where: \.isMeasured)
                         ? "phone and watch" : nil)
            Card(padding: 0) {
                VStack(spacing: 0) {
                    ForEach(rows) { m in
                        NavigationLink(value: m) {
                            SignalRow(metric: m, signal: app.metrics?.signal(for: m.key))
                        }
                        .buttonStyle(.mpRow)
                        if m.id != rows.last?.id { RowDivider() }
                    }
                }
                .clipShape(MP.surfaceShape)
            }
        }
    }

    private var emptyState: some View {
        Card {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    Glyph(systemName: "chart.xyaxis.line", family: .teal, size: 40)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Nothing to chart yet").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                        Text("Your signals arrive from Apple Health, a wearable, or a measurement with your phone.")
                            .mpFont(.copy).foregroundStyle(MP.body)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                if let me = app.me, !me.wearables.appleHealth.connected, me.features.appleHealth {
                    PrimaryButton(title: "Connect Apple Health", icon: "heart.fill") { app.showConnections = true }
                }
                if !app.isPersonal {
                    SecondaryButton(title: "Measure a walk with your phone", icon: "figure.walk.motion") {
                        app.selectedTab = .measure
                    }
                }
            }
        }
        .mpRise(1)
    }
}

/// One signal as a row: glyph, name, state in words, a two-week sparkline,
/// the latest reading.
struct SignalRow: View {
    let metric: PortfolioMetric
    var signal: PatientSignal? = nil
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    /// The state in a row's width: the care team's four states, shortened.
    private var stateLine: String {
        if let signal {
            if signal.state == "waiting", let c = signal.daysLeftText {
                return c.hasPrefix("waiting") ? "Waiting on new data" : "Shows in \(c)"
            }
            switch signal.state {
            case "good": return "Steady"
            case "watch": return "Worth watching"
            case "reviewing": return "Team reviewing"
            default: return signal.stateLabel
            }
        }
        return Dates.agoWords(metric.latest.date).prefix(1).uppercased() + Dates.agoWords(metric.latest.date).dropFirst()
    }

    private var tone: MP.Tone? {
        guard let signal, signal.state != "waiting" else { return nil }
        return MP.tone(forMetricState: signal.state)
    }

    var body: some View {
        let stacked = dynamicTypeSize.isAccessibilitySize
        HStack(alignment: .center, spacing: 12) {
            Glyph(systemName: metric.symbol, family: metric.family)
            VStack(alignment: .leading, spacing: 3) {
                Text(metric.displayLabel).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if let tone {
                    StateLabel(text: stateLine, tone: tone)
                } else {
                    Text(stateLine).mpFont(.label).foregroundStyle(MP.muted)
                }
                if stacked { figure }
            }
            Spacer(minLength: 8)
            if !stacked {
                if metric.series.count > 1 {
                    Sparkline(values: metric.series.suffix(14).map(\.value), bars: metric.isDailyTotal)
                }
                figure
            }
            Image(systemName: "chevron.right")
                .font(.systemGlyphs(13, weight: .semibold))
                .foregroundStyle(MP.faint)
                .accessibilityHidden(true)
        }
        .padding(.horizontal, 16).padding(.vertical, 11)
        .frame(minHeight: 56)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text("\(metric.displayLabel), \(metric.spokenText(for: metric.latest.value)), \(stateLine)"))
    }

    private var figure: some View {
        RowFigure(value: metric.latestText, unit: metric.hideUnit ? nil : metric.unit)
            .frame(minWidth: 56, alignment: .trailing)
    }
}

/// One of the care team's metrics as a row: glyph, title, the state in
/// words, and one sentence.
struct CareMetricRow: View {
    let metric: PatientMetric

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Glyph(systemName: metric.symbol, family: metric.family)
            VStack(alignment: .leading, spacing: 3) {
                Text(metric.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
                HStack(alignment: .top, spacing: 5) {
                    Group {
                        if metric.tone == .missing {
                            Circle().strokeBorder(MP.foreground(metric.tone), lineWidth: 1.5)
                        } else {
                            Circle().fill(MP.foreground(metric.tone))
                        }
                    }
                    .frame(width: 6, height: 6)
                    .padding(.top, 5)
                    .accessibilityHidden(true)
                    Text(metric.isWaiting ? (metric.countdown ?? metric.stateLabel) : metric.stateLabel)
                        .mpFont(.label).foregroundStyle(MP.foreground(metric.tone))
                        .fixedSize(horizontal: false, vertical: true)
                        .multilineTextAlignment(.leading)
                }
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.right")
                .font(.systemGlyphs(13, weight: .semibold))
                .foregroundStyle(MP.faint)
                .accessibilityHidden(true)
        }
        .padding(.horizontal, 16).padding(.vertical, 11)
        .frame(minHeight: 52)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}
