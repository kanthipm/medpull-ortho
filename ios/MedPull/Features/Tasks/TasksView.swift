import SwiftUI

struct TasksView: View {
    @Environment(AppModel.self) private var app
    @State private var openTask: RecoveryTask?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Tasks").title(MPSize.displayS).padding(.top, 8)
                    section("To do", app.tasks.open, empty: "Nothing waiting. New tasks arrive by text and land here.")
                    if !app.tasks.recent.isEmpty {
                        section("Recently done", app.tasks.recent, empty: "")
                    }
                }
                .padding(.horizontal, 18).padding(.bottom, 24)
            }
            // The one scroll edge effect in this view: hard, so task rows stop
            // at a definite line under the tab bar rather than fading under
            // it. Passthrough below iOS 26.
            .mpHardScrollEdge()
            .refreshable { await app.refreshTasks() }
            .screen()
            .toolbar(.hidden, for: .navigationBar)
            // The check-in gets its own flow; every other kind uses the
            // generic form. Both post the same answers to the same endpoint.
            .navigationDestination(item: $openTask) { task in
                if task.kind == "checkin" {
                    CheckinView(task: task)
                } else {
                    TaskDetailView(task: task)
                }
            }
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
                // This helper draws twice on the screen, so an eyebrow here
                // would spend the one-uppercase budget twice. The screen
                // title carries the orientation instead.
                Text(title).font(.labelMedium).foregroundStyle(MP.muted)
                    .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 6)
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
                                .font(.labelMedium)
                                // brandInk on brandTint is 4.96:1 light /
                                // 5.62:1 dark; `brand` was 3.10:1 on the dark tint.
                                .foregroundStyle(MP.brandInk)
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(MP.pillShape.fill(MP.brandTint))
                        }
                    }
                    Text(task.title).title(MPSize.displayS)
                    if !task.why.isEmpty {
                        Text(task.why).font(.copy).foregroundStyle(MP.muted)
                    }
                    if task.inSmsConversation {
                        ErrorBanner(text: "You started this one by text. Finishing it here is fine — the text thread will close.")
                    }
                }
                if done {
                    Card(tint: true) {
                        HStack(spacing: 10) {
                            Image(systemName: "checkmark.seal.fill").foregroundStyle(MP.riskLow).font(.subhead)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Sent to your care team").font(.copyLargeMedium).foregroundStyle(MP.ink)
                                Text("They'll see it with their next review.").font(.copy).foregroundStyle(MP.muted)
                            }
                        }
                    }
                } else {
                    ForEach(task.questions) { q in
                        QuestionView(question: q, value: binding(for: q.id))
                    }
                    if let error { ErrorBanner(text: error) }
                }
            }
            .padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
        .mpHardScrollEdge()
        // THE ONE CUSTOM GLASS SURFACE IN THE APP, and why it is here: the
        // `number` question opens a number pad, which has no return key, and
        // the submit button used to sit at the end of the scroll — under the
        // keyboard. A bottom bar rides above the keyboard and above the tab
        // bar, so "Mark done" is always reachable. It is a safe-area bar, so
        // the form is inset by its height and nothing is under it at rest.
        // Hidden once the task is sent: the confirmation card is the screen.
        .mpGlassActionBar(isPresented: !done) { actionBarContent }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
    }

    /// Plain buttons, monochrome ink — the bar forbids a token colour, a
    /// filled brand button and a glass button inside it. BOTH LABELS ARE
    /// `.primary`: system secondaryLabel measures 3.44:1 on the light panel
    /// (the reduce-transparency ground), under the 4.5:1 text floor, so it is
    /// not used for words here. Hierarchy is size, weight and the leading
    /// glyph instead: 16/500 with a checkmark for the action, 14/400 for the
    /// way out. 44pt rows for the touch target.
    private var actionBarContent: some View {
        HStack(spacing: 12) {
            Button("Skip this one") { skip() }
                .font(.copy)
                .foregroundStyle(.primary)
                .frame(minHeight: 44)
                .padding(.horizontal, 6)
                .contentShape(Rectangle())
                .disabled(sending)
            Spacer(minLength: 8)
            Button { submit() } label: {
                HStack(spacing: 6) {
                    if sending {
                        ProgressView()
                    } else {
                        Image(systemName: "checkmark")
                    }
                    Text(task.kind == "checkin" ? "Send to my care team" : "Mark done")
                }
                .font(.copyLargeMedium)
                .foregroundStyle(.primary)
                .frame(minHeight: 44)
                .padding(.horizontal, 6)
                .contentShape(Rectangle())
            }
            .disabled(sending || (task.kind == "checkin" && !answered))
        }
        .buttonStyle(.plain)
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
            Text(question.prompt).font(.copyLargeMedium).foregroundStyle(MP.ink)
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
                // `prompt:` rather than the title-as-placeholder form: the
                // default placeholder is the system tertiary label, measured
                // at 1.72:1 on the field, and a placeholder is text under
                // WCAG 1.4.3. `muted` is the placeholder tier (5.39:1 on
                // panel) — never `faint`. The title is kept for VoiceOver.
                let label = question.id == "minutes" ? "Minutes" : "Number"
                TextField(label,
                          text: Binding(get: { value?.intValue.map(String.init) ?? "" },
                                        set: { value = Int($0).map(AnswerValue.int) }),
                          prompt: Text(label).foregroundColor(MP.muted))
                    .textFieldStyle(FieldStyle()).keyboardType(.numberPad)
            default:
                TextField("Optional", text: Binding(get: { value?.stringValue ?? "" },
                                                    set: { value = $0.isEmpty ? nil : .string($0) }),
                          prompt: Text("Optional").foregroundColor(MP.muted),
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
