import SwiftUI

/// Every task, open and done: pushed from Today's "All tasks". Today owns
/// the day; this is the record.
struct TaskHistoryView: View {
    @Environment(AppModel.self) private var app
    @State private var openTask: RecoveryTask?
    @State private var quickDone = 0
    @State private var quickError: String?

    private var nothingAtAll: Bool { app.tasks.open.isEmpty && app.tasks.recent.isEmpty }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if let quickError { ErrorBanner(text: quickError) }
                if app.tasks.open.isEmpty {
                    caughtUp
                } else {
                    section("To do", app.tasks.open)
                }
                if !app.tasks.recent.isEmpty {
                    section("Done", app.tasks.recent)
                }
            }
            .padding(.horizontal, 18).padding(.top, 4).padding(.bottom, 24)
        }
        .mpHardScrollEdge()
        .refreshable { await app.refreshTasks() }
        .ambientScreen(height: 300)
        .mpNavigationTitle(app.isPersonal ? "Plan" : "Tasks")
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(item: $openTask) { task in TaskDestination(task: task) }
        .task { await app.refreshTasks() }
        .mpCompletionFeedback(count: quickDone)
        .mpErrorFeedback(quickError)
    }

    private var caughtUp: some View {
        ContentUnavailableView {
            Label {
                Text("You’re all caught up").mpFont(.subheadSemibold).foregroundStyle(MP.ink)
            } icon: {
                Image(systemName: "checkmark.circle")
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(MP.riskLow)
                    .accessibilityHidden(true)
            }
        } description: {
            Text(app.isPersonal ? "Your plan is written each morning from the night’s numbers."
                 : "New tasks from your care team show up here.")
                .mpFont(.copy).foregroundStyle(MP.muted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, nothingAtAll ? 72 : 8)
    }

    private func section(_ title: String, _ tasks: [RecoveryTask]) -> some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardTitleRow(title)
                ForEach(tasks) { t in
                    if t.isOpen {
                        Button { openTask = t } label: { PlanRow(task: t) }
                            .buttonStyle(.mpRow)
                            .contextMenu { rowMenu(t) }
                    } else {
                        PlanRow(task: t)
                    }
                    if t.id != tasks.last?.id { RowDivider() }
                }
            }
            .padding(.bottom, 4)
            .clipShape(MP.surfaceShape)
        }
    }

    @ViewBuilder
    private func rowMenu(_ t: RecoveryTask) -> some View {
        Button { openTask = t } label: { Label("Open", systemImage: "arrow.up.forward.app") }
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
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

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
                            // Sage on its tint: 6.27 light / 7.98 dark.
                            .foregroundStyle(MP.brandInk)
                            .padding(.horizontal, 10).padding(.vertical, 4)
                            .background(MP.capsuleShape.fill(MP.brandTint))
                    }
                    Text(task.title.typeset).title(MPSize.displayS)
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
                                Text(app.isPersonal ? "Logged" : "Sent to your care team")
                                    .mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                                Text(app.isPersonal ? "It feeds tomorrow’s readouts." : "They’ll see it with their next review.")
                                    .mpFont(.copy).mpSecondary()
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
        .ambientScreen()
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
    /// for words). The commit is the prominent glass capsule on iOS 26 — the
    /// site's near-black primary — and the filled capsule before it.
    ///
    /// One row when it fits. At accessibility sizes (and whenever the row
    /// does not fit) it stacks: a full-width commit above a full-width
    /// "Skip this one", and the bar's outline becomes a rounded rectangle
    /// (Glass.swift), so it never balloons into a circle over the questions.
    @ViewBuilder
    private var actionBarContent: some View {
        if dynamicTypeSize.isAccessibilitySize {
            stackedActions
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) {
                    skipButton
                    Spacer(minLength: 8)
                    commitButton(fullWidth: false)
                }
                stackedActions
            }
        }
    }

    private var stackedActions: some View {
        VStack(spacing: 2) {
            commitButton(fullWidth: true)
            skipButton.frame(maxWidth: .infinity)
        }
        .padding(.vertical, 6)
    }

    private var skipButton: some View {
        Button { skip() } label: {
            Text("Skip this one")
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(minHeight: 44)
                .padding(.horizontal, 6)
                .contentShape(Rectangle())
        }
        .mpFont(.copy)
        .foregroundStyle(.primary)
        .buttonStyle(.plain)
        .disabled(sending)
    }

    /// The visible word is short ("Send"), so it never wraps at any size;
    /// VoiceOver and Voice Control still hear the full "Send to my care team".
    private func commitButton(fullWidth: Bool) -> some View {
        let spoken = task.kind == "checkin" ? (app.isPersonal ? "Save my check-in" : "Send to my care team") : "Mark done"
        let shown = task.kind == "checkin" ? (app.isPersonal ? "Save" : "Send") : "Mark done"
        return Button { submit() } label: {
            HStack(spacing: 6) {
                if sending {
                    ProgressView()
                } else {
                    Image(systemName: "checkmark")
                }
                Text(shown)
                    .lineLimit(1)
                    .fixedSize()
            }
            .mpFont(.copyLargeMedium)
            .frame(maxWidth: fullWidth ? .infinity : nil)
        }
        .mpGlassButton(prominent: true)
        .controlSize(.large)
        .disabled(sending || (task.kind == "checkin" && !answered))
        .accessibilityLabel(Text(spoken))
        .accessibilityInputLabels([Text(spoken), Text(shown)])
        .accessibilityValue(sending ? Text("Working") : Text(""))
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
