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
    // MARK: - Risk grid (re-derived; all four Material pairs were failing)

    /// 5.62:1 on panel, 4.83:1 on its own tint (was #E53935 on #FFEBEE, 3.70:1).
    static let riskHigh = pair((198, 40, 40), (255, 138, 135))
    /// Light solid / the 0.16 wash frozen over dark panel. 5.70:1 against
    /// `riskHigh` on dark, 4.83:1 on light.
    static let riskHighBg = pair((251, 234, 234), (58, 46, 52))
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

    /// Sheets, cards, panels — anything that holds content. 12pt.
    static let radiusSurface: CGFloat = 12
    /// Buttons, fields, chips, segments — anything you touch. 10pt.
    static let radiusControl: CGFloat = 10

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
/// Rules: 150-300ms, `easeOut` entering, `easeIn` leaving, no springs on
/// clinical content. SwiftUI does NOT honour `accessibilityReduceMotion` for
/// explicit animations — `.animation(_:value:)` and `withAnimation` run
/// regardless — so a call site reads the environment value and goes through
/// `MPMotion.gated(_:reduceMotion:)` (nil: no animation) or
/// `MPMotion.transition(reduceMotion:)` (a 150ms cross-fade instead).
///
/// `MPGlass` in Glass.swift still carries its own copies of `enter`, `exit`,
/// `morph` and `crossFade` with identical values; it should alias these.
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
/// That inversion is Apple's, not ours — in the system table AX5 body (53pt)
/// overtakes AX5 largeTitle (44pt) — and it is the reason the display band is
/// pinned to `.largeTitle`: on the old `.body` curve a 54pt readout reached
/// 150pt and took the screen with it. At AX sizes the hierarchy is carried by
/// weight, space and order, because the sizes converge no matter what we do.
///
/// Why raw numbers are named instead of banned: the six `.system(design:
/// .monospaced)` escapes hold column and chart alignment and cannot go
/// through `.mp`, so they need the same numbers. Use these constants there
/// (or `Font.mono…`) rather than retyping a literal.
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

extension Font {
    /// The app's typeface, in one place so the face is one edit.
    ///
    /// Instrument Sans (SIL OFL 1.1), bundled at weights 400 and 500 only.
    /// It is the measured-closest open substitute for the console's reference
    /// face, and it is the shared UI face on both surfaces: the console loads
    /// the same two cuts as woff2 from frontend/public/fonts.
    ///
    /// Why this fixes legibility without touching a single size: the earlier
    /// serif swap was mechanical and preserved every point size while dropping
    /// x-height 21.2% (sxHeight 400/1000 against San Francisco's 0.5078em),
    /// so an 11pt rung rendered an apparent 8.7px and a 9pt one 7.1px.
    /// (Written out rather than as call syntax: the sub-floor-size gate reads
    /// source text and counted this sentence as a live 9pt site.)
    /// Instrument Sans measures sxHeight 510/1000 = 0.5100em, within +0.4% of
    /// San Francisco, so the same numbers now render the size they claim.
    ///
    /// A missing file falls back to the system face, so a build that lost its
    /// resources is plain rather than broken — but silently, which is why the
    /// PostScript names below are verified against the bundled files rather
    /// than typed from the family name.
    ///
    /// PREFER A NAMED RUNG. `.mp(_:weight:)` stays because it is the primitive
    /// the rungs are built from and because 133 call sites still use it, but a
    /// new site should name a rung: the ladder is only frozen if nobody has to
    /// remember the numbers.
    ///
    /// This scales with Dynamic Type from `.body`, as `Font.custom(_:size:)`
    /// has since iOS 14 — measured 2.81x at AX5. The size you type is the
    /// size at the default content category, not the size on every device.
    static func mp(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .custom(MPFont.name(for: weight), size: size)
    }

    // MARK: - The UI band (frozen)
    //
    // Two cuts ship, so each rung has exactly two forms: the bare name is 400
    // and the `Medium` suffix is 500. There is no third form, and no call
    // site anywhere in the app names a weight above 500 any more — the count
    // was 53 when the `…Medium` rungs were added and it is 0 now. The
    // `…Medium` name IS the emphasis vocabulary.

