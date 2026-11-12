import Foundation
import Observation
import SwiftUI

/// The signed-in person's exercise calendar: today's feed and the program
/// around it, kept fresh while a screen that shows them is up, and the three
/// things a person does to a row (start, complete, skip).
///
/// One instance lives in the environment beside `AppModel`. The real app's
/// `AppModel` has no exercise feed (the App Store app has no exercise
/// screens), so the demo keeps its own here instead of growing the shared
/// class.
@Observable
@MainActor
final class ExerciseStore {
    private let app: AppModel

    init(app: AppModel) { self.app = app }

    // MARK: What the server said

    /// `GET /api/mobile/exercises` for the phone's own day, as last read.
    private(set) var feed: ExercisesResponse?
    /// `GET /api/mobile/exercises/program`: a week back and a week ahead.
    private(set) var program: ProgramResponse?
    /// True once the day has answered (or failed) for this person, so "no
    /// schedule" is something the server said and not a guess.
    private(set) var dayAsked = false
    private(set) var programAsked = false
    /// Why the program could not be read, when there is none to show.
    private(set) var programError: String?

    /// The program opens a week back, like the web app's.
    static let daysBack = 7
    static let days = 14

    /// The phone's own day, "yyyy-MM-dd".
    var today: String { Dates.dayString(Date()) }

    /// The unit this person's clinic reads loads in.
    var unit: LoadUnit { feed?.clinic?.loadUnit ?? program?.clinic?.loadUnit ?? .kg }

    /// The row behind an id, from wherever it is held: today's list, the
    /// still-to-do group, the program's days.
    func assignment(_ id: Int) -> ExerciseAssignment? {
        if let hit = feed?.items.first(where: { $0.id == id }) { return hit }
        if let hit = feed?.overdue.first(where: { $0.id == id }) { return hit }
        for day in program?.days ?? [] {
            if let hit = day.items.first(where: { $0.id == id }) { return hit }
        }
        return nil
    }

    // MARK: Routing

    /// The exercise Today has open, pushed on its navigation stack
    /// (`TodayExercisesHost`). A row sets it; so does a link to one exercise.
    var openOnToday: ExerciseRef?
    /// The day the Calendar tab has chosen ("yyyy-MM-dd"); nil is today. A
    /// tap on a day sets it; so does a link to the program that names one.
    /// Held here rather than in the tab, so it is still there when a link
    /// has just rebuilt the tabs for another person.
    var calendarDay: String?

    // MARK: Watching

    /// Who is watching, and whether each wants the program as well.
    private var watchers: [UUID: Bool] = [:]
    private var watchLoop: Task<Void, Never>?

