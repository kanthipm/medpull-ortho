# The HIRT demo: five lifters, followed by text alone

H.I.R.T. Physical Therapy (Harris Institute for Rehabilitative Therapies),
11703 Spring Cypress Rd, Tomball TX, inside Rise Gym. Dr. Sean Harris (PT,
DPT, PhD, OCS, FAAOMPT; owner of both) and Dr. Ashley Gregg, the day-to-day
user. Cash-pay, 60-minute one-on-one visits, free 20-minute injury screens,
lifters who train in a 24/7 gym between visits. Their edge is progressive
loading — right load, right time. The gap MedPull tests is the time between
visits: a lifter overloads a tendon too fast, or quietly stops coming, and
HIRT finds out at the next visit or never.

The experiment: five lifters Sean names — two with tendinopathy (the
load-too-fast risk), two spine patients returning to lifting, one recent
free-screen convert (the go-quiet risk) — for two weeks. One evening text a
day. Under ten minutes of the clinician's day: a morning shortlist before the
clinic opens, and a draft nudge to approve or edit before anything sends.

The demo org is `hirt` (`backend/app/seed/hirt.py`). Every lifter is
fictional. Nobody wears anything; every number comes from the check-in.

## What the room sees on a fresh fill

| Lifter | Program | Morning read | Tier |
| --- | --- | --- | --- |
| Cole Whitaker, 31 | Patellar tendinopathy · progressive loading | Two light weeks as prescribed, then back on his old leg day: six sessions at RPE 8–9. Training load 1.6× its recent average, pain 3 → 6. | **High** — load spike, pain rising |
| Rafael Quintero, 24 | Free screen · shoulder · program | Came in through a free screen, checked in every evening for eleven days, then a new job. Nothing for three days. | Medium — went quiet |
| Devon Castellanos, 42 | Low back · return to lifting | Still lifting, but the back program itself got done on under half of the last three days. | Medium — program slipping |
| Tessa Marlowe, 29 | Achilles tendinopathy · progressive loading | Load held, pain easing, program done every day. | Low |
| June Halvorsen, 48 | Lumbar disc · return to lifting | Steady. | Low |

Dr. Harris is on every chart as the evaluating clinician (the drafts say
"Dr. Harris"); Dr. Gregg carries Cole, Tessa and Rafael on the worklist.

## The walkthrough (under five minutes)

Open the console as HIRT (login link below). The worklist is the morning
shortlist: exceptions first, the rest below.

**1. The shortlist and the flag.** Cole Whitaker is the one red row. The line
under his name reads *Training load 1.6× its recent average — too much, too
soon · Pain up 2 points on the week before (4 → 6)*. The briefing paragraph
above the list opens with him — he is this roster's one red row (the
briefing orders a tier by score, the way the list does, so on a console that
shows every org it opens with whoever scores highest across them). Say what
the flag is: his reported training
load this week against his own prior weeks, the same ratio the tile on his
page shows, with the pain he reported moving the same way. Nothing here was
measured by a device; he texted it. Rafael is the amber row that reads *Went
quiet — no check-in for 3 days*: the free-screen convert the clinic would
otherwise never hear from again. Devon's amber row reads *Program slipping —
17% done over the last 3 days*: the Mon/Tue/Wed "did you do it" marks.

**2. The text he tapped through, and the phone check.** Click Cole. Under the
summary, *Check-ins* lists fourteen evenings. Open the latest: *How's the
pain today, 0 to 10?* — 6. *Any swelling you didn't have yesterday?* — yes.
*Any new pain that wasn't there at your last visit?* — no. *How did you
sleep?* — rough. *Did you get today's program in?* — all. *Training today:
how hard was it?* — 8, for about 80 minutes. And his note: "Back on my old
leg day all week. Knee's talking on the way down stairs and a bit puffy under
the kneecap tonight." That is the whole daily ask, under a minute, from a
text link: no download. To show the link itself, press **Send check-in** on
his next steps (or the daily check-in action): the thread row carries the
tokenized link; open it in a second browser tab to show the form the lifter
sees (`/t/<token>`). The phone ROM/gait check lives in the patient web app at
`https://demo.medpull.app/patient/` — sign in as the lifter (Which hospital →
H.I.R.T. Physical Therapy → find my record → phone), **Measure** tab, *Range
of motion* or *Guided walk*; the browser's motion sensors do the measuring,
no app installed. Do not lead with wearables; this clinic has none.

