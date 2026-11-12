import XCTest
@testable import MedPullDemo

/// The exercise calendar's wire types against what the server sends
/// (`/api/mobile/exercises…`, backend/app/hep/schedule.py), including the
/// fields the calendar stream has since added, and the words and sums the
/// screens build from them.
final class ExerciseModelTests: XCTestCase {
    // MARK: Fixtures: rows a local server answered for the seeded lifter

    /// Done, with the session, what was actually done and the review.
    private static let reviewed = """
    {"id": 28, "exercise_id": 18, "title": "Step-Ups", "equipment": "A low step or bottom stair",
     "precautions": "Keep the knee over the foot. Use a rail for balance.",
     "steps": ["Stand facing a low step.", "Step up with one foot.", "Step down slowly."],
     "scheduled_for": "2026-11-09", "sort_order": 0, "sets": 3, "reps": 10, "hold_seconds": null,
     "side": "left", "side_label": "Left", "load_kg": 10.0, "rpe_target": 7,
     "dose": "3 sets × 10 reps · 10 kg · Left", "clinician_instructions": "Slow on the way down.",
     "assigned_by": "ct_gregg", "assigned_by_name": "Dr. Ashley Gregg",
     "video_requirement": "required", "wearable_requirement": "optional", "status": "done",
     "video": {"id": 1, "kind": "video", "source": "clinic", "exercise_id": 18, "clinic_id": "hirt",
               "approval_status": "approved", "playable": true, "url": "/api/mobile/exercises/media/1/raw",
               "poster_url": null, "content_type": "video/mp4", "uploaded_by": "ct_gregg",
               "uploaded_by_name": "Dr. Ashley Gregg", "version": 1},
     "session": {"started_at": "2026-11-09T18:40:00", "ended_at": "2026-11-09T18:53:00", "duration_s": 780,
                 "pain_before": 3, "wearable_worn": null, "hr_avg": null, "hr_max": null},
     "completion": {"completed_at": "2026-11-09T18:53:00", "pain_after": 4, "note": "", "source": "app",
                    "video": {"id": 7, "content_type": "video/mp4", "byte_size": 179510,
                              "filename": "attempt.mp4", "kind": "video", "uploaded_by": "patient",
                              "source": "app", "withdrawn": false, "url": null},
                    "effort": 7, "sets_done": 3, "reps_done": 10, "load_done_kg": 16.0,
                    "review": {"at": "2026-11-09T21:13:00", "by": "ct_gregg", "by_name": "Dr. Ashley Gregg",
                               "note": "Depth looks good."},
                    "awaiting_review": false},
     "skip_reason": null}
    """

    /// Open, a timed hold, a clip required, and the two fields the calendar
    /// stream added to every row (`state`, `series_id`).
    private static let wallSits = """
    {"id": 378, "exercise_id": 20, "title": "Wall Sits", "equipment": "A wall", "precautions": "",
     "scheduled_for": "2026-11-12", "sort_order": 2, "series_id": "s-19", "sets": 3, "reps": null,
     "hold_seconds": 30, "side": "not_applicable", "side_label": "", "load_kg": null, "rpe_target": 7,
     "dose": "3 sets · hold 30 s", "clinician_instructions": "", "assigned_by_name": "Dr. Ashley Gregg",
     "video_requirement": "required", "wearable_requirement": "off", "status": "assigned", "state": "due",
     "video": null, "session": null, "completion": null, "skip_reason": null}
    """

    private func row(_ json: String) throws -> ExerciseAssignment {
        try Fixtures.decode(ExerciseAssignment.self, json)
    }

    // MARK: Rows