    /// A screen that shows the calendar came up: read now, and keep reading
    /// every ten seconds until the last such screen has gone.
    func beginWatch(program: Bool) -> UUID {
        let id = UUID()
        watchers[id] = program
        Task { if program { await self.refreshAll() } else { await self.refreshDay() } }
        if watchLoop == nil {
            watchLoop = Task { [weak self] in
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(ExerciseStore.watchInterval))
                    guard let self, !Task.isCancelled else { return }
                    if self.watchers.values.contains(true) { await self.refreshAll() } else { await self.refreshDay() }
                }
            }
        }
        return id
    }

    func endWatch(_ id: UUID) {
        watchers[id] = nil
        if watchers.isEmpty {
            watchLoop?.cancel()
            watchLoop = nil
        }
    }

    // MARK: Reading

    private var dayInFlight: Task<Void, Never>?
    private var programInFlight: Task<Void, Never>?
    /// Bumped when someone else signs in, so an answer still in flight for
    /// the person before is dropped.
    private var generation = 0

    /// Read the day. One call at a time: a slow answer is not stacked
    /// behind the next tick of the watch. A failed re-read keeps the list
    /// that is on screen.
    func refreshDay() async {
        if let running = dayInFlight { return await running.value }
        let mine = generation
        let task = Task { [weak self] in
            guard let self else { return }
            do {
                let answer = try await self.app.api.exercises(date: self.today)
                guard mine == self.generation else { return }
                self.feed = answer
            } catch {
                guard mine == self.generation else { return }
                self.noteReadFailure(error)
            }
            if mine == self.generation { self.dayAsked = true }
        }
        dayInFlight = task
        await task.value
        if dayInFlight == task { dayInFlight = nil }
    }

    /// Read the program around today.
    func refreshProgram() async {
        if let running = programInFlight { return await running.value }
        let mine = generation
        let start = Calendar.current.date(byAdding: .day, value: -Self.daysBack, to: Date()) ?? Date()
        let task = Task { [weak self] in
            guard let self else { return }
            do {
                let answer = try await self.app.api.exerciseProgram(start: Dates.dayString(start), days: Self.days)
                guard mine == self.generation else { return }
                self.program = answer
                self.programError = nil
            } catch {
                guard mine == self.generation else { return }
                self.noteReadFailure(error)
                if self.program == nil, let sentence = ExerciseStore.sentence(for: error) {
                    self.programError = sentence
                }
            }
            if mine == self.generation { self.programAsked = true }
        }
        programInFlight = task
        await task.value
        if programInFlight == task { programInFlight = nil }
    }

    func refreshAll() async {
        async let day: Void = refreshDay()
        async let program: Void = refreshProgram()
        _ = await (day, program)
    }

    /// A session that has ended signs the app out, as any other read does;
    /// nothing else about a failed poll is worth interrupting the person.
    private func noteReadFailure(_ error: Error) {
        if let e = error as? APIError, e.isUnauthorized { app.note(error) }
    }

    /// Someone else signed in (or nobody is): the feeds belong to whoever
    /// was here before.
    func reset() {
        generation += 1
        dayInFlight?.cancel()
        programInFlight?.cancel()
        dayInFlight = nil
        programInFlight = nil
        feed = nil
        program = nil
        dayAsked = false
        programAsked = false
        programError = nil
        openOnToday = nil
        calendarDay = nil
        // A screen that is still up (the same tabs, another server) should
        // not wait for the next tick to fill in again.
        if !watchers.isEmpty { Task { await self.refreshAll() } }
    }

    // MARK: Doing

    /// "Start": the row comes back with its session begun.
    @discardableResult
    func start(_ a: ExerciseAssignment, painBefore: Int?, wearableWorn: Bool?) async throws -> ExerciseAssignment {
        let updated = try await guarded {
            try await self.app.api.startExercise(id: a.id, painBefore: painBefore, wearableWorn: wearableWorn)
        }
        replace(updated)
        return updated
    }

    /// "Send": the row comes back done. The server also wrote a line on the
    /// thread (with the clip on it), so Care is read again.
    @discardableResult
    func complete(_ a: ExerciseAssignment, body: ExerciseCompletionBody) async throws -> ExerciseAssignment {
        let updated = try await guarded { try await self.app.api.completeExercise(id: a.id, body: body) }
        replace(updated)
        Task { await self.app.refreshMessages(surface: false) }
        return updated
    }

    /// "Can't do it today": the row is skipped with the reason.
    @discardableResult
    func skip(_ a: ExerciseAssignment, reason: String) async throws -> ExerciseAssignment {
        let updated = try await guarded { try await self.app.api.skipExercise(id: a.id, reason: reason) }
        replace(updated)
        return updated
    }

    /// Run an action the person is waiting on. A session that has ended
    /// signs the app out (the picker takes over); everything else is the
    /// caller's to show, in the server's own sentence.
    private func guarded<T>(_ call: () async throws -> T) async throws -> T {
        do {
            return try await call()
        } catch {
            if let e = error as? APIError, e.isUnauthorized { app.note(error) }
            throw error
        }
    }

    /// The row as the server now has it, wherever this app holds it, with
    /// the counts beside each day recounted the way the server counts them.
    private func replace(_ updated: ExerciseAssignment) {
        if var feed {
            feed.items = feed.items.map { $0.id == updated.id ? updated : $0 }
            // The still-to-do group lists open rows only.
            feed.overdue = feed.overdue.compactMap { $0.id == updated.id ? (updated.isOpen ? updated : nil) : $0 }
            feed.week = feed.week.map { day in
                guard day.date == feed.date else { return day }
                var day = day
                day.done = feed.items.filter(\.isDone).count
                day.skipped = feed.items.filter(\.isSkipped).count
                return day
            }
            self.feed = feed
        }
        if var program {
            let today = self.today
            program.days = program.days.map { day in
                guard day.items.contains(where: { $0.id == updated.id }) else { return day }
                var day = day
                day.items = day.items.map { $0.id == updated.id ? updated : $0 }
                day.done = day.items.filter(\.isDone).count
                day.skipped = day.items.filter(\.isSkipped).count
                day.missed = day.date < today ? day.items.filter(\.isOpen).count : 0
                return day
            }
            self.program = program
        }
    }

    // MARK: Words

    /// What to tell the person when a call fails, or nil when the screen
    /// simply went away. A refusal (422, 409) is the server's own sentence.
    static func sentence(for error: Error) -> String? {
        if error is CancellationError { return nil }
        if let e = error as? URLError, e.code == .cancelled { return nil }
        if let e = error as? APIError {
            if e.status == 404, e.detail.caseInsensitiveCompare("Not Found") == .orderedSame {
                return "This server has no exercise calendar."
            }
            return e.detail.typeset
        }
        return error.localizedDescription
    }
}

/// An exercise to open, by its assignment id. The screen reads the row from
/// the store each time it draws, so what it shows is never a stale copy.
struct ExerciseRef: Identifiable, Hashable {
    let id: Int
}

// MARK: - Live

extension ExerciseStore {
    /// How often the calendar is read again while a screen is watching.
    static let watchInterval: Double = 10
}

/// Keeps the calendar fresh while the view it is on is showing: once as it
/// appears, every ten seconds after that, and again the moment the app comes
/// back to the foreground. So an exercise the therapist assigns on the
/// console lands on the phone without a pull. Nothing runs while no watching
/// view is on screen or the app is in the background.
///
/// Screens overlap (the guided session covers the exercise it was started
/// from), so the store counts its watchers and runs one loop for all of
/// them rather than one each.
private struct ExerciseWatch: ViewModifier {
    let program: Bool
    @Environment(ExerciseStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase

    func body(content: Content) -> some View {
        // Keyed on being in the background, not on being active: a system
        // alert or the app switcher makes the scene inactive, and the
        // calendar under it should still load.
        content.task(id: scenePhase == .background) {
            guard scenePhase != .background else { return }
            let watch = store.beginWatch(program: program)
            defer { store.endWatch(watch) }
            // Held until the view goes away or the app leaves the foreground.
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(3600))
            }
        }
    }
}

extension View {
    /// Re-read the day (and, with `program`, the two weeks around it) while
    /// this view is on screen.
    func exerciseWatch(program: Bool = false) -> some View {
        modifier(ExerciseWatch(program: program))
    }
}
