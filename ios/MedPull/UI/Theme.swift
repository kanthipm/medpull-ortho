import Observation
import SwiftUI
import UIKit

/// The design tokens, shared with the console (frontend/src/index.css) and
/// taken from medpull.org: warm neutrals, a near-black primary capsule, the
/// site's sage as the brand fill, clay/amber/sage/periwinkle status pills,
/// lime accent dots, and earthy gradient tiles. Light is the default; dark
/// follows the site's retired dark theme in structure (warm-neutral surfaces,
/// low-alpha fills, no bright borders) and keeps the same gradients and lime.
///
/// Every hex below is the hex the console's `:root` / `.dark` blocks resolve
/// to, so the app and the console read as one product. Ratios are WCAG
/// (sRGB, 0.04045 threshold), light / dark:
///
///     ink      #141414 / #F5F5F7   18.42 on panel / 15.63 on dark panel
///     body     #585B58 / #A1A1A6    6.88 / 6.61
///     muted    #636662 / #8E8E93    5.82 / 5.22 (5.19 / 4.63 on soft)
///     lineStr  #8A8C88 / #78787D    3.39 / 3.87 — field boundaries
///     brand    #4A663E / #5A7D4A    white on it 6.44 / 4.70
///     brandInk #3F5F33 / #B7D68A    7.25 / 10.53
enum MP {
    /// One dynamic UIColor per token: the trait closure is the only place the
    /// mode is read. `lightHigh`/`darkHigh` are the Increase Contrast
    /// substitutions, the same tokens the console strengthens under
    /// `@media (prefers-contrast: more)`.
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

    /// #141414 / #F5F5F7.
    static let ink = pair((20, 20, 20), (245, 245, 247))
    /// #585B58 / #A1A1A6. 6.88 / 6.14 on panel/soft light, 6.61 / 5.87 dark.
    static let body = pair((88, 91, 88), (161, 161, 166))
    /// #636662 / #8E8E93. Secondary text and placeholders: 5.82 / 5.19 light,
    /// 5.22 / 4.63 dark on panel / soft.
    static let muted = pair((99, 102, 98), (142, 142, 147))
    /// #A6A8A4 / #58585D. NON-TEXT, inactive or decorative only.
    static let faint = pair((166, 168, 164), (88, 88, 93),
                            lightHigh: (99, 102, 98), darkHigh: (142, 142, 147))

    // MARK: - Rules

    /// Ink at .08 on white / white at .09 on dark. Decorative inset dividers.
    static let hairline = pair((236, 236, 236), (44, 44, 47),
                               lightHigh: (196, 197, 193), darkHigh: (88, 88, 93))
    /// Ink at .14 / #3A3A3D. A quiet structural rule; cards separate by fill
    /// and shadow, never by a bright border.
    static let line = pair((222, 222, 222), (58, 58, 61),
                           lightHigh: (138, 140, 136), darkHigh: (120, 120, 125))
    /// #8A8C88 / #78787D. The boundary that is a control's only cue (field
    /// borders): 3.39 on light panel, 3.87 on dark panel.
    static let lineStrong = pair((138, 140, 136), (120, 120, 125))

    // MARK: - Surfaces

    /// #FBFBF9 / #0B0B0C — the site's hero canvas.
    static let canvas = pair((251, 251, 249), (11, 11, 12))
    /// Warm fill .10 over white / #262628.
    static let soft = pair((242, 242, 240), (38, 38, 40))
    /// #FFFFFF / #1C1C1E.
    static let panel = pair((255, 255, 255), (28, 28, 30))
    /// Slider and progress troughs: the site's fill-strong.
    static let track = pair((227, 227, 224), (52, 52, 55))
    /// The disabled pair: 5.19:1 light / 4.63:1 dark.
    static let disabledFill = pair((242, 242, 240), (38, 38, 40))
    static let disabledInk = pair((99, 102, 98), (142, 142, 147))

    // MARK: - Primary action — the site's near-black capsule

