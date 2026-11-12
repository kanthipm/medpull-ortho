# The showcase: three versions of one console, a demo phone, and links that open it

This is the contract for the November 2026 overhaul of the demo. It says
what the pieces are, how they talk to each other, and who owns which file
while they are being built. Each stream writes what it actually built
(routes, shapes, traps) to its own file under `docs/dev/showcase/`; this
page is the map.

## What it is

The console is one app that shows three versions of the product, chosen
from a menu at the top right:

| Version | Who it is for | Tabs |
| --- | --- | --- |
| **Clinic** | a clinic following patients between visits | Worklist · Calendar · Data |
| **Personal** | a member reading their own body | Today · Trends · Data |
| **Sports** | a team's performance and medical staff | Board · Calendar · Data |

The three tabs answer the same three questions in every version: who needs
attention now, what is planned, and what is the data underneath.

Beside it there is a demo iPhone app (`ios/MedPullDemo`) that signs in as
any fictional person on the demo with no account, in any of the three
versions, and a text channel (Sendblue) whose links open that app at the
right screen.

## Rules that hold everywhere

- **One build, two stacks.** The same `frontend/dist` and the same Lambda
  code go to the real app and to the public demo. Anything that exists for
  the showcase keys on runtime — `/api/health` `demo`, the console scope,
  `/api/console/workspaces` — never on a hostname or a build flag.
- **Demo-only routes answer 404 unless `settings.demo_mode`.** Acting as a
  patient, listing personas and opening a Personal member's space are all
  demo-only.
- **A GET never commits.** On AWS a commit re-uploads the whole database.
  No new GET may call `run_patient`, `ensure_fresh_assessment`,
  `insights.get_brief`, `daily.start_day` or anything else that writes.
- **The schema only grows.** New tables, and new columns that are nullable
  or have a default (`app/database.py` adds them; nothing migrates).
- **Subscribers stay off clinic rosters.** Roster reads go through
  `scoped_clinic_patients` / `clinic_filter`; a per-chart console read adds
  an `is_clinic` check so an open console cannot open a member or an
  athlete through `/api/patients/{id}`.
- **Words.** The clinic's own: lifter, load, dose, program, "too much, too
  soon", "went quiet". Never "compliance", "AI detects", "predicts injury",
  "cleared", "validated", an acute:chronic ratio as a risk number, or a
  MedPull-written dose. MedPull shows what was done against what was
  prescribed and drafts messages; the clinician decides. Patient-facing
  text never names a diagnosis (`_no_diagnostic`) and server-side SMS copy
  keeps straight apostrophes.
- **Design.** medpull.org's language as the console already speaks it
  (`frontend/src/index.css` recipes, Outfit, sage, glass, one near-black
  primary button, state as a chip with a word). Every new page has a
  `<header data-hero>`. Light is the default; check dark too. A `.tsx` file
  exports components only.

## The console

### Versions and routes

`frontend/src/components/layout/version.ts` derives the version from the
path, so every link is deterministic:

| Path | Version | Tab |
| --- | --- | --- |
| `/`, `/patients/:id` | clinic | Worklist |
| `/calendar`, `/calendar/week`, `/calendar/review`, `/calendar/programs[/:id]`, `/calendar/library`, `/calendar/plans[/:id]`, `/demo/hirt` | clinic | Calendar |
| `/data`, `/data/patients/:id`, `/data/dictionary` | clinic | Data |
| `/integrations`, `/settings/*` | clinic (no tab lit; reached from the menu) | — |
| `/personal` (→ first member), `/personal/:memberId` | personal | Today |
| `/personal/:memberId/trends` | personal | Trends |
| `/personal/:memberId/data` | personal | Data |
| `/sports` (→ the stored or first team), `/sports/teams/:teamId`, `/sports/teams/:teamId/athletes/:id` | sports | Board |
| `/sports/teams/:teamId/calendar` | sports | Calendar |
| `/sports/teams/:teamId/data` | sports | Data |

