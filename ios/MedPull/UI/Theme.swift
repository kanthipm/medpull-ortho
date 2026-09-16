import SwiftUI
import UIKit

/// The console's design tokens (frontend/src/index.css), so the app and the
/// provider console read as one product. Every hex below is the same hex the
/// console's `:root` / `.dark` blocks resolve to — the two files were written
/// against each other, not from the same prose.
///
/// ONE RAMP, TWO INDEXES. There is a single blue-cast neutral ramp (every step
/// R<G<B, hue held at 210-216 rather than drifting, because clinic displays are
/// uncalibrated). Light and dark are not two palettes — they re-index the same
/// hexes, which is why seven steps do double duty and why a hue change is one
/// edit for both modes. The acceptance test is the mirror: `body` lands at
/// 7.22:1 light / 7.11:1 dark and `muted` at 5.39:1 / 5.24:1 (deltas 0.11 and
/// 0.15), all four computed here.
///
///     n-0   #FFFFFF  L=1.00000     n-475 #6B7480  L=0.17175  (inserted)
///     n-50  #F5F7FA  L=0.92836     n-500 #626B78  L=0.14468
///     n-100 #EDF1F6  L=0.87569     n-600 #4E5865  L=0.09539
///     n-200 #E0E5EC  L=0.77942     n-700 #2A333D  L=0.03197
///     n-300 #C9D0DA  L=0.62591     n-800 #1A222B  L=0.01538
///     n-400 #98A2AF  L=0.35611     n-900 #141C24  L=0.01107
///     n-425 #8B95A3  L=0.28818 (inserted)
///     n-450 #7F8A98  L=0.24956     n-950 #0E151C  L=0.00714
///     n-460 #7A8390  L=0.22867 (inserted)
///
/// The three inserted steps are what the adversarial review added; the spec's
/// 13 could not carry a compliant boundary and four text tiers without two
/// roles landing on the same hex:
///   * n-460 is light `lineStrong`. The spec used #626B78, which is byte-
///     identical to light `muted` — that collapses the three-weight rule
///     system into secondary text. n-460 is 3.83:1 on panel: clears WCAG
///     1.4.11 without reading at text weight.
///   * n-425 is dark `lineStrong`, one step ABOVE dark `muted` (n-450) for
///     the same reason. 5.67:1 on dark panel.
///   * n-475 is dark `faint` AND dark `line`. The spec published dark faint at
///     3.94/3.68/3.44; recomputed it is 3.41/3.19/2.98 — under the 3:1
///     non-text floor on `soft`. n-475 is the first step that clears 3:1 on
///     all three dark grounds (3.63 panel / 3.88 canvas / 3.39 soft).
///
/// Every ratio in this file was computed here, from sRGB relative luminance
/// with the 0.04045 linearisation threshold and (L1+0.05)/(L2+0.05).
enum MP {
    /// One dynamic UIColor per token: the trait closure is the only place the
    /// mode is read, so a repalette never needs an asset catalog entry or a
    /// per-screen `colorScheme` branch. The alpha parameters exist for `scrim`
    /// alone — every tint is a solid in both modes, deliberately, because an
    /// alpha wash's real ratio depends on which of the three grounds is behind
    /// it and these carry clinical state. The dark tints below ARE the
    /// 0.16/0.18/0.28 washes, frozen over `panel`.
    ///
    /// `lightHigh`/`darkHigh` are the Increase Contrast substitutions, and
    /// they are the same four tokens the console strengthens under
    /// `@media (prefers-contrast: more)`. The trait is right here in the
    /// closure, so honouring it costs nothing and the alternative is a
    /// clinician who turns Increase Contrast on and gets no card edge back.
    private static func pair(_ light: (Double, Double, Double),
                             _ dark: (Double, Double, Double),
                             lightAlpha: Double = 1,
                             darkAlpha: Double = 1,
                             lightHigh: (Double, Double, Double)? = nil,
                             darkHigh: (Double, Double, Double)? = nil) -> Color {
        Color(UIColor { traits in
            let isDark = traits.userInterfaceStyle == .dark
            let boost = traits.accessibilityContrast == .high
            let base = isDark ? dark : light
            let high = isDark ? darkHigh : lightHigh
            let c = boost ? (high ?? base) : base
            let a = isDark ? darkAlpha : lightAlpha
            return UIColor(red: c.0 / 255, green: c.1 / 255, blue: c.2 / 255, alpha: a)
        })
    }