    func testADoneRowDecodesWithItsSessionCompletionAndReview() throws {
        let a = try row(Self.reviewed)
        XCTAssertEqual(a.id, 28)
        XCTAssertEqual(a.title, "Step-Ups")
        XCTAssertEqual(a.steps.count, 3)
        XCTAssertEqual(a.dose, "3 sets × 10 reps · 10 kg · Left")
        XCTAssertEqual(a.loadKg, 10)
        XCTAssertEqual(a.rpeTarget, 7)
        XCTAssertEqual(a.videoRequirement, .required)
        XCTAssertEqual(a.wearableRequirement, .optional)
        XCTAssertTrue(a.isDone)
        XCTAssertTrue(a.hasSide)
        XCTAssertFalse(a.holdIsUnit)

        XCTAssertEqual(a.video?.id, 1)
        XCTAssertEqual(a.video?.source, "clinic")
        XCTAssertEqual(a.video?.url, "/api/mobile/exercises/media/1/raw")
        XCTAssertEqual(a.video?.uploadedByName, "Dr. Ashley Gregg")
        XCTAssertEqual(a.demonstration, .demonstration(assignmentId: 28, mediaId: 1))

        XCTAssertEqual(a.session?.painBefore, 3)
        XCTAssertEqual(a.sessionSeconds, 780)
        XCTAssertNil(a.session?.wearableWorn)

        let c = try XCTUnwrap(a.completion)
        XCTAssertEqual(c.painAfter, 4)
        XCTAssertEqual(c.effort, 7)
        XCTAssertEqual(c.setsDone, 3)
        XCTAssertEqual(c.repsDone, 10)
        XCTAssertEqual(c.loadDoneKg, 16)
        XCTAssertEqual(c.video?.id, 7)
        XCTAssertEqual(c.review?.byName, "Dr. Ashley Gregg")
        XCTAssertEqual(c.review?.note, "Depth looks good.")
        // A clip she has looked at is no longer waiting for her.
        XCTAssertFalse(a.awaitingReview)

        // What was done against what was prescribed, in either unit.
        XCTAssertEqual(a.doneLine(unit: .kg), "3 × 10\(MP.dot)16 kg")
        XCTAssertEqual(a.prescribedLine(unit: .kg), "3 × 10\(MP.dot)10 kg")
        XCTAssertEqual(a.doneLine(unit: .lb), "3 × 10\(MP.dot)35.3 lb")
        XCTAssertEqual(a.prescribedLine(unit: .lb), "3 × 10\(MP.dot)22 lb")
    }

    func testAnOpenRowWithFieldsThisBuildHasNeverHeardOf() throws {
        let a = try row(Self.wallSits)
        XCTAssertTrue(a.isOpen)
        XCTAssertTrue(a.holdIsUnit)
        XCTAssertFalse(a.hasSide)
        XCTAssertNil(a.demonstration)
        XCTAssertEqual(a.wearableRequirement, .off)
        XCTAssertNil(a.session)
        XCTAssertNil(a.completion)
        XCTAssertEqual(a.prescribedLine(unit: .kg), "3 sets")
        XCTAssertNil(a.sessionSeconds)
    }

