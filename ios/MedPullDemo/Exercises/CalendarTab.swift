import SwiftUI

/// The Calendar tab of a clinic person: the program their clinic has set,
/// day by day. The fortnight around today as two rows of seven, a dot per
/// exercise (done, skipped, missed, to do) with today ringed, and the chosen
/// day's exercises under it. A past day shows what happened and can still be
/// caught up; today's rows open the exercise; the days ahead open as a
/// preview. A visit to the clinic and a rest day the clinic set are marked on
/// their days: a small symbol in the fortnight, the words on the chosen day.
///
/// Two rows of seven rather than a month grid: a loading program is read a
/// week at a time, and seven cells across a phone leave each day wide enough
/// for its dots.
struct CalendarTab: View {
    @Environment(AppModel.self) private var app
    @Environment(DemoShell.self) private var shell
    @Environment(ExerciseStore.self) private var store
    @State private var open: ExerciseRef?

    var body: some View {
        NavigationStack {
            ExerciseScroll {
                VStack(alignment: .leading, spacing: 18) {
                    content
                }
                .padding(.horizontal, 18).padding(.top, 4).padding(.bottom, 28)
            }
            .refreshable { await store.refreshAll() }
            .mpHardScrollEdge()
            .ambientScreen()
            .mpNavigationTitle("Calendar")
            .toolbarTitleDisplayMode(.large)
            .navigationDestination(item: $open) { ref in ExerciseScreen(id: ref.id) }
            .exerciseWatch(program: true)
            .onChange(of: shell.dayResets) { _, _ in Task { await store.refreshAll() } }
            #if DEBUG
            .task {
                // Simulator verification: `-MP_CAL_DAY 2026-11-13`, or `1` for
                // that many days ahead. A day behind today needs its date:
                // `-2` is read as the next argument's name, not a value.
                guard let raw = AppConfig.debugFlag("MP_CAL_DAY") else { return }
                if let offset = Int(raw), let date = Calendar.current.date(byAdding: .day, value: offset, to: Date()) {
                    store.calendarDay = Dates.dayString(date)
                } else {
                    store.calendarDay = raw
                }
            }
            #endif
        }
    }

    @ViewBuilder private var content: some View {
        if let program = store.program {
            if program.hasProgram {
                let today = store.today
                // The chosen day, or today when none is (or the one chosen
                // has left the fortnight on show).
                let day = store.calendarDay.flatMap { chosen in program.days.contains { $0.date == chosen } ? chosen : nil }
                    ?? today
                ProgramHero(program: program, today: today, clinic: clinicName(program)).mpRise(0)
                DayStrip(program: program, today: today, selected: day) { store.calendarDay = $0 }.mpRise(1)
                DayCard(day: program.days.first { $0.date == day }, date: day, today: today,
                        visits: program.visits(on: day), rest: program.restDay(on: day)) { open = ExerciseRef(id: $0.id) }
                    .mpRise(2)
                Text("Set by \(clinicName(program)). What you send goes back to them.")
                    .mpFont(.label).foregroundStyle(MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
            } else {
                Card(padding: 0) {
                    EmptyRow(icon: "calendar", title: "No exercises on your program yet",
                             detail: "They show up here as soon as \(clinicName(program)) sets them.")
                }
            }
        } else if store.programAsked {
            Card {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(alignment: .top, spacing: 12) {
                        Glyph(systemName: "wifi.exclamationmark", family: .blue, size: 40)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Can’t load your program").mpFont(.copyLargeMedium).foregroundStyle(MP.ink)
                            Text(store.programError ?? "Check your connection and try again.")
                                .mpFont(.copy).foregroundStyle(MP.body).lineSpacing(2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 0)
                    }
                    SecondaryButton(title: "Try again", icon: "arrow.clockwise") {
                        Task { await store.refreshAll() }
                    }
                }
            }
        } else {
            LoadingCard(text: "Reading your program…")
        }
    }

    private func clinicName(_ program: ProgramResponse) -> String {
        program.clinic?.name ?? app.me?.patient.hospital?.name ?? "your clinic"
    }
}

// MARK: - Hero

/// The screen's one gradient: how much of the last week (and today) is
/// done, the fortnight as white marks, and what is next in a sentence.
private struct ProgramHero: View {
    let program: ProgramResponse
    let today: String
    let clinic: String