    /// #141414 light, #F5F5F7 dark (the capsule inverts).
    static let action = pair((20, 20, 20), (245, 245, 247))
    /// The radial highlight at the top of the capsule.
    static let actionTop = pair((58, 58, 58), (255, 255, 255))
    /// White on the light capsule (18.42), ink on the dark one (16.92).
    static let onAction = pair((255, 255, 255), (20, 20, 20))

    // MARK: - Brand — the site's sage

    /// #4A663E / #5A7D4A. A FILL: outgoing message bubbles, switches,
    /// "verified" marks, a selected answer. White on it 6.44 / 4.70.
    static let brand = pair((74, 102, 62), (90, 125, 74))
    static let onBrand = pair((255, 255, 255), (255, 255, 255))
    /// #3F5F33 / #B7D68A. Links, active labels, sage text and glyphs:
    /// 7.25 / 10.53 on panel, 6.27 / 7.98 on `brandTint`.
    static let brandInk = pair((63, 95, 51), (183, 214, 138))
    /// Pressed fill: #334D29 / #4A663E (white 8.9 / 6.44).
    static let brandDeep = pair((51, 77, 41), (74, 102, 62))
    /// #E9F1E4 / #2C3428.
    static let brandTint = pair((233, 241, 228), (44, 52, 40))
    /// #DBE8D3 / #35402F. `brandInk` on it: 5.8 / 7.1.
    static let brandTintStrong = pair((219, 232, 211), (53, 64, 47))
    static let brandInkPressed = pair((51, 77, 41), (183, 214, 138))
    /// A "reached" mark on a `track` trough (progress dots, a filled step).
    static let stateFill = pair((74, 102, 62), (159, 214, 122))

    // MARK: - Live / adherent — the site's "ok" green

    static let teal = pair((95, 127, 79), (90, 125, 74))
    static let onTeal = pair((255, 255, 255), (255, 255, 255))
    /// #43712F / #9FD67A: 5.77 / 10.03.
    static let tealInk = pair((67, 113, 47), (159, 214, 122))
    static let tealGraphic = pair((95, 127, 79), (159, 214, 122))
    static let tealTint = pair((231, 239, 225), (45, 54, 40))

    // MARK: - Accent

    /// #D4F14A. Dots, "now" markers, the primary capsule's dot. Never text.
    static let lime = Color(red: 212 / 255, green: 241 / 255, blue: 74 / 255)

    // MARK: - Secondary text on a tinted card

    /// `body` on the briefing wash and on status tints (5.7 or better).
    static let onTintSecondary = body

    // MARK: - Fog — the soft colour fields behind the glass

    /// The site's --fog-1..5, strong in light, quiet in dark.
    static let fogSage = pair((143, 174, 116), (143, 174, 116), lightAlpha: 0.42, darkAlpha: 0.16)
    static let fogAmber = pair((236, 199, 110), (236, 199, 110), lightAlpha: 0.40, darkAlpha: 0.09)
    static let fogClay = pair((233, 160, 125), (233, 160, 125), lightAlpha: 0.34, darkAlpha: 0.09)
    static let fogLilac = pair((154, 163, 220), (154, 163, 220), lightAlpha: 0.36, darkAlpha: 0.15)
    static let fogMint = pair((120, 190, 175), (120, 190, 175), lightAlpha: 0.32, darkAlpha: 0.09)
    /// Kept for older call sites: the lilac field.
    static let ambient = fogLilac
    static let ambientTeal = fogMint

    // MARK: - Glass

