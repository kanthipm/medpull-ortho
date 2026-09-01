# Runtime architecture and unit economics of AI in the MedPull Recovery Copilot backend (AWS serverless + LLM layer)

## Summary

The runtime economics of this product are lopsided in a useful way: at 1,000 patients the entire AI bill is ~$90-150/month on Groq's llama-3.3-70b ($0.59/$0.79 per MTok) and the whole AWS stack another ~$50-100, so cost optimization is a non-goal — the design problems are latency, reliability, and compliance. The winning runtime shape is event-driven precomputation: webhook → SQS → worker Lambda recomputes deterministic analytics synchronously (<1 s/patient) and regenerates narratives asynchronously, a nightly EventBridge Scheduler job reconciles the roster and pre-generates briefings at 50% batch pricing, and the clinician page load reads only precomputed rows — the only synchronous LLM call left is streaming ask-the-roster. Your measured dependency stack (numpy+pandas+scipy = 144 MB installed, 226 MB total site-packages) fits Lambda's 250 MB zip limit only because the build already strips scipy; statsmodels or PyMC forces a container image or Fargate, and SnapStart (Python 3.12+, ~$7/month) eliminates the scientific-Python cold start. The data layer must move off SQLite-in-S3-with-a-lock-file — which serializes all writes and cannot survive concurrent webhooks or a second tenant — to Postgres (Aurora Serverless v2 at $15-45/month or RDS t4g.micro at $12); Timestream is formally end-of-support and DynamoDB fights your pandas access patterns. The existing input-hash cache and Groq→deterministic fallback are the right primitives but need canonicalized hash inputs, hard client-side deadlines, jittered 429/5xx-only retries, a real half-open circuit breaker, and PHI-free envelope logging. The two go/no-go gates before selling to practices are a Groq BAA (or rerouting PHI traffic to Bedrock/Anthropic-with-BAA) and row-level tenant isolation with practice_id + Postgres RLS threaded through the DB, cache keys, and logs.

## Findings

### Your scientific stack fits the Lambda zip limit today, but with ~25% headroom left — statsmodels/PyMC will not fit
*[strong]*

Measured in the repo's own venv: numpy 24 MB + scipy 71 MB + pandas 49 MB installed; full site-packages is 226 MB against Lambda's hard 250 MB unzipped limit (50 MB zipped via API/console; container images go to 10 GB uncompressed). Your infra/build-lambda.sh already excludes scipy and boto3 and targets aarch64/manylinux_2_28, so the shipped artifact is roughly 150-190 MB unzipped (Linux wheels add ~25-35 MB of OpenBLAS .libs that macOS wheels omit). Adding statsmodels (~40 MB + patsy) is borderline-over; PyMC (pytensor + arviz, 250 MB+, wants a compiler at runtime) is categorically wrong for Lambda zip. The escape hatches, in order: drop rarely-used subpackages, move to a container image (10 GB, with 2023-era lazy chunk loading cold starts are comparable to zip), or move heavy stats to Fargate.

> Local measurement of backend/.venv site-packages + infra/build-lambda.sh; AWS Lambda quotas: docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html

### Lambda limits relevant to this workload: 15-min max, memory-CPU coupling at 1,769 MB = 1 vCPU, /tmp 512 MB-10 GB
*[strong]*

Timeout hard cap 900 s; memory 128 MB-10,240 MB in 1-MB steps with CPU allocated proportionally (1 vCPU at 1,769 MB — numpy/pandas benefit from ≥1,769 MB, and BLAS threading only helps above ~3,538 MB); /tmp configurable 512 MB-10,240 MB (paid above 512 MB at $0.0000000309/GB-s); 6 MB sync payload / 200 MB streamed; 5 layers max, layers count against the same 250 MB unzipped cap (a 'numpy layer' does not buy extra room — container image is the real escape hatch). Your CloudFormation currently sets Timeout: 30 on the API function, which is correct for interactive traffic and correctly forces batch work elsewhere.

> docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html; repo infra/cloudformation.yaml (Timeout: 30, arm64, python3.12)

### SnapStart now supports Python 3.12+ and is the right cold-start fix for a numpy/pandas Lambda — but it excludes EFS and >512 MB /tmp
*[strong]*

