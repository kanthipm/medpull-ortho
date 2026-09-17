import SwiftUI

/// The shared components, in the medpull.org language.
///
/// THE RULES THESE ENFORCE, so no screen has to remember them:
///  * A card is the site's glass card: a white gradient, a light-catching rim
///    and a soft layered shadow drawn on the SHAPE only (never on its text,
///    which would make scrolling expensive). Dark mode keeps the rim at 6%
///    white — never a bright border.
///  * The primary action is the near-black capsule with a lime dot; it
///    inverts to a light capsule in dark mode. Everything else is a warm
///    grey capsule, a white glass capsule, or sage text.
///  * Icon tiles, avatars and hero tiles are grainy earthy gradients with
///    white marks. Hue names a category, never a state: state is always a
///    pill with a word (and a dot).
///  * `MP.brand` (sage) is a FILL; sage text is `MP.brandInk`.
///  * `MP.faint` carries no text.
///  * Type comes from the ladder, read inside `body`, so Bold Text and
///    Dynamic Type reach every label.
///
/// CONTRAST (WCAG, light / dark):
///   primary     white on #141414 18.42; ink on #F5F5F7 16.92
///   tinted      ink on the warm fill 16.4 / 13.9
///   glass       ink on white glass 17.6 / 13.8
///   plain       brandInk on panel 7.25 / 10.53
///   destructive riskHigh on riskHighBg 4.73 / 6.12
///   disabled    disabledInk on disabledFill 5.19 / 4.63
///   pills       every status ink on its tint 4.73 or better
///   gradients   white on every tile's top band 5.65 or better (7.1 under the
///               scrim); white marks only below it

// MARK: - Tint context

private struct MPOnTintKey: EnvironmentKey {
    static let defaultValue = false
}

extension EnvironmentValues {
    /// True inside `Card(tint: true)`. Button styles and `.mpSecondary()`
    /// read it; set it yourself on any other tinted surface with `.mpOnTint()`.
    var mpOnTint: Bool {
        get { self[MPOnTintKey.self] }
        set { self[MPOnTintKey.self] = newValue }
    }
}

/// Secondary text that follows the ground it sits on.
private struct MPSecondaryInk: ViewModifier {
    @Environment(\.mpOnTint) private var onTint

    func body(content: Content) -> some View {
        content.foregroundStyle(onTint ? MP.onTintSecondary : MP.muted)
    }
}

extension View {
    /// Secondary text colour: `MP.muted` on glass and canvas, `MP.body` on a
    /// tinted card.
    func mpSecondary() -> some View { modifier(MPSecondaryInk()) }

    /// Marks a subtree as sitting on a tint (see `mpOnTint`).
    func mpOnTint(_ onTint: Bool = true) -> some View {
        environment(\.mpOnTint, onTint)
    }
}

// MARK: - Grain

/// The site's grain: a tileable noise texture blended soft-light over a
/// gradient (or as faint specks on a plain surface). Decorative; gone under
/// Reduce Transparency and Increase Contrast.
struct GrainOverlay: View {
    enum Kind { case gradient, surface }
    var kind: Kind = .gradient
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        if !reduceTransparency && contrast != .increased {
            switch kind {
            case .gradient:
                Image("Grain")
                    .resizable(resizingMode: .tile)
                    .blendMode(.softLight)
                    .opacity(0.7)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            case .surface:
                Image("GrainSoft")
                    .resizable(resizingMode: .tile)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
        }
    }
}

/// A grainy earthy gradient: the stops, the warm glow that pools at the
/// bottom, and the grain. Used by icon tiles, avatars and gradient tiles.
struct GradientFill: View {
    let gradient: MPGradient

    var body: some View {
        ZStack {
            // The site's 175° run: top to bottom, leaning a touch.
            LinearGradient(stops: gradient.stops,
                           startPoint: UnitPoint(x: 0.54, y: 0),
                           endPoint: UnitPoint(x: 0.46, y: 1))
            if let glow = gradient.glow {
                GeometryReader { proxy in
                    RadialGradient(colors: [glow.0, glow.0.opacity(0)],
                                   center: glow.1,
                                   startRadius: 0,
                                   endRadius: max(proxy.size.width, proxy.size.height) * 0.55)
                }
            }
            GrainOverlay()
        }
    }
}

// MARK: - Card

/// The site's glass card: a white gradient (the fog shows faintly through),
/// a light-catching rim, and the layered glass shadow. 26pt continuous.
struct Card<Content: View>: View {
    var padding: CGFloat = 16
    /// The narrative card (recovery summary): the site's briefing wash, lilac
    /// into amber, over the glass. Secondary text inside is `body`.
    var tint: Bool = false
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background { GlassSurface(shape: MP.surfaceShape, tint: tint) }
            .environment(\.mpOnTint, tint)
    }
}

