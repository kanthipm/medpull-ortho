import PhotosUI
import SwiftUI

struct MessagesView: View {
    @Environment(AppModel.self) private var app
    @State private var draft = ""
    @State private var sending = false
    @State private var error: String?
    @FocusState private var focused: Bool
    /// SwiftUI does not honour Reduce Motion for explicit animations, so the
    /// two animated moments on this screen read it themselves.
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// Files picked but not sent yet. They are uploaded on pick, so a slow
    /// photo is a slow photo rather than a slow send button; the message
    /// then carries only their ids. A row nobody sends is swept server-side.
    @State private var pending: [ChatAttachment] = []
    @State private var photoPicks: [PhotosPickerItem] = []
    @State private var uploading = false
    @State private var choosingPhotos = false
    @State private var choosingFile = false

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        header
                        if app.messages.isEmpty {
                            EmptyRow(icon: "bubble.left.and.bubble.right", title: "No messages yet",
                                     detail: app.isPersonal
                                        ? "Your morning brief lands here, and anything you write goes to your coach."
                                        : "Anything you write here goes to your care team. Task texts show up here too.")
                        }
                        ForEach(app.messages) { m in
                            Bubble(message: m).id(m.id)
                        }
                    }
                    .padding(.horizontal, 16).padding(.bottom, 12)
                }
                .defaultScrollAnchor(.bottom)
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: app.messages.count, initial: true) { _, _ in
                    guard let last = app.messages.last else { return }
                    withAnimation(MPMotion.gated(MPMotion.enter, reduceMotion: reduceMotion)) {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
                // The composer rides in the bottom safe area: on iOS 26 as a
                // `safeAreaBar`, so the conversation scrolls under it with the
                // system's scroll-edge effect; before that as a plain inset on
                // an opaque canvas strip. Everything drawn IN the bar is
                // opaque either way — the field is `panel`, the chips are
                // `soft` — so no text ever reads against moving content.
                .mpComposerBar { composer }
            }
            .ambientScreen()
            .navigationTitle(app.isPersonal ? "Coach" : "Messages")
            .navigationBarTitleDisplayMode(.inline)
            .photosPicker(isPresented: $choosingPhotos, selection: $photoPicks,
                          maxSelectionCount: 4, matching: .images)
            .fileImporter(isPresented: $choosingFile,
                          allowedContentTypes: AttachmentPrep.acceptedFiles,
                          allowsMultipleSelection: true) { result in
                if case .success(let urls) = result { attach(files: urls) }
            }
            .onChange(of: photoPicks) { _, picks in
                guard !picks.isEmpty else { return }
                attach(photos: picks)
            }
            // A light tap when a message lands — sent or received — but not
            // for the first load, which goes 0 -> N in one step.
            .sensoryFeedback(.impact(weight: .light), trigger: app.messages.count) { old, new in
                old > 0 && new > old
            }
            .mpErrorFeedback(error)
            .task {
                await app.refreshMessages()
                await app.markMessagesRead()
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(20))
                    // Nobody asked for this one, so nobody should be told it
                    // failed: a poll that misses is invisible, and the next
                    // one twenty seconds later fixes it.
                    await app.refreshMessages(surface: false)
                }
            }
        }
    }

    /// The conversation header, the way Messages heads a group thread: the
    /// people first, then their names. The screen title lives in the
    /// navigation bar now, so this is only about WHO is on the other end.
    @ViewBuilder private var header: some View {
        if let team = app.me?.patient.careTeam, !team.isEmpty {
            VStack(spacing: 8) {
                HStack(spacing: -10) {
                    ForEach(Array(team.prefix(3).enumerated()), id: \.offset) { _, member in
                        // Soft discs (brandInk on brandTint, 4.96 / 5.62)
                        // with a canvas ring so the overlap reads as three
                        // people rather than one blob.
                        Initials(text: Self.initials(member.name), size: 40, style: .soft)
                            .padding(2)
                            .background(Circle().fill(MP.canvas))
                    }
                }
                .accessibilityHidden(true)
                VStack(spacing: 2) {
                    Text("Your care team").mpFont(.copyMedium).foregroundStyle(MP.ink)
                    // `muted` on canvas: 5.03:1 light / 5.24:1 dark.
                    Text(team.map(\.name).joined(separator: ", "))
                        .mpFont(.label).foregroundStyle(MP.muted)
                        .multilineTextAlignment(.center)
                }
                .accessibilityElement(children: .combine)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 12).padding(.bottom, 10)
        }
    }

    static func initials(_ name: String) -> String {
        // "Dr. Priya Shah" -> "PS": honorifics end in a period and are not
        // what the patient calls them.
        let words = name.split(separator: " ").filter { !$0.hasSuffix(".") }
        let letters = [words.first, words.count > 1 ? words.last : nil].compactMap { $0?.first }
        return String(letters).uppercased()
    }

    private var composer: some View {
        VStack(spacing: 8) {
            if let error { ErrorBanner(text: error) }
            if !pending.isEmpty || uploading { pendingStrip }
            HStack(alignment: .bottom, spacing: 8) {
                // A Menu on the attach button, not a confirmation dialog: the
                // two choices appear where the finger already is.
                Menu {
                    Button { choosingPhotos = true } label: {
                        Label("Photo library", systemImage: "photo.on.rectangle")
                    }
                    Button { choosingFile = true } label: {
                        Label("Choose a file", systemImage: "doc")
                    }
                } label: {
                    ComposerRoundButton(systemName: "plus")
                }
                .disabled(uploading || pending.count >= 4)
                .accessibilityLabel("Attach a photo or file")
                ComposerField(placeholder: app.isPersonal ? "Message your coach" : "Message your care team",
                              text: $draft,
                              canSend: canSend,
                              busy: sending,
                              multiline: true,
                              focused: $focused,
                              send: send)
            }
        }
    }

    /// A photo can be the whole message, so words are not required — only
    /// an empty message with nothing attached is refused.
    private var canSend: Bool {
        !uploading && (!draft.trimmingCharacters(in: .whitespaces).isEmpty || !pending.isEmpty)
    }

    private var pendingStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(pending) { a in
                    HStack(spacing: 5) {
                        Image(systemName: a.isImage ? "photo" : "doc")
                            .font(.labelMedium).foregroundStyle(MP.brandInk)
                        Text(a.displayName).font(.labelMedium)
                            .foregroundStyle(MP.ink).lineLimit(1)
                        // `muted` (4.75:1 on `soft` light / 4.58:1 dark), not
                        // `faint` (2.28:1 there): a file size is text.
                        Text(a.sizeLabel).font(.label).foregroundStyle(MP.muted)
                        Button {
                            remove(a)
                        } label: {
                            // Was 9pt — four points under the floor, and on
                            // `faint`, which is the inactive tier. This is a
                            // live control, so it is 12pt on `muted`.
                            Image(systemName: "xmark").font(.labelMedium)
                                .foregroundStyle(MP.muted)
                        }
                        .accessibilityLabel("Remove \(a.displayName)")
                    }
                    .padding(.horizontal, 9).padding(.vertical, 6)
                    .background(MP.pillShape.fill(MP.soft))
                    // `MP.pillShape`, not a bare `Capsule()`, and `lineStrong`
                    // rather than `line`: `soft` is 1.13:1 against the panel
                    // this strip sits on (1.07:1 dark), so the fill separates
                    // nothing and the border is the only cue the row exists —
                    // 1.4.11's 3:1 applies to it (3.83:1 light / 5.67:1 dark).
                    .overlay(MP.pillShape.strokeBorder(MP.lineStrong, lineWidth: 1))
                }
                if uploading {
                    HStack(spacing: 5) {
                        ProgressView().controlSize(.mini)
                        Text("Adding…").font(.labelMedium)
                            .foregroundStyle(MP.muted)
                    }
                    .padding(.horizontal, 9).padding(.vertical, 6)
                    // Opaque: the strip rides over the scrolling thread on
                    // iOS 26, and `muted` is only measured on `soft` (4.76 /
                    // 4.58).
                    .background(MP.pillShape.fill(MP.soft))
                    .overlay(MP.pillShape.strokeBorder(MP.lineStrong, lineWidth: 1))
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: attaching

    private func attach(photos picks: [PhotosPickerItem]) {
        photoPicks = []
        uploading = true
        error = nil
        Task {
            defer { uploading = false }
            for pick in picks.prefix(4 - pending.count) {
                do {
                    guard let raw = try await pick.loadTransferable(type: Data.self),
                          let ready = AttachmentPrep.photo(raw) else {
                        error = "That photo could not be read."
                        continue
                    }
                    let stored = try await app.api.upload(ready.data,
                                                          contentType: ready.contentType,
                                                          filename: ready.filename)
                    pending.append(stored)
                } catch {
                    self.error = AppModel.message(for: error)
                }
            }
        }
    }

    private func attach(files urls: [URL]) {
        uploading = true
        error = nil
        Task {
            defer { uploading = false }
            for url in urls.prefix(4 - pending.count) {
                // A document picked outside the app's own container is only
                // readable while its security scope is held.
                let scoped = url.startAccessingSecurityScopedResource()
                defer { if scoped { url.stopAccessingSecurityScopedResource() } }
                guard let ready = AttachmentPrep.file(at: url) else {
                    error = "That file can’t be sent — photos and PDFs only."
                    continue
                }
                do {
                    let stored = try await app.api.upload(ready.data,
                                                          contentType: ready.contentType,
                                                          filename: ready.filename)
                    pending.append(stored)
                } catch {
                    self.error = AppModel.message(for: error)
                }
            }
        }
    }

    /// Taking one back before sending deletes the bytes rather than leaving
    /// them on the chart for a sweeper to find.
    private func remove(_ a: ChatAttachment) {
        pending.removeAll { $0.id == a.id }
        Task { try? await app.api.withdrawAttachment(id: a.id) }
    }

    private func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        let ids = pending.map(\.id)
        guard !text.isEmpty || !ids.isEmpty else { return }
        sending = true
        error = nil
        Task {
            defer { sending = false }
            do {
                try await app.send(message: text, attachmentIds: ids)
                draft = ""
                pending = []
            } catch { self.error = AppModel.message(for: error) }
        }
    }
}