SnapStart supports Python 3.12+ (and Java 11+, .NET 8+); it snapshots the initialized microVM so the 2-6 s numpy/pandas import cost disappears, giving sub-second resumes. Python/.NET pricing: $0.0000015046 per GB-s of snapshot cache + $0.0001397998 per GB restored — a 1,769 MB function cached 24/7 costs ~$6.90/month/version, trivial. Constraints that matter to you: zip-only (no container images), published versions/aliases only, and no EFS and no ephemeral storage >512 MB — so SnapStart and SQLite-on-EFS are mutually exclusive. Provisioned concurrency is the alternative at $0.0000041667/GB-s ≈ $5.47/month per always-warm 512 MB instance ($19/month at 1,769 MB); for a low-traffic clinician console, SnapStart is cheaper and sufficient.

> docs.aws.amazon.com/lambda/latest/dg/snapstart.html; aws.amazon.com/lambda/pricing/

### Amazon Timestream for LiveAnalytics is reaching end of support — it is off the table
*[strong]*

AWS's own product page now banners: 'For similar capabilities to Amazon Timestream for LiveAnalytics, please consider Amazon Timestream for InfluxDB.' LiveAnalytics stopped onboarding new customers (announced 2025) and is being wound down. Timestream for InfluxDB is a managed always-on instance (db.influx instances, ~$60+/month minimum) — overkill for 20 metrics/patient/day. This settles the 'Timestream vs Postgres' question: Postgres with a plain time-partitioned observations table. At your volume (1,000 patients × 20 obs/day = 600 K rows/month, ~1.8 M live rows in a 90-day window, well under 1 GB) you don't even need pg_partman — a composite index on (patient_id, metric, observed_at) is enough for years.

> aws.amazon.com/timestream/ (end-of-support banner, fetched 2026-07-31)

### Aurora Serverless v2 can now scale to 0 ACU; realistic Postgres cost at 1,000 patients is $15-45/month
*[strong]*

Aurora Serverless v2 PostgreSQL: $0.12/ACU-hour (Standard; $0.156 I/O-Optimized), storage $0.10/GB-month, I/O $0.20 per million ops, and 0 ACU minimum with auto-pause — resume from 0 takes ~15 s, so keep 0.5 ACU floor during clinic hours. Cost sketch: 0.5 ACU × 12 h/day ≈ $22/month; always-on 0.5 ACU ≈ $44/month; your storage is <1 GB. Alternative: plain RDS Postgres db.t4g.micro ≈ $12/month + storage, no serverless resume latency, no per-second granularity. DynamoDB would be even cheaper on paper (600 K writes = $0.38/month at $0.625/M writes, reads $0.125/M, storage $0.25/GB-month) but is a poor fit: your engine loads per-patient 90-day windows into pandas and runs cross-metric joins — relational access patterns, SQL migrations, and RLS multi-tenancy all favor Postgres.

> aws.amazon.com/rds/aurora/pricing/; aws.amazon.com/dynamodb/pricing/on-demand/

### The current SQLite-in-S3-with-lock-file design is the single biggest architectural liability
*[strong]*

cloudformation.yaml shows S3_DB_KEY: db/recovery.db and S3_LOCK_KEY: db/recovery.db.lock — the Lambda downloads the whole SQLite file, mutates it, and uploads it back under an advisory S3 lock. This serializes all writes globally, loses writes on crash between download and upload, makes concurrent webhook ingestion impossible, and cannot express tenant isolation. SQLite-on-EFS would fix durability but not concurrency (SQLite over NFS locking is fragile, one writer at a time, and EFS is incompatible with SnapStart). This is fine for a demo; it must be replaced with Postgres before the first paying practice or the first real wearable webhook feed.

> repo infra/cloudformation.yaml lines ~229-231; SQLite documented NFS-locking caveats

### LLM cost is a rounding error: roughly $0.003/patient/day on Groq llama-3.3-70b — reliability and latency, not cost, should drive the design
*[strong]*