    func testARowNeedsOnlyItsIdAndStatus() throws {
        let bare = try row(#"{"id": 5, "status": "assigned"}"#)
        XCTAssertEqual(bare.title, "Exercise")
        XCTAssertEqual(bare.steps, [])
        XCTAssertEqual(bare.dose, "")
        // The server's default for both requirements, and a server that
        // does not send them yet, is "optional".
        XCTAssertEqual(bare.videoRequirement, .optional)
        XCTAssertEqual(bare.wearableRequirement, .optional)
        XCTAssertNil(bare.loadKg)
        XCTAssertThrowsError(try row(#"{"title": "No id"}"#))
        // Numbers that arrive as text or with a decimal point still read.
        let loose = try row(#"{"id": 6, "status": "assigned", "sets": "3", "reps": 10.0, "load_kg": 12}"#)
        XCTAssertEqual(loose.sets, 3)
        XCTAssertEqual(loose.reps, 10)
        XCTAssertEqual(loose.loadKg, 12)
    }

    func testStateIsReadOffTheDayAndTheSession() throws {
        let open = try row(Self.wallSits)
        XCTAssertEqual(open.state(on: "2026-11-12"), .due)
        XCTAssertEqual(open.state(on: "2026-11-13"), .missed)
        XCTAssertEqual(open.state(on: "2026-11-11"), .upcoming)
        XCTAssertEqual(try row(Self.reviewed).state(on: "2026-11-12"), .done)
        XCTAssertEqual(try row(#"{"id": 1, "status": "skipped", "scheduled_for": "2026-11-12"}"#).state(on: "2026-11-12"),
                       .skipped)
        // Started today and not finished: in progress, today only.
        let started = try row(#"""
        {"id": 2, "status": "assigned", "scheduled_for": "2026-11-12",
         "session": {"started_at": "2026-11-12T09:05:11.120000", "pain_before": 2}}
        """#)
        XCTAssertEqual(started.state(on: "2026-11-12"), .inProgress)
        XCTAssertEqual(started.state(on: "2026-11-13"), .missed)
    }

    func testTheStartCompleteAndSkipRoutesAnswerEitherWay() throws {
        let wrapped = try Fixtures.decode(AssignmentAnswer.self, #"{"assignment": \#(Self.wallSits)}"#)
        XCTAssertEqual(wrapped.assignment.id, 378)
        let bare = try Fixtures.decode(AssignmentAnswer.self, Self.wallSits)
        XCTAssertEqual(bare.assignment.id, 378)
    }

    // MARK: Feeds

    func testTodaysFeed() throws {
        let feed = try Fixtures.decode(ExercisesResponse.self, #"""
        {"date": "2026-11-12", "today": "2026-11-12",
         "items": [\#(Self.wallSits), {"broken": true}],
         "overdue": [{"id": 380, "status": "assigned", "title": "Terminal Knee Extensions", "scheduled_for": "2026-11-10"}],
         "week": [{"date": "2026-11-11", "assigned": 5, "done": 5, "skipped": 0},
                  {"date": "2026-11-12", "assigned": 1, "done": 0},
                  {"date": "2026-11-13", "assigned": 5, "done": 0, "skipped": 0}],
         "clinic": {"id": "hirt", "name": "H.I.R.T. Physical Therapy"}}
        """#)
        // The row that could not be read is dropped; the day still shows.
        XCTAssertEqual(feed.items.map(\.id), [378])
        XCTAssertEqual(feed.overdue.map(\.id), [380])
        XCTAssertEqual(feed.week.count, 3)
        XCTAssertEqual(feed.week[1].skipped, 0)
        XCTAssertTrue(feed.hasSchedule)
        // A clinic that has not said reads in kilograms.
        XCTAssertEqual(feed.clinic?.loadUnit, .kg)
        XCTAssertEqual(TodayExercises.countLine(feed), "1 to do today and 1 from earlier this week.")

        let rest = try Fixtures.decode(ExercisesResponse.self, #"""
        {"date": "2026-11-12", "items": [], "overdue": [],
         "week": [{"date": "2026-11-12", "assigned": 0, "done": 0}, {"date": "2026-11-13", "assigned": 5, "done": 0}],
         "clinic": {"id": "hirt", "name": "H.I.R.T. Physical Therapy", "load_unit": "lb"}}
        """#)
        XCTAssertTrue(rest.hasSchedule)
        XCTAssertEqual(rest.clinic?.loadUnit, .lb)
        XCTAssertEqual(TodayExercises.restDayLine(rest), "A rest day. Your next exercises are on Friday.")

        // No schedule at all: Today shows no card.
        let none = try Fixtures.decode(ExercisesResponse.self, #"{"date": "2026-11-12", "items": [], "week": [], "clinic": null}"#)
        XCTAssertFalse(none.hasSchedule)
        XCTAssertNil(none.clinic)
    }

    func testTheProgram() throws {
        let program = try Fixtures.decode(ProgramResponse.self, #"""
        {"start": "2026-11-09", "today": "2026-11-12",
         "days": [{"date": "2026-11-09", "items": [\#(Self.reviewed)], "assigned": 1, "done": 1, "skipped": 0, "missed": 0},
                  {"date": "2026-11-10", "items": [], "assigned": 0, "done": 0, "skipped": 0, "missed": 0},
                  {"date": "2026-11-12", "items": [\#(Self.wallSits)]}],
         "clinic": {"id": "hirt", "name": "H.I.R.T. Physical Therapy", "load_unit": "lb"}}
        """#)
        XCTAssertEqual(program.days.count, 3)
        XCTAssertTrue(program.hasProgram)
        XCTAssertEqual(program.days[0].done, 1)
        // A day sent without its counts is counted from its rows.
        XCTAssertEqual(program.days[2].assigned, 1)
        XCTAssertEqual(program.days[2].done, 0)
        XCTAssertEqual(program.clinic?.loadUnit, .lb)
        let empty = try Fixtures.decode(ProgramResponse.self, #"{"start": "2026-11-09", "days": [{"date": "2026-11-09", "items": []}]}"#)
        XCTAssertFalse(empty.hasProgram)
    }

    // MARK: Loads

    func testPoundsAreForTheEyeAndKilogramsAreSent() {
        XCTAssertEqual(LoadUnit(wire: nil), .kg)
        XCTAssertEqual(LoadUnit(wire: "stone"), .kg)
        XCTAssertEqual(LoadUnit(wire: "lb"), .lb)
        XCTAssertEqual(LoadUnit.kg.text(kg: 10), "10 kg")
        XCTAssertEqual(LoadUnit.kg.text(kg: 12.5), "12.5 kg")
        // The server's own rounding (app/hep/service.py load_text): pounds
        // to a tenth.
        XCTAssertEqual(LoadUnit.lb.text(kg: 10), "22 lb")
        XCTAssertEqual(LoadUnit.lb.text(kg: 16), "35.3 lb")
        // 25 lb typed is stored as 11.34 kg and comes back as 25 lb.
        let stored = LoadUnit.lb.kilograms(from: 25)
        XCTAssertEqual(stored, 11.34, accuracy: 0.0001)
        XCTAssertEqual(LoadUnit.lb.shown(kg: stored), 25, accuracy: 0.0001)
        XCTAssertEqual(LoadUnit.lb.text(kg: stored), "25 lb")
        XCTAssertEqual(LoadUnit.kg.kilograms(from: 12.5), 12.5)
    }

    func testWhatThePersonDidStartsFromTheDose() throws {
        let stepUps = try row(Self.reviewed)
        var counts = DoneCounts(stepUps, unit: .lb, setsCounted: 2)
        XCTAssertEqual(counts.setsDone, 2)
        XCTAssertEqual(counts.repsDone, 10)
        XCTAssertEqual(counts.load, 22)
        counts.load = 35
        XCTAssertEqual(try XCTUnwrap(counts.loadDoneKg(unit: .lb)), 15.88, accuracy: 0.0001)
        // A timed hold has no reps to count, and no load unless one is typed.
        let hold = DoneCounts(try row(Self.wallSits), unit: .kg)
        XCTAssertEqual(hold.setsDone, 3)
        XCTAssertNil(hold.repsDone)
        XCTAssertNil(hold.loadDoneKg(unit: .kg))
    }

    // MARK: What is sent

    func testTheCompletionBodyIsSnakeCaseAndLeavesOutWhatWasNotSaid() throws {
        var body = ExerciseCompletionBody()
        body.painAfter = 3
        body.note = "Felt strong."
        body.effort = 6
        body.setsDone = 3
        body.repsDone = 12
        body.loadDoneKg = 15
        body.wearableWorn = true
        body.startedAt = "2026-11-12T03:24:22-06:00"
        body.video = StagedClip(storageKey: nil, attachmentId: 1, contentType: "video/mp4",
                                byteSize: 179510, filename: "attempt.mp4")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: encoder.encode(body)) as? [String: Any])
        XCTAssertEqual(sent["pain_after"] as? Int, 3)
        XCTAssertEqual(sent["effort"] as? Int, 6)
        XCTAssertEqual(sent["sets_done"] as? Int, 3)
        XCTAssertEqual(sent["reps_done"] as? Int, 12)
        XCTAssertEqual(sent["load_done_kg"] as? Double, 15)
        XCTAssertEqual(sent["wearable_worn"] as? Bool, true)
        XCTAssertEqual(sent["started_at"] as? String, "2026-11-12T03:24:22-06:00")
        XCTAssertNil(sent["ended_at"])
        let video = try XCTUnwrap(sent["video"] as? [String: Any])
        XCTAssertEqual(video["attachment_id"] as? Int, 1)
        XCTAssertNil(video["storage_key"])
        XCTAssertEqual(video["content_type"] as? String, "video/mp4")
        XCTAssertEqual(video["byte_size"] as? Int, 179510)

        let presigned = StagedClip(storageKey: "patients/hirt-cole/abc.mp4", attachmentId: nil,
                                   contentType: "video/mp4", byteSize: 10, filename: nil)
        let key = try XCTUnwrap(JSONSerialization.jsonObject(with: encoder.encode(presigned)) as? [String: Any])
        XCTAssertEqual(key["storage_key"] as? String, "patients/hirt-cole/abc.mp4")
        XCTAssertNil(key["attachment_id"])
    }

    // MARK: Words

    func testWords() {
        XCTAssertEqual(ExerciseWords.effort(0), "Nothing")
        XCTAssertEqual(ExerciseWords.effort(7), "Very hard")
        XCTAssertEqual(ExerciseWords.effort(10), "All out")
        XCTAssertEqual(ExerciseWords.effort(42), "All out")
        XCTAssertEqual(ExerciseWords.therapist("Dr. Ashley Gregg"), "Dr. Gregg")
        XCTAssertEqual(ExerciseWords.therapist("Ashley Gregg"), "Ashley")
        XCTAssertEqual(ExerciseWords.therapist(nil), "your therapist")
        XCTAssertEqual(ExerciseWords.clock(0), "0:00")
        XCTAssertEqual(ExerciseWords.clock(252), "4:12")
        XCTAssertEqual(ExerciseWords.duration(45), "45 s")
        XCTAssertEqual(ExerciseWords.duration(780), "13 min")
        XCTAssertNil(ExerciseWords.duration(nil))
        XCTAssertEqual(ExerciseWords.dayTitle("2026-11-12", today: "2026-11-12"), "Today")
        XCTAssertEqual(ExerciseWords.weekday("2026-11-13"), "Friday")
        XCTAssertEqual(ExerciseWords.typeset("3 sets × 10 reps · 10 kg"), "3 sets × 10 reps\(MP.dot)10 kg")
    }

    // MARK: The session's stages

    @MainActor
    func testTheSessionHasOnlyTheStagesTheTherapistAskedFor() throws {
        // Clip required, watch off: no watch stage.
        let hold = SessionModel(a: try row(Self.wallSits), unit: .kg)
        XCTAssertEqual(hold.stages, [.start, .setup, .exercise, .record, .upload, .finish, .done])
        XCTAssertEqual(hold.stepCount, 6)
        // Both optional: every stage.
        let both = SessionModel(a: try row(#"{"id": 1, "status": "assigned"}"#), unit: .kg)
        XCTAssertEqual(both.stages, [.start, .watch, .setup, .exercise, .record, .upload, .finish, .done])
        // Both off: start, set up, do it, say how it went.
        let neither = SessionModel(a: try row(
            #"{"id": 1, "status": "assigned", "video_requirement": "off", "wearable_requirement": "off"}"#
        ), unit: .kg)
        XCTAssertEqual(neither.stages, [.start, .setup, .exercise, .finish, .done])

        // Skipping an optional recording goes forward to the answers, never back.
        both.advance(); both.advance(); both.advance(); both.advance()
        XCTAssertEqual(both.stage, .record)
        both.jump(to: .finish)
        XCTAssertEqual(both.stage, .finish)
        both.jump(to: .start)
        XCTAssertEqual(both.stage, .finish)
    }
}
