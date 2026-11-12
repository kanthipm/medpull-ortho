import SwiftUI

/// One exercise on the calendar: what it is and the dose, the therapist's
/// clip to follow (looping, muted), her note, the steps, what to take care
/// of, then Start (the guided session), with "Just mark it done" for an
/// exercise done away from the phone and "Can't do it today" with a reason.
/// Done, it shows what went back and what the therapist said about it.
///
/// The row is read from the store every time this draws, and the calendar
/// keeps polling while the screen is up: the therapist may log it done from
/// the room while the person is reading it.
struct ExerciseScreen: View {
    let id: Int
    @Environment(AppModel.self) private var app
    @Environment(ExerciseStore.self) private var store
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    /// True once a row that was not held has been asked for.
    @State private var asked = false
    @State private var marking = false
    @State private var skipping = false
    @State private var inSession = false

    var body: some View {
        Group {
            if let a = store.assignment(id) {
                detail(a)
            } else {
                missing
            }
        }
        .ambientScreen(height: 300)
        .navigationTitle("Exercise")
        .navigationBarTitleDisplayMode(.inline)
        .exerciseWatch(program: true)
        .task(id: id) {
            if store.assignment(id) == nil { await store.refreshAll() }
            asked = true
            #if DEBUG
            // Simulator verification: `-MP_EX_SHOW session|mark|skip` opens
            // what the three actions open.
            switch AppConfig.debugFlag("MP_EX_SHOW") {
            case "session": inSession = true
            case "mark": marking = true
            case "skip": skipping = true
            default: break
            }
            #endif
        }
    }

    /// The screen while a row is looked for, and once it was not found: a
    /// link to an exercise that has since been moved or taken off.
    private var missing: some View {
        ScrollView {
            VStack(spacing: 18) {
                if asked {
                    Card(padding: 0) {
                        EmptyRow(icon: "figure.strengthtraining.functional", title: "That exercise isn’t on your list",
                                 detail: "It may have been moved to another day or taken off by your therapist.")
                    }
                } else {
                    LoadingCard(text: "Finding the exercise…")
                }
            }
            .padding(.horizontal, 18).padding(.top, 12)
        }
    }