Groq current prices: llama-3.3-70b-versatile $0.59 in / $0.79 out per MTok (394 tok/s), llama-3.1-8b-instant $0.05/$0.08, and a 50% batch discount. Your daily per-patient narrative set (reason line + recovery summary + suggested actions ≈ 4 K input, 500 output tokens) costs ≈ $0.0028/patient/day ≈ $0.085/patient/month on the 70B. Monthly LLM totals including roster briefing, ask-the-roster, drafts, and monthly RTM notes: ~$10-15 at 100 patients, ~$90-150 at 1,000, ~$900-1,500 at 10,000. Even regenerating every narrative on every data change only ~2-3× these numbers. Routing routine reason lines to llama-3.1-8b-instant cuts the daily-narrative line item ~10× (to <$10/month at 1,000 patients) but saves almost nothing in absolute terms — do it for latency, not cost.

> groq.com/pricing (fetched 2026-07-31); token estimates from the described analytics-bundle prompt shapes

### Cross-provider price ladder (July 2026): Groq 8B → GPT-5-nano → Groq 70B → Haiku 4.5 → Sonnet 5
*[strong]*

Per MTok in/out: Groq llama-3.1-8b $0.05/$0.08; OpenAI gpt-5-nano $0.05/$0.40 (cached input $0.005); gpt-5-mini $0.25/$2.00; Groq llama-3.3-70b $0.59/$0.79; Anthropic Claude Haiku 4.5 $1/$5; Claude Sonnet 5 $3/$15 (intro $2/$10 through 2026-08-31); gpt-5.1 $1.25/$10. Batch discounts: 50% at Groq, OpenAI, and Anthropic alike. Anthropic prompt caching: reads ~0.1×, writes 1.25× (5-min TTL) — break-even at two hits. Bedrock is partner-priced; current-generation Claude on Bedrock tracks first-party rates and Bedrock batch is also -50%, but verify per-model (the visible page showed legacy Claude 3.5 at a premium $6/$30). For your fallback tier, Haiku 4.5 as the 'complex case' model behind Groq costs pennies at your volumes and brings a BAA-eligible provider (via Bedrock or Anthropic enterprise) into the chain.

> groq.com/pricing; developers.openai.com/api/docs/pricing; Anthropic pricing via claude-api skill (cached 2026-06-24); aws.amazon.com/bedrock/pricing/ (partial)

### Input-hash caching is already the right primitive, but it silently degrades to 0% hit rate unless the hash is over canonicalized semantic inputs
*[moderate]*

Three pitfalls with content-hash caches like yours: (1) any timestamp, run-id, or float jitter in the analytics bundle changes the hash every recompute even when nothing clinically changed — hash a canonical projection (sorted keys, rounded metrics, no generated_at fields); (2) the hash must include prompt-template version and model id, or a prompt edit serves stale text and a model swap poisons A/B comparisons; (3) since a new observation arrives ~daily per patient, cross-day hits are structurally ~0 — the cache's real job is intra-day dedupe (page reloads, multiple clinicians) plus 'nothing new since yesterday' patients (missed check-ins, ~20-30% of days in RTM practice). Add negative caching for the deterministic-fallback outputs too, and store (hash, model, prompt_version, created_at, token_usage) so cache rows double as your cost ledger.

> Analysis of the described cache design; standard content-addressed-cache failure modes; RTM adherence rates from CMS RTM billing literature (16-day/30 requirement)

### Event-driven recompute beats both nightly-only and on-demand-at-page-load; the deterministic engine is cheap enough to run on every webhook
*[strong]*

Your deterministic pass (EWMA/CUSUM, curves, composite index) over a 90-day, 20-metric window is sub-second per patient in numpy — so recompute analytics synchronously in the webhook consumer and enqueue narrative regeneration asynchronously. Pattern: wearable webhook → API Lambda returns 200 immediately → SQS standard queue (backpressure + retry + DLQ; ~$0.40/M requests, first 1 M free — effectively $0 at your scale) → worker Lambda with batch size 10 and a per-patient debounce (skip if recomputed <5 min ago) → write analytics rows → enqueue LLM narrative job. Nightly EventBridge Scheduler run (free under 14 M invocations/month) remains as the reconciler: full-roster recompute, next-day roster briefing pre-generation via a 50%-off batch API, and drift detection. Page load then reads only precomputed rows — no analytics, no LLM on the request path except 'ask the roster', which should stream.

> aws.amazon.com/eventbridge/pricing/ (Scheduler 14M free, $1.00/M after); SQS standard pricing; engine complexity from backend/app/engine modules

