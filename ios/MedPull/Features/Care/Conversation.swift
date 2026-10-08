import SwiftUI

/// The pieces of a conversation: the bubble, its shape, the composer field
/// with the send button inside it, the round buttons beside it, and the
/// bar that pins the composer to the bottom of the screen.

struct Bubble: View {
    @Environment(AppModel.self) private var app
    let message: ChatMessage

    private var mine: Bool { message.sender == "patient" }

    /// A clinician's message is signed with their name; the app's own words
    /// are not, because that is the patient's default assumption and a badge
    /// on everything would make the one that matters invisible.
    private var who: String {
        if message.fromClinician && !app.isPersonal {
            return message.authorName ?? "Care team"
        }
        switch message.sender {
        case "care_team": return "Care team"
        case "copilot": return message.channel == "sms" ? "MedPull\(MP.dot)text" : (app.isPersonal ? "Coach" : "MedPull")
        default: return message.channel == "sms" ? "You\(MP.dot)by text" : message.channel == "voice" ? "You\(MP.dot)by voice" : "You"
        }
    }

    var body: some View {
        VStack(alignment: mine ? .trailing : .leading, spacing: 3) {
            if !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                // The patient's words on the sage bubble (white 6.4), everyone
                // else's on the warm grey bubble (ink 16). Opaque: a bubble is
                // a repeating cell carrying what a sore patient is reading.
                Text(message.text)
                    .font(.copyLarge)
                    .foregroundStyle(mine ? Color.white : MP.ink)
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background {
                        if mine {
                            BubbleFill().clipShape(BubbleShape(mine: true))
                        } else {
                            BubbleShape(mine: false)
                                .fill(message.sender == "care_team" || message.fromClinician
                                      ? MP.fillStrong : MP.fill)
                                .background(BubbleShape(mine: false).fill(MP.panel.opacity(0.7)))
                        }
                    }
            }
            AttachmentStrip(attachments: message.files, mine: mine)
            if let taskId = message.action?.opensTask, let label = message.action?.label {
                actionButton(label, taskId: taskId)
            }
            HStack(spacing: 4) {
                Text(who)
                if message.fromClinician && !app.isPersonal {
                    Text("Care team approved")
                        .font(.labelMedium)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(MP.pillShape.fill(MP.brandTint))
                        .foregroundStyle(MP.brandInk)
                }
                Text("·")
                Text(Dates.relative(message.createdAt))
                if message.deliveryStatus == "failed" {
                    Text("\(MP.dotLead)not delivered by text").foregroundStyle(MP.riskMed)
                }
            }
            .font(.label).foregroundStyle(MP.muted)
        }
        .frame(maxWidth: .infinity, alignment: mine ? .trailing : .leading)
        .padding(mine ? .leading : .trailing, 48)
    }

    /// The tap a text message could not carry: straight to the task.
    private func actionButton(_ label: String, taskId: Int) -> some View {
        Button {
            app.pendingTaskId = taskId
            app.selectedTab = .today
            Task { await app.refreshTasks() }
        } label: {
            Label(label, systemImage: "arrow.right.circle.fill")
        }
        .buttonStyle(.mpFilled)
        .padding(.top, 2)
    }
}

/// A message bubble: 20pt continuous corners with a tighter 6pt corner at
/// the bottom on the speaker's side.
struct BubbleShape: InsettableShape {
    let mine: Bool
    var inset: CGFloat = 0

    func path(in rect: CGRect) -> Path {
        let big = max(MP.radiusSurface - inset, 0)
        let tail = max(6 - inset, 0)
        return UnevenRoundedRectangle(
            topLeadingRadius: big,
            bottomLeadingRadius: mine ? big : tail,
            bottomTrailingRadius: mine ? tail : big,
            topTrailingRadius: big,
            style: .continuous
        )
        .path(in: rect.insetBy(dx: inset, dy: inset))
    }

    func inset(by amount: CGFloat) -> BubbleShape {
        BubbleShape(mine: mine, inset: inset + amount)
    }
}

