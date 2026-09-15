import SwiftUI

/// The console's design tokens (frontend/src/index.css), so the app and the
/// provider console read as one product. Light/dark pairs mirror `:root` and
/// `.dark` there.
enum MP {
    private static func pair(_ light: (Double, Double, Double), _ dark: (Double, Double, Double)) -> Color {
        Color(UIColor { traits in
            let c = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: c.0 / 255, green: c.1 / 255, blue: c.2 / 255, alpha: 1)
        })
    }

    static let ink = pair((13, 18, 32), (236, 239, 246))
    static let body = pair((58, 67, 88), (186, 193, 208))
    static let muted = pair((106, 116, 136), (140, 149, 168))
    static let faint = pair((152, 161, 179), (110, 120, 140))
    static let line = pair((233, 236, 243), (42, 48, 64))
    static let canvas = pair((247, 248, 251), (12, 14, 20))
    static let soft = pair((244, 246, 250), (22, 26, 36))
    static let panel = pair((255, 255, 255), (18, 22, 32))
    static let track = pair((236, 238, 244), (28, 33, 46))
    static let brand = pair((91, 104, 223), (122, 134, 236))
    static let brandDeep = pair((67, 80, 201), (148, 158, 242))
    static let brandTint = pair((236, 238, 252), (36, 40, 68))
    static let cyan = pair((62, 198, 183), (62, 198, 183))
    static let riskHigh = pair((229, 72, 77), (255, 107, 112))
    static let riskHighBg = pair((253, 236, 236), (58, 28, 32))
    static let riskMed = pair((224, 123, 0), (255, 170, 64))
    static let riskMedBg = pair((255, 244, 229), (54, 38, 18))
    static let riskLow = pair((10, 157, 87), (52, 199, 128))
    static let riskLowBg = pair((231, 248, 239), (20, 48, 36))
    static let riskMissing = pair((124, 135, 158), (140, 149, 168))
    static let riskMissingBg = pair((240, 242, 247), (32, 36, 48))

    static let cardRadius: CGFloat = 14
    static let buttonRadius: CGFloat = 11

    enum Tone { case low, med, high, missing, brand }

    static func tone(for level: String) -> Tone {
        switch level {
        case "low": return .low
        case "medium": return .med
        case "high": return .high
        default: return .missing
        }
    }

    static func foreground(_ tone: Tone) -> Color {
        switch tone {
        case .low: return riskLow
        case .med: return riskMed
        case .high: return riskHigh
        case .missing: return riskMissing
        case .brand: return brand
        }
    }

    static func background(_ tone: Tone) -> Color {
        switch tone {
        case .low: return riskLowBg
        case .med: return riskMedBg
        case .high: return riskHighBg
        case .missing: return riskMissingBg
        case .brand: return brandTint
        }
    }
}

extension Font {
    static func display(_ size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        .system(size: size, weight: weight, design: .default)
    }
}

extension View {
    /// The console's `.micro` eyebrow: small caps, tracked out, muted.
    func eyebrow() -> some View {
        self.font(.system(size: 11, weight: .semibold))
            .textCase(.uppercase)
            .kerning(0.8)
            .foregroundStyle(MP.muted)
    }

    func title(_ size: CGFloat = 26) -> some View {
        self.font(.display(size)).tracking(-0.6).foregroundStyle(MP.ink)
            .fixedSize(horizontal: false, vertical: true)
            .lineLimit(nil)
    }
}