### A 1,000-patient nightly batch does NOT fit one 15-minute Lambda once narratives are included — fan out via SQS, not Step Functions or AWS Batch
*[strong]*

Deterministic recompute at ~0.5-1 s/patient is 8-17 min for 1,000 patients — already at or over the 900 s cap, and LLM narrative calls at 1-3 s each blow far past it. The cheapest fix is the one you already need for webhooks: the scheduler Lambda enumerates patient IDs into SQS (or uses S3-manifest chunking), and the same worker Lambda drains it with reserved concurrency ~10-20 (stays polite to Groq rate limits). Step Functions distributed Map works but adds $25/M state transitions and a second orchestration surface for no benefit at this scale. AWS Batch/Fargate is warranted only when per-patient compute exceeds ~5-10 min (e.g. future PyMC posterior sampling) — Fargate Spot at ~$0.012/vCPU-hr is then the target, launched from the same queue.

> Arithmetic on Lambda 900 s cap (docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html); Step Functions/Fargate published pricing

### Total infrastructure + AI cost: ≈$30/mo at 100 patients, ≈$150-250/mo at 1,000, ≈$1,100-2,000/mo at 10,000
*[moderate]*

At 1,000 patients: LLM $90-150 (Groq 70B, un-routed); Aurora Serverless v2 $15-45; Lambda compute ~$1-5 (nightly 1,000 × 2 s × 1.8 GB ≈ 108 K GB-s/month ≈ $1.80 after free tier, API traffic mostly inside the 400 K GB-s free tier); SQS/EventBridge ≈ $0; S3+CloudFront ≈ $2-5; SnapStart ≈ $7. At 100 patients everything except the DB rounds to free tier: ≈$25-40. At 10,000: LLM $900-1,500, DB 1-2 ACU sustained ≈ $90-175, Lambda ≈ $20-40, total ≈ $1,100-2,000 — i.e., $0.11-0.20 per patient per month against RTM reimbursement of roughly $50+/patient/month (CPT 98975-98981), a gross margin non-issue. Optimization effort should go to reliability and clinician latency, not COGS.

> Composed from aws.amazon.com/lambda/pricing/, aws.amazon.com/rds/aurora/pricing/, groq.com/pricing; RTM CPT reimbursement approximate

### The Groq→deterministic fallback with cooldown is the right shape; it needs a hard deadline, jittered retry on 429/5xx only, and half-open probes
*[moderate]*

Evaluate: silent fallback on contract violation is correct for a clinical product (never show unvalidated text), but three gaps are typical of this design. (1) Timeouts: set a per-call budget — 3-5 s for interactive paths, 20-30 s for batch — enforced client-side (httpx timeout), because your 30 s Lambda timeout plus CloudFront's origin read timeout means a hung Groq call kills the whole page; the deterministic renderer must be reachable within the page budget. (2) Retries: retry once with full jitter on 429/5xx/connect errors only, honoring Retry-After; never retry 4xx contract failures (they're deterministic) and never retry inside the interactive path more than once. (3) The cooldown should be a real circuit breaker: trip after N consecutive failures, half-open with a single probe per interval, and expose breaker state as a metric so a Groq outage is visible, not silent. Because output is cached by hash, a provider outage mostly serves yesterday's cached narratives — label them with generated_at so clinicians see staleness.

> Standard SRE circuit-breaker practice applied to the described design; Groq 429/Retry-After semantics

### Observability without PHI: log envelope metadata to CloudWatch, keep prompts/completions only in the BAA-covered database
*[moderate]*

Per LLM call, log: request id, tenant id, patient id as an opaque surrogate key (not name/MRN — even under a BAA, minimize), task type, model id, prompt-template version, input hash, token usage (in/out/cached), latency ms, HTTP status, validation outcome (pass / banned-language / schema-fail / guardrail-missing), fallback reason, cache hit/miss, and breaker state. Do NOT log prompt or completion bodies to CloudWatch: transcripts and narratives are PHI, CloudWatch is HIPAA-eligible only under your AWS BAA and with disciplined access control, and log groups leak through consoles, subscriptions, and Grafana. Store bodies (when needed for QA) as rows in Postgres with tenant-scoped access and retention. Emit CloudWatch EMF metrics for: fallback rate, validation-failure rate by type, p50/p95 latency per task, daily token spend per tenant. Alarm on fallback rate >10% over 15 min.

