# Between visits (`backend/app/pt`)

What a physical-therapy clinic keeps about a person on its own program
beyond the exercise calendar. Built 2026-11-12 for the H.I.R.T. pilot, from
the feature list in that day's session. Sixteen features, one module.

## Rules that hold across all of it

- **Nothing authors a dose or moves a phase.** A therapist clicks; the
  software records. A phase with unticked criteria has to be moved twice
  (`with_unmet`).
- **Nothing is written by a model.** Sorting a question is a word list a
  clinician edits. A red-flag reply is the clinic's own text once a named
  clinician has approved it, and one fixed line until then.
- **Nothing says what a number means.** A test shows left beside right as a
  ratio. An outcome measure shows the change beside a published threshold
  and the threshold's source. No "cleared", no "ready", no risk band.
- **Everything a person is asked is a task** (`app/tasks`) that carries its
  own questions, so the iPhone app, the Android app, the browser app and a
  text conversation all ask it with no change to any of them.
- **A trainer's page exists only once the person agrees**, and holds limits
  and doses: nothing from the record.

## The sixteen, and where each lives

| # | Feature | Server | Console | Person |
| --- | --- | --- | --- | --- |
| 1 | New pain by body area | `PainArea`, `regions.py`; a check-in "new pain: yes" is followed by the ask `pt_new_area` (`intake.after_checkin`); `engine/reported._new_area` names an area not among the evaluation's; `risk.score_reported` words it and adds `NEW_AREA_SCORE` | Chart → Program → areas | task |
| 2 | Next-morning check | `MorningCheck`; ask `pt_morning`; settled = pain at or under the ceiling and not stiffer; the clinic's default and each person's own in `settings.py` | Chart → Program; Week review | task |
| 3 | Function line | `FunctionGoal`, `FunctionRating`; asks `pt_goals`, `pt_function`; the average is the PSFS score | Chart → Program → Function | task; `GET /api/mobile/pt` |
| 4 | Dose with a ceiling | `ExerciseAssignment.load_max_kg`, `.rpe_max`; `schedule.check_ceilings`; a done day past either is `over` and `past_ceiling` | Assign dialog, day dialog | exercise screen and session |
| 5 | Friday next-week check-in | `WeekCheckin`; ask `pt_week` | Week review; chart | task |
| 6 | Question triage | `Message.triage` (`today` / `weekly`), `triage.py`; the word list in the clinic's settings | Calendar → Questions | none: nothing is sent |
| 7 | Red-flag wording | `RedFlagText`; `triage.on_patient_line`; `STANDING_REPLY` until a clinician approves the clinic's own text | Calendar → Rules | the reply on their thread |
| 8 | Phases with gates | `Protocol`, `PatientPhase`; `service.advance_phase` | Chart → Program; Rules → Protocols | `GET /api/mobile/pt` `phase` |
| 9 | Test-day card | `Measurement` (table `pt_test_results`), `measures.py` | Chart → Program → Tests | none |
| 10 | Trainer handoff | `Handoff`; ask `pt_handoff`; page `GET /api/handoff/{token}`, console route `/h/:token` | Chart → Program → Trainer | task |
| 11 | Faster clip review | `ClipComment`; a voice note goes to the thread at once, typed comments ride the review note | Day dialog on a done day with a clip | the note; the voice line |
| 12 | Flag rules page | `settings.FLAG_RULES`, `FlagEvent`; thresholds threaded into `score_reported` | Calendar → Rules | none |
| 13 | Outcome measures | `OutcomeSchedule`, `OutcomeScore`, `instruments.py`; ask `pt_outcome` | Chart → Program → Tests | task |
| 14 | Clinic visits | `ClinicVisit`; on every calendar payload as `visits` | Schedule grid; chart | Today, program |
| 15 | Bulk assign, rest days, exercise count | `patient_ids` and `allow_over_guard` on `POST /api/hep/schedule`; `POST /api/hep/schedule/check`; `CalendarMark` | Assign dialog; grid | Today, program |
| 16 | Timed holds at home | ask `pt_hold` → `Measurement` with `source: "patient"` | Chart → Program → Tests | task |

