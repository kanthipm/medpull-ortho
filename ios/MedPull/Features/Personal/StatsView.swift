import Charts
import SwiftUI

/// Every readout, built to be read fast: a glance grid of today's numbers,
/// this week against last, thirteen weeks of trend, then each panel as a
/// row that opens into its chart, numbers and method. Readiness starts
/// open; everything else starts closed. For a recovery goal the clinic
/// engine's own metrics (M1–M18) sit where the goal puts them.
struct StatsView: View {
    @Environment(AppModel.self) private var app
    @State private var dive: DeepDive?
    @State private var loadingDive: String?
    @State private var expanded: Set<String> = ["readiness"]
    @State private var error: String?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private static let dives: [(String, String, String)] = [
        ("recovery", "Recovery", "waveform.path.ecg"),
        ("training", "Training", "flame.fill"),
        ("sleep", "Sleep", "bed.double.fill"),
        ("weekly", "The week", "calendar"),
    ]

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if let response = app.dashboard {
                            glance(response.dashboard, proxy: proxy)
                            if let week = response.dashboard.week { WeekCard(week: week) { open("weekly") }.id("week") }
                            if let trends = response.dashboard.trends, !trends.isEmpty { TrendsCard(trends: trends).id("trends") }
                            divesRow
                            ForEach(response.dashboard.sections, id: \.self) { key in
                                if key == "care" {
                                    if let care = response.care { CareSectionCard(section: care).id("care") }
                                } else if let panel = response.dashboard.panel(key) {
                                    PanelCard(panel: panel, expanded: binding(for: key)).id(key)
                                }
                            }
                        } else if app.paywall == nil {
                            Card {
                                HStack(spacing: 14) {
                                    ProgressView().tint(MP.brand)
                                    Text("Reading your signals…").mpFont(.copyLarge).foregroundStyle(MP.body)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                        if let error { ErrorBanner(text: error) }
                        PersonalGuardrail()
                    }
                    .padding(.horizontal, 18).padding(.top, 4).padding(.bottom, 24)
                }
                .mpNavigationTitle("Stats")
                .toolbarTitleDisplayMode(.large)
                .mpHardScrollEdge()
                .refreshable { await app.refreshDashboard() }
                .ambientScreen()
                .mpErrorFeedback(error)
                .task {
                    if app.dashboard == nil { await app.refreshDashboard(startDay: true) }
                    #if DEBUG
                    if let target = AppConfig.debugFlag("MP_SCROLL") {
                        try? await Task.sleep(for: .seconds(2))
                        expanded.insert(target)
                        proxy.scrollTo(target, anchor: .top)
                    }
                    #endif
                }
                .sheet(item: $dive) { d in DeepDiveSheet(dive: d) }
            }
        }
    }

    private func binding(for key: String) -> Binding<Bool> {
        Binding(get: { expanded.contains(key) },
                set: { on in if on { expanded.insert(key) } else { expanded.remove(key) } })
    }

    private var gridColumns: [GridItem] {
        let n = dynamicTypeSize.isAccessibilitySize ? 1 : (dynamicTypeSize >= .xxxLarge ? 2 : 3)
        return Array(repeating: GridItem(.flexible(), spacing: 8, alignment: .top), count: n)
    }

    /// Today's numbers in one look. A tap opens that panel below.
    private func glance(_ board: Dashboard, proxy: ScrollViewProxy) -> some View {
        let keys = board.sections.filter { !["care", "subjective"].contains($0) }
        let panels = keys.compactMap { board.panel($0) }.prefix(6)
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    CardHeader("At a glance")
                    Spacer()
                    Text(board.asOf == Dates.dayString(Date()) ? "Today" : Dates.shortDay(board.asOf))
                        .mpFont(.label).foregroundStyle(MP.muted).padding(.trailing, 16).padding(.top, 8)
                }
                LazyVGrid(columns: gridColumns, spacing: 8) {
                    ForEach(Array(panels), id: \.key) { p in
                        Button {
                            expanded.insert(p.key)
                            withAnimation(MPMotion.gated(MPMotion.layout, reduceMotion: reduceMotion)) {
                                proxy.scrollTo(p.key, anchor: .top)
                            }
                        } label: {
                            GlanceTile(panel: p)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 12)
            }
        }
    }

    /// The coach's longer reads, as a row of chips.
    private var divesRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Text("Deep dives").mpFont(.labelMedium).foregroundStyle(MP.muted).padding(.trailing, 2)
                ForEach(Self.dives, id: \.0) { domain, label, symbol in
                    Button {
                        open(domain)
                    } label: {
                        HStack(spacing: 6) {
                            if loadingDive == domain {
                                ProgressView().controlSize(.small)
                            } else {
                                Image(systemName: symbol).font(.systemGlyphs(13, weight: .medium))
                            }
                            Text(label)
                        }
                    }
                    .buttonStyle(MPButtonStyle(kind: .gray))
                    .controlSize(.small)
                    .disabled(loadingDive != nil)
                }
            }
            .padding(.horizontal, 2)
        }
        .accessibilityLabel("Deep dives")
    }

    private func open(_ domain: String) {
        loadingDive = domain
        error = nil
        Task {
            defer { loadingDive = nil }
            do { dive = try await app.api.deepDive(domain) } catch { self.error = AppModel.message(for: error) }
        }
    }
}