> HHS HIPAA Security Rule minimum-necessary principle; AWS HIPAA-eligible services list (CloudWatch, Lambda, S3, RDS, SQS all eligible under BAA)

### PHI flowing to Groq without a BAA is the compliance hole in the current AI chain
*[moderate]*

Patient check-in transcripts and metric bundles are PHI. Sending them to Groq's standard API makes Groq a business associate; HIPAA requires a signed BAA before that traffic flows. Groq advertises enterprise/HIPAA options but a BAA is not part of the self-serve tier — this must be verified and papered before go-live with real patients. BAA-clean alternatives that preserve your unit economics: Amazon Bedrock (HIPAA-eligible under the AWS BAA you already need, serves Llama 70B-class and Claude Haiku), or Anthropic first-party with an enterprise BAA. This is a go/no-go gate for selling to practices, independent of architecture.

> HIPAA business-associate rule (45 CFR 160.103); AWS HIPAA-eligible services documentation; Groq public pricing pages carry no self-serve BAA offer

### Multi-tenancy: shared Postgres with practice_id + RLS is the right default; per-tenant databases only as an enterprise SKU
*[moderate]*

For selling to multiple practices: pooled model — every table carries practice_id, Postgres Row-Level Security enforces it (SET app.current_tenant per request from the JWT; policies USING (practice_id = current_setting('app.current_tenant')::uuid)), one Aurora cluster, one schema, one migration path. This is HIPAA-compatible: HIPAA requires access controls and auditability, not physical separation. Silo (database-per-tenant) buys blast-radius isolation, per-tenant backup/restore/delete, and satisfies hospital-system procurement checklists — offer it as a premium tier later; running N Aurora clusters at $15-45 each erases margins at small-practice price points. Critical: RLS is meaningless in the current SQLite design, and tenant id must also partition the LLM cache keys, SQS message attributes, and log fields — cross-tenant cache hits on identical hashes would leak one practice's narrative text to another.

> AWS SaaS multi-tenant data-partitioning guidance (pool vs bridge vs silo); Postgres RLS documentation; HIPAA Security Rule access-control standards

### Precomputation and warming: pre-generate at data-change time and nightly; pre-warm only the roster briefing; SnapStart replaces code-level warmers
*[strong]*

Warming strategy in three layers. (1) Narrative precomputation: generate on data-change (webhook consumer) and in the nightly batch at 50% batch pricing, so every page load is a cache read — the clinician page needs zero LLM calls. (2) The one latency-sensitive generated-fresh artifact, the daily roster briefing, is pre-generated by the nightly job for 7-8 am clinic open; regenerate on material tier changes during the day. (3) Cold starts: SnapStart on the API function eliminates the numpy import penalty; do not build EventBridge 'ping' warmers (they only keep one execution environment warm and SnapStart obsoletes them). If you later adopt Anthropic for interactive ask-the-roster, prompt caching (reads 0.1×, min 1,024-2,048 tokens cacheable depending on model, 512 on Opus 5) makes the stable system-prompt + tool schema effectively free across a clinician session.

> docs.aws.amazon.com/lambda/latest/dg/snapstart.html; Anthropic prompt-caching economics via claude-api skill; Groq/OpenAI/Anthropic batch discounts

### Latency budgets that make the console feel instant and the numbers that support them
*[moderate]*

Targets: page load (worklist/patient view) < 300 ms server-side — pure Postgres reads of precomputed rows (~5-20 ms) + SnapStart-resumed Lambda; 'ask the roster' first token < 1.5 s, full answer < 8 s — Groq's 394 tok/s on 70B means a 300-token answer streams in <1 s once first token lands, so use Lambda response streaming (200 MB streamed limit, 6 MB non-streamed) through CloudFront; drafted patient message < 3 s or fall back to deterministic template with an 'AI unavailable' badge; webhook ack < 500 ms (enqueue only). Batch paths have no latency budget — only the 24 h batch-API completion window, which comfortably precedes the next clinic day.

> groq.com/pricing throughput figures; Lambda response streaming limits (docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)