/// The glass fill + rim + shadow, reusable for any shape.
struct GlassSurface<S: InsettableShape>: View {
    let shape: S
    var tint: Bool = false
    var solid: Bool = false
    var elevated: Bool = true
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    private var flat: Bool { contrast == .increased || reduceTransparency }

    var body: some View {
        let dark = colorScheme == .dark
        shape
            .fill(flat ? AnyShapeStyle(MP.panel)
                  : AnyShapeStyle(LinearGradient(colors: solid ? [MP.glassSolidTop, MP.glassSolidBottom]
                                                          : [MP.glassTop, MP.glassBottom],
                                                 startPoint: .topLeading, endPoint: .bottomTrailing)))
            .overlay {
                if tint && !flat {
                    shape.fill(LinearGradient(colors: [MP.fogLilac.opacity(dark ? 0.8 : 0.45),
                                                       MP.fogAmber.opacity(dark ? 0.6 : 0.32)],
                                              startPoint: .topLeading, endPoint: .bottomTrailing))
                }
            }
            .overlay {
                shape.strokeBorder(flat ? MP.lineStrong : MP.glassRim, lineWidth: flat ? 1 : 1)
            }
            .overlay {
                // The half-point outer hairline that keeps a white card
                // from dissolving into a pale canvas.
                if !flat { shape.stroke(MP.glassRing, lineWidth: 0.5) }
            }
            .shadow(color: MP.shadow.opacity(elevated && !flat ? (dark ? 0.35 : 0.05) : 0), radius: 1, y: 1)
            .shadow(color: MP.shadow.opacity(elevated && !flat ? (dark ? 0.45 : 0.09) : 0), radius: 14, y: 8)
    }
}

extension View {
    /// Wraps any content in the site's glass surface.
    func glassSurface<S: InsettableShape>(_ shape: S, solid: Bool = false, elevated: Bool = true) -> some View {
        background { GlassSurface(shape: shape, solid: solid, elevated: elevated) }
    }
}

/// A card's header row: the title and an optional trailing text action
/// ("Details", "All tasks"). Pairs with `Card(padding: 0)`.
///
/// The title is 15/500 ink, like the site's app cards. The action is sage
/// `brandInk` (7.25 / 10.53) with a 44pt target.
struct CardHeader: View {
    let title: String
    var actionTitle: String? = nil
    var action: (() -> Void)? = nil

    init(_ title: String, actionTitle: String? = nil, action: (() -> Void)? = nil) {
        self.title = title
        self.actionTitle = actionTitle
        self.action = action
    }

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Text(title)
                .mpFont(MPType(15, .medium))
                .foregroundStyle(MP.ink)
                .accessibilityAddTraits(.isHeader)
            Spacer(minLength: 8)
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
            }
        }
        .frame(minHeight: actionTitle != nil && action != nil ? 44 : 34)
        .padding(.horizontal, 16)
        .padding(.top, 8)
    }
}

/// An inset hairline between rows in a card, aligned to the row text.
/// `leading` defaults to a row that starts with a 30pt `IconTile`.
struct InsetDivider: View {
    var leading: CGFloat? = nil
    @ScaledMetric(relativeTo: .body) private var tileSide: CGFloat = 30
    @Environment(\.displayScale) private var displayScale
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        Rectangle()
            .fill(contrast == .increased ? MP.line : MP.hairline)
            .frame(height: 1 / max(displayScale, 1))
            .padding(.leading, leading ?? (16 + tileSide + 14))
            .padding(.trailing, 16)
            .accessibilityHidden(true)
    }
}

/// The site's gradient glyph square: a white SF Symbol on a grainy gradient,
/// with an inner highlight and a soft drop. Decorative — the row title
/// carries the meaning.
struct IconTile: View {
    let systemName: String
    var family: MP.Category = .blue
    @ScaledMetric private var side: CGFloat

    init(systemName: String, family: MP.Category = .blue, size: CGFloat = 30) {
        self.systemName = systemName
        self.family = family
        _side = ScaledMetric(wrappedValue: size, relativeTo: .body)
    }

    init(_ systemName: String, family: MP.Category = .blue, size: CGFloat = 30) {
        self.init(systemName: systemName, family: family, size: size)
    }

    private var radius: CGFloat { (side * 0.3).rounded() }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        Image(systemName: systemName)
            .symbolRenderingMode(.monochrome)
            .font(.system(size: (side * 16 / 30).rounded(),
                          weight: MPFont.systemWeight(for: .medium)))
            .foregroundStyle(.white)
            .frame(width: side, height: side)
            .background {
                GradientFill(gradient: MP.categoryGradient(family))
                    .clipShape(shape)
                    .overlay(alignment: .top) {
                        shape.strokeBorder(
                            LinearGradient(colors: [.white.opacity(0.35), .white.opacity(0)],
                                           startPoint: .top, endPoint: .center),
                            lineWidth: 1)
                    }
                    .shadow(color: MP.shadow.opacity(0.22), radius: 5, y: 3)
            }
            .accessibilityHidden(true)
    }
}

