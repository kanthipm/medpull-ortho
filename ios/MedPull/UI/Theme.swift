import Observation
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

    /// n-200 / n-700. Decorative inset dividers only — 1.27:1 light, 1.34:1
    /// dark on panel (dark moved n-800 -> n-700: at 1.07:1 the inset rows of a
    /// grouped card read as one slab). Never the sole cue for anything.
    /// Increase Contrast: n-300 light (1.27 -> 1.55:1), n-475 dark
    /// (1.34 -> 3.63:1).
    static let hairline = pair((224, 229, 236), (42, 51, 61),
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
    /// Brand ink on a PRESSED tinted control (`brandTintStrong`): brandDeep
    /// light (6.365:1), brandInk dark (4.954:1). One token because dark
    /// brandDeep is the base anchor and would be 2.73:1 there, and light
    /// brandInk is 4.238:1. Used by the tinted button style.
    static let brandInkPressed = pair((13, 71, 161), (99, 164, 255))
    /// A "reached" state mark on a `track` trough (progress dots, a filled
    /// step): the #1976D2 fill on light (3.635:1 on track, 4.602 on panel)
    /// but `brandInk` on dark, where the anchor is only 2.784:1 on track and
    /// fails the 1.4.11 floor; #63A4FF is 5.054:1 on track, 6.783 on panel.
    static let stateFill = pair((25, 118, 210), (99, 164, 255))

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

    // MARK: - Secondary text on a tinted card

    /// Secondary text (labels, meta) on `brandTint` / `tealTint` cards. This is
    /// `body`, not `muted`: dark `muted` on `brandTint` is 4.07:1 and fails,
    /// dark `body` there is 5.51:1; light `body` on #E3F0FC is 6.24:1.
    /// `Card(tint:)` passes this to its secondary labels.
    static let onTintSecondary = body

    // MARK: - Ambient wash

    /// The soft brand wash at the top of a tab root (a LinearGradient from
    /// this to clear, ~320pt, behind the content). Alpha pairs .70 / .40 over
    /// `canvas`. Its only job is to give the bars something to show. Text at
    /// the wash peak: muted 4.76 light / 4.81 dark, body 6.37 / 6.52. Drop it
    /// (plain `canvas`) under `colorSchemeContrast == .increased`.
    static let ambient = pair((227, 240, 252), (21, 44, 67), lightAlpha: 0.70, darkAlpha: 0.40)
    /// The teal half of the wash, same alphas. muted on its peak 4.86 / 4.67.
    static let ambientTeal = pair((223, 246, 249), (16, 54, 64), lightAlpha: 0.70, darkAlpha: 0.40)

    // MARK: - Category tiles (Health-style, NON-RISK hues only)

    /// Four families for leading icon tiles: blue, teal, indigo, violet. Red,
    /// amber and green are risk colours and never a category. Ink is the
    /// glyph, tint the tile fill; every pair clears 4.5:1 anyway:
    ///   blue   #1565C0 on #E3F0FC 4.96  |  #63A4FF on #152C43 5.62
    ///   teal   #00707D on #DFF6F9 5.17  |  #5DDEF4 on #103640 8.14
    ///   indigo #3F3DB8 on #ECEBFD 6.95  |  #A9A6FF on #24244A 6.72
    ///   violet #7B2FA8 on #F4E9FA 6.35  |  #D7A3F5 on #33224A 7.11
    static let catBlue = brandInk
    static let catBlueTint = brandTint
    static let catTeal = tealInk
    static let catTealTint = tealTint
    static let catIndigo = pair((63, 61, 184), (169, 166, 255))
    static let catIndigoTint = pair((236, 235, 253), (36, 36, 74))
    static let catViolet = pair((123, 47, 168), (215, 163, 245))
    static let catVioletTint = pair((244, 233, 250), (51, 34, 74))

    enum Category: CaseIterable { case blue, teal, indigo, violet }

    /// Glyph colour for a category tile.
    static func categoryInk(_ c: Category) -> Color {
        switch c {
        case .blue: return catBlue
        case .teal: return catTeal
        case .indigo: return catIndigo
        case .violet: return catViolet
        }
    }

    /// Fill for a category tile.
    static func categoryTint(_ c: Category) -> Color {
        switch c {
        case .blue: return catBlueTint
        case .teal: return catTealTint
        case .indigo: return catIndigoTint
        case .violet: return catVioletTint
        }
    }
    // MARK: - Risk grid (re-derived; all four Material pairs were failing)

    /// 5.62:1 on panel, 4.83:1 on its own tint (was #E53935 on #FFEBEE, 3.70:1).
    static let riskHigh = pair((198, 40, 40), (255, 138, 135))
    /// Light solid / the 0.16 wash frozen over dark panel. 5.70:1 against
    /// `riskHigh` on dark, 4.83:1 on light.
    static let riskHighBg = pair((251, 234, 234), (58, 46, 52))
    /// `riskHigh` ink on a PRESSED destructive capsule (riskHigh 12% over
    /// `riskHighBg`): deep red #8E1818 light (6.600:1), riskHigh dark
    /// (4.587:1).
    static let riskHighPressed = pair((142, 24, 24), (255, 138, 135))
    /// Ink for a SOLID `riskHigh` disc or bar — the one place the two modes
    /// need different inks rather than one token. White on #C62828 is 5.62:1,
    /// but white on the dark half #FF8A87 is only 2.27:1, so dark flips to
    /// n-950 (8.08:1). `onBrand` cannot cover this case, which is why the
    /// avatar disc used to put white on a light-red fill in dark mode.
    static let onRiskHigh = pair((255, 255, 255), (14, 21, 28))
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

    /// Sheets, cards, grouped lists — anything that holds content. 20pt,
    /// continuous (was 12). The console's `--r-surface` is the same 20.
    static let radiusSurface: CGFloat = 20
    /// Fields, grey metric tiles, segmented tracks, menus. 12pt (was 10).
    /// Buttons and pills are NOT this: they are capsules.
    static let radiusControl: CGFloat = 12
    /// Compact controls and a segmented thumb inside a 12pt track with 2pt
    /// padding (12 - 2 = 10). Console `--r-control-sm`.
    static let radiusThumb: CGFloat = 10
    /// The 30pt leading category tile. 8/30 = 0.27, near Apple's 0.22.
    /// Console `--r-tile`.
    static let radiusTile: CGFloat = 8

    /// The separator between two facts: "Day 8 · Total Knee Replacement".
    /// Instrument Sans draws "·" 0.103em wide with no sidebearings, so plain
    /// spaces leave it 0.200em from each word and it crowds them. The face has
    /// no thin space, so iOS takes U+2009 from San Francisco (0.103em), which
    /// brings each side to 0.303em. Retell's Untitled Sans gets 0.304em from
    /// space plus sidebearing.
    static let dot = " \u{2009}·\u{2009} "
    /// The same dot opening a trailing fact inside an HStack, where the stack's
    /// own spacing already sits to its left: "· done by text".
    static let dotLead = "·\u{2009} "
    // `cardRadius` and `buttonRadius` are DELETED. The doc comment here used
    // to name six surviving call sites in CheckinView and OnboardingFlow; all
    // six now use `surfaceShape`/`controlShape`, so a live-code scan of ios/
    // finds ZERO references to either name (any hit a grep still returns is
    // prose describing the migration). They had already gone before this deletion, so no
    // deprecation warning was firing — the names were simply unreachable.

    /// Always `.continuous`. `.circular` is the iOS 6 corner and reads as a
    /// different product next to a system sheet; the app has exactly one
    /// non-continuous corner left (Components.swift's ErrorBanner) and it is
    /// visible at r=10 across its instances.
    static let surfaceShape = RoundedRectangle(cornerRadius: radiusSurface, style: .continuous)
    static let controlShape = RoundedRectangle(cornerRadius: radiusControl, style: .continuous)
    static let thumbShape = RoundedRectangle(cornerRadius: radiusThumb, style: .continuous)
    static let tileShape = RoundedRectangle(cornerRadius: radiusTile, style: .continuous)
    /// Every button and pill. Same shape as `pillShape`, named for buttons.
    static let capsuleShape = Capsule(style: .continuous)
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

// MARK: - Motion

/// THE APP'S ONE MOTION VOCABULARY. Every duration in the app lives here.
///
/// Rules: 150-350ms, `easeOut` entering, `easeIn` leaving. Springs are
/// allowed for controls and layout only (`press`, `layout`), are critically
/// damped (no visible overshoot), and never move a clinical number — a
/// number changes with `.contentTransition(.numericText())` gated here. SwiftUI does NOT honour `accessibilityReduceMotion` for
/// explicit animations — `.animation(_:value:)` and `withAnimation` run
/// regardless — so a call site reads the environment value and goes through
/// `MPMotion.gated(_:reduceMotion:)` (nil: no animation) or
/// `MPMotion.transition(reduceMotion:)` (a 150ms cross-fade instead).
///
/// Glass.swift carries no motion of its own; its old private copies were
/// deleted, so this enum is the only place a duration is written.
enum MPMotion {
    /// 150ms ease-out. The reduce-motion substitute: a cross-fade at the
    /// bottom of the band.
    static let crossFade = Animation.easeOut(duration: 0.15)
    /// 180ms ease-out. A step within a screen (the check-in questions).
    static let step = Animation.easeOut(duration: 0.18)
    /// 180ms ease-in. Leaving.
    static let exit = Animation.easeIn(duration: 0.18)
    /// 200ms ease-out. A small state change (step dots, a toggle's knock-on).
    static let state = Animation.easeOut(duration: 0.2)
    /// 240ms ease-out. Entering — a step advancing, a surface appearing.
    static let enter = Animation.easeOut(duration: 0.24)
    /// 250ms ease-out. A completion state settling in (check-in sent).
    static let settle = Animation.easeOut(duration: 0.25)
    /// 280ms ease-out. A morph between two shapes. Top of the band, because
    /// a morph that is too quick reads as a glitch rather than a move.
    static let morph = Animation.easeOut(duration: 0.28)
    /// 250ms snappy spring, no bounce. A control reacting to a press: the 0.97
    /// scale on a capsule button or chip.
    static let press = Animation.snappy(duration: 0.25)
    /// 350ms smooth spring, no bounce. A layout change: a card expanding, a
    /// row inserting, a done-state settling.
    static let layout = Animation.smooth(duration: 0.35)
    /// The press scale, and 1 (no scale) under Reduce Motion.
    static func pressScale(_ isPressed: Bool, reduceMotion: Bool) -> CGFloat {
        (isPressed && !reduceMotion) ? 0.97 : 1
    }

    /// `animation`, or nil when the patient has asked for less motion.
    static func gated(_ animation: Animation, reduceMotion: Bool) -> Animation? {
        reduceMotion ? nil : animation
    }

    /// A morph, or the cross-fade under Reduce Motion.
    static func transition(reduceMotion: Bool) -> Animation {
        reduceMotion ? crossFade : morph
    }
}

/// THE FROZEN LADDER. Five UI rungs — 12 / 14 / 16 / 18 / 20 — plus 11
/// reserved for chart axis labels alone, and a four-rung display band above.
/// Nothing between 20 and 28 is a size: 26 is not a rung, and the two
/// `.title(26)` sites are the last of it.
///
/// "FROZEN" MEANS THE AUTHORED NUMBER, NOT THE RENDERED ONE. Every rung still
/// honours Dynamic Type — a patient app cannot opt out of it, and
/// `Font.custom(_:size:)` has scaled from `.body` since iOS 14 (the opt-out
/// is `custom(_:size:fixedSize:)`, which this file deliberately never calls).
/// The two bands scale on DIFFERENT curves, measured on device at AX5 against
/// the same screen at the default size:
///   * UI band, `.body`-relative: 16pt of body copy went from 14.7pt of ink
///     to 41.3pt. 2.81x.
///   * Display band, `.largeTitle`-relative: a 34pt title went from 31.7pt of
///     ink to 53.7pt. 1.69x.
/// That is Apple's curve, not ours — in the system table AX5 body is 53pt
/// against an AX5 largeTitle of 60pt, so body grows 3.1x while largeTitle
/// grows 1.8x — and it is the reason the display band is
/// pinned to `.largeTitle`: on the old `.body` curve a 54pt readout reached
/// 150pt and took the screen with it. At AX sizes the hierarchy is carried by
/// weight, space and order, because the sizes converge no matter what we do.
///
/// Why raw numbers are named instead of banned: the six `.system(design:
/// .monospaced)` escapes hold column and chart alignment and cannot go
/// through `.mp`, so they need the same numbers. Use these constants there
/// (or `Font.figures…`) rather than retyping a literal.
enum MPSize {
    /// 11pt. CHART AXIS LABELS ONLY — the one thing allowed under 12, and the
    /// floor for the whole app. It is a real size for a real reason: an axis
    /// label sits inside a plot it must not crowd, and it is never the only
    /// copy of the number (the series label and the readout carry that).
    /// Anything a patient reads as a sentence, a control label or a caption is
    /// 12 at the smallest. Nothing is 9 or 10.
    static let axis: CGFloat = 11
    /// 12pt. Captions, meta lines, pill and eyebrow labels, timestamps.
    static let label: CGFloat = 12
    /// 14pt. The default. Body copy, list rows, field help, most labels.
    static let copy: CGFloat = 14
    /// 16pt. Primary copy and every full-width control label: buttons, chips,
    /// field input. Also the iOS floor for text a patient types into.
    static let copyLarge: CGFloat = 16
    /// 18pt. A lede paragraph, a card headline, a metric value in a row.
    static let lede: CGFloat = 18
    /// 20pt. Section and card subheads — the top of the UI band.
    static let subhead: CGFloat = 20

    // The display band: 28pt and up, scaling from `.largeTitle` (1.69x at
    // AX5, measured) rather than the UI band's `.body` curve (2.81x). A
    // display line must be free to WRAP — `title()` sets `lineLimit(nil)` and
    // vertical `fixedSize` for exactly that — and a one-line readout that
    // cannot wrap takes `.lineLimit(1).minimumScaleFactor(0.7)`. Neither is
    // optional: at AX5 the onboarding hero already pushes its own wordmark
    // off the top of a screen with no ScrollView.
    /// 28pt. Screen titles. The bottom of the display band.
    static let displayS: CGFloat = 28
    /// 34pt. A hero line, an onboarding promise.
    static let displayM: CGFloat = 34
    /// 44pt. A single large figure.
    static let displayL: CGFloat = 44
    /// 54pt. The one-per-screen readout — the pain-scale number.
    static let displayXL: CGFloat = 54
}


// MARK: - Typography

/// The live Bold Text state every font rung reads at render time.
///
/// WHY THIS EXISTS. Measured on the iOS 26 simulator with ImageRenderer:
/// SwiftUI applies `legibilityWeight == .bold` to San Francisco (595 -> 631pt
/// for the same string) but NOT to `Font.custom` — Instrument Sans stayed at
/// 651pt with Bold Text on, with or without `.weight(_:)`. So the app has to
/// swap the file itself, and it has to do it at render time: a `static let`
/// font is evaluated once, and rebuilding the tree with `.id` would throw away
/// a half-answered check-in.
///
/// HOW. `@Environment(\.legibilityWeight)` is read once, at the root, by
/// `mpLegibilityBridge()`, which copies it here. Every rung below is a
/// computed property that reads `isBold`, and Observation records that read
/// inside whichever `body` evaluated the font, so flipping this re-renders
/// exactly the views that draw text and keeps all their @State. Verified in a
/// scratch app: a Text in a VStack and one inside a List both went
/// 650 -> 668 -> 650pt as the root's legibilityWeight toggled, with their
/// @State intact.
///
/// A tree without the bridge (a preview, an ImageRenderer, a harness) renders
/// at the regular mapping unless it seeds `isBold` itself.
@Observable
final class MPLegibility {
    var isBold = false
}

/// A named rung: size, default weight, the text style it scales with, and its
/// tracking. `View.mpFont(_:)` applies all four; `Font.copy` and friends give
/// the font alone for sites that only take a `Font`.
///
/// Tracking (points at the default size, scaled with the rung by
/// `@ScaledMetric`): label 0, copy -0.15, copyLarge -0.32, lede -0.47,
/// subhead -0.44, displayS -0.62, displayM/largeTitle -0.83, displayL -1.21,
/// displayXL -1.6. These are the console's --track-* rungs in points;
/// Instrument Sans wants negative tracking at size, not SF Display's positive.
struct MPType {
    let size: CGFloat
    let weight: Font.Weight
    let style: Font.TextStyle
    let kerning: CGFloat

    init(_ size: CGFloat, _ weight: Font.Weight = .regular,
         style: Font.TextStyle? = nil, kerning: CGFloat? = nil) {
        self.size = size
        self.weight = weight
        self.style = style ?? MPFont.textStyle(for: size)
        self.kerning = kerning ?? MPFont.kerning(for: size)
    }

    /// The same rung at another weight.
    func weight(_ w: Font.Weight) -> MPType { MPType(size, w, style: style, kerning: kerning) }

    /// The font, resolved against the live Bold Text state.
    var font: Font { Font.mp(size, weight: weight, relativeTo: style) }

    static let axis = MPType(MPSize.axis)
    static let label = MPType(MPSize.label)
    static let labelMedium = MPType(MPSize.label, .medium)
    static let copy = MPType(MPSize.copy)
    static let copyMedium = MPType(MPSize.copy, .medium)
    static let copyLarge = MPType(MPSize.copyLarge)
    static let copyLargeMedium = MPType(MPSize.copyLarge, .medium)
    static let lede = MPType(MPSize.lede)
    static let ledeMedium = MPType(MPSize.lede, .medium)
    static let ledeSemibold = MPType(MPSize.lede, .semibold)
    static let subhead = MPType(MPSize.subhead)
    static let subheadMedium = MPType(MPSize.subhead, .medium)
    static let subheadSemibold = MPType(MPSize.subhead, .semibold)
    static let displayS = MPType(MPSize.displayS, .semibold, style: .largeTitle)
    static let displayM = MPType(MPSize.displayM, .semibold, style: .largeTitle)
    static let displayL = MPType(MPSize.displayL, .semibold, style: .largeTitle)
    static let displayXL = MPType(MPSize.displayXL, .semibold, style: .largeTitle)
}

extension Font {
    /// The app's typeface, in one place so the face is one edit.
    ///
    /// Instrument Sans (SIL OFL 1.1), bundled at 400, 500 and 600, plus 700
    /// which is ONLY the Bold Text substitute for 600. It is the stand-in for
    /// the console's unlicensed reference face on both surfaces; the console
    /// loads the same cuts as woff2.
    ///
    /// Scales with Dynamic Type relative to the text style its size maps to
    /// (12 caption, 14 subheadline, 16 callout, 18 body, 20 title3, 28 title,
    /// 34+ largeTitle) unless `relativeTo` says otherwise. The size you type is
    /// the size at the default content category.
    ///
    /// Resolved at render time: this reads `MPFont.live`, so call it inside a
    /// `body`, never to initialise a stored `let`.
    static func mp(_ size: CGFloat, weight: Font.Weight = .regular,
                   relativeTo style: Font.TextStyle? = nil) -> Font {
        .custom(MPFont.name(for: weight), size: size,
                relativeTo: style ?? MPFont.textStyle(for: size))
    }

    // MARK: - The UI band
    //
    // Computed, not stored: each read resolves against Bold Text. Bare name
    // is 400, `Medium` 500, `Semibold` 600.

    /// 11pt regular. CHART AXIS LABELS ONLY. Pair with `MP.chartAxisLabel`.
    static var axis: Font { MPType.axis.font }
    /// 12pt / 400.
    static var label: Font { MPType.label.font }
    /// 12pt / 500. Pills, eyebrows, any 12pt that has to hold its own.
    static var labelMedium: Font { MPType.labelMedium.font }
    /// 12pt / 600.
    static var labelSemibold: Font { .mp(MPSize.label, weight: .semibold) }
    /// 14pt / 400 — the default text style of the app.
    static var copy: Font { MPType.copy.font }
    /// 14pt / 500.
    static var copyMedium: Font { MPType.copyMedium.font }
    /// 14pt / 600.
    static var copySemibold: Font { .mp(MPSize.copy, weight: .semibold) }
    /// 16pt / 400. Field input and primary copy.
    static var copyLarge: Font { MPType.copyLarge.font }
    /// 16pt / 500. Every full-width control label.
    static var copyLargeMedium: Font { MPType.copyLargeMedium.font }
    /// 16pt / 600.
    static var copyLargeSemibold: Font { .mp(MPSize.copyLarge, weight: .semibold) }
    /// 18pt / 400.
    static var lede: Font { MPType.lede.font }
    /// 18pt / 500.
    static var ledeMedium: Font { MPType.ledeMedium.font }
    /// 18pt / 600. A card headline that leads a screen.
    static var ledeSemibold: Font { MPType.ledeSemibold.font }
    /// 20pt / 400.
    static var subhead: Font { MPType.subhead.font }
    /// 20pt / 500.
    static var subheadMedium: Font { MPType.subheadMedium.font }
    /// 20pt / 600.
    static var subheadSemibold: Font { MPType.subheadSemibold.font }

    // MARK: - The display band (fluid)

    /// Display sizes scale from `.largeTitle`. The default weight is now 600
    /// (was 500): titles are the one place the app raises its voice.
    ///
    /// It does not clamp: `display(20)` would be a 20pt fluid font, which is
    /// a bug, not a size. Name a rung instead.
    static func display(_ size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        .custom(MPFont.name(for: weight), size: size, relativeTo: .largeTitle)
    }

    /// 28pt / 600, fluid. Screen titles.
    static var displayS: Font { .display(MPSize.displayS) }
    /// 34pt / 600, fluid.
    static var displayM: Font { .display(MPSize.displayM) }
    /// 44pt / 600, fluid.
    static var displayL: Font { .display(MPSize.displayL) }
    /// 54pt / 600, fluid. Guard it with `.lineLimit(1).minimumScaleFactor(0.7)`.
    static var displayXL: Font { .display(MPSize.displayXL) }
    // `Font.largeTitle` / `MPType.largeTitle` (aliases of displayM) are
    // DELETED: zero users, and the Font one shadowed the system's own
    // `Font.largeTitle`, so `.font(.largeTitle)` silently meant Instrument
    // Sans 34 instead of the system style. Use `.displayM`.

    // MARK: - Figures

    /// Numbers that have to line up: portfolio values, the recovery stats,
    /// the pain readout, an avatar's initials.
    ///
    /// `.custom(…, relativeTo:).monospacedDigit()` switches Instrument Sans's
    /// `tnum` on AND scales with Dynamic Type. Measured on the iOS 26
    /// simulator at 20pt: "1111111111" and "0000000000" both render 121pt wide
    /// (120/121 for Medium; proportional they are 77 vs 136), and at AX5 both
    /// 312pt. So the old fixed-size UIFontDescriptor path is gone, and a
    /// readout now grows with the patient's text size: guard one-line
    /// readouts with `.lineLimit(1).minimumScaleFactor(0.7)`.
    static func figures(_ size: CGFloat, weight: Font.Weight = .regular,
                        relativeTo style: Font.TextStyle? = nil) -> Font {
        Font.mp(size, weight: weight, relativeTo: style).monospacedDigit()
    }

    /// 12pt figures / 400.
    static var figuresLabel: Font { .figures(MPSize.label) }
    /// 14pt figures / 400.
    static var figuresCopy: Font { .figures(MPSize.copy) }
    /// 16pt figures / 500, a metric value inside a row.
    static var figuresCopyLarge: Font { .figures(MPSize.copyLarge, weight: .medium) }
    /// 18pt figures / 500, the headline metric.
    static var figuresLede: Font { .figures(MPSize.lede, weight: .medium) }
    /// 20pt figures / 500.
    static var figuresSubhead: Font { .figures(MPSize.subhead, weight: .medium) }
    /// 20pt figures / 600, a stat in a summary card.
    static var figuresSubheadSemibold: Font { .figures(MPSize.subhead, weight: .semibold) }
    /// A display-band readout, such as the pain-scale number. 600, and scaled
    /// on the `.largeTitle` curve.
    static func figuresDisplay(_ size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        figures(size, weight: weight, relativeTo: .largeTitle)
    }

    /// GLYPHS INSTRUMENT SANS DOES NOT HAVE. Its cmap has no U+00B1 `±`, no
    /// U+00B5 `µ`, no U+03BC `μ`, and no `≥`/`≤`/`′`/`″`. iOS has no
    /// unicode-range, so those fall back to San Francisco one glyph at a time,
    /// at a different width. A string that must carry one should use this, so
    /// the whole string is San Francisco and the faces cannot mix mid-number.
    /// (It does have `°`, `×`, `·`, `–`, `−`, `—`, `→`, `’` and `…`.) San
    /// Francisco follows Bold Text on its own.
    static func systemGlyphs(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: MPFont.systemWeight(for: weight)).monospacedDigit()
    }
}