    // MARK: - Text

    /// n-950 / n-0. 18.38:1 on panel in both modes.
    static let ink = pair((14, 21, 28), (255, 255, 255))
    /// n-600 / n-400. Panel/canvas/soft: 7.22 / 6.73 / 6.37 light,
    /// 6.65 / 7.11 / 6.21 dark.
    static let body = pair((78, 88, 101), (152, 162, 175))
    /// n-500 / n-450. Secondary text AND the placeholder tier:
    /// 5.39 / 5.03 / 4.75 light, 4.91 / 5.24 / 4.58 dark — clears 4.5:1 on
    /// panel, canvas and a zebra `soft` row in both modes. Placeholders live
    /// here, not on `faint`: placeholder text is text under WCAG 1.4.3.
    static let muted = pair((98, 107, 120), (127, 138, 152))
    /// n-400 / n-475. NON-TEXT AND INACTIVE ONLY — decoration, disabled
    /// glyphs, empty-state art. Light is 2.59:1 on panel and 2.28:1 on soft,
    /// which is conformant only because inactive components are exempt from
    /// 1.4.11; dark is 3.63 / 3.88 / 3.39. Anything a patient must read goes
    /// on `muted`, and a disabled control goes on `disabledInk`.
    /// Increase Contrast: n-500 light (2.59 -> 5.39:1), n-425 dark
    /// (3.63 -> 5.67:1).
    static let faint = pair((152, 162, 175), (107, 116, 128),
                            lightHigh: (98, 107, 120), darkHigh: (139, 149, 163))

    // MARK: - Rules (three weights, distinct in both modes)

    /// n-200 / n-800. Decorative seams only — 1.27:1 light, 1.07:1 dark on
    /// panel. Never the sole cue for anything. Increase Contrast: n-300 light
    /// (1.27 -> 1.55:1), n-475 dark (1.07 -> 3.63:1).
    static let hairline = pair((224, 229, 236), (26, 34, 43),
                               lightHigh: (201, 208, 218), darkHigh: (107, 116, 128))
    /// n-300 / n-475. Structural table rules and card edges. The dark half
    /// steps all the way to n-475 (3.63:1 on panel, 3.88 canvas, 3.39 soft)
    /// because on dark this line is the ONLY cue that a card is a card: dark
    /// `panel` is 1.07:1 against `canvas`, so there is no fill delta and no
    /// 8pt seam to lean on, and the spec's n-700 edge was 1.34:1 — less than
    /// half of 1.4.11's 3:1. Light stays low (1.55:1) because there the
    /// canvas seam is a real second cue. Increase Contrast: n-460 light
    /// (1.55 -> 3.83:1), n-425 dark (3.63 -> 5.67:1) — this is the token that
    /// gives a card edge back to a clinician who turns the setting on.
    static let line = pair((201, 208, 218), (107, 116, 128),
                           lightHigh: (122, 131, 144), darkHigh: (139, 149, 163))
    /// n-460 / n-425. For a boundary that is the only cue a control exists:
    /// field borders, the focused edge, a table rule that carries meaning.
    /// 3.83 / 3.57 / 3.38 light, 5.67 / 6.06 / 5.30 dark.
    static let lineStrong = pair((122, 131, 144), (139, 149, 163))

    // MARK: - Surfaces

    /// n-50 / n-950.
    static let canvas = pair((245, 247, 250), (14, 21, 28))
    /// n-100 / n-800. Zebra rows, grouping, recessed wells. 1.13:1 against
    /// panel light, 1.07:1 dark — a seam, not a colour change.
    static let soft = pair((237, 241, 246), (26, 34, 43))
    /// n-0 / n-900.
    static let panel = pair((255, 255, 255), (20, 28, 36))
    /// n-200 / n-700. Slider and progress troughs. 1.27:1 on light panel,
    /// 1.43:1 on dark canvas — a trough, not a boundary.
    static let track = pair((224, 229, 236), (42, 51, 61))
    /// The disabled-control pair, and the fix for the send buttons that put a
    /// white arrow on a `faint` disc (2.60:1, reading as an enabled button
    /// that is badly drawn). n-100/n-500 light, n-800/n-450 dark:
    /// `disabledInk` on `disabledFill` is 4.75:1 light / 4.58:1 dark, so a
    /// disabled label stays readable even though it does not have to be.
    static let disabledFill = pair((237, 241, 246), (26, 34, 43))
    static let disabledInk = pair((98, 107, 120), (127, 138, 152))

