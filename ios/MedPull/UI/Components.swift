import SwiftUI

/// The shared components, on the tokens.
///
/// THE RULES THESE ENFORCE, so no screen has to remember them:
///  * Separation is a hairline OR a fill, never both on the same edge, and
///    never a shadow on a card. Nothing here casts a shadow; the ambient
///    shadow belongs to floating overlays only.
///  * `MP.brand` is a FILL and a stroke, never a foreground. A brand
///    foreground is `MP.brandInk` (#1976D2 as text is 3.74:1 on dark panel;
///    `brandInk` is 6.78:1). The app's root tint is `MP.brandInk`; a control
///    whose FILL must be #1976D2 names `MP.brand` itself (the filled button
///    style below does).
///  * `MP.faint` carries NO TEXT. It is 2.59:1 on light panel. The only use
///    below is EmptyRow's glyph, which is empty-state art.
///  * Every button and every pill is a continuous capsule. Cards are 20pt
///    continuous, controls 12, tiles 8.
///  * Inside a tinted card, controls never take the card's own tint: the
///    tinted and gray button styles switch to a panel fill there, and
///    secondary text switches from `muted` to `body` (`MPOnTint`, below).
///  * Type comes from the ladder, read inside `body` (never a stored `let`),
///    so Bold Text and Dynamic Type reach every label.
///
/// CONTRAST, computed with the WCAG formula (0.04045 threshold), light / dark
/// (script: scratchpad/i1contrast.py):
///   filled      white on brand 4.602 / 4.602; pressed on brandDeep 8.631 / 4.602
///   tinted      brandInk on brandTint 4.963 / 5.624; pressed: brandDeep on
///               brandTintStrong 6.365 light, brandInk on it 4.954 dark
///               (brandInk on brandTintStrong light is 4.238 and is NOT used)
///   tinted on a tint card: brandInk on panel 5.746 / 6.783
///   gray        ink on soft 16.202 / 16.060; pressed on track 14.517 / 12.810
///   plain       brandInk on panel 5.746 / 6.783, on canvas 5.354 / 7.250;
///               pressed on soft 5.066 / 6.336
///   destructive riskHigh on riskHighBg 4.835 / 5.701; pressed (riskHigh 12%
///               over the bg) with `MP.riskHighPressed` 6.600 light, riskHigh
///               4.587 dark
///   destructive filled: onRiskHigh on riskHigh 5.622 / 8.084; pressed
///               (ink 12% over) 6.674 / 8.911
///   disabled    disabledInk on disabledFill 4.755 / 4.582
///   secondary on tint: body on brandTint 6.237 / 5.513, on tealTint 6.427 /
///               5.002 (muted on brandTint dark is 4.067 and fails — R8)
///   tiles       brandInk/brandTint 4.963 / 5.624, tealInk/tealTint 5.171 /
///               8.142, indigo 6.950 / 6.721, violet 6.354 / 7.114
///   initials    white on brand 4.602; onRiskHigh on riskHigh 5.622 / 8.084;
///               soft variants: every risk ink on its own bg >= 4.731
///
/// NON-TEXT CONTRAST. Tinted and gray fills are only 1.13-1.21:1 against the
/// panel. That is accepted under the WCAG 1.4.11 reading in which the visible
/// text label identifies the control (the same basis as "Details" and "All
/// tasks"). Under Increase Contrast every non-filled style gains a 1pt
/// `lineStrong` edge (3.834 / 5.671 on panel), and so does every disabled
/// style (its fill is 1.06:1 against canvas).

// MARK: - Tint context (R8, and the "never the same tint" rule)

private struct MPOnTintKey: EnvironmentKey {
    static let defaultValue = false
}

extension EnvironmentValues {
    /// True inside `Card(tint: true)`. Button styles and `.mpSecondary()`
    /// read it; set it yourself on any other brand- or teal-tinted surface
    /// with `.mpOnTint()`.
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
    /// Secondary text colour: `MP.muted` on panel/canvas, `MP.body` on a tinted
    /// card (dark `muted` on `brandTint` is 4.067:1; `body` is 5.513:1).
    func mpSecondary() -> some View { modifier(MPSecondaryInk()) }

    /// Marks a subtree as sitting on a brand/teal tint (see `mpOnTint`).
    func mpOnTint(_ onTint: Bool = true) -> some View {
        environment(\.mpOnTint, onTint)
    }
}