enum MPFont {
    /// The typographic family name. The Medium and SemiBold files carry
    /// "Instrument Sans Medium"/"… SemiBold" as name ID 1 (the RIBBI split,
    /// with 16/17 = "Instrument Sans"/weight), so this resolves the Regular
    /// only — never pass it to `Font.custom`. CoreText does group all four
    /// files under it (`UIFont.fontNames(forFamilyName:)` lists all four),
    /// which is why `.fontWeight(.semibold)` on an `.mp` font now lands on
    /// the real SemiBold file (measured 668pt, same as naming it).
    static let family = "Instrument Sans"

    /// PostScript names — what `Font.custom` and `UIFont(name:size:)` match
    /// on. Read back from the bundled files with fontTools AND resolved on the
    /// simulator via `UIFont(name:size:)?.fontName`.
    static let regular = "InstrumentSans-Regular"
    static let medium = "InstrumentSans-Medium"
    /// Static wght=600, wdth=100 instance of the variable master.
    static let semibold = "InstrumentSans-SemiBold"
    /// Static wght=700 instance. Bold Text substitute for 600 ONLY.
    static let bold = "InstrumentSans-Bold"

    /// The live Bold Text state. Written by `mpLegibilityBridge()`, seeded at
    /// launch from `UIAccessibility.isBoldTextEnabled`.
    static let live = MPLegibility()

