import SwiftUI

/// The shared components, on the tokens.
///
/// THE FOUR RULES THESE ENFORCE, so no screen has to remember them:
///  * Separation is a hairline OR a fill, never both on the same edge, and
///    never a shadow on a card. Nothing here casts a shadow; the ambient
///    shadow belongs to floating overlays only.
///  * `MP.brand` is a FILL and a stroke, never a foreground. A brand
///    foreground is `MP.brandInk` (#1976D2 as text is 3.74:1 on dark panel;
///    `brandInk` is 6.78:1).
///  * `MP.faint` carries NO TEXT. It is 2.59:1 on light panel. The only use
///    below is EmptyRow's glyph, which is empty-state art.
///  * Type comes from the ladder — `MPSize` / the named `Font` rungs — at
///    weight 400 or 500. Nothing here names `.semibold`.

/// Instrument panel: one hairline edge, flat surface, no shadow.
struct Card<Content: View>: View {
    var padding: CGFloat = 16
    /// A brand-tinted card: the same surface, filled with the brand tint
    /// SOLID. It used to be a `panel -> brandTint.opacity(0.55)` gradient,
    /// which is two defects in one: a wash whose real contrast depends on
    /// whichever of the three grounds shows through, and a gradient where the
    /// system has flat fills. `MP.ink` on `brandTint` is 15.87:1 light /
    /// 14.26:1 dark either way.
    var tint: Bool = false
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(MP.surfaceShape.fill(tint ? MP.brandTint : MP.panel))
            // ONE edge. A card gets the hairline or a ring, never both, and
            // never either plus a shadow: on dark, `panel` is 1.07:1 against
            // `canvas`, so this 1pt `MP.line` (3.63:1 on dark panel) is the
            // only thing that says "card".
            .overlay(MP.surfaceShape.strokeBorder(MP.line, lineWidth: 1))
    }
}

/// The one full-width commit button. Brand fill, white ink — the single
/// sanctioned white-on-brand pairing, at 4.60:1 in both modes.
struct PrimaryButton: View {
    let title: String
    var icon: String? = nil
    var loading = false
    var disabled = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if loading {
                    ProgressView().tint(MP.onBrand)
                } else {
                    if let icon { Image(systemName: icon) }
                    Text(title)
                }
            }
            .font(.copyLargeMedium)
            .foregroundStyle(disabled ? MP.disabledInk : MP.onBrand)
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(MP.controlShape.fill(disabled ? MP.disabledFill : MP.brand))
            // Disabled is a token pair, not `.opacity(0.45)`. A 45% brand
            // fill with 45% white on it read as an enabled button rendered
            // badly; `disabledInk` on `disabledFill` is 4.75:1 light / 4.58:1
            // dark, so the label stays readable even though an inactive
            // control is exempt. The fill is only 1.06:1 against canvas
            // though, so the disabled state takes the `lineStrong` edge to
            // keep its shape.
            .overlay {
                if disabled { MP.controlShape.strokeBorder(MP.lineStrong, lineWidth: 1) }
            }
        }
        .buttonStyle(.plain)
        .disabled(disabled || loading)
    }
}

/// The quieter full-width button: panel fill, `lineStrong` edge.
struct SecondaryButton: View {
    let title: String
    var icon: String? = nil
    var loading = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if loading { ProgressView() } else {
                    if let icon { Image(systemName: icon) }
                    Text(title)
                }
            }
            .font(.copyLargeMedium)
            .foregroundStyle(MP.ink)
            .frame(maxWidth: .infinity, minHeight: 48)
            .background(MP.controlShape.fill(MP.panel))
            // `lineStrong` (3.83:1 light / 5.67:1 dark), not `line`: the
            // panel fill is 1.13:1 against canvas, so this border is the only
            // cue the button exists and 1.4.11's 3:1 applies to it. `line` at
            // 1.55:1 would leave the button invisible in light.
            .overlay(MP.controlShape.strokeBorder(MP.lineStrong, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(loading)
    }
}