    var body: some View {
        let soFar = program.days.filter { $0.date <= today }
        let assigned = soFar.reduce(0) { $0 + $1.assigned }
        let done = soFar.reduce(0) { $0 + $1.done }
        let todayDay = program.days.first { $0.date == today }
        let openToday = todayDay?.items.filter(\.isOpen).count ?? 0
        let side: (String, String) = {
            guard let todayDay, todayDay.assigned > 0 else { return ("Rest", "day today") }
            return openToday == 0 ? ("Done", "for today") : ("\(openToday)", "to do today")
        }()
        GradientTile(.meadow, kicker: "Your program", value: "\(done)", unit: "of \(assigned) done", side: side) {
            ProgramArt(days: program.days, today: today).padding(.top, 2)
        } caption: {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    if let todayDay, todayDay.assigned > 0 {
                        StatusPill(text: openToday == 0 ? "Today is done" : "\(openToday) to do today",
                                   tone: openToday == 0 ? .low : .brand)
                    } else {
                        StatusPill(text: "Rest day", tone: .missing)
                    }
                    Spacer()
                }
                Text(Self.nextLine(program, today: today))
                    .mpFont(.copyLarge).foregroundStyle(MP.ink).lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
            }
        }
        .accessibilityElement(children: .combine)
    }

    /// "Today: Heel Slides." or "Next: Friday. Step-Ups, Wall Sits and 3
    /// more."
    static func nextLine(_ program: ProgramResponse, today: String) -> String {
        func names(_ items: [ExerciseAssignment]) -> String {
            let titles = items.map(\.title)
            switch titles.count {
            case 0: return ""
            case 1: return titles[0]
            case 2: return "\(titles[0]) and \(titles[1])"
            default: return "\(titles[0]), \(titles[1]) and \(titles.count - 2) more"
            }
        }
        if let now = program.days.first(where: { $0.date == today }) {
            let open = now.items.filter(\.isOpen)
            if !open.isEmpty { return "Today: \(names(open))." }
        }
        if let next = program.days.first(where: { $0.date > today && !$0.items.isEmpty }) {
            return "Next: \(ExerciseWords.dayTitle(next.date, today: today)). \(names(next.items))."
        }
        return "Nothing is planned after today yet."
    }
}

/// The fortnight as white marks: one square per exercise, solid once done,
/// outlined while it is still to do, faint when it was skipped or missed. A
/// lime dot sits under today.
private struct ProgramArt: View {
    let days: [ProgramDay]
    let today: String

    var body: some View {
        let tallest = max(1, min(5, days.map { max($0.items.count, $0.assigned) }.max() ?? 1))
        HStack(alignment: .bottom, spacing: 5) {
            ForEach(days) { day in
                VStack(spacing: 4) {
                    Spacer(minLength: 0)
                    ForEach(Array(marks(day).enumerated()), id: \.offset) { _, mark in
                        RoundedRectangle(cornerRadius: 3, style: .continuous)
                            .fill(Color.white.opacity(mark.fill))
                            .overlay(RoundedRectangle(cornerRadius: 3, style: .continuous)
                                .strokeBorder(Color.white.opacity(mark.edge), lineWidth: 1.5))
                            .frame(height: 11)
                    }
                    Circle().fill(day.date == today ? MP.lime : Color.clear)
                        .frame(width: 6, height: 6)
                        .shadow(color: day.date == today ? MP.lime.opacity(0.9) : .clear, radius: 4)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .frame(height: CGFloat(tallest) * 15 + 14)
    }

    private func marks(_ day: ProgramDay) -> [(fill: Double, edge: Double)] {
        let past = day.date < today
        // Top to bottom in the day's own order, so the column reads like
        // the list under the calendar.
        return day.items.prefix(5).map { a -> (fill: Double, edge: Double) in
            if a.isDone { return (0.95, 0) }
            if a.isSkipped { return (0.3, 0) }
            return past ? (0.12, 0.45) : (0, 0.9)
        }
    }
}

// MARK: - The fortnight

/// Two rows of seven: the days before today, and today with the six after.
private struct DayStrip: View {
    let program: ProgramResponse
    let today: String
    let selected: String
    let select: (String) -> Void

    var body: some View {
        let past = program.days.filter { $0.date < today }
        let ahead = program.days.filter { $0.date >= today }
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                if !past.isEmpty {
                    label("The last \(past.count) days")
                    week(past)
                }
                if !ahead.isEmpty {
                    label("From today")
                    week(ahead)
                }
                legend
            }
            .padding(.vertical, 6)
        }
        .mpSelectionFeedback(selected)
    }

    private func label(_ text: String) -> some View {
        Text(text).mpFont(.label).foregroundStyle(MP.muted)
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 4)
            .accessibilityAddTraits(.isHeader)
    }