/// The site's lime accent dot with its halo.
struct LimeDot: View {
    var size: CGFloat = 8
    var body: some View {
        Circle()
            .fill(MP.lime)
            .frame(width: size, height: size)
            .background(Circle().fill(MP.lime.opacity(0.35)).padding(-size * 0.45))
            .accessibilityHidden(true)
    }
}

// MARK: - Gradient tile

/// The site's signature card: a grainy gradient, white type in the dark top
/// band (kicker, big light number, a side note), white line art in the
/// middle, and an ink caption on solid glass at the bottom.
///
///     GradientTile(.sage, kicker: "Daily steps", value: "4,820", unit: "steps",
///                  side: ("Day 8", "latest")) { art } caption: { ... }
struct GradientTile<Art: View, Caption: View>: View {
    let gradient: MPGradient
    let kicker: String
    var value: String? = nil
    var unit: String? = nil
    var side: (String, String)? = nil
    var valueSize: CGFloat = MPSize.displayL
    @ViewBuilder var art: () -> Art
    @ViewBuilder var caption: () -> Caption
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    init(_ gradient: MPGradient, kicker: String, value: String? = nil, unit: String? = nil,
         side: (String, String)? = nil, valueSize: CGFloat = MPSize.displayL,
         @ViewBuilder art: @escaping () -> Art,
         @ViewBuilder caption: @escaping () -> Caption) {
        self.gradient = gradient
        self.kicker = kicker
        self.value = value
        self.unit = unit
        self.side = side
        self.valueSize = valueSize
        self.art = art
        self.caption = caption
    }