## Implications for backend

- backend/infra/build-lambda.sh's scipy exclusion is currently load-bearing for the 250 MB limit — any engineer re-adding scipy imports to app/ (the grep guard catches this) or adding statsmodels forces the container-image migration; plan that migration before the dependency need arrives, not after a failed deploy.
- The engine modules (baseline.py, deviation.py, composite.py, etc.) must become callable per-patient with a bounded 90-day window read from Postgres, not from a whole-file SQLite load — the worker Lambda and the API Lambda should share this code path so precomputed and ad-hoc numbers can never diverge.
- The FastAPI request path should be rewritten to read precomputed analytics_snapshots + narratives rows only; any endpoint that currently computes on demand becomes a fallback for cache-miss with an explicit slow-path budget, and 'ask the roster' moves to a Lambda response-streaming endpoint.
- The LLM client layer needs four additions that are code, not config: canonical-projection hashing (excluding timestamps, including model+prompt_version+tenant), a circuit breaker object persisted across warm invocations, per-call envelope logging with zero PHI fields, and a batch-API submission path for the nightly job.
- Every table, SQS message attribute, cache key, and log line grows a practice_id now, even while there is one tenant — retrofitting tenant scoping into a live clinical dataset is far more dangerous than carrying an always-'default' column.
- The 30 s Lambda timeout and CloudFront origin timeout define the interactive budget: the Groq client must enforce its own 4-5 s deadline so the deterministic fallback renders within the page load rather than after the gateway has already timed out.

## Recommendation
**Adopt an event-driven precompute architecture on your existing Lambda footprint: webhook→SQS→worker recompute with narratives regenerated asynchronously and cached by canonical input hash; nightly EventBridge Scheduler reconciliation fanning out through the same SQS queue; Postgres (Aurora Serverless v2, 0.5 ACU floor during clinic hours) replacing SQLite-in-S3 with practice_id + RLS from day one; SnapStart on the Python 3.12 API function; Groq llama-3.3-70b as primary model with the deterministic renderer as fallback — hardened with client-side deadlines, 429/5xx-only jittered retry, and a half-open circuit breaker — and PHI routed through a BAA-covered provider (Groq enterprise BAA or Bedrock) before first real patient data.**

AI spend is $0.10-0.20/patient/month against ~$50/patient/month RTM reimbursement, so nothing should be architected around token cost; the binding constraints are the 250 MB Lambda package ceiling you are already touching (226 MB site-packages measured locally), the 900 s Lambda cap that a 1,000-patient nightly batch overruns, the write-serializing SQLite-in-S3 lock that cannot absorb webhook traffic or a second tenant, and HIPAA obligations that currently have PHI flowing to a provider without a confirmed BAA. Event-driven precomputation makes every clinician page load a pure database read (the deterministic engine is fast enough to run on every webhook), the nightly batch at 50% batch-API pricing keeps briefings fresh for clinic open, and Postgres+RLS is the only option on the table that simultaneously serves the pandas access patterns, multi-tenant isolation, and a sane migration story — Timestream is end-of-support and DynamoDB fits neither the analytics reads nor RLS.

**Do NOT:**
- Do not adopt Timestream in any form — LiveAnalytics is end-of-support and Timestream-for-InfluxDB's always-on instance pricing is absurd for 20 obs/patient/day; a time-indexed Postgres table is correct.
- Do not call the LLM synchronously during clinician page load for worklist lines or summaries — precompute and cache; the only synchronous LLM path should be streaming ask-the-roster.
- Do not bring PyMC (or even statsmodels casually) into the Lambda zip — the 250 MB unzipped cap is already 90% consumed; heavy stats goes to a container image or Fargate task fed by the same queue.
- Do not build EventBridge ping-warmers or buy provisioned concurrency for the console — SnapStart at ~$7/month solves the numpy cold start; provisioned concurrency only if p99 double-digit-ms is ever contractually required.
- Do not use Step Functions or AWS Batch for the nightly job at this scale — SQS fan-out with reserved worker concurrency is simpler, free, and doubles as the webhook path; revisit only when per-patient compute exceeds ~5 minutes.
- Do not ship multi-tenancy as database-per-practice by default — pooled Postgres with RLS is HIPAA-compatible and margin-preserving; sell silo isolation as an enterprise tier later.
- Do not log prompts, completions, or transcripts to CloudWatch — envelope metadata only; bodies live in Postgres under the BAA with tenant-scoped access.
- Do not regenerate narratives on a timer when the input hash is unchanged, and do not let timestamps or float jitter into the hash — that converts your cache into a 0%-hit-rate cost multiplier.