    private func week(_ days: [ProgramDay]) -> some View {
        HStack(spacing: 0) {
            ForEach(days) { day in
                DayCell(day: day, today: today, isSelected: day.date == selected,
                        visits: program.visits(on: day.date), rest: program.restDay(on: day.date),
                        marksRow: program.hasMarks) { select(day.date) }
            }
            // A short week (the program's window is being changed) keeps
            // its cells the width of a full one.
            ForEach(0..<max(0, 7 - days.count), id: \.self) { _ in Color.clear.frame(maxWidth: .infinity) }
        }
        .padding(.horizontal, 8)
    }

    /// The dots, and under them the two symbols, each only when a day of
    /// the fortnight carries one.
    private var legend: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 14) {
                key("done", MP.riskLow, hollow: false)
                key("to do", MP.riskMissing, hollow: true)
                key("missed", MP.riskMed, hollow: false)
                key("skipped", MP.muted, hollow: false)
            }
            if program.hasMarks {
                HStack(spacing: 14) {
                    if !program.visits.isEmpty { key("clinic visit", symbol: DayFact.visitSymbol, MP.brandInk) }
                    if !program.restDays.isEmpty { key("rest day", symbol: DayFact.restSymbol, MP.muted) }
                }
            }
        }
        .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 8)
        .accessibilityHidden(true)
    }

    private func key(_ word: String, symbol: String, _ color: Color) -> some View {
        HStack(spacing: 5) {
            DayMark(symbol: symbol, color: color)
            Text(word).mpFont(.label).foregroundStyle(MP.muted)
        }
    }

    private func key(_ word: String, _ color: Color, hollow: Bool) -> some View {
        HStack(spacing: 5) {
            ProgramDot(color: color, hollow: hollow)
            Text(word).mpFont(.label).foregroundStyle(MP.muted)
        }
    }
}

private struct ProgramDot: View {
    let color: Color
    let hollow: Bool

    var body: some View {
        Group {
            if hollow {
                Circle().strokeBorder(color, lineWidth: 1.5)
            } else {
                Circle().fill(color)
            }
        }
        .frame(width: 6, height: 6)
    }
}

/// A visit or a set rest day as the strip draws it: its symbol, small. The
/// words are on the chosen day's card and in the legend.
private struct DayMark: View {
    let symbol: String
    let color: Color

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: 9, weight: .semibold))
            .foregroundStyle(color)
            .frame(height: 10)
    }
}

/// One day of the strip: the weekday, the date, a dot for each exercise in
/// its state, and under the dots the mark of a clinic visit or a rest day
/// the clinic set. Today is ringed; the chosen day is filled.
private struct DayCell: View {
    let day: ProgramDay
    let today: String
    let isSelected: Bool
    /// The clinic visits on this day, and the rest day set on it.
    var visits: [ClinicVisit] = []
    var rest: RestDay? = nil
    /// Whether the strip keeps a line under the dots for those marks. Only
    /// a fortnight that has some does, and then every cell keeps it, so
    /// the days stay level.
    var marksRow = false
    let select: () -> Void

