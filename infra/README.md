# Recovery Copilot on AWS

The provider console, deployed to run inside AWS's **always-free** tier — not
the 12-month trial tier, the allowances that never expire. Steady-state cost
for the demo is a few cents a month, and that is S3 request charges.

```bash
./infra/deploy.sh
```

That builds the Lambda package, deploys the stack, uploads the SPA, seeds the
demo database, and prints a URL.

---

## Architecture

```
                    ┌─────────────── CloudFront (one origin for both) ───────────────┐
  browser ─HTTPS──► │  /api/*  ──► Lambda Function URL   (+ x-origin-verify header)  │
                    │  /*      ──► S3 web/  via OAC      (+ SPA-routing function)    │
                    └───────────────────────────────────────────────────────────────┘
                                            │
                       Lambda · python3.12 · arm64 · 1024 MB · 45s
                       FastAPI (unchanged) behind Mangum
                         ├── SQLite in /tmp, hydrated from S3 per instance
                         │     writes: S3 distributed lock → serialized
                         │     reads:  conditional If-Match write-back
                         ├── Groq API key from SSM Parameter Store
                         └── Groq over the public internet — no VPC, no NAT
                                            │
                       S3 (private) · db/recovery.db + web/ (built SPA)
                       CloudWatch Logs · 14-day retention
```

The two timeouts in that picture are deliberately unequal: CloudFront stops
waiting at 30s while the function has 45s. On a slow request the edge gives up
first, by 15 seconds, and the function keeps running long enough to finish its
write-back and release the S3 lock instead of being killed mid-upload. So the
ceiling a caller experiences is 30s, not 45.

Nothing here runs when idle. There is no VPC, no NAT gateway, no API Gateway,
no ECR repository, and no always-on database — between them, those are where an
"AWS demo" normally starts costing $30–50/month.

## What it costs

| Service | Always-free allowance | This app's usage |
| --- | --- | --- |
| Lambda | 1M requests + 400,000 GB-s / month | ~1 GB-s per API request; a demo uses a fraction of a percent |
| CloudFront | 1 TB egress + 10M requests / month | SPA is ~250 KB gzipped, cached at the edge |
| CloudFront Functions | 2M invocations / month | one per non-API request |
| SSM Parameter Store | standard parameters free | 2 parameters |
| CloudWatch Logs | 5 GB ingest + 5 GB storage | capped at 14-day retention |
| AWS Budgets | first 2 budgets free | 1, optional |
| S3 storage | 5 GB (first 12 months) | ~20 MB — about **$0.0005/month** after that |
| S3 requests | — | at most one `HEAD` per API request (a 5s freshness TTL coalesces bursts) → **~$0.04 per 100k requests** |

**Realistic steady state: under $0.10/month.** The only line that is not
free-forever is S3, and at these volumes it rounds to nothing.

> **On the free tier itself:** AWS changed it in July 2025. Accounts created
> since then get sign-up credits plus a free *plan* period rather than the old
> blanket 12-month tier — but the always-free allowances in the table above
> (Lambda, CloudFront, Parameter Store, CloudWatch) were not affected. This
> stack is built to live inside those, so it does not fall off a cliff when a
> trial period ends.

Cost guardrails wired into the stack:

- **Reserved concurrency** caps the API at 5 simultaneous executions, so a
  traffic spike or a redirect loop cannot run away with the compute budget.
- **`PriceClass_100`** restricts CloudFront to its cheapest edge footprint.
- **14-day log retention** — the default is *never expire*, which is how a
  quiet demo silently outgrows the CloudWatch free tier.
- **Lifecycle rules** expire old database versions after 7 days and old
  deployment zips after 90. Ninety, not thirty: a stack rollback re-points the
  function at the previous zip, and expiring those after a month would fail the
  rollback of any stack that has not shipped since.
- **An optional monthly budget alarm**: `BUDGET_EMAIL=you@example.com ./infra/deploy.sh`.

Tear the whole thing down with `./infra/destroy.sh`. It keeps the database
bucket and the SSM parameters unless you ask for them: `--delete-data` and
`--delete-secrets`.

## Deploying

### The easiest path: CloudShell (no access keys)

