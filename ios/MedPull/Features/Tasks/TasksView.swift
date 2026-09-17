import SwiftUI

struct TasksView: View {
    @Environment(AppModel.self) private var app
    @State private var openTask: RecoveryTask?
    /// Tasks marked done straight from a row's context menu. Drives the
    /// success haptic and a row error banner; the detail view has its own.
    @State private var quickDone = 0
    @State private var quickError: String?

    private var nothingAtAll: Bool { app.tasks.open.isEmpty && app.tasks.recent.isEmpty }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let quickError { ErrorBanner(text: quickError) }
                    if app.tasks.open.isEmpty {
                        caughtUp
                    } else {
                        section("To do", app.tasks.open)
                    }
                    if !app.tasks.recent.isEmpty {
                        section("Recently done", app.tasks.recent)
                    }
                }
                .padding(.horizontal, 18).padding(.top, 4).padding(.bottom, 24)
            }
            // Hard scroll edge (R13): rows stop at a definite line under the
            // bars rather than fading under them. Passthrough below iOS 26.
            .mpHardScrollEdge()
            .refreshable { await app.refreshTasks() }
            .ambientScreen()
            // A real large title (600, from the UIKit proxy) that collapses
            // to an inline "Tasks" on scroll, and names TaskDetail's back
            // button.
            .mpNavigationTitle("Tasks")
            .navigationBarTitleDisplayMode(.large)
            .navigationDestination(item: $openTask) { task in TaskDestination(task: task) }
            .task { await app.refreshTasks() }
            .onChange(of: app.pendingTaskId, initial: true) { _, id in openPending(id) }
            .onChange(of: app.tasks) { _, _ in openPending(app.pendingTaskId) }
            .mpCompletionFeedback(count: quickDone)
            .mpErrorFeedback(quickError)
        }
    }

    /// The friendly empty state. When nothing has ever arrived it is the
    /// whole screen; otherwise it sits above "Recently done".
    private var caughtUp: some View {
        ContentUnavailableView {
            Label {
                Text("You're all caught up").mpFont(.subheadSemibold).foregroundStyle(MP.ink)
            } icon: {
                // Decorative (the title says the same thing), so riskLow
                // on the canvas is fine at any ratio; it is 5.2:1 anyway.
                Image(systemName: "checkmark.circle")
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(MP.riskLow)
                    .accessibilityHidden(true)
            }
        } description: {
            // Explicit `muted`: the system description colour is secondary
            // label, 3.44:1 on the light canvas.
            Text("New tasks from your care team show up here.")
                .mpFont(.copy).foregroundStyle(MP.muted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, nothingAtAll ? 72 : 8)
    }

    private func openPending(_ id: Int?) {
        guard let id, let task = (app.tasks.open + app.tasks.recent).first(where: { $0.id == id }) else { return }
        app.pendingTaskId = nil
        openTask = task
    }

    private func section(_ title: String, _ tasks: [RecoveryTask]) -> some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardHeader(title)
                ForEach(tasks) { t in
                    if t.isOpen {
                        Button { openTask = t } label: { TaskListRow(task: t) }
                            .buttonStyle(.mpRow)
                            .contextMenu { rowMenu(t) }
                    } else {
                        TaskListRow(task: t)
                    }
                    if t.id != tasks.last?.id { InsetDivider() }
                }
            }
            .padding(.bottom, 4)
        }
    }

    @ViewBuilder
    private func rowMenu(_ t: RecoveryTask) -> some View {
        Button { openTask = t } label: { Label("Open", systemImage: "arrow.up.forward.app") }
        // Only a task with nothing to answer can be finished without
        // opening it; a check-in always goes through its own flow.
        if t.questions.isEmpty && t.kind != "checkin" {
            Button { markDone(t) } label: { Label("Mark done", systemImage: "checkmark.circle") }
        }
    }

    private func markDone(_ t: RecoveryTask) {
        quickError = nil
        Task {
            do {
                try await app.complete(t, answers: [:])
                quickDone += 1
            } catch {
                quickError = AppModel.message(for: error)
            }
        }
    }
}