    var body: some View {
        // At accessibility sizes the side note moves under the number and the
        // unit under the figure, so nothing truncates.
        let stacked = dynamicTypeSize.isAccessibilitySize
        let header = stacked
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 10))
            : AnyLayout(HStackLayout(alignment: .top, spacing: 12))
        let figure = stacked
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 0))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 4))
        VStack(alignment: .leading, spacing: 0) {
            header {
                VStack(alignment: .leading, spacing: 4) {
                    Text(kicker)
                        .mpFont(.labelMedium)
                        .foregroundStyle(.white)
                        .fixedSize(horizontal: false, vertical: true)
                    if let value {
                        figure {
                            Text(value)
                                .font(.figuresDisplay(valueSize, weight: .light))
                                .kerning(-valueSize * 0.045)
                                .foregroundStyle(.white)
                                .lineLimit(1)
                                .minimumScaleFactor(0.5)
                                .contentTransition(reduceMotion ? .identity : .numericText())
                            if let unit, !unit.isEmpty {
                                Text(unit)
                                    .mpFont(.copyMedium)
                                    .foregroundStyle(.white.opacity(0.9))
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
                if !stacked { Spacer(minLength: 8) }
                if let side {
                    VStack(alignment: stacked ? .leading : .trailing, spacing: 0) {
                        Text(side.0)
                            .font(.mp(MPSize.subhead, weight: .light))
                            .foregroundStyle(.white)
                        Text(side.1)
                            .mpFont(.label)
                            .foregroundStyle(.white.opacity(0.92))
                    }
                    .multilineTextAlignment(stacked ? .leading : .trailing)
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
            .shadow(color: .black.opacity(0.12), radius: 10)
            .padding(.horizontal, 18)
            .padding(.top, 16)

            art()
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 18)
                .padding(.vertical, 12)
                .accessibilityHidden(true)

            caption()
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .glassSurface(MP.controlShape, solid: true, elevated: false)
                .padding(.horizontal, 8)
                .padding(.bottom, 8)
        }
        .background {
            GradientFill(gradient: gradient)
                .overlay {
                    // The scrim that keeps white type readable at the top.
                    LinearGradient(stops: [.init(color: Color(red: 24 / 255, green: 22 / 255, blue: 14 / 255).opacity(0.3), location: 0),
                                           .init(color: Color(red: 24 / 255, green: 22 / 255, blue: 14 / 255).opacity(0.1), location: 0.34),
                                           .init(color: .clear, location: 0.55)],
                                   startPoint: .top, endPoint: .bottom)
                }
                .clipShape(MP.surfaceShape)
                .overlay(MP.surfaceShape.strokeBorder(.white.opacity(0.14), lineWidth: 0.5))
                .shadow(color: MP.shadow.opacity(0.1), radius: 2, y: 1)
                .shadow(color: MP.shadow.opacity(0.22), radius: 18, y: 12)
        }
    }
}

extension GradientTile where Caption == EmptyView {
    init(_ gradient: MPGradient, kicker: String, value: String? = nil, unit: String? = nil,
         side: (String, String)? = nil, valueSize: CGFloat = MPSize.displayL,
         @ViewBuilder art: @escaping () -> Art) {
        self.init(gradient, kicker: kicker, value: value, unit: unit, side: side,
                  valueSize: valueSize, art: art, caption: { EmptyView() })
    }
}

// MARK: - Buttons

/// The site's button hierarchy, all continuous capsules.
enum MPButtonKind {
    /// The near-black capsule (light capsule in dark mode). The one commit
    /// action on a screen.
    case filled
    /// The warm grey capsule, ink label. Secondary actions.
    case tinted
    /// The white glass capsule, ink label. Neutral actions.
    case gray
    /// No fill, sage label; a warm capsule appears on press.
    case plain
    /// Risk tint, `riskHigh` label. Removing / cancelling something.
    case destructive
    /// Risk fill, `onRiskHigh` label. An irreversible confirm.
    case destructiveFilled
}

/// The button style behind every MedPull button. Size comes from
/// `.controlSize`: `.large` 52pt, `.extraLarge` 56pt, `.regular` 44pt,
/// `.small` / `.mini` a 34pt capsule inside a 44pt hit target.
///
/// Press feedback is the site's spring (a small overshoot) and a 0.97 scale,
/// none under Reduce Motion.
struct MPButtonStyle: ButtonStyle {
    var kind: MPButtonKind
    var fullWidth: Bool = false
    /// Plain only: no horizontal inset, so the label aligns with the
    /// surrounding text (a card header's trailing action).
    var bare: Bool = false

    func makeBody(configuration: Configuration) -> some View {
        MPButtonBody(configuration: configuration, kind: kind, fullWidth: fullWidth, bare: bare)
    }
}

extension ButtonStyle where Self == MPButtonStyle {
    static var mpFilled: MPButtonStyle { MPButtonStyle(kind: .filled) }
    static var mpTinted: MPButtonStyle { MPButtonStyle(kind: .tinted) }
    static var mpGray: MPButtonStyle { MPButtonStyle(kind: .gray) }
    static var mpPlain: MPButtonStyle { MPButtonStyle(kind: .plain) }
    static var mpDestructive: MPButtonStyle { MPButtonStyle(kind: .destructive) }
    static var mpDestructiveFilled: MPButtonStyle { MPButtonStyle(kind: .destructiveFilled) }
    static func mp(_ kind: MPButtonKind, fullWidth: Bool = false) -> MPButtonStyle {
        MPButtonStyle(kind: kind, fullWidth: fullWidth)
    }
}

private struct MPButtonBody: View {
    let configuration: ButtonStyleConfiguration
    let kind: MPButtonKind
    let fullWidth: Bool
    let bare: Bool

    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.controlSize) private var controlSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.mpOnTint) private var onTint
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.colorScheme) private var colorScheme

    private var pressed: Bool { configuration.isPressed }

    private var height: CGFloat {
        switch controlSize {
        case .mini, .small: return 34
        case .large: return 52
        case .extraLarge: return 56
        default: return 44
        }
    }

    private var isCompact: Bool { controlSize == .mini || controlSize == .small }

    private var hPad: CGFloat {
        if bare { return 0 }
        switch controlSize {
        case .mini, .small: return 14
        case .large, .extraLarge: return 24
        default: return 18
        }
    }

    private var font: MPType { isCompact ? .copyMedium : .copyLargeMedium }

    private var label: Color {
        guard isEnabled else { return MP.disabledInk }
        switch kind {
        case .filled: return MP.onAction
        case .tinted, .gray: return MP.ink
        case .plain: return MP.brandInk
        case .destructive: return pressed ? MP.riskHighPressed : MP.riskHigh
        case .destructiveFilled: return MP.onRiskHigh
        }
    }

    private var needsEdge: Bool {
        if !isEnabled { return kind != .plain }
        guard contrast == .increased else { return false }
        switch kind {
        case .tinted, .gray, .destructive: return true
        case .plain: return pressed
        default: return false
        }
    }

    @ViewBuilder private var fill: some View {
        let shape = MPAdaptiveCapsule()
        if !isEnabled {
            if kind != .plain { shape.fill(MP.disabledFill) }
        } else {
            switch kind {
            case .filled:
                shape
                    .fill(RadialGradient(colors: [MP.actionTop, MP.action],
                                         center: UnitPoint(x: 0.3, y: 0),
                                         startRadius: 0, endRadius: 140))
                    .overlay(shape.strokeBorder(
                        LinearGradient(colors: [.white.opacity(colorScheme == .dark ? 0.9 : 0.24), .clear],
                                       startPoint: .top, endPoint: .center),
                        lineWidth: 1))
                    .shadow(color: MP.shadow.opacity(colorScheme == .dark ? 0.5 : 0.28), radius: pressed ? 4 : 9,
                            y: pressed ? 2 : 6)
            case .tinted:
                shape.fill(onTint ? MP.panel : (pressed ? MP.fillStrong : MP.fill))
            case .gray:
                shape.fill(onTint ? AnyShapeStyle(MP.panel)
                           : AnyShapeStyle(LinearGradient(colors: [MP.glassSolidTop, MP.glassSolidBottom],
                                                          startPoint: .top, endPoint: .bottom)))
                    .overlay(shape.strokeBorder(MP.glassRim, lineWidth: 1))
                    .overlay(shape.stroke(MP.glassRing, lineWidth: 0.5))
                    .shadow(color: MP.shadow.opacity(colorScheme == .dark ? 0.35 : 0.08), radius: pressed ? 3 : 8,
                            y: pressed ? 1 : 4)
            case .plain:
                shape.fill(pressed ? MP.fill : .clear)
            case .destructive:
                shape.fill(MP.riskHighBg)
                    .overlay(shape.fill(pressed ? MP.riskHigh.opacity(0.12) : .clear))
            case .destructiveFilled:
                shape.fill(MP.riskHigh)
                    .overlay(shape.fill(pressed ? MP.ink.opacity(0.12) : .clear))
            }
        }
    }

    var body: some View {
        configuration.label
            .mpFont(font)
            .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 2)
            .fixedSize(horizontal: false, vertical: true)
            .multilineTextAlignment(.center)
            .foregroundStyle(label)
            .tint(label)
            .padding(.horizontal, hPad)
            .padding(.vertical, 6)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: height)
            .background { if !bare { fill } }
            .overlay {
                if needsEdge && !bare {
                    MPAdaptiveCapsule().strokeBorder(MP.lineStrong, lineWidth: 1)
                }
            }
            .opacity(bare && pressed ? 0.6 : 1)
            .padding(.vertical, isCompact ? 5 : 0)
            .contentShape(Rectangle())
            .scaleEffect(bare ? 1 : MPMotion.pressScale(pressed, reduceMotion: reduceMotion))
            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion), value: pressed)
    }
}