## What the phone gets (additions only)

The App Store app talks to this server, so everything here is an added
field or an added route. Nothing that existed changed shape.

**An assignment** (every `/api/mobile/exercises*` row, and the console's):

```
"load_max_kg": 13.61 | null,     // kilograms, like load_kg
"rpe_max": 8 | null,
"ceiling": "Stop at RPE 8 · do not exceed 30 lb" | "",   // worded in the clinic's unit
"completion": { ..., "past_ceiling": true | false }
```

Show `ceiling` on the exercise screen and through the session (while the
person is working, where the dose is). It is the therapist's limit, in her
words: no styling that reads as an error, and nothing when it is empty.

**`GET /api/mobile/exercises`** (today's feed) adds:

```
"rest_day": {"note": "Deload."} | null,     // today is a rest day set on purpose
"next_visit": {"on": "2026-11-14", "at": "09:30" | null,
               "kind": "visit" | "evaluation" | "test_day", "kind_label": "Test day"} | null
```

**`GET /api/mobile/exercises/program`** adds, for its window:

```
"visits": [{"on", "at", "kind", "kind_label"}],
"rest_days": [{"day": "2026-11-15", "note": ""}]
```

**`GET /api/mobile/pt`** (new; the person's own read):

```
{
  "next_visit": {...} | null,
  "rest_day": {"note"} | null,
  "phase": {"name": "Isotonic loading", "goal": "Build strength through range, slowly.",
            "number": 2, "count": 4} | null,
  "goals": [{"id", "text", "first": 4 | null, "latest": 4 | null,
             "ratings": [{"on": "2026-10-29", "score": 4, "source": "clinic" | "patient"}]}],
  "handoff": {"trainer_name": "Mara Ellis", "status": "awaiting" | "active"} | null
}
```

A subscriber's or an athlete's space answers the same shape, empty.

**Asks** arrive in `GET /api/mobile/tasks` like any task, kind `custom`,
with their own `questions` (the kinds the apps already render: `scale`,
`yes_no`, `choice`, `number`, `text`). Nothing to build.

## The console's routes (`/api/pt`, behind the console's door)

Clinic-level routes act for the clinic the console acts for (the calendar's
rule: `X-MedPull-Clinic`, else the chart named). A chart's routes answer 404
for a chart the console cannot see. Every chart mutation answers with the
whole chart bundle (`GET /api/pt/patients/{id}`), plus `sent` where it asked
the person something: `{"sent": bool, "detail": str, "reused": bool}`.

```
GET   /catalog                         areas, tests, instruments, visit kinds, care team
GET   /settings        PATCH /settings flags, exercise_guard, triage_words, morning_check,
                                       week_checkin, outcome_thresholds
GET   /flags                           each flag: rule, inputs, thresholds, how often it fired
GET   /red-flags   POST   PATCH /{id}  POST /{id}/approve {by, approved}   DELETE /{id}
GET   /protocols   POST   PUT /{id}    DELETE /{id}
GET   /questions?days=14               {today, weekly, done, words}
POST  /questions/{message_id}          {triage: today|weekly|none, done, by}

GET   /patients/{id}                   the chart bundle
PATCH /patients/{id}/settings          {morning_check, week_checkin}  (null: back to the clinic's)
POST  /patients/{id}/areas             {area, side, source, note}
POST  /patients/{id}/areas/{aid}/seen  DELETE /patients/{id}/areas/{aid}
POST  /patients/{id}/morning/ask       {session_day?, text}
POST  /patients/{id}/goals             {text}          DELETE .../goals/{gid}
POST  /patients/{id}/goals/ask         POST .../goals/ask-rating
POST  /patients/{id}/goals/rate        {scores: {goal_id: 0..10}, on?}
POST  /patients/{id}/week/ask
PUT   /patients/{id}/phases            {protocol_id} | {name, phases}
POST  /patients/{id}/phases/{pid}/criteria/{index}   {by, met}
POST  /patients/{id}/phases/advance    {by, with_unmet}   409 names the unticked criteria
POST  /patients/{id}/phases/back       {by}
POST  /patients/{id}/tests             {kind, side, value, tested_on?, label?, unit?, note?}
DELETE /patients/{id}/tests/{mid}      POST .../tests/ask-hold {kind}
PUT   /patients/{id}/outcomes/{instrument}/schedule {every_days, start?}   DELETE (stop)
POST  /patients/{id}/outcomes/{instrument}/scores   {total, on?}
POST  /patients/{id}/outcomes/{instrument}/ask
PUT   /patients/{id}/handoff           {trainer_name, limits[], report_back, include_week}
POST  /patients/{id}/handoff/request   POST .../handoff/revoke
POST  /patients/{id}/visits            {on, at?, kind, note?}     DELETE /visits/{vid}
POST  /patients/{id}/marks             {day, kind: "rest", note?} DELETE /marks/{mid}
GET   /assignments/{aid}/clip          {comments, earlier}
POST  /assignments/{aid}/comments      {by, at_ms?, text?, voice_attachment_id?}
DELETE /comments/{cid}
```

Public, no credential: `GET /api/handoff/{token}` (the trainer's page data).

On the calendar (`/api/hep`): every schedule, calendar, week and
patient-strip payload carries `visits` and `marks` for its window; each
entry of `GET /api/hep/week` carries `between_visits`
(`week_checkin`, `mornings`, `next_visit`, `phase`);
`POST /api/hep/schedule` takes `load_max_kg`, `rpe_max`, `patient_ids`,
`allow_over_guard` and answers 409 with a sentence when a day would pass
the clinic's exercise count; `POST /api/hep/schedule/check` says which days
would, without writing.

## What goes out by itself

Nothing, unless the deployment has the morning text on
(`EXERCISE_REMINDERS=true`): the same hourly run then also calls
`pt.service.run_daily`, which asks the morning-after check of anyone who
did a loaded exercise yesterday, the Friday word on the week, and any
outcome measure that has come due, for people whose settings say so. Each
is asked once. Every one of these can be asked by hand from the chart.

## Outcome-measure thresholds, and where they come from

`app/pt/instruments.py`. A clinic can set its own for any instrument; the
page then says "the clinic's own".

| Instrument | Threshold | Source |
| --- | --- | --- |
| NPRS | 2 points | Ostelo et al., Spine 2008 (consensus); Childs et al., Spine 2005 |
| PSFS | 2 points on the average (3 on one activity) | Stratford et al., Physiotherapy Canada 1995 |
| VISA-P | 13 points | Hernandez-Sanchez et al., Br J Sports Med 2014 |
| VISA-A | 14 points at 12 weeks (7 at 24) | Lagas et al., JOSPT 2021 (midportion) |
| ODI | 10 points | Ostelo et al., Spine 2008 (consensus) |
| LEFS | 9 points | Binkley et al., Phys Ther 1999 |
| QuickDASH, ACL-RSI | none set | published values vary; the clinic sets its own |

NPRS and PSFS are asked in the app. The others are published
questionnaires whose wording is not reproduced here (ODI is licensed): the
clinic gives its own copy and the total is entered.

## Demo data

`app/seed/hirt_between.py` gives the five lifters a record that follows
their existing stories and adds no check-in, so the pitched tiers do not
move. The two protocols and the trainer ("Mara Ellis") are examples and are
named as examples where a clinician reads them. The red-flag entries start
as drafts with a blank the clinic must fill.

## Tests

`backend/tests/test_pt.py`: one test per feature group, through the routes.