/// The 44pt round button beside a composer field. An opaque `panel` disc
/// with a `lineStrong` edge and a `brandInk` glyph; `active` turns it into
/// the risk fill (the mic while listening).
struct ComposerRoundButton: View {
    let systemName: String
    var active = false
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Image(systemName: systemName)
            .font(.systemGlyphs(17, weight: .semibold))
            .foregroundStyle(!isEnabled ? MP.disabledInk : active ? MP.onRiskHigh : MP.brandInk)
            .frame(width: 44, height: 44)
            .background(Circle().fill(!isEnabled ? MP.disabledFill : active ? MP.riskHigh : MP.panel))
            .overlay(Circle().strokeBorder(active ? Color.clear : MP.lineStrong, lineWidth: 1))
            .contentShape(Circle())
            .contentTransition(.symbolEffect(.replace))
    }
}

/// The composer: a capsule field with the send button inside it.
struct ComposerField: View {
    let placeholder: String
    @Binding var text: String
    let canSend: Bool
    var busy = false
    var multiline = false
    var focused: FocusState<Bool>.Binding
    let send: () -> Void

    var body: some View {
        HStack(alignment: .bottom, spacing: 4) {
            Group {
                if multiline {
                    TextField(placeholder, text: $text,
                              prompt: Text(placeholder).foregroundStyle(MP.muted),
                              axis: .vertical)
                        .lineLimit(1...5)
                } else {
                    TextField(placeholder, text: $text,
                              prompt: Text(placeholder).foregroundStyle(MP.muted))
                        .submitLabel(.send)
                        .onSubmit { if canSend && !busy { send() } }
                }
            }
            .font(.copyLarge)
            .foregroundStyle(MP.ink)
            .focused(focused)
            .padding(.leading, 16)
            .padding(.vertical, 11)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)

            Button(action: send) {
                ZStack {
                    if busy {
                        ProgressView().tint(MP.onAction).controlSize(.small)
                    } else {
                        Image(systemName: "arrow.up")
                            .font(.systemGlyphs(15, weight: .semibold))
                            .foregroundStyle(canSend ? MP.onAction : MP.disabledInk)
                    }
                }
                .frame(width: 32, height: 32)
                .background(Circle().fill(canSend || busy ? MP.action : MP.disabledFill))
                .overlay {
                    if !canSend && !busy { Circle().strokeBorder(MP.lineStrong, lineWidth: 1) }
                }
                .frame(width: 44, height: 44)
                .contentShape(Circle())
            }
            .buttonStyle(ComposerSendStyle())
            .disabled(!canSend || busy)
            .accessibilityLabel(busy ? "Sending" : "Send")
            .padding(.trailing, 2)
        }
        .background(RoundedRectangle(cornerRadius: 22, style: .continuous).fill(MP.panel))
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous)
            .strokeBorder(MP.lineStrong, lineWidth: 1))
    }
}

struct ComposerSendStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(reduceMotion ? 1 : (configuration.isPressed ? 0.88 : 1))
            .animation(MPMotion.gated(MPMotion.press, reduceMotion: reduceMotion),
                       value: configuration.isPressed)
    }
}

private struct MPComposerBar<Bar: View>: ViewModifier {
    @ViewBuilder let bar: () -> Bar

    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 26, *), !MPGlass.legacyOverride {
            // No fill of our own: the system's scroll-edge effect sits behind
            // the bar, and every element in it is opaque.
            content.safeAreaBar(edge: .bottom) {
                bar()
                    .padding(.horizontal, 12)
                    .padding(.top, 6)
                    .padding(.bottom, 8)
            }
        } else {
            content.safeAreaInset(edge: .bottom, spacing: 0) {
                bar()
                    .padding(.horizontal, 12)
                    .padding(.top, 8)
                    .padding(.bottom, 8)
                    .background(MP.canvas.overlay(alignment: .top) {
                        Rectangle().fill(MP.hairline).frame(height: 1)
                    })
            }
        }
    }
}

extension View {
    /// A conversation composer pinned to the bottom safe area. iOS 26:
    /// `safeAreaBar` over the thread. Earlier: an opaque canvas strip.
    func mpComposerBar<Bar: View>(@ViewBuilder _ bar: @escaping () -> Bar) -> some View {
        modifier(MPComposerBar(bar: bar))
    }
}
