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
    @State private var picking = false
    @State private var choosingPhotos = false
    @State private var choosingFile = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 10) {
                            header
                            if app.messages.isEmpty {
                                EmptyRow(icon: "bubble.left.and.bubble.right", title: "No messages yet",
                                         detail: "Anything you write here goes to your care team. Task texts show up here too.")
                            }
                            ForEach(app.messages) { m in
                                Bubble(message: m).id(m.id)
                            }
                        }
                        .padding(.horizontal, 16).padding(.bottom, 12)
                    }
                    .onChange(of: app.messages.count, initial: true) { _, _ in
                        guard let last = app.messages.last else { return }
                        withAnimation(MPMotion.gated(MPMotion.enter, reduceMotion: reduceMotion)) {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
                composer
            }
            .screen()
            .confirmationDialog("Attach", isPresented: $picking, titleVisibility: .visible) {
                Button("Photo library") { choosingPhotos = true }
                Button("Choose a file") { choosingFile = true }
                Button("Cancel", role: .cancel) {}
            }
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
            .toolbar(.hidden, for: .navigationBar)
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

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Messages").title(MPSize.displayS)
            if let team = app.me?.patient.careTeam, !team.isEmpty {
                Text("Your care team: " + team.map(\.name).joined(separator: ", "))
                    .font(.copy).foregroundStyle(MP.muted)
            }
        }
        .padding(.top, 8).padding(.bottom, 6)
    }

    private var composer: some View {
        VStack(spacing: 6) {
            if let error { ErrorBanner(text: error) }
            if !pending.isEmpty || uploading { pendingStrip }
            HStack(alignment: .bottom, spacing: 8) {
                Button {
                    picking = true
                } label: {
                    Image(systemName: "paperclip").font(.copyLargeMedium)
                        // `brandInk`, not `brand`: a glyph set with
                        // `foregroundStyle` is a foreground, and #1976D2 as a
                        // foreground is 3.74:1 on dark panel. `brandInk` is
                        // 5.75:1 light / 6.78:1 dark.
                        .foregroundStyle(MP.brandInk)
                        .frame(width: 40, height: 44)
                }
                .disabled(uploading || pending.count >= 4)
                .accessibilityLabel("Attach a photo or file")
                // The prompt is set explicitly because SwiftUI's own
                // placeholder colour is not a token and does not pass: it
                // renders #C5C5C7 on white (1.72:1) and #545A62 on dark panel
                // (2.47:1), both WCAG 1.4.3 failures on text a patient reads.
                // `muted` is the placeholder tier (5.39:1 light / 4.91:1
                // dark); `faint` is not. FieldStyle cannot reach this —
                // SwiftUI gives no hook — so it belongs at the call site.
                TextField("Message your care team", text: $draft,
                          prompt: Text("Message your care team").foregroundStyle(MP.muted),
                          axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(FieldStyle())
                    .focused($focused)
                Button {
                    send()
                } label: {
                    // Disabled is the token pair, not a `faint` disc: a white
                    // arrow on `faint` was 2.60:1 and read as an enabled button
                    // drawn badly. `disabledInk` on `disabledFill` is 4.75:1
                    // light / 4.58:1 dark, and because that fill is only 1.06:1
                    // against the panel behind it the disabled disc takes the
                    // `lineStrong` edge to keep its shape — the same treatment
                    // PrimaryButton uses.
                    Image(systemName: "arrow.up").font(.copyLargeMedium)
                        .foregroundStyle(canSend ? MP.onBrand : MP.disabledInk)
                        .frame(width: 44, height: 44)
                        .background(Circle().fill(canSend ? MP.brand : MP.disabledFill))
                        .overlay {
                            if !canSend { Circle().strokeBorder(MP.lineStrong, lineWidth: 1) }
                        }
                }
                .disabled(!canSend || sending)
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .background(MP.panel.overlay(Divider().overlay(MP.line), alignment: .top))
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
                    error = "That file can't be sent — photos and PDFs only."
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
                // 16pt / 400: a message is the patient's own copy, and 15
                // is not a rung. Opaque on purpose — a bubble is a repeating
                // list cell, which is barred from glass outright, and it
                // carries the words a post-operative patient is reading.
                Text(message.text)
                    .font(.copyLarge)
                    .foregroundStyle(mine ? MP.onBrand : MP.ink)
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background(MP.surfaceShape
                        .fill(mine ? MP.brand : (message.sender == "care_team" ? MP.brandTint : MP.panel)))
                    // ONE edge, and only where the fill does not separate:
                    // `brand` and `brandTint` are their own boundary, `panel`
                    // is 1.13:1 on canvas light and 1.07:1 dark and needs the
                    // hairline. No shadow — this is not a floating overlay.
                    .overlay(MP.surfaceShape
                        .strokeBorder(mine || message.sender == "care_team" ? .clear : MP.line, lineWidth: 1))
            }
            AttachmentStrip(attachments: message.files, mine: mine)
            if let taskId = message.action?.opensTask, let label = message.action?.label {
                actionButton(label, taskId: taskId)
            }
            HStack(spacing: 4) {
                Text(who)
                if message.fromClinician {
                    // Was 10pt — under the floor — with `brand` as its ink,
                    // which is 3.10:1 on its own tint in dark. 12pt / 500 on
                    // `brandInk`: 4.96:1 light / 5.62:1 dark on `brandTint`.
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
            HStack(spacing: 6) {
                Image(systemName: "arrow.right.circle.fill").font(.copyMedium)
                Text(label).font(.copyMedium)
            }
            .foregroundStyle(MP.onBrand)
            .padding(.horizontal, 16).frame(minHeight: 40)
            // A control, so `controlShape` (10pt) rather than a 12pt literal.
            .background(MP.controlShape.fill(MP.brand))
        }
        .buttonStyle(.plain)
        .padding(.top, 2)
    }
}