// MARK: - Card

/// Instrument panel: one hairline edge, flat surface, no shadow. 20pt
/// continuous corners.
struct Card<Content: View>: View {
    var padding: CGFloat = 16
    /// A brand-tinted card: the same surface, filled with the brand tint
    /// SOLID. `MP.ink` on `brandTint` is 15.87:1 light / 14.26:1 dark.
    /// Secondary text inside must use `.mpSecondary()` (or
    /// `MP.onTintSecondary`), never `MP.muted` — see R8.
    var tint: Bool = false
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(MP.surfaceShape.fill(tint ? MP.brandTint : MP.panel))
            // ONE edge. On dark, `panel` is 1.07:1 against `canvas`, so this
            // 1pt `MP.line` (3.63:1 on dark panel) is what says "card".
            .overlay(MP.surfaceShape.strokeBorder(MP.line, lineWidth: 1))
            .environment(\.mpOnTint, tint)
    }
}

/// A card's header row: a quiet title and an optional trailing text action
/// ("Details", "All tasks"). Pairs with `Card(padding: 0)`.
///
/// The title is 12/500 in the secondary ink (muted 5.393 / 4.906 on panel,
/// body on a tint card). The action is 14/500 `brandInk` (5.746 / 6.783 on
/// panel, 4.963 / 5.624 on brandTint) with a 44pt target.
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
                .mpFont(.labelMedium)
                .mpSecondary()
                .accessibilityAddTraits(.isHeader)
            Spacer(minLength: 8)
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
            }
        }
        // 44pt only when the row carries a tap target; a title-only header
        // needs no hit area and the extra height read as a gap above the
        // first row.
        .frame(minHeight: actionTitle != nil && action != nil ? 44 : 32)
        .padding(.horizontal, 16)
        .padding(.top, 6)
    }
}

/// An inset hairline between rows in a card, aligned to the row text rather
/// than the card edge (the Settings / Health list look). `leading` defaults to
/// a row that starts with a 30pt `IconTile`: 16 + tile + 14, scaled with the
/// tile. Pass `leading: 16` for rows without a tile.
struct InsetDivider: View {
    var leading: CGFloat? = nil
    @ScaledMetric(relativeTo: .body) private var tileSide: CGFloat = 30
    @Environment(\.displayScale) private var displayScale
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        Rectangle()
            // Decorative only (1.266 / 1.342). Increase Contrast uses `line`.
            .fill(contrast == .increased ? MP.line : MP.hairline)
            .frame(height: 1 / max(displayScale, 1))
            .padding(.leading, leading ?? (16 + tileSide + 14))
            .padding(.trailing, 16)
            .accessibilityHidden(true)
    }
}

/// A Health-style category tile: an SF Symbol in its family ink on the
/// family tint, 8pt continuous corners. Families are non-risk hues only.
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

    var body: some View {
        Image(systemName: systemName)
            .symbolRenderingMode(.hierarchical)
            // The side is already Dynamic-Type scaled, so the glyph is a
            // fixed fraction of it (16 in 30).
            .font(.system(size: (side * 16 / 30).rounded(),
                          weight: MPFont.systemWeight(for: .medium)))
            .foregroundStyle(MP.categoryInk(family))
            .frame(width: side, height: side)
            .background(MP.tileShape.fill(MP.categoryTint(family)))
            .accessibilityHidden(true)
    }
}

// MARK: - Buttons