/// A capsule while the view is one control tall; a continuous rounded
/// rectangle once it grows past `rowCeiling` (a wrapped label at
/// accessibility text sizes).
struct MPAdaptiveCapsule: InsettableShape {
    var rowCeiling: CGFloat = 64
    var stackedRadius: CGFloat = 26
    var inset: CGFloat = 0

    func path(in rect: CGRect) -> Path {
        let radius = (rect.height <= rowCeiling ? rect.height / 2 : stackedRadius) - inset
        let r = rect.insetBy(dx: inset, dy: inset)
        return RoundedRectangle(cornerRadius: max(0, min(radius, r.width / 2, r.height / 2)),
                                style: .continuous)
            .path(in: r)
    }

    func inset(by amount: CGFloat) -> MPAdaptiveCapsule {
        var copy = self
        copy.inset += amount
        return copy
    }
}

/// A whole-row button inside a card: the pressed state is a warm fill behind
/// the row, no scale.
struct MPRowButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .background(configuration.isPressed ? MP.fill : Color.clear)
    }
}

extension ButtonStyle where Self == MPRowButtonStyle {
    static var mpRow: MPRowButtonStyle { MPRowButtonStyle() }
}

/// The one full-width commit button: the near-black capsule with the site's
/// lime dot, 52pt. `loading` keeps the fill with a spinner and swallows
/// taps; `disabled` uses the disabled token pair.
struct PrimaryButton: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    let title: String
    var icon: String? = nil
    var loading = false
    var disabled = false
    let action: () -> Void

    var body: some View {
        Button { if !loading { action() } } label: {
            HStack(spacing: 10) {
                if loading {
                    ProgressView()
                } else {
                    if !disabled && !dynamicTypeSize.isAccessibilitySize {
                        if let icon { Image(systemName: icon) } else { LimeDot(size: 7) }
                    }
                    Text(title)
                }
            }
        }
        .buttonStyle(MPButtonStyle(kind: .filled, fullWidth: true))
        .controlSize(.large)
        .disabled(disabled)
        .allowsHitTesting(!loading)
        .accessibilityLabel(Text(title))
        .accessibilityValue(loading ? Text("Working") : Text(""))
    }
}

