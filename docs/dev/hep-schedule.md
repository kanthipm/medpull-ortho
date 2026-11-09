# The exercise schedule: calendar, the therapist's clip, the patient's pain and clip

What H.I.R.T. asked for (docs/demo/hirt.md): a calendar where the therapist puts
exercises on each lifter's days, her own video of the exercise for the patient to
follow, and from the patient a pain score after doing it and a video of their
attempt. This document is the contract the backend, the console and the patient
web app are built against. The phone apps follow later.

It extends the exercise library (`backend/app/hep`): exercises (30 standard, any
custom), `ExerciseMedia` (a clip), plans with published snapshots, and
`ExerciseCompletion` for plan days. Nothing there changes meaning.

## Data

- `exercise_assignments` (`app/hep/models.py: ExerciseAssignment`): one exercise on
  one patient's day. Fields: `hospital_id`, `patient_id`, `exercise_id`,
  `plan_exercise_id` (null for calendar entries), `scheduled_for` (date),
  `sort_order`, dose (`sets`, `reps`, `hold_seconds`, `side`), `clinician_instructions`
  (patient-facing), `assigned_by` (care team id), `status` = `assigned | done | skipped`,
  and what came back: `completed_at`, `pain_after` (0–10), `note`, `completion_source`
  (`app | console`), `video_attachment_id` (an `attachments` row on the patient's
  thread), `skip_reason`. Unique per (patient, exercise, day).
- `exercise_media.exercise_id` (new, nullable): a clinic's own demonstration of that
  exercise. Resolution for any exercise shown to a clinic or its patients:
  **the clinic's latest approved clip for that exercise, else the library clip
  (`Exercise.media_id`), else none.** A clinic upload is approved on creation
  (the therapist is the reviewer), `uploaded_by` = her care-team id.
- Clinic clips are stored at `attachments/clinic/<hospital_id>/<random>.<ext>`
  (`blobs.new_clinic_key`, `blobs.owned_by_clinic`), so the bucket policy, CORS and
  lifecycle for attachments apply unchanged. Patient return clips are ordinary
  patient attachments (`attachments/<patient_id>/…`).

## Payloads

**Assignment** (the one shape both clients read; the patient routes drop
`clinic_id` and `patient_id` is still present):

```json
{
  "id": 12, "clinic_id": "hirt", "patient_id": "hirt-cole",
  "exercise_id": 18, "exercise_key": "functional_step_ups", "title": "Step-Ups",
  "body_region": "full_body", "body_region_label": "Full body",
  "category": "functional", "category_label": "Functional",
  "steps": ["Stand facing a step…", "…"], "equipment": "A step", "precautions": "…",
  "scheduled_for": "2026-11-09", "sort_order": 0,
  "sets": 3, "reps": 10, "hold_seconds": null, "side": "left", "side_label": "Left",
  "dose": "3 sets × 10 reps · Left",
  "clinician_instructions": "Slow on the way down.",
  "assigned_by": "ct_gregg", "assigned_by_name": "Dr. Ashley Gregg",
  "status": "assigned",
  "video": { "id": 3, "kind": "video", "source": "clinic", "url": "https://…", "poster_url": null,
             "content_type": "video/mp4", "duration_ms": null, "uploaded_by": "ct_gregg",
             "uploaded_by_name": "Dr. Ashley Gregg", "created_at": "…" },
  "completion": null,
  "skip_reason": null,
  "created_at": "…", "updated_at": "…"
}
```

`video` is null when neither the clinic nor the library has a clip; `source` is
`clinic` or `library`. `dose` is built like `plans.dose_line` without the
frequency. When `status` is `done`:

```json
"completion": { "completed_at": "2026-11-08T19:12:00", "pain_after": 4, "note": "Left knee ached on the last set",
                "source": "app",
                "video": { "id": 77, "content_type": "video/quicktime", "byte_size": 8123456, "kind": "video",
                           "filename": "step-ups.mov", "url": "https://…", "created_at": "…" } }
```

(`completion.video` is the attachment view from `app/api/attachments.py: _view`
with its URL; null when none was sent.)

**Exercise** (`service.exercise_payload`) gains `"clinic_media"`: the clinic's own
clip payload (same shape as `media`, plus `source: "clinic"`), or null. `media`
stays the library clip. Every exercise list and read on the console passes the
clinic so this is filled.

