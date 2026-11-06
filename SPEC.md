# SPEC.md — P1: Remote Therapeutic Monitoring (RTM)

> Product spec for the P1 Orthopedic RTM track. The existing Recovery Copilot
> console (see [README.md](README.md)) is the foundation this builds on.

## Overview

P1 expands the existing MedPull Recovery Copilot into an AI-powered Remote
Therapeutic Monitoring (RTM) platform for orthopedic recovery.

The current Recovery Copilot remains the foundation. Patients continue
receiving AI recovery check-ins while providers use the same dashboard and
patient views. P1 adds RTM-specific workflows including patient onboarding,
therapeutic monitoring, provider treatment management, AI documentation,
compliance tracking, and billing readiness.

## Implementation status

This spec is the product target, not a description of the code. Part of it
ships today and part of it does not, and the prose alone gives a reader no way
to tell which is which. So it is stated here, and again under each workflow
section below. Nothing in this document has been trimmed to match the build.

Markers used below:

- **Built:** implemented, and covered by the backend test suite.
- **Partly built:** the provider-facing half exists; something this spec
  describes is missing, and the gap is named rather than glossed.
- **Not built:** designed here, with no implementation behind it.

| Section | Status | What is actually there |
| --- | --- | --- |
| 1. Patient enrollment (98975) | Partly built | Enrollment happens in the patient app: a patient finds their chart by hospital, name and phone (or self-joins), accepts the beta consent form with a typed signature, and gets a session; consent is recorded on enroll, verify and join. The RTM education / consent / baseline ladder and the readiness card it gated were removed with the RTM platform (commit 8df30664). There is no baseline assessment step. |
| 2. Daily therapeutic monitoring (98985 / 98977) | Partly built | Monitoring-day counting and the CPT ladder went with the RTM platform. Conversational check-ins are built: the console assigns a check-in or task, and the patient answers in the app, on the texted `/t/<token>` web page, or by replying to the text one question at a time; every answer becomes a check-in transcript plus an adherence record. Of the nine monitored signals, activity, sleep and vitals come from wearables; pain from check-ins and the copilot; mobility and function from the Measure tab (walking speed, cadence, asymmetry, double support, steadiness, stairs, six-minute walk and joint range of motion, computed in `engine/mobility`). Swelling, medication adherence, PT adherence and home exercise are task answers only; `THERAPY_ADHERENCE`, `EXERCISE_REPS` and `PROM_SCORE` remain declared with no producer. |
| 3. Recovery intelligence | Partly built | The AI recovery summary, clinical flags, recovery trends and recommended next action are built, off the wearable analytics. Conversations are written by the app, the web page and SMS, and the symptom series they produce feed the M2 and C5 care metrics and the next-steps planner; the deterministic risk tier itself still takes no conversation input. The engine also returns a fourth Recovery Status this spec does not list, **Missing data**, for a patient whose device coverage is too thin to support any verdict. |
| 4. Provider worklist | Built | Patient, recovery status, one-line AI summary and the suggested next step, in that order, plus the daily briefing and Ask. Monitoring progress went with the RTM platform. |
| 5. Patient detail | Partly built | Recovery timeline, conversation history, trend graphs and wearable signals are there, plus the six-tile headline, Full stats (Metrics, Signals, Raw data), the care plan with its 14-day verification, the message thread with attachments and the wearable card. Documentation and the RTM readiness card were removed. There is no provider-notes surface. |
| 6. Provider treatment management (98979 / 98980 / 98981) | Partly built | Assign tasks, Message, Escalate and the rules-based next-steps planner exist. Message writes to the patient's thread and texts them when a number is on file. Provider time logging went with the RTM platform. "Escalate to nurse" notifies the patient's **assigned provider**, who in the demo roster is the surgeon: there is no role-based routing, and the nurse on the care team is never an assignee. |
| 7. AI documentation | Removed | Encounter notes, monthly summaries and review-and-approve went with the RTM platform. Recovery summaries exist as an on-screen insight rather than an approvable document; AI message drafts and task-plan drafts are the surviving generated text. |
| 8. RTM compliance & billing | Removed | The readiness card, the CPT ladder and Ready to Bill were built and then removed in commit 8df30664 (README, "RTM platform — removed"); `app/rtm/` no longer exists. Two limits of that implementation are worth keeping in mind for any rebuild: the monitoring-day count was clamped to the enrollment date, and 98980/98981 are per calendar month while the card accrued over a rolling 30 days, so a record of what has actually been claimed is required. |
| 9. Practice overview | Removed | `GET /api/practice/overview` went with the RTM platform. |
| Future integrations | Partly built | The Junction wearable aggregator is live end to end: one Junction account per patient issued from the patient record, a hosted Link page for the patient, Svix-verified webhooks for summaries and timeseries, automatic and on-demand back-fill, and disconnect — all through the same connector interface, webhook path, idempotent upsert and capability map. Oura, Fitbit/Google Health, Garmin, WHOOP, Withings, Polar and Dexcom connect this way. Apple Health is live through Junction's SDK inside the iOS app, and the app posts Apple's gait metrics directly (`POST /api/mobile/observations/gait`) because Junction does not pass them through; MedPull also computes its own gait, stairs, six-minute walk and range of motion from phone motion windows. Android Health Connect needs the same SDK inside an Android app, which is not built; Terra stays scaffolded; EHR, PT platforms and patient portals are not started. |