**3. The draft nudge, then the progress line.** Back on Cole, *Next steps*
leads with **Send a hold-the-load note**. Click it: the composer opens with
the draft — *Hi Cole — Dr. Harris's team here. Your training load jumped this
week — hold at last week's numbers until your session with Dr. Harris. Reply
with how the knee feels today.* He edits or approves; nothing sends until he
does. (On the demo roster the numbers are placeholders, so the text records
as not delivered and the thread shows it; the draft and the approval are the
point.) Then click Tessa Marlowe for the one-line progress view: the stats
row under her summary reads **Load vs prior weeks** (held, within ±20%),
**Pain, 7-day trend** (down, 3 → 2) and **Program** (7 of 7). Same three
numbers for every lifter; Cole's read +354%, +2 (4 → 6) and 7 of 7 — he did
the program and then some.

**4. Hand him the pen.** Rafael's next step is **Send a one-tap check-in**
with the draft *Haven't heard from you in a few days — one tap: how's it
going?* Let Sean edit it in his own words and press send. Then ask which
five lifters he would name.

## The day-14 line

In Sean's words: "I caught the lifter who was about to overload before they
came in, and the screen patients didn't go quiet." Cole is the first half;
Rafael is the second. Both are visible before 7:55 AM without opening a
chart, and the shortlist shows completion of what was laid out that week
(the Program number) and the questions that need an answer (the drafts).

## Rules of the room

No RTM, billing or reimbursement language. No price. No accuracy
percentage. No EMR integration promise ("EMR — rather they just text me").
No clinical promises: MedPull flags and drafts; the clinician decides. The
copy on every surface says "too much, too soon", "went quiet", "program
slipping" — the clinic's own words — and never a code.

## Getting in

**The HIRT console login link.** The console is opened with a link of the form
`https://demo.medpull.app/login#token=…`. A token scoped to the HIRT roster is
minted against the deployed database with

```
cd backend && uv run python scripts/admin_db.py --bucket <bucket> --mint-token hospital:hirt "HIRT console"
```

(`--mint-token` is the mechanism another stream is adding to `admin_db.py`;
until it lands, the deployment's console token opens every roster and the
HIRT rows are filtered by eye.) Treat the link as a credential: it is the
clinic's door.

**The check-in by text link.** The lifter's phone receives one text an
evening. It carries the tokenized link (`https://demo.medpull.app/t/<token>`)
to the eight questions, or they reply `1` and answer by text, one question at
a time (`How's the pain today, 0 to 10? (reply a number from 0 to 10)`). The
answers become the transcript the console shows and, for the training
answers, the load and program numbers the tier reads. Enrollment is the same
text link: no download, nothing to install.

**The patient web app.** `https://demo.medpull.app/patient/` is the clinic
iPhone app in the browser: Today, Progress, Measure, Care. The Measure tab's
*Range of motion* and *Guided walk* use the phone's motion sensors
(DeviceMotion) and post to the same engine.

## Filling the roster

The HIRT roster is part of the shipped seed and of the demo fill, so both a
scratch database and the deployed one carry it.

Scratch database (what the tests run against, re-anchored to today):

```
cd backend && DEMO_MODE=true DATABASE_URL=sqlite:///./data/hirt-dev.db GROQ_API_KEY= \
  SENDBLUE_API_KEY= SENDBLUE_API_SECRET= S3_BUCKET= WARM_CACHES_ON_STARTUP=false \
  uv run python -m app.seed.seed --reset
```

The deployed database, the morning of the demo, under the S3 write lock,
with a server-side backup first (this re-anchors every demo org to today and
never touches the protected charts):