/// The quieter full-width button: the white glass capsule, 52pt.
struct SecondaryButton: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    let title: String
    var icon: String? = nil
    var loading = false
    let action: () -> Void

    var body: some View {
        Button { if !loading { action() } } label: {
            HStack(spacing: 8) {
                if loading {
                    ProgressView()
                } else {
                    if let icon, !dynamicTypeSize.isAccessibilitySize { Image(systemName: icon) }
                    Text(title)
                }
            }
        }
        .buttonStyle(MPButtonStyle(kind: .gray, fullWidth: true))
        .controlSize(.large)
        .allowsHitTesting(!loading)
        .accessibilityLabel(Text(title))
        .accessibilityValue(loading ? Text("Working") : Text(""))
    }
}

// MARK: - Chip

/// The check-in answer: the site's quick reply. A white capsule with a ring
/// and a soft lift; picked, the sage message bubble with white text and a
/// check. 44pt minimum, a selection haptic, the spring press.
struct Chip: View {
    let label: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) { Text(label) }
            .buttonStyle(MPChipStyle(selected: selected))
            .sensoryFeedback(.selection, trigger: selected)
            .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

private struct MPChipStyle: ButtonStyle {
    let selected: Bool

    func makeBody(configuration: Configuration) -> some View {
        MPChipBody(configuration: configuration, selected: selected)
    }
}

/// The site's sage bubble gradient, for anything the patient has said.
struct BubbleFill: View {
    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 94 / 255, green: 125 / 255, blue: 78 / 255),
                                    Color(red: 68 / 255, green: 95 / 255, blue: 57 / 255)],
                           startPoint: .top, endPoint: .bottom)
            GrainOverlay()
        }
    }
}

private struct MPChipBody: View {
    let configuration: ButtonStyleConfiguration
    let selected: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        HStack(spacing: 6) {
            if selected {
                Image(systemName: "checkmark")
                    .font(.system(size: 13, weight: .semibold))
                    .transition(.scale.combined(with: .opacity))
            }
            configuration.label
        }
        .mpFont(.copyLargeMedium)
        // White on the sage bubble 6.4; ink on the white capsule 18.4.
        .foregroundStyle(selected ? Color.white : MP.ink)
        .padding(.horizontal, 20)
        .frame(minHeight: 48)
        .background {
            if selected {
                BubbleFill()
                    .clipShape(MP.capsuleShape)
                    .shadow(color: Color(red: 74 / 255, green: 102 / 255, blue: 62 / 255).opacity(0.45),
                            radius: 8, y: 4)
            } else {
                MP.capsuleShape
                    .fill(colorScheme == .dark ? MP.fill : MP.panel)
                    .overlay(MP.capsuleShape.strokeBorder(MP.lineStrong.opacity(0.6), lineWidth: 1))
                    .shadow(color: MP.shadow.opacity(colorScheme == .dark ? 0 : 0.08),
                            radius: configuration.isPressed ? 2 : 6, y: configuration.isPressed ? 1 : 3)
            }
        }
        .contentShape(MP.capsuleShape)
        .scaleEffect(MPMotion.pressScale(configuration.isPressed, reduceMotion: reduceMotion))
        .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion), value: configuration.isPressed)
        .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion), value: selected)
    }
}

// MARK: - Pills and avatars

/// A state pill, the site's: a capsule on the tone's tint, a dot and the
/// word. Missing data gets a hollow dot. 12pt / 500.
struct StatusPill: View {
    let text: String
    let tone: MP.Tone

    var body: some View {
        HStack(spacing: 5) {
            Group {
                if tone == .missing {
                    Circle().strokeBorder(MP.foreground(tone), lineWidth: 1.5)
                } else {
                    Circle().fill(MP.foreground(tone))
                }
            }
            .frame(width: 6, height: 6)
            .accessibilityHidden(true)
            Text(text)
                .font(.labelMedium)
                .foregroundStyle(MP.foreground(tone))
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
        .padding(.horizontal, 10).padding(.vertical, 5)
        .background(MP.pillShape.fill(MP.background(tone)))
    }
}

/// An avatar disc that scales with Dynamic Type (capped at 1.5x): the site's
/// grainy gradient avatar with white initials, its tone picked from the
/// initials so a person keeps their colour. `.high` is the clay disc.
/// `.soft` keeps the tone's tint with its ink (every pair 4.73 or better).
struct Initials: View {
    enum Style { case filled, soft }

    let text: String
    var size: CGFloat = 40
    var tone: MP.Tone = .brand
    var style: Style = .filled
    @ScaledMetric(relativeTo: .body) private var scale: CGFloat = 1

    init(text: String, size: CGFloat = 40, tone: MP.Tone = .brand, style: Style = .filled) {
        self.text = text
        self.size = size
        self.tone = tone
        self.style = style
    }

    private var side: CGFloat { (size * min(scale, 1.5)).rounded() }