    /// The card fill, top and bottom of its 160° gradient (the console's
    /// --glass-card), and the light-catching rim.
    static let glassTop = pair((255, 255, 255), (36, 36, 40), lightAlpha: 0.92, darkAlpha: 0.94)
    static let glassBottom = pair((255, 255, 255), (28, 28, 30), lightAlpha: 0.78, darkAlpha: 0.9)
    static let glassRim = pair((255, 255, 255), (255, 255, 255), lightAlpha: 0.85, darkAlpha: 0.06)
    /// Solid glass, for captions on gradient tiles and floating rows.
    static let glassSolidTop = pair((255, 255, 255), (46, 46, 50), lightAlpha: 0.95, darkAlpha: 0.96)
    static let glassSolidBottom = pair((255, 255, 255), (34, 34, 38), lightAlpha: 0.84, darkAlpha: 0.92)
    /// The half-point hairline around a floating surface.
    static let glassRing = pair((20, 20, 20), (0, 0, 0), lightAlpha: 0.10, darkAlpha: 0.5)
    /// The shadow tint for glass (ink in light, black in dark).
    static let shadow = pair((20, 20, 20), (0, 0, 0), lightAlpha: 1, darkAlpha: 1)
    /// The site's recessed / tinted fills.
    static let fill = pair((120, 120, 110), (255, 255, 255), lightAlpha: 0.10, darkAlpha: 0.07)
    static let fillStrong = pair((120, 120, 110), (255, 255, 255), lightAlpha: 0.18, darkAlpha: 0.12)

    // MARK: - Icon tiles — the site's gradient glyph squares

    /// The four families, named for their old slots. Hue is category, never
    /// state:
    ///   blue   -> amber  communication, check-ins, engagement
    ///   teal   -> sage   activity, mobility
    ///   indigo -> lilac  sleep, trajectory, AI
    ///   violet -> clay   vitals, medication, wound, care plan
    static let catBlue = pair((124, 93, 10), (243, 196, 106))
    static let catBlueTint = pair((248, 240, 216), (62, 52, 38))
    static let catTeal = brandInk
    static let catTealTint = brandTint
    static let catIndigo = pair((84, 78, 142), (179, 174, 240))
    static let catIndigoTint = pair((236, 235, 245), (44, 43, 66))
    static let catViolet = pair((122, 89, 70), (224, 180, 154))
    static let catVioletTint = pair((244, 236, 231), (58, 44, 38))

    enum Category: CaseIterable { case blue, teal, indigo, violet }

    /// Ink for a glyph drawn in a category colour on its own (not in a tile).
    static func categoryInk(_ c: Category) -> Color {
        switch c {
        case .blue: return catBlue
        case .teal: return catTeal
        case .indigo: return catIndigo
        case .violet: return catViolet
        }
    }

    /// A soft category fill, for the few places a flat tint is wanted.
    static func categoryTint(_ c: Category) -> Color {
        switch c {
        case .blue: return catBlueTint
        case .teal: return catTealTint
        case .indigo: return catIndigoTint
        case .violet: return catVioletTint
        }
    }

    /// The gradient behind a category's tile.
    static func categoryGradient(_ c: Category) -> MPGradient {
        switch c {
        case .blue: return .amber
        case .teal: return .sage
        case .indigo: return .lilac
        case .violet: return .clay
        }
    }

    // MARK: - Status — the site's pills, deepened to clear AA on their tints

    /// high #B04A26 on #FBECE6 4.73 | #FF9477 on #402B28 6.12
    static let riskHigh = pair((176, 74, 38), (255, 148, 119))
    static let riskHighBg = pair((251, 236, 230), (64, 43, 40))
    static let riskHighPressed = pair((140, 56, 26), (255, 148, 119))
    /// Ink for a SOLID `riskHigh` fill: white light (5.45), ink dark.
    static let onRiskHigh = pair((255, 255, 255), (20, 20, 20))
    /// med #7C5D0A on #F8F0D8 5.38 | #F3C46A on #3E3426 7.49
    static let riskMed = pair((124, 93, 10), (243, 196, 106))
    static let riskMedBg = pair((248, 240, 216), (62, 52, 38))
    /// low #43712F on #E7EFE1 4.90 | #9FD67A on #2D3628 7.41
    static let riskLow = pair((67, 113, 47), (159, 214, 122))
    static let riskLowBg = pair((231, 239, 225), (45, 54, 40))
    /// missing #4C5680 on #E8EAF3 5.93 | #AAB3E6 on #303240 6.22
    static let riskMissing = pair((76, 86, 128), (170, 179, 230))
    static let riskMissingBg = pair((232, 234, 243), (48, 50, 64))

