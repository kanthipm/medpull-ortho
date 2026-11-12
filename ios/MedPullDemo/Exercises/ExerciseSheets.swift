import SwiftUI

// The two sheets on the exercise screen: "Just mark it done", for an
// exercise done away from the phone, and "Can't do it today".

/// A sheet's close button: the system's on iOS 26, a word before.
struct SheetClose: ToolbarContent {
    let title: String
    let action: () -> Void

    var body: some ToolbarContent {
        ToolbarItem(placement: .cancellationAction) {
            if #available(iOS 26, *) {
                Button(role: .close, action: action)
            } else {
                Button(title, action: action).mpFont(.copyLargeMedium)
            }
        }
    }
}

/// The bar a sheet's one commit button sits on, pinned under the form. The
/// check-in's bar, on an opaque ground: here the form scrolls underneath it,
/// and half-seen rows behind a button read as clutter.
struct SheetControls<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(spacing: 8) { content() }
            .padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 8)
            .frame(maxWidth: .infinity)
            .background(
                MP.canvas
                    .overlay(LinearGradient(colors: [MP.glassSolidTop, MP.glassSolidBottom],
                                            startPoint: .top, endPoint: .bottom))
                    .overlay(alignment: .top) { InsetDivider(leading: 0) }
                    .ignoresSafeArea(edges: .bottom)
            )
    }
}

// MARK: - Just mark it done

/// How much it hurts now, how hard it was, what was actually done (filled
/// in from the dose), a note, the clip of the attempt the way the therapist
/// asked for it, and whether the watch was on. Send stays off, and says why,
/// while something she required is missing.
struct CompletionSheet: View {
    let a: ExerciseAssignment
    let unit: LoadUnit