/// One number in the glance grid: glyph, state dot, the figure, the name.
private struct GlanceTile: View {
    let panel: Panel

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                IconTile(panel.symbol, family: panel.family, size: 20)
                Spacer(minLength: 2)
                Circle().fill(MP.foreground(panel.tone)).frame(width: 7, height: 7)
                    .accessibilityHidden(true)
            }
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                Text(panel.hasData ? panel.headline : "—")
                    .font(.figures(MPSize.subhead, weight: .medium)).foregroundStyle(MP.ink)
                    .lineLimit(1).minimumScaleFactor(0.6)
                if panel.hasData, !panel.unit.isEmpty {
                    Text(panel.unit).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
                        .minimumScaleFactor(0.7)
                }
            }
            Text(panel.title).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1).minimumScaleFactor(0.8)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MP.controlShape.fill(MP.fill))
        .contentShape(MP.controlShape)
        .accessibilityElement(children: .combine)
        .accessibilityValue(Text(panel.statusText))
    }
}

/// This week against last: three deltas, the highlights, the streaks, and
/// the coach's review a tap away.
struct WeekCard: View {
    let week: WeekReview
    var onReview: () -> Void

    private var deltas: [(String, String, String, Double?)] {
        var out: [(String, String, String, Double?)] = []
        if let r = week.metrics["readiness"], let v = r.this {
            out.append(("Readiness", String(format: "%.0f", v), "", r.deltaPct))
        }
        if let s = week.metrics["sleep"], let v = s.this {
            let minutes = Int((v * 60).rounded())
            out.append(("Sleep", "\(minutes / 60)h\(String(format: "%02d", minutes % 60))", "/night", s.deltaPct))
        }
        if let l = week.metrics["load"], let v = l.this {
            out.append(("Load", v >= 1000 ? String(format: "%.1fk", v / 1000) : String(format: "%.0f", v), l.unit, l.deltaPct))
        }
        if let h = week.metrics["hrv"], let v = h.this {
            out.append(("HRV", String(format: "%.0f", v), "ms", h.deltaPct))
        }
        return Array(out.prefix(4))
    }