    private static let tones: [(Color, Color)] = [
        (Color(red: 192 / 255, green: 132 / 255, blue: 98 / 255), Color(red: 138 / 255, green: 89 / 255, blue: 66 / 255)),
        (Color(red: 135 / 255, green: 151 / 255, blue: 187 / 255), Color(red: 82 / 255, green: 95 / 255, blue: 134 / 255)),
        (Color(red: 201 / 255, green: 164 / 255, blue: 76 / 255), Color(red: 143 / 255, green: 111 / 255, blue: 31 / 255)),
        (Color(red: 136 / 255, green: 168 / 255, blue: 110 / 255), Color(red: 74 / 255, green: 103 / 255, blue: 62 / 255)),
        (Color(red: 157 / 255, green: 147 / 255, blue: 203 / 255), Color(red: 100 / 255, green: 104 / 255, blue: 168 / 255)),
    ]

    private var colors: [Color] {
        if tone == .high {
            return [Color(red: 201 / 255, green: 121 / 255, blue: 90 / 255),
                    Color(red: 154 / 255, green: 74 / 255, blue: 46 / 255)]
        }
        let h = text.unicodeScalars.reduce(0) { ($0 &* 31 &+ Int($1.value)) & 0xFFFF }
        let pair = Self.tones[h % Self.tones.count]
        return [pair.0, pair.1]
    }

    var body: some View {
        let soft = style == .soft && tone != .brand && tone != .high
        Text(text)
            .font(.mp(side * 0.36, weight: .medium, relativeTo: .body))
            .dynamicTypeSize(...DynamicTypeSize.large)
            .lineLimit(1)
            .minimumScaleFactor(0.6)
            .foregroundStyle(soft ? MP.foreground(tone) : .white)
            .shadow(color: soft ? .clear : .black.opacity(0.18), radius: 1, y: 1)
            .frame(width: side, height: side)
            .background {
                if soft {
                    Circle().fill(MP.background(tone))
                } else {
                    ZStack {
                        LinearGradient(colors: colors, startPoint: .topLeading, endPoint: .bottomTrailing)
                        GrainOverlay()
                    }
                    .clipShape(Circle())
                    .overlay(Circle().strokeBorder(
                        LinearGradient(colors: [.white.opacity(0.3), .clear], startPoint: .top, endPoint: .center),
                        lineWidth: 1))
                    .shadow(color: MP.shadow.opacity(0.25), radius: 3, y: 2)
                }
            }
    }
}

// MARK: - Empty, error, field

/// The in-card empty state: a quiet gradient glyph and one line of ink.
struct EmptyRow: View {
    let icon: String
    let title: String
    var detail: String? = nil

    var body: some View {
        VStack(spacing: 10) {
            IconTile(icon, family: .teal, size: 40)
            Text(title).font(.copyLargeMedium).foregroundStyle(MP.ink)
            if let detail {
                Text(detail).font(.copy).mpSecondary()
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .padding(.horizontal, 16)
    }
}

/// An inline error, on the amber status tint.
struct ErrorBanner: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(MP.riskMed)
                .accessibilityHidden(true)
            Text(text).font(.copyMedium).foregroundStyle(MP.ink)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MP.controlShape.fill(MP.riskMedBg))
    }
}

/// A text field, the site's form control: a light fill, 14pt corners and a
/// `lineStrong` ring (3.39 / 3.87) — an empty field's boundary is its only cue.
struct FieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .font(.copyLarge)
            .foregroundStyle(MP.ink)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(minHeight: 52)
            .background(MP.thumbShape.fill(MP.panel.opacity(0.8)))
            .overlay(MP.thumbShape.strokeBorder(MP.lineStrong.opacity(0.75), lineWidth: 1))
    }
}

// MARK: - Screen backgrounds

struct ScreenBackground: ViewModifier {
    func body(content: Content) -> some View {
        content.background {
            ZStack {
                MP.canvas
                GrainOverlay(kind: .surface)
            }
            .ignoresSafeArea()
        }
    }
}