    // MARK: - Brand — Medical Blue #1976D2 is a FILL, never a foreground

    /// The exact anchor, unchanged in both modes because white on it is
    /// 4.60:1 either way. FILLS, focus rings, the 2pt active-tab rule, dots.
    /// As text it is 4.60:1 on light panel (passing by 0.10) but 3.74:1 on
    /// dark panel and 3.99:1 on dark canvas — both AA failures, which is why
    /// every foreground use goes to `brandInk`.
    static let brand = pair((25, 118, 210), (25, 118, 210))
    /// 4.60:1 on `brand`. Zero headroom: `brand` must never be lightened.
    static let onBrand = pair((255, 255, 255), (255, 255, 255))
    /// #1565C0 / #63A4FF. Links, active labels, brand text on paper, brand
    /// glyphs. 5.75 / 5.35 / 5.07 on panel/canvas/soft light, 6.78 / 7.25 /
    /// 6.34 dark, and 4.96:1 light / 5.62:1 dark on `brandTint`. The 21 sites
    /// that pass `MP.brand` to `foregroundStyle` move here in the migration
    /// phase; without that move dark brand text goes from today's measured
    /// 5.92:1 to 3.99:1, an AA failure the redesign would have introduced.
    static let brandInk = pair((21, 101, 192), (99, 164, 255))
    /// Pressed/hover fill, and any brand surface that must carry white text:
    /// white on it is 8.63:1 light / 5.75:1 dark. On light it is also the only
    /// brand ink allowed on `brandTintStrong` (6.36:1, where `brandInk` is
    /// 4.24:1). The dark half is the base anchor, as on the console.
    static let brandDeep = pair((13, 71, 161), (25, 118, 210))
    /// #E3F0FC / #152C43 (the 0.18 wash frozen over dark panel). 1.16:1 on
    /// light panel. `brandInk` on it: 4.96:1 light, 5.62:1 dark.
    static let brandTint = pair((227, 240, 252), (21, 44, 67))
    /// #C8E0F9 / #153555 (the 0.28 wash frozen). Selected rows, chart bands,
    /// text selection. Text on this is `ink` (13.55:1 light / 12.56:1 dark)
    /// or, on light only, `brandDeep`. NOT `brandInk`, which is 4.24:1 here.
    static let brandTintStrong = pair((200, 224, 249), (21, 53, 85))

    // MARK: - Teal — one semantic slot: verified / adherent / live

    /// The exact anchor. FILL and 4pt accent bars only on light, where it is
    /// 2.74:1 on white — it fails even the 3:1 non-text bar, and white on it
    /// is also 2.74:1, so white-on-teal is banned outright. On dark the same
    /// hex inverts into the strong half (6.28:1 panel / 6.71 canvas / 5.87
    /// soft) and may carry text there; `tealInk` covers both modes so no call
    /// site has to know that.
    static let teal = pair((0, 172, 193), (0, 172, 193))
    /// n-950 on `teal`: 6.71:1.
    static let onTeal = pair((14, 21, 28), (14, 21, 28))
    /// #00707D / #5DDEF4 — the only teal allowed as text. 5.81 / 5.41 / 5.12
    /// light, 10.82 / 11.57 / 10.11 dark.
    static let tealInk = pair((0, 112, 125), (93, 222, 244))
    /// Chart strokes, icon strokes, 1pt rules. #0097A7 clears 1.4.11 at
    /// 3.51:1 on light panel; on dark the base anchor works at 6.28:1.
    static let tealGraphic = pair((0, 151, 167), (0, 172, 193))
    /// #DFF6F9 / #103640. `tealInk` on it: 5.17:1 light, 8.14:1 dark.
    static let tealTint = pair((223, 246, 249), (16, 54, 64))
    /// RETIRED NAME, kept so nothing breaks: the old #3EC6B7 mint is gone and
    /// this resolves to the teal anchor. Its 2 call sites move to `teal`
    /// (fill) or `tealInk` (text) in the migration phase.
    static let cyan = teal

