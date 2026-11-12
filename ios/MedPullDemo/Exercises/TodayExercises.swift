import SwiftUI

/// Today's exercises on a clinic person's Today screen, under the greeting
/// and above the recovery hero: the day's exercises in order, then what is
/// still open from earlier in the week, with the count beside the title. The shared
/// `TodayView` places this view there in the demo target only
/// (`#if DEMO_APP` in ios/MedPull/Features/Today/TodayView.swift).
///
/// Two lines come from the clinic's between-visits record (docs/dev/pt.md):
/// "Rest day", with the therapist's note, under the title when the clinic
/// set today aside, and the next visit to the clinic as the card's last
/// line. Neither makes a card appear where there was none.
///
/// A person with no exercise calendar gets no card at all, so their Today
/// reads exactly as it does in the real app; a rest day inside a scheduled
/// week does show, so nothing looks missing. The reading, the ten-second
/// re-read and the screen a row opens are on `TodayExercisesHost`, which is
/// attached to Today itself and so is there whether or not this card is.
struct TodayExercises: View {
    @Environment(AppModel.self) private var app
    @Environment(ExerciseStore.self) private var store

    var body: some View {
        if let feed = store.feed, feed.hasSchedule {
            card(feed)
        }
    }

    private func card(_ feed: ExercisesResponse) -> some View {
        let today = store.today
        let open = feed.items.filter(\.isOpen)
        let settled = feed.items.filter { !$0.isOpen }
        let ordered = open + settled
        let done = feed.items.filter(\.isDone).count
        return Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardTitleRow("Today’s exercises",
                             note: feed.items.isEmpty ? nil : "\(done) of \(feed.items.count) done",
                             actionTitle: "Calendar") { app.selectedTab = .calendar }
                // A rest day the clinic set on purpose is said first, with
                // the therapist's note: it frames whatever is listed under it.
                if let rest = feed.restDay {
                    DayFactLine(symbol: DayFact.restSymbol, lead: "Rest day",
                                facts: rest.note.isEmpty ? [] : [ExerciseWords.typeset(rest.note)])
                        .padding(.horizontal, 16).padding(.bottom, 8)
                }
                if ordered.isEmpty && feed.overdue.isEmpty {
                    EmptyRow(icon: "figure.strengthtraining.functional", title: "Nothing today",
                             detail: Self.restDayLine(feed))
                        .padding(.bottom, 4)
                } else {
                    ForEach(ordered) { a in
                        row(a, today: today)
                        if a.id != ordered.last?.id { RowDivider() }
                    }
                    if !feed.overdue.isEmpty {
                        if !ordered.isEmpty { InsetDivider(leading: 16) }
                        Text("Still to do from earlier this week")
                            .mpFont(.label).foregroundStyle(MP.muted)
                            .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 2)
                            .accessibilityAddTraits(.isHeader)
                        ForEach(feed.overdue) { a in
                            row(a, today: today, dayLabel: ExerciseWords.weekday(a.scheduledFor))
                            if a.id != feed.overdue.last?.id { RowDivider() }
                        }
                    }
                    Text(Self.countLine(feed))
                        .mpFont(.label).foregroundStyle(MP.muted)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 14)
                }
                // The next visit to the clinic closes the card: after today,
                // this is what is coming.
                if let visit = feed.nextVisit {
                    InsetDivider(leading: 16)
                    DayFactLine(symbol: DayFact.visitSymbol, lead: "Next visit",
                                facts: ExerciseWords.visitFacts(visit, today: today))
                        .padding(.horizontal, 16).padding(.vertical, 12)
                }
            }
            .clipShape(MP.surfaceShape)
        }
        .mpCompletionFeedback(count: done)
    }

    private func row(_ a: ExerciseAssignment, today: String, dayLabel: String? = nil) -> some View {
        Button { store.openOnToday = ExerciseRef(id: a.id) } label: {
            ExerciseRow(a: a, today: today, dayLabel: dayLabel)
        }
        .buttonStyle(.mpRow)
    }

    /// "2 to do, 1 done and 1 from earlier this week." The header says how
    /// many of today's are done; this says what is left, in a sentence.
    static func countLine(_ feed: ExercisesResponse) -> String {
        let open = feed.items.filter(\.isOpen).count
        let skipped = feed.items.filter(\.isSkipped).count
        let earlier = feed.overdue.count
        var parts: [String] = []
        if open > 0 { parts.append("\(open) to do today") }
        if skipped > 0 { parts.append("\(skipped) skipped") }
        if earlier > 0 { parts.append("\(earlier) from earlier this week") }
        if parts.isEmpty {
            return feed.items.isEmpty ? restDayLine(feed)
                : "All done for today. \(ExerciseWords.therapist(feed.items.first?.assignedByName)) sees what you sent."
        }
        let list = parts.count == 1 ? parts[0] : parts.dropLast().joined(separator: ", ") + " and " + parts.last!
        return list.prefix(1).uppercased() + list.dropFirst() + "."
    }

    /// "A rest day. Your next exercises are on Wednesday." A rest day the
    /// clinic set has its own line above this one, so then only what comes
    /// next is said.
    static func restDayLine(_ feed: ExercisesResponse) -> String {
        let opening = feed.restDay == nil ? "A rest day. " : ""
        if let next = feed.week.first(where: { $0.date > feed.date && $0.assigned > 0 }) {
            return "\(opening)Your next exercises are on \(ExerciseWords.weekday(next.date))."
        }
        return "\(opening)New exercises from your therapist show up here."
    }
}