    var body: some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader("Your week", actionTitle: "Review", action: onReview)
                HStack(alignment: .top, spacing: 12) {
                    ForEach(deltas, id: \.0) { label, value, unit, delta in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(label).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
                            HStack(alignment: .firstTextBaseline, spacing: 2) {
                                Text(value).font(.figuresLede).foregroundStyle(MP.ink)
                                    .lineLimit(1).minimumScaleFactor(0.7)
                                if !unit.isEmpty { Text(unit).mpFont(.label).foregroundStyle(MP.muted) }
                            }
                            if let delta {
                                Text(abs(delta) < 0.5 ? "same as last"
                                     : String(format: "%@%.0f%% vs last", delta >= 0 ? "+" : "−", abs(delta)))
                                    .font(.figuresLabel)
                                    .foregroundStyle(MP.muted)
                                    .lineLimit(1).minimumScaleFactor(0.7)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityElement(children: .combine)
                    }
                }
                .padding(.horizontal, 16).padding(.top, 8)
                if !week.highlights.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(week.highlights.enumerated()), id: \.offset) { _, line in
                            HStack(alignment: .top, spacing: 8) {
                                LimeDot(size: 6).padding(.top, 7)
                                Text(line.typeset).mpFont(.copy).foregroundStyle(MP.body)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    .padding(.horizontal, 16).padding(.top, 12)
                }
                HStack(spacing: 8) {
                    if week.streaks.checkinDays > 0 {
                        StatusPill(text: "\(week.streaks.checkinDays)-day check-in streak", tone: .brand)
                    }
                    if week.streaks.sleepOnNeedDays > 0 {
                        StatusPill(text: "\(week.streaks.sleepOnNeedDays) nights on need", tone: .low)
                    }
                    if week.sessions > 0 {
                        StatusPill(text: "\(week.sessions) session\(week.sessions == 1 ? "" : "s")", tone: .brand)
                    }
                }
                .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 14)
            }
        }
    }
}

/// Thirteen weeks, four metrics, small multiples: the direction things are
/// moving in, which one day cannot show.
struct TrendsCard: View {
    let trends: [String: Trend]
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private static let order = ["readiness", "hrv", "sleep", "load", "resting_hr", "steps"]

    var body: some View {
        let shown = Self.order.compactMap { key in trends[key].map { (key, $0) } }
            .filter { $0.1.weeksWithData >= 3 }.prefix(4)
        if !shown.isEmpty {
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        CardHeader("13 weeks")
                        Spacer()
                        Text("weekly means").mpFont(.label).foregroundStyle(MP.muted)
                            .padding(.trailing, 16).padding(.top, 8)
                    }
                    let columns = Array(repeating: GridItem(.flexible(), spacing: 10),
                                        count: dynamicTypeSize.isAccessibilitySize ? 1 : 2)
                    LazyVGrid(columns: columns, spacing: 10) {
                        ForEach(Array(shown), id: \.0) { _, trend in
                            TrendTile(trend: trend)
                        }
                    }
                    .padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 12)
                }
            }
        }
    }
}

private struct TrendTile: View {
    let trend: Trend

    private var points: [TrendWeek] { trend.weeks.filter { $0.value != nil } }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(trend.label).mpFont(.labelMedium).foregroundStyle(MP.muted)
                Spacer()
                if let change = trend.changePct {
                    Text(abs(change) < 0.5 ? "flat" : String(format: "%@%.0f%%", change >= 0 ? "+" : "−", abs(change)))
                        .font(.figuresLabel)
                        .foregroundStyle(MP.ink)
                }
            }
            Chart(points) { w in
                LineMark(x: .value("Week", w.start, unit: .weekOfYear), y: .value(trend.label, w.value ?? 0))
                    .foregroundStyle(MP.chartS1)
                    .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round))
                    .interpolationMethod(.monotone)
                if w.id == points.last?.id {
                    PointMark(x: .value("Week", w.start, unit: .weekOfYear), y: .value(trend.label, w.value ?? 0))
                        .foregroundStyle(MP.lime).symbolSize(50)
                }
            }
            .chartXAxis(.hidden)
            .chartYAxis(.hidden)
            .chartYScale(domain: .automatic(includesZero: false))
            .frame(height: 44)
            .accessibilityLabel(Text("\(trend.label), 13 weeks"))
            if let last = points.last?.value {
                Text("\(trend.unit.isEmpty ? String(format: "%.0f", last) : PanelChart.axisNumber(last)) \(trend.unit)"
                    .trimmingCharacters(in: .whitespaces))
                    .font(.figuresCopy).foregroundStyle(MP.ink)
            }
        }
        .padding(10)
        .background(MP.controlShape.fill(MP.fill))
    }
}

