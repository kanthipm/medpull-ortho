import SwiftUI

struct MessagesView: View {
    @Environment(AppModel.self) private var app
    @State private var draft = ""
    @State private var sending = false
    @State private var error: String?
    @FocusState private var focused: Bool

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
            .toolbar(.hidden, for: .navigationBar)
            .task {
                await app.refreshMessages()
                await app.markMessagesRead()
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(20))
                    await app.refreshMessages()
                }
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Messages").title(28)
            if let team = app.me?.patient.careTeam, !team.isEmpty {
                Text("Your care team: " + team.map(\.name).joined(separator: ", "))
                    .font(.system(size: 13)).foregroundStyle(MP.muted)
            }
        }
        .padding(.top, 8).padding(.bottom, 6)
    }

    private var composer: some View {
        VStack(spacing: 6) {
            if let error { ErrorBanner(text: error) }
            HStack(alignment: .bottom, spacing: 8) {
                TextField("Message your care team", text: $draft, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(FieldStyle())
                    .focused($focused)
                Button {
                    send()
                } label: {
                    Image(systemName: "arrow.up").font(.system(size: 16, weight: .bold)).foregroundStyle(.white)
                        .frame(width: 44, height: 44)
                        .background(Circle().fill(draft.trimmingCharacters(in: .whitespaces).isEmpty ? MP.faint : MP.brand))
                }
                .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty || sending)
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .background(MP.panel.overlay(Divider().overlay(MP.line), alignment: .top))
    }

    private func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        sending = true
        error = nil
        Task {
            defer { sending = false }
            do {
                try await app.send(message: text)
                draft = ""
            } catch { self.error = error.localizedDescription }
        }
    }
}

struct Bubble: View {
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
            Text(message.text)
                .font(.system(size: 15))
                .foregroundStyle(mine ? .white : MP.ink)
                .padding(.horizontal, 14).padding(.vertical, 10)
                .background(RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(mine ? MP.brand : (message.sender == "care_team" ? MP.brandTint : MP.panel)))
                .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(mine ? .clear : MP.line))
            HStack(spacing: 4) {
                Text(who)
                if message.fromClinician {
                    Text("Care team approved")
                        .font(.system(size: 10, weight: .semibold))
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
            .font(.system(size: 11.5)).foregroundStyle(MP.faint)
        }
        .frame(maxWidth: .infinity, alignment: mine ? .trailing : .leading)
        .padding(mine ? .leading : .trailing, 48)
    }
}