    private func detail(_ a: ExerciseAssignment) -> some View {
        let today = store.today
        let state = a.state(on: today)
        let actionable = a.isOpen && state != .upcoming
        return ExerciseScroll {
            VStack(alignment: .leading, spacing: 18) {
                header(a, today: today)
                if !a.isOpen { OutcomeCard(a: a, unit: store.unit) }
                VStack(alignment: .leading, spacing: 8) {
                    ClipTile(source: a.demonstration, label: "\(a.title), demonstration")
                    if let video = a.video, a.demonstration != nil {
                        Text(video.source == "clinic" && video.uploadedByName != nil
                             ? "\(video.uploadedByName ?? "")’s demonstration"
                             : "From the exercise library\(MP.dot)follow the steps below")
                            .mpFont(.label).foregroundStyle(MP.muted)
                            .padding(.horizontal, 4)
                    }
                }
                if state == .inProgress, let started = a.session?.startedAt {
                    Text("You started this \(ExerciseWords.ago(started)). Start again and the clock begins afresh.")
                        .mpFont(.label).foregroundStyle(MP.muted)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 4)
                }
                if state == .upcoming {
                    Text("Planned for \(ExerciseWords.dayInSentence(a.scheduledFor, today: today)). You can start it on the day.")
                        .mpFont(.copy).foregroundStyle(MP.body)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 4)
                }
                if !a.clinicianInstructions.isEmpty { TherapistNote(a: a) }
                if !a.steps.isEmpty { StepsCard(a: a) }
                if !a.precautions.isEmpty { precautions(a) }
                facts(a)
            }
            .padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 28)
        }
        .mpHardScrollEdge()
        .mpGlassActionBar(isPresented: actionable) { actions }
        .sheet(isPresented: $marking) { CompletionSheet(a: a, unit: store.unit) }
        .sheet(isPresented: $skipping) { SkipSheet(a: a) }
        .fullScreenCover(isPresented: $inSession) { GuidedSession(id: a.id) }
        .mpCompletionFeedback(a.isDone)
    }

    // MARK: Header

    private func header(_ a: ExerciseAssignment, today: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            BrandFlow(spacing: 6) {
                ExercisePill(text: a.scheduledFor == today ? "Today" : Dates.monthDay(a.scheduledFor))
                if a.videoRequirement == .required { ExercisePill(text: "Clip asked for", symbol: "video.fill") }
                if a.wearableRequirement == .required { ExercisePill(text: "Watch on", symbol: "applewatch") }
            }
            Text(a.title.typeset).title(MPSize.displayS)
                .accessibilityAddTraits(.isHeader)
            Text(ExerciseWords.typeset(a.dose)).mpFont(.copyLarge).foregroundStyle(MP.body)
                .fixedSize(horizontal: false, vertical: true)
            if let target = a.rpeTarget {
                Text("Aim for effort \(target)/10\(MP.dot)\(ExerciseWords.effort(target).lowercased())")
                    .mpFont(.copy).foregroundStyle(MP.muted)
            }
            // Her ceiling on the dose, right under it.
            if a.hasCeiling { DoseCeiling(a: a).padding(.vertical, 2) }
            if let name = a.assignedByName, !name.isEmpty {
                Text("From \(name)").mpFont(.copy).foregroundStyle(MP.muted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 2)
    }

    // MARK: Cards

    private func precautions(_ a: ExerciseAssignment) -> some View {
        Card {
            HStack(alignment: .top, spacing: 12) {
                Glyph(systemName: "exclamationmark.triangle.fill", family: .blue)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Take care").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                    Text(a.precautions.typeset).mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
        }
        .accessibilityElement(children: .combine)
    }

    /// The dose, a line at a time, and what the therapist asked for with it.
    private func facts(_ a: ExerciseAssignment) -> some View {
        var rows: [(String, String)] = [("Dose", ExerciseWords.typeset(a.dose))]
        if a.hasSide { rows.append(("Side", a.sideLabel)) }
        if let hold = a.holdSeconds, hold > 0 { rows.append(("Hold", "\(hold) s")) }
        if let load = a.loadKg { rows.append(("Load", store.unit.text(kg: load))) }
        if let target = a.rpeTarget {
            rows.append(("Effort to aim for", "\(target)/10\(MP.dot)\(ExerciseWords.effort(target).lowercased())"))
        }
        if a.hasCeiling { rows.append(("Limit", ExerciseWords.typeset(a.ceiling))) }
        rows.append(("Equipment", a.equipment.isEmpty ? "None needed" : a.equipment))
        if a.videoRequirement != .off {
            rows.append(("A clip of you doing it", a.videoRequirement == .required ? "Asked for" : "If you like"))
        }
        if a.wearableRequirement != .off {
            rows.append(("Your watch on", a.wearableRequirement == .required ? "Asked for" : "If you like"))
        }
        return Card(padding: 0) {
            VStack(spacing: 0) {
                ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                    if index > 0 { InsetDivider(leading: 16) }
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        Text(row.0).mpFont(.copyLarge).foregroundStyle(MP.ink)
                        Spacer(minLength: 8)
                        Text(row.1).mpFont(.copyLarge).foregroundStyle(MP.muted)
                            .multilineTextAlignment(.trailing)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12)
                    .frame(minHeight: 48)
                    .accessibilityElement(children: .combine)
                }
            }
        }
    }

    // MARK: Actions

    /// Start is the one commit; the other two are quiet words, as on the
    /// task screen's bar. One row with "Just mark it done" under it, or a
    /// column at accessibility text sizes.
    @ViewBuilder private var actions: some View {
        if dynamicTypeSize.isAccessibilitySize {
            VStack(spacing: 2) {
                startButton(fullWidth: true)
                quiet("Just mark it done") { marking = true }.frame(maxWidth: .infinity)
                quiet("Can’t do it today") { skipping = true }.frame(maxWidth: .infinity)
            }
            .padding(.vertical, 6)
        } else {
            VStack(spacing: 0) {
                HStack(spacing: 12) {
                    quiet("Can’t do it today") { skipping = true }
                    Spacer(minLength: 8)
                    startButton(fullWidth: false)
                }
                quiet("Just mark it done") { marking = true }.frame(maxWidth: .infinity)
            }
            .padding(.top, 6)
        }
    }

    private func startButton(fullWidth: Bool) -> some View {
        Button { inSession = true } label: {
            HStack(spacing: 6) {
                Image(systemName: "play.fill")
                Text("Start").lineLimit(1).fixedSize()
            }
            .mpFont(.copyLargeMedium)
            .frame(maxWidth: fullWidth ? .infinity : nil)
            .padding(.horizontal, fullWidth ? 0 : 10)
        }
        .mpGlassButton(prominent: true)
        .controlSize(.large)
        .accessibilityHint("Opens the guided session")
    }

    private func quiet(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(minHeight: 44)
                .padding(.horizontal, 6)
                .contentShape(Rectangle())
        }
        .mpFont(.copy)
        .foregroundStyle(.primary)
        .buttonStyle(.plain)
    }
}