/// What Today needs for its exercises whether or not the card is showing:
/// the day read as Today appears and every ten seconds while it is up, the
/// exercise screen a row (or a texted link, `DemoShell.openExercise`) opens,
/// and the re-read after the presenter puts the day back.
struct TodayExercisesHost: ViewModifier {
    @Environment(AppModel.self) private var app
    @Environment(DemoShell.self) private var shell
    @Environment(ExerciseStore.self) private var store

    func body(content: Content) -> some View {
        @Bindable var store = store
        content
            .navigationDestination(item: $store.openOnToday) { ref in ExerciseScreen(id: ref.id) }
            .exerciseWatch()
            .onChange(of: shell.dayResets) { _, _ in Task { await store.refreshAll() } }
            #if DEBUG
            .task { await debugOpen() }
            #endif
    }

    #if DEBUG
    /// Simulator verification: `-MP_EXERCISE <assignment id>` opens that
    /// exercise on launch; `first` opens today's first open one, `required`
    /// the first that asks for a clip, `done` the latest done one.
    private func debugOpen() async {
        guard let wanted = AppConfig.debugFlag("MP_EXERCISE"), store.openOnToday == nil else { return }
        if let id = Int(wanted) {
            store.openOnToday = ExerciseRef(id: id)
            return
        }
        await store.refreshAll()
        let today = store.feed?.items ?? []
        let all = (store.program?.days ?? []).flatMap(\.items)
        let pick: ExerciseAssignment?
        switch wanted {
        case "required": pick = (today + all).first { $0.isOpen && $0.videoRequirement == .required }
        case "hold": pick = (today + all).first { $0.isOpen && $0.holdIsUnit }
        case "done": pick = today.last(where: \.isDone) ?? all.last(where: \.isDone)
        case "reviewed": pick = all.last { $0.completion?.review != nil }
        case "skipped": pick = (today + all).last(where: \.isSkipped)
        default: pick = today.first(where: \.isOpen) ?? today.first
        }
        if let pick { store.openOnToday = ExerciseRef(id: pick.id) }
    }
    #endif
}

extension View {
    /// Attached to Today's scroll view in the demo target.
    func todayExercisesHost() -> some View { modifier(TodayExercisesHost()) }
}
