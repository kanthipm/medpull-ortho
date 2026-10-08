import Charts
import SwiftUI

/// One of the care team's metrics in full: its state in words, the one
/// sentence, the chart the engine drew for it (post-op day on the x axis),
/// and the explanation the server wrote. Served word for word; the app
/// never invents a clinical line.
struct CareMetricDetailView: View {
    let metric: PatientMetric

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 8) {
                    if !metric.isWaiting, let v = metric.value, !v.isEmpty {
                        BigFigure(value: v, unit: metric.unit)
                    }
                    StatusPill(text: metric.stateLabel, tone: metric.tone)
                    Text(metric.headline.typeset)
                        .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                    if let line = metric.readiness?.sentence ?? metric.countdown {
                        Text(line).mpFont(.label).foregroundStyle(MP.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(.horizontal, 4)

                if let chart = metric.chart, !chart.points.isEmpty {
                    Card(padding: 0) {
                        VStack(alignment: .leading, spacing: 8) {
                            MetricPlot(metric: metric, chart: chart)
                                .padding(.horizontal, 12).padding(.top, 16)
                            Text(chart.xLabel ?? "Post-op day").mpFont(.label).foregroundStyle(MP.muted)
                                .padding(.horizontal, 16).padding(.bottom, 14)
                        }
                    }
                } else if metric.isWaiting, let r = metric.readiness, r.left > 0 {
                    Card {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text("\(r.left)").font(.figuresDisplay(MPSize.displayS)).kerning(-0.9).foregroundStyle(MP.ink)
                            Text("more \(r.left == 1 && r.unit.hasSuffix("s") ? String(r.unit.dropLast()) : r.unit) of data")
                                .mpFont(.copy).foregroundStyle(MP.muted)
                        }
                    }
                }

                if let explain = metric.explain {
                    Card(padding: 0) {
                        VStack(alignment: .leading, spacing: 0) {
                            ExplainBlock("What it is", explain.what)
                            InsetDivider(leading: 16)
                            ExplainBlock("Why it matters", explain.why)
                            InsetDivider(leading: 16)
                            ExplainBlock("How to help it show", explain.help)
                        }
                        .padding(.vertical, 4)
                    }
                }
                Text("Monitoring signals for your care team — not a diagnosis.")
                    .mpFont(.label).foregroundStyle(MP.muted).padding(.horizontal, 4)
            }
            .padding(.horizontal, 18).padding(.top, 4).padding(.bottom, 28)
        }
        .mpHardScrollEdge()
        .ambientScreen(height: 300)
        .mpNavigationTitle(metric.title, short: "Metric")
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// The engine's own series for a care metric, in ink.
private struct MetricPlot: View {
    let metric: PatientMetric
    let chart: PatientMetricChart

    var body: some View {
        let last = chart.points.last
        Chart {
            ForEach(Array(chart.points.enumerated()), id: \.offset) { _, p in
                if chart.kind == "bars" {
                    BarMark(x: .value("Day", p.x), y: .value(metric.title, p.y))
                        .foregroundStyle(p == last ? MP.brand : MP.chartS1.opacity(0.5))
                        .cornerRadius(2)
                } else {
                    LineMark(x: .value("Day", p.x), y: .value(metric.title, p.y))
                        .foregroundStyle(MP.chartS1)
                        .lineStyle(StrokeStyle(lineWidth: 2.2, lineCap: .round, lineJoin: .round))
                        .interpolationMethod(.monotone)
                    if p == last {
                        PointMark(x: .value("Day", p.x), y: .value(metric.title, p.y))
                            .foregroundStyle(MP.brand)
                            .symbolSize(70)
                    }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                AxisValueLabel().font(.axis).foregroundStyle(MP.chartAxisLabel)
            }
        }
        .chartYAxis {
            AxisMarks(values: .automatic(desiredCount: 3)) { _ in
                AxisGridLine().foregroundStyle(MP.chartGrid)
                AxisValueLabel().font(.axis).foregroundStyle(MP.chartAxisLabel)
            }
        }
        .chartYScale(domain: .automatic(includesZero: chart.kind == "bars"))
        .frame(height: 150)
        .accessibilityLabel(Text("\(metric.title), \(chart.points.count) days"))
    }
}