/// Where a task opens. The daily check-in gets its own one-question-at-a-time
/// flow; every other kind uses the generic form. Both post the same answers
/// to the same endpoint. Home and Tasks both route through this, so a
/// check-in opens the same screen from either tab.
struct TaskDestination: View {
    let task: RecoveryTask

    var body: some View {
        if task.kind == "checkin" {
            CheckinView(task: task)
        } else {
            TaskDetailView(task: task)
        }
    }
}

/// A task row for the Tasks list: category tile, title, one meta line, and a
/// trailing chevron (open) or state glyph (done / skipped).
struct TaskListRow: View {
    let task: RecoveryTask

    private var isDone: Bool { task.status == "done" }

    private var icon: String {
        switch task.kind {
        case "checkin": return "text.bubble.fill"
        case "exercise": return "figure.strengthtraining.functional"
        case "walk": return "figure.walk"
        case "medication": return "pills.fill"
        case "wound_check": return "bandage.fill"
        case "sleep": return "bed.double.fill"
        default: return "checklist"
        }
    }

    private var family: MP.Category {
        switch task.kind {
        case "exercise", "walk": return .teal
        case "medication", "wound_check": return .violet
        case "sleep": return .indigo
        default: return .blue
        }
    }

    var body: some View {
        HStack(spacing: 14) {
            IconTile(icon, family: family)
            VStack(alignment: .leading, spacing: 2) {
                Text(task.title)
                    .mpFont(.copyLargeMedium)
                    .foregroundStyle(MP.ink)
                    .strikethrough(isDone, color: MP.muted)
                    .multilineTextAlignment(.leading)
                meta
            }
            Spacer(minLength: 8)
            trailing
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityValue(Text(isDone ? "Done" : task.isOpen ? "" : "Skipped"))
    }

    private var meta: some View {
        HStack(spacing: 0) {
            Text(task.kindLabel).foregroundStyle(MP.muted)
            if isDone, let via = task.completedVia {
                Text("\(MP.dot)done by \(via)").foregroundStyle(MP.muted)
            } else if task.inSmsConversation {
                // riskMed as text: the words carry the state, not the hue.
                Text("\(MP.dot)in progress by text").foregroundStyle(MP.riskMed)
            } else if let due = task.dueAt {
                Text("\(MP.dot)due \(Dates.relative(due))").foregroundStyle(MP.muted)
            } else if let schedule = task.scheduleLabel {
                Text("\(MP.dot)\(schedule)").foregroundStyle(MP.muted)
            }
        }
        .mpFont(.label)
        .lineLimit(1)
    }

    @ViewBuilder
    private var trailing: some View {
        if task.isOpen {
            Image(systemName: "chevron.right")
                .font(.copyMedium)
                .foregroundStyle(MP.muted)
                .accessibilityHidden(true)
        } else {
            Image(systemName: isDone ? "checkmark.circle.fill" : "minus.circle")
                .symbolRenderingMode(.hierarchical)
                .contentTransition(.symbolEffect(.replace))
                .font(.copyLarge)
                .foregroundStyle(isDone ? MP.riskLow : MP.muted)
                .accessibilityHidden(true)
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
    /// The seal starts drawn off and draws on once the done card is up
    /// (iOS 26); older systems bounce it instead.
    @State private var sealHidden = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var answered: Bool { !answers.isEmpty }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 8) {
                    // The kind now lives in the inline navigation title, so
                    // the eyebrow that restated it is gone; only the
                    // schedule, which nothing else says, keeps a pill.
                    if let schedule = task.scheduleLabel {
                        Text(schedule)
                            .mpFont(.labelMedium)
                            // brandInk on brandTint is 4.96:1 light /
                            // 5.62:1 dark; `brand` was 3.10:1 on the dark tint.
                            .foregroundStyle(MP.brandInk)
                            .padding(.horizontal, 10).padding(.vertical, 4)
                            .background(MP.capsuleShape.fill(MP.brandTint))
                    }
                    Text(task.title).title(MPSize.displayS)
                    if !task.why.isEmpty {
                        Text(task.why).mpFont(.copy).foregroundStyle(MP.muted)
                    }
                    if task.inSmsConversation {
                        ErrorBanner(text: "You started this one by text. Finishing it here is fine — the text thread will close.")
                    }
                }
                if done {
                    Card(tint: true) {
                        HStack(spacing: 12) {
                            seal
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Sent to your care team").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                Text("They'll see it with their next review.").mpFont(.copy).mpSecondary()
                            }
                        }
                    }
                    .transition(.opacity)
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
        .navigationTitle(task.kindLabel)
        .navigationBarTitleDisplayMode(.inline)
        .animation(MPMotion.gated(MPMotion.settle, reduceMotion: reduceMotion), value: done)
        .mpCompletionFeedback(done)
        .mpErrorFeedback(error)
    }

    /// The done seal. riskLow on brandTint is decorative here (the words
    /// beside it say "sent"), and measures above 3:1 in both modes anyway.
    @ViewBuilder
    private var seal: some View {
        let base = Image(systemName: "checkmark.seal.fill")
            .symbolRenderingMode(.hierarchical)
            .font(.subheadSemibold)
            .foregroundStyle(MP.riskLow)
            .accessibilityHidden(true)
        if #available(iOS 26, *) {
            // Indefinite draw-on: active = drawn off. Flipping it after the
            // card appears draws the seal in. Reduce Motion removes it.
            base
                .symbolEffect(.drawOn, isActive: sealHidden && !reduceMotion)
                .symbolEffectsRemoved(reduceMotion)
                .task {
                    // A beat after the card lands, so the draw is seen.
                    try? await Task.sleep(for: .milliseconds(150))
                    sealHidden = false
                }
        } else {
            base
                .symbolEffect(.bounce, value: done)
                .symbolEffectsRemoved(reduceMotion)
        }
    }

