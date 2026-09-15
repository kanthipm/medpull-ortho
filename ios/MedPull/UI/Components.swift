import SwiftUI

/// Instrument panel: hairline border, flat surface, like SectionCard.
struct Card<Content: View>: View {
    var padding: CGFloat = 16
    var tint: Bool = false
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: MP.cardRadius, style: .continuous)
                    .fill(tint ? AnyShapeStyle(LinearGradient(colors: [MP.panel, MP.brandTint.opacity(0.55)],
                                                              startPoint: .top, endPoint: .bottom))
                               : AnyShapeStyle(MP.panel))
            )
            .overlay(
                RoundedRectangle(cornerRadius: MP.cardRadius, style: .continuous)
                    .strokeBorder(MP.line, lineWidth: 1)
            )
    }
}

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
                    ProgressView().tint(.white)
                } else {
                    if let icon { Image(systemName: icon) }
                    Text(title)
                }
            }
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(RoundedRectangle(cornerRadius: MP.buttonRadius, style: .continuous).fill(MP.brand))
        }
        .buttonStyle(.plain)
        .disabled(disabled || loading)
        .opacity(disabled ? 0.45 : 1)
    }
}

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
            .font(.system(size: 15, weight: .semibold))
            .foregroundStyle(MP.ink)
            .frame(maxWidth: .infinity, minHeight: 48)
            .background(RoundedRectangle(cornerRadius: MP.buttonRadius, style: .continuous).fill(MP.panel))
            .overlay(RoundedRectangle(cornerRadius: MP.buttonRadius, style: .continuous).strokeBorder(MP.line))
        }
        .buttonStyle(.plain)
        .disabled(loading)
    }
}

/// The check-in page's answer chip.
struct Chip: View {
    let label: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(selected ? MP.brand : MP.ink)
                .padding(.horizontal, 16)
                .frame(minHeight: 44)
                .background(RoundedRectangle(cornerRadius: MP.buttonRadius, style: .continuous)
                    .fill(selected ? MP.brandTint : MP.panel))
                .overlay(RoundedRectangle(cornerRadius: MP.buttonRadius, style: .continuous)
                    .strokeBorder(selected ? MP.brand : MP.line, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

struct StatusPill: View {
    let text: String
    let tone: MP.Tone

    var body: some View {
        Text(text)
            .font(.system(size: 11.5, weight: .semibold))
            .foregroundStyle(MP.foreground(tone))
            .padding(.horizontal, 9).padding(.vertical, 4)
            .background(Capsule().fill(MP.background(tone)))
    }
}

struct Initials: View {
    let text: String
    var size: CGFloat = 40
    var tone: MP.Tone = .brand

    var body: some View {
        Text(text)
            .font(.system(size: size * 0.34, weight: .semibold, design: .monospaced))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(Circle().fill(tone == .high ? MP.riskHigh : MP.brand))
    }
}

struct EmptyRow: View {
    let icon: String
    let title: String
    var detail: String? = nil

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon).font(.system(size: 26)).foregroundStyle(MP.faint)
            Text(title).font(.system(size: 15, weight: .semibold)).foregroundStyle(MP.ink)
            if let detail {
                Text(detail).font(.system(size: 13)).foregroundStyle(MP.muted)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
    }
}

struct ErrorBanner: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(MP.riskMed)
            Text(text).font(.system(size: 13.5, weight: .medium)).foregroundStyle(MP.ink)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(MP.riskMedBg))
    }
}

/// A field styled like the console's `.field`.
struct FieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .font(.system(size: 17, weight: .medium))
            .padding(.horizontal, 14)
            .frame(minHeight: 52)
            .background(RoundedRectangle(cornerRadius: MP.buttonRadius, style: .continuous).fill(MP.panel))
            .overlay(RoundedRectangle(cornerRadius: MP.buttonRadius, style: .continuous).strokeBorder(MP.line))
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