    // MARK: - Overlays

    static let overlayPanel = pair((255, 255, 255), (36, 36, 40))
    static let overlayBorder = pair((222, 222, 222), (58, 58, 61))
    /// The site's dialog backdrop: warm and light.
    static let scrim = pair((30, 30, 25), (0, 0, 0), lightAlpha: 0.34, darkAlpha: 0.55)

    // MARK: - Charts (sage and lilac; the dash and label carry identity)

    static let chartS1 = pair((74, 102, 62), (183, 214, 138))
    static let chartS2 = pair((84, 78, 142), (179, 174, 240))
    static let chartSeq: [Color] = [
        pair((238, 243, 233), (44, 52, 40)),
        pair((207, 224, 194), (63, 90, 51)),
        pair((157, 189, 134), (95, 127, 79)),
        pair((95, 127, 79), (143, 180, 111)),
        pair((63, 95, 51), (197, 224, 155)),
    ]
    static let chartGrid = pair((236, 236, 236), (44, 44, 47),
                                lightHigh: (138, 140, 136), darkHigh: (120, 120, 125))
    static let chartAxisLabel = pair((99, 102, 98), (142, 142, 147))
    static let chartRefLine = pair((138, 140, 136), (120, 120, 125))

    // MARK: - Radii — the site's

    /// Cards and tiles: 26pt continuous.
    static let radiusSurface: CGFloat = 26
    /// Inner rows, menus, the check-in scale cells: 18.
    static let radiusControl: CGFloat = 18
    /// Fields and compact controls: 14.
    static let radiusThumb: CGFloat = 14
    /// The 30pt icon tile: 9.
    static let radiusTile: CGFloat = 9
    /// The fog canvas and big panels: 34.
    static let radiusCanvas: CGFloat = 34

    /// The separator between two facts: "Day 8 · Total Knee Replacement".
    /// Outfit draws "·" 0.13em wide with no sidebearings, so the dot is held
    /// off each word by a thin space (Outfit has none; iOS takes U+2009 from
    /// San Francisco).
    static let dot = " \u{2009}·\u{2009} "
    /// The same dot opening a trailing fact inside an HStack.
    static let dotLead = "·\u{2009} "

    /// Always `.continuous`.
    static let surfaceShape = RoundedRectangle(cornerRadius: radiusSurface, style: .continuous)
    static let controlShape = RoundedRectangle(cornerRadius: radiusControl, style: .continuous)
    static let thumbShape = RoundedRectangle(cornerRadius: radiusThumb, style: .continuous)
    static let tileShape = RoundedRectangle(cornerRadius: radiusTile, style: .continuous)
    static let canvasShape = RoundedRectangle(cornerRadius: radiusCanvas, style: .continuous)
    /// Every button and pill.
    static let capsuleShape = Capsule(style: .continuous)
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

// MARK: - Typesetting

extension String {
    /// Straight apostrophes turned into typographic ones for display. Server
    /// copy keeps plain ones because it is also sent by text, where a curly
    /// apostrophe can push a message into a costlier encoding.
    var typeset: String {
        replacingOccurrences(of: "(\\w)'(\\w)", with: "$1\u{2019}$2", options: .regularExpression)
    }
}

// MARK: - Gradients

/// The site's grainy gradient tiles: dark at the top, where white text sits
/// (every top stop is 5.6:1 or better against white, 7.1 or better under the
/// tile scrim), light at the bottom, where art and solid-glass captions sit.
/// The same in both modes.
enum MPGradient: CaseIterable {
    case sage, meadow, amber, clay, dusk, lilac, mint

    private static func c(_ r: Double, _ g: Double, _ b: Double) -> Color {
        Color(red: r / 255, green: g / 255, blue: b / 255)
    }