struct Bubble: View {
    @Environment(AppModel.self) private var app
    let message: ChatMessage

    private var mine: Bool { message.sender == "patient" }

    /// A clinician's message is signed with their name; the app's own words
    /// are not, because that is the patient's default assumption and a badge
    /// on everything would make the one that matters invisible.
    private var who: String {
        if message.fromClinician {
            return message.authorName ?? "Care team"
        }
        switch message.sender {
        case "care_team": return "Care team"
        case "copilot": return message.channel == "sms" ? "MedPull\(MP.dot)text" : "MedPull"
        default: return message.channel == "sms" ? "You\(MP.dot)by text" : message.channel == "voice" ? "You\(MP.dot)by voice" : "You"
        }
    }

    var body: some View {
        VStack(alignment: mine ? .trailing : .leading, spacing: 3) {
            if !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                // 16pt / 400, the site's Messages look: the patient's words
                // on the sage bubble (white 6.4), everyone else's on the warm
                // grey bubble (ink 16). Opaque — a bubble is a repeating list
                // cell and carries what a post-operative patient is reading.
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
                if message.fromClinician {
                    // 12pt / 500 sage on its tint: 6.27 light / 7.98 dark.
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
            // 11.5 was a half-point size below the floor, on the non-text
            // tier. 12pt on `muted` — a signature and a timestamp are text.
            .font(.label).foregroundStyle(MP.muted)
        }
        .frame(maxWidth: .infinity, alignment: mine ? .trailing : .leading)
        .padding(mine ? .leading : .trailing, 48)
    }

    /// The tap a text message could not carry. It goes to the task itself
    /// rather than to the Tasks list, because the message already said what
    /// is being asked and making them find it again is the whole problem
    /// this button exists to remove.
    private func actionButton(_ label: String, taskId: Int) -> some View {
        Button {
            app.pendingTaskId = taskId
            app.selectedTab = .tasks
            // The task this points at was created moments ago, server-side,
            // so the cached list may not hold it yet. Tasks opens on whatever
            // arrives; without this the button lands on an empty list.
            Task { await app.refreshTasks() }
        } label: {
            Label(label, systemImage: "arrow.right.circle.fill")
        }
        // The shared primary capsule, pressed scale gated on Reduce Motion,
        // 44pt tall.
        .buttonStyle(.mpFilled)
        .padding(.top, 2)
    }
}

// MARK: - Shared conversation pieces (Messages and Talk)

/// A message bubble: 20pt continuous corners with a tighter 6pt corner at
/// the bottom on the speaker's side — the tail, drawn as geometry rather
/// than a glyph so it scales and strokes like the rest of the shape.
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

/// The 44pt round button beside a composer field (attach). An opaque
/// `panel` disc with a `lineStrong` edge (3.83:1 light / 5.67:1 dark) and a
/// `brandInk` glyph (5.75 / 6.78 on panel): it floats over the thread on
/// iOS 26, so it cannot borrow its ground.
struct ComposerRoundButton: View {
    let systemName: String
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Image(systemName: systemName)
            .font(.systemGlyphs(17, weight: .semibold))
            .foregroundStyle(isEnabled ? MP.brandInk : MP.disabledInk)
            .frame(width: 44, height: 44)
            .background(Circle().fill(isEnabled ? MP.panel : MP.disabledFill))
            .overlay(Circle().strokeBorder(MP.lineStrong, lineWidth: 1))
            .contentShape(Circle())
    }
}

/// The composer: a capsule field with the send button inside it, bottom-
/// trailing, the way Messages does it. The field keeps its `lineStrong`
/// border — an empty field's edge is its only cue (1.4.11).
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
            // The prompt is set explicitly because SwiftUI's own placeholder
            // colour is not a token and does not pass: #C5C5C7 on white is
            // 1.72:1. `muted` on `panel` is 5.39:1 light / 4.91:1 dark.
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
                            // Disabled is the token pair, not a faded disc:
                            // `disabledInk` on `disabledFill` is 4.75 / 4.58,
                            // with the `lineStrong` edge because that fill is
                            // 1.06:1 against the panel it sits in.
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

private struct ComposerSendStyle: ButtonStyle {
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
    /// A conversation composer pinned to the bottom safe area (Messages and
    /// Talk). iOS 26: `safeAreaBar` over the thread. Earlier: an opaque
    /// canvas strip with a hairline.
    func mpComposerBar<Bar: View>(@ViewBuilder _ bar: @escaping () -> Bar) -> some View {
        modifier(MPComposerBar(bar: bar))
    }
}
