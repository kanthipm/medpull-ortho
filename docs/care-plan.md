# Care plan: library, builder, verification, messages, next steps

Backend package `backend/app/plan/`, router `backend/app/api/plan.py`, tables in
`backend/app/models/library.py`. Everything here sits on top of the patient-app
session's task and message models: a plan item becomes one of their
`AdherenceTask` rows through their `create_task`, and the plan's own semantics
live under `task.payload["care"]`.

## Library (`app/plan/library.py`)

71 `TaskTemplate`s keyed by use case: UC1–UC7 transcribe the orthopedic task
library row for row (TKA, THA, ACL, shoulder, spine, fracture, cross-cutting);
UC8–UC12 add heart failure, COPD, diabetes, hypertension and chronic pain.
Each carries a patient-facing `title`/`why` (plain, warm, no metric values), a
provider-facing `clinical_target`, a `verify_kind` (`app/plan/verify_kinds.py`,
28 kinds with a params schema and a "verified by" label), the patient-app
`task_kind` it is created as, the metrics it `feeds`, and the `pathways` (keys
or domains; `[]` = all) it applies to. Seven are pinned as quick-invoke chips.

`ensure_library(db)` upserts by key — wording follows the code, a clinician's
`pinned`/`archived`/`usage_count` survive. It runs once per process from the
router's `_library_ready` dependency (and from the worklist), not at startup.

```
GET  /api/task-templates?pathway=ortho_tka&q=walk&include_archived=false
POST /api/task-templates            PATCH /api/task-templates/{id}
```

## Builder (`app/plan/builder.py`)

`POST /api/task-builder/draft {text, patient_id?, pathway?}` turns a clinician's
free text into plan items. With an LLM configured the prompt is pathway-aware
(vocabulary + the pathway's library + first name, day in program, reasons, top
findings; phone numbers and emails are stripped from the text). Validation
coerces — unknown params dropped, enums defaulted, lengths clamped, a
diagnostic-language task dropped — and only a total contract failure counts a
strike. The deterministic fallback is a keyword matcher over the library
(counts parsed: "three short walks" → `bouts: 3`, "morning and evening" →
`times: 2`, "by next week" → `due_at`), with "no …/avoid …" clauses kept as
precautions in the clinician's words.

`POST /api/patients/{id}/plan/suggest` picks 3–5 library tasks from the
patient's phase, reason codes and headline findings (rule table fallback).

## Assigning and reading the plan (`app/plan/service.py`)

`POST /api/patients/{id}/plan {items, notify}` creates each item through their
`create_task(notify=False)`, stores `payload["care"]` (`template_key`,
`verify: {kind, params}`, `feeds`, `phase`, `schedule`, `clinical_target`,
`pathway`, `assigned_by`, `assigned_on`), sets `verified_by`, bumps template
usage, and — when `notify` and the patient has a phone — sends ONE summary text
(`plan_text`, ≤ 900 chars) and writes ONE `Message(sender="copilot",
channel="sms")`, marking the tasks `sent`. Then `run_patient` so M14/M15 refresh.

`GET /api/patients/{id}/plan` lists every active task (theirs and ours) with
`last14` records `{date, status, source, count}`, `rate`, `verified_rate`, and a
summary. `POST …/plan/{task_id}/end` deactivates; `POST …/plan/{task_id}/record
{date, status, count?}` is a provider-entered status.

## Verification (`app/plan/verification.py`)

`verify_recent(db, patient_id, today, series)` runs inside `run_patient` before
`compute_adherence`, for every active task with `payload["care"]["verify"]`,
over the last 14 days from the assignment date. Steps, sessions, hourly steps,
pain/breathlessness logs, check-ins, sleep, scale/cuff/glucose rows confirm the
kind's rule (e.g. `steps_min`, `steps_band` auto = 0.75–1.15× the expected-curve
value or the personal trailing mean, `walk_bouts` from sessions or hours with
≥ 200 steps, `pain_log` 2 of 2 → verified, 1 of 2 → self-attested).

Rules: a record never moves down (`verified` stays, a contradicted self-report
stays `self_attested`); today is never missed; weekly/one-off tasks are never
missed on a day; self-report-only kinds are never written here; tasks without a
care payload (the seed, plain `assign-task`) are never touched, so the golden
tiers hold. Provenance (`source`, `count`) lives in `task_verifications` — the
record table belongs to the patient-app session. Idempotent.

## Message templates (`app/plan/messages.py`)

13 `MessageTemplate`s (`{first}`/`{surgeon}` placeholders; four pinned; three
chronic-care). `POST /api/patients/{id}/messages/draft {intent?, tone?,
template_id?}` reuses `app/llm/draft.py`'s prompt and fallback by import and adds
the clinician's intent, tone (warm | direct | encouraging) and template
personalization; the deterministic path rewrites "remind her to …" into second
person. Sending is their `POST /actions/message`.

## Next steps (`app/plan/next_steps.py`)

A rules-based planner ranks concrete steps per patient from reason codes,
care-metric statuses and a few counts: `call`, `message` (two clicks — the
composer opens prefilled), `assign_tasks`, `send_checkin`, `escalate`, `open`,
`acknowledge`. At most four open steps; executing or dismissing one writes a
`CareAction` and the step shows as done for its cooldown (message/check-in 2 d,
assign 14 d, escalate 3 d, call/ack/open 1 d). Assign steps skip templates
already on the plan.

```
GET  /api/patients/{id}/next-steps
POST /api/patients/{id}/next-steps/{key}/execute {payload_override?}
POST /api/patients/{id}/next-steps/{key}/complete {result}
POST /api/patients/{id}/next-steps/{key}/dismiss
```

`GET /api/worklist` rows carry `next_step` (the top open step) and
`next_steps_open`.