    var stops: [Gradient.Stop] {
        switch self {
        case .sage: return [.init(color: Self.c(64, 90, 54), location: 0), .init(color: Self.c(95, 125, 76), location: 0.52), .init(color: Self.c(174, 191, 135), location: 1)]
        case .meadow: return [.init(color: Self.c(63, 87, 53), location: 0), .init(color: Self.c(88, 117, 72), location: 0.42), .init(color: Self.c(138, 165, 106), location: 0.78), .init(color: Self.c(184, 185, 119), location: 1)]
        case .amber: return [.init(color: Self.c(125, 100, 32), location: 0), .init(color: Self.c(168, 140, 53), location: 0.42), .init(color: Self.c(205, 180, 106), location: 1)]
        case .clay: return [.init(color: Self.c(122, 89, 70), location: 0), .init(color: Self.c(162, 122, 100), location: 0.48), .init(color: Self.c(201, 168, 147), location: 1)]
        case .dusk: return [.init(color: Self.c(154, 90, 57), location: 0), .init(color: Self.c(168, 128, 122), location: 0.42), .init(color: Self.c(107, 127, 160), location: 1)]
        case .lilac: return [.init(color: Self.c(64, 69, 127), location: 0), .init(color: Self.c(84, 78, 142), location: 0.62), .init(color: Self.c(128, 107, 140), location: 1)]
        case .mint: return [.init(color: Self.c(63, 127, 116), location: 0), .init(color: Self.c(120, 187, 168), location: 0.5), .init(color: Self.c(212, 224, 166), location: 1)]
        }
    }

    /// The warm glow that pools at the bottom of some tiles.
    var glow: (Color, UnitPoint)? {
        switch self {
        case .sage: return (Self.c(230, 219, 124), UnitPoint(x: 0.5, y: 1.08))
        case .meadow: return (Self.c(217, 207, 126), UnitPoint(x: 0.7, y: 1.1))
        case .amber: return (Self.c(238, 194, 122), UnitPoint(x: 0.25, y: 1.0))
        case .clay: return (Self.c(227, 170, 102), UnitPoint(x: 0.3, y: 1.0))
        default: return nil
        }
    }

    /// The top stop, for anything that needs one flat colour of the family.
    var top: Color { stops[0].color }
}

// MARK: - Motion

/// THE APP'S ONE MOTION VOCABULARY — the site's. Every duration lives here.
///
/// The site moves with two curves: an ease (cubic-bezier .2, .8, .2, 1) for
/// entrances and colour, and a spring with a small overshoot for buttons,
/// tabs and chips. Entrances are opacity plus a short rise, never a blur.
/// Loops (drifting fog, a light travelling a line, breathing bars) are
/// transform-only and stop under Reduce Motion.
///
/// SwiftUI does NOT honour `accessibilityReduceMotion` for explicit
/// animations, so a call site reads the environment value and goes through
/// `MPMotion.gated(_:reduceMotion:)` (nil: no animation) or
/// `MPMotion.transition(reduceMotion:)` (a 150ms cross-fade instead).
enum MPMotion {
    /// The site's ease, as a timing curve.
    static func ease(_ duration: Double) -> Animation {
        .timingCurve(0.2, 0.8, 0.2, 1, duration: duration)
    }
    /// 150ms ease-out. The reduce-motion substitute.
    static let crossFade = Animation.easeOut(duration: 0.15)
    /// A step within a screen (the check-in questions).
    static let step = ease(0.32)
    /// Leaving.
    static let exit = Animation.easeIn(duration: 0.18)
    /// A small state change (step dots, a toggle's knock-on).
    static let state = ease(0.25)
    /// Entering — a surface appearing: 600ms on the site's ease.
    static let enter = ease(0.6)
    /// A completion state settling in (check-in sent).
    static let settle = Animation.spring(response: 0.45, dampingFraction: 0.72)
    /// A morph between two shapes.
    static let morph = ease(0.36)
    /// The site's spring: buttons, chips, thumbs. A small overshoot.
    static let press = Animation.spring(response: 0.32, dampingFraction: 0.68)
    /// A layout change: a card expanding, a row inserting.
    static let layout = Animation.spring(response: 0.42, dampingFraction: 0.82)
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
/// for the same string) but NOT to `Font.custom` — a bundled face keeps its
/// width with Bold Text on, with or without `.weight(_:)`. So the app has to
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
/// `@ScaledMetric`) is the site's, in points: body barely closes, titles
/// close, display type closes hard (-0.04em to -0.05em).
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
    static let displayS = MPType(MPSize.displayS, .light, style: .largeTitle)
    static let displayM = MPType(MPSize.displayM, .light, style: .largeTitle)
    static let displayL = MPType(MPSize.displayL, .light, style: .largeTitle)
    static let displayXL = MPType(MPSize.displayXL, .light, style: .largeTitle)
}

extension Font {
    /// The app's typeface, in one place so the face is one edit.
    ///
    /// Outfit (SIL OFL 1.1), the medpull.org face, bundled at 200, 300, 400
    /// and 500, plus 600 which is ONLY the Bold Text step for 500. The
    /// console loads the same family as a variable woff2.
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