## Beside this spec: MedPull Personal

Since 2026-09-25 the same app also carries a consumer subscription tier for
people who are not a hospital's patient (training, sleep, recovery on their
own). It reuses this platform's wearable stream, engine and copilot but is a
separate product with its own rows, screens, storage bucket and words; it is
specified in [docs/personal-tier.md](docs/personal-tier.md), not here. A
subscriber never appears on a provider worklist, and a person who is both a
patient and a subscriber holds two paired rows and switches between them.

## CPT code reference

Source: Centers for Medicare & Medicaid Services.

| CPT code | Covers | MedPull role |
| --- | --- | --- |
| 98975 | Initial setup & patient education | AI onboarding, consent, patient education, enrollment tracking |
| 98985 | Musculoskeletal monitoring, 2–15 days | Daily recovery check-ins, adherence tracking, monitoring-day counter |
| 98977 | Musculoskeletal monitoring, 16–30 days | Same as above for longer monitoring periods |
| 98979 | First 10 minutes of treatment management (new in 2026) | Automatically track provider review time + require one live interaction |
| 98980 | First 20 minutes of treatment management | Time tracking, documentation, communication logging |
| 98981 | Each additional 20 minutes | Additional provider time tracking |

## Goals

- Monitor orthopedic recovery remotely
- Improve therapy adherence
- Detect at-risk patients earlier
- Reduce provider administrative burden
- Simplify CMS RTM workflows
- Increase RTM reimbursement

## Design philosophy

P1 should feel like a natural extension of the existing MedPull application.

Reuse the current UI, colors, typography, spacing, components, and navigation.
The interface should remain clean, minimal, and AI-first.

Providers should never be overwhelmed with dashboards or raw patient data.
Every screen should answer three questions:

1. Who needs my attention?
2. Why?
3. What should I do next?

Display concise AI summaries first, with detailed information available
through expandable sections only when needed.

## RTM workflow

### 1. Patient enrollment (CPT 98975)

**Status: partly built.** The provider-side enrollment record and its
billing consequences are real. The chatbot that would set it is not: enrollment
is written only by the demo seed, so education, consent and baseline are
fixtures rather than something a patient can complete.

Using the existing chatbot, AI automatically guides patients through:

- RTM education
- Consent
- Baseline assessment
- Pain and mobility baseline
- Surgery or injury details
- Recovery pathway assignment

Provider status:

- Enrollment Complete
- Education Complete
- Consent Complete
- Baseline Complete

### 2. Daily therapeutic monitoring (CPT 98985 / 98977)

**Status: partly built.** Day counting, the 16-of-30 window and the
monitoring card are built from wearable data. The scheduled conversational
check-in is not, and seven of the nine signals below have no producer: only
daily activity and sleep are actually collected.

Patients receive scheduled conversational recovery check-ins through SMS or
the MedPull app.

The AI dynamically asks follow-up questions based on recovery stage and
previous responses while monitoring:

- Pain
- Mobility
- Swelling
- Medication adherence
- Physical therapy adherence
- Home exercise completion
- Daily activity
- Sleep
- New symptoms

Each patient includes a simple monitoring card:

> **Monitoring Progress**
> 14 / 16 Days
> Monitoring Eligible

### 3. Recovery intelligence

