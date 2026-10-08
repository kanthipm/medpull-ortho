import SwiftUI

/// The list vocabulary the rebuilt screens share. Rows are quiet: a small
/// monochrome glyph on a soft tint, ink text, a figure, a chevron. Colour
/// marks a category (the glyph) or a state (a dot beside a word), never both,
/// and nothing in a row is a gradient. The gradient is spent once per
/// screen, on the hero.

// MARK: - Glyph

/// A category glyph: an SF Symbol in the category's ink on its tint disc.
struct Glyph: View {
    let systemName: String
    var family: MP.Category = .teal
    var size: CGFloat = 32
    @ScaledMetric(relativeTo: .body) private var scale: CGFloat = 1

    private var side: CGFloat { (size * min(scale, 1.4)).rounded() }

    var body: some View {
        Image(systemName: systemName)
            .font(.system(size: (side * 0.46).rounded(), weight: .medium))
            .foregroundStyle(MP.categoryInk(family))
            .frame(width: side, height: side)
            .background(Circle().fill(MP.categoryTint(family)))
            .accessibilityHidden(true)
    }
}

// MARK: - Section title

/// A section title on the canvas: 20/500 ink, with an optional note in
/// `body` on the same baseline, and an optional trailing action.
struct SectionTitle: View {
    let title: String
    var note: String? = nil
    var actionTitle: String? = nil
    var action: (() -> Void)? = nil

    init(_ title: String, note: String? = nil, actionTitle: String? = nil, action: (() -> Void)? = nil) {
        self.title = title
        self.note = note
        self.actionTitle = actionTitle
        self.action = action
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(title)
                .mpFont(.subheadMedium)
                .foregroundStyle(MP.ink)
                .accessibilityAddTraits(.isHeader)
            if let note {
                Text(note).mpFont(.copy).foregroundStyle(MP.muted).lineLimit(1)
            }
            Spacer(minLength: 8)
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
            }
        }
        .padding(.horizontal, 4)
    }
}

/// A header row INSIDE a card: 15/500 ink title, a muted note, a trailing
/// action. The card's first row.
struct CardTitleRow: View {
    let title: String
    var note: String? = nil
    var actionTitle: String? = nil
    var action: (() -> Void)? = nil

    init(_ title: String, note: String? = nil, actionTitle: String? = nil, action: (() -> Void)? = nil) {
        self.title = title
        self.note = note
        self.actionTitle = actionTitle
        self.action = action
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(title).mpFont(MPType(15, .medium)).foregroundStyle(MP.ink)
                .accessibilityAddTraits(.isHeader)
            if let note {
                Text(note).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
            }
            Spacer(minLength: 8)
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
            }
        }
        .frame(minHeight: 40)
        .padding(.horizontal, 16)
        .padding(.top, 6)
    }
}

// MARK: - State

/// A state as a dot and a word, no fill. For a row; the pill is for a hero.
struct StateLabel: View {
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
            Text(text).mpFont(.label).foregroundStyle(MP.foreground(tone)).lineLimit(1)
        }
    }
}

// MARK: - Sparkline

/// Two weeks in 60 points: a line for a sampled reading, bars for a daily
/// total. Ink, with the newest mark in the brand fill. Decorative — the row
/// states the value — so it is hidden from VoiceOver.
struct Sparkline: View {
    let values: [Double]
    var bars: Bool = false
    var width: CGFloat = 60
    var height: CGFloat = 24

    var body: some View {
        Canvas { ctx, size in
            let v = values
            guard v.count > 1, let lo = v.min(), let hi = v.max() else { return }
            let span = max(hi - (bars ? 0 : lo), 0.0001)
            let base = bars ? 0 : lo
            let ink = MP.ink.opacity(0.55)
            if bars {
                let gap: CGFloat = 2
                let w = max(1, (size.width - gap * CGFloat(v.count - 1)) / CGFloat(v.count))
                for (i, value) in v.enumerated() {
                    let h = max(1.5, CGFloat((value - base) / span) * size.height)
                    let rect = CGRect(x: CGFloat(i) * (w + gap), y: size.height - h, width: w, height: h)
                    let path = Path(roundedRect: rect, cornerRadius: 1)
                    ctx.fill(path, with: .color(i == v.count - 1 ? MP.brand : ink))
                }
            } else {
                var path = Path()
                for (i, value) in v.enumerated() {
                    let x = CGFloat(i) / CGFloat(v.count - 1) * size.width
                    let y = size.height - CGFloat((value - base) / span) * (size.height - 4) - 2
                    if i == 0 { path.move(to: CGPoint(x: x, y: y)) } else { path.addLine(to: CGPoint(x: x, y: y)) }
                }
                ctx.stroke(path, with: .color(ink), style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
                if let last = v.last {
                    let y = size.height - CGFloat((last - base) / span) * (size.height - 4) - 2
                    let dot = Path(ellipseIn: CGRect(x: size.width - 3, y: y - 3, width: 6, height: 6))
                    ctx.fill(dot, with: .color(MP.brand))
                }
            }
        }
        .frame(width: width, height: height)
        .accessibilityHidden(true)
    }
}

// MARK: - Rows

/// A navigation row: glyph, title, one-line subtitle, trailing content, a
/// chevron. The tap target is the whole row.
struct ListRow<Trailing: View>: View {
    let title: String
    var subtitle: String? = nil
    var symbol: String? = nil
    var family: MP.Category = .teal
    var chevron: Bool = true
    @ViewBuilder var trailing: () -> Trailing
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    init(_ title: String, subtitle: String? = nil, symbol: String? = nil, family: MP.Category = .teal,
         chevron: Bool = true, @ViewBuilder trailing: @escaping () -> Trailing) {
        self.title = title
        self.subtitle = subtitle
        self.symbol = symbol
        self.family = family
        self.chevron = chevron
        self.trailing = trailing
    }