    /// Display sizes scale from `.largeTitle`, in the site's light display
    /// weight (300): big type stays quiet and lets size carry it.
    ///
    /// It does not clamp: `display(20)` would be a 20pt fluid font, which is
    /// a bug, not a size. Name a rung instead.
    static func display(_ size: CGFloat, weight: Font.Weight = .light) -> Font {
        .custom(MPFont.name(for: weight), size: size, relativeTo: .largeTitle)
    }

    /// 28pt / 300, fluid. Screen titles.
    static var displayS: Font { .display(MPSize.displayS) }
    /// 34pt / 300, fluid.
    static var displayM: Font { .display(MPSize.displayM) }
    /// 44pt / 300, fluid.
    static var displayL: Font { .display(MPSize.displayL) }
    /// 54pt / 300, fluid. Guard it with `.lineLimit(1).minimumScaleFactor(0.7)`.
    static var displayXL: Font { .display(MPSize.displayXL) }
    // `Font.largeTitle` / `MPType.largeTitle` (aliases of displayM) are
    // DELETED: zero users, and the Font one shadowed the system's own
    // `Font.largeTitle`. Use `.displayM`.

    // MARK: - Figures

    /// Numbers that have to line up: portfolio values, the recovery stats,
    /// the pain readout, an avatar's initials.
    ///
    /// `.custom(…, relativeTo:).monospacedDigit()` switches Outfit's `tnum` on
    /// AND scales with Dynamic Type, so a readout grows with the patient's
    /// text size: guard one-line readouts with
    /// `.lineLimit(1).minimumScaleFactor(0.7)`.
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
    /// A display-band readout, such as the pain-scale number: the site's big
    /// light number, scaled on the `.largeTitle` curve.
    static func figuresDisplay(_ size: CGFloat, weight: Font.Weight = .light) -> Font {
        figures(size, weight: weight, relativeTo: .largeTitle)
    }

    /// GLYPHS OUTFIT DOES NOT HAVE: `≥`, `≤`, `≈`, `′`, `″` and the thin
    /// spaces. iOS has no unicode-range, so those fall back to San Francisco
    /// one glyph at a time. A string that must carry one can use this, so the
    /// whole string is San Francisco. (Outfit does have `±`, `µ`, `°`, `×`,
    /// `·`, `–`, `−`, `—`, `’` and `…`.) San Francisco follows Bold Text on
    /// its own.
    static func systemGlyphs(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: MPFont.systemWeight(for: weight)).monospacedDigit()
    }
}

enum MPFont {
    /// The typographic family name. Never pass it to `Font.custom`: each
    /// static file carries its own PostScript name, listed below.
    static let family = "Outfit"

