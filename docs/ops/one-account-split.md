# One account, two stacks, compartments inside: the runbook

Decided 2026-11-07. One AWS account (556683673972, us-east-1) keeps everything,
compartmentalized: the public demo and the real product are **two stacks**;
inside the real stack each facet and org is told apart by **org-scoped
console credentials**, **a KMS key and bucket per facet**, and **tags** on
every resource. This file is the operator's order of work. Every step that
changes AWS is marked **[AWS]** and is run only on an explicit go-ahead; the
others are local edits or reads.

## The shape

| | Real product | Public demo |
| --- | --- | --- |
| Stack | `recovery-copilot` (exists) | `medpull-demo` (new) |
| Why this way round | the iOS and Android apps are built against this stack's CloudFront domain (`d1msmt8r5u7oxx.cloudfront.net`, see `ios/project.yml` and `android/app/build.gradle.kts`), so real people's phones keep working without an app update | a demo can move hosts freely |
| Host today | `demo.medpull.app` (keeps answering; `app.medpull.org` is added as a second alias later, then the apps move to it) | `demo.medpull.org` (certificate already issued in this account; DNS record lives in the other account) |
| Env file | `.env` — `DEMO_MODE=false`, `CONSOLE_ACCESS_TOKEN=generate` | `.env.demo` — `DEMO_MODE=true`, `ALLOW_MOCK_WEBHOOK=true` |
| Console | locked: staff token + one token per org | open; an org token (HIRT) narrows it for a scripted demo |
| Database | today's database minus the generated personas | a copy of today's database minus the real people, re-anchored to today by `push_demo_fill.py` |
| Integrations | Junction, Sendblue inbound + outbound, Apple notifications (all already point here) | Sendblue outbound only (one number posts inbound texts to one webhook), no Junction, its own Groq key |
| People | Steve, Medha, Naga and their personal spaces, App Review's account, Steve's athlete account, HIRT's real patients, the Rice testers | the 18 clinic personas, the generated Rice roster, the fictional HIRT lifters, `guest` |

Compartments inside the real stack (what the merged code provides):

- **Credentials**: `console_credentials` rows (`hospital:<id>`, `sports_org:<id>`, `team:<id>`) minted with `scripts/admin_db.py --mint-token`; every console and team route is filtered by the credential's scope; the staff token (`CONSOLE_ACCESS_TOKEN`) sees everything.
- **Storage**: clinic objects (`db/`, `attachments/`) in the data bucket under the clinic KMS key; subscribers' files in the personal bucket under the personal key; sports has no objects yet (rows + scoping + tags).
- **Tags**: `medpull:facet` (clinic | personal | sports | shared), `medpull:deployment` (demo | real), `medpull:stack`, activated as cost-allocation tags so Cost Explorer can group by facet.
- **Audit**: `make audit-compartments` lists every org, its counts, its credentials and where its data lives.

## Who is who on today's database (read 2026-11-07)

Real: `steve` (+ `steve-me`), `medha-pulluru` (+ `medha-pulluru-77ca`, `medha-pulluru-me`), `naga` (+ `naga-me`), `app-review-me`, `steve-zhang-ath`. Intentional demo slot: `guest`.

Generated: clinic `ana dana helen kevin lucia marcus omar rosa tom` (hosp_demo), `grace robert` (hosp_hermann), `aisha elena linda` (hosp_methodist), `david sofia` (hosp_stlukes), `james priya` (hosp_utsw); athletes `kofi-mensah sloane-whitaker andre-beaumont caleb-whitfield devin-marsh ethan-nakamura isaiah-cole jalen-okoro kwame-asante luka-petrovic mateo-reyes-vega noah-brennan rafael-dossantos samuel-adeyemi tobias-lindqvist`; sports orgs `rockets dynamo uh hcta` (empty).

## Decisions Steve makes before the AWS steps

1. **Medha's and Naga's org.** They sit on `hosp_demo` ("MedPull Demo Hospital"). On the real stack that row is renamed to their real organization (`--rename-hospital hosp_demo "<name>"`) — which name?
2. **Groq key for the demo.** A second key (console.groq.com, free) keeps the demo's daily narrative warming from eating the real product's rate limit. Paste it into `.env.demo` (never commit).
3. **Steve's own chart on the demo.** Recommended: not there (a phone can only sync to one stack, and the demo caption says every chart is generated). Say if you want a frozen copy kept.
4. **IAM user names** for `infra/account.sh --user …` (you and Kanthi), and whether to turn on GuardDuty (a few dollars a month) and the CloudTrail data events (cents).
5. **The DNS owner.** `demo.medpull.org` must become a CNAME to the new demo distribution, in the account that holds the medpull.org zone (not this one).

## Steps, in order

### 0. Ship the merged code to the real stack  [AWS]
`DEMO_MODE=true ./infra/deploy.sh` one last time in demo mode (the data is still mixed), which also creates the two KMS keys, switches both buckets to SSE-KMS for new objects and tags every resource. Check `make audit-compartments` afterwards. Existing objects stay SSE-S3 until `infra/reencrypt.sh` runs (optional, any time).