    /// Three weights ship, and Bold Text moves each up one file:
    ///
    ///     asked          normal      Bold Text
    ///     ≤ regular      Regular     Medium
    ///     medium         Medium      SemiBold
    ///     semibold+      SemiBold    Bold
    ///
    /// Anything heavier than semibold maps to SemiBold: 700 is not a weight
    /// the design uses, only the Bold Text step. Mapping (rather than naming a
    /// file per weight) matters because `Font.custom` with a name that does
    /// not resolve falls back to San Francisco silently.
    static func name(for weight: Font.Weight, bold: Bool) -> String {
        switch weight {
        case .ultraLight, .thin, .light, .regular: return bold ? medium : regular
        case .medium: return bold ? semibold : medium
        default: return bold ? self.bold : semibold
        }
    }

    /// The same, against the live state. Reading this inside a `body`
    /// subscribes that view to Bold Text changes.
    static func name(for weight: Font.Weight) -> String {
        name(for: weight, bold: live.isBold)
    }

    /// The ceiling for the `.system` path: 600, matching the bundled files.
    /// San Francisco applies Bold Text itself, so no bump here.
    static func systemWeight(for weight: Font.Weight) -> Font.Weight {
        switch weight {
        case .ultraLight, .thin, .light, .regular: return .regular
        case .medium: return .medium
        default: return .semibold
        }
    }

