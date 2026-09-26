# MedPull Personal: the subscription tier

The same iPhone app, the same wearable stream, the same engine, sold to a
person who is not a hospital's patient. Backend package `backend/app/personal/`,
routes under `/api/mobile/personal` and `/api/mobile/profiles`, iOS screens
under `ios/MedPull/Features/Personal/`.

## The two products, side by side

| | With a care team (existing) | On my own (Personal) |
| --- | --- | --- |
| Who pays | The clinic; free to the patient | The person, an App Store subscription after a 14-day trial |
| Row | `patients.account_kind = "clinic"`, on a hospital roster | `account_kind = "personal"`, `hospital_id` NULL, assigned to the synthetic `ct_medpull` care-team row |
| Who sees it | The console (worklist, briefing, Ask, patient page) | Nobody but the person; every console roster enumeration goes through `app.personal.scope.clinic_patients()` |
| Readouts | Risk tier, trajectory, M1–M18 care metrics for clinicians | Readiness, HRV, resting HR, sleep need/debt, training load, fitness, body signals, rhythm, activity, how-you-feel (`metrics.py`), plus the M1–M18 report for a recovery goal |
| Words | Clinician handoff prose, patient-facing labels | The morning brief and four deep dives, written for someone who reads their own numbers (`insights.py`) |
| Tasks | Assigned by the care team or the care plan | Written each morning from the verdict and the goal (`plan.py`) |
| Copilot | Logs pain, completes tasks, passes notes to the care team | The coach: same machinery, knows the day's readouts, keeps a journal instead (`coach.py`) |
| Texts | Task invitations, care-team messages | The morning brief with "reply 1 for your check-in", when opted in |
| Files | `attachments/<patient>/…` in the data bucket | `personal/<patient>/…` in the **personal bucket** (`PersonalDataBucket`) |

## Identity and the two-space workflow

A person who is both a hospital's patient and a subscriber holds **two
rows**, paired by `Patient.linked_patient_id` in both directions. Each keeps
its own tasks, thread, insights and check-ins. The wearable stream is
shared: the phone's Health SDK is signed into one aggregator user, the
**clinic chart's**, and the personal row reads through it
(`Patient.observations_from`; `scope.data_patient_id()` resolves every
observation read for the app). Pairing moves any readings the personal row
had collected onto the chart with the same dedupe-aware merge the console's
app-link uses (`personal/identity.link`).

Three ways the pair forms:

1. **Clinic patient adds a personal space** (Profile → Spaces): `POST
   /mobile/personal/add`. The session proves the person; no code. A recovery
   goal inherits the chart's operation and date.
2. **Subscriber adds their hospital** (Profile → Spaces): `POST
   /mobile/personal/link-hospital` with `mode: enroll` (a record found through
   `/patients/search`; open when the record has no number or carries this one,
   else a texted code to the record's number) or `mode: join` (a new record at
   that hospital).
3. **Personal sign-up with a number already on a chart**: the join asks for
   a texted code; verifying it (`POST /mobile/personal/verify`) pairs the new
   space with the chart. Without Sendblue the join is refused and the person is
   told to sign in to the record first and add the space from Profile.

Switching is `POST /mobile/profiles/switch {patient_id}`: a session for the
other row. The app keeps one token per space (Keychain) so switching back is
instant. `GET /mobile/me` carries `profiles` (the spaces) and `subscription`.

The shared phone number is deliberate. `_claim_phone` and the clinic
re-enroll leave a paired row's number alone; `tasks.patient_for_phone` routes
an inbound text to whichever row is mid-way through a task conversation, else
the clinic chart.

## Accounts, consent and the lake

A subscriber signs up with a name, an email and a password (`auth.py`:
scrypt hashes in `personal_credentials`; eight failed attempts lock the login
for fifteen minutes and answer 423). `POST /mobile/personal/login` opens a
session on any phone; `password/forgot` texts a code when the account has a
number and Sendblue is configured (the answer is the same either way),
`password/reset` and `password/change` do what they say. A phone number is
optional and only feeds texts and pairing with a hospital record.

