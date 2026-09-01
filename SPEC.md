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
| 1. Patient enrollment (98975) | Partly built | The enrollment record (education / consent / baseline / complete, with a date) is real and gates every billing code on the readiness card. Nothing writes it outside the demo seed: there is no chatbot, no consent capture, no baseline assessment. The first three suggested next actions therefore name steps the product cannot yet perform. |
| 2. Daily therapeutic monitoring (98985 / 98977) | Partly built | Monitoring-day counting over the rolling 16-of-30 window is built and drives the CPT ladder, off wearable observations. Conversational check-ins are not: there is no SMS or in-app patient channel and no write path for a check-in outside the seed. Of the nine monitored signals only daily activity and sleep are collected; pain, mobility, swelling, medication adherence, PT adherence and home exercise have metric types declared (`PAIN_NRS`, `RANGE_OF_MOTION`, `THERAPY_ADHERENCE`, `EXERCISE_REPS`, `PROM_SCORE`) and no producer anywhere. The monitoring card is built. |
| 3. Recovery intelligence | Partly built | The AI recovery summary, clinical flags, recovery trends and recommended next action are built, off the wearable analytics. "After every conversation" is not: the seeded transcripts are read into the narrative prompts and tagged by topic on the check-in timeline, but with no conversation write path a patient's transcript never changes, and the deterministic risk tier takes no conversation input at all. The engine also returns a fourth Recovery Status this spec does not list, **Missing data**, for a patient whose device coverage is too thin to support any verdict. |
| 4. Provider worklist | Built | Patient, recovery status, one-line AI summary, monitoring progress and suggested action, in that order. |
| 5. Patient detail | Partly built | Recovery timeline, conversation history, trend graphs, documentation (inside the RTM readiness card) and wearable signals are all there. There is no provider-notes surface. |
| 6. Provider treatment management (98979 / 98980 / 98981) | Partly built | All five actions exist, and each logs an interaction plus provider time; review time on a patient record is tracked in the background. Message records intent and delivers nothing. "Escalate to nurse" notifies the patient's **assigned provider**, who in the demo roster is the surgeon: there is no role-based routing, and the nurse on the care team is never an assignee. |
| 7. AI documentation | Partly built | Two of the five document types are generated: encounter notes and monthly RTM summaries. Recovery summaries exist as an on-screen insight rather than an approvable document. Outreach and treatment-management documentation are not built. Review-and-approve is built, and an approved document is never regenerated. |
| 8. RTM compliance & billing | Built, with two stated limits | The readiness card, the CPT ladder, the suggested next action and Ready to Bill are implemented and fully deterministic. First limit: the sample card below is not reproducible as printed. Marcus Reyes is the patient it was written around and he matches its provider-review half exactly (14 minutes logged, 6 remaining on 98980, and that suggested next action), but his monitoring days read 8, not 14, because the count is clamped to the enrollment date and he enrolled eight days ago, and his documentation is not yet approved. Second limit: 98980/98981 are defined per calendar month while this card accrues over a rolling 30 days, so a practice billing at each month end could claim one accrual twice. Closing that needs a record of what has actually been claimed, which the product does not keep. Both are documented in `app/rtm/readiness.py`. |
| 9. Practice overview | Built | Five numbers, every one of them from `GET /api/practice/overview`. |
| Future integrations | Mocked, as this spec intends | The connector interface, webhook path, idempotent upsert and per-provider capability map are real; every non-demo connector raises `NotImplementedError`. |

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

Design interfaces now using mocked data.

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