    /// Which Dynamic Type curve a rung scales on.
    static func textStyle(for size: CGFloat) -> Font.TextStyle {
        switch size {
        case ..<12: return .caption2
        case ..<14: return .caption
        case ..<16: return .subheadline
        case ..<18: return .callout
        case ..<20: return .body
        case ..<28: return .title3
        case ..<34: return .title
        default: return .largeTitle
        }
    }

    static func uiTextStyle(for style: Font.TextStyle) -> UIFont.TextStyle {
        switch style {
        case .largeTitle: return .largeTitle
        case .title: return .title1
        case .title2: return .title2
        case .title3: return .title3
        case .headline: return .headline
        case .subheadline: return .subheadline
        case .callout: return .callout
        case .footnote: return .footnote
        case .caption: return .caption1
        case .caption2: return .caption2
        default: return .body
        }
    }

    /// Tracking in points at the default size (see `MPType`).
    static func kerning(for size: CGFloat) -> CGFloat {
        switch size {
        case ..<13: return 0
        case ..<15: return -0.15
        case ..<17: return -0.32
        case ..<19: return -0.47
        case ..<28: return -0.44
        case ..<34: return -0.62
        case ..<44: return -0.83
        case ..<54: return -1.21
        default: return -1.6
        }
    }

    /// A UIKit font for the proxies: the bundled file for `weight` under the
    /// CURRENT Bold Text setting, scaled by UIFontMetrics for `style` at the
    /// CURRENT content size, optionally capped.
    @MainActor
    static func uiFont(_ size: CGFloat, _ weight: Font.Weight, style: UIFont.TextStyle,
                       maximumPointSize: CGFloat? = nil) -> UIFont {
        let file = name(for: weight, bold: UIAccessibility.isBoldTextEnabled)
        let base = UIFont(name: file, size: size)
            ?? .systemFont(ofSize: size, weight: weight == .regular ? .regular : .semibold)
        let metrics = UIFontMetrics(forTextStyle: style)
        if let cap = maximumPointSize {
            return metrics.scaledFont(for: base, maximumPointSize: cap)
        }
        return metrics.scaledFont(for: base)
    }

