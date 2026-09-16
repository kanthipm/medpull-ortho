import PhotosUI
import SwiftUI

struct MessagesView: View {
    @Environment(AppModel.self) private var app
    @State private var draft = ""
    @State private var sending = false
    @State private var error: String?
    @FocusState private var focused: Bool

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
                        if let last = app.messages.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
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
            Text("Messages").title(28)
            if let team = app.me?.patient.careTeam, !team.isEmpty {
                Text("Your care team: " + team.map(\.name).joined(separator: ", "))
                    .font(.mp(13)).foregroundStyle(MP.muted)
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
                    Image(systemName: "paperclip").font(.mp(17, weight: .medium))
                        .foregroundStyle(MP.brand)
                        .frame(width: 40, height: 44)
                }
                .disabled(uploading || pending.count >= 4)
                .accessibilityLabel("Attach a photo or file")
                TextField("Message your care team", text: $draft, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(FieldStyle())
                    .focused($focused)
                Button {
                    send()
                } label: {
                    Image(systemName: "arrow.up").font(.mp(16, weight: .bold)).foregroundStyle(.white)
                        .frame(width: 44, height: 44)
                        .background(Circle().fill(canSend ? MP.brand : MP.faint))
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
                            .font(.mp(11, weight: .semibold)).foregroundStyle(MP.brand)
                        Text(a.displayName).font(.mp(12, weight: .medium))
                            .foregroundStyle(MP.ink).lineLimit(1)
                        Text(a.sizeLabel).font(.mp(11)).foregroundStyle(MP.faint)
                        Button {
                            remove(a)
                        } label: {
                            Image(systemName: "xmark").font(.mp(9, weight: .bold))
                                .foregroundStyle(MP.faint)
                        }
                        .accessibilityLabel("Remove \(a.displayName)")
                    }
                    .padding(.horizontal, 9).padding(.vertical, 6)
                    .background(Capsule().fill(MP.soft))
                    .overlay(Capsule().strokeBorder(MP.line))
                }
                if uploading {
                    HStack(spacing: 5) {
                        ProgressView().controlSize(.mini)
                        Text("Adding…").font(.mp(12, weight: .medium))
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
        case "copilot": return message.channel == "sms" ? "MedPull · text" : "MedPull"
        default: return message.channel == "sms" ? "You · by text" : message.channel == "voice" ? "You · by voice" : "You"
        }
    }

    var body: some View {
        VStack(alignment: mine ? .trailing : .leading, spacing: 3) {
            if !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Text(message.text)
                    .font(.mp(15))
                    .foregroundStyle(mine ? .white : MP.ink)
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background(RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(mine ? MP.brand : (message.sender == "care_team" ? MP.brandTint : MP.panel)))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .strokeBorder(mine ? .clear : MP.line))
            }
            AttachmentStrip(attachments: message.files, mine: mine)
            if let taskId = message.action?.opensTask, let label = message.action?.label {
                actionButton(label, taskId: taskId)
            }
            HStack(spacing: 4) {
                Text(who)
                if message.fromClinician {
                    Text("Care team approved")
                        .font(.mp(10, weight: .semibold))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Capsule().fill(MP.brandTint))
                        .foregroundStyle(MP.brand)
                }
                Text("·")
                Text(Dates.relative(message.createdAt))
                if message.deliveryStatus == "failed" {
                    Text("· not delivered by text").foregroundStyle(MP.riskMed)
                }
            }
            .font(.mp(11.5)).foregroundStyle(MP.faint)
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
                Image(systemName: "arrow.right.circle.fill").font(.mp(14, weight: .semibold))
                Text(label).font(.mp(14.5, weight: .semibold))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 16).frame(minHeight: 40)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(MP.brand))
        }
        .buttonStyle(.plain)
        .padding(.top, 2)
    }
}