### 1. Create the demo stack  [AWS]
- `cp .env.demo.example .env.demo`; set `STACK_NAME=medpull-demo`, `DEMO_MODE=true`, `SEED=none` (the database is copied in step 2, not seeded), `ALLOW_MOCK_WEBHOOK=true`, `SENDBLUE_VERIFIED_CONTACTS_ONLY=false`, the demo Groq key, the Sendblue API key and secret from `.env` (outbound only — no `SENDBLUE_WEBHOOK_SECRET`, no Junction keys), `SITE_DOMAIN=demo.medpull.org`, `SITE_CERTIFICATE_ARN=arn:aws:acm:us-east-1:556683673972:certificate/4a262c26-1fc5-4803-ab5e-088c5c835c03` (its primary name is demo.medpull.org; a certificate may serve two distributions).
- `./infra/deploy.sh --env .env.demo` — prints the new distribution domain and the data bucket name.

### 2. Give the demo its database  [AWS]
- `aws s3 cp s3://recovery-copilot-databucket-cay8lc5zark5/db/recovery.db s3://<demo data bucket>/db/recovery.db` (server-side copy; the demo API re-hydrates on its next request).
- Remove the real people, under the demo's own lock: `cd backend && uv run python scripts/admin_db.py --bucket <demo data bucket> --revoke-sessions steve --revoke-sessions steve-me --revoke-sessions medha-pulluru --revoke-sessions medha-pulluru-77ca --revoke-sessions medha-pulluru-me --revoke-sessions naga --revoke-sessions naga-me --revoke-sessions app-review-me --revoke-sessions steve-zhang-ath --delete-patient steve-me --delete-patient steve --delete-patient medha-pulluru-me --delete-patient medha-pulluru-77ca --delete-patient medha-pulluru --delete-patient naga-me --delete-patient naga --delete-patient app-review-me --delete-patient steve-zhang-ath --purge-phone-verifications` (dry-run first with `--dry-run`).
- Re-anchor the roster to today and add the fictional HIRT lifters: `uv run python scripts/push_demo_fill.py --bucket <demo data bucket>`.
- Mint the demo's HIRT login: `uv run python scripts/admin_db.py --bucket <demo data bucket> --mint-token hospital:hirt "HIRT demo"` → the link is `https://demo.medpull.org/login#token=<printed once>`.

### 3. Point demo.medpull.org at it  [other account]
A CNAME from `demo.medpull.org` to the distribution domain step 1 printed, in the account that hosts the zone. Until then the old redirect (to demo.medpull.app) stands.

### 4. Lock the real stack and remove the personas  [AWS]
- In `.env`: `DEMO_MODE=false`, `ALLOW_MOCK_WEBHOOK=false`, `CONSOLE_ACCESS_TOKEN=generate` (printed once; keep it), then `./infra/deploy.sh`. From here the console at demo.medpull.app asks for a token and the welcome screen is gone.
- Under the real stack's lock: `uv run python scripts/admin_db.py --bucket recovery-copilot-databucket-cay8lc5zark5 --rename-hospital hosp_demo "<Medha and Naga's org>" --delete-patient ana … (the 18 clinic personas) --delete-patient kofi-mensah … (the 15 generated athletes) --delete-sports-org rockets --delete-sports-org dynamo --delete-sports-org uh --delete-sports-org hcta --prune-assessments` (dry-run first).
- Mint the real orgs' tokens: `--mint-token hospital:hosp_medpull "MedPull clinic"`, `--mint-token hospital:hirt "HIRT"` (the `hirt` hospital row arrives with the merged seed list on the next start), `--mint-token sports_org:rice "Rice Athletics"`.
- Nothing to change at Sendblue, Junction or App Store Connect: their webhooks already point at this stack.

### 5. Account hygiene  [AWS]
`./infra/account.sh --dry-run`, then `./infra/account.sh --user <steve> --user <kanthi> [--trail-bucket medpull-cloudtrail-logs-1759818803]`: IAM group with AdministratorAccess and an MFA requirement, one-time passwords printed once, GuardDuty on, cost-allocation tags activated (may need a rerun a day after the first tagged deploy), the CloudTrail bucket policy. Then `TRAIL_BUCKET_NAME=medpull-cloudtrail-logs-1759818803` in `.env` and `./infra/deploy.sh --stack-only` for the trail. Stop using root after the users exist.

### 6. Later, not blocking
- `app.medpull.org` as a second alias on the real stack (the template takes one `CustomDomainName` today; extend to a list) and the apps rebuilt against `https://app.medpull.org`; retire the redirect distribution in the other account.
- `infra/reencrypt.sh` to rewrite existing objects under the KMS keys.
- The sports facet's first object store (`sports/` prefix, its own key) when sports gains attachments.

## Checks after each AWS step
- `curl https://<host>/api/health` → `demo` true on the demo, false on the real stack; `console_auth` true on the real stack.
- `make audit-compartments` against each stack: no real person on the demo, no persona on the real stack, every org with a credential.
- A phone signed in as Steve still refreshes (real stack unchanged).
