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

Open **https://demo.medpull.app/?clinic=hirt**: the console, already on
H.I.R.T.'s roster (the menu at the top right reads *Clinic · H.I.R.T.
Physical Therapy*; no sign-in). The worklist is the morning shortlist:
exceptions first, the rest below. The tabs beside it are **Calendar** (the
exercise schedule) and **Data** (everything underneath).

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
row under her summary reads **Load vs recent average** (0.9×, held),
**Pain, 7-day trend** (down, 3 → 2) and **Program** (7 of 7). Same three
numbers for every lifter; Cole's read 1.6× (the number his flag states),
+2 (4 → 6) and 7 of 7 — he did the program and then some.

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

**The HIRT console.** `https://demo.medpull.app/?clinic=hirt` opens the
console on H.I.R.T.'s roster with no sign-in: the `?clinic=` is taken once
and remembered, and the menu at the top right switches to every clinic, to a
Personal member, or to a team. A link that can see *only* H.I.R.T. (a
clinic's own door, for when they should not see the other rosters) is a
token minted against the deployed database:

```
cd backend && uv run python scripts/admin_db.py --bucket <bucket> --mint-token hospital:hirt "HIRT console"
```

It prints `https://demo.medpull.app/login#token=…`. Treat that link as a
credential.

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

The deployed database re-anchors itself: every morning at 10:30 UTC the
showcase fill rewrites every generated persona around the new day (the five
lifters, the other clinic rosters, the teams, the Personal members) and
leaves every other row alone (`docs/ops/one-deployment.md`). To run it by
hand, say after a walkthrough that left the day in a state:

```
aws lambda invoke --function-name recovery-copilot-seed \
  --cli-binary-format raw-in-base64-out --payload '{"action":"showcase_fill"}' /dev/stdout
```

One lifter's day alone is put back from the demo screen (**Reset the day**),
which clears what the walkthrough did to today's exercises and nothing else.

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
- `backend/app/engine/care/pathways.py` `TRAINING` — the six tiles a lifter's
  chart leads with, chosen because a calendar and a check-in fill all of
  them: **Verified adherence** (the exercise calendar's last 14 days, one row
  per exercise), the load ratio, **Pain–load sensitivity** (what a unit of
  training load costs in next-morning pain), symptom burden, how the chart
  is followed (check-ins by day, no watch) and engagement. A done exercise
  day counts as verified when a clip came back, a watch recorded the
  session, the session was run on the phone start to finish, or the clinic
  logged it; a done mark alone counts half; a skipped or passed day is a
  miss (`care/loaders.py` `exercise_outcome`). Devon's tile reads *Adherence
  low*, Rafael's *Adherence slipping*; the wearable tiles (trend against own
  baseline, the overnight index) are under **All metrics** and come back to
  attention beside the six if a watch is connected and one of them flags.
- `backend/tests/test_hirt.py` — every rule, the five tiers, every path.

## The calendar, her clip, their clip (added 2026-11-08)

What Dr. Gregg asked for after the first walkthrough, and how it shows:

1. **The week grid** — the **Calendar** tab (`/calendar`): one row per lifter, one column per day, today marked. Each chip is an exercise with its dose; a done one carries a check and the pain the lifter reported after it; a skipped one is muted; a film badge means a clip plays on the phone. The `+` in any cell opens the assign dialog: pick from the library, dose, side, a note in her words, who assigns it, and the other days of the week to put it on too.
2. **Her demonstration** — open any chip (or an exercise in the Library) → *Upload your demonstration*. The file input opens the camera on a phone; the clip goes straight to the clinic's bucket, is approved on upload, and from then on plays on every lifter's phone wherever that exercise is assigned. Standard exercises keep one clip per clinic; nothing is copied. The demo roster ships placeholder title cards (`backend/scripts/seed_hirt_media.py`) until she films hers.
3. **The phone** — Today shows *Today's exercises* with the dose, her note and a Clip badge. The exercise screen plays her clip, lists the steps and precautions, then *Mark done*: pain after (0–10), an optional note, *Record a clip of you doing it* (the phone's camera; the clip is staged to storage and confirmed with the completion), *Send to Dr. Gregg*. *Can't do it today* skips with a reason. Today polls every ten seconds, so an assignment made in the room appears on the phone during the conversation.
4. **What comes back** — the chip flips to done with the pain badge; the dialog shows when, pain, the note and the lifter's clip; the chart's thread gets a line "Did Step-Ups · pain 4/10 after" with the clip beside it; the patient page carries an *Exercises this week* strip.
5. **The demo screen** — `/demo/hirt` (Calendar → *Open the demo screen*): the schedule on the left two thirds, an iPhone frame on the right running the real patient web app signed in as the lifter you pick (a demo-only session; no text message needed). Assign on the left, watch it land on the right; mark it done on the phone, watch the chip flip on the left.

Seeded for the room: each lifter's calendar from program day 0 through next week in catalog exercises that fit the pathway, with outcomes matching the check-in story (Cole done with pain climbing 2 → 6, Devon mostly missed, Rafael quiet for three days, Tessa and June all done), their beta consent already accepted, and three returned clips. Contract and routes: `docs/dev/hep-schedule.md`.

## The guided task and her side (added 2026-11-08, second pass)