## Console routes (`/api/hep`, behind the console credential; `clinic` from `_clinic`)

- `GET /hep/schedule?start=YYYY-MM-DD&days=7&today=YYYY-MM-DD[&patient_id=]`
  → `{ "start", "days": ["…"×days], "today", "patients": [ { "id", "name", "initials",
  "pathway", "assigned_provider_id", "assigned_provider_name", "risk_tier",
  "assignments": [Assignment…] } ], "care_team": [ {"id","name","role"} ] }`.
  Patients: the clinic's clinic charts (`is_clinic`), by name; `pathway` is
  `care_pathway` or `procedure_display`; `risk_tier` from the newest risk assessment
  (lower-case, or null). `care_team`: the members who are assigned providers of
  those patients, plus the HIRT two when the clinic is `hirt` — in practice "the
  clinic's therapists". `start` defaults to the Monday of `today`'s week; `today`
  defaults to the server date. `days` 1–28.
- `POST /hep/schedule` `{ "patient_id", "exercise_id", "dates": ["YYYY-MM-DD", …],
  "sets", "reps", "hold_seconds", "side", "clinician_instructions", "assigned_by" }`
  → 201 `{ "assignments": [Assignment…] }`. Patient must be the clinic's
  (`plans.clinic_patient`), exercise visible to the clinic (`service.visible_to`),
  dates within −60…+90 days of today, 1–31 dates, side in `SIDES`, counts via
  `plans._count`, `assigned_by` a care-team id (default the patient's assigned
  provider). A date that already has that exercise → 409 naming the date. Audit
  `assignment.create`.
- `PATCH /hep/schedule/{id}` any of `sets, reps, hold_seconds, side,
  clinician_instructions, scheduled_for, assigned_by, sort_order` → Assignment.
  Moving or re-dosing a `done` row → 409. Audit `assignment.update`.
- `DELETE /hep/schedule/{id}` → `{ "ok": true }`; a `done` row → 409 (the record
  stays). Audit `assignment.delete`.
- `POST /hep/schedule/{id}/complete` `{ "pain_after", "note", "actor" }` → Assignment
  with `completion_source: "console"` (the therapist logging it from the room).
- `GET /hep/patients/{patient_id}/schedule?start&days&today` → `{ "patient": {…as
  above…}, "days", "today", "assignments" }` for the patient page.