    /// The UIKit half of the app — navigation titles, the tab bar, the
    /// segmented control on Profile, bar button items — draws with the system
    /// face no matter what SwiftUI's `.font` says, so those proxies are set
    /// here.
    ///
    /// Font and kerning ONLY. No `UINavigationBarAppearance`, no background,
    /// tint or foreground colour: custom bar backgrounds interfere with the
    /// system scroll-edge effect and Liquid Glass, and every custom background
    /// is a surface whose contrast and Reduce Transparency behaviour we would
    /// then own by hand.
    ///
    /// Large title: 34pt / 600, kern -0.83, on the `.largeTitle` curve.
    /// Inline title: 17pt / 600, kern -0.4, on the `.headline` curve (17 is
    /// the system bar size, and the one off-ladder number the app keeps,
    /// because it has to match the system back button beside it), capped at
    /// 22pt. Verified on the iOS 26 simulator: a NavigationStack large title
    /// renders in Instrument Sans SemiBold through these proxies, 34pt at the
    /// default size and 58pt at AX5.
    ///
    /// DYNAMIC TYPE AND BOLD TEXT. A proxy's attributes are copied into a bar
    /// when the bar is created, and UIFontMetrics scales to the content size
    /// at the moment of the call. So MedPullApp re-runs this on
    /// `UIContentSizeCategory.didChangeNotification` and
    /// `UIAccessibility.boldTextStatusDidChangeNotification`, and this also
    /// walks the live windows and re-assigns the attributes on every existing
    /// `UINavigationBar`, so bars already on screen update too.
    ///
    /// At accessibility sizes the large title scales to 60pt; a long title
    /// does not wrap, it truncates — use `mpNavigationTitle(_:short:)`.
    @MainActor
    static func applyUIKitAppearance() {
        let large = uiFont(MPSize.displayM, .semibold, style: .largeTitle)
        // The system inline title barely grows with text size; uncapped, the
        // headline curve took it to 48pt at AX5 (measured) and the bar with it.
        let inline = uiFont(17, .semibold, style: .headline, maximumPointSize: 22)
        let largeAttrs: [NSAttributedString.Key: Any] = [
            .font: large, .kern: -0.83 * large.pointSize / MPSize.displayM,
        ]
        let inlineAttrs: [NSAttributedString.Key: Any] = [
            .font: inline, .kern: -0.4 * inline.pointSize / 17,
        ]
        let navProxy = UINavigationBar.appearance()
        navProxy.largeTitleTextAttributes = largeAttrs
        navProxy.titleTextAttributes = inlineAttrs

        let segNormal = uiFont(MPSize.copy, .regular, style: .subheadline, maximumPointSize: 28)
        let segSelected = uiFont(MPSize.copy, .medium, style: .subheadline, maximumPointSize: 28)
        UISegmentedControl.appearance().setTitleTextAttributes([.font: segNormal], for: .normal)
        UISegmentedControl.appearance().setTitleTextAttributes([.font: segSelected], for: .selected)
        // The tab bar does not grow its items with Dynamic Type (it shows the
        // large-content viewer instead), so its label is capped rather than
        // allowed to overflow a ~75pt item.
        let tab = uiFont(MPSize.label, .medium, style: .caption1, maximumPointSize: 15)
        UITabBarItem.appearance().setTitleTextAttributes([.font: tab], for: .normal)
        let barButton = uiFont(MPSize.copyLarge, .regular, style: .callout)
        UIBarButtonItem.appearance().setTitleTextAttributes([.font: barButton], for: .normal)

        // Bars that already exist keep the attributes they were created with.
        for scene in UIApplication.shared.connectedScenes {
            guard let windowScene = scene as? UIWindowScene else { continue }
            for window in windowScene.windows {
                forEachNavigationBar(in: window) { bar in
                    bar.largeTitleTextAttributes = largeAttrs
                    bar.titleTextAttributes = inlineAttrs
                    bar.setNeedsLayout()
                }
            }
        }
    }