/// The coach's long read: a display title, two paragraphs, the guardrail.
struct DeepDiveSheet: View {
    let dive: DeepDive
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(dive.domain == "weekly" ? "Your week" : dive.domain.capitalized).eyebrow()
                    Text(dive.title.typeset).title(MPSize.displayS).accessibilityAddTraits(.isHeader)
                    ForEach(Array(dive.body.components(separatedBy: "\n\n").enumerated()), id: \.offset) { _, para in
                        Text(para.typeset)
                            .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(4)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Text(dive.provider == "fallback" || dive.provider == nil
                         ? "Written from your numbers." : "Written by your coach from your numbers.")
                        .mpFont(.label).foregroundStyle(MP.muted)
                    PersonalGuardrail()
                }
                .padding(.horizontal, 22).padding(.top, 8).padding(.bottom, 28)
            }
            .ambientScreen()
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if #available(iOS 26, *) {
                        Button(role: .close) { dismiss() }
                    } else {
                        Button("Done") { dismiss() }.mpFont(.copyLargeMedium)
                    }
                }
            }
        }
        .presentationDetents([.large])
    }
}

/// The clinic engine's care metrics for a recovery goal: the headline three
/// first, then the rest, each with its state and finding.
struct CareSectionCard: View {
    let section: CareSection
    @State private var expanded = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var ordered: [CareMetricView] {
        let head = section.headline.compactMap { id in section.metrics.first { $0.id == id } }
        let rest = section.metrics.filter { !section.headline.contains($0.id) }
        return head + rest
    }

    var body: some View {
        let rows = ordered
        let shown = expanded ? rows : Array(rows.prefix(3))
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 12) {
                    IconTile("cross.case.fill", family: .violet)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("MedPull recovery metrics").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            .accessibilityAddTraits(.isHeader)
                        Text([section.pathway.map { $0.replacingOccurrences(of: "_", with: " ").capitalized },
                              section.postopDay.map { "day \($0)" }].compactMap { $0 }.joined(separator: MP.dot))
                            .mpFont(.label).foregroundStyle(MP.muted)
                    }
                    Spacer()
                }
                .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 6)
                ForEach(shown) { m in
                    InsetDivider(leading: 16)
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(m.name).mpFont(.copyMedium).foregroundStyle(MP.ink)
                            Spacer(minLength: 8)
                            if let v = m.value, m.status != "nodata" {
                                Text("\(v) \(m.unit)").font(.figuresCopy).foregroundStyle(MP.ink)
                            }
                            StatusPill(text: m.statusText, tone: m.tone)
                        }
                        Text((m.status == "nodata" ? (m.unlock ?? m.finding) : m.finding).typeset)
                            .mpFont(.label).foregroundStyle(MP.body).lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    .accessibilityElement(children: .combine)
                }
                if rows.count > 3 {
                    InsetDivider(leading: 16)
                    Button(expanded ? "Show fewer" : "Show all \(rows.count) metrics") {
                        withAnimation(MPMotion.gated(MPMotion.layout, reduceMotion: reduceMotion)) {
                            expanded.toggle()
                        }
                    }
                    .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                    .padding(.horizontal, 16).padding(.vertical, 10)
                }
            }
            .padding(.bottom, 6)
        }
        .clipShape(MP.surfaceShape)
    }
}