    // MARK: - Risk grid (re-derived; all four Material pairs were failing)

    /// 5.62:1 on panel, 4.83:1 on its own tint (was #E53935 on #FFEBEE, 3.70:1).
    static let riskHigh = pair((198, 40, 40), (255, 138, 135))
    /// Light solid / the 0.16 wash frozen over dark panel. 5.70:1 against
    /// `riskHigh` on dark, 4.83:1 on light.
    static let riskHighBg = pair((251, 234, 234), (58, 46, 52))
    /// 5.82:1 on panel, 5.17:1 on tint (was #EF6C00 on #FFF3E0, 2.81:1).
    static let riskMed = pair((154, 83, 0), (255, 178, 92))
    static let riskMedBg = pair((251, 240, 225), (58, 52, 45))
    /// 5.37:1 on panel, 4.73:1 on tint (was #388E3C on #E8F5E9, 3.66:1).
    static let riskLow = pair((27, 122, 67), (92, 209, 153))
    static let riskLowBg = pair((230, 244, 235), (32, 57, 55))
    /// n-600 / n-400. 7.22:1 on panel, 6.37:1 light / 5.09:1 dark on tint
    /// (was #757575 on #EEEEEE, 3.97:1).
    static let riskMissing = pair((78, 88, 101), (152, 162, 175))
    static let riskMissingBg = pair((237, 241, 246), (41, 49, 58))

    // MARK: - Overlays (the light/dark inversion)

    /// On light a sheet separates by FILL: `panel` on the scrim composite is
    /// 6.50:1. On dark a fill cannot separate — n-800 on the scrim is 1.26:1
    /// and n-700 only 1.58:1 — so the panel steps UP to n-700 and the 1pt
    /// border carries the edge instead.
    static let overlayPanel = pair((255, 255, 255), (42, 51, 61))
    /// n-460 / n-425. On dark this IS the modal edge: 4.22:1 on
    /// `overlayPanel` and 6.69:1 against the scrim composite. On light it is
    /// 3.83:1 on white and merely reinforces a fill that already separates.
    static let overlayBorder = pair((122, 131, 144), (139, 149, 163))
    /// Black at 62% light / 70% dark, and deliberately NOT `ink`, which
    /// inverts to #FFFFFF in dark and would brighten the page behind the
    /// sheet. Light composites to #5D5E5F over canvas; dark to #040608.
    static let scrim = pair((0, 0, 0), (0, 0, 0), lightAlpha: 0.62, darkAlpha: 0.70)

    // MARK: - Charts (categorical caps at 2 series)

    /// Series 1, solid stroke. 4.60:1 on light panel / 6.78:1 dark.
    static let chartS1 = pair((25, 118, 210), (99, 164, 255))
    /// Series 2 — and the 4-2 dash plus a direct end-of-line label are
    /// MANDATORY, not decorative: s1-vs-s2 separation is only 1.26:1 light
    /// and 1.60:1 dark, so colour alone does not distinguish them. There is
    /// no series 3: 3+ series uses `chartSeq`.
    static let chartS2 = pair((0, 112, 125), (93, 222, 244))
    /// Single-hue sequential ramp for 3+ series, heatmaps and bands. Adjacent
    /// steps are 1.56 / 1.85 / 1.72 / 1.50 light and 2.48 / 1.72 / 1.85 /
    /// 1.48 dark, so neighbours stay separable; dark runs dark-to-light. The
    /// lowest light step is 1.16:1 on panel, so a sequential cell always
    /// takes a `line` stroke or an empty cell and a low cell are one pixel.
    static let chartSeq: [Color] = [
        pair((227, 240, 252), (13, 44, 74)),
        pair((156, 197, 238), (21, 101, 192)),
        pair((74, 144, 217), (74, 144, 217)),
        pair((21, 101, 192), (156, 197, 238)),
        pair((13, 71, 161), (220, 234, 251)),
    ]
    /// n-200 / n-700. 1.27:1 light / 1.34:1 dark on panel. Increase Contrast:
    /// n-460 light (-> 3.83:1), n-425 dark (-> 5.67:1).
    static let chartGrid = pair((224, 229, 236), (42, 51, 61),
                                lightHigh: (122, 131, 144), darkHigh: (139, 149, 163))
    /// n-500 / n-450, 5.39:1 light / 4.91:1 dark on panel. Axis labels are
    /// text; they never take `faint`, which was 2.59:1 under them.
    static let chartAxisLabel = pair((98, 107, 120), (127, 138, 152))
    /// n-400 / n-475, dashed, non-text. 3.63:1 on dark panel.
    static let chartRefLine = pair((152, 162, 175), (107, 116, 128))