    @MainActor
    private static func forEachNavigationBar(in view: UIView, _ body: (UINavigationBar) -> Void) {
        if let bar = view as? UINavigationBar { body(bar) }
        for sub in view.subviews { forEachNavigationBar(in: sub, body) }
    }

    /// Launch-time wiring: seed Bold Text, set the proxies, and keep both in
    /// step with Settings. Called once from the app delegate.
    @MainActor
    static func startObservingAccessibility() {
        live.isBold = UIAccessibility.isBoldTextEnabled
        applyUIKitAppearance()
        let center = NotificationCenter.default
        for name in [UIAccessibility.boldTextStatusDidChangeNotification,
                     UIContentSizeCategory.didChangeNotification] {
            center.addObserver(forName: name, object: nil, queue: .main) { _ in
                MainActor.assumeIsolated {
                    live.isBold = UIAccessibility.isBoldTextEnabled
                    applyUIKitAppearance()
                }
            }
        }
    }
}

/// Copies the environment's legibility weight into `MPFont.live`.
private struct MPLegibilityBridge: ViewModifier {
    @Environment(\.legibilityWeight) private var legibilityWeight

    func body(content: Content) -> some View {
        content.onChange(of: legibilityWeight, initial: true) { _, weight in
            let bold = weight == .bold
            if MPFont.live.isBold != bold { MPFont.live.isBold = bold }
        }
    }
}

