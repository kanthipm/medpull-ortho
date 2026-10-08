import SwiftUI

/// Every individual metric a subscriber has, one per row, each opening in
/// full. Two kinds: the readouts the personal engine computes (readiness,
/// HRV balance, sleep need, load...) and the raw signals under them (steps,
/// resting heart rate, sleep duration, SpO2...), grouped the way the
/// hospital app groups them. The home page shows the headline; the Trends
/// tab shows the weekly aggregates; this is where the day-by-day numbers
/// live.
struct PersonalMetricsView: View {
    @Environment(AppModel.self) private var app

    private var board: Dashboard? { app.dashboard?.dashboard }

    private var readouts: [Panel] {
        guard let board else { return [] }
        return board.sections.filter { $0 != "care" }.compactMap { board.panel($0) }
    }

    private var grouped: [(SignalGroup, [PortfolioMetric])] {
        SignalGroup.allCases.compactMap { g in
            let rows = app.portfolio.filter { $0.group == g }
                .sorted { SignalGroup.rank($0.key) < SignalGroup.rank($1.key) }
            return rows.isEmpty ? nil : (g, rows)
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let board {
                    Text([board.asOf == Dates.dayString(Date()) ? "Today" : Dates.shortDay(board.asOf),
                          "\(board.daysWithData) days of data"].joined(separator: MP.dot))
                        .mpFont(.copyLarge).foregroundStyle(MP.body)
                        .padding(.horizontal, 4)
                    readoutsSection
                    if board.sections.contains("care"), let care = app.dashboard?.care {
                        CareSectionCard(section: care)
                    }
                } else {
                    Card {
                        HStack(spacing: 14) {
                            ProgressView().tint(MP.brand)
                            Text("Reading your signals…").mpFont(.copyLarge).foregroundStyle(MP.body)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                if app.portfolio.isEmpty {
                    signalsEmpty
                } else {
                    ForEach(Array(grouped.enumerated()), id: \.element.0) { i, entry in
                        signalSection(entry.0, entry.1).mpRise(i + 1)
                    }
                }
                PersonalGuardrail()
            }
            .padding(.horizontal, 18).padding(.top, 2).padding(.bottom, 28)
        }
        .mpHardScrollEdge()
        .ambientScreen(height: 320)
        .navigationTitle("All metrics")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable {
            await app.refreshDashboard()
            await app.refreshPortfolio(surface: false)
        }
        .task {
            if app.dashboard == nil { await app.refreshDashboard(startDay: true) }
            if app.portfolio.isEmpty { await app.refreshPortfolio(surface: false) }
        }
    }

    // MARK: Readouts

    /// The computed readouts, in the goal's order, each a row that opens
    /// the full card with its chart, numbers and method.
    private var readoutsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Readouts", note: "computed from your baseline")
            Card(padding: 0) {
                VStack(spacing: 0) {
                    ForEach(readouts, id: \.key) { panel in
                        NavigationLink { PanelDetailView(panel: panel) } label: {
                            PanelRow(panel: panel)
                        }
                        .buttonStyle(.mpRow)
                        if panel.key != readouts.last?.key { RowDivider() }
                    }
                }
                .clipShape(MP.surfaceShape)
            }
        }
        .mpRise(0)
    }

    // MARK: Signals

    private func signalSection(_ group: SignalGroup, _ rows: [PortfolioMetric]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle(group.title, note: group.blurb)
            Card(padding: 0) {
                VStack(spacing: 0) {
                    ForEach(rows) { m in
                        NavigationLink { SignalDetailView(metric: m) } label: {
                            SignalRow(metric: m)
                        }
                        .buttonStyle(.mpRow)
                        if m.id != rows.last?.id { RowDivider() }
                    }
                }
                .clipShape(MP.surfaceShape)
            }
        }
    }

    private var signalsEmpty: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Signals")
            Card {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(spacing: 12) {
                        Glyph(systemName: "chart.xyaxis.line", family: .teal, size: 40)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("No raw signals yet").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            Text("Steps, heart rate, sleep and the rest arrive from Apple Health or a wearable.")
                                .mpFont(.copy).foregroundStyle(MP.body)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    if let me = app.me, !me.wearables.appleHealth.connected, me.features.appleHealth {
                        PrimaryButton(title: "Connect Apple Health", icon: "heart.fill") { app.showConnections = true }
                    }
                }
            }
        }
    }
}

/// One readout as a row: glyph, name, the state in words, the figure.
struct PanelRow: View {
    let panel: Panel
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var figure: String {
        guard panel.hasData else { return "—" }
        if panel.key == "readiness", let score = panel.number("score") {
            return String(format: "%.0f", score)
        }
        return panel.headline
    }

    var body: some View {
        let stacked = dynamicTypeSize.isAccessibilitySize
        HStack(alignment: .center, spacing: 12) {
            Glyph(systemName: panel.symbol, family: panel.family)
            VStack(alignment: .leading, spacing: 3) {
                Text(panel.title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if panel.hasData {
                    StateLabel(text: panel.statusText, tone: panel.tone)
                } else {
                    Text(panel.statusText).mpFont(.label).foregroundStyle(MP.muted)
                }
                if stacked { value }
            }
            Spacer(minLength: 8)
            if !stacked {
                if panel.series.count > 1 {
                    Sparkline(values: panel.series.suffix(14).map(\.value), bars: panel.isBar)
                }
                value
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
        .accessibilityLabel(Text("\(panel.title), \(figure) \(panel.unit), \(panel.statusText)"))
    }

    /// The row's unit, in a row's width: "steps/day" is the headline's
    /// unit, but beside a figure in a list "steps" says it.
    private var rowUnit: String? {
        guard panel.hasData, !panel.unit.isEmpty else { return nil }
        return panel.unit.components(separatedBy: "/").first
    }

    private var value: some View {
        RowFigure(value: figure, unit: rowUnit)
            .frame(minWidth: 56, alignment: .trailing)
    }
}

/// One readout in full: the card as the Trends tab opens it, always open,
/// then every day's value under it, newest first, so the individual
/// numbers behind the chart can be read off.
struct PanelDetailView: View {
    let panel: Panel

    private var days: [PanelPoint] { Array(panel.series.suffix(28).reversed()) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                PanelCard(panel: panel)
                if !days.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        SectionTitle("Day by day", note: "last \(days.count) days")
                        Card(padding: 0) {
                            VStack(spacing: 0) {
                                ForEach(days) { point in
                                    HStack {
                                        Text(Dates.shortDay(point.date)).mpFont(.copy).foregroundStyle(MP.ink)
                                        Spacer()
                                        RowFigure(value: PanelChart.format(point.value, panel: panel),
                                                  unit: panel.unit.isEmpty ? nil : panel.unit)
                                    }
                                    .padding(.horizontal, 16).padding(.vertical, 9)
                                    .accessibilityElement(children: .combine)
                                    if point.id != days.last?.id { RowDivider() }
                                }
                            }
                            .clipShape(MP.surfaceShape)
                        }
                    }
                }
                PersonalGuardrail()
            }
            .padding(.horizontal, 18).padding(.top, 4).padding(.bottom, 28)
        }
        .mpHardScrollEdge()
        .ambientScreen(height: 300)
        .navigationTitle(panel.title)
        .navigationBarTitleDisplayMode(.inline)
    }
}

extension Panel: Identifiable {
    public var id: String { key }
}