    /// 11pt regular. CHART AXIS LABELS ONLY. Pair with `MP.chartAxisLabel`,
    /// never with `MP.faint`.
    static let axis = Font.mp(MPSize.axis)
    /// 12pt / 400.
    static let label = Font.mp(MPSize.label)
    /// 12pt / 500. Pills, eyebrows, any 12pt that has to hold its own.
    static let labelMedium = Font.mp(MPSize.label, weight: .medium)
    /// 14pt / 400 — the default text style of the app.
    static let copy = Font.mp(MPSize.copy)
    /// 14pt / 500.
    static let copyMedium = Font.mp(MPSize.copy, weight: .medium)
    /// 16pt / 400. Field input and primary copy.
    static let copyLarge = Font.mp(MPSize.copyLarge)
    /// 16pt / 500. Every full-width control label.
    static let copyLargeMedium = Font.mp(MPSize.copyLarge, weight: .medium)
    /// 18pt / 400.
    static let lede = Font.mp(MPSize.lede)
    /// 18pt / 500.
    static let ledeMedium = Font.mp(MPSize.lede, weight: .medium)
    /// 20pt / 400.
    static let subhead = Font.mp(MPSize.subhead)
    /// 20pt / 500.
    static let subheadMedium = Font.mp(MPSize.subhead, weight: .medium)

    // MARK: - The display band (fluid)

    /// Same face — there is one typeface on both surfaces now, and a display
    /// moment is made with size and space, not a second family. The default
    /// weight is `.medium` because 500 is the ceiling, and the size scales
    /// with Dynamic Type from `.largeTitle`, which is what makes this band
    /// fluid where the UI band is frozen.
    ///
    /// It does not clamp: `display(20)` would be a 20pt fluid font, which is
    /// a bug, not a size. Name a rung instead.
    static func display(_ size: CGFloat, weight: Font.Weight = .medium) -> Font {
        .custom(MPFont.name(for: weight), size: size, relativeTo: .largeTitle)
    }

    /// 28pt / 500, fluid. Screen titles.
    static let displayS = Font.display(MPSize.displayS)
    /// 34pt / 500, fluid.
    static let displayM = Font.display(MPSize.displayM)
    /// 44pt / 500, fluid.
    static let displayL = Font.display(MPSize.displayL)
    /// 54pt / 500, fluid. Guard it with
    /// `.lineLimit(1).minimumScaleFactor(0.7)`.
    static let displayXL = Font.display(MPSize.displayXL)

    // MARK: - The monospace escape

