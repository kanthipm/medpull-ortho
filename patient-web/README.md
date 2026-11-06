# MedPull patient app — web

The patient-facing app, for the browser: the same product as the iPhone app
in `ios/` (Today, Progress, Measure, Care, the profile and connections
sheets, the daily check-in, the thread with photos, videos, voice notes and
files, and the onboarding flow), built against the same `/api/mobile/*`
routes and the same design system (medpull.org: Outfit, warm neutrals,
sage, gradient tiles, glass, lime; light by default with dark and system
modes behind the avatar).

It is the **clinic version only**: a hospital's patient, recovering from an
operation or followed for their everyday signals. The MedPull Personal
(subscriber) tier and the Sports athlete app are not part of it.

**Apple Health** cannot be connected from a browser — HealthKit lives on the
phone — so the web app has no Health step in onboarding and no Connect
button anywhere. The Connections sheet reports what the MedPull iPhone app
has already connected (last sync; the data shows on every tab) and says
that the connection is made there, signed in to the same record. Wearables
through Junction (Oura, Garmin, WHOOP…) link from here as they do on the
phone.

## Run it

```bash
make dev-backend        # the API on :8000 (from the repo root)
make dev-patient-web    # Vite on :5174, proxying /api to :8000
```

Then open http://localhost:5174/patient/ — the app is built with the base
path `/patient/`, the same path it has on the deployed stack. `npm install`
once inside `patient-web/`. The dev server runs on port 5174 so it can sit
beside the provider console (`make dev-frontend`, :5173).

`npm run build` produces `dist/`; `npm run lint` and `tsc -b` are what the
console runs too.

## Where it is served

- **AWS**: `./infra/deploy.sh` builds it and uploads `dist/` to
  `web/patient/` in the data bucket next to the console; the CloudFront
  rewrite function sends `/patient/*` client routes to `/patient/index.html`
  (`infra/cloudformation.yaml`). So it lives at `https://app.medpull.org/patient/`
  and talks to the same `/api/*` origin.
- **Single process** (`make run`): the backend serves `patient-web/dist`
  under `/patient` beside `frontend/dist`.
- A saved server URL on the Profile screen (Developer) points the app at a
  different API at runtime, as on the phone.

## How it maps to the iPhone app

| iPhone (`ios/MedPull`) | Web (`patient-web/src`) |
| --- | --- |
| `Core/AppModel.swift` | `core/appModel.ts` — one observable model, `useApp()` |
| `Core/APIClient.swift`, `Core/Models.swift` | `core/api.ts`, `core/models.ts` — same wire types, snake ↔ camel |
| `Core/MotionCapture.swift` | `core/motion.ts` — DeviceMotion; no pedometer, the server counts |
| `Core/SpeechController.swift`, `SpokenVoice.swift` | `core/speech.ts` — Web Speech API |
| `Core/Attachments.swift` | `core/attachments.ts` — canvas JPEG, MediaRecorder / WAV |
| `Core/HealthConnector.swift` | `core/health.ts` — never connects; carries the iPhone note |
| `UI/Theme.swift`, `Components.swift`, `Rows.swift`, `TileArt.swift` | `ui/theme.css`, `components.css`, `components.tsx`, `rows.tsx`, `tileArt.tsx` |
| `Features/*` | `features/*`, one folder per tab or sheet |

The phone's SF Symbols are drawn with the nearest Lucide glyph under the
same SF name (`ui/icons.tsx`), so a screen ported from Swift keeps its
`symbol: "figure.walk"` lines.

Deep links: `/patient/tasks/<id>` opens that task on Today (the phone's
`medpull://tasks/<id>`); `/patient/connections` opens the Connections sheet
(`medpull://wearables`).