On the phone, an exercise is a task done step by step, each step one screen with one button:
1. **You have this to do**: the exercise, dose, her note, and "Pain right now?" (one tap, skippable). **Start**.
2. **Your watch** (when she set the wearable to optional or required): "Checking for your watch…", then a green check, "Detected · Apple Watch". The detection is a demo stand-in.
3. **Set up your phone**: prop it at knee height, two metres away. **Ready**.
4. **Do the exercise**: her clip looping, the steps, a timer, "Set 1 of 2 · Next set", a rest countdown between sets.
5. **Record your attempt** (when she asked for a clip): a live camera with a 3-2-1 countdown where the browser records MP4 (Safari, recent Chrome); elsewhere the camera roll. On the demo stack, **Use a sample clip (demo)** stands in, so the room never waits on a camera prompt. Required means no skipping.
6. **Checking your recording**: a ring for two seconds, then "Looks good — saved for Dr. Gregg" while the upload actually happens. The check itself is a demo stand-in.
7. **How did it go?**: pain after and effort, 0–10, and a note. **Send to Dr. Gregg**.
8. **Done**: pain before → after, effort, time, sets × reps × load, watch on, the clip.

On her side the chip flips to done with pain and effort and an amber dot; the row header carries adherence ("19 of 20 · 95%") and "clips to review"; **Review** (Calendar → Review) lists what waits for her newest first, opens them beside her demonstration (**Compare**), and **Send reply** puts her note in the lifter's Care thread and on the done card. Also there: load and target effort on every dose, clip and watch requirements per exercise (off / optional / required), **Copy last week**, and **Programs** (templates by phase, applied to a lifter for a number of weeks). The phone's **See the week** shows the program as a 14-day calendar.

For the room, the order that tells the story in under three minutes: on `/demo/hirt`, pick Cole on the phone; on the left, `+` on today, Mini Squats, 2 × 10 at 25 lb, clip and watch required, a note; it lands on the phone at once; run the task on the phone with the sample clip; watch the chip flip on the left; open Review, Compare, reply; the reply shows on the phone.

## The showcase (added 2026-11-12)

The console is now three versions of one product behind the menu at the top
right, and H.I.R.T. is one clinic in the first of them. What that adds to
this room, in the order it is worth showing:

1. **Calendar, grown.** The chips say where each day stands: *missed* (a
   dashed outline once the day has passed), *in progress* (the session is
   open on their phone), and a rising mark when a session went **over the
   dose**. Open Cole's Step-Ups from Monday: *More than prescribed · 35 lb
   done, 25 lb prescribed*, with sets, reps, load and effort side by side.
   Loads read in pounds here (the **lb | kg** switch is the clinic's, top
   right of the grid; rows are kept in kilograms either way). Drag a chip to
   another day to move it; hold Option to copy. The `+` now has **Repeat**
   (Mon/Wed/Fri for four weeks, as one repeat that is re-dosed or cleared
   "this and the following") and **Text Cole about it**. **Month** shows six
   weeks: a strip per lifter (done, missed, still ahead) and the picked
   lifter's calendar. The row menu has **Text today's plan**.
2. **Week** (Calendar → Week). Each lifter's week in review, the ones with
   something to look at first: done against written, pain before and after,
   effort against the target, the load moved against the load written and
   against last week, the days over the dose, and whether next week is set.
   June's is not ("not set yet"): **Copy this week forward** sets it in one
   press. This is the Monday-morning page.
3. **Review** now says why each day waits: a clip to watch, or a session
   over the dose (which waits for a look even with no clip).
4. **Data** (third tab). The roster by what was collected; open Cole →
   **Reported**: the grid a clinic keeps in a spreadsheet today, one row a
   day — pain, swelling, sleep, program, his own training, the exercise
   calendar with *More than prescribed* marked, his note — and **Export
   CSV**. For a chart with a watch (pick *All clinics*, then Dana Okonkwo):
   Sources, Raw, Signals, what MedPull computes itself, Care metrics, Sleep.
   **Dictionary** lists every metric with its unit, source and method.
5. **The text that opens the app.** A text from the calendar carries
   `https://demo.medpull.app/a/<token>`. On a phone with the demo app it
   opens the app on that exercise; in a browser it opens the patient web
   app there, signed in as that lifter (personas only: a link never signs
   anyone into a real chart). Replies work: **DONE** marks today's open
   exercises done and asks for the pain; **STOP** stops every text until
   **START**; **HELP** says who this is. A row that asks for a clip or the
   watch cannot be closed by text and answers with the link instead.
6. **The demo iPhone app** (MedPull Demo, target `MedPullDemo`). One app
   with no accounts that becomes any persona of any version: pick Clinic →
   H.I.R.T. → Cole and it is Cole's phone, with the exercise calendar and
   the guided session on it. **Text my phone** (the avatar at the top right)
   binds the presenter's own number to that persona, so the texts in step 5
   arrive on a real phone and their links open the app. It is a demo tool,
   not the app a patient installs (`docs/dev/showcase/ios.md`).
7. **The other two versions**, one click each from the menu, if the room
   asks what else this is: **Personal** (a member's own Today, Trends and
   Data) and **Sports** (a team's Board, Calendar and Data).

Still true, and still the rules of the room: nothing here sets a dose,
scores a movement, or says a lifter is cleared. "Over the dose" describes a
session; the therapist decides what it means.