    // MARK: - Radii

    /// Sheets, cards, panels — anything that holds content. 12pt.
    static let radiusSurface: CGFloat = 12
    /// Buttons, fields, chips, segments — anything you touch. 10pt.
    static let radiusControl: CGFloat = 10
    /// RETIRED NAMES, pointed at the two tokens so the 15 existing call sites
    /// keep compiling and pick up the new values; the migration phase repoints
    /// them and retires the seven scattered literals (14, 16, 14, 12, 10, 8, 3).
    static let cardRadius: CGFloat = radiusSurface
    static let buttonRadius: CGFloat = radiusControl

    /// Always `.continuous`. `.circular` is the iOS 6 corner and reads as a
    /// different product next to a system sheet; the app has exactly one
    /// non-continuous corner left (Components.swift's ErrorBanner) and it is
    /// visible at r=10 across its instances.
    static let surfaceShape = RoundedRectangle(cornerRadius: radiusSurface, style: .continuous)
    static let controlShape = RoundedRectangle(cornerRadius: radiusControl, style: .continuous)
    /// A pill is a Capsule, not a large radius — a 999pt rectangle and a
    /// capsule diverge the moment the element is taller than it is wide.
    static let pillShape = Capsule(style: .continuous)

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
        // This helper is by definition a foreground, so brand resolves to
        // brandInk: #1976D2 is 3.74:1 on dark panel.
        case .brand: return brandInk
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
    /// Instrument Sans (SIL OFL 1.1), bundled at weights 400 and 500 only.
    /// It is the measured-closest open substitute for the console's reference
    /// face, and it is the shared UI face on both surfaces: the console loads
    /// the same two cuts as woff2 from frontend/public/fonts. EB Garamond is
    /// not a UI face anywhere any more — its four files are still in
    /// Resources/Fonts but are no longer registered in project.yml and
    /// nothing references them.
    ///
    /// Why this fixes legibility without touching a single size: the Garamond
    /// swap was mechanical and preserved every point size while dropping
    /// x-height 21.2% (sxHeight 400/1000 against San Francisco's 0.5078em),
    /// so `.mp(11)` rendered an apparent 8.7px and `.mp(9)` an apparent 7.1px.
    /// Instrument Sans measures sxHeight 510/1000 = 0.5100em, within +0.4% of
    /// San Francisco, so the same numbers now render the size they claim.
    /// The size ladder itself (12/14/16/18/20) lands in the migration phase.
    ///
    /// A missing file falls back to the system face, so a build that lost its
    /// resources is plain rather than broken — but silently, which is why the
    /// PostScript names below are verified against the bundled files rather
    /// than typed from the family name.
    static func mp(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .custom(MPFont.name(for: weight), size: size)
    }

    /// Same face — there is one typeface on both surfaces now, and a display
    /// moment is made with size and space, not a second family. The default
    /// is `.medium` because 500 is the weight ceiling.
    static func display(_ size: CGFloat, weight: Font.Weight = .medium) -> Font {
        .mp(size, weight: weight)
    }
}

enum MPFont {
    /// The typographic family name. Note the Medium's own name ID 1 is
    /// "Instrument Sans Medium" (the Google Fonts RIBBI split, where name
    /// 16/17 carry "Instrument Sans"/"Medium" for modern shapers), so the
    /// family name resolves the Regular only — never pass this to
    /// `Font.custom`, or the Medium silently becomes San Francisco.
    static let family = "Instrument Sans"