Before anything is stored the app shows the beta consent (`GET
/mobile/consent`: `CONSENT_VERSION`, the full text and its SHA-256, the
scopes). Three scopes are required (beta acknowledgement, data storage, AI
processing) and one is optional (research use, switchable later through
`PATCH /mobile/personal/consent/research`). Acceptance is a `consents` row
(version, text hash, scopes, typed signature, device, app version) plus a copy
of the whole form in the person's lake; hospital enrolments record it too
(`consent` on enroll, verify and join). `GET /mobile/me` carries
`consent.needs_consent`, which the app turns into a full-screen gate whenever
the version moves.

The lake (`archive.py`) is the tier's memory for later work, under
`personal/<patient>/lake/` in the personal bucket: `consent/<version>.json`,
`days/<date>.json` (the morning's dashboard, brief, plan and the week's logs),
`ai/<kind>/<stamp>.json` (every model result with its prompt version, provider
and digest fingerprint), `coach/<stamp>.json` (each coach turn) and
`events/<stamp>-<name>.json`. `DELETE /mobile/personal/account` unpairs,
revokes sessions, deletes the rows and sweeps the prefix, lake included.

## Subscription

Every personal account starts on a trial (`PERSONAL_TRIAL_DAYS`, 14). The app
sells two auto-renewing products through StoreKit 2
(`com.medpull.recovery.personal.monthly` / `.annual`, `ios/MedPull.storekit`
for local testing) and reports each signed transaction (JWS) to
`POST /mobile/personal/subscription/apple`. The server, never the app, decides
access (`subscription.status`): the best live row among trial, Apple (three
days' grace after expiry) and complimentary grants. Readout routes answer
**402** with the state in `X-MedPull-Paywall` once access lapses; the app shows
the paywall over the personal screens with a switch to the hospital space when
there is one.

Verification mode is `APPLE_SUBSCRIPTION_VERIFY`: `lenient` (decode, check
bundle id, product and expiry; grant recorded `verified=false`) until App
Store Connect is live, because Xcode's local StoreKit signs with a certificate
Apple's chain cannot vouch for; `strict` verifies the x5c chain to the pinned
Apple Root CA G3 fingerprint and the ES256 signature (`cryptography`).

## The readouts (`metrics.py`)

Every number is a comparison with the person's own trailing baseline (28
days ending yesterday, at least five points, SD floors as in the clinic
engine). Every panel carries its `method`, `confidence` and `coverage`.