/// Apple's button hierarchy, all as continuous capsules.
enum MPButtonKind {
    /// Brand fill, white label. The one commit action on a screen.
    case filled
    /// Brand tint fill, `brandInk` label. Secondary actions.
    case tinted
    /// Neutral `soft` fill, `ink` label. Tertiary / neutral actions.
    case gray
    /// No fill, `brandInk` label; a soft capsule appears on press.
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
/// Press feedback is a 0.97 scale on `MPMotion.press` (a snappy spring),
/// none under Reduce Motion, plus a pressed fill that keeps its label pair
/// above 4.5:1 (see the file header).
struct MPButtonStyle: ButtonStyle {
    var kind: MPButtonKind
    /// Stretch to the container's width (`PrimaryButton`).
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
    /// Any kind, optionally full width.
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
        case .large, .extraLarge: return 22
        default: return 18
        }
    }

    private var font: MPType { isCompact ? .copyMedium : .copyLargeMedium }

    private var label: Color {
        guard isEnabled else { return MP.disabledInk }
        switch kind {
        case .filled: return MP.onBrand
        case .tinted: return pressed ? MP.brandInkPressed : MP.brandInk
        case .gray: return MP.ink
        case .plain: return MP.brandInk
        case .destructive: return pressed ? MP.riskHighPressed : MP.riskHigh
        case .destructiveFilled: return MP.onRiskHigh
        }
    }

    private var fill: Color {
        if !isEnabled { return kind == .plain ? .clear : MP.disabledFill }
        switch kind {
        case .filled: return pressed ? MP.brandDeep : MP.brand
        case .tinted:
            // Never the card's own tint (R1): a panel capsule on a tint card.
            if onTint { return pressed ? MP.soft : MP.panel }
            return pressed ? MP.brandTintStrong : MP.brandTint
        case .gray:
            if onTint { return pressed ? MP.soft : MP.panel }
            return pressed ? MP.track : MP.soft
        case .plain: return pressed ? MP.soft : .clear
        case .destructive: return MP.riskHighBg
        case .destructiveFilled: return MP.riskHigh
        }
    }

    /// A pressed overlay for the two risk fills (no token for a deeper red).
    private var pressOverlay: Color {
        guard isEnabled, pressed else { return .clear }
        switch kind {
        case .destructive: return MP.riskHigh.opacity(0.12)
        case .destructiveFilled: return MP.ink.opacity(0.12)
        default: return .clear
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

    var body: some View {
        configuration.label
            .mpFont(font)
            .lineLimit(2)
            .multilineTextAlignment(.center)
            .foregroundStyle(label)
            .tint(label) // a ProgressView inside the label
            .padding(.horizontal, hPad)
            .padding(.vertical, 6)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: height)
            .background {
                if !bare {
                    MP.capsuleShape.fill(fill)
                        .overlay(MP.capsuleShape.fill(pressOverlay))
                }
            }
            .overlay {
                if needsEdge && !bare {
                    MP.capsuleShape.strokeBorder(MP.lineStrong, lineWidth: 1)
                }
            }
            .opacity(bare && pressed ? 0.6 : 1)
            // A 34pt capsule still gets a 44pt target.
            .padding(.vertical, isCompact ? 5 : 0)
            .contentShape(Rectangle())
            .scaleEffect(bare ? 1 : MPMotion.pressScale(pressed, reduceMotion: reduceMotion))
            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion), value: pressed)
    }
}

/// A whole-row button inside a card: the pressed state is a `soft` fill
/// behind the row, no scale (a scaling row inside a card reads as a glitch).
struct MPRowButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .background(configuration.isPressed ? MP.soft : Color.clear)
    }
}

extension ButtonStyle where Self == MPRowButtonStyle {
    static var mpRow: MPRowButtonStyle { MPRowButtonStyle() }
}

/// The one full-width commit button: `.mpFilled`, 52pt. `loading` keeps the
/// brand fill with a white spinner and swallows taps; `disabled` uses the
/// disabled token pair.
struct PrimaryButton: View {
    let title: String
    var icon: String? = nil
    var loading = false
    var disabled = false
    let action: () -> Void