    var body: some View {
        let date = Dates.parse(day.date)
        let isToday = day.date == today
        Button(action: select) {
            VStack(spacing: 5) {
                Text(date?.formatted(.dateTime.weekday(.narrow)) ?? "")
                    .mpFont(.label).foregroundStyle(MP.muted)
                Text(date.map { "\(Calendar.current.component(.day, from: $0))" } ?? "")
                    .font(.figuresCopyLarge)
                    .foregroundStyle(isSelected ? MP.onAction : MP.ink)
                    .frame(width: 36, height: 36)
                    .background {
                        if isSelected {
                            Circle().fill(MP.action)
                        } else if isToday {
                            Circle().strokeBorder(MP.ink, lineWidth: 1.5)
                        }
                    }
                HStack(spacing: 3) {
                    ForEach(Array(dots.enumerated()), id: \.offset) { _, dot in
                        ProgramDot(color: dot.0, hollow: dot.1)
                    }
                }
                .frame(height: 6)
                if marksRow {
                    HStack(spacing: 4) {
                        if !visits.isEmpty { DayMark(symbol: DayFact.visitSymbol, color: MP.brandInk) }
                        if rest != nil { DayMark(symbol: DayFact.restSymbol, color: MP.muted) }
                    }
                    .frame(height: 10)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(spoken(date, isToday: isToday))
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }

    /// A dot per exercise, five at most: done, skipped, missed (still to do
    /// and the day has passed), or the hollow dot of one still to do.
    private var dots: [(Color, Bool)] {
        day.items.prefix(5).map { a -> (Color, Bool) in
            switch a.state(on: today) {
            case .done: return (MP.riskLow, false)
            case .skipped: return (MP.muted, false)
            case .missed: return (MP.riskMed, false)
            default: return (MP.riskMissing, true)
            }
        }
    }

    private func spoken(_ date: Date?, isToday: Bool) -> String {
        let name = date?.formatted(.dateTime.weekday(.wide).month(.abbreviated).day()) ?? day.date
        let what = day.assigned == 0 ? "a rest day"
            : "\(day.assigned) \(day.assigned == 1 ? "exercise" : "exercises"), \(day.done) done"
                + (day.missed > 0 ? ", \(day.missed) missed" : "")
        // A day with nothing on it is already called a rest day.
        let marks = visits.map(ExerciseWords.visitMarker) + (rest != nil && day.assigned > 0 ? ["rest day"] : [])
        return (["\(isToday ? "Today, " : "")\(name)", what] + marks).joined(separator: ", ")
    }
}

// MARK: - The chosen day

private struct DayCard: View {
    let day: ProgramDay?
    let date: String
    let today: String
    /// The clinic visits on this day, and the rest day the clinic set on it.
    var visits: [ClinicVisit] = []
    var rest: RestDay? = nil
    let open: (ExerciseAssignment) -> Void

    var body: some View {
        let past = date < today
        let future = date > today
        let items = day?.items ?? []
        let ordered = date == today ? items.filter(\.isOpen) + items.filter { !$0.isOpen } : items
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                CardTitleRow(ExerciseWords.dayTitle(date, today: today), note: note(past: past, future: future))
                if !visits.isEmpty || rest != nil { marks }
                if ordered.isEmpty {
                    // A day the clinic set aside is a rest day whenever it
                    // falls; an empty day ahead may still be filled.
                    EmptyRow(icon: "figure.strengthtraining.functional",
                             title: future && rest == nil ? "Nothing planned yet" : "A rest day",
                             detail: rest != nil ? "Your clinic set this day aside for rest."
                                : future ? "Your therapist may still add to this day."
                                : past ? "Nothing was scheduled." : "Nothing scheduled today.")
                        .padding(.bottom, 4)
                } else {
                    ForEach(ordered) { a in
                        Button { open(a) } label: { ExerciseRow(a: a, today: today) }
                            .buttonStyle(.mpRow)
                        if a.id != ordered.last?.id { RowDivider() }
                    }
                }
            }
            .padding(.bottom, ordered.isEmpty ? 0 : 4)
            .clipShape(MP.surfaceShape)
        }
    }

    /// What else is on the day, in words: "Test day 9:30 AM", "Rest day",
    /// and the therapist's note on a rest day when she left one.
    private var marks: some View {
        VStack(alignment: .leading, spacing: 6) {
            BrandFlow(spacing: 6) {
                ForEach(Array(visits.enumerated()), id: \.offset) { _, visit in
                    ExercisePill(text: ExerciseWords.visitMarker(visit), symbol: DayFact.visitSymbol)
                }
                if rest != nil { ExercisePill(text: "Rest day", symbol: DayFact.restSymbol) }
            }
            if let note = rest?.note, !note.isEmpty {
                Text(ExerciseWords.typeset(note)).mpFont(.label).foregroundStyle(MP.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16).padding(.bottom, 8)
    }

    /// "Nov 13 · 3 of 4 done · 1 missed" beside the title.
    private func note(past: Bool, future: Bool) -> String {
        var parts = [Dates.monthDay(date)]
        guard let day, day.assigned > 0 else { return parts[0] }
        if future {
            parts.append("\(day.assigned) \(day.assigned == 1 ? "exercise" : "exercises")")
        } else {
            parts.append("\(day.done) of \(day.assigned) done")
            if past, day.missed > 0 { parts.append("\(day.missed) missed") }
        }
        return parts.joined(separator: MP.dot)
    }
}