/// The site's canvas: warm white with soft colour fog that drifts slowly
/// (transform only, rendered once as a Metal layer), grain, and a faint dot
/// grid at the top. Static under Reduce Motion; plain canvas under Increase
/// Contrast or Reduce Transparency.
struct FogBackground: View {
    var height: CGFloat = 520
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.scenePhase) private var scenePhase
    @State private var drift = false

    var body: some View {
        ZStack(alignment: .top) {
            MP.canvas
            if contrast != .increased && !reduceTransparency {
                GeometryReader { proxy in
                    let w = proxy.size.width
                    ZStack {
                        blob(MP.fogSage, size: w * 1.0, x: w * 0.78, y: height * 0.12, dx: 26, dy: -18)
                        blob(MP.fogAmber, size: w * 0.8, x: w * 1.02, y: height * 0.52, dx: -22, dy: 16)
                        blob(MP.fogClay, size: w * 0.75, x: w * 0.42, y: height * 0.78, dx: 18, dy: 12)
                        blob(MP.fogLilac, size: w * 0.8, x: w * 0.02, y: height * 0.08, dx: 20, dy: 14)
                        blob(MP.fogMint, size: w * 0.6, x: w * -0.05, y: height * 0.7, dx: -14, dy: -10)
                    }
                    .frame(width: w, height: height)
                    .drawingGroup()
                    .mask(LinearGradient(stops: [.init(color: .black, location: 0),
                                                 .init(color: .black, location: 0.62),
                                                 .init(color: .clear, location: 1)],
                                         startPoint: .top, endPoint: .bottom))
                }
                .frame(height: height)
                DotGrid()
                    .frame(height: height * 0.7)
                    .mask(LinearGradient(colors: [.black, .black.opacity(0.4), .clear],
                                         startPoint: .top, endPoint: .bottom))
                GrainOverlay(kind: .surface)
            }
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
        .onAppear { startDrift() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { startDrift() }
        }
    }

    private func startDrift() {
        guard !reduceMotion else { return }
        drift = false
        withAnimation(.easeInOut(duration: 14).repeatForever(autoreverses: true)) { drift = true }
    }

    private func blob(_ color: Color, size: CGFloat, x: CGFloat, y: CGFloat, dx: CGFloat, dy: CGFloat) -> some View {
        Circle()
            .fill(RadialGradient(colors: [color, color.opacity(0)], center: .center,
                                 startRadius: 0, endRadius: size / 2))
            .frame(width: size, height: size)
            .scaleEffect(drift ? 1.1 : 0.96)
            .position(x: x + (drift ? dx : -dx * 0.6), y: y + (drift ? dy : -dy * 0.6))
    }
}

/// The site's faint dot grid (graph paper).
private struct DotGrid: View {
    var body: some View {
        Canvas { ctx, size in
            let step: CGFloat = 22
            var path = Path()
            var y: CGFloat = step / 2
            while y < size.height {
                var x: CGFloat = step / 2
                while x < size.width {
                    path.addEllipse(in: CGRect(x: x - 0.75, y: y - 0.75, width: 1.5, height: 1.5))
                    x += step
                }
                y += step
            }
            ctx.fill(path, with: .color(MP.ink.opacity(0.06)))
        }
        .allowsHitTesting(false)
    }
}

/// Canvas with the fog at the top (tab roots).
struct AmbientScreenBackground: ViewModifier {
    var height: CGFloat = 520

    func body(content: Content) -> some View {
        content.background { FogBackground(height: height) }
    }
}

extension View {
    func screen() -> some View { modifier(ScreenBackground()) }
    /// The fog canvas; for Home, Tasks, Health and Messages roots.
    func ambientScreen(height: CGFloat = 520) -> some View {
        modifier(AmbientScreenBackground(height: height))
    }

    /// The site's entrance: fade in and rise 18pt, staggered by `index`
    /// (60ms steps). Nothing under Reduce Motion.
    func mpRise(_ index: Int = 0) -> some View {
        modifier(MPRise(index: index))
    }
}

private struct MPRise: ViewModifier {
    let index: Int
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown = false

    func body(content: Content) -> some View {
        content
            .opacity(shown || reduceMotion ? 1 : 0)
            .offset(y: shown || reduceMotion ? 0 : 18)
            .onAppear {
                guard !shown, !reduceMotion else { return }
                withAnimation(MPMotion.enter.delay(Double(index) * 0.06)) { shown = true }
            }
    }
}

// MARK: - Sensory feedback

extension View {
    /// A success haptic when a task or check-in completes: fires only on the
    /// false -> true edge, so re-renders and resets stay silent.
    func mpCompletionFeedback(_ completed: Bool) -> some View {
        sensoryFeedback(.success, trigger: completed) { old, new in !old && new }
    }

    /// A success haptic whenever `count` goes up (tasks done today, etc.).
    func mpCompletionFeedback(count: Int) -> some View {
        sensoryFeedback(.success, trigger: count) { old, new in new > old }
    }

    /// An error haptic when an error message appears.
    func mpErrorFeedback(_ message: String?) -> some View {
        sensoryFeedback(.error, trigger: message) { old, new in old == nil && new != nil }
    }

    /// A selection tick on any change of `value` (pickers, steppers, sliders).
    func mpSelectionFeedback<V: Equatable>(_ value: V) -> some View {
        sensoryFeedback(.selection, trigger: value)
    }

    /// A light impact when `trigger` changes (a toggle, a swipe action).
    func mpImpactFeedback<V: Equatable>(_ trigger: V) -> some View {
        sensoryFeedback(.impact(weight: .light), trigger: trigger)
    }
}