[CloudShell](https://console.aws.amazon.com/cloudshell) is a free browser
terminal that inherits your console login, so there are no long-lived
credentials to create, store, or rotate. It already has `aws`, `node`, `zip`
and `git`.

```bash
# in CloudShell
curl -LsSf https://astral.sh/uv/install.sh | sh && export PATH="$HOME/.local/bin:$PATH"
git clone <this repo> && cd MedPullKiosk/recovery-copilot
./infra/deploy.sh
```

The script prompts once for the Groq API key and stores it in Parameter Store.

### From a laptop

Needs `aws` (authenticated), `uv`, `node` 20+, and `zip`.

```bash
aws configure          # an IAM user/role with AdministratorAccess
./infra/deploy.sh
```

Prefer an IAM user or Identity Center role over the account root user. Root
access keys can do anything in the account, cannot be scoped, and AWS
recommends against creating them at all.

### Options

```bash
./infra/deploy.sh                  # build, deploy, seed on first run
./infra/deploy.sh --reseed         # rebuild the demo database (dates shift to today)
./infra/deploy.sh --backend-only   # skip the frontend build and upload
```

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `AWS_REGION` | `us-east-1` | Deployment region |
| `STACK_NAME` | `recovery-copilot` | CloudFormation stack name |
| `GROQ_API_KEY` | — | Skips the prompt; also read from `recovery-copilot/.env` |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Overrides the model |
| `JUNCTION_API_KEY` | — | Stored in SSM on first deploy; also read from `.env`. Optional — without it the wearable connector stays idle |
| `JUNCTION_WEBHOOK_SECRET` | — | The Svix `whsec_…` secret for the registered endpoint; stored in SSM like the key |
| `JUNCTION_ENVIRONMENT` | `sandbox` | `sandbox` or `production` — must match the key |
| `JUNCTION_REGION` | `us` | `us` or `eu` |
| `JUNCTION_LINK_REDIRECT_URL` | — | Where Junction Link sends a patient afterwards |
| `BUDGET_EMAIL` | — | Enables the monthly cost alarm |
| `API_RESERVED_CONCURRENCY` | `5` | `-1` leaves concurrency unreserved |

## The Groq hookup

Unchanged from local: the provider chain is still **Groq → deterministic
fallback**, selected per call by `app/llm/provider.py`. Only the key's storage
moves.

`deploy.sh` writes it to SSM Parameter Store as a `SecureString`, and
`app/aws/secrets.py` reads it once per cold start into `settings.groq_api_key`.
Standard parameters are free, and the key stays out of the function's plaintext
environment where any console reader would see it.

To rotate it:

```bash
aws ssm put-parameter --name /recovery-copilot/groq-api-key \
  --type SecureString --value "gsk_..." --overwrite
```

New cold starts pick it up; force it immediately by redeploying the function.

The two Junction secrets follow the same path (`/recovery-copilot/junction-api-key`
and `/recovery-copilot/junction-webhook-secret`, read into
`settings.junction_api_key` / `settings.junction_webhook_secret`). Register
`https://<CloudFront domain>/api/webhooks/wearables/junction` as the endpoint in
Junction's webhook dashboard, store the `whsec_…` secret it shows, and
redeploy. Both are optional: with neither stored the connector is idle and the
console's Integrations page says so.

Ollama is explicitly disabled on Lambda (`OLLAMA_URL=""`) — there is no local
model to reach. With no Groq key configured the app still works end to end and
renders every narrative from the deterministic engine. Four surfaces label that
on screen (the recovery summary, the daily briefing, Ask answers and RTM
documents); worklist reasons, suggested actions and AI drafts carry no
provenance label either way. See the project README for why.

## How the database works

The app's SQLAlchemy/SQLite layer is untouched. What changed is where the file
lives: the durable copy is `s3://<bucket>/db/recovery.db`, and each Lambda
instance keeps a working copy in `/tmp`.

This matters because the app writes on read paths — the engine's input hash
includes today's date, so the first request each day recomputes every
assessment, and insight caches fill lazily. Deciding what to persist by HTTP
verb alone would lose those. So `app/aws/storage.py` hooks the sessionmaker's
`after_commit` and treats the two kinds of write differently:

| | Locking | Write-back | On a conflict |
| --- | --- | --- | --- |
| **`POST`/`PUT`/`DELETE`** — provider-authored data (tasks, escalations, RTM time, approvals) | S3 distributed lock held across the whole request | unconditional, under the lock | cannot happen — writes are serialized |
| **`GET`** — derived rows (assessments, insight caches) | none | conditional `If-Match` on the hydrated ETag | discard and re-hydrate; the row regenerates |

The lock is an S3 object created with `If-None-Match: *`, which S3 makes
atomic — that is all a mutex needs. Each lock carries an expiry so an instance
that dies mid-request cannot wedge writes for longer than its TTL.

**Known limits, stated plainly.** This is a demo-scale design. Writes are
serialized globally, so throughput is one mutation at a time, and each one
uploads the whole database file (~1.7 MB seeded). That is the right trade at ten
patients and a handful of providers, and the wrong one at a hundred clinics.
The graduation path is to point `DATABASE_URL` at Postgres and delete
`app/aws/` entirely — no other application code assumes SQLite.

### Reseeding

The roster is generated relative to the seed date, so a database seeded in July
shows drifting post-op days by September. `./infra/deploy.sh --reseed` rebuilds
it (and discards anything entered through the UI). It runs on a separate
`-seed` function because warming every insight through Groq takes minutes,
well past the API function's 45-second timeout.

## Security posture

The app ships **no authentication**, by design, for demos — that predates this
deployment and is called out in the project README. Anyone with the CloudFront
URL can call all 30 API routes, the write paths among them. What the stack does
add:

- The S3 bucket is private. CloudFront reaches the SPA through an Origin Access
  Control; the `db/` prefix is not reachable through the distribution at all.
- The Function URL is `AuthType: NONE` so CloudFront can reach it without SigV4
  origin signing, but CloudFront injects a 32-byte shared secret as
  `x-origin-verify` and the handler rejects anything without it. The origin is
  effectively unreachable directly.
- Only `/api/*` is routed to the function. FastAPI's `/docs`, `/redoc` and
  `/openapi.json` are open on a local run but are not reachable through the
  distribution, because everything outside `/api/*` is served from the SPA
  origin.
- Bucket policy denies any non-TLS request.
- The Lambda role reads and writes only the `db/` prefix, holds one SSM
  parameter, and can `kms:Decrypt` only via SSM. Its `s3:ListBucket` grant is
  the one bucket-wide permission and is deliberately unconditioned: S3 consults
  it to decide whether a missing key is a 404 or a 403, and `s3:prefix` is
  populated only for list requests, so conditioning on it would turn the
  "database not seeded yet" HEAD into a permissions error. The grant exposes key
  names, not object contents.

**Before this holds real patient data** you need, at minimum: authentication, an
AWS Business Associate Addendum, encryption with a customer-managed KMS key,
CloudTrail data events, and access logging. Nothing here is HIPAA-ready, and the
seeded roster is synthetic.

## Files

| File | Purpose |
| --- | --- |
| `cloudformation.yaml` | The whole stack, one template |
| `build-lambda.sh` | Builds the arm64 deployment zip from `uv.lock` |
| `deploy.sh` | Build → deploy → upload SPA → seed → invalidate → smoke test |
| `destroy.sh` | Tears it down; keeps the database and the SSM parameters unless `--delete-data` / `--delete-secrets` |

Application-side code lives in `backend/app/aws/` and
`backend/app/lambda_handler.py`, covered by `backend/tests/test_aws_storage.py`
and `backend/tests/test_lambda_handler.py`.

## Troubleshooting

**`/api/health` returns 403.** Two different 403s, told apart by the body:

- *Lambda's own* `{"Message":"Forbidden..."}` (an `x-amzn-ErrorType` header is
  present): the Function URL's resource policy is incomplete. URLs created
  since October 2025 need `lambda:InvokeFunction` (scoped by
  `lambda:InvokedViaFunctionUrl`) **in addition to** `lambda:InvokeFunctionUrl`;
  the template grants both. Redeploying the stack restores them.
- *The app's* `{"detail":"Direct access is not permitted."}`: CloudFront and
  the function disagree about the origin secret. Redeploy — `deploy.sh` reads
  it from Parameter Store, so both sides end up consistent.

**`/api/health` reports `db_ok: false`.** The database object is missing. Run
`./infra/deploy.sh --reseed`.

**`llm_provider` is `fallback` when a key is set.** Either the key is missing
from Parameter Store, or Groq is inside its 3-minute cooldown. The cooldown is
armed by a failed call and also by three consecutive completions that parse but
fail the product's output validation. Check the function logs:
`aws logs tail /aws/lambda/recovery-copilot-api --follow`.

**Stack fails on `ReservedConcurrentExecutions`.** The account's concurrency
limit is too low to reserve any (new accounts sometimes start at 10). `deploy.sh`
detects this and leaves concurrency unreserved; to force it,
`API_RESERVED_CONCURRENCY=-1 ./infra/deploy.sh`.

**First request after a quiet period is slow.** Cold start: importing
numpy/pandas plus the S3 hydrate runs 3–6 seconds. Provisioned concurrency
would fix it and is not free, so it is deliberately not configured.