| Panel | What is computed |
| --- | --- |
| Readiness | Weighted z-scores: ln-HRV 40 %, resting HR 25 %, sleep vs need 25 %, breathing rate and skin temperature 5 % each (penalty-only). Logistic to 0–100, slope ln(67/33): one SD off, taken together, is the green/red edge. 28-day history, each day against its own trailing baseline. |
| HRV | ln-transformed 7-day mean and 28-day baseline; smallest worthwhile change = 0.5 SD; balance = 7d/28d; CV over 7 days; 14-day OLS slope with a t-statistic. RMSSD or SDNN, whichever the device ships. |
| Resting HR | 7-day mean vs baseline mean/SD; last night's z. |
| Sleep | Need = 28-night median (or the person's target) + up to 1 h after a heavy day. Debt = seven nights' shortfall, discounted 15 % a night. Consistency = circular SD of bedtime and wake time over 14 nights. Efficiency and stage shares from the sleep summaries. |
| Training load | Load from active energy, else exercise minutes, else steps. EWMA acute (7 d) and chronic (28 d), ACWR with 0.8–1.3 as the working range and 1.5 the spike. Banister fitness (42 d) / fatigue (7 d) / form. Foster monotony and strain on the load above the 28-day 20th-percentile floor. A 0–21 day-strain figure. Weekly minutes vs target. |
| Cardio fitness | VO2 max and one-minute HR recovery (new `MetricType`s, read from HealthKit by the app and posted through the gait upload path); 90-day change; a coarse age/sex band. |
| Body signals | SpO₂, breathing rate, skin temperature vs baseline; the strain tally counts adverse overnight moves across resting HR, HRV, breathing rate and temperature. Guarded wording; never a condition. |
| Rhythm | Bedtime/wake regularity; interdaily stability over hourly steps when the phone sends them. |
| Activity | Steps, exercise minutes, active energy: today, 7 d, 28 d. |
| How you feel | Energy, soreness, mood, sleep quality, RPE from the morning check-in and the coach (`personal_logs`). |

The **verdict** (push / steady / easy / rest / unknown) reads readiness, the
body tally, ACWR, form and sleep debt; the goal (`recovery`, `performance`,
`sleep`, `everyday`) decides the order of sections and the wording. A recovery
goal also surfaces the clinic engine's M1–M18 report for the same stream.

## AI

`insights.py`: the brief (a headline of at most nine words naming the
signals that decided today with their values, never the verdict or the score,
which the tile shows beside it; then 45–90 words ending in one instruction)
and deep dives (recovery, training, sleep, weekly; 140–240 words). An
account still learning (verdict `unknown`) never reaches the model: the
deterministic brief says what to do and costs nothing. Same provider chain and cache table
as the clinic (`insights`, kinds `personal_brief` / `personal_deep`), keyed on
the dashboard's digest fingerprint and the day. Validation bans diagnostic and
prescribing language and enforces length; a rejected paragraph is replaced by
the deterministic renderer. The guardrail sentence is
`PERSONAL_GUARDRAIL_SENTENCE` ("Guidance for training and recovery — not
medical advice."), added in code.

## The morning run (`daily.py`)

`start_day` writes today's plan, generates the brief, puts it on the thread
as a `Message` with an `open_task` button into the check-in, and texts it
(with "Reply 1 for your morning check-in") when the profile opted in. The app
calls `POST /mobile/personal/day` on open; EventBridge invokes the API function
with `{"action": "personal_daily"}` once a morning (`PersonalDailyCron`, 12:00
UTC by default), which holds the write lock like the seed and uploads once.

## Storage

`PersonalDataBucket` (CloudFormation) holds subscribers' files and data
exports, never served by CloudFront; the function's IAM grants are per-bucket
so neither grant reaches the other. `blobs.bucket_for(key)` routes keys under
`personal/` to it (`PERSONAL_S3_BUCKET`); on a laptop it is a sibling
directory. `POST /mobile/personal/export` writes a JSON document there and
answers with a five-minute link (inline without S3). The same bucket holds
each subscriber's lake (above). The deployed name is the stack output
`PersonalDataBucketName`.

## Verifying on the simulator

Debug builds accept launch arguments: `-MP_SESSION_TOKEN <token> -MP_TAB
stats|tasks|talk|health` signs in without onboarding (the unsigned simulator
build has no keychain, so the token is used directly);
`-MP_ONBOARDING_STEP mode|consent|login|personalAbout|goals` opens the flow
on a step; `-MP_SHOW profile|session|brief` opens that sheet over Today;
`-MP_SCROLL <id>` scrolls Today (`plan`, `numbers`, `brief`, `quick`) or Stats
(`week`, `trends`, or a panel key, which also expands it); and
`-MP_SCROLL_PROFILE account` scrolls the profile sheet. A synthetic athlete
is one script away: create the account through `/mobile/personal/join`, run a
seed script with `PYTHONPATH=. uv run python <script> <patient_id>` from
`backend/` (ingest through `ingest_observations`, logs through
`personal.logs.record`), then `POST /mobile/personal/day`. Point the app at a local API with `xcrun simctl spawn "iPhone 17"
defaults write com.medpull.recovery api_base_url -string http://localhost:8000`.
