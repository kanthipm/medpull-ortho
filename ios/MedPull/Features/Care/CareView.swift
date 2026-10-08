import PhotosUI
import SwiftUI

/// One thread with everyone on the other end. What the patient types goes
/// to their care team. The mic, and the quick-log chips, go to MedPull's
/// assistant, which logs pain or a task, answers at once, and passes
/// anything serious to the team. Both land in the same thread, which is
/// also where task texts and the assistant's replies already lived, so a
/// patient has one place to look. A subscriber's space has no care team:
/// everything there goes to the coach.
struct CareView: View {
    @Environment(AppModel.self) private var app
    @State private var draft = ""
    @State private var sending = false
    @State private var error: String?
    @FocusState private var focused: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var speech = SpeechController()
    @State private var thinking = false
    /// True while the draft began from a quick-log chip: it goes to the
    /// assistant, not the care team, and the composer says so.
    @State private var draftToAssistant = false

    @State private var pending: [ChatAttachment] = []
    @State private var photoPicks: [PhotosPickerItem] = []
    @State private var uploading = false
    @State private var choosingPhotos = false
    @State private var choosingFile = false

    /// Quick logs. They FILL the field, never send it: a tapped "my pain is
    /// a 4" that went straight to the chart would be a score nobody gave.
    private var quickLogs: [String] {
        app.isPersonal
            ? ["Why is my readiness low?", "I ran 45 minutes, RPE 7", "Energy is a 6 today"]
            : ["My pain is a ", "I did my exercises", "I walked today", "A note for my nurse: "]
    }

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        header
                        if app.messages.isEmpty { intro }
                        ForEach(app.messages) { m in
                            Bubble(message: m).id(m.id)
                        }
                        if speech.isListening && !speech.transcript.isEmpty {
                            Text(speech.transcript).font(.copyLarge).foregroundStyle(MP.muted)
                                .frame(maxWidth: .infinity, alignment: .trailing)
                                .padding(.leading, 48)
                                .id("transcript")
                        }
                        if thinking {
                            HStack(spacing: 8) {
                                ProgressView().tint(MP.brandInk)
                                Text(app.isPersonal ? "Your coach is thinking" : "MedPull is thinking")
                                    .mpFont(.label).foregroundStyle(MP.muted)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .id("thinking")
                        }
                        if let e = speech.errorText { ErrorBanner(text: e) }
                    }
                    .padding(.horizontal, 16).padding(.bottom, 12)
                }
                .defaultScrollAnchor(app.messages.isEmpty ? .top : .bottom)
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: app.messages.count, initial: true) { _, _ in
                    guard let last = app.messages.last else { return }
                    withAnimation(MPMotion.gated(MPMotion.enter, reduceMotion: reduceMotion)) {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
                .onChange(of: thinking) { _, on in
                    if on { withAnimation(MPMotion.gated(MPMotion.enter, reduceMotion: reduceMotion)) { proxy.scrollTo("thinking", anchor: .bottom) } }
                }
                .onChange(of: speech.transcript) { _, _ in
                    proxy.scrollTo("transcript", anchor: .bottom)
                }
                .mpComposerBar { composer }
            }
            .ambientScreen(height: 300)
            .navigationTitle(app.isPersonal ? "Coach" : "Care team")
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
            .onChange(of: draft) { _, new in if new.isEmpty { draftToAssistant = false } }
            .sensoryFeedback(.impact(weight: .light), trigger: app.messages.count) { old, new in
                old > 0 && new > old
            }
            .sensoryFeedback(trigger: speech.isListening) { _, on in on ? .start : .stop }
            .mpErrorFeedback(error)
            .task {
                await app.refreshMessages()
                await app.markMessagesRead()
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(20))
                    await app.refreshMessages(surface: false)
                }
            }
        }
    }

    // MARK: header

    /// Who is on the other end, the way Messages heads a group thread.
    @ViewBuilder private var header: some View {
        if let team = app.me?.patient.careTeam, !team.isEmpty {
            VStack(spacing: 8) {
                HStack(spacing: -10) {
                    ForEach(Array(team.prefix(3).enumerated()), id: \.offset) { _, member in
                        Initials(text: TeamAvatars.initials(member.name), size: 40, style: .soft)
                            .padding(2)
                            .background(Circle().fill(MP.canvas))
                    }
                }
                .accessibilityHidden(true)
                VStack(spacing: 2) {
                    Text("Your care team").mpFont(.copyMedium).foregroundStyle(MP.ink)
                    Text(team.map(\.name).joined(separator: ", "))
                        .mpFont(.label).foregroundStyle(MP.muted)
                        .multilineTextAlignment(.center)
                }
                .accessibilityElement(children: .combine)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 12).padding(.bottom, 10)
        } else if app.isPersonal {
            VStack(spacing: 8) {
                Glyph(systemName: "sparkles", family: .indigo, size: 44)
                Text("Your coach").mpFont(.copyMedium).foregroundStyle(MP.ink)
                Text("Knows today’s readouts. Ask about any of your numbers.")
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 12).padding(.bottom, 10)
        }
    }

    private var intro: some View {
        Card {
            VStack(alignment: .leading, spacing: 8) {
                Text(app.isPersonal ? "Nothing here yet" : "How this works")
                    .mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                Text(app.isPersonal
                     ? "Your morning brief lands here, and anything you write goes to your coach."
                     : "Anything you type goes to your care team. Tap the mic, or one of the quick logs, to tell MedPull how you feel: it logs it for you, answers straight away, and passes anything serious to the team.")
                    .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: composer

    private var composer: some View {
        VStack(spacing: 8) {
            if let error { ErrorBanner(text: error) }
            if !pending.isEmpty || uploading { pendingStrip }
            if draft.isEmpty && !speech.isListening { quickRow }
            if draftToAssistant && !draft.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: "sparkles").font(.systemGlyphs(12, weight: .medium))
                    Text(app.isPersonal ? "To your coach" : "To MedPull, which logs it for you")
                    Spacer()
                    Button("Clear") { draft = ""; draftToAssistant = false }
                        .buttonStyle(MPButtonStyle(kind: .plain, bare: true))
                        .controlSize(.small)
                }
                .mpFont(.label).foregroundStyle(MP.brandInk)
                .padding(.horizontal, 6)
            }
            HStack(alignment: .bottom, spacing: 8) {
                if !app.isPersonal {
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
                    .disabled(uploading || pending.count >= 4 || speech.isListening || draftToAssistant)
                    .accessibilityLabel("Attach a photo or file")
                }
                ComposerField(placeholder: speech.isListening ? "Listening…"
                                : app.isPersonal ? "Ask your coach"
                                : draftToAssistant ? "Tell MedPull" : "Message your care team",
                              text: $draft,
                              canSend: canSend,
                              busy: sending,
                              multiline: true,
                              focused: $focused,
                              send: send)
                    .disabled(speech.isListening)
                Button { toggleMic() } label: {
                    ComposerRoundButton(systemName: speech.isListening ? "stop.fill" : "mic.fill",
                                        active: speech.isListening)
                }
                .buttonStyle(ComposerSendStyle())
                .disabled(thinking || sending)
                .accessibilityLabel(speech.isListening ? "Stop and send" : "Talk")
                .accessibilityHint(speech.isListening ? "Sends what you said"
                                   : app.isPersonal ? "Speak to your coach" : "Speak to MedPull; it logs it for you")
            }
            if speech.isListening {
                Text("Listening. Tap stop to send.")
                    .mpFont(.label).foregroundStyle(MP.riskHigh)
                    .accessibilityAddTraits(.updatesFrequently)
            }
        }
    }

    /// Chips that go straight to the assistant.
    private var quickRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                Text(app.isPersonal ? "Ask" : "Quick log")
                    .mpFont(.labelMedium).foregroundStyle(MP.muted).padding(.trailing, 2)
                ForEach(quickLogs, id: \.self) { phrase in
                    Button {
                        draft = phrase
                        draftToAssistant = true
                        focused = true
                    } label: { Text(phrase.trimmingCharacters(in: .whitespaces) + (phrase.hasSuffix(" ") ? "…" : "")) }
                        .buttonStyle(MPButtonStyle(kind: .gray))
                        .controlSize(.small)
                        .disabled(thinking)
                        .accessibilityHint("Puts this in the message field")
                }
            }
            .padding(.horizontal, 4)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var canSend: Bool {
        !uploading && !speech.isListening && !thinking
            && (!draft.trimmingCharacters(in: .whitespaces).isEmpty || !pending.isEmpty)
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
                        Text(a.sizeLabel).font(.label).foregroundStyle(MP.muted)
                        Button { remove(a) } label: {
                            Image(systemName: "xmark").font(.labelMedium).foregroundStyle(MP.muted)
                        }
                        .accessibilityLabel("Remove \(a.displayName)")
                    }
                    .padding(.horizontal, 9).padding(.vertical, 6)
                    .background(MP.pillShape.fill(MP.soft))
                    .overlay(MP.pillShape.strokeBorder(MP.lineStrong, lineWidth: 1))
                }
                if uploading {
                    HStack(spacing: 5) {
                        ProgressView().controlSize(.mini)
                        Text("Adding…").font(.labelMedium).foregroundStyle(MP.muted)
                    }
                    .padding(.horizontal, 9).padding(.vertical, 6)
                    .background(MP.pillShape.fill(MP.soft))
                    .overlay(MP.pillShape.strokeBorder(MP.lineStrong, lineWidth: 1))
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: sending

    /// Typed: to the care team on a hospital record, to the coach in a
    /// personal space.
    private func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        let ids = pending.map(\.id)
        guard !text.isEmpty || !ids.isEmpty else { return }
        if app.isPersonal || draftToAssistant {
            draft = ""
            draftToAssistant = false
            ask(text, channel: "app", speak: false)
            return
        }
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

    /// To the assistant. The exchange lands on the thread server-side, so
    /// the refresh inside `ask` is what draws it.
    private func ask(_ text: String, channel: String, speak: Bool) {
        thinking = true
        error = nil
        Task {
            defer { thinking = false }
            do {
                let r = try await app.ask(text, channel: channel)
                if speak { speech.speak(r.reply) }
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }

    private func toggleMic() {
        if speech.isListening {
            let heard = speech.stopListening()
            if !heard.isEmpty { ask(heard, channel: "voice", speak: true) }
        } else {
            focused = false
            Task {
                if !speech.authorized {
                    guard await speech.requestAuthorization() else { return }
                }
                speech.startListening()
            }
        }
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
                    let stored = try await app.api.upload(ready.data, contentType: ready.contentType,
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
                let scoped = url.startAccessingSecurityScopedResource()
                defer { if scoped { url.stopAccessingSecurityScopedResource() } }
                guard let ready = AttachmentPrep.file(at: url) else {
                    error = "That file can’t be sent — photos and PDFs only."
                    continue
                }
                do {
                    let stored = try await app.api.upload(ready.data, contentType: ready.contentType,
                                                          filename: ready.filename)
                    pending.append(stored)
                } catch {
                    self.error = AppModel.message(for: error)
                }
            }
        }
    }

    private func remove(_ a: ChatAttachment) {
        pending.removeAll { $0.id == a.id }
        Task { try? await app.api.withdrawAttachment(id: a.id) }
    }
}