```
cd backend && uv run python scripts/push_demo_fill.py --bucket <bucket> --dry-run
cd backend && uv run python scripts/push_demo_fill.py --bucket <bucket>
```

A local copy of any database: `uv run python scripts/push_demo_fill.py --local
/path/to/copy.db`. The fill adds the `hirt` hospital and both therapists to a
database that predates them, then writes the five lifters, their fourteen
evenings and their threads, and re-runs the engine.

## What is under it

- `backend/app/seed/hirt.py` — the org, the five, their fourteen days.
- `backend/app/tasks/service.py` `LIFTER_CHECKIN_QUESTIONS` (`checkin_lifter`) —
  picked for a general-mode patient whose `care_pathway` names a clinic
  program rather than one of the engine's pathways.
- `backend/app/tasks/reported.py` — the training answers become
  `SESSION_LOAD` (RPE × minutes) and `PROGRAM_DONE` (1 / 0.5 / 0) observations.
- `backend/app/engine/reported.py` and `engine/risk.py` `score_reported` — a
  chart with no device series and three check-ins in two weeks is scored from
  what was reported: `LOAD_SPIKE`, `PAIN_RISING`, `NEW_PAIN`,
  `PROGRAM_SLIPPING`, `WENT_QUIET`. The load ratio is the one the M1 tile
  shows (`care/load.py` `load_windows`), so the flag and the tile agree.
- `backend/app/plan/messages.py`, `plan/next_steps.py`, `llm/draft.py` — the
  drafts: hold the load, one-tap check-in, ask about the pain, program nudge.
- `backend/app/api/patients.py` `progress` — the three numbers on the
  console's stats row (`frontend/src/features/patient/PatientDetailPage.tsx`).
- `backend/tests/test_hirt.py` — every rule, the five tiers, every path.

## The calendar, her clip, their clip (added 2026-11-08)

What Dr. Gregg asked for after the first walkthrough, and how it shows:

1. **The week grid** — Exercises → Schedule (`/exercise-schedule`): one row per lifter, one column per day, today marked. Each chip is an exercise with its dose; a done one carries a check and the pain the lifter reported after it; a skipped one is muted; a film badge means a clip plays on the phone. The `+` in any cell opens the assign dialog: pick from the library, dose, side, a note in her words, who assigns it, and the other days of the week to put it on too.
2. **Her demonstration** — open any chip (or an exercise in the Library) → *Upload your demonstration*. The file input opens the camera on a phone; the clip goes straight to the clinic's bucket, is approved on upload, and from then on plays on every lifter's phone wherever that exercise is assigned. Standard exercises keep one clip per clinic; nothing is copied. The demo roster ships placeholder title cards (`backend/scripts/seed_hirt_media.py`) until she films hers.
3. **The phone** — Today shows *Today's exercises* with the dose, her note and a Clip badge. The exercise screen plays her clip, lists the steps and precautions, then *Mark done*: pain after (0–10), an optional note, *Record a clip of you doing it* (the phone's camera; the clip is staged to storage and confirmed with the completion), *Send to Dr. Gregg*. *Can't do it today* skips with a reason. Today polls every ten seconds, so an assignment made in the room appears on the phone during the conversation.
4. **What comes back** — the chip flips to done with the pain badge; the dialog shows when, pain, the note and the lifter's clip; the chart's thread gets a line "Did Step-Ups · pain 4/10 after" with the clip beside it; the patient page carries an *Exercises this week* strip.
5. **The demo screen** — `/demo/hirt` on the demo stack only: the schedule on the left two thirds, an iPhone frame on the right running the real patient web app signed in as the lifter you pick (a demo-only session; no text message needed). Assign on the left, watch it land on the right; mark it done on the phone, watch the chip flip on the left.

Seeded for the room: each lifter's calendar from program day 0 through next week in catalog exercises that fit the pathway, with outcomes matching the check-in story (Cole done with pain climbing 2 → 6, Devon mostly missed, Rafael quiet for three days, Tessa and June all done), their beta consent already accepted, and three returned clips. Contract and routes: `docs/dev/hep-schedule.md`.