    /// PostScript names, which is what `Font.custom(_:size:)` and
    /// `UIFont(name:size:)` actually match on. Read back from the two
    /// bundled files, not assumed.
    static let regular = "InstrumentSans-Regular"
    static let medium = "InstrumentSans-Medium"

    /// Two cuts ship: 400 and 500. 500 is the ceiling, so `.semibold`,
    /// `.bold`, `.heavy` and `.black` all MAP DOWN to the 500 cut rather than
    /// naming a file that does not exist — `Font.custom` with an unbundled
    /// PostScript name falls back to San Francisco silently, which would put
    /// a third face mid-screen at the 47 call sites that still ask for
    /// `.semibold` or `.bold`. Those call sites are cleaned up in the
    /// migration phase; until then they compile and render at the ceiling.
    /// Nothing ever asks for a heavier file, so there is no synthetic bold.
    static func name(for weight: Font.Weight) -> String {
        switch weight {
        case .ultraLight, .thin, .light, .regular: return regular
        case .medium, .semibold, .bold, .heavy, .black: return medium
        default: return regular
        }
    }

    /// The UIKit half of the app — the tab bar, the segmented control on
    /// Profile, the rows of a native List — draws with the system face no
    /// matter what SwiftUI's `.font` says, so those proxies are set once at
    /// launch. Without this the app is half Instrument Sans and half San
    /// Francisco, most visibly on the Profile sheet.
    ///
    /// What is deliberately NOT here any more: the three
    /// `UINavigationBarAppearance` assignments (standard, scrollEdge,
    /// compact). Apple's guidance is that custom backgrounds in navigation
    /// can overlay or interfere with the effects the system provides,
    /// including the scroll edge effect, and every custom background is a
    /// surface whose contrast and reduce-transparency behaviour we then own by
    /// hand. The nav bar, the tab bar and the toolbar now render themselves.
    /// The dead `largeTitleTextAttributes` went with them — seven of eight
    /// screens hide the nav bar and the three that keep it use `.inline`, so
    /// it never drew. What remains is font-only: `titleTextAttributes` is the
    /// legacy proxy and sets no background, no tint and no shadow.
    @MainActor
    static func applyUIKitAppearance() {
        func font(_ size: CGFloat, _ weight: Font.Weight) -> UIFont {
            UIFont(name: name(for: weight), size: size)
                ?? .systemFont(ofSize: size, weight: weight == .regular ? .regular : .medium)
        }

        UINavigationBar.appearance().titleTextAttributes = [.font: font(17, .medium)]
        UISegmentedControl.appearance().setTitleTextAttributes([.font: font(14, .regular)], for: .normal)
        UISegmentedControl.appearance().setTitleTextAttributes([.font: font(14, .medium)], for: .selected)
        UITabBarItem.appearance().setTitleTextAttributes([.font: font(10, .medium)], for: .normal)
        UIBarButtonItem.appearance().setTitleTextAttributes([.font: font(17, .regular)], for: .normal)
    }
}

extension View {
    /// The console's `.micro` eyebrow: uppercase, tracked out, muted.
    ///
    /// Real capitals, not small caps — Instrument Sans has no `smcp` in its
    /// GSUB (it carries `case`, `tnum` and ss01-ss12), so
    /// `.textCase(.uppercase)` is the whole mechanism. Tracking is the
    /// console's `--track-eyebrow` +0.06em, which at 11pt is 0.66pt; the
    /// 1.0pt it used to carry was tuned to open up a serif's tight uppercase
    /// fitting and reads gappy on a neo-grotesque.
    func eyebrow() -> some View {
        self.font(.mp(11, weight: .medium))
            .textCase(.uppercase)
            .kerning(0.66)
            .foregroundStyle(MP.muted)
    }

    /// Tracking sits at zero here for now. The console's title and display
    /// tracking tokens are -0.02em and -0.03em; applying them is a per-site
    /// change that belongs with the size ladder in the migration phase, so
    /// nothing shifts in this one.
    func title(_ size: CGFloat = 26) -> some View {
        self.font(.display(size)).foregroundStyle(MP.ink)
            .fixedSize(horizontal: false, vertical: true)
            .lineLimit(nil)
    }
}