/// Font + Dynamic-Type-scaled tracking for one rung.
private struct MPFontModifier: ViewModifier {
    let type: MPType
    @ScaledMetric private var kerning: CGFloat

    init(_ type: MPType) {
        self.type = type
        _kerning = ScaledMetric(wrappedValue: type.kerning, relativeTo: type.style)
    }

    func body(content: Content) -> some View {
        content.font(type.font).kerning(kerning)
    }
}

extension View {
    /// Apply at the app root (and at any other root, e.g. a harness). Reads
    /// `@Environment(\.legibilityWeight)` and publishes it to every font rung.
    func mpLegibilityBridge() -> some View {
        modifier(MPLegibilityBridge())
    }

    /// A rung with its tracking: `.mpFont(.copy)`,
    /// `.mpFont(.lede.weight(.semibold))`. Prefer this to `.font(.copy)` for
    /// new code; both follow Bold Text and Dynamic Type.
    func mpFont(_ type: MPType) -> some View {
        modifier(MPFontModifier(type))
    }

    /// A navigation title that stays whole at accessibility sizes: a large
    /// title does not wrap, so at AX sizes (60pt at AX5) it swaps to `short`.
    /// "Hi, Maximilian" -> "Today"; "Health" needs no short form.
    func mpNavigationTitle(_ title: String, short: String? = nil) -> some View {
        modifier(MPNavigationTitle(title: title, short: short))
    }