**Status: partly built.** Everything below is generated per patient, but from
the wearable analytics rather than from a conversation, because no new
conversation can occur. Seeded transcripts do reach the narrative prompts; the
deterministic risk tier reads none of them. Note also that the engine returns a fourth status,
**Missing data**, when device coverage is too thin to justify any of the three
below.

After every conversation, AI converts patient responses into concise clinical
insights.

Each patient receives a Recovery Status:

- On Track
- Needs Review
- High Risk

Along with:

- AI recovery summary
- Clinical flags
- Recovery trends
- Recommended next action

The goal is to summarize rather than display raw questionnaire data.

### 4. Provider worklist

**Status: built.**

The homepage functions as an intelligent worklist rather than an EHR
dashboard.

Display only: patient, recovery status, one-line AI summary, monitoring
progress, and suggested action.

| Patient | Status | Summary | Action |
| --- | --- | --- | --- |
| Jane Doe | High Risk | Pain increasing, missed PT | Review today |
| John Smith | Needs Review | Missed check-ins | Message patient |
| Emily Chen | On Track | Recovery progressing normally | No action |

### 5. Patient detail

**Status: partly built.** Every expandable section below exists except
provider notes.

Each patient page begins with an AI-generated recovery summary.

Expandable sections include:

- Recovery timeline
- Conversation history
- Trend graphs
- Documentation
- Provider notes
- Future wearable data

The AI summary should remain the primary focus.

### 6. Provider treatment management (CPT 98979 / 98980 / 98981)

**Status: partly built.** All five actions exist and all logging is real.
Messaging delivers nothing yet, and escalation goes to the patient's assigned
provider (the surgeon in the demo roster) because no role-based routing exists.

Providers can:

- Message patient
- Call patient
- Schedule follow-up
- Escalate to nurse
- Update treatment plan

All interactions are automatically logged while provider review time is
tracked in the background.

### 7. AI documentation

**Status: partly built.** Two of the five types below are generated:
encounter notes and monthly RTM summaries. Review and approve are built.

Automatically generate:

- Recovery summaries
- Encounter notes
- Monthly RTM summaries
- Outreach documentation
- Treatment management documentation

Providers simply review and approve.

### 8. RTM compliance & billing

**Status: built, with two stated limits.** The card, the ladder, the suggested
next action and Ready to Bill are implemented and deterministic. The sample
values below are illustrative: the demo patient they were written around
matches the provider-review half exactly, but his monitoring days read 8 rather
than 14 (the count is clamped to his enrollment date) and his documentation is
not yet approved. Separately, 98980/98981 are monthly codes measured here over
a rolling 30 days, so the card cannot by itself prevent one accrual being
claimed in two consecutive months. Both points are documented in
`app/rtm/readiness.py`.

Every patient includes an RTM Readiness Card:

> **RTM Readiness**
> Enrollment Complete
> Education Complete
> Baseline Complete
> Monitoring Days: 14 / 16
> Provider Review: 14 minutes
> Interactive Communication: Required
> Documentation: Ready
>
> **Billing Eligibility**
> CPT 98975
> CPT 98985
> CPT 98980 (6 minutes remaining)
>
> **Suggested Next Action**
> Call patient to complete RTM requirements.

Once all requirements are satisfied, MedPull automatically marks the patient
as **Ready to Bill**.

The Compliance Engine continuously tracks CMS requirements, identifies
missing steps, and recommends the next action without requiring providers to
understand billing rules.

### 9. Practice overview

**Status: built.**

A lightweight overview displaying:

- RTM patients
- Patients needing review
- Patients ready for billing
- Therapy adherence
- Estimated RTM revenue opportunity

Avoid complex dashboards or unnecessary analytics.

## Future integrations

**Status: partly built.** Wearables are live through Junction (see the status
table and README's wearable section); the rest below is designed against the
same connector interface using mocked data.

Future integrations include:

- Apple Health
- Wearables
- Physical therapy platforms
- Electronic Health Records
- Patient portals

All external data should flow through the Recovery Intelligence Engine so
providers receive concise AI summaries rather than raw data streams.

## Product philosophy

MedPull is an AI RTM Copilot, not another patient monitoring dashboard.

Patients recover through conversational AI while providers receive concise,
actionable insights instead of overwhelming data. By combining intelligent
monitoring, provider prioritization, automated documentation, compliance
tracking, and billing readiness into a single workflow, MedPull enables
practices to deliver better patient care while making RTM significantly
easier to operate and reimburse.