**Sequencing:**
- 1. (Compliance gate, ~0 code) Confirm Groq enterprise BAA or decide to route PHI-bearing calls via Bedrock; sign AWS BAA covering Lambda/S3/RDS/SQS/CloudWatch. Blocks real-patient go-live. [days, mostly legal]
- 2. (1-2 wks) Stand up Postgres (Aurora Serverless v2 Standard, 0.5 ACU floor; or RDS t4g.micro to start) with SQLAlchemy migrations: observations(practice_id, patient_id, metric, observed_at, value) indexed on (practice_id, patient_id, metric, observed_at), plus analytics_snapshots and narratives(input_hash, model, prompt_version) tables. Port the S3-SQLite loader; keep SQLite for local dev.
- 3. (1 wk) Ingestion path: webhook endpoint acks <500 ms and enqueues to SQS; worker Lambda (same artifact) with batch size 10, per-patient 5-min debounce, DLQ + alarm; deterministic recompute inline, narrative jobs enqueued behind it.
- 4. (2-3 days) Canonicalize the cache: hash sorted/rounded semantic fields only, include model id + prompt_version in the key, add tenant id, add stale-while-revalidate serving with a generated_at badge in the UI.
- 5. (2-3 days) Nightly EventBridge Scheduler job: enumerate roster into SQS, workers recompute + pre-generate next-day briefings and stale narratives via provider batch API (50% off); reconciliation metrics emitted.
- 6. (2 days) Reliability hardening: httpx client deadlines (4 s interactive / 25 s batch), single jittered retry on 429/5xx honoring Retry-After, circuit breaker with half-open probe, breaker-state + fallback-rate CloudWatch metrics and a >10%/15-min alarm.
- 7. (1-2 days) Enable SnapStart on published versions of the API function; measure p50/p95 page load; verify no EFS//tmp>512MB dependency.
- 8. (1 wk) Multi-tenancy: practice_id through schema, JWT claim → SET app.current_tenant, RLS policies on every table, tenant in cache keys and log envelope; integration test that tenant A cannot read tenant B by any path.
- 9. (later, when needed) Model routing (8B for reason lines, 70B/Haiku for summaries and ask-the-roster) and a container-image or Fargate lane for statsmodels/PyMC when predictive-risk work starts.

## Open questions

- Does Groq's enterprise tier actually offer a signed BAA today, and at what minimum commitment? If not, does routing PHI-bearing calls to Bedrock (Llama 3.3 70B or Claude Haiku 4.5) meet the latency budget that Groq's 394 tok/s currently underwrites?
- What fraction of patient-days produce no new data (missed check-ins, wearable gaps)? This sets the real cross-day cache hit rate and whether nightly narrative regeneration should skip unchanged hashes entirely.
- Which wearable vendors' webhooks are actually planned (Terra, Vital, direct HealthKit sync?) — their delivery semantics (at-least-once? batched backfills?) determine debounce and idempotency-key design in the SQS consumer.
- Is scale-to-zero Aurora acceptable for after-hours 'ask the roster' use (~15 s resume), or do on-call clinicians require an always-on 0.5 ACU floor ($44/mo)?
- When predictive risk arrives, is it PyMC-class Bayesian modeling (forces Fargate/Batch lane) or gradient-boosted survival models that fit a Lambda container image? This decides whether to build the container pipeline now.
- Bedrock's current Claude Haiku 4.5 and Llama 3.3 70B on-demand prices in us-east-1 (the fetched pricing page surfaced only legacy Claude 3.5 rows at premium extended-access pricing) — verify before committing the BAA-path cost model.
- Will conversational SMS check-ins (roadmap) run on the same fallback chain? A multi-turn conversation cannot silently fall back to a deterministic renderer mid-dialogue, so that feature needs its own reliability design (likely queue-and-resume rather than fallback-text).