The old exercise paths redirect: `/exercise-schedule` → `/calendar`,
`/exercise-review` → `/calendar/review`, `/exercise-programs[/:id]` →
`/calendar/programs[/:id]`, `/exercise-library` → `/calendar/library`,
`/exercise-plans[/:id]` → `/calendar/plans[/:id]`. `/sports/teams/:teamId`
keeps meaning the board, because that link is in circulation.

Two pages sit outside the shell, like `/t/:token`: `/a/:token` (a texted
link opened in a browser: see Links) and `/login`.

### The workspace menu

One trigger in the bar's right cluster, labelled with where you are
("Clinic · H.I.R.T.", "Personal · Jordan Avery", "Sports · Rice MBB"). The
menu is grouped:

```
CLINIC          All clinics / one row per clinic with charts
PERSONAL        one row per demo member
SPORTS TEAMS    one row per team with a roster
────────
Demo screen     (demo stack, staff scope)
Integrations    (staff scope)
Settings
Sign out        (when a token is stored)
```

It is fed by `GET /api/console/workspaces`. A hospital credential sees only
its clinic, a sports credential only its teams; a version with nothing in it
is not listed; with one version and one row the trigger is a plain label.

**Acting clinic.** On a staff console, choosing a clinic stores its id
(`medpull-console.clinic`) and every console request carries
`X-MedPull-Clinic: <hospital id>`. The server narrows roster reads to that
hospital and the exercise calendar acts for it (`ConsoleScope
.acting_hospital_id`); staff may still open any chart by id, and the staff
pages keep working. "All clinics" clears it. `?clinic=<id>` (or `all`) on
any console URL sets it once and is removed from the address, so
`https://<host>/?clinic=hirt` is the H.I.R.T. room's bookmark. Changing it
resets the query cache.

Console storage keys keep the `medpull-console.` prefix (the patient web
app on the same origin clears `medpull.`).

### Clinic

- **Worklist** — as today. The chart keeps the summary, next steps,
  check-ins, this week's exercises, tasks and the thread; the deep data
  (Full stats: metrics, signals, raw) moves to Data, with a link from the
  chart.
- **Calendar** — the exercise schedule, grown: week and month views, drag to
  move or copy, repeat on weekdays for N weeks, missed and in-progress
  marks, done against prescribed, planned load against last week, one
  exercise's history, a week review per lifter with next week's draft,
  pounds or kilograms, and a text to the lifter that opens the app. Sub-nav:
  Schedule · Week · Review · Programs · Library · Plans.
- **Data** — tiered: sources and coverage → raw readings → daily signals
  against the person's baseline → what MedPull computes itself (gait,
  stairs, six-minute walk, range of motion, stress; reported load, pain and
  program) → care metrics and the risk read. A roster view (coverage by
  family), a chart view, a sleep view, the reported grid (what the clinic
  keeps in a spreadsheet today) and a dictionary of every metric with its
  unit, tier, source and method. CSV export.

### Personal

The demo members' own spaces, read-only, as a member sees them: **Today**
(verdict, readiness, plan, brief, alerts, the coach), **Trends** (sleep and
recovery, training load and form, thirteen weeks), **Data** (every panel
with its method and coverage, raw signals, logs). Demo stack only.

### Sports

