# Wearable data aggregation APIs and direct device APIs for RTM ingestion (state of market, 2026)

## Summary

The aggregator market has consolidated into four viable commercial options for a HIPAA workload — Junction (fka Vital, ~$0.50/user/mo with $300/mo minimum, SOC 2 Type 2 + ISO 27001, sandbox at app.junction.com), Terra ($399-499/mo base + credit overages, but BAA only on custom-priced Enterprise), ROOK ($399/mo for 750 active users up to $1,999/mo for 15,000 — cheapest at scale), and Spike (from $450/mo) — while Validic remains the enterprise/EHR-integrated incumbent and Metriport has exited wearables entirely. On the direct-API side the platform constraint set is hard: Apple HealthKit has no server-side API whatsoever (native iOS app + background delivery required, and it exposes HRV only as SDNN, not the RMSSD our engine uses), Google Fit's REST API has no replacement and dies end of 2026 (new signups already closed May 1, 2024) with Health Connect being strictly on-device, and Fitbit intraday data for commercial Server/Client apps is granted only case-by-case via an Issue Tracker petition. Garmin, Oura v2, Whoop v2, Withings, and Polar all offer free webhook-push APIs adequate for our vitals set; Dexcom is retrospective-delayed unless you join its real-time partner program. Apple Health Records (FHIR R4 via HKClinicalRecord) and SMART Health Cards exist but are read-only, app-mediated, and low-value for our vitals pipeline today. Recommendation: hybrid strategy — Junction as the launch aggregator (HIPAA-eligible at $300/mo floor, covers Oura/Whoop/Garmin/Withings/Fitbit/Dexcom server-side) plus our own native HealthKit/Health Connect collection in the companion app (which an RTM product needs anyway for PROs); revisit ROOK at ~5,000+ patients where its flat tiers undercut per-user pricing. Estimated aggregator TCO: ~$3.6k/yr at 100 patients, ~$6-12k/yr at 1,000, ~$24-60k/yr at 10,000, versus roughly $150-250k one-time engineering to build all direct integrations in-house.

## Findings

### Terra API: $399-499/mo base, credit-metered, BAA gated to Enterprise
*[strong]*

Quick Start plan is $499/mo (monthly) or $399/mo (annual) including 100,000 credits; an active user consumes ~200 credits/mo (~$2/user effective), overage priced at $0.005/credit minimum with volume discounts. Add-ons: Streaming API $99/mo+usage, Blood Report API $499/mo, Graph API $50/2 graphs/mo. Webhook-push architecture (data delivered on provider sync; webhook signed via `terra-signature` HMAC header). SOC 2 Type II; 'Signed BAA (data protection agreement)' is listed ONLY under the custom-priced Enterprise plan — the $399-499 tier does not include a BAA, which is disqualifying for PHI use at startup pricing. 30-day money-back guarantee; 'Usage Spike Protection' first 6 months.

> Terra pricing page, 2026, https://tryterra.co/pricing

### Junction (fka Vital): ~$0.50/user/mo with $300/mo minimum; HIPAA-native; also does labs
*[moderate]*

Third-party comparisons cite $0.50 per user/month with a $300 monthly minimum (pricing no longer published at junction.com/pricing — 404s; confirm in sales call). HIPAA compliant with SOC 2 Type 2, ISO 27001, GDPR; BAA available (healthcare-focused company; raised $18M Series A, Mar 2025, TechCrunch). Claims 300+ device integrations on-site (500+ in press), incl. Apple Watch (via mobile SDK), Oura, Withings, Dexcom CGM, Garmin, Fitbit, Whoop. Self-serve sandbox at app.junction.com. Webhooks delivered via Svix (HMAC-SHA256 `svix-signature` scheme with timestamp replay protection); historical backfill on connect (default ~180 days for most providers, configurable). Unique adjacency: nationwide lab ordering (walk-in, at-home kits, mobile phlebotomy) under the same API.

> junction.com 2026, https://www.junction.com/; TechCrunch 2025, https://techcrunch.com/2025/03/11/junction-an-api-to-link-health-wearables-with-labs-raises-18m; openwearables.io comparison 2025

### ROOK: flat tiers — $399/mo (750 active users), $999 (5,000), $1,999 (15,000); cheapest at scale
*[strong]*

