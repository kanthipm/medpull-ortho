import SwiftUI

/// MedPull's own measurements, as a tab of their own: three short tests the
/// phone runs and the server scores the same way for every patient, so the
/// numbers compare week to week. Each test says when it was last done and
/// whether it is due; the readings they produce sit underneath.
struct MeasureTab: View {
    @Environment(AppModel.self) private var app
    @State private var flow: MeasureFlow?

    private var statuses: [MeasureStatus] {
        MeasureFlow.allCases.map { MeasureStatus.status(for: $0, in: app.portfolio) }
    }

    private var results: [PortfolioMetric] {
        app.portfolio.filter(\.isMeasured).sorted { SignalGroup.rank($0.key) < SignalGroup.rank($1.key) }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("Your phone reads how you walk, how far you can go, and how far a joint bends. Same method every time, so a change is yours and not the device’s.")
                        .mpFont(.copyLarge).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 4)
                    ForEach(Array(statuses.enumerated()), id: \.element.flow) { i, s in
                        testCard(s).mpRise(i)
                    }
                    if !results.isEmpty {
                        VStack(alignment: .leading, spacing: 10) {
                            SectionTitle("Your readings", note: "last two weeks")
                            Card(padding: 0) {
                                VStack(spacing: 0) {
                                    ForEach(results) { m in
                                        NavigationLink(value: m) {
                                            SignalRow(metric: m, signal: app.metrics?.signal(for: m.key))
                                        }
                                        .buttonStyle(.mpRow)
                                        if m.id != results.last?.id { RowDivider() }
                                    }
                                }
                                .clipShape(MP.surfaceShape)
                            }
                        }
                        .mpRise(3)
                    }
                    Text("Results go to your care team’s console beside your wearable data. Nothing here is a diagnosis.")
                        .mpFont(.label).foregroundStyle(MP.muted).padding(.horizontal, 4)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, 18).padding(.top, 2).padding(.bottom, 28)
            }
            .mpNavigationTitle("Measure")
            .toolbarTitleDisplayMode(.large)
            .mpHardScrollEdge()
            .refreshable { await app.refreshPortfolio() }
            .ambientScreen(height: 360)
            .navigationDestination(for: PortfolioMetric.self) { m in
                SignalDetailView(metric: m, signal: app.metrics?.signal(for: m.key))
            }
            .sheet(item: $flow) { item in
                NavigationStack {
                    switch item {
                    case .guidedWalk: GuidedWalkView(sixMinute: false)
                    case .sixMinuteWalk: GuidedWalkView(sixMinute: true)
                    case .rangeOfMotion: RangeOfMotionView()
                    }
                }
                .environment(app)
                .onDisappear { Task { await app.refreshPortfolio(surface: false) } }
            }
        }
    }

    /// One test: what it is, how long it takes, when it was last done, and
    /// Start. The due test leads with the filled button; the rest are quiet.
    private func testCard(_ s: MeasureStatus) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top, spacing: 12) {
                    Glyph(systemName: s.flow.symbol, family: .teal, size: 40)
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(s.flow.title).mpFont(.ledeMedium).foregroundStyle(MP.ink)
                                .accessibilityAddTraits(.isHeader)
                            Spacer(minLength: 4)
                            StateLabel(text: s.dueLabel, tone: s.isDue ? .med : .low)
                        }
                        Text(s.flow.subtitle).mpFont(.copy).foregroundStyle(MP.body)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(s.lastLine.map { "Last: \($0)" } ?? "Nothing recorded yet.")
                            .font(.figuresLabel).foregroundStyle(MP.muted)
                    }
                }
                if s.isDue {
                    PrimaryButton(title: "Start", icon: "play.fill") { flow = s.flow }
                } else {
                    SecondaryButton(title: "Do it again", icon: "arrow.counterclockwise") { flow = s.flow }
                }
            }
        }
    }
}

extension MeasureFlow {
    /// What the test measures, for the Measure tab's card.
    var measures: String {
        switch self {
        case .guidedWalk: return "Walking speed, step length, rhythm, evenness and steadiness"
        case .sixMinuteWalk: return "Distance in six minutes, and how your pace holds"
        case .rangeOfMotion: return "How far the joint bends or straightens, in degrees"
        }
    }
}