One team at a time, picked from the menu: **Board** (briefing, attention,
roster, injuries — today's team page), **Calendar** (the events calendar
with team load), **Data** (signals, wellness, tests, jumps and devices
across the roster; the athlete page's unused panels).

## The demo API (`/api/demo/*`, demo stack only)

No console credential: the demo iPhone app calls these before it has any.

`GET /api/demo/personas`

```json
{
  "as_of": "2026-11-12",
  "sms": {"number": "+15049081262", "text_body": "Hi MedPull", "configured": true},
  "versions": [
    {"key": "clinic", "label": "Clinic", "blurb": "Followed by a clinic between visits",
     "orgs": [{"id": "hirt", "name": "H.I.R.T. Physical Therapy", "personas": [
       {"id": "hirt-cole", "name": "Cole Whitaker", "hero": true,
        "tagline": "Patellar tendinopathy · progressive loading",
        "detail": "Load spike, pain rising",
        "account_kind": "clinic", "tier": "high",
        "has": {"wearable": false, "exercises": true, "thread": true}}]}]},
    {"key": "personal", "label": "Personal", "blurb": "…", "orgs": [{"id": "personal", "name": "MedPull Personal", "personas": []}]},
    {"key": "sports", "label": "Sports", "blurb": "…", "orgs": [{"id": "rice-mbb", "name": "Rice · Men's Basketball", "personas": []}]}
  ]
}
```

`POST /api/demo/session` `{"persona_id": "hirt-cole", "device_name": "iPhone"}`
→ `{"session_token": "…", "me": { …exactly GET /api/mobile/me… }, "persona": {"id", "name", "version"}}`.
Registry ids only (`app/seed/showcase.py`); one live session per persona and
device name (re-issued, not piled up). Every persona has consent on file, so
no app lands on the consent gate.

`POST /api/demo/reset-day` `{"persona_id": "…"}` → puts that persona's day
back (today's exercise rows reopened, the lines today's demo added to the
thread removed) so a walkthrough can be run again. `{"reopened": n, "removed": n}`.

`GET|POST|DELETE /api/demo/phone` — authorised by the persona's app session
(`Authorization: Bearer <session_token>`). `POST {"phone": "+1…"}` binds a
real number to the persona (and takes it off any other demo chart), so the
demo's texts reach the presenter's phone; `GET` reports it; `DELETE`
unbinds. All answer
`{"phone": "+1…"|null, "reachable": bool, "text_to": "+1504…", "text_body": "Hi MedPull", "sent": bool, "detail": str|null}`:
on Sendblue's free plan a number is reachable only after it has texted the
line once, so the app shows "text us first" and polls `GET` until
`reachable` turns true, at which point the welcome text (with a link into
the app) goes out.

`POST /api/demo/patient-session` (console credential) stays for the
presenter's phone frame.

`GET /api/health` adds `"showcase": {"filled_on": "YYYY-MM-DD" | null}`.

The fill: `app.seed.showcase.fill_showcase(db, today)` re-anchors every demo
org to today — clinic personas and H.I.R.T. (`demo_fill`), sports rosters,
Personal members — keeping persona sessions and bound phones. It runs from
`scripts/push_demo_fill.py`, and on the demo stack from a morning
EventBridge rule (Lambda action `showcase_fill`), so the demo is current
without anyone remembering to refill it.

## Links (`app/links.py`, `/api/links/*`, `/a/<token>`)

A text carries `https://<host>/a/<token>`. The token is opaque; the row
(`app_links`) names a patient and a place: `today`, `exercise` (ref =
assignment id), `program`, `task` / `checkin` (ref = task id), `thread`,
`measure`, `progress`.

- `GET /api/links/{token}` →
  `{"kind", "ref_id", "day", "expires_at", "signin": bool, "patient": {"first_name"}, "clinic": {"name"}|null, "app": {"scheme": "medpulldemo", "url": "medpulldemo://a/<token>"}, "web": "/patient/#link=<token>"}`.
  No side effects (iMessage fetches a link to preview it). 404 when unknown
  or expired.
- `POST /api/links/{token}/session` `{"device_name"}` →
  `{"session_token", "me", "target": {"kind", "ref_id", "day"}}`. Allowed
  where `signin` is true: on the demo stack. On the real app it answers 403
  ("Open MedPull and sign in"), and an app that is already signed in as that
  patient just uses the target.
- **iPhone.** The association file (`/.well-known/apple-app-site-association`)
  lists the app ids from `IOS_TEAM_ID.IOS_BUNDLE_ID` and `IOS_LINK_APP_IDS`
  with the paths in `IOS_LINK_PATHS` (`/t/*`, `/a/*`). The demo app has the
  `applinks:<host>` entitlement and also answers `medpulldemo://a/<token>`.
  It redeems the token, adopts the session if it is not already that
  person, and opens the target.
- **Browser.** `/a/:token` is a console route outside the shell: it reads
  the link, offers "Open in the app" (the custom scheme) and continues to
  `/patient/#link=<token>`; the patient web app redeems it on boot and
  navigates to the target.

## Texts (`app/hep/texts.py`, `app/notifications/sendblue.py`)

- `notify_assigned(db, patient, rows, *, base_url, by)` — called by
  `POST /api/hep/schedule` when the body says `text_patient: true`.
- `notify_review(db, row, *, base_url)` — called when a review carries a
  note.
- `text_today(db, patient, *, base_url, day, by)` — behind
  `POST /api/hep/patients/{id}/text-today` and the morning run
  (`EXERCISE_REMINDERS`, Lambda action `exercise_reminders`).

Each writes a thread line (`Message`, channel `sms`, an `action_kind` the
apps can render as a button: `action` on the line carries `kind`
(`open_<link kind>`), `label`, `url` and `target`, the `{"kind", "ref_id",
"day"}` a redeemed link answers with; the patient web app and the demo
iPhone app draw the button from `target`, so it opens the place without
redeeming the link again) and returns
`{"sent", "status", "detail", "message_id", "link"}` or None. None of them
raises into its caller.

Inbound (`app/tasks/service.py`), before anything reaches the assistant:
`STOP` / `START` / `HELP` (an opt-out the send path honours); `DONE` with
or without a pain number, and a bare 0–10 after a `DONE`, mark today's open
exercises done from a text (rows that require a clip are left open and the
reply says so with the link). The demo stack registers its own Sendblue
`receive` webhook (Sendblue allows several) and passes a per-message
`status_callback`, so replies and delivery states reach it too.

## The demo iPhone app (`ios/MedPullDemo`, target `MedPullDemo`)

Bundle id `com.medpull.demo`, scheme `medpulldemo`, built against the demo
stack. A second target in `ios/project.yml` that shares the design system,
the API client, the models and the feature screens with the real app and
supplies its own shell:

1. Pick a version (Clinic, Personal, Sports), then a person
   (`GET /api/demo/personas` → `POST /api/demo/session`).
2. The same switcher is one tap away afterwards (top right), like the
   console's.
3. Clinic adds what the real app does not have yet: today's exercises, the
   program calendar and the guided session, natively
   (`/api/mobile/exercises…`).
4. "Text my phone" binds the presenter's number (`/api/demo/phone`).
5. A link from a text opens the app at its target, signing in as that
   person if needed.

Launch arguments for the simulator: `-MP_DEMO_PERSONA <id>`, `-MP_TAB …`,
`-MP_OPEN_LINK <token>`, `-api_base_url <url>`.

## Who owns what while it is being built

Backend streams (first wave) and their as-built notes:

| Stream | Owns | Notes file |
| --- | --- | --- |
| showcase | `app/seed/showcase.py`, `app/seed/demo_fill.py`, `app/seed/hirt.py`, `app/seed/generators.py`, `app/seed/patients.py`, `app/api/demo.py`, `app/api/system.py`, the `showcase_fill` action in `app/lambda_handler.py`, `scripts/push_demo_fill.py`, `scripts/admin_db.py`, the fill's rule in `infra/` | `docs/dev/showcase/fill.md` |
| personal | `app/personal/showcase.py`, `app/api/console_personal.py`, non-persisting reads in `app/personal/insights.py` | `docs/dev/showcase/personal.md` |
| data | `app/api/data.py`, `app/engine/data_catalog.py`, the acting clinic in `app/api/auth.py` / `app/api/scope.py` / `app/hep/api.py::_clinic`, `GET /api/console/workspaces` | `docs/dev/showcase/data.md` |
| links-texts | `app/links.py`, `app/api/links.py`, `app/api/applinks.py`, `app/hep/texts.py`, `app/api/exercise_texts.py`, `app/api/demo_phone.py`, `app/notifications/*`, `app/api/sendblue_webhook.py`, the inbound routing in `app/tasks/service.py`, the `exercise_reminders` action, the link and Sendblue settings in `infra/` | `docs/dev/showcase/links.md` |
| calendar | `app/hep/*` except `texts.py`, `app/api/exercises.py` | `docs/dev/showcase/calendar.md` |
| sports | `app/sports/*` | `docs/dev/showcase/sports.md` |

`backend/openapi.json` is regenerated once, after the streams merge.