    /// The console's `.micro` eyebrow: uppercase, tracked out, muted.
    ///
    /// Real capitals, not small caps — Instrument Sans has no `smcp` in its
    /// GSUB (it carries `case`, `tnum` and ss01-ss12), so
    /// `.textCase(.uppercase)` is the whole mechanism. Tracking is the
    /// console's `--track-eyebrow` +0.06em, which at 12pt is 0.72pt.
    ///
    /// 12pt, `muted` (5.39:1 light / 4.91:1 dark on panel), never `faint`.
    /// ONE PER SCREEN: that is the uppercase budget.
    func eyebrow() -> some View {
        self.font(.labelMedium)
            .textCase(.uppercase)
            .kerning(0.72)
            .foregroundStyle(MP.muted)
    }

    /// A display-band title: fluid, `ink`, wraps freely, tracked per rung.
    /// 600 by default (was 500); pass `weight: .medium` to keep a line at the
    /// old voice. Pass `MPSize` values, not literals.
    func title(_ size: CGFloat = MPSize.displayS, weight: Font.Weight = .semibold) -> some View {
        self.mpFont(MPType(size, weight, style: .largeTitle))
            .foregroundStyle(MP.ink)
            .fixedSize(horizontal: false, vertical: true)
            .lineLimit(nil)
    }

    /// A UI-band line with its rung's tracking: `.copy()`, `.copy(MPSize.lede,
    /// weight: .medium)`. Colour is left to the call site.
    func copy(_ size: CGFloat = MPSize.copy, weight: Font.Weight = .regular) -> some View {
        self.mpFont(MPType(size, weight))
    }
}

private struct MPNavigationTitle: ViewModifier {
    let title: String
    let short: String?
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    func body(content: Content) -> some View {
        content.navigationTitle(dynamicTypeSize.isAccessibilitySize ? (short ?? title) : title)
    }
}
