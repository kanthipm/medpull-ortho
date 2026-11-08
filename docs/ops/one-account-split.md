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
`DEMO_MODE=true ./infra/deploy.sh --plan` first: the change set should read Add for the two keys and their aliases and Modify with Replacement False for the buckets, the function and the distribution; anything marked Replacement True or Remove on a bucket stops here. Then `DEMO_MODE=true ./infra/deploy.sh` one last time in demo mode (the data is still mixed), which also creates the two KMS keys (`alias/recovery-copilot-clinic`, `-personal`), switches both buckets to SSE-KMS for new objects (the app now presigns with SigV4, which SSE-KMS requires) and tags every resource. Smoke-test one attachment upload from a phone afterwards and run `make audit-compartments AUDIT="--stack recovery-copilot"`. Existing objects stay SSE-S3 until `./infra/reencrypt.sh` runs (`--dry-run` first; optional, any time).

### 1. Create the demo stack  [AWS]  — done 2026-11-07, without the domain
- `cp .env.demo.example .env.demo`; set `STACK_NAME=medpull-demo`, `DEMO_MODE=true`, `SEED=none` (the database is copied in step 2, not seeded), `ALLOW_MOCK_WEBHOOK=true`, `SENDBLUE_VERIFIED_CONTACTS_ONLY=false`, the demo Groq key, the Sendblue API key, secret and from-number from `.env` (outbound only — no `SENDBLUE_WEBHOOK_SECRET`, no Junction keys), and **both `SITE_DOMAIN` and `SITE_CERTIFICATE_ARN` blank**: `demo.medpull.org` is still an alternate domain name on the redirect distribution in the other account (`aws cloudfront list-conflicting-aliases --distribution-id E1AQUZI9S5GVUO --alias demo.medpull.org` shows it, account …273521), and CloudFront refuses a second distribution with the same alias — the create would roll back. The domain is attached in step 3.
- `./infra/deploy.sh --env .env.demo` — creates the stack and prints the distribution domain and the data bucket name (2026-11-07: `https://d9w8mctktwvg9.cloudfront.net`, data bucket `medpull-demo-databucket-3ly03wbbch7n`, personal bucket `medpull-demo-personaldatabucket-rtuvllza92hs`, secrets under `/medpull-demo/`). A first deploy leaves `PublicBaseUrl` blank, so follow it at once with `./infra/deploy.sh --env .env.demo --stack-only`, which fills it from the stack's own `SiteUrl` output (texted check-in links carry it).

### 2. Give the demo its database  [AWS]  — done 2026-11-07 ~21:30 UTC
(Outcome: 24 clinic charts, all generated, plus 15 athletes; every real person 404s on the demo; pre-fill backup `s3://medpull-demo-databucket-3ly03wbbch7n/db/backups/recovery-20261107T212842Z.db`; console credential id 1 `hospital:hirt` "HIRT demo" minted, token handed to Steve, never written down here.)
- `aws s3 cp s3://recovery-copilot-databucket-cay8lc5zark5/db/recovery.db s3://medpull-demo-databucket-3ly03wbbch7n/db/recovery.db` (server-side copy; the demo API re-hydrates on its next request).
- Remove the real people, under the demo's own lock: `cd backend && uv run python scripts/admin_db.py --bucket medpull-demo-databucket-3ly03wbbch7n --revoke-sessions steve --revoke-sessions steve-me --revoke-sessions medha-pulluru --revoke-sessions medha-pulluru-77ca --revoke-sessions medha-pulluru-me --revoke-sessions naga --revoke-sessions naga-me --revoke-sessions app-review-me --revoke-sessions steve-zhang-ath --delete-patient steve-me --delete-patient steve --delete-patient medha-pulluru-me --delete-patient medha-pulluru-77ca --delete-patient medha-pulluru --delete-patient naga-me --delete-patient naga --delete-patient app-review-me --delete-patient steve-zhang-ath --purge-phone-verifications` (dry-run first with `--dry-run`).
- Re-anchor the roster to today and add the fictional HIRT lifters: `uv run python scripts/push_demo_fill.py --bucket medpull-demo-databucket-3ly03wbbch7n`.
- Mint the demo's HIRT login: `uv run python scripts/admin_db.py --bucket medpull-demo-databucket-3ly03wbbch7n --mint-token hospital:hirt "HIRT demo"` → the link is `https://demo.medpull.org/login#token=<printed once>`.

### 3. Point demo.medpull.org at it  [other account, then AWS]
Where the DNS is (looked up 2026-11-07): `medpull.org` and `medpull.app` are both Route 53 hosted zones in the OTHER AWS account, the one whose id ends in **273521** (this account is 556683673972); it also holds the redirect distribution (id ending V32PMWR, domain `d39jklhz8lekh0.cloudfront.net`) that `app.medpull.org`, `www.medpull.org` and the apex point at. The domain is registered with Amazon Registrar (Route 53 Domains, expiry 2034-01-19), so the registration sits there too. The `medpull.org` zone in THIS account (Z035211224ZJZCSSWJCP) is an unused stub whose nameservers are not the public ones; it can be deleted.

