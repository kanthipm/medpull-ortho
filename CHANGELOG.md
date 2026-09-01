# Changelog

## [recovery-copilot 1.4.0] - 2026-09-01

### Added
- **Junction wearable integration** (`app/connectors/junction.py`, `junction_client.py`) — the aggregator chosen for production is live: `POST /api/patients/{id}/wearables/junction/link` creates the patient's Junction user (opaque `client_user_id`, `fallback_time_zone`, `ingestion_start` pinned to the ingestible window) and mints a one-time hosted Link URL; `provider.connection.created|error` events maintain Device rows and a provider snapshot; `daily.data.{activity,sleep,workouts}` summaries and `blood_oxygen` / `respiratory_rate` / `hrv` / `body_temperature(_delta)` timeseries normalize onto `MetricType` with the semantics the engine expects (one resting-HR definition per provider, Apple HRV routed to `HRV_SDNN`, delta vs absolute temperature kept apart, intraday totals never ingested, only `long_sleep` sessions counted as the night); `historical.data.*` events pull the announced window through the API; `.updated` deliveries restate in place by Junction record id, and timeseries samples are keyed on their UTC instant so a DST fall-back hour stays two samples
- **Per-patient wearable lifecycle** — `GET /api/patients/{id}/wearables` (`?refresh=true` re-syncs the snapshot from Junction), `POST …/junction/backfill` (optional Junction re-sync first, clamped to the ingestible window, chunked under the ingest ceiling, recomputes the engine), `DELETE …/junction` (deregisters at Junction, retires the mapping, keeps history, and reports truthfully whether Junction deleted the account); `GET /api/integrations/junction/status` for operators. No route exposes Junction's pre-authenticated Svix portal link
- **`wearable_connections` table** (`app/models/connection.py`) — the only place a Junction user id meets a patient id; webhooks are resolved through it and never through the body, a delivery for an unknown user is recorded as `ignored` and answered 202, and a sandbox account cannot be driven against the production host (409). Junction is given an opaque `client_user_id`, the time zone and a month-granular ingestion floor, never the surgery date
- **Webhook hardening** — bodies over 1 MB are refused (413) before verification; an unverified body is never stored (its size, hash and Svix id are); a non-ASCII signature header reads as a mismatch instead of a 500; every Junction API call is deadline-bounded so a request stays inside the 25 s S3 write-lock TTL on Lambda
- **Console** — the Integrations page leads with the aggregator card (live / needs setup, environment, webhook endpoint and secret state, linked-patient counts, recent deliveries) and labels brands *Via Junction* or *Needs patient app*; every patient record gains a Wearable connection card with Connect (copyable one-time link), Back-fill, Refresh status and Disconnect
- **Lambda secrets** — `JUNCTION_API_KEY_PARAMETER` and `JUNCTION_WEBHOOK_SECRET_PARAMETER` (SSM SecureStrings) alongside the Groq key; `deploy.sh` stores them from the environment or `.env` when present
- 38 Junction tests (normalization semantics, Svix-signed end-to-end deliveries, resolution, out-of-window and implausible handling, historical pulls, link/backfill/disconnect against a fake Junction, unverified-body handling, DST-safe sample identity, chunked back-fill baseline pinning, client back-off, deadlines and paging)

### Changed
- `WearableConnector` contract: `authorize` / `handle_oauth_callback` / `fetch_historical` take the session, `normalize` takes the resolved `PatientContext`, and connectors gain `resolve_patient` / `receive` hooks; the ingest layer gains `partition_by_window` and `ingest_in_batches` for aggregator deliveries (the demo path keeps all-or-nothing rejection)
- `POST /api/integrations/{brand}/connect` answers 409 (link from a patient record) for Junction-reachable brands and 501 for on-device stores; the registry reports six statuses instead of two
- Provider `source_updated_at` stamps are flattened to naive UTC at ingest so a restatement can be ordered against what SQLite hands back
- `make seed` (or a fresh deploy) is not required: the new table is created additively on first request

## [recovery-copilot 1.3.2] - 2026-07-21

