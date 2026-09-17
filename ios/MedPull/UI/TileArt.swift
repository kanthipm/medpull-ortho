import SwiftUI

/// White line art for gradient tiles — the medpull.org vocabulary: a curve
/// that draws itself in with a light travelling along it, a dashed
/// reference, a lime marker on the newest point with a pulsing ring, and
/// white bars that grow in. Decorative (the tile's number and caption carry
/// the reading), transform/trim only, and still under Reduce Motion.

// MARK: - Geometry

/// A monotone cubic through `points` (Fritsch–Carlson): smooth, and it never
/// overshoots the data, so a flat stretch stays flat.
struct SmoothLine: Shape {
    var points: [CGPoint]

    func path(in rect: CGRect) -> Path {
        var path = Path()
        guard points.count > 1 else { return path }
        let p = points.map { CGPoint(x: rect.minX + $0.x * rect.width, y: rect.minY + $0.y * rect.height) }
        let n = p.count
        var m = [CGFloat](repeating: 0, count: n - 1)
        for i in 0..<(n - 1) {
            let dx = max(p[i + 1].x - p[i].x, 0.0001)
            m[i] = (p[i + 1].y - p[i].y) / dx
        }
        var t = [CGFloat](repeating: 0, count: n)
        t[0] = m[0]
        t[n - 1] = m[n - 2]
        if n > 2 {
            for i in 1..<(n - 1) {
                t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2
            }
        }
        for i in 0..<(n - 1) where m[i] != 0 {
            let a = t[i] / m[i], b = t[i + 1] / m[i]
            let s = a * a + b * b
            if s > 9 {
                let k = 3 / s.squareRoot()
                t[i] = k * a * m[i]
                t[i + 1] = k * b * m[i]
            }
        }
        path.move(to: p[0])
        for i in 0..<(n - 1) {
            let h = (p[i + 1].x - p[i].x) / 3
            path.addCurve(to: p[i + 1],
                          control1: CGPoint(x: p[i].x + h, y: p[i].y + t[i] * h),
                          control2: CGPoint(x: p[i + 1].x - h, y: p[i + 1].y - t[i + 1] * h))
        }
        return path
    }
}

/// Values -> unit points (x 0...1, y 0...1 top-down) with headroom.
func unitPoints(_ values: [Double], pad: Double = 0.14) -> [CGPoint] {
    guard values.count > 1, let lo = values.min(), let hi = values.max() else { return [] }
    let span = hi - lo == 0 ? 1 : hi - lo
    let low = lo - span * pad, high = hi + span * pad
    return values.enumerated().map { i, v in
        CGPoint(x: CGFloat(i) / CGFloat(values.count - 1),
                y: CGFloat(1 - (v - low) / (high - low)))
    }
}

// MARK: - Pieces

/// The lime marker: a dot, its halo and a ring that pulses outward.
struct LimeMarker: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulse = false

    var body: some View {
        ZStack {
            Circle()
                .stroke(MP.lime, lineWidth: 2)
                .frame(width: 20, height: 20)
                .scaleEffect(pulse ? 2.2 : 0.6)
                .opacity(pulse ? 0 : 0.9)
            Circle().fill(MP.lime.opacity(0.25)).frame(width: 28, height: 28)
            Circle().fill(MP.lime).frame(width: 12, height: 12)
                .shadow(color: MP.lime.opacity(0.9), radius: 6)
        }
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.easeOut(duration: 2.4).repeatForever(autoreverses: false)) { pulse = true }
        }
    }
}

/// Faint horizontal rules behind the art.
struct ArtGrid: View {
    var lines = 4
    var body: some View {
        GeometryReader { proxy in
            Path { p in
                for i in 0..<lines {
                    let y = proxy.size.height * CGFloat(i) / CGFloat(max(lines - 1, 1))
                    p.move(to: CGPoint(x: 0, y: y))
                    p.addLine(to: CGPoint(x: proxy.size.width, y: y))
                }
            }
            .stroke(Color.white.opacity(0.22), lineWidth: 1)
        }
    }
}

// MARK: - Curve art