    /// PostScript names — what `Font.custom` and `UIFont(name:size:)` match
    /// on, read back from the bundled files with fontTools.
    static let extraLight = "Outfit-ExtraLight"
    static let light = "Outfit-Light"
    static let regular = "Outfit-Regular"
    static let medium = "Outfit-Medium"
    /// Static wght=600. The Bold Text step for 500 ONLY; the design never
    /// asks for 600.
    static let semibold = "Outfit-SemiBold"

    /// The live Bold Text state. Written by `mpLegibilityBridge()`, seeded at
    /// launch from `UIAccessibility.isBoldTextEnabled`.
    static let live = MPLegibility()

    /// The site never sets UI type heavier than 500, so every weight maps
    /// onto the five files, and Bold Text moves each up one:
    ///
    ///     asked          normal       Bold Text
    ///     ultraLight/thin ExtraLight  Light
    ///     light          Light        Regular
    ///     regular        Regular      Medium
    ///     medium+        Medium       SemiBold
    ///
    /// Mapping (rather than naming a file per weight) matters because
    /// `Font.custom` with a name that does not resolve falls back to San
    /// Francisco silently.
    static func name(for weight: Font.Weight, bold: Bool) -> String {
        switch weight {
        case .ultraLight, .thin: return bold ? light : extraLight
        case .light: return bold ? regular : light
        case .regular: return bold ? medium : regular
        default: return bold ? semibold : medium
        }
    }

    /// The same, against the live state. Reading this inside a `body`
    /// subscribes that view to Bold Text changes.
    static func name(for weight: Font.Weight) -> String {
        name(for: weight, bold: live.isBold)
    }

    /// The `.system` path, matched to the bundled files (500 is the
    /// ceiling). San Francisco applies Bold Text itself, so no bump here.
    static func systemWeight(for weight: Font.Weight) -> Font.Weight {
        switch weight {
        case .ultraLight, .thin: return .ultraLight
        case .light: return .light
        case .regular: return .regular
        default: return .medium
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
        case ..<15: return -0.06
        case ..<17: return -0.1
        case ..<19: return -0.18
        case ..<28: return -0.4
        case ..<34: return -1.1
        case ..<44: return -1.4
        case ..<54: return -2.0
        default: return -2.7
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
            ?? .systemFont(ofSize: size, weight: weight == .regular ? .regular : .medium)
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
    /// Large title: 34pt / 300, kern -1.4, on the `.largeTitle` curve (the
    /// site's light display type). Inline title: 17pt / 500, kern -0.3, on
    /// the `.headline` curve (17 is
    /// the system bar size, and the one off-ladder number the app keeps,
    /// because it has to match the system back button beside it), capped at
    /// 22pt.
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
        let large = uiFont(MPSize.displayM, .light, style: .largeTitle)
        // The system inline title barely grows with text size; uncapped, the
        // headline curve took it to 48pt at AX5 (measured) and the bar with it.
        let inline = uiFont(17, .medium, style: .headline, maximumPointSize: 22)
        let largeAttrs: [NSAttributedString.Key: Any] = [
            .font: large, .kern: -1.4 * large.pointSize / MPSize.displayM,
        ]
        let inlineAttrs: [NSAttributedString.Key: Any] = [
            .font: inline, .kern: -0.3 * inline.pointSize / 17,
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
    /// Real capitals (`.textCase(.uppercase)`), tracked +0.06em, which at
    /// 12pt is 0.72pt. 12pt, `muted`, never `faint`.
    /// ONE PER SCREEN: that is the uppercase budget.
    func eyebrow() -> some View {
        self.font(.labelMedium)
            .textCase(.uppercase)
            .kerning(0.72)
            .foregroundStyle(MP.muted)
    }

    /// A display-band title: fluid, `ink`, wraps freely, tracked per rung, in
    /// the site's light display weight. Pass `MPSize` values, not literals.
    func title(_ size: CGFloat = MPSize.displayS, weight: Font.Weight = .light) -> some View {
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