### Changed
- **Everyday/Advanced/Clinical tier toggle removed** — supporting evidence is now one "Supporting signals" dropdown: collapsed to a summary line (trajectory · wearable trends · adherence · N flagged), or open with everything in full detail (trajectory chart, deviation drivers, metric cards with next steps and guarded markers, adherence & monitoring); metric data still loads lazily on first open
- **Check-in history redesigned** — the card no longer floats the last patient line as a context-free quote ("Okay, I will."). Each check-in is now a timeline row with a deterministic digest (`app/engine/checkin_digest.py`): the patient's most informative quote (acknowledgments are never selected), topic chips (pain, swelling, fever/chills, sleep, exercises, …), and a reported-trend marker (worse / better / about the same) taken from the patient's own words. Rows expand individually to the full chat transcript; long histories collapse to the 4 most recent (6 new tests, 78 total)

## [recovery-copilot 1.3.1] - 2026-07-21

### Fixed
- **Monitoring days now accrue from RTM enrollment** (the CPT 98975 setup event), not from pre-op device wear — pre-enrollment data still feeds engine baselines but never counts toward 98985/98977 thresholds; unenrolled patients show "monitoring starts after enrollment" instead of a misleading count (this is what made "19/16 days" appear for a day-8 patient)
- **Suggested next action prefers provider-actionable steps** (call, log minutes, approve docs) over passive monitoring-day accrual
- **Review-time tracker counts only engaged time** — pauses while the tab is hidden, stops after 2 minutes without interaction; a chart left open in a background tab no longer accrues billable review minutes
- **Groq failure cooldown** — a failed cloud call (quota exhaustion, outage) trips a 3-minute cooldown with a hard 15s per-call deadline, so pages render instantly on the deterministic fallback instead of hanging for minutes of retries
- **Practice overview "need review" now matches the worklist headline** (high tier only; it previously also counted medium)

### Changed
- **Cloud-first provider chain**: local Ollama is now opt-in (`OLLAMA_URL` empty by default) — the default chain is Groq → deterministic fallback

## [recovery-copilot 1.3.0] - 2026-07-21