Core $399/mo up to 750 active users incl. all integrations, sandbox, basic SLAs; Core+ $999/mo up to 5,000 users + 3 free add-ons; Business $1,999/mo up to 15,000 users with advanced SLAs, white-label auth, ROOKScore; Enterprise custom with FHIR-compliant data output. Add-ons $99-$499/mo (Notifications Webhook $99, end-user data-extraction app $499). Claims HIPAA and GDPR compliance ('data anonymized, encrypted') but pricing page does not mention a BAA — must be confirmed. Mobile SDKs (iOS/Android) cover Apple Health and Health Connect/Samsung Health on-device extraction, which pure server-side aggregators cannot. The 'Thryve/Rook' pairing: Berlin-based Thryve (mHealth Pioneers) still operates its own API and docs (docs.thryve.health active in 2026); a ROOK-Thryve consolidation is implied in market chatter but I found no primary confirmation — verify before relying on either roadmap.

> ROOK pricing, 2026, https://www.tryrook.io/pricing; Thryve docs, https://docs.thryve.health

### Spike API: from $450/mo, 40+ providers/500+ devices, explicit event deduplication
*[strong]*

Entry 'Sandbox' tier starts at $450/mo: unlimited API/SDK integrations, 40+ providers, 500+ devices, medical IoT integrations, standardized data model, historical data retrieval, and — notably for our idempotent-upsert design — built-in event deduplication. Claims full HIPAA/GDPR/CCPA compliance with dedicated implementation engineer even at entry tier; Enterprise adds custom MSAs/SLAs and 'AI-ready (MCP-compatible)' data. No per-user price published. More expensive floor than Junction ($450 vs $300/mo) with less healthcare depth (no labs, weaker EHR story).

> Spike API pricing, 2026, https://www.spikeapi.com/pricing

### Validic: enterprise incumbent, EHR-integrated RPM (Epic/Oracle/Salesforce), non-public pricing
*[moderate]*

At HLTH 2025 Validic showcased a dual offering: (1) wearable data API for digital health/life sciences and (2) EHR-integrated RPM with generative-AI summaries for health systems, with productized integrations into Epic, Oracle Health, and Salesforce Health Cloud. Signs BAAs (core business is PHI). Pricing is contract-only; market reports place typical contracts in the mid-five to six figures annually ($50k-150k+), which prices out a startup until health-system distribution matters. Relevant later if MedPull sells into hospital orthopedics service lines that demand Epic flowsheet write-back for RTM billing.

> Validic press release, Oct 2025, https://validic.com/news/validic-to-showcase-dual-solutions-at-hlth-2025--wearable-data-api-for-digital-health-and-ehr-integrated-remote-patient-monitoring-for-health-systems/

### Metriport has EXITED wearables — do not build on its device API
*[moderate]*

Metriport (open-source, FHIR-native) pivoted to being a medical-records/HIE on-ramp (Carequality/CommonWell network access) and wound down its wearables Devices API; industry analysis (Brendan Keeler, 'The Wearables Interoperability Stack') confirms the exit. Its remaining product is actually relevant to our FUTURE EHR-integration gap (patient record retrieval via nationwide HIEs, usage-based pricing reportedly from ~$0.20/query), but it is no longer a wearable aggregator option.

> Health API Guy substack, 2025, https://healthapiguy.substack.com/p/the-wearables-interoperability-stack; saasworthy Metriport pricing

### Open-source/standards lane: Open mHealth (IEEE 1752.1) schemas + MIT-licensed Open Wearables
*[moderate]*

Open mHealth schemas were standardized as IEEE 1752.1-2021 (sleep and physical activity data representation); its reference aggregator Shimmer is effectively unmaintained — use the schemas as a canonicalization reference for our Observation store, not as running software. New in 2025: 'Open Wearables' (openwearables.io), an MIT-licensed self-hosted aggregator ($0/user, self-host; BAA + HIPAA-eligible infra only on its paid Enterprise plan) positioning directly against Terra/Rook/Spike/Junction — young project, treat as a hedge/reference implementation rather than production dependency for PHI.

> openwearables.io pricing/compare, 2025-2026, https://openwearables.io/pricing; IEEE 1752.1-2021