    var body: some View {
        let stacked = dynamicTypeSize.isAccessibilitySize
        HStack(alignment: .center, spacing: 12) {
            if let symbol { Glyph(systemName: symbol, family: family) }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle).mpFont(.label).foregroundStyle(MP.muted)
                        .lineLimit(stacked ? nil : 2)
                        .fixedSize(horizontal: false, vertical: true)
                        .multilineTextAlignment(.leading)
                }
                if stacked { trailing() }
            }
            Spacer(minLength: 8)
            if !stacked { trailing() }
            if chevron {
                Image(systemName: "chevron.right")
                    .font(.systemGlyphs(13, weight: .semibold))
                    .foregroundStyle(MP.faint)
                    .accessibilityHidden(true)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 11)
        .frame(minHeight: 52)
        .contentShape(Rectangle())
    }
}

extension ListRow where Trailing == EmptyView {
    init(_ title: String, subtitle: String? = nil, symbol: String? = nil, family: MP.Category = .teal,
         chevron: Bool = true) {
        self.init(title, subtitle: subtitle, symbol: symbol, family: family, chevron: chevron) { EmptyView() }
    }
}

/// The divider between two rows that start with a 32pt glyph.
struct RowDivider: View {
    var glyph: Bool = true
    var body: some View { InsetDivider(leading: glyph ? 16 + 32 + 12 : 16) }
}

/// A figure with its unit, for a row's trailing edge: 16/500 tabular figures
/// and a 12pt unit.
struct RowFigure: View {
    let value: String
    var unit: String? = nil

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 3) {
            Text(value).font(.figuresCopyLarge).foregroundStyle(MP.ink)
                .lineLimit(1).minimumScaleFactor(0.7)
            if let unit, !unit.isEmpty {
                Text(unit).mpFont(.label).foregroundStyle(MP.muted).lineLimit(1)
            }
        }
    }
}

/// A big figure for a detail screen or a hero caption: the display face,
/// light, with the unit beside it.
struct BigFigure: View {
    let value: String
    var unit: String? = nil
    var size: CGFloat = MPSize.displayL
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(value)
                .font(.figuresDisplay(size))
                .kerning(-size * 0.04)
                .foregroundStyle(MP.ink)
                .lineLimit(1).minimumScaleFactor(0.6)
                .contentTransition(reduceMotion ? .identity : .numericText())
            if let unit, !unit.isEmpty {
                Text(unit).mpFont(.copyMedium).foregroundStyle(MP.muted)
            }
        }
    }
}

/// A whole card as a button: the gated 0.97 press scale, nothing else.
struct CardTapStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .contentShape(MP.surfaceShape)
            .scaleEffect(MPMotion.pressScale(configuration.isPressed, reduceMotion: reduceMotion))
            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion),
                       value: configuration.isPressed)
    }
}

// MARK: - Dates for rows

extension Dates {
    /// "Sep 29" for a server day string; the raw string if it does not parse.
    static func monthDay(_ raw: String) -> String {
        guard let d = parse(raw) else { return raw }
        return d.formatted(.dateTime.month(.abbreviated).day())
    }

    /// Whole days from a server day to today (0 = today), or nil.
    static func daysAgo(_ raw: String) -> Int? {
        guard let d = parse(raw) else { return nil }
        return Calendar.current.dateComponents([.day], from: Calendar.current.startOfDay(for: d),
                                               to: Calendar.current.startOfDay(for: Date())).day
    }

    /// "today", "yesterday", "3 days ago".
    static func agoWords(_ raw: String) -> String {
        guard let n = daysAgo(raw) else { return "" }
        switch n {
        case ..<1: return "today"
        case 1: return "yesterday"
        default: return "\(n) days ago"
        }
    }
}