### Added
- **P1 RTM platform** (per `recovery-copilot/SPEC.md`): deterministic compliance engine (`app/rtm/readiness.py`) computing per-CPT billing eligibility (98975/98985/98977/98979/98980/98981), suggested next action, and automatic Ready-to-Bill; enrollment tracking (education/consent/baseline); provider time ledger with live-interaction flag; treatment-management actions (call, schedule follow-up, update plan) auto-logged from the action bar; quiet chart-review time tracking from the patient page
- **AI documentation** — encounter notes + monthly RTM summaries with the same validate-or-fallback guardrail pipeline as insights; provider review/approve flow; approved documents pinned against regeneration
- **RTM readiness card** on patient detail, monitoring-days chip per worklist row, and a five-stat practice overview strip (RTM patients, needing review, ready to bill, adherence, estimated revenue)
- Seeded RTM demo states across all 10 patients (Marcus reproduces the spec's "98980 — 6 minutes remaining" card; David/James are Ready to Bill); 15 new tests (69 total), golden tiers untouched

### Changed
- `make seed` required after pulling this change (new tables: rtm_enrollment, rtm_time_logs, rtm_interactions, rtm_documents)

## [recovery-copilot 1.2.1] - 2026-07-21

### Added
- **P1 RTM spec** (`recovery-copilot/SPEC.md`) — Remote Therapeutic Monitoring product spec: enrollment (CPT 98975), daily therapeutic monitoring (98985/98977), provider treatment management with time tracking (98979/98980/98981), AI documentation, compliance engine, billing readiness

### Changed
- **README LLM section corrected** — architecture diagram now shows the full Groq → Ollama → deterministic chain; documented Groq model default (`llama-3.3-70b-versatile`, `GROQ_MODEL`), `OLLAMA_URL` override, the 60s-cached availability probe, and that provider selection is configuration-priority (a failed Groq call falls back to deterministic, not to Ollama)

## [recovery-copilot 1.2.0] - 2026-07-11

### Added
- **Live LLM connection via local Ollama** — auto-detected at :11434 (native API, JSON-constrained, thinking disabled); provider priority Groq → Ollama → deterministic fallback; every narrative now genuinely regenerates on refresh
- **Ask bar** — natural-language questions over the roster with a retrieve → per-patient verify → compose pipeline (prevents cross-patient fact attribution by small local models); answers cite and filter to matching patients
- **Draft with AI** — grounded, editable patient-message drafts in the Message modal
- **Startup insight warmer** — caches generate in a background thread so first loads never block on a cold model; stable patients keep deterministic worklist reasons for speed

## [recovery-copilot 1.1.0] - 2026-07-11

### Changed
- **Console redesigned onto the orthopedic-demo design system** — liquid-glass chrome, gradient canvas, demo risk tokens (rpills, status accents, triage rows), Inter with the demo's weight hierarchy
- **Care action bar restored** — Assign tasks (persists to the patient plan), Message (queued stub until SMS integration), Escalate (in-app care-team notification), each with glass modals and toasts
- **Everyday / Advanced / Clinical tier toggle restored** — gates supporting-signal depth per the original demo
- **Refresh analysis now performs a true refresh** — engine rerun + narrative-cache bust (fresh LLM generation) with shimmer loading overlays across every card
- Micro-animations throughout: staggered card entrances, hover lifts, modal/toast transitions, animated disclosure — all gated by prefers-reduced-motion

## [recovery-copilot 1.0.0] - 2026-07-11

### Added
- **Recovery Copilot Provider Console** (`recovery-copilot/`) — the production-track provider web app for post-surgical recovery monitoring, replacing the orthopedic-demo dashboard a physician flagged as too cluttered
- **Recovery Intelligence Engine** — real statistics in Python (EWMA control charts, CUSUM drift, per-procedure expected recovery curves, trajectory + change-point detection, multi-signal composite index, data-confidence gate, risk tiers with typed reason codes)
- **AI narrative layer** — Groq (free tier, optional) with deterministic fallback; strict JSON contracts, banned diagnostic-language validation, guardrail-sentence enforcement, input-hash caching
- **Provider Worklist + Patient Detail UI** — AI daily briefing, prioritized roster, summary-first patient pages with progressive disclosure (React 19 + Vite + Tailwind)
- **Wearable integration scaffolding** — provider-agnostic connector interface, idempotent webhook ingestion (`/api/webhooks/wearables/{provider}`), normalized observation store, per-provider capability map (Apple-only gait metrics), documented Terra/Junction/HealthKit stubs
- **RTM coverage tracking** (16-of-30 monitoring-day windows), in-app high-priority notifications with SMS/email channel stubs
- **Deterministic 10-patient seed** with golden-tier tests (44-test backend suite)

## [1.2.0] - 2026-05-05

### Added
- **Program selection screen** — patients choose between Sliding Fee Eligibility and Medical Intake on entry
- **Sliding Fee Eligibility intake flow** — full 9-field schema (demographics, household size, income sources, employment, insurance status)
- **Back navigation with value preservation** — tapping back steps to the previous question; existing answers are pre-populated, not erased
- **Back from review returns to last field** — IntakeReview "back" lands on the last answered field for easy edits
- **Address auto-fill** — entering a full address in the street field intelligently skips city/state/zip prompts
- **Field normalization** — all parsed values are deterministically formatted: dates → MM/DD/YYYY, phones → (XXX) XXX-XXXX, ZIP → 5 digits, states → 2-letter code, names/city/street → Title Case
- **Groq API fallback** — automatic fallback to Groq (llama-3.3-70b-versatile) when primary Grok API is unavailable
- **Signature capture screen** — `SignatureCapture.kt` composable for drawn signatures
- **PDF form preview** — `FilledFormPreviewScreen` with print and send actions post-submission
- **PDF fallback generation** — `createFormattedSummaryPdf()` handles forms without a matching PDF template

### Fixed
- "Could not generate PDF file" error for the Sliding Fee form (missing template now falls through to summary PDF)
- Address parser using wrong field IDs for `alsoFills` when prefix didn't match expected pattern
- Duplicate companion object compile error in `IntakeConversationEngine`
- Back button exiting intake instead of navigating to previous question

### Changed
- Welcome screen now routes to Program Selection (not directly to Form Selection)
- Login/register/verify success navigates to Program Selection
- `IntakeConversationEngine` refactored to stateless single-field question/parse API

## [1.1.0] - 2026-04-11

### Added
- Typeform-style one-question-at-a-time intake UI
- Floating chat sidebar FAB
- Coastal Gateway form with 50 fields and complete skip logic
- Consent batch review panel
- Demo mode with Medicaid form, save progress, prefill, PDF export
- Filled form PDF preview with print/send after review submit
- AI model routing: Grok-3-mini for conversation, Groq fallback
- FHIR R4 integration (HAPI FHIR 7.4.0) with neutral healthcare adapter layer
- AWS Cognito auth, S3 storage, Textract OCR, Translate
- HIPAA audit logging

## [1.0.0] - Initial release
