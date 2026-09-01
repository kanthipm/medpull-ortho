# MedPull — Recovery Copilot · Provider Console

The provider-facing web application for post-surgical recovery monitoring.
It answers one question for the care team, every morning:

> **Who needs my attention today, and why?**

AI summaries and prioritization come first; supporting stats stay behind
progressive disclosure. Every LLM narrative is validated in code before it can
reach a screen: diagnostic language (`detect…`/`diagnos…`) is rejected outright
and the deterministic renderer takes its place. The product guardrail sentence,
*monitoring signals for clinician review, not a diagnosis*, is appended in code
to the patient recovery summary and to RTM document bodies, and stands as a
footnote on the worklist and the patient page. The short-form narratives
(worklist reasons, suggested actions, the daily briefing, Ask answers, drafts)
get the validation but not the sentence.

Product direction: **[SPEC.md](SPEC.md)** — the P1 Remote Therapeutic
Monitoring (RTM) spec that this console is the foundation for. Read its
implementation-status table before treating any section of it as shipped.

## Quickstart

Requirements: [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
make setup     # install backend (uv) + frontend (npm) dependencies
make seed      # create + populate the demo database (10 patients, 2,825 observations)
make dev       # API on :8000 + Vite dev server on :5173
```

Single-process demo (serves the built frontend from FastAPI):

```bash
make build && make run     # everything on http://localhost:8000
```

`make test` runs the backend suite (224 tests: seed determinism, engine golden
tiers, baseline stability, guardrail enforcement, API contracts, connector
idempotency and ingest bounds, RTM billing gates, LLM deadline and cooldown
behaviour, static-file containment, AWS persistence). There are no frontend
tests. `make lint` runs ESLint over the frontend and ruff over the backend.

## Deploying

```bash
make deploy      # or: ./infra/deploy.sh
```

Puts the backend on AWS Lambda behind CloudFront, sized to sit inside the
always-free tier — steady-state cost is a few cents a month. Runbook, cost
breakdown and the write-concurrency design: **[infra/README.md](infra/README.md)**.

The application code is unchanged by this: `app/aws/` disables itself when
`S3_BUCKET` is unset, so `make dev` behaves exactly as it always did.

### LLM setup

Provider priority (cloud-first): **Groq → deterministic fallback**, with
local Ollama available strictly as an opt-in middle tier. Selection happens
per call from what's configured and reachable (`app/llm/provider.py`); there
is no other provider — no OpenAI, Anthropic, or xAI code path anywhere.

- **Groq (the cloud model):** set `GROQ_API_KEY` in `.env` (free tier at
  console.groq.com). Model: `llama-3.3-70b-versatile` by default — override
  with `GROQ_MODEL`. Calls go to Groq's OpenAI-compatible chat-completions
  endpoint with JSON response format and retry-after-aware 429 handling.
- **No LLM at all:** the deterministic engine renders narratives from typed
  reason codes.
- **Ollama (opt-in, off by default):** set `OLLAMA_URL` explicitly (e.g.
  `http://127.0.0.1:11434`) to slot a local model between Groq and the
  deterministic fallback — model `qwen3-vl-agent:latest` by default, override
  with `OLLAMA_MODEL`. Availability is probed via `/api/tags` (cached 60s);
  calls use Ollama's native API with `format: json` and thinking disabled.

Error handling: a failed call (rate-limit exhaustion, outage) falls back to the
deterministic renderer for that request and trips a 3-minute cooldown on that
provider, so the rest of the page load skips it instead of paying the same
timeout again. Three *consecutive* completions that parse but fail product
validation arm the same cooldown, because output that can never be shown costs
exactly as much as an outage. After the cooldown one probe call rediscovers the
provider automatically. Cooldowns are per provider, so a cooling Groq routes to
Ollama when it is opted in and to the deterministic renderer otherwise.

The Groq call carries a hard 15-second deadline. It is enforced by streaming the
response and re-checking the clock between chunks, not by an httpx timeout: a
read timeout only bounds the gap between two received bytes, so a slow dribble
resets it forever. The one piece of slack is a socket read already in flight
when the budget runs out, which gets its own timeout to finish or fail. A single
completion therefore cannot outlive roughly 15 seconds plus one attempt, and a
cold page load that needs several completions is bounded by the cooldown rather
than by repeating that wait per call.

All LLM output is validated (JSON contracts, banned diagnostic language,
guardrail sentence where it applies) and silently replaced by the deterministic
version on any violation. Results are cached in the `insights` table under a
hash of the engine's input hash, the risk tier, the check-in digest, the prompt
version and the provider that produced the row; each write trims its own series,
so the table stays bounded. A fallback row written during a transient failure
does not satisfy a key that expected a real model, and is retried on the next
read; a *deliberate* skip of the LLM is keyed as fallback and caches like any
other row. Insight caches warm in a background thread at startup so the first
page load never waits on a cold model (off on Lambda, where the deploy warms
the database once instead).

### AI features

- **Recovery summaries, worklist reasons, suggested actions, daily briefing**
  — regenerated whenever the data (or a Refresh) changes them, and once on the
  first request of each calendar day, because the post-op day is part of the
  engine's input hash. Worklist reasons for low-risk patients are always the
  deterministic renderer: the line is a pure status line ("tracking as
  expected") and the model adds nothing to it.
- **Ask bar** — natural-language questions over the roster ("Who reported
  fever this week?", "Which knee patients are struggling?"). Answers use a
  retrieve → per-patient verify → compose pipeline so a small local model
  can't attribute one patient's symptoms to another, and the worklist filters
  to the cited patients. A verification pass lost to a provider outage is never
  cached as a finding; it degrades to the deterministic answer instead.
- **Draft with AI** — one click drafts a patient message grounded in their
  analytics and their own check-in words; always editable, never auto-sent.

Which of these carry a provenance label on screen, exactly: the recovery
summary, the daily briefing, Ask answers and RTM documents each show an eyebrow
reading "AI …" or "Rules-based …" from the row's `llm_provider`. The draft
returns that field but does not render it, so a deterministic draft still sits
under an "AI drafts are editable" note. Worklist reasons and suggested actions
do not return the field at all, so they carry no label rather than a borrowed
one, and low-risk worklist reasons are the case where that matters most: they
are always deterministic.

## Architecture

```
                    ┌────────────────────────────────────────────┐
 wearables ── webhooks ──► connectors/ ──► observations (canonical store)
 (mocked in v1)     │            │                               │
                    │   Recovery Intelligence Engine (engine/)   │
                    │   baselines · EWMA/CUSUM deviation ·       │
                    │   expected recovery curves · trajectory ·  │
                    │   composite index · confidence gate ·      │
                    │   adherence · risk tiers + reason codes    │
                    │            │                               │
                    │   LLM layer (llm/): Groq → Ollama →        │
                    │   deterministic fallback·validated·cached  │
                    │            │                               │
                    │   REST API (api/) ──► React console        │
                    └────────────────────────────────────────────┘
```

- **infra/** — the AWS deployment: one CloudFormation stack (Lambda + Function
  URL + CloudFront + S3 + Parameter Store) and the scripts that build and ship
  it. The Lambda adapters live in `backend/app/aws/`.
- **backend/** — FastAPI + SQLAlchemy 2 + SQLite. numpy and pandas power the
  analytics. The engine stores one `RiskAssessment` per run and recomputes
  lazily against an input hash over the observation set, the engine version and
  today's date, so a patient recomputes when their data changes and once on the
  first request of each calendar day.
- **frontend/** — React 19 + Vite + TypeScript + Tailwind, styled on the
  MedPull liquid-glass design system (gradient canvas, glass chrome, the
  orthopedic-demo risk tokens). Two primary surfaces: the Worklist
  (prioritized roster + AI daily briefing) and the Patient Detail (AI recovery
  summary, care actions, timeline, check-in conversations, tiered supporting
  signals), plus Integrations and Notification settings.

  - **Care actions** — Assign task, Message, and Escalate live in a glass
    action bar on every patient record. Each one logs an RTM interaction and
    provider time. A task is saved to the patient's plan and nothing more:
    there is no patient-facing surface and no completion tracking, so it cannot
    move the adherence rate, and the endpoint returns `assigned_untracked` so
    the UI does not imply follow-through. Message records intent only (no queue
    behind it). Escalate raises an in-app notification to the patient's
    assigned provider.
  - **Supporting signals** — all evidence lives behind one dropdown:
    collapsed to a summary line by default, or open with everything in full
    detail (trajectory chart, deviation drivers, metric cards with next
    steps, adherence & monitoring). Metric data loads lazily on first open.
  - **Refresh analysis** — reruns the engine, drops this patient's cached
    narratives and the roster briefing so the LLM genuinely regenerates them
    (Ask answers are keyed on the roster, not on one patient, and are left
    alone), and covers each card with shimmer until the new analysis lands.
    Only an explicit Refresh shimmers; ordinary background loads do not.

### The intelligence engine

Two layers, deliberately separated:

1. **Deterministic analytics** (`app/engine/`) — every number on screen is
   computed here (or, for the billing figures, in the equally deterministic
   `app/rtm/`). No number is ever produced by a model.
   - **Vitals** are judged against the patient's own pre-op baseline (EWMA
     control charts + CUSUM drift). That baseline is established once, from the
     record at the time, and then held (`engine/baseline_store.py`): data that
     arrives later is stored, charted and scored, but does not redefine the
     reference it is being scored against. Re-establishing one is an explicit
     operator action (a forced recompute), not something an inbound webhook can
     do by accident.
   - **No pre-op window** (a device connected only after surgery) is a real
     case and is labelled rather than hidden: the engine anchors on the first
     three days from day 2, marks the baseline as not pre-op, and that flag
     travels with every downstream result.
   - **Activity metrics** are judged against a per-procedure **expected
     recovery curve**, so a day-8 knee patient walking 40% of baseline is
     *normal*, not a finding. The comparison comes in two strengths: with a
     pre-op baseline it is absolute ("44% below expected for day 12" means
     exactly that); without one the curve is divided by its own level on the
     anchor days, which cancels the pre-op unit and asks a scale-free question
     about pace instead of capacity. The cards and the flag text say which of
     the two they are reporting.
   - **Staleness** is one window for the whole engine (5 days). A metric that
     stopped reporting keeps its numbers but can no longer raise a flag, weigh
     into the composite, or move a tier, so the risk header and the metric
     cards can never disagree about whether a signal is still reporting.
   - **Coverage-based confidence gates the risk tier**: a patient the engine
     cannot see is "Missing data", never an "On track" verdict it has no
     evidence for. Confidence is the weaker of two coverage dimensions, how
     many recent days reported at all and how much of the key panel is still
     reporting, so three faithful metrics cannot vouch for three dark ones.
     Note what the gate does *not* do: it does not overwrite the individual
     metric cards. A signal that is still reporting shows its own status next
     to its coverage line, so a Missing-data patient can legitimately have a
     "Stable" card reading "1 of 7 days of data" beneath the gated header.

   Output: a risk tier plus typed reason codes.
2. **Narrative layer** (`app/llm/`) — turns the analytics bundle + check-in
   transcripts into the worklist reason, patient summary, suggested actions,
   and roster briefing. Strict JSON contracts, banned-phrase validation
   (`detect…`/`diagnos…`), guardrail-sentence enforcement on the summary and on
   RTM documents, and caching by input hash, so nothing is regenerated until
   the data, the tier, the transcript, the prompt version or the provider
   changes.

### Wearable integration scaffolding

No live integrations ship in v1, by design — but the seams are real:

- `connectors/base.py` — provider-agnostic `WearableConnector` interface
  (authorize / OAuth callback / webhook registration / historical fetch /
  normalize).
- `POST /api/webhooks/wearables/{provider}` — signature check, raw event
  persistence, normalization, **idempotent upsert** by dedupe key (wearable
  providers re-deliver, restate and back-fill as a matter of course), engine
  recompute. Signature verification fails closed: an unknown provider or a
  configured scheme with no secret is a rejection, never a pass-through. Svix
  (Junction) and Terra verifiers are written and unit-tested, but neither
  aggregator is in `connectors/registry.py` yet, so those paths answer 501
  before verification is reached. The demo `mock` endpoint is deliberately
  unsigned and stamps its rows `mock`: a `provider` field in the body is
  recorded as provenance, never obeyed, so an anonymous POST cannot write into
  a real connector's keyspace.
- `connectors/ingest.py` is the one choke point every connector's output passes
  through, and it bounds what may land: a batch ceiling (5,000 rows), an
  ingestible date window per patient (60 days before surgery through tomorrow,
  rejected all-or-nothing with a 422 and a recorded failed webhook event), and
  a physiological plausibility range per metric. A provider tombstone
  soft-deletes rather than removing the row, so the retraction survives
  re-delivery, and all three readers (the engine's day series, the RTM
  monitoring count, and the patient chart endpoint) filter it out.
- `connectors/capabilities.py` — per-provider metric capability map. Gait
  metrics (walking speed/asymmetry/steadiness) are Apple-exclusive. Be precise
  about how that reaches the UI: there is no per-patient capability lookup. A
  patient's chart carries a card for each signal that patient's own device
  actually reported, so gait cards are simply absent for everyone else, and the
  capability map itself is surfaced on the Integrations page.
- `terra.py` / `junction.py` / `apple_healthkit.py` — documented stubs
  capturing what each production integration requires (BAAs, webhook
  signatures, the iOS companion-app constraint for HealthKit). Every method
  raises `NotImplementedError`.

Recommended production path (researched mid-2026): one aggregator — **Terra**
(~$399/mo flat, BAA, widest coverage) or **Junction** fka Vital
($0.50/user/mo, bundles labs) — plus a thin Apple HealthKit path for gait.
Avoid: Human API (absorbed into LexisNexis), Metriport (exited wearables),
Google Fit (shut down; Fitbit moves to the Google Health API in 2026).

### RTM platform (P1)

The **[SPEC.md](SPEC.md)** P1 *provider-side* workflows are implemented end to
end. The patient-side half of the spec (conversational enrollment and daily
check-ins) is not built; SPEC.md's status table says which is which.

- **Compliance engine** (`app/rtm/readiness.py`) — deterministic, never the
  LLM: enrollment (CPT 98975), monitoring-day thresholds (98985/98977 via
  `app/rtm/coverage.py`'s 16-of-30 window), treatment-management time +
  live-interaction requirements (98979/98980/98981), per-CPT billing
  eligibility, a suggested next action, and an automatic **Ready to Bill**
  state. Every gate measures the same rolling 30-day window, floored at the
  patient's enrollment, so work done before RTM started is never billable and no
  gate flips at midnight on the 1st while its neighbour holds. (Minutes and
  documentation are floored at the enrolling instant; monitoring days at the
  enrollment date, because a monitoring day is a calendar day.)
  98975 is offered for the 30 days following enrollment and never again.
  Known limitation, documented in the module rather than hidden: 98980/98981
  are defined per calendar month, and a rolling window is not the same thing,
  so a practice billing off this card at each month end could claim one
  accrual twice. Closing that needs a record of what has actually been claimed,
  which a card recomputed per request cannot infer; the card reports the window
  it measured so the same accrual is recognisable as the same accrual.
- **Treatment management** — Call / Follow-up / Update plan join the action
  bar; every action auto-logs an interaction and treatment-management time,
  and time on a patient record is quietly tracked as chart review.
- **AI documentation** (`app/llm/documentation.py`) — encounter notes and
  monthly RTM summaries (two of the five document types SPEC.md §7 lists),
  drafted by the LLM under the same validation + deterministic-fallback
  discipline as insights; providers review and approve, and approved documents
  are never regenerated. The "monthly" summary is titled with the calendar month
  but its numbers cover the window the billing ladder actually scores: a rolling
  30 days, floored at the patient's enrollment, read from the same function, so
  a signed note cannot claim minutes the ladder did not count.
- **UI** — an RTM readiness card on every patient page (monitoring progress,
  enrollment checklist, billing chips, documentation behind a disclosure), a
  monitoring-days chip per worklist row, and a five-number practice overview
  strip (patients, high risk, ready to bill, adherence, estimated revenue),
  every number of it read from `GET /api/practice/overview` and the revenue
  figure labelled "demo rates".

## Demo roster

Seeded deterministically (`app/seed/`): 10 patients across 7 orthopedic
procedures. Marcus Reyes (TKA day 8) carries a possible-infection signal
pattern — coupled RHR/temperature rise, falling HRV, activity collapse — that
exercises every part of the engine, including the high-priority notification
path. Priya Nair's barely-worn watch exercises the missing-data gate.

Demo webhook (full ingestion path against the seeded DB). Dates are bounded per
patient, so use a recent one; the seed is generated relative to the day it ran:

```bash
curl -X POST localhost:8000/api/webhooks/wearables/mock \
  -H 'Content-Type: application/json' \
  -d "{\"patient_id\":\"james\",\"records\":[{\"metric_type\":\"steps\",\"date\":\"$(date +%F)\",\"value\":9100,\"unit\":\"count\"}]}"
```

A date outside the patient's ingestible window, or a physiologically impossible
value, comes back 422 with the bounds in the message and is recorded as a
failed webhook event.

## Not in v1

- **Auth.** Deliberately open for demos. All 30 API routes are unauthenticated,
  write paths included (RTM time, document approval, escalations, the demo
  webhook). Running locally, `/docs`, `/redoc` and `/openapi.json` are open too;
  on AWS only `/api/*` is routed to the function, so those three are not
  reachable there. The demo server does contain the SPA catch-all to the built
  bundle and 404s unmatched `/api/*` paths rather than falling through to
  index.html, so it will not serve the database or read outside the bundle. That
  is containment, not authentication.
- **Real integrations.** See the scaffolding section above.
- **SMS/email delivery.** Channel stubs record intent; only in-app
  notifications are deliverable, and the preferences API refuses to enable a
  channel that would deliver nowhere.
- **The patient side of the product.** There is no chatbot, no patient app and
  no write path for check-ins or enrollment outside the seed. Check-in
  transcripts on screen are seeded conversations.
- **FHIR export, multi-clinic tenancy.**
