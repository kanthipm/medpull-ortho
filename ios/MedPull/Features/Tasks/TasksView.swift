import SwiftUI

struct TasksView: View {
    @Environment(AppModel.self) private var app
    @State private var openTask: RecoveryTask?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Tasks").title(28).padding(.top, 8)
                    section("To do", app.tasks.open, empty: "Nothing waiting. New tasks arrive by text and land here.")
                    if !app.tasks.recent.isEmpty {
                        section("Recently done", app.tasks.recent, empty: "")
                    }
                }
                .padding(.horizontal, 18).padding(.bottom, 24)
            }
            .refreshable { await app.refreshTasks() }
            .screen()
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(item: $openTask) { task in TaskDetailView(task: task) }
            .task { await app.refreshTasks() }
            .onChange(of: app.pendingTaskId, initial: true) { _, id in openPending(id) }
            .onChange(of: app.tasks) { _, _ in openPending(app.pendingTaskId) }
        }
    }

    private func openPending(_ id: Int?) {
        guard let id, let task = (app.tasks.open + app.tasks.recent).first(where: { $0.id == id }) else { return }
        app.pendingTaskId = nil
        openTask = task
    }

    private func section(_ title: String, _ tasks: [RecoveryTask], empty: String) -> some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                Text(title).eyebrow().padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 6)
                if tasks.isEmpty {
                    EmptyRow(icon: "checkmark.circle", title: "All caught up", detail: empty)
                } else {
                    ForEach(tasks) { t in
                        if t.isOpen {
                            Button { openTask = t } label: { TaskRow(task: t) }.buttonStyle(.plain)
                        } else {
                            TaskRow(task: t)
                        }
                        if t.id != tasks.last?.id { Divider().overlay(MP.line).padding(.leading, 56) }
                    }
                }
            }
        }
    }
}

struct TaskDetailView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let task: RecoveryTask

    @State private var answers: [String: AnswerValue] = [:]
    @State private var sending = false
    @State private var error: String?
    @State private var done = false

    private var answered: Bool { !answers.isEmpty }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 6) {
                        Text(task.kindLabel).eyebrow()
                        if let schedule = task.scheduleLabel {
                            Text(schedule)
                                .font(.system(size: 10.5, weight: .semibold))
                                .foregroundStyle(MP.brand)
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(Capsule().fill(MP.brandTint))
                        }
                    }
                    Text(task.title).title(26)
                    if !task.why.isEmpty {
                        Text(task.why).font(.system(size: 14.5)).foregroundStyle(MP.muted)
                    }
                    if task.inSmsConversation {
                        ErrorBanner(text: "You started this one by text. Finishing it here is fine — the text thread will close.")
                    }
                }
                if done {
                    Card(tint: true) {
                        HStack(spacing: 10) {
                            Image(systemName: "checkmark.seal.fill").foregroundStyle(MP.riskLow).font(.system(size: 22))
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Sent to your care team").font(.system(size: 15, weight: .semibold)).foregroundStyle(MP.ink)
                                Text("They'll see it with their next review.").font(.system(size: 13)).foregroundStyle(MP.muted)
                            }
                        }
                    }
                } else {
                    ForEach(task.questions) { q in
                        QuestionView(question: q, value: binding(for: q.id))
                    }
                    if let error { ErrorBanner(text: error) }
                    PrimaryButton(title: task.kind == "checkin" ? "Send to my care team" : "Mark done",
                                  loading: sending, disabled: task.kind == "checkin" && !answered) {
                        submit()
                    }
                    Button("Skip this one") { skip() }
                        .font(.system(size: 14, weight: .medium)).foregroundStyle(MP.muted)
                        .frame(maxWidth: .infinity)
                }
            }
            .padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
        .screen()
        .navigationBarTitleDisplayMode(.inline)
    }

    private func binding(for id: String) -> Binding<AnswerValue?> {
        Binding(get: { answers[id] }, set: { new in
            if let new { answers[id] = new } else { answers.removeValue(forKey: id) }
        })
    }

    private func submit() {
        sending = true
        error = nil
        Task {
            defer { sending = false }
            do {
                try await app.complete(task, answers: answers)
                done = true
                try? await Task.sleep(for: .seconds(1.2))
                dismiss()
            } catch {
                self.error = AppModel.message(for: error)
            }
        }
    }

    private func skip() {
        Task {
            do { try await app.skip(task); dismiss() } catch { self.error = AppModel.message(for: error) }
        }
    }
}

/// One question, rendered by kind — the same chips as the web check-in.
struct QuestionView: View {
    let question: Question
    @Binding var value: AnswerValue?

    private static let labels: [String: String] = [
        "yes": "Yes", "no": "No", "well": "Well", "rough": "Rough night",
        "all": "All of them", "some": "Some", "none": "Not today",
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(question.prompt).font(.system(size: 15.5, weight: .semibold)).foregroundStyle(MP.ink)
            switch question.kind {
            case "scale":
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 6), spacing: 8) {
                    ForEach(0...10, id: \.self) { n in
                        Chip(label: "\(n)", selected: value == .int(n)) { toggle(.int(n)) }
                    }
                }
            case "yes_no", "choice":
                FlowChips(options: question.options ?? ["yes", "no"], labels: Self.labels, value: $value)
            case "number":
                TextField(question.id == "minutes" ? "Minutes" : "Number",
                          text: Binding(get: { value?.intValue.map(String.init) ?? "" },
                                        set: { value = Int($0).map(AnswerValue.int) }))
                    .textFieldStyle(FieldStyle()).keyboardType(.numberPad)
            default:
                TextField("Optional", text: Binding(get: { value?.stringValue ?? "" },
                                                    set: { value = $0.isEmpty ? nil : .string($0) }),
                          axis: .vertical)
                    .lineLimit(3...6)
                    .textFieldStyle(FieldStyle())
            }
        }
    }

    private func toggle(_ new: AnswerValue) {
        value = (value == new) ? nil : new
    }
}

struct FlowChips: View {
    let options: [String]
    let labels: [String: String]
    @Binding var value: AnswerValue?

    var body: some View {
        HStack(spacing: 8) {
            ForEach(options, id: \.self) { opt in
                Chip(label: labels[opt] ?? opt.capitalized, selected: value == .string(opt)) {
                    value = (value == .string(opt)) ? nil : .string(opt)
                }
            }
        }
    }
}