### Apple HealthKit: no server API, native iOS app mandatory — and HRV is SDNN, not RMSSD
*[strong]*

HealthKit data lives on-device; the only extraction path is a native iOS app using HKObserverQuery + enableBackgroundDelivery (per-type frequency caps: .immediate for heart rate, but step count and many types are throttled to hourly; delivery requires the app to wake, so uploads lag device sync by minutes-to-hours and stall if the user force-quits the app). Free; App Review prohibits selling health data or using it for ads. Metric coverage for us is excellent: restingHeartRate, heartRateVariabilitySDNN (NOT RMSSD — cannot feed our RMSSD EWMA/CUSUM without a separate SDNN baseline channel), oxygenSaturation, respiratoryRate, sleep stages, appleSleepingWristTemperature (delta-based, Watch Series 8+/Ultra), stepCount, walkingSpeed, walkingAsymmetryPercentage, walkingDoubleSupportPercentage, appleWalkingSteadiness — the gait set is uniquely valuable for ortho recovery curves. Historical backfill: full history readable on first authorization (subject to user grant).

> Apple HealthKit docs (developer.apple.com/documentation/healthkit); Momentum analysis 2025, https://www.themomentum.ai/blog/what-you-can-and-cant-do-with-apple-healthkit-data

### Google Fit REST API: signups closed May 1, 2024; supported only until end of 2026; NO replacement REST API
*[strong]*

Google's official migration FAQ states 'There is no alternative to the Fit REST API' — the two sanctioned paths are Health Connect (on-device only, no cloud API) or the Fitbit Web API (cloud, account-centric). New Fit REST/Android API signups stopped May 1, 2024; existing apps supported 'until the end of 2026' (deadline was extended from the originally announced Jun 30, 2025). Health Connect specifics that bite: built into Android 14+ (APK on 9-13); apps can read only 30 days of history prior to first permission grant unless they also hold READ_HEALTH_DATA_HISTORY; background reads need READ_HEALTH_DATA_IN_BACKGROUND (Android 15+); OEM battery managers (Samsung, Xiaomi, OnePlus) throttle background sync, so Android-side latency is inherently jittery. Samsung Health syncs into Health Connect since app v6.22.5 (Oct 2022), making Health Connect the practical single Android read point for Galaxy Watch data.

> Android Fit migration FAQ, 2026, https://developer.android.com/health-and-fitness/health-connect/migration/fit/faq

### Fitbit Web API: free, 150 req/hr/user, but commercial intraday access is case-by-case approval
*[strong]*