- Media (the therapist's clip):
  - `GET /hep/exercises/{exercise_id}/media/upload-ticket?content_type&byte_size` →
    the attachments ticket shape `{ "storage_key", "direct", "max_bytes",
    "upload": {"url","fields","expires_in"} | null }` for a clinic key
    (`blobs.new_clinic_key`). Video types only (`blobs.kind_of` = video, or image).
  - `POST /hep/exercises/{exercise_id}/media` `{ "storage_key", "content_type",
    "byte_size", "filename", "actor" }` → confirm like `attachments._confirm`
    (owned by the clinic, stat, size, sniff; refuse and delete on failure) →
    `ExerciseMedia(hospital_id=clinic, exercise_id, kind, storage_key, content_type,
    size_bytes, approval_status="approved", reviewed_by=actor, reviewed_at=now,
    uploaded_by=actor)` → 201 `{ "exercise": Exercise payload with clinic_media }`.
  - `POST /hep/exercises/{exercise_id}/media/direct` (raw body, `Content-Type`
    header, `?filename=&actor=`): the laptop / test path, like
    `attachments.console_upload_direct`.
  - `DELETE /hep/exercises/{exercise_id}/media/{media_id}` → `{ "ok": true }`
    (blob and row; another clinic's → 404).
  - `GET /hep/media/{media_id}/raw` streams a clip when there is no object store
    (laptop, tests); `service.media_url` returns this path when
    `blobs.download_url` gives none. Both media payload URLs follow that rule.

## Patient routes (`/api/mobile/exercises`, dependency `app.api.mobile.current_patient`)

- `GET /mobile/exercises?date=YYYY-MM-DD` (default: server date) → `{ "date",
  "items": [Assignment…] for that day (by sort_order, id), "overdue": [Assignment…]
  still `assigned` from the seven days before it, "week": [ { "date",
  "assigned", "done", "skipped" } for date−3…date+3 ], "clinic": { "id", "name" } }`.
  The demo screen posts `{ type: "medpull:exercises-changed" }` into the phone
  frame (same origin) after every schedule change; the app re-reads the day. Videos
  carry playable URLs (presigned on AWS; `/api/mobile/exercises/media/{id}/raw` on
  the laptop, which streams under the patient's session).
- `POST /mobile/exercises/{assignment_id}/complete` `{ "pain_after": 0–10 | null,
  "note": "", "video": { "storage_key", "content_type", "byte_size", "filename" } | null }`
  → `{ "assignment": Assignment }`. Only the patient's own row; `done` already →
  409. The video key comes from the existing patient ticket
  `GET /api/mobile/attachments/upload-ticket` + S3 POST (or the direct path), and
  is confirmed exactly as `attachments._confirm` does (owned by this patient,
  stat/size/sniff), as an `Attachment(uploaded_by="patient", source="app")`.
  Then one thread `Message` from the patient (sender "patient", channel "app"):
  `"Did <title> · pain <n>/10 after"` plus the note on a new line, with the
  attachment linked (`Attachment.message_id`), so the chart's thread shows the
  clip beside the score. `completion_source: "app"`.
- `POST /mobile/exercises/{assignment_id}/skip` `{ "reason": "" }` → Assignment with
  `status: "skipped"`, `skip_reason`.

## Demo session (`/api/demo`, demo stacks only)

- `POST /demo/patient-session` `{ "patient_id" }`, behind the console credential →
  `{ "token", "patient": {"id","name"} }`. 404 unless `settings.demo_mode`; the patient
  must be within the console's scope (`scope.require_patient`) and a clinic chart.
  Issues a `PatientSession` (`mobile._issue_session`, device_name "demo screen").
- The patient web app accepts `/patient/#session=<token>` on boot: store it as the
  session token, strip the hash, act signed in (`appModel.bootstrap`).

## Console UI (`frontend/`)

- `Exercises` nav → `/exercise-schedule` (new first tab "Schedule" in
  `features/hep/ExercisesNav.tsx`; Plans and Library stay). Page width class for
  `/exercise-schedule` is `wide`.
- `SchedulePage`: week header (← Today →, the dates), a grid with one row per
  patient (initials tile, name, pathway, tier chip) and one column per day, today
  marked. A cell lists its assignments as chips: title + dose; `done` shows a check
  and `pain n` badge (pain ≥ 5 in the warning tone), `skipped` muted, a film badge
  when a video exists. Empty cell: a `+` affordance. Clicking `+` opens
  `AssignDialog`: exercise picker (search + region/category filters, reusing the
  plan editor's `LibraryPicker`, extracted to its own file), dose fields, side,
  note to the patient, assigned by (care_team select, default the row's provider),
  "also on" checkboxes for the other days of the week, Save → `POST /hep/schedule`.
  Clicking a chip opens `AssignmentDialog`: the clip (video player, or "No
  demonstration yet" with an **Upload your demonstration** button), steps,
  precautions, dose editor (PATCH), "Move to…" day, Remove (DELETE), and when done
  the completion: when, pain, note, the patient's clip (player). A "Log it done"
  button (console completion) for the room.
- `ClinicClipUpload` (used in AssignmentDialog and in the library's
  `ExercisePreviewModal`): file input `accept="video/mp4,video/quicktime"` with
  `capture="user"` (opens the camera on a phone), ticket → S3 POST (or `/direct`
  when the ticket says so) → confirm; progress and a clear error. After upload the
  exercise shows "Your demonstration" and the clip plays everywhere it is assigned.
- `PatientDetailPage`: an "Exercises this week" strip (the patient's assignments
  for the current week with status and pain) above Kanthi's plan card; links to the
  schedule.
- `DemoScreenPage` at `/demo/hirt`, rendered only when `useHealth().data?.demo` is
  true (otherwise a one-line "This screen is for the demo stack"). Full-bleed layout
  outside the normal content column: left ≈ 2/3 the `SchedulePage` content; right
  ≈ 1/3 a phone frame (390×844 points, rounded bezel, scaled to fit the viewport
  height) holding `<iframe src="/patient/#session=…">`. Above the phone a lifter
  selector; choosing one calls `POST /api/demo/patient-session` and reloads the
  iframe with the token. A small "Open the demo screen" link on the Schedule page
  header, demo stacks only.

## Patient web UI (`patient-web/`)

- Boot: read `#session=` as above.
- Today tab: a **Today's exercises** section (above "Today's plan") listing the day's
  assignments as rows: title, dose, the therapist's note, a film badge when there is
  a clip, status. Tapping opens `/today/exercises/:id`: the clip (inline `<video
  controls playsInline>` with poster), steps, precautions, dose, note, then **Mark
  done** → a sheet: pain after (0–10 scale, reuse `ScaleAnswer` from `TasksView`),
  optional note, **Record a clip of you doing it** (`<input type="file"
  accept="video/mp4,video/quicktime" capture="environment">`, uploaded through the
  existing `core/attachments.ts` uploader → `storage_key`), Send → `POST
  /mobile/exercises/{id}/complete`. Done state: "Sent to Dr. Gregg · pain 4/10". A
  "Can't do it today" link → skip with a reason.
- The exercises feed refreshes with `refreshAll` and polls every 10 s while the
  Today tab is visible, so a therapist's assignment appears on the phone during the
  demo without a reload.
- `core/models.ts` gets the Assignment type (camelCased by the client's `camelize`).

## Seed (`backend/app/seed/hirt.py`, carried by `demo_fill` / `push_demo_fill.py`)

Each lifter gets a schedule from program day 0 through today + 7, in catalog
exercises that fit the pathway, three or four per training day, assigned by their
therapist, with outcomes that match the fourteen-day check-in story:

- `hirt-cole` (patellar tendinopathy, Dr. Gregg): Step-Ups, Wall Sits, Mini Squats,
  Terminal Knee Extensions on Mon/Wed/Fri, Heel Slides daily. Done through
  yesterday with pain climbing 2 → 4 → 6 over the last week (today's rows open).
- `hirt-tessa` (Achilles, Dr. Gregg): Calf Raises, Ankle Dorsiflexion Stretch daily,
  Single-Leg Stance three days a week. All done, pain ≤ 2.
- `hirt-devon` (low back, Dr. Harris): Bird Dog, Glute Bridges, Pelvic Tilts, Cat-Cow
  daily. About a sixth done, most rows left `assigned` (missed), two `skipped`
  ("long shift").
- `hirt-june` (lumbar disc, Dr. Harris): Pelvic Tilts, Bird Dog, Glute Bridges,
  Sit-to-Stand daily. All done, pain 1–2.
- `hirt-rafael` (shoulder, Dr. Gregg): Pendulum Swings, Wall Slides, Band External
  Rotation, Scapular Retractions daily. Done until three days ago, nothing since
  (the went-quiet story).

Seed completions carry no video (bytes need an object store); the media script
below adds clips. `write_schedule(db, patient_id, today)` sits beside
`write_history` and is called wherever it is. Nothing is pushed to any stack by the
seed itself.

## Placeholder clips (`backend/scripts/seed_hirt_media.py`)

`--local <db>` or `--bucket <demo data bucket>` (the S3 lock, hydrate, persist, as
`scripts/admin_db.py` does). Makes short silent MP4 title cards with ffmpeg (720×1280,
6 s, the sage `#3f6b5a` background, white text "Dr. Ashley Gregg · <exercise> ·
demonstration") for every exercise HIRT's schedule uses, stores them with
`blobs.put` under clinic keys and writes approved `ExerciseMedia` rows for `hirt`;
and two or three patient return clips ("Cole Whitaker · Step-Ups · day 12") as
attachments linked to done assignments and their thread messages. Idempotent (skips
exercises that already have a clinic clip). Real footage replaces these through
the upload button.

## Out of scope now

The iPhone and Android apps (they keep showing plans and tasks; the schedule
reaches them in a later pass), reminders for an assigned day, and any change to the
risk engine (the schedule's completions do not feed the tier yet).

---

## Second pass (2026-11-08): the whole pipeline, the way a PT would run it

What the first demo showed and what H.I.R.T. asked for next: the patient sees
their whole program by day, starts an exercise as a session (wearable on, if
she asks for it), films it when she asks for it, reports how it felt, and all
of it lands in front of her with a place to answer. Requirements are hers to
set per exercise. The foundation (columns, the templates table) is already on
main; the three surfaces build the rest against this section.

### Data (already in `app/hep/models.py`)

- `ExerciseAssignment` gains the lifter's dose `load_kg` and `rpe_target`; the
  therapist's `video_requirement` and `wearable_requirement`, each
  `off | optional | required` (`REQUIREMENTS`, default `optional`); the session
  `started_at`, `ended_at`, `duration_s`, `pain_before`, `wearable_worn`,
  `hr_avg`, `hr_max`; the completion's `effort` (RPE 0–10), `sets_done`,
  `reps_done`, `load_done_kg`; and the review `reviewed_at`, `reviewed_by`,
  `review_note`.
- `exercise_templates` (`ExerciseTemplate`): a clinic's program — `name`,
  `description`, `weeks`, `items` JSON (each item is an assignment's fields with
  `weekdays` `[0..6]` or null for every day, plus `exercise_key` or
  `exercise_id`).

### Payload additions

**Assignment** gains `load_kg`, `rpe_target`, `video_requirement`,
`wearable_requirement`, `dose` now ending with the load when set ("3 sets × 10
reps · 12 kg · Left"), and `session: { "started_at", "ended_at", "duration_s",
"pain_before", "wearable_worn", "hr_avg", "hr_max" } | null` (null until the
patient starts it). **Completion** gains `effort`, `sets_done`, `reps_done`,
`load_done_kg`, `review: { "at", "by", "by_name", "note" } | null`. A done row
with a clip and no review is "awaiting review".

**Schedule patient row** gains `adherence: { "assigned", "done", "skipped",
"missed", "pct" }` for the seven days ending today and `load_week: { "this",
"last", "change_pct" }` (sum of `load_done_kg × reps_done`, else `load_kg ×
reps × sets` of done rows), and `awaiting_review` (count).

### Console routes (`/api/hep`, clinic from `_clinic`)

- `POST /hep/schedule` and `PATCH /hep/schedule/{id}` accept `load_kg`,
  `rpe_target`, `video_requirement`, `wearable_requirement` (validated against
  `REQUIREMENTS`; load 0–500, RPE 0–10).
- `POST /hep/schedule/{id}/review` `{ "note", "actor" }` → Assignment. Sets the
  review fields and, when `note` is not empty, writes one thread `Message` from
  the care team (`sender "care_team"`, `sender_id` = actor) "About your <title>
  clip: <note>", so the patient reads it in Care. Reviewing an open row → 409.
- `GET /hep/review?days=14` → `{ "items": [Assignment…] }`: done rows of the
  clinic with a clip and no review, newest completion first, each carrying
  `patient_name`.
- `POST /hep/schedule/copy-week` `{ "patient_id", "from_start", "to_start",
  "assigned_by" }` → `{ "assignments": [...] }`: every assignment of the seven
  days from `from_start` copied to the same weekday from `to_start`, dose,
  note and requirements included, skipping days that already have that
  exercise; 201.
- Templates: `GET /hep/templates` → `{ "templates": [...] }` (the clinic's, not
  archived), `POST /hep/templates` `{ name, description, weeks, items }` → 201,
  `PUT /hep/templates/{id}`, `DELETE /hep/templates/{id}` (archives),
  `POST /hep/templates/{id}/apply` `{ "patient_id", "start", "weeks"?,
  "assigned_by" }` → `{ "assignments": [...] }` (every item on its weekdays from
  `start` for `weeks` weeks, duplicates skipped). Template payload: `{ id,
  clinic_id, name, description, weeks, items: [ { exercise_id, exercise_key,
  title, weekdays, sets, reps, hold_seconds, side, load_kg, rpe_target,
  clinician_instructions, video_requirement, wearable_requirement } ],
  created_by, created_at, updated_at }`.
- Worklist: `/api/worklist` patient rows gain `exercises: { "assigned", "done",
  "pct", "awaiting_review" } | null` for the seven days ending today (null when
  the patient has no assignments in that window).

### Patient routes (`/api/mobile/exercises`)

- `GET /mobile/exercises/program?start=YYYY-MM-DD&days=14` → `{ "start",
  "days": [ { "date", "items": [Assignment…], "assigned", "done", "skipped",
  "missed" } ], "clinic" }` — the calendar. `missed` = assigned and before
  today. Default start = today − 7, days 14 (1–35).
- `POST /mobile/exercises/{id}/start` `{ "pain_before": 0–10 | null,
  "wearable_worn": bool | null }` → `{ "assignment" }` with `session.started_at`
  set (restarting an open row moves `started_at`; a done row → 409).
- `POST /mobile/exercises/{id}/complete` body as before plus `effort`,
  `sets_done`, `reps_done`, `load_done_kg`, `wearable_worn`, `started_at`,
  `ended_at` (ISO, optional; the server keeps its own `started_at` if the
  phone sends none). Enforcement: `video_requirement == "required"` and no
  clip → 422 "This exercise needs a clip of your attempt"; `wearable_requirement
  == "required"` and `wearable_worn` is not true → 422 "This exercise is done
  with your wearable on". `duration_s` = ended − started when both are known.
  `hr_avg`/`hr_max` from `Observation` rows of `MetricType.HR_SAMPLE` for the
  patient inside the window, when any. The thread line becomes "Did <title> ·
  pain <n>/10 after · effort <e>/10" with the note on a new line.
- `GET /mobile/exercises?date=` unchanged (plus the fields above on each item).

### Console UI

- **Assign and assignment dialogs**: load (kg) and target RPE beside sets/reps;
  two segmented controls, "Clip of their attempt" and "Wearable on", each
  off / optional / required; the completion section shows duration, pain before
  → after, effort, sets × reps × load done, wearable worn with HR avg/max when
  present; when her clip and theirs both exist, **Compare** shows them side by
  side; a **Reply** box posts the review (and marks it reviewed), with "Mark
  reviewed" alone for no note.
- **Grid**: a small amber dot on chips awaiting review; each patient row header
  carries the adherence chip "3 of 4 · 75%" (amber under 60%, red under 30%) and
  the load trend when there is one ("load +12%"); a row menu with "Copy last week
  →" and "Apply a program…".
- **Review** (`/exercise-review`, a new tab in the exercises sub-nav with a count):
  the queue, newest first; a row opens the assignment dialog.
- **Programs** (`/exercise-programs`, a sub-nav tab): the clinic's templates;
  create / edit (the library picker, weekdays, dose, requirements per item) and
  "Apply to…" (patient, start date, weeks).
- **Worklist card**: the adherence chip for patients with `exercises`.
- **Demo screen**: unchanged; the board carries the new chips.

### Patient web UI

- **Program** at `/today/program` (a link "See the week" on the exercises card
  and a row under it): a strip of the 14 days (dots: assigned, done, missed,
  today ringed), the chosen day's list below, past days read-only with the
  outcome, future days as a preview. Today is the default.
- **Start the exercise**: the exercise screen's primary button becomes **Start**
  (Mark done stays as a secondary "Just mark it done" for an exercise done away
  from the phone). Start → the session screen: pain right now (0–10, skippable
  unless the therapist set nothing — always shown, one tap), the wearable line
  ("Wear your watch for this one" with a confirmation switch; required → the
  session cannot begin without it; optional → a gentle line; off → nothing), then
  the running session: her clip looping muted, the dose, a timer, a set counter
  ("Set 2 of 3 · Next set"), rest between sets when `hold_seconds` is not the
  unit. **Finish** → the completion sheet: pain after, effort (0–10 with the
  words "easy … all out"), sets/reps/load done prefilled from the dose, note,
  the clip (`required` → Send disabled until a clip is attached, with the words
  why; `optional` → as today; `off` → no clip control), Send. The app sends
  `started_at`/`ended_at` from its own clock.
- **Done state** shows duration and effort beside pain; a review from the
  therapist shows under it ("Dr. Gregg: …") and in Care.

### Seed (`app/seed/hirt.py`)

Requirements and loads on the lifters' rows: Cole's Step-Ups and Wall Sits
`video_requirement: required`, `load_kg` 10 and none, `rpe_target` 7; Tessa's
Calf Raises `wearable_requirement: required`; Devon and June `optional` across;
Rafael's band work `off` for the wearable. Done rows carry `started_at`/`ended_at`
(8–14 minutes), `effort` tracking the pain story (Cole 5 → 8), `pain_before` one
below `pain_after`, `sets_done`/`reps_done` equal to the dose; two of Cole's and
one of June's reviewed with a note from their therapist (and the matching thread
line). Two templates for `hirt`: "Patellar tendinopathy · phase 2" (Cole's
pattern) and "Lumbar · return to lifting" (June's). `EXPECTED_SCHEDULE` stays
true.

### Out of scope here

Texted reminders at a time of day (a daily job and a per-patient setting; the
real stack only), feeding assignment adherence into the risk tier (the check-in's
program answer still does that), and the phone apps.