/// A curve tile: an optional dashed reference, the patient's line drawing
/// itself in, a light travelling along it, and the lime marker at the end.
/// `points` are unit points (see `unitPoints`).
struct CurveArt: View {
    let points: [CGPoint]
    var reference: [CGPoint]? = nil
    var height: CGFloat = 120
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var drawn = false
    @State private var comet = false

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .topLeading) {
                ArtGrid()
                if let reference, reference.count > 1 {
                    SmoothLine(points: reference)
                        .stroke(Color.white.opacity(0.6),
                                style: StrokeStyle(lineWidth: 1.5, lineCap: .round, dash: [3, 6]))
                }
                SmoothLine(points: points)
                    .trim(from: 0, to: drawn || reduceMotion ? 1 : 0)
                    .stroke(Color.white, style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                if !reduceMotion {
                    SmoothLine(points: points)
                        .trim(from: comet ? 0.95 : -0.05, to: comet ? 1.0 : 0.0)
                        .stroke(Color.white, style: StrokeStyle(lineWidth: 5, lineCap: .round))
                        .shadow(color: .white.opacity(0.9), radius: 4)
                        .opacity(drawn ? 0.9 : 0)
                }
                if let last = points.last {
                    LimeMarker()
                        .position(x: last.x * proxy.size.width, y: last.y * proxy.size.height)
                        .opacity(drawn || reduceMotion ? 1 : 0)
                        .scaleEffect(drawn || reduceMotion ? 1 : 0.2, anchor: .center)
                }
            }
        }
        .frame(height: height)
        .onAppear {
            guard !reduceMotion, !drawn else { return }
            withAnimation(MPMotion.ease(1.4).delay(0.15)) { drawn = true }
            withAnimation(.timingCurve(0.4, 0, 0.6, 1, duration: 3.6).delay(1.6).repeatForever(autoreverses: false)) {
                comet = true
            }
        }
    }
}

/// The recovery tile's art from one number: the typical curve (dashed) and
/// the patient's own, ending `pct` percent above or below it. With no
/// number, the typical curve alone.
struct RecoveryCurveArt: View {
    let pct: Double?

    private static let typical: [CGPoint] = (0...8).map { i in
        let x = CGFloat(i) / 8
        return CGPoint(x: x, y: 0.9 - 0.72 * (1 - pow(1 - x, 2.2)))
    }

    var body: some View {
        if let pct {
            let shift = CGFloat(max(-40, min(40, pct))) / 100
            let patient = Self.typical.map { p in
                CGPoint(x: p.x, y: min(0.95, max(0.08, p.y - shift * 0.9 * pow(p.x, 1.4))))
            }
            CurveArt(points: patient, reference: Self.typical)
        } else {
            CurveArt(points: [], reference: Self.typical)
        }
    }
}

// MARK: - Bars art

/// White columns that grow in on the spring; the newest is outlined in lime.
struct BarsArt: View {
    let values: [Double]
    var height: CGFloat = 110
    @State private var grown = false

    var body: some View {
        let shown = Array(values.suffix(14))
        let top = max(shown.max() ?? 1, 0.0001)
        HStack(alignment: .bottom, spacing: 5) {
            ForEach(Array(shown.enumerated()), id: \.offset) { i, v in
                BarColumn(share: max(0.05, v / top), isLast: i == shown.count - 1,
                          index: i, height: height, grown: grown)
            }
        }
        .frame(height: height, alignment: .bottom)
        .onAppear { grown = true }
    }
}

private struct BarColumn: View {
    let share: Double
    let isLast: Bool
    let index: Int
    let height: CGFloat
    let grown: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var shape: UnevenRoundedRectangle {
        UnevenRoundedRectangle(topLeadingRadius: 5, bottomLeadingRadius: 2,
                               bottomTrailingRadius: 2, topTrailingRadius: 5, style: .continuous)
    }

    var body: some View {
        let fill: Color = isLast ? Color.white.opacity(0.35) : Color.white.opacity(0.9)
        let glow: Color = isLast ? MP.lime.opacity(0.5) : Color.clear
        let barHeight: CGFloat = height * CGFloat(share)
        let scale: CGFloat = grown || reduceMotion ? 1 : 0.02
        shape
            .fill(fill)
            .overlay { if isLast { shape.strokeBorder(MP.lime, lineWidth: 1.5) } }
            .shadow(color: glow, radius: 6)
            .frame(maxWidth: .infinity)
            .frame(height: barHeight)
            .scaleEffect(x: 1, y: scale, anchor: .bottom)
            .animation(reduceMotion ? nil : MPMotion.press.delay(Double(index) * 0.04), value: grown)
    }
}