Rate limit: 150 API requests/hour per consented user, resets hourly, 429 + Fitbit-Rate-Limit-* headers. Intraday endpoints exist for Active Zone Minutes, Activity (steps: 1min/5min/15min), Breathing Rate, Heart Rate (1sec/1min), HRV, SpO2 — but for 'Client'/'Server' app types access is 'granted on a case-by-case basis' via a Google Issue Tracker request; auto-granted only for the Personal app type; commercial apps face 'thorough review' and Fitbit 'reserves the right to limit this access.' Daily-level HRV is RMSSD from deep sleep (matches our engine's metric, unlike Apple), plus skin-temperature delta and SpO2 in the Health Metrics endpoints. Subscriptions API gives webhook pings (activities/sleep/body collections; you then fetch — verify via X-Fitbit-Signature HMAC-SHA1). Consumer API — Google does not sign a BAA. Fitbit accounts were force-migrated to Google accounts by Feb 2, 2025.

> Fitbit dev docs, 2026, https://dev.fitbit.com/build/reference/web-api/intraday/ and application-design page

### Garmin Health API: no recurring license fee, push webhooks, second-level HR; BBI licensed separately
*[strong]*

Garmin Connect Developer Program has 'no licensing or maintenance fees' (business use only; some integrators report a one-time admin/setup fee ~$5,000 — unverified); approval confirmation in ~2 business days, evaluation environment first (~15 test users), typical integration 1-4 weeks. Push OR ping/pull architecture (JSON webhooks fired on device sync to Garmin Connect). Metrics: steps, HR (second-level during activities, epoch summaries otherwise), sleep, stress, pulse ox (SpO2), respiration, body composition, blood pressure; beat-to-beat interval (BBI/HRV raw) 'commercial use requires licensing' — nightly HRV summaries are available but confirm scope during vetting. Backfill via explicit backfill endpoints per summary type (historically capped and rate-throttled; plan for chunked replay). No BAA — consumer platform.

> Garmin Health API overview, 2026, https://developer.garmin.com/gc-developer-program/health-api/

### Oura API v2: free, 5,000 req/5min, webhooks with challenge verification; PATs deprecated Dec 2025
*[strong]*

V2 rate limit 5,000 requests per 5 minutes, enforced per-access-token AND per-application. Personal Access Tokens deprecated Dec 2025 — new integrations must use OAuth2. Webhook subscriptions use a verification challenge (GET with challenge echo) and are 'strongly recommended' over polling. Exposes exactly our vitals: nightly average HRV (RMSSD) plus 5-min HRV time series inside sleep documents, resting/lowest HR, respiratory rate, SpO2 (spo2_percentage daily), temperature deviation (delta from baseline — note: NOT absolute skin temp), sleep stages/duration, daily activity/steps. Backfill: full historical data readable once authorized. Consumer API, no BAA; Oura Health/Teams B2B program exists for research fleets (ring hardware $299-349 + $5.99/mo membership per patient if provisioning devices).

> Oura API docs, 2026, https://cloud.ouraring.com/docs and https://api.ouraring.com/v2/docs

### Whoop API v2: 100 req/min & 10,000 req/day; v1 webhooks removed; UUID-keyed events
*[strong]*

Default limits 100 requests/minute and 10,000 requests/day per client (increases via formal application), X-RateLimit-* headers, 429 on breach. v1 API/webhooks removed (v1 sunset completed Oct 2025); v2 webhooks key recovery events to the UUID of the associated sleep, and workout/sleep events use UUIDs instead of integer IDs — dedupe keys must be UUID-based with an ID-mapping lookup for any stored v1 identifiers. Webhook payloads signed via X-WHOOP-Signature (HMAC-SHA256 of timestamp+body) with X-WHOOP-Signature-Timestamp. Recovery payload carries hrv_rmssd_milli (RMSSD — engine-compatible), resting_heart_rate, spo2_percentage, skin_temp_celsius (absolute); plus sleep stages, respiratory rate, strain/cycles. Free API; hardware requires WHOOP subscription (~$199-359/yr); no BAA.

> WHOOP developer docs, 2026, https://developer.whoop.com/docs/developing/rate-limiting/ and v1-v2 migration guide

### Withings: free public API with paid 'Health Solutions' tiers; the only cellular-device option
*[moderate]*

Public API is free after app registration (documented throttle ~120 requests/minute) with webhook 'Notify' subscriptions (callback ping on new measurement; you then poll Measure endpoints — appli-type coded categories, e.g. 1=weight, 4=BP, 44=sleep). Advanced/medical tiers (Withings Health Solutions) are contract-priced and unlock dropship logistics, cellular devices (BPM Connect Pro, Body Pro scale — sync WITHOUT a smartphone, decisive for ~66-year-old arthroplasty patients), raw/high-frequency data, and enterprise terms incl. BAA. Metrics: BP, weight/body comp, SpO2, skin/body temp (Thermo), sleep (Sleep Analyzer mat: apnea-hypopnea index, HR, respiratory rate), steps via ScanWatch. Backfill: full account history via Measure API date-range queries.

> Withings Partner Hub, 2026, https://developer.withings.com/developer-guide/v3/withings-solutions/withings-api-plans/ (plan page JS-gated; tier names from portal nav + integrator reports)

### Samsung Health: legacy SDK dead (Jul 31, 2025); new Data SDK is on-device; Health Connect is the practical route
*[strong]*

Samsung Health SDK for Android deprecated July 31, 2025; replacement 'Samsung Health Data SDK' (v1.1.0 released Mar 12, 2026) is on-device only, requires per-data-type user consent, and requires Samsung partnership approval for production. Since Samsung Health v6.22.5 (Oct 2022) data syncs into Health Connect, so a Health Connect reader in our Android companion app captures Galaxy Watch vitals (HR, sleep, SpO2, skin temp on Watch 5+) without a separate Samsung integration. Caveat: sync cadence into Health Connect is uneven per data type (exercise near-immediate, sleep delayed), adding hours of jitter our coverage gate must tolerate.

> Samsung Developer health docs, 2026, https://developer.samsung.com/health/android/overview.html and Data SDK release notes

### Polar AccessLink v3 and Dexcom: niche but free; Dexcom standard API is NOT real-time
*[moderate]*

Polar AccessLink v3: free after registration; webhook support for exercise/sleep/nightly-recharge events; exposes training sessions, continuous HR, sleep, Nightly Recharge (ANS/HRV-based recovery); modest undocumented rate limits; small install base in 66-yo ortho population — low priority. Dexcom API v3: free sandbox with simulated users (no hardware needed); OAuth2; endpoints /v3/users/self/egvs, /devices, /events, /alerts, /calibrations, /dataRange; standard API serves RETROSPECTIVE estimated glucose values with a delay (historically 3h in v2, reduced ~1h in v3 — confirm current figure with Dexcom; docs fetch 404'd during research); true real-time streaming requires the invite-only Dexcom real-time/partner program. Relevant only for diabetic comorbidity infection-risk enrichment, not core vitals.

> Polar AccessLink, https://www.polar.com/accesslink-api/; Dexcom developer portal, https://developer.dexcom.com/ (portal is JS-rendered; delay figure from prior v2/v3 documentation)

### Apple Health Records (FHIR) and SMART Health Cards: real but marginal for our vitals pipeline
*[strong]*

Apple Health Records surfaces clinical records as raw FHIR (R4, with DSTU2 for legacy connections) via HKClinicalRecord types (allergies, conditions, immunizations, lab results, medications, procedures, vitals) from hundreds of connected US health systems — but it is read-only, requires the native iOS app + separate user authorization per record type, delivers provider-entered EHR data (not device streams), and cannot be pulled server-side. Useful later for pre-op med lists/comorbidities (infection risk priors), not for wearable vitals. SMART Health Cards: HL7 FHIR R4 bundle serialized into an ES256-signed JWS in a QR (spec at spec.smarthealth.cards); issuers governed by the VCI coalition; post-COVID issuance has contracted to vaccination/lab-result niches, with SMART Health Links (shareable URLs for payloads too big for QR) as the successor pattern and SMART Health Insurance Cards as the active 2024-2026 use case. Neither is an ingestion priority for MedPull v1.

> smarthealth.cards (VCI), 2026, https://smarthealth.cards/; Apple HealthKit HKClinicalRecord documentation

### TCO comparison at 100 / 1,000 / 10,000 monitored patients (aggregator licensing only)
*[moderate]*

100 patients: Junction $300/mo minimum = $3,600/yr (Terra $399-499/mo base=$4.8-6k/yr but NO BAA at that tier; ROOK Core $399/mo=$4.8k/yr; Spike $450/mo=$5.4k/yr). 1,000 patients: Junction ~$500/mo=$6k/yr; ROOK Core+ $999/mo=$12k/yr; Terra ~200k credits→base+~$500 overage≈$11-12k/yr + Enterprise uplift for BAA. 10,000 patients: Junction ~$5,000/mo=$60k/yr; ROOK Business $1,999/mo=$24k/yr (covers to 15,000 — cheapest); Terra ~2M credits≈$115-125k/yr; Validic likely $100k+. Direct-build alternative: $0 licensing but ~6-8 provider integrations × 2-6 eng-weeks each plus perpetual API-churn maintenance (Whoop v1 removal, Oura PAT deprecation, Fit shutdown all within 18 months) ≈ $150-250k initial + ~0.25 FTE ongoing. Crossover favors ROOK on pure price at ≥5k patients, but Junction's BAA-at-floor-price and healthcare posture wins at launch.

> Synthesis of vendor pricing pages: tryrook.io/pricing, tryterra.co/pricing, spikeapi.com/pricing, openwearables.io comparisons, 2025-2026


## Implications for backend

- HRV metric normalization is a correctness blocker: Apple HealthKit yields SDNN only, while Fitbit, Oura, and Whoop yield RMSSD — the canonical Observation schema needs an explicit hrv_method field (sdnn|rmssd) and the EWMA/CUSUM engine must keep per-method baselines; never mix SDNN and RMSSD in one control chart (they are not unit-convertible).
- Temperature semantics differ per provider: Apple and Oura deliver DELTAS from a rolling baseline, Whoop delivers absolute skin temp Celsius, Withings Thermo delivers absolute body temp — store a temp_reference field (absolute|baseline_delta) and route deltas straight into the deviation index (skipping our own baseline subtraction) to avoid double-differencing.
- Restatement handling: Fitbit, Garmin, and aggregators resend updated daily summaries as sleep/HR data finalizes (sleep records commonly restate 2-3 times in 24h) — the idempotent upsert must key on (patient, provider, metric, effective_period, provider_record_id) and overwrite on newer modified_at, and the composite deviation index must be recomputable when a prior day's value is restated (append-only raw log + derived-table rebuild).
- Latency must be modeled per-source in the coverage/confidence gate: webhook-push aggregators deliver minutes after device-to-cloud sync, but HealthKit background delivery adds hours (hourly throttles, app force-quit) and Health Connect adds OEM battery-manager jitter — gate freshness thresholds should be per-provider (e.g., 6h for cloud webhooks, 24-36h for phone-mediated sources) rather than global.
- Do not architect around Fitbit intraday for commercial use — approval is case-by-case and revocable; design the steps/walking-speed expected-recovery pipeline to run on daily aggregates with intraday as progressive enhancement, and prefer Apple gait metrics (walkingSpeed, walkingAsymmetryPercentage, doubleSupportPercentage) which need no special approval.
- Webhook endpoint needs per-provider signature verifiers behind one interface: Svix HMAC (Junction), terra-signature HMAC-SHA256 (Terra), X-WHOOP-Signature+timestamp, X-Fitbit-Signature HMAC-SHA1, Oura GET challenge handshake — plus SQS/queue buffering in front of Lambda because provider syncs and backfills arrive in bursts (a user's 180-day backfill can be thousands of events in minutes).
- BAA chain for HIPAA: Junction (or Terra Enterprise/ROOK enterprise) must sign a BAA with us AND our AWS account already needs its BAA (AWS Artifact) covering Lambda/CloudFront/S3/SQS in the data path; direct consumer APIs (Fitbit, Garmin, Oura, Whoop) do not sign BAAs — under HIPAA that data becomes PHI only once we ingest it, so consent language must cover patient-directed collection from non-covered consumer platforms.
- Cost gating: at launch the entire ingestion licensing bill is Junction's $300/mo floor; budget the crossover review at ~5,000 patients where ROOK Business ($1,999/mo flat to 15k users) undercuts per-user pricing, and keep the connector interface provider-agnostic so an aggregator swap is a config change, not a rewrite (we already scaffolded this correctly).

## Open questions

- Junction's current exact per-user price and BAA terms (pricing page now 404s; the $0.50/user + $300 minimum figure is from third-party comparisons — confirm in sales conversation, and ask about Apple HealthKit SDK data flow specifics).
- Will Fitbit/Google grant intraday access to a commercial RTM application, and what evidence package do they require via Issue Tracker? (Determines whether Fitbit users get intraday HR or daily-only.)
- Garmin licensing scope: is the nightly HRV summary included in the free Health API tier, or does our HRV use case trip the beat-to-beat-interval commercial license fee (and is the reported ~$5k one-time admin fee real)?
- ROOK vs Thryve corporate status — merged, partnered, or independent competitors? Affects which of the two European-coverage roadmaps is durable, and whether ROOK's non-enterprise tiers will sign a BAA.
- Dexcom API v3 exact data delay (1h vs 3h) and real-time partner program admission criteria — only matters if diabetic-comorbidity glucose monitoring enters the infection-surveillance roadmap.
- Terra: is a BAA obtainable at any price below full Enterprise, and what does Enterprise actually cost at ~1,000 users?
- Withings Health Solutions contract pricing for cellular devices + dropshipping — the strongest option for non-smartphone elderly arthroplasty patients, but no public numbers.
- For CMS RTM billing (98975-98977), does patient-provided consumer wearable data satisfy the 'medical device' requirement, or does that push us toward FDA-listed devices (Withings medical line) for billable monitoring days?