    /// "Skip this one" stays a plain `.primary` label (system secondaryLabel
    /// is 3.44:1 on the light reduce-transparency ground, so it is never used
    /// for words). The commit is the prominent glass capsule on iOS 26 — tinted
    /// Medical Blue with a white label — and the filled capsule before it.
    private var actionBarContent: some View {
        HStack(spacing: 12) {
            Button("Skip this one") { skip() }
                .mpFont(.copy)
                .foregroundStyle(.primary)
                .frame(minHeight: 44)
                .padding(.horizontal, 6)
                .contentShape(Rectangle())
                .buttonStyle(.plain)
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
                .mpFont(.copyLargeMedium)
            }
            .mpGlassButton(prominent: true)
            .controlSize(.large)
            .disabled(sending || (task.kind == "checkin" && !answered))
            .accessibilityValue(sending ? Text("Working") : Text(""))
        }
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
            Text(question.prompt).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
            switch question.kind {
            case "scale":
                // The same slider as the check-in flow, so a 0-10 answer
                // looks and feels the same wherever it is asked.
                ScaleAnswer(value: $value, painting: question.id == "pain")
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
}

struct FlowChips: View {
    let options: [String]
    let labels: [String: String]
    @Binding var value: AnswerValue?

    var body: some View {
        // One row when it fits; a column at large text sizes, so no chip
        // is ever pushed off the edge.
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) { chips }
            VStack(alignment: .leading, spacing: 8) { chips }
        }
    }

    @ViewBuilder
    private var chips: some View {
        ForEach(options, id: \.self) { opt in
            Chip(label: labels[opt] ?? opt.capitalized, selected: value == .string(opt)) {
                value = (value == .string(opt)) ? nil : .string(opt)
            }
        }
    }
}