    @Environment(AppModel.self) private var app
    @Environment(DemoShell.self) private var shell
    @Environment(ExerciseStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var pain: Int?
    @State private var effort: Int?
    @State private var counts: DoneCounts
    @State private var note = ""
    @State private var worn = false
    @State private var clip = AttemptClip()
    @State private var sending = false
    @State private var error: String?
    @FocusState private var typing: Bool

    init(a: ExerciseAssignment, unit: LoadUnit) {
        self.a = a
        self.unit = unit
        _counts = State(initialValue: DoneCounts(a, unit: unit))
    }

    private var therapist: String { ExerciseWords.therapist(a.assignedByName) }
    private var clipMissing: Bool { a.videoRequirement == .required && clip.staged == nil }
    private var watchMissing: Bool { a.wearableRequirement == .required && !worn }
    private var blocked: Bool { clip.isWorking || clipMissing || watchMissing }

    /// Why Send is off, in a sentence, or nil when nothing is missing.
    private var why: String? {
        if clip.isWorking { return nil }
        if clipMissing { return "\(therapist) asked for a clip of this one. Send is ready once it’s attached." }
        if watchMissing { return "\(therapist) asked for this one with your watch on." }
        return nil
    }

    var body: some View {
        NavigationStack {
            ExerciseScroll {
                VStack(alignment: .leading, spacing: 26) {
                    VStack(alignment: .leading, spacing: 8) {
                        ExercisePill(text: a.title)
                        Text("Nice work. How did it go?").title(MPSize.displayS)
                            .accessibilityAddTraits(.isHeader)
                        Text("\(therapist) sees your answers with the rest of your week.")
                            .mpFont(.copy).foregroundStyle(MP.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    section("How’s the pain, now that you’ve done it?") { PainAnswer(value: $pain) }
                    section("How hard was it?", note: a.rpeTarget.map {
                        "\(therapist) suggested around \($0)\(MP.dot)\(ExerciseWords.effort($0).lowercased())."
                    }) { EffortAnswer(value: $effort) }
                    section("What you did",
                            note: "Filled in from \(therapist)’s dose. Change it to what you really did.") {
                        DoneCountsCard(counts: $counts, a: a, unit: unit)
                    }
                    section("Anything to add?") {
                        TextField("A note for your therapist", text: $note,
                                  prompt: Text("Optional: how it felt, what was hard").foregroundColor(MP.muted),
                                  axis: .vertical)
                            .lineLimit(3...6).textFieldStyle(FieldStyle()).focused($typing)
                    }
                    if a.videoRequirement != .off { clipSection }
                    if a.wearableRequirement != .off { watchSection }
                }
                .padding(.horizontal, 20).padding(.top, 8).padding(.bottom, 28)
            }
            .scrollDismissesKeyboard(.interactively)
            .safeAreaInset(edge: .bottom, spacing: 0) {
                SheetControls {
                    if let error { ErrorBanner(text: error) }
                    if let why {
                        Text(why).mpFont(.label).foregroundStyle(MP.muted)
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    PrimaryButton(title: sendTitle, loading: sending, disabled: blocked) { send() }
                }
            }
            .ambientScreen(height: 260)
            .navigationTitle("Mark done")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                SheetClose(title: "Cancel") { dismiss() }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") { hideKeyboard() }
                }
            }
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
        .interactiveDismissDisabled(sending || clip.isWorking)
        #if DEBUG
        .task {
            // Simulator verification: `-MP_EX_FILL 1` answers the sheet the
            // way a tap-through would, so its filled state can be looked at.
            guard AppConfig.debugFlag("MP_EX_FILL") != nil else { return }
            pain = 3
            effort = 6
            note = "Felt strong today."
            if a.wearableRequirement != .off { worn = true }
            if a.videoRequirement != .off, shell.isDemoServer {
                await clip.useSample(for: a, store: store, api: app.api)
                await clip.upload(api: app.api)
            }
            // `-MP_EX_SEND 1` then presses Send.
            if AppConfig.debugFlag("MP_EX_SEND") != nil {
                try? await Task.sleep(for: .seconds(2))
                send()
            }
        }
        #endif
    }

    private var sendTitle: String {
        if case .uploading(_, let fraction) = clip.phase {
            return "Uploading your clip\(MP.dot)\(Int((fraction * 100).rounded()))%"
        }
        return "Send to \(therapist)"
    }

    private func section<Content: View>(_ title: String, note: String? = nil,
                                        @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                .accessibilityAddTraits(.isHeader)
            content()
            if let note {
                Text(note).mpFont(.label).foregroundStyle(MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: The clip

    private var clipSection: some View {
        section(a.videoRequirement == .required ? "\(therapist) asked for a clip of this one"
                : "Show \(therapist) your form",
                note: "A few seconds of you doing it is plenty. It goes to your care team only.") {
            if clip.phase == .none {
                AttemptSources(a: a, clip: clip, prominent: false) {
                    Task { await clip.upload(api: app.api) }
                }
            } else {
                AttemptChip(clip: clip)
                if case .failed(_, let take) = clip.phase {
                    if take != nil {
                        SecondaryButton(title: "Try the upload again", icon: "arrow.clockwise") {
                            Task { await clip.upload(api: app.api) }
                        }
                    } else {
                        AttemptSources(a: a, clip: clip, prominent: false) {
                            Task { await clip.upload(api: app.api) }
                        }
                    }
                }
            }
        }
    }

    // MARK: The watch

    private var watchSection: some View {
        section("Your watch") {
            Card(padding: 0) {
                Toggle(isOn: $worn) {
                    HStack(spacing: 12) {
                        Glyph(systemName: "applewatch", family: .indigo)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("I wore my watch").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            Text(a.wearableRequirement == .required
                                 ? "\(therapist) asked for your heart rate with this one."
                                 : "Your heart rate comes along with it.")
                                .mpFont(.label).foregroundStyle(MP.muted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                .tint(MP.brand)
                .padding(.horizontal, 16).padding(.vertical, 10)
            }
            .mpSelectionFeedback(worn)
        }
    }

    // MARK: Send

    private func send() {
        typing = false
        sending = true
        error = nil
        var body = ExerciseCompletionBody()
        body.painAfter = pain
        body.note = note.trimmingCharacters(in: .whitespacesAndNewlines)
        body.video = clip.staged
        body.effort = effort
        body.setsDone = counts.setsDone
        body.repsDone = a.holdIsUnit ? nil : counts.repsDone
        body.loadDoneKg = counts.loadDoneKg(unit: unit)
        body.wearableWorn = a.wearableRequirement == .off ? nil : worn
        Task {
            defer { sending = false }
            do {
                try await store.complete(a, body: body)
                dismiss()
            } catch {
                // A refusal (a clip she required, the watch, a day already
                // done) is the server's own sentence, here where it applies.
                self.error = ExerciseStore.sentence(for: error)
            }
        }
    }

    private func hideKeyboard() {
        typing = false
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
    }
}

// MARK: - Can't do it today

/// A reason, in a tap or in words, then the day is skipped.
struct SkipSheet: View {
    let a: ExerciseAssignment

    @Environment(ExerciseStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var reason = ""
    @State private var sending = false
    @State private var error: String?

    private static let reasons = ["Too sore", "No time today", "Not sure how", "No equipment"]
    private var therapist: String { ExerciseWords.therapist(a.assignedByName) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    VStack(alignment: .leading, spacing: 8) {
                        ExercisePill(text: a.title)
                        Text("That’s okay. What’s in the way?").title(MPSize.displayS)
                            .accessibilityAddTraits(.isHeader)
                        Text("\(therapist) will see this and can change the plan.")
                            .mpFont(.copy).foregroundStyle(MP.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    BrandFlow(spacing: 8) {
                        ForEach(Self.reasons, id: \.self) { r in
                            Chip(label: r, selected: reason == r) { reason = reason == r ? "" : r }
                        }
                    }
                    TextField("Why not today", text: $reason,
                              prompt: Text("Or say it in your own words (optional)").foregroundColor(MP.muted),
                              axis: .vertical)
                        .lineLimit(2...5).textFieldStyle(FieldStyle())
                }
                .padding(.horizontal, 20).padding(.top, 8).padding(.bottom, 28)
            }
            .scrollDismissesKeyboard(.interactively)
            .safeAreaInset(edge: .bottom, spacing: 0) {
                SheetControls {
                    if let error { ErrorBanner(text: error) }
                    PrimaryButton(title: "Skip today", loading: sending) { skip() }
                }
            }
            .ambientScreen(height: 260)
            .navigationTitle("Can’t do it today")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { SheetClose(title: "Cancel") { dismiss() } }
            .mpErrorFeedback(error)
        }
        .presentationDetents([.large])
        #if DEBUG
        .task {
            // Simulator verification: `-MP_EX_SKIP "Too sore"` picks that
            // reason; with `-MP_EX_SEND 1` it then presses "Skip today".
            guard let chosen = AppConfig.debugFlag("MP_EX_SKIP") else { return }
            try? await Task.sleep(for: .seconds(1))
            reason = chosen
            if AppConfig.debugFlag("MP_EX_SEND") != nil {
                try? await Task.sleep(for: .seconds(2))
                skip()
            }
        }
        #endif
    }

    private func skip() {
        sending = true
        error = nil
        Task {
            defer { sending = false }
            do {
                try await store.skip(a, reason: reason.trimmingCharacters(in: .whitespacesAndNewlines))
                dismiss()
            } catch {
                self.error = ExerciseStore.sentence(for: error)
            }
        }
    }
}
