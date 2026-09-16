import SwiftUI
import UIKit

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
    /// The app's typeface, in one place so the face is one edit.
    ///
    /// Garamond ships with Office and macOS but not with iOS, so the bundled
    /// face is EB Garamond, the open-licensed revival, which is also what the
    /// console loads — the two surfaces are meant to look like one product.
    /// Four static cuts rather than the variable font, because `.weight()`
    /// does not drive a variable axis on a custom face; the nearest cut is
    /// picked here instead. A missing file falls back to the system face, so
    /// a build that lost its resources is plain rather than broken.
    static func mp(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .custom(MPFont.name(for: weight), size: size)
    }

    static func display(_ size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        .mp(size, weight: weight)
    }
}

enum MPFont {
    static let family = "EB Garamond"

    /// EB Garamond carries 400/500/600/700; everything lighter reads as
    /// regular and everything heavier as bold.
    static func name(for weight: Font.Weight) -> String {
        switch weight {
        case .ultraLight, .thin, .light, .regular: return "EBGaramond-Regular"
        case .medium: return "EBGaramond-Medium"
        case .semibold: return "EBGaramond-SemiBold"
        case .bold, .heavy, .black: return "EBGaramond-Bold"
        default: return "EBGaramond-Regular"
        }
    }

    /// The UIKit half of the app — navigation titles, the tab bar, the
    /// segmented control on Profile, the rows of a native List — draws with
    /// the system face no matter what SwiftUI's `.font` says, so those
    /// proxies are set once at launch. Without this the app is half Garamond
    /// and half San Francisco, most visibly on the Profile sheet.
    @MainActor
    static func applyUIKitAppearance() {
        func font(_ size: CGFloat, _ weight: Font.Weight) -> UIFont {
            UIFont(name: name(for: weight), size: size)
                ?? .systemFont(ofSize: size, weight: weight == .bold ? .bold : .regular)
        }

        let nav = UINavigationBarAppearance()
        nav.configureWithDefaultBackground()
        nav.titleTextAttributes = [.font: font(17, .semibold)]
        nav.largeTitleTextAttributes = [.font: font(32, .bold)]
        UINavigationBar.appearance().standardAppearance = nav
        UINavigationBar.appearance().scrollEdgeAppearance = nav
        UINavigationBar.appearance().compactAppearance = nav

        UISegmentedControl.appearance().setTitleTextAttributes([.font: font(14, .medium)], for: .normal)
        UISegmentedControl.appearance().setTitleTextAttributes([.font: font(14, .semibold)], for: .selected)
        UITabBarItem.appearance().setTitleTextAttributes([.font: font(10, .medium)], for: .normal)
        UIBarButtonItem.appearance().setTitleTextAttributes([.font: font(17, .regular)], for: .normal)
    }
}

extension View {
    /// The console's `.micro` eyebrow: small caps, tracked out, muted.
    /// Tracked a little wider than the sans version was: a serif's uppercase
    /// runs tighter, and these are 11pt.
    func eyebrow() -> some View {
        self.font(.mp(11, weight: .semibold))
            .textCase(.uppercase)
            .kerning(1.0)
            .foregroundStyle(MP.muted)
    }

    /// Tracking sits at zero here. The -0.6 it used to carry was tuned to
    /// pull San Francisco's wide caps together at display sizes; a Garamond
    /// is already tightly fitted and the same value reads cramped.
    func title(_ size: CGFloat = 26) -> some View {
        self.font(.display(size)).foregroundStyle(MP.ink)
            .fixedSize(horizontal: false, vertical: true)
            .lineLimit(nil)
    }
}