    var body: some View {
        Button { if !loading { action() } } label: {
            HStack(spacing: 8) {
                if loading {
                    ProgressView()
                } else {
                    if let icon { Image(systemName: icon) }
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

/// The quieter full-width button: `.mpGray`, 52pt. On a tint card it takes a
/// panel fill automatically.
struct SecondaryButton: View {
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
                    if let icon { Image(systemName: icon) }
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

/// The check-in answer chip. A capsule, 44pt minimum, a selection tick of
/// haptic feedback and a gated press scale.
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

private struct MPChipBody: View {
    let configuration: ButtonStyleConfiguration
    let selected: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        configuration.label
            .mpFont(.copyLargeMedium)
            // brandInk on brandTint 4.963 / 5.624; ink on panel 18.4 / 17.2.
            .foregroundStyle(selected ? MP.brandInk : MP.ink)
            .padding(.horizontal, 18)
            .frame(minHeight: 44)
            .background(MP.capsuleShape.fill(selected ? MP.brandTint : (configuration.isPressed ? MP.soft : MP.panel)))
            // The stroke is the state cue, so it is a graphic: `brand`
            // selected, `lineStrong` idle. Selection is never colour alone —
            // the fill and the isSelected trait change with it.
            .overlay(MP.capsuleShape.strokeBorder(selected ? MP.brand : MP.lineStrong,
                                                  lineWidth: selected ? 1.5 : 1))
            .contentShape(MP.capsuleShape)
            .scaleEffect(MPMotion.pressScale(configuration.isPressed, reduceMotion: reduceMotion))
            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion),
                       value: configuration.isPressed)
    }
}

// MARK: - Pills and avatars

/// A state pill. 12pt / 500, a continuous capsule on the tone's bg. Risk
/// pills are opaque fills and always carry a word.
struct StatusPill: View {
    let text: String
    let tone: MP.Tone

    var body: some View {
        Text(text)
            .font(.labelMedium)
            .foregroundStyle(MP.foreground(tone))
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(MP.pillShape.fill(MP.background(tone)))
    }
}

/// An avatar disc that scales with Dynamic Type (capped at 1.5x).
///
/// `.filled` (default): brand disc with white initials (4.602), or for
/// `.high` a riskHigh disc with `onRiskHigh` (5.622 light / 8.084 dark —
/// white on the dark #FF8A87 would be 2.27, so it is n-950 there). Other
/// risk tones never fill; they fall back to `.soft`.
/// `.soft`: the tone's bg with its ink (every pair >= 4.731).
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

    private var isFilled: Bool {
        style == .filled && (tone == .brand || tone == .high)
    }

    private var ink: Color {
        if isFilled { return tone == .high ? MP.onRiskHigh : MP.onBrand }
        return MP.foreground(tone)
    }

    private var disc: Color {
        if isFilled { return tone == .high ? MP.riskHigh : MP.brand }
        return MP.background(tone)
    }

    var body: some View {
        Text(text)
            .font(.mp(side * 0.36, weight: .medium, relativeTo: .body))
            .dynamicTypeSize(...DynamicTypeSize.large) // the disc already scaled
            .lineLimit(1)
            .minimumScaleFactor(0.6)
            .foregroundStyle(ink)
            .frame(width: side, height: side)
            .background(Circle().fill(disc))
    }
}

// MARK: - Empty, error, field

/// The in-card empty state.
struct EmptyRow: View {
    let icon: String
    let title: String
    var detail: String? = nil

    var body: some View {
        VStack(spacing: 8) {
            // The ONE sanctioned `MP.faint` in this file: empty-state art is
            // decoration, and the row says the same thing in `ink` below it.
            Image(systemName: icon).font(.displayS).foregroundStyle(MP.faint)
                .accessibilityHidden(true)
            Text(title).font(.copyLargeMedium).foregroundStyle(MP.ink)
            if let detail {
                Text(detail).font(.copy).mpSecondary()
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
    }
}

/// An inline error. Separation is the `riskMedBg` fill alone.
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

/// A text field. 16pt / 400. A field keeps its `lineStrong` border (3.834 /
/// 5.671): an empty field's boundary is its only cue.
struct FieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .font(.copyLarge)
            .foregroundStyle(MP.ink)
            .padding(.horizontal, 14)
            .frame(minHeight: 52)
            .background(MP.controlShape.fill(MP.panel))
            .overlay(MP.controlShape.strokeBorder(MP.lineStrong, lineWidth: 1))
    }
}

struct ScreenBackground: ViewModifier {
    func body(content: Content) -> some View {
        content.background(MP.canvas.ignoresSafeArea())
    }
}

/// Canvas with the ambient brand wash at the top (tab roots). Plain canvas
/// under Increase Contrast.
struct AmbientScreenBackground: ViewModifier {
    var height: CGFloat = 320
    @Environment(\.colorSchemeContrast) private var contrast

    func body(content: Content) -> some View {
        content.background {
            ZStack(alignment: .top) {
                MP.canvas
                if contrast != .increased {
                    LinearGradient(colors: [MP.ambient, MP.ambient.opacity(0)],
                                   startPoint: .top, endPoint: .bottom)
                        .frame(height: height)
                }
            }
            .ignoresSafeArea()
        }
    }
}

extension View {
    func screen() -> some View { modifier(ScreenBackground()) }
    /// `screen()` plus the ambient wash; for Home, Tasks and Health roots.
    func ambientScreen(height: CGFloat = 320) -> some View {
        modifier(AmbientScreenBackground(height: height))
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