/// The check-in page's answer chip. 44pt minimum target.
struct Chip: View {
    let label: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.copyLargeMedium)
                // Selected ink is `brandInk`, not `brand`: 4.96:1 light /
                // 5.62:1 dark on `brandTint`, where `brand` itself is 3.10:1
                // dark and fails as text.
                .foregroundStyle(selected ? MP.brandInk : MP.ink)
                .padding(.horizontal, 16)
                .frame(minHeight: 44)
                .background(MP.controlShape.fill(selected ? MP.brandTint : MP.panel))
                // The stroke is the state cue, so it is a graphic: `brand`
                // selected (3.97:1 on its own tint light, 3.10:1 dark),
                // `lineStrong` idle. Selection is never colour alone — the
                // fill changes with it.
                .overlay(MP.controlShape.strokeBorder(selected ? MP.brand : MP.lineStrong, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

/// A state pill. 12pt / 500 — it was 11.5pt semibold, which broke three
/// rules at once: a half-point size, a size under the 12pt floor, and a
/// weight above the 500 ceiling that only rendered correctly because
/// `MPFont.name(for:)` clamps it.
struct StatusPill: View {
    let text: String
    let tone: MP.Tone

    var body: some View {
        Text(text)
            .font(.labelMedium)
            .foregroundStyle(MP.foreground(tone))
            .padding(.horizontal, 10).padding(.vertical, 4)
            // `MP.pillShape`, not a bare `Capsule()`: one pill vocabulary.
            .background(MP.pillShape.fill(MP.background(tone)))
    }
}

/// An avatar disc. Monospace on purpose — two initials in a proportional
/// face sit off-centre in a circle, because the pair's advance depends on
/// which letters they are.
struct Initials: View {
    let text: String
    var size: CGFloat = 40
    var tone: MP.Tone = .brand

    /// Snapped to the ladder instead of `size * 0.34`: the two call sites are
    /// 40pt (-> 14) and 48pt (-> 16), which is 0.35 and 0.33 of the disc.
    private var glyph: Font {
        .mono(size >= 48 ? MPSize.copyLarge : MPSize.copy, weight: .medium)
    }

    var body: some View {
        Text(text)
            .font(glyph)
            // `onRiskHigh`, because white is only right on one of the two
            // fills: white on #C62828 is 5.62:1, but white on the dark half
            // #FF8A87 is 2.27:1 and dark needs n-950 (8.08:1).
            .foregroundStyle(tone == .high ? MP.onRiskHigh : MP.onBrand)
            .frame(width: size, height: size)
            .background(Circle().fill(tone == .high ? MP.riskHigh : MP.brand))
    }
}

/// The in-card empty state.
struct EmptyRow: View {
    let icon: String
    let title: String
    var detail: String? = nil

    var body: some View {
        VStack(spacing: 8) {
            // The ONE sanctioned `MP.faint` in this file: empty-state art is
            // decoration, and the row says the same thing in `ink` directly
            // underneath. Nothing readable rides on it.
            Image(systemName: icon).font(.displayS).foregroundStyle(MP.faint)
            Text(title).font(.copyLargeMedium).foregroundStyle(MP.ink)
            if let detail {
                // `muted` (5.39:1 light / 4.91:1 dark), not `faint`: this is
                // a sentence a patient reads.
                Text(detail).font(.copy).foregroundStyle(MP.muted)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
    }
}

/// An inline error. Separation is the `riskMedBg` fill alone — no border, no
/// shadow.
struct ErrorBanner: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(MP.riskMed)
            Text(text).font(.copyMedium).foregroundStyle(MP.ink)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        // Was `RoundedRectangle(cornerRadius: 10)` — the app's last
        // `.circular` corner, which reads as a different product next to a
        // system sheet. Same radius, continuous.
        .background(MP.controlShape.fill(MP.riskMedBg))
    }
}

/// A text field. 16pt / 400: input is the patient's own copy, so it takes the
/// larger body rung at regular weight, not a medium label weight.
struct FieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .font(.copyLarge)
            .foregroundStyle(MP.ink)
            .padding(.horizontal, 14)
            .frame(minHeight: 52)
            .background(MP.controlShape.fill(MP.panel))
            // A field border is the textbook "only cue the control exists",
            // so it is `lineStrong`. Placeholders are `MP.muted` at the call
            // site — never `MP.faint`, which is 2.59:1 and is text here.
            .overlay(MP.controlShape.strokeBorder(MP.lineStrong, lineWidth: 1))
    }
}

struct ScreenBackground: ViewModifier {
    func body(content: Content) -> some View {
        content.background(MP.canvas.ignoresSafeArea())
    }
}

extension View {
    func screen() -> some View { modifier(ScreenBackground()) }
}