    /// THE SIX ESCAPES, and the glyph escape hatch.
    ///
    /// Two jobs, both real:
    ///  1. ALIGNMENT. A column of numbers, a chart readout and an avatar's
    ///     initials all need equal advance widths. Instrument Sans carries
    ///     `tnum` but SwiftUI gives no way to switch a feature on a
    ///     `Font.custom`, so these stay on the system monospace face.
    ///  2. GLYPHS INSTRUMENT SANS DOES NOT HAVE. Its cmap (501 glyphs) has no
    ///     U+00B1 `±`, no U+00B5 `µ`, no U+03BC `μ`, and no `≥`/`≤`/`′`/`″`.
    ///     iOS has no unicode-range mechanism, so those characters fall back
    ///     to San Francisco per-glyph, silently and at a different width —
    ///     one word in a second face mid-sentence. A string that must carry
    ///     `±` or `µ` goes through here, where the whole string is already
    ///     San Francisco and the mix cannot happen. (It does have `°`, `×`,
    ///     `·`, `–`, `—`, `→`, `’` and `…`, so those are safe inline.)
    ///
    /// The weight is clamped to the same 500 ceiling as `.mp`: `.system` is
    /// the one path that could still draw a real semibold.
    static func mono(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: MPFont.systemWeight(for: weight), design: .monospaced)
    }

    /// 12pt monospace / 400.
    static let monoLabel = Font.mono(MPSize.label)
    /// 14pt monospace / 400.
    static let monoCopy = Font.mono(MPSize.copy)
    /// 16pt monospace / 500 — a metric value inside a row.
    static let monoCopyLarge = Font.mono(MPSize.copyLarge, weight: .medium)
    /// 18pt monospace / 500 — the headline metric.
    static let monoLede = Font.mono(MPSize.lede, weight: .medium)
    /// 20pt monospace / 500.
    static let monoSubhead = Font.mono(MPSize.subhead, weight: .medium)
    /// A display-band monospace readout. Fixed, not fluid: `.system(size:)`
    /// has no `relativeTo`, and a tabular readout that grows is a readout
    /// that clips. Use it for the pain-scale number instead of
    /// `design: .rounded`, which is a third face on the screen.
    static func monoDisplay(_ size: CGFloat) -> Font {
        .system(size: size, weight: .medium, design: .monospaced)
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

    /// Two cuts ship: 400 and 500, and 500 is the ceiling. Two files means two
    /// buckets, so this maps the light half of `Font.Weight` to the Regular
    /// file and EVERYTHING ELSE to the Medium file.
    ///
    /// The migration crutch is gone: the case list used to spell out all four
    /// over-ceiling weight identifiers explicitly, for 53 call sites that
    /// asked for them. A live-code scan now finds ZERO of those call sites —
    /// the only occurrences left anywhere in ios/ are prose in four doc
    /// comments in other files. Spelling them out here was the last thing
    /// making the source lie about its own weights (and the last thing making
    /// the weight gate report 16 hits against this file), so the identifiers
    /// are out and the two buckets stay.
    ///
    /// The buckets CANNOT go, and that is not the same question as the clamp.
    /// `Font.Weight` is a struct, not an enum, so this switch needs a default
    /// no matter what, and `Font.mp(_:weight:)` takes a full `Font.Weight`
    /// across 133 call sites — narrowing that parameter to a two-case type is
    /// an API change, not a cleanup. Mapping down is also the only safe
    /// default: `Font.custom` with an unbundled PostScript name falls back to
    /// San Francisco SILENTLY, so a name that does not resolve here would put
    /// a third face mid-screen rather than fail to build. Nothing ever asks
    /// for a heavier FILE, so nothing is ever synthesised.
    static func name(for weight: Font.Weight) -> String {
        switch weight {
        case .ultraLight, .thin, .light, .regular: return regular
        default: return medium
        }
    }

    /// The same ceiling for the `.system` path, and this is the one that
    /// matters. `name(for:)` protects `.mp` by having no bolder file to name,
    /// but `.system(weight:)` asked for a weight above 500 draws a REAL San
    /// Francisco semibold — the single way a weight over the ceiling can still
    /// reach the screen. Every monospace escape goes through here.
    static func systemWeight(for weight: Font.Weight) -> Font.Weight {
        switch weight {
        case .ultraLight, .thin, .light, .regular: return .regular
        default: return .medium
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

        // On the ladder, including here. These were 17 / 14 / 14 / 10 / 17:
        // 17 is not a rung and 10 is under the floor. The tab title moves to
        // 12 rather than to 11, because 11 belongs to chart axis labels —
        // "Messages", the longest of the five, measures ~52pt of the ~75pt
        // each tab gets at the narrowest supported width.
        UINavigationBar.appearance().titleTextAttributes = [.font: font(MPSize.lede, .medium)]
        UISegmentedControl.appearance().setTitleTextAttributes([.font: font(MPSize.copy, .regular)], for: .normal)
        UISegmentedControl.appearance().setTitleTextAttributes([.font: font(MPSize.copy, .medium)], for: .selected)
        UITabBarItem.appearance().setTitleTextAttributes([.font: font(MPSize.label, .medium)], for: .normal)
        UIBarButtonItem.appearance().setTitleTextAttributes([.font: font(MPSize.copyLarge, .regular)], for: .normal)
    }
}

extension View {
    /// The console's `.micro` eyebrow: uppercase, tracked out, muted.
    ///
    /// Real capitals, not small caps — Instrument Sans has no `smcp` in its
    /// GSUB (it carries `case`, `tnum` and ss01-ss12), so
    /// `.textCase(.uppercase)` is the whole mechanism. Tracking is the
    /// console's `--track-eyebrow` +0.06em, which at 12pt is 0.72pt; the
    /// 1.0pt it used to carry was tuned to open up a serif's tight uppercase
    /// fitting and reads gappy on a neo-grotesque.
    ///
    /// Now 12pt, not 11: uppercase at 11pt was borrowing the axis-label
    /// exception for something a patient reads, and 11 is reserved. `muted`
    /// (5.39:1 light / 4.91:1 dark on panel) is the floor for it, never
    /// `faint`.
    ///
    /// ONE PER SCREEN. This is the uppercase budget, and it is spent the
    /// moment a second eyebrow appears on the same screen — HomeView has
    /// five today. Everything else that used to be an eyebrow is
    /// `.labelMedium` + `MP.muted`, sentence case.
    func eyebrow() -> some View {
        self.font(.labelMedium)
            .textCase(.uppercase)
            .kerning(0.72)
            .foregroundStyle(MP.muted)
    }

    /// A screen title: display band, fluid, `ink`, wraps freely.
    ///
    /// Tracking sits at zero here. The console's title and display tracking
    /// tokens are -0.02em and -0.03em; SwiftUI's `.kerning` is absolute
    /// points, so applying them means a per-rung number (-0.56pt at 28,
    /// -0.68 at 34) and that is a per-site judgement the screen agents make
    /// with the copy in front of them.
    ///
    /// The default moved 26 -> 28 because 26 is not a rung. Pass `MPSize`
    /// values, not literals: `.title(MPSize.displayM)`.
    func title(_ size: CGFloat = MPSize.displayS) -> some View {
        self.font(.display(size)).foregroundStyle(MP.ink)
            .fixedSize(horizontal: false, vertical: true)
            .lineLimit(nil)
    }
}
