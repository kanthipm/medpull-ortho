import SwiftUI

/// The launch and loading screen: an opaque sheet of the site's glass over
/// the fog, the MedPull mark in the centre, and the sport's ball on a slow,
/// tilted orbit around it, turning on its own axis as it goes. With no sport
/// known (a hospital record, a personal space, a first launch) the brand's
/// lime dot takes the orbit. Reduce Motion holds the ball still.
struct LaunchOrbitView: View {
    var sport: String?
    var caption: String? = nil
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var colorScheme

    private static let orbitSeconds = 5.2
    private static let spinSeconds = 7.0

    var body: some View {
        ZStack {
            glass
            VStack(spacing: 28) {
                TimelineView(.animation(paused: reduceMotion)) { context in
                    let t = context.date.timeIntervalSinceReferenceDate
                    let angle = reduceMotion ? 0.9 : t.truncatingRemainder(dividingBy: Self.orbitSeconds) / Self.orbitSeconds * 2 * .pi
                    let spin = reduceMotion ? 0 : t.truncatingRemainder(dividingBy: Self.spinSeconds) / Self.spinSeconds * 360
                    OrbitScene(angle: angle, spin: spin, sport: sport)
                }
                .frame(height: 220)
                VStack(spacing: 6) {
                    Text("MedPull")
                        .font(.mp(22, weight: .medium, relativeTo: .title3))
                        .kerning(-0.6)
                        .foregroundStyle(MP.ink)
                    if let caption {
                        Text(caption).mpFont(.label).foregroundStyle(MP.muted)
                    }
                }
            }
            .padding(.bottom, 24)
        }
        .ignoresSafeArea()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(caption.map { "MedPull. \($0)" } ?? "MedPull is loading"))
    }

    /// Opaque liquid glass: the canvas and the fog underneath, the solid
    /// glass sheet over them, its grain, and a light catching the top edge.
    private var glass: some View {
        ZStack {
            MP.canvas
            FogBackground(height: 900)
            Rectangle()
                .fill(LinearGradient(colors: [MP.glassTop, MP.glassBottom],
                                     startPoint: .top, endPoint: .bottom))
            GrainOverlay(kind: .surface)
            RadialGradient(colors: [Color.white.opacity(colorScheme == .dark ? 0.06 : 0.5), .clear],
                           center: .init(x: 0.5, y: 0.42), startRadius: 20, endRadius: 360)
                .allowsHitTesting(false)
            LinearGradient(colors: [Color.white.opacity(colorScheme == .dark ? 0.08 : 0.55), .clear, .clear],
                           startPoint: .top, endPoint: .center)
                .allowsHitTesting(false)
            VStack {
                Rectangle().fill(MP.glassRim).frame(height: 1)
                Spacer()
            }
        }
        .accessibilityHidden(true)
    }
}

/// One frame of the orbit: the mark in the middle, the ball on a tilted
/// ellipse, behind the mark on the far side and in front on the near side,
/// a little smaller when far.
private struct OrbitScene: View {
    let angle: Double
    let spin: Double
    let sport: String?

    private let radiusX: CGFloat = 104
    private let radiusY: CGFloat = 36

    var body: some View {
        let x = radiusX * CGFloat(cos(angle))
        let y = radiusY * CGFloat(sin(angle))
        let depth = (sin(angle) + 1) / 2          // 0 far, 1 near
        let scale = 0.74 + 0.36 * depth
        ZStack {
            Ellipse()
                .strokeBorder(MP.ink.opacity(0.08), lineWidth: 1)
                .frame(width: radiusX * 2 + 24, height: radiusY * 2 + 24)
                .offset(y: 6)
            SportBall(sport: sport, size: 46)
                .scaleEffect(scale)
                .rotationEffect(.degrees(spin))
                .shadow(color: Color.black.opacity(0.12 + 0.18 * depth), radius: 5 + 5 * depth, y: 4 + 3 * depth)
                .offset(x: x, y: y + 6)
                .zIndex(depth < 0.5 ? 0 : 2)
            mark.zIndex(1)
        }
    }

    /// The MedPull mark on the site's white app-icon tile, lifted.
    private var mark: some View {
        let d: CGFloat = 88
        let shape = RoundedRectangle(cornerRadius: d * 0.28, style: .continuous)
        return shape
            .fill(Color.white)
            .frame(width: d, height: d)
            .overlay(Image("MedPullMark").resizable().scaledToFit().padding(d * 0.17))
            .overlay(shape.strokeBorder(Color.black.opacity(0.08), lineWidth: 0.5))
            .shadow(color: Color.black.opacity(0.18), radius: 16, x: 0, y: 10)
    }
}

/// The ball of the sport: a basketball in orange with its seams, a tennis
/// ball in optic yellow, a soccer ball in black and white. Anything else
/// is the lime dot.
struct SportBall: View {
    let sport: String?
    var size: CGFloat = 38

    var body: some View {
        switch sport {
        case "basketball":
            ZStack {
                Circle()
                    .fill(Color(red: 0.36, green: 0.16, blue: 0.06))
                    .frame(width: size * 0.92, height: size * 0.92)
                Image(systemName: "basketball.fill")
                    .font(.system(size: size, weight: .regular))
                    .foregroundStyle(
                        RadialGradient(colors: [Color(red: 1.0, green: 0.62, blue: 0.28), Color(red: 0.87, green: 0.39, blue: 0.09)],
                                       center: .init(x: 0.35, y: 0.3), startRadius: 2, endRadius: size * 0.8))
            }
        case "tennis":
            ZStack {
                Circle()
                    .fill(Color.white)
                    .frame(width: size * 0.92, height: size * 0.92)
                Image(systemName: "tennisball.fill")
                    .font(.system(size: size, weight: .regular))
                    .foregroundStyle(
                        RadialGradient(colors: [Color(red: 0.93, green: 0.98, blue: 0.35), Color(red: 0.69, green: 0.78, blue: 0.08)],
                                       center: .init(x: 0.35, y: 0.3), startRadius: 2, endRadius: size * 0.8))
            }
        case "soccer":
            ZStack {
                Circle()
                    .fill(Color.white)
                    .frame(width: size * 0.94, height: size * 0.94)
                    .shadow(color: Color.black.opacity(0.1), radius: 1)
                Image(systemName: "soccerball")
                    .font(.system(size: size, weight: .regular))
                    .foregroundStyle(Color(white: 0.12))
            }
        default:
            LimeDot(size: size * 0.42)
        }
    }
}
