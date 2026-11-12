# One deployment again (2026-11-12)

The split into a real stack and a demo stack (`one-account-split.md`,
2026-11-07) is undone. There is one deployment: the `recovery-copilot` stack
at **https://demo.medpull.app**, and it is the public demo. Steve's words:
"get rid of demo.medpull.org. demo.medpull.app should be the public demo, use
the real data from there right now its fine. we don't have an official
version currently".

## What that means

| | |
| --- | --- |
| Stack | `recovery-copilot` (us-east-1), `DEMO_MODE=true` |
| Host | https://demo.medpull.app (console at `/`, patient web app at `/patient/`) |
| Database | the same S3 SQLite as before: the team's own accounts, with the showcase's generated personas beside them |
| Apps | the App Store iPhone app and the Android app keep talking to this host; the demo iPhone app (`MedPullDemo`) is built against it too |
| Texts | Sendblue delivers inbound texts to `https://demo.medpull.app/api/webhooks/sendblue/<secret>` |
| Retired | the `medpull-demo` stack and `demo.medpull.org` |

The settings that make it so are at the end of the repo's `.env` (deploy.sh
takes the last value of a key): `DEMO_MODE=true`, `SEED=none`,
`HEP_CLINIC_ID=hirt`, `APP_TIMEZONE=America/Chicago`,
`IOS_LINK_APP_IDS=2DFDVFGSH3.com.medpull.demo`, `IOS_LINK_PATHS=/a/*`.
Deploy with plain `./infra/deploy.sh`.

## Real accounts live beside the personas

The database holds a few real accounts (the team's own charts and spaces,
the App Review account, `guest`). Everything that is demo-only is written so
it cannot reach them:

- **The morning fill** (`{"action": "showcase_fill"}` on the seed function,
  10:30 UTC, `ShowcaseDailyRule`) rewrites only the ids the showcase owns: the
  clinic roster (`app/seed/demo_fill.py`), the sports rosters
  (`app/sports/seed.py`), and the Personal members that carry the showcase
  mark. A Personal row without the mark is never touched; the clinic roster
  refuses to name a protected id. Before the first fill the roster's ids
  were checked against the live database (none existed) and a dry run on a
  copy left all 4,219 rows of the 13 other accounts identical.
- **The destructive seed is off**: `SEED=none`, and `seed --reset` refuses a
  database that holds anyone it could not rebuild.
- **"Become a persona"** (`/api/demo/session`, `/api/demo/patient-session`,
  a texted link's sign-in, the phone binding) answers only for generated
  personas. A real chart cannot be acted as from the open console.
- **Personal** on the console lists generated members only. A real
  subscriber's space is never listed and its routes answer 404.
- The worklist's caption counts what it shows ("25 generated, 6 of the
  team's own") instead of claiming every chart is generated.

The console is open (no sign-in) by Steve's earlier decision; org-scoped
tokens still narrow it (`scripts/admin_db.py --mint-token`). To lock it
again: `CONSOLE_ACCESS_TOKEN=generate ./infra/deploy.sh --stack-only`.

## Day to day

```
./infra/deploy.sh                      # ship the working tree to the one stack
aws lambda invoke --function-name recovery-copilot-seed \
  --cli-binary-format raw-in-base64-out --payload '{"action":"showcase_fill"}' /dev/stdout
                                       # re-anchor the personas to today by hand
cd backend && uv run python scripts/sendblue_webhooks.py      # where inbound texts go
```

A backup before anything that writes the database by hand:
`aws s3api copy-object --bucket <data bucket> --copy-source <data bucket>/db/recovery.db --key db/backups/recovery-<stamp>.db`.
The one made before the first showcase fill is
`db/backups/recovery-20261112T103047Z-pre-showcase.db`.

The morning exercise text (`EXERCISE_REMINDERS=true`) is off. Turned on, it
texts every lifter who can be texted their plan for the day at
`EXERCISE_REMINDER_HOUR` (8, Central): only a real phone bound to a persona
from the demo app receives one, and it keeps receiving one each morning
until it is unbound or replies STOP.

## Retiring the demo stack

1. Here (done 2026-11-12): `./infra/destroy.sh --env .env.demo` deletes the
   `medpull-demo` stack. Its buckets and keys are retained by the template
   (they hold generated data only); delete them with `--delete-data` once
   nobody wants a copy.
2. In the account that holds the medpull.org zone (…273521), which only Steve
   can change: Route 53 → medpull.org → the `demo` record. Either delete it,
   or point it at the redirect distribution that already sends
   `app.medpull.org` to `demo.medpull.app` (add `demo.medpull.org` back to
   that distribution's alternate names first). Until then `demo.medpull.org`
   resolves to a distribution that no longer exists.
3. Anyone holding the old HIRT link (`https://demo.medpull.org/…`) gets the
   new one: **https://demo.medpull.app/?clinic=hirt**.

## If a real, separate product is wanted later

`one-account-split.md` is still the runbook: a second stack from a second
env file, the database copied, the showcase kept on this one. Nothing here
prevents it; the two differ only in their env files.