Order matters, and it is NOT release → attach → repoint. CloudFront checks the name's DNS when an alias is added and refuses one whose record still points at another distribution ("incorrectly configured DNS record that points to another CloudFront distribution", a 409 that rolls the stack update back). So:
1. Zone owner (account …273521): CloudFront → the redirect distribution → Settings → Edit → Alternate domain names → remove `demo.medpull.org`, save. The name goes dark (TLS refused) from here until step 3 completes.
2. Zone owner: Route 53 → Hosted zones → medpull.org → the `demo` CNAME → value `d9w8mctktwvg9.cloudfront.net`, save. Wait until public resolvers return it (`dig +short @8.8.8.8 demo.medpull.org CNAME`; the record's TTL).
3. Here: `SITE_DOMAIN=demo.medpull.org` and `SITE_CERTIFICATE_ARN=arn:aws:acm:us-east-1:556683673972:certificate/4a262c26-1fc5-4803-ab5e-088c5c835c03` in `.env.demo` (the certificate's primary name is demo.medpull.org; a certificate may serve two distributions), then `./infra/deploy.sh --env .env.demo --stack-only`.

Until all three, the demo answers on its `*.cloudfront.net` URL. Done 2026-11-07: parts 1 and 2 by Steve in the other account; the first attach (run between them) was refused and rolled back cleanly, the second went through once the resolvers had the new record.

### 4. Lock the real stack and remove the personas  [AWS]  — done 2026-11-08
- In `.env`: `DEMO_MODE=false`, `ALLOW_MOCK_WEBHOOK=false`. Then ONE deploy with the token minted on the command line, never in the file (a `generate` left in `.env` would mint a new token on every deploy): `CONSOLE_ACCESS_TOKEN=generate ./infra/deploy.sh --stack-only`. The token is printed once and stored at `/recovery-copilot/console-access-token` in SSM (`aws ssm get-parameter --name /recovery-copilot/console-access-token --with-decryption --query Parameter.Value --output text` reads it back). From here the console at demo.medpull.app asks for a token and the welcome screen is gone.
- Back up first: `aws s3 cp s3://recovery-copilot-databucket-cay8lc5zark5/db/recovery.db s3://recovery-copilot-databucket-cay8lc5zark5/db/backups/recovery-<utc>-pre-step4.db` (2026-11-08: `recovery-20261108T185224Z-pre-step4.db`).
- Under the real stack's lock (dry-run first): `uv run python scripts/admin_db.py --bucket recovery-copilot-databucket-cay8lc5zark5 --delete-patient ana … (the 18 clinic personas) --delete-patient kofi-mensah … (the 15 generated athletes) --delete-sports-org rockets --delete-sports-org dynamo --delete-sports-org uh --delete-sports-org hcta --prune-assessments`. Done: 33 charts and the four programs gone, 18 assessments pruned; left: `steve`, `steve-me`, `steve-zhang-ath`, `medha-pulluru`, `medha-pulluru-77ca`, `medha-pulluru-me`, `naga`, `naga-me`, `app-review-me`, `guest`. The legacy hospital rows (methodist, hermann, stlukes, utsw) are empty and still there; `--rename-hospital hosp_demo "<Medha and Naga's org>"` still waits on decision 1.
- Minted on the real stack: credential 1 `hospital:hosp_medpull` "MedPull clinic", 2 `hospital:hirt` "HIRT", 3 `sports_org:rice` "Rice Athletics" (tokens handed to Steve once; `--report` lists them, `--revoke-token ID` retires one).
- Nothing to change at Sendblue, Junction or App Store Connect: their webhooks already point at this stack.

### 5. Account hygiene  [AWS]
`./infra/account.sh --dry-run`, then `./infra/account.sh --user <steve> --user <kanthi>`: IAM group `medpull-admins` with AdministratorAccess and an MFA requirement, one-time passwords printed once (each person then sets a password and registers MFA in the console), GuardDuty on, cost-allocation tags activated (reports "not on a bill yet" until a day after the first tagged deploy; rerun then). The account already has a trail (`medpull-audit-trail` → `medpull-cloudtrail-logs-1759818803`, management events only, and its bucket policy already allows CloudTrail), so put `TRAIL_BUCKET=medpull-cloudtrail-logs-1759818803` and `TRAIL_MANAGEMENT_EVENTS=false` in both env files and `./infra/deploy.sh --stack-only` on each stack: the per-stack trails then add only the S3 data events for the data buckets. Root has access keys: delete them in the console once the users work, and stop using root.

### 6. Later, not blocking
- `app.medpull.org` as a second alias on the real stack (the template takes one `CustomDomainName` today; extend to a list) and the apps rebuilt against `https://app.medpull.org`; retire the redirect distribution in the other account.
- `infra/reencrypt.sh` to rewrite existing objects under the KMS keys.
- The sports facet's first object store (`sports/` prefix, its own key) when sports gains attachments.

## Checks after each AWS step
- `curl https://<host>/api/health` → `demo` true on the demo (https://demo.medpull.org), false on the real stack; `console_auth` true on the real stack.
- `make audit-compartments AUDIT="--stack recovery-copilot"` and `AUDIT="--stack medpull-demo"`: no real person on the demo, no persona on the real stack, every org with a credential, both buckets on their keys.
- A phone signed in as Steve still refreshes (real stack unchanged).
