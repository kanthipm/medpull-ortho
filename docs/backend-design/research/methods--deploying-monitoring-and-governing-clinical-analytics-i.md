# Deploying, monitoring, and governing clinical analytics in production for a small-cohort post-op RTM platform (shadow deployment, drift detection, audit/reproducibility, regulatory-adjacent governance, AWS batch architecture)

## Summary

The single most load-bearing practice for MedPull is a silent (shadow) deployment: run every new engine version against live patients with clinicians blinded, for at least ~90 days and until a minimum count of high-tier events has accrued, because the best-documented silent trial (Kwong et al., hydronephrosis AI) saw AUROC collapse from 0.90 retrospective to 0.50 prospective purely from dataset drift — exactly the wearable firmware/device-mix risk MedPull faces. Report that evaluation against DECIDE-AI (17 AI-specific items + 10 generic); reserve SPIRIT-AI/CONSORT-AI for a future randomized (ideally stepped-wedge, clustered by surgeon/clinic) trial. For drift, at 10–1000 patients use Evidently's small-data defaults (two-sample KS at p<=0.05, chi-squared for categoricals) on weekly batches, plus deterministic guards keyed on device model + firmware version as first-class columns — PSI and NannyML-style label-free performance estimation are honest only above ~500–1000 observations per window and mostly inappropriate at current scale. Reproducibility should come from a bitemporal, append-only observation store (effective_date vs ingested_at, versioned restatements, never UPDATE) plus an immutable per-score audit event (input snapshot hash, feature vector, engine git SHA, config/threshold version, tier, reason codes, viewer, action) written to S3 with Object Lock; Feast is not warranted at this scale but its TTL-bounded point-in-time join semantics are the correctness spec to copy. Even while staying outside FDA device regulation via the CDS exemption, structure change management as a lightweight Predetermined Change Control Plan (description of modifications, modification protocol with pre-defined acceptance criteria, impact assessment) and follow the 10 FDA/Health Canada/MHRA GMLP principles, so a later regulated pivot is paperwork rather than a rewrite. HTI-1's 31 predictive-DSI source attributes (via 45 CFR 170.315(b)(11)) bind certified EHR vendors, not MedPull directly, but they are the de facto disclosure schema any EHR integration partner will demand — maintain a model card holding those attributes from day one, including subgroup performance and the known skin-tone bias risk in PPG-derived SpO2.

## Findings

### Silent trials catch deployment-killing drift that retrospective validation cannot: 0.90 -> 0.50 AUROC
*[strong]*

Kwong et al. ran a prospective silent trial of a hydronephrosis-obstruction AI at SickKids: clinicians blinded to predictions, Aug–Dec 2020, Silent Trial 1 = 523 kidneys/150 patients, Silent Trial 2 = 711 kidneys/202 patients. Retrospective test AUROC 0.90 fell to 0.50 in Silent Trial 1 due to dataset drift (patient-age shift, laterality distribution change, image-format differences); after correcting the pipeline, performance recovered to 0.85–0.92. Design themes they recommend evaluating during the silent phase: dataset drift, bias, feasibility, stakeholder attitudes. Implication for MedPull: the silent period must be long enough to accrue events and to expose cohort heterogeneity (multiple device brands, multiple surgeons), not a fixed calendar time; 150–200 patients was enough to expose catastrophic drift in their setting.

> Kwong et al., 'The silent trial – the bridge between bench-to-bedside clinical AI applications', Frontiers in Digital Health 2022, 10.3389/fdgth.2022.929508

### DECIDE-AI is the reporting standard for exactly MedPull's current stage (small-scale live evaluation)
*[strong]*

DECIDE-AI (Nature Medicine, May 2022; modified Delphi, 20 stakeholder groups) defines 17 AI-specific reporting items (28 subitems) + 10 generic items for early-stage live clinical evaluation of AI decision support: actual clinical performance at small scale, safety monitoring and error reporting, human factors/usability evaluation, description of modifications made during the study, and the human-AI interaction. It sits between offline validation and SPIRIT-AI/CONSORT-AI trials. Use its checklist as the protocol template for the first live pilot with surgeons, even if never published.

> Vasey et al., Nature Medicine 2022, PMID 35585198

### SPIRIT-AI (15 items) and CONSORT-AI (14 items) govern any future randomized evaluation
*[moderate]*

SPIRIT-AI adds 15 AI-specific items to trial protocols and CONSORT-AI adds 14 to trial reports (both published Sept 2020, Nature Medicine/BMJ/Lancet Digital Health): version of the algorithm used (and changes mid-trial), input-data quality and handling of poor-quality/missing input, human-AI interaction description, error analysis. For a pragmatic evaluation across surgeons/clinics, a stepped-wedge cluster design (Hemming et al., BMJ 2015;350:h391) is usually the right frame for clinical software: clusters (surgeon practices) cross from control to intervention at randomized times, all eventually receive it — politically feasible and handles secular recovery-protocol trends, but requires time-effect modeling (mixed model with cluster random effect and period fixed effect).

> Cruz Rivera et al. & Liu et al., Nature Medicine 2020 (SPIRIT-AI/CONSORT-AI); Hemming et al., BMJ 2015 (stepped wedge) — from background knowledge, not fetched this session

### The Epic Sepsis Model failure is the canonical argument for local prospective validation before go-live
*[strong]*

Wong et al. (JAMA Internal Medicine 2021) externally validated Epic's proprietary sepsis model on 27,697 patients / 38,455 hospitalizations (7% sepsis prevalence): hospitalization-level AUC 0.63 (95% CI 0.62–0.64) versus vendor-claimed 0.76–0.83; missed 67% of sepsis patients; alerted on 18% of all hospitalizations (severe alert fatigue). Lesson: never trust transported performance claims — validate on your own cohort in shadow mode, and measure alert burden (alerts per patient-week) as a first-class safety metric, not just discrimination.

> Wong et al., JAMA Intern Med 2021, PMID 34152373

### Continuous monitoring of deployed clinical AI: the AI-QI framework recommends control charts (CUSUM) on inputs and performance
*[strong]*

Feng et al. (npj Digital Medicine 2022) propose hospital 'AI-QI' units and adapt statistical process control — explicitly CUSUM procedures — to monitor (a) input-variable distributions and (b) the conditional outcome-predictor relationship of deployed models, to detect performance decay early; they stress that model-updating procedures are nascent and monitoring must be a standing cross-functional process. Convenient for MedPull: the engine already implements EWMA + CUSUM for patients; the same code (k=0.5, h=4–5 in standardized units) can monitor the fleet-level feature means (e.g., cohort mean resting HR, missingness rate) chunked weekly.

> Feng et al., npj Digital Medicine 2022, PMID 35641814

### Evidently's small-data drift defaults are the right statistical tests at 10-1000 patients
*[strong]*

Evidently (Python, Apache-2.0, evidently>=0.7) defaults: reference <=1000 rows -> two-sample Kolmogorov-Smirnov for numerical (n_unique>5), chi-squared for categorical, z-test for binary, drift flagged at p<=0.05; reference >1000 rows -> Wasserstein distance (numerical) and Jensen-Shannon divergence (categorical) with default threshold 0.1; dataset-level drift when a configurable share (e.g., 50%) of columns drift. Generates HTML reports usable as a weekly artifact. At MedPull's scale the KS-branch applies; note KS on daily-aggregated vitals violates independence if you pool days within patient — compare patient-level summaries (per-patient means over the window) or accept inflated false positives.

> Evidently documentation, docs.evidentlyai.com/metrics/explainer_drift

### NannyML CBPE/DLE estimate performance without labels but are mostly inappropriate at MedPull's current scale
*[strong]*

NannyML (Python, Apache-2.0) CBPE estimates classification metrics without ground truth by aggregating calibrated predicted probabilities into an expected confusion matrix (P(correct)=1-|y_hat - p_hat|); requires well-calibrated probabilities (NannyML calibrates via isotonic regression, 3-fold stratified splits on reference data); fails under concept drift and under covariate shift into unseen feature regions — both undetectable without labels. DLE trains a 'nanny' model to predict absolute error for regression. Inapplicability for MedPull today: the risk tier is rule-based (no probability output) and chunks of a few hundred patient-days give wide sampling error; revisit CBPE only if/when a calibrated probabilistic complication model exists and chunks reach ~500+ observations.

> NannyML documentation, nannyml.readthedocs.io (how_it_works/performance_estimation)

### PSI is a large-sample tool; use it only for fleet-level device-mix questions, with 0.1/0.25 conventions
*[moderate]*

Population Stability Index (sum over bins of (p_i - q_i) * ln(p_i/q_i), conventionally 10 quantile bins) with industry thresholds PSI<0.1 stable, 0.1–0.25 moderate shift, >0.25 major shift, originates in credit scoring and assumes roughly >=500 observations per window and >=20 per bin; below that it is noise. Alibi Detect (Python, alibi-detect, Seldon) offers KS, chi-squared, MMD, classifier-based and online drift detectors if a heavier framework is ever needed; whylogs (whylabs) does lightweight streaming data profiling (distribution sketches per batch) suited to Lambda. At MedPull scale: whylogs profiles + Evidently KS are sufficient; skip Alibi Detect.

> Industry convention (credit-risk PSI literature); Alibi Detect / whylogs documentation — from background knowledge, docs not fetched this session

### MedPull's four concrete drift risks map to metadata-keyed deterministic guards, not statistics alone
*[moderate]*

(1) Firmware update changes sensor calibration: a step-change within-patient that EWMA/CUSUM will misread as deterioration — log device_model + firmware_version per observation and force per-patient re-baselining (re-estimate baseline offset over the next 7–14 days) whenever firmware changes; (2) new device brand entering the cohort: stratify all drift comparisons by device_model, never pool brands in one KS test; (3) seasonality in step counts: use season-matched or trailing-quarter reference windows, or deseasonalize with STL before drift testing; (4) new surgeon/protocol: treat surgeon_id as a stratum; a new surgeon's patients should not enter the pooled expected-recovery-curve comparison until n>=10 episodes. These are label-free, small-n-safe controls; the statistical detectors are the backstop.

> Synthesis of Kwong et al. 2022 (drift taxonomy) and Feng et al. 2022 with MedPull's engine design; guard design is original

### Point-in-time correctness: Feast's TTL-bounded as-of join is the semantics to copy; Feast itself is overkill
*[strong]*

Feast implements point-in-time correct training joins by scanning backward from each entity-row event timestamp up to a feature-view TTL, excluding anything ingested later — preventing leakage of restated/late-arriving values. It requires an offline store (Parquet/warehouse), online store, and registry — unjustified below ~10^5 rows/day and a single consumer. Equivalent correctness in SQLAlchemy: bitemporal observation table (patient_id, metric, effective_date [when it happened], value, ingested_at [when we learned it], source, device_model, firmware_version, revision_seq), INSERT-only; 'current' view = max(revision_seq) per (patient, metric, effective_date); 'as-of T' view = max revision with ingested_at <= T. Every backtest and every historical-score reproduction must query the as-of view, never the current view.

> Feast documentation, docs.feast.dev/getting-started/concepts/point-in-time-joins

### Wearable data restatement is routine, so backtests on 'current' data have look-ahead bias by construction
*[moderate]*

Consumer wearable aggregates arrive late and get restated: multi-day sync gaps (watch offline), vendor reprocessing of historical HRV/sleep after algorithm updates, and timezone/day-boundary reassignment all silently rewrite past days. A backtest of the EWMA/CUSUM/tier pipeline using today's database answers 'what would we have flagged with data we did not have yet.' Correct procedure: replay day-by-day against the as-of view (ingested_at <= end of that day), score with the engine version pinned to that date, and report both 'as-of' and 'fully-settled' performance plus the data-latency distribution (share of a day's observations present within 24h/72h). The gap between the two runs is itself a key operating metric (how much alert timing depends on sync lag).

> Standard practice from quantitative-finance point-in-time backtesting transferred to wearables; consistent with Feast leakage rationale — no single clinical citation fetched

### FDA PCCP final guidance (Dec 2024): three components define disciplined change management even outside regulation
*[moderate]*

'Marketing Submission Recommendations for a Predetermined Change Control Plan for Artificial Intelligence-Enabled Device Software Functions' (finalized December 2024) requires: (1) Description of Modifications — enumerated, specific, verifiable planned changes with rationale, stating whether implemented automatically or manually and uniformly or per-site/subpopulation; (2) Modification Protocol — data management practices (collection, annotation, reference standards, sequestration of test data), re-training practices, performance evaluation with pre-defined acceptance criteria, and update procedures including user communication/labeling; (3) Impact Assessment — benefits/risks of each modification individually and cumulatively. A companion Jan 2025 draft ('AI-Enabled Device Software Functions: Lifecycle Management...') extends this to total product lifecycle. Adopting a mini-PCCP now (a versioned doc listing permitted parameter changes, e.g. threshold recalibration, with acceptance criteria on a frozen validation cohort) makes later 510(k)/De Novo submissions incremental.

> FDA final guidance, Dec 2024 (fda.gov; page not fetchable this session — content from background knowledge)

### GMLP: 10 FDA/Health Canada/MHRA principles are the checklist reviewers and partners will use
*[moderate]*

Good Machine Learning Practice (Oct 2021, FDA + Health Canada + UK MHRA): (1) multi-disciplinary expertise across lifecycle; (2) good software engineering and security practices; (3) participants/datasets representative of intended population; (4) training and test sets independent; (5) best-available reference-standard datasets; (6) model design tailored to available data, reflects intended use; (7) focus on human-AI team performance; (8) testing under clinically relevant conditions; (9) users given clear, essential information (intended use, performance, subgroups, limitations); (10) deployed models monitored for performance with re-training risks (overfitting, bias, drift) managed. Items 3, 4, 9, 10 are the ones MedPull can operationalize immediately: device/demographic representativeness statement, sequestered validation episodes, clinician-facing model fact sheet, and the drift-monitoring pipeline.

> FDA/Health Canada/MHRA GMLP Guiding Principles, Oct 2021 (fda.gov page not fetchable this session — content from background knowledge)

### HTI-1 / 45 CFR 170.315(b)(11): 31 predictive-DSI source attributes are the disclosure schema EHR partners will demand
*[strong]*

ONC's HTI-1 rule requires certified Health IT Modules to expose source attributes for Predictive DSIs across nine categories: details/output (developer, funding, output type); purpose (intended use, population, users, decision role); cautioned out-of-scope uses; development details (training-data inclusion/exclusion, input variables, demographic representativeness); fairness process (bias management approach); external validation (data source, setting, who ran it, demographics); quantitative performance (validity AND fairness metrics in test data and external data); ongoing maintenance (validity/fairness monitoring frequency, local performance); update schedule and risk-correction procedures. Evidence-based DSIs need 13 simpler attributes (citation, developer, funding, revision dates, demographic-variable use). Developers must also apply Intervention Risk Management: risk analysis (validity, reliability, robustness, fairness, intelligibility, safety, security, privacy), risk mitigation, and governance of data acquisition/management, with summary info publicly available. The (b)(11) criterion took effect for certified health IT around Jan 1, 2025. MedPull is not certified health IT, but any EHR embedding its scores is — so MedPull must be able to hand over these 31 attributes.

> healthit.gov test-method page for §170.315(b)(11) Decision Support Interventions (fetched); effective-date detail from background knowledge

### Model cards (Mitchell et al.) are the right container for GMLP principle 9 and the HTI-1 attributes
*[strong]*

Mitchell et al. (FAT* 2019, arXiv:1810.03993) define model card sections: model details, intended use, factors (demographic/environmental — explicitly including Fitzpatrick skin type), metrics, evaluation data, training data, quantitative analyses disaggregated by group and intersection, ethical considerations, caveats. For MedPull, one model card per engine version, with per-subgroup (age band, sex, device brand, skin tone where known) false-alert rate and missed-deterioration proxy rates; regenerate on every version bump and store alongside the release tag. The HTI-1 31 attributes map almost 1:1 onto model card sections, so one artifact serves both.

> Mitchell et al., arXiv:1810.03993 (fetched)

### PPG/skin-tone bias: heart rate holds up, motion is the bigger error source, but SpO2 is the real equity risk
*[strong]*

Bent et al. (npj Digital Medicine 2020) tested 6 wearables (Apple Watch, Garmin, Empatica, Biovotion, Xiaomi Miband) against ECG across Fitzpatrick 1–6 with balanced skin-tone groups: no statistically significant HR accuracy difference by skin tone, but absolute error ~30% higher during activity than rest, with device-dependent lag responding to activity change. However, pulse oximetry literature (Sjoding et al., NEJM 2021: occult hypoxemia — SaO2<88% despite SpO2 92–96% — in 11.7% of Black vs 3.6% of white patients) shows the same optical physics biases SpO2 by skin pigmentation; wearable SpO2 is less validated than fingertip clinical oximeters. For MedPull: SpO2-driven reason codes should carry lower weight/confidence for equity reasons until subgroup performance is measured, and the model card must state this; activity-state should gate which intraday HR samples feed resting-HR baselines.

> Bent et al., npj Digital Medicine 2020, PMID 32047863 (fetched); Sjoding et al., NEJM 2021 (background knowledge)

### Per-score immutable audit record: the minimal reproducibility contract
*[moderate]*

For every tier/score ever displayed, log one append-only event: patient_id; effective_date scored; content-hash + pointer to the exact as-of input snapshot (or the ingested_at watermark that reconstructs it); full resolved feature vector (post-imputation values actually used); engine version (git SHA) and parameter-set version (EWMA lambda, CUSUM k/h, composite weights, thresholds — config is versioned data, not code); coverage/confidence gate result; output tier + typed reason codes; LLM narrative id + prompt/version if narrative shown; who viewed it (user id, timestamp, from access logs) and any action (acknowledge, dismiss, escalate, contact patient). Storage pattern: event-sourced append-only table in the primary DB plus daily export to S3 with versioning + Object Lock (compliance mode, e.g. 7-year retention) for WORM immutability. Reproduction = checkout git SHA + config version, rebuild as-of snapshot from bitemporal store at the recorded watermark, re-run, assert hash equality. This satisfies HIPAA audit-control expectations and pre-builds the FDA design-history/PCCP evidence trail.

> Synthesis: event-sourcing pattern + AWS S3 Object Lock documentation + GMLP principle 10 / PCCP modification-protocol requirements — architecture recommendation, not a fetched study


## Implications for backend

- Add bitemporality now: make the observations table INSERT-only with both effective_date and ingested_at plus revision_seq, expose 'current' and 'as_of(watermark)' views in SQLAlchemy, and route all engine reads through them — this is a small schema change today and a prohibitive retrofit later; it is also the prerequisite for honest backtests of the EWMA/CUSUM/tier pipeline.
- Create a score_events append-only table written on every scoring run (shadow and live): as-of watermark, engine git SHA, config version, resolved feature vector, coverage gate, tier, reason codes, narrative id, plus viewer/action rows from the API layer; export daily JSONL to an S3 bucket with versioning + Object Lock compliance mode. Reproduction test in CI: re-run a sampled historical score from its recorded watermark and assert identical output.
- Promote device_model and firmware_version to first-class columns on every observation and implement the deterministic firmware-change guard (suppress flags 3 days, additive baseline re-offset, CUSUM reset, DEVICE_CHANGED reason code); stratify all cohort-level drift reports by device brand and surgeon_id.
- Move all tunable parameters (EWMA lambda/L, CUSUM k/h, composite weights, tier thresholds, recovery-curve r/d50/floor per procedure) out of code into a versioned config document whose version id is stamped on every score; maintain a one-page mini-PCCP listing which parameter changes are permitted, their acceptance criteria on a frozen validation set, and the silent-run requirement before promotion.
- Ship every engine version with a generated model card (Mitchell et al. sections) pre-populated with the 31 HTI-1 predictive-DSI source attributes, including subgroup breakdowns (age, sex, device brand) and an explicit stated limitation on SpO2 accuracy by skin pigmentation; keep clinician-facing reason codes and displayed input values, since showing the basis for recommendations is what keeps the product inside the FDA CDS exemption (21 USC 360j(o)) — time-critical alarm framing would jeopardize that.
- Add the weekly Evidently drift Lambda (KS/chi-squared small-data branch, patient-level rows, frozen quarterly reference, HTML report to S3) and weekly SPC charts on alert burden, tier shares, and override rates using the engine's existing EWMA code — plus mandatory adjudication of every high-tier alert to build the rare-label store.

## Recommended stack

- **Silent/shadow deployment gate for every new engine version (including parameter changes to EWMA/CUSUM/weights)** — Dual-run in production: new version scores every patient nightly alongside the live version; outputs written to the audit store flagged shadow=true, never shown to clinicians. Promotion criteria (pre-registered, PCCP-style): >=90 days elapsed AND >=30 completed patient episodes AND >=5 high-tier events observed AND tier agreement/disagreement reviewed case-by-case by a clinician AND alert burden (alerts per patient-week) within a pre-set budget. Report the evaluation against the DECIDE-AI checklist (17 AI items + 10 generic). via `No new library — existing FastAPI/SQLAlchemy engine + a shadow_version column; DECIDE-AI checklist as protocol template`
  - params: min_days=90, min_episodes=30, min_high_tier_events=5, alert_budget e.g. <=1.5 alerts/patient-week, kappa on tier agreement reported (no hard threshold — review disagreements)
  - needs: ~30 completed episodes and >=5 high-tier events; at 10-50 concurrent patients expect 3-6 months of silent running
  - why: Kwong et al. showed retrospective AUROC 0.90 collapsing to 0.50 prospectively from dataset drift with only ~150 patients; a silent phase is the only way to see this before clinicians act on scores; event-count gating (not calendar gating) is what makes it honest at low event rates.
- **Weekly batch drift detection on vitals features, per device brand** — Evidently Report with DataDriftPreset, stratified by device_model: per-patient window summaries (mean resting HR, RMSSD, skin temp, SpO2, RR, sleep, steps ratio-to-expected, plus missingness rate) for trailing 28 days vs a frozen season-matched reference (same calendar quarter of prior period once available; else trailing 90 days frozen at quarter start). Small-data branch: two-sample KS p<=0.05 numerical, chi-squared categorical; dataset drift if >=50% of columns drift. Output HTML report to S3 + flag to ops. via `evidently>=0.7 (Python, Apache-2.0); scheduled via EventBridge -> existing Lambda`
  - params: stattest auto (KS for n<=1000), stattest_threshold 0.05; drift_share 0.5; reference frozen per quarter; one row per patient (not per patient-day) to preserve independence; min 20 patients per stratum before testing a stratum
  - needs: >=20 patients per compared stratum-window; below that, report distributions descriptively without hypothesis tests
  - why: Evidently's defaults are exactly calibrated to the <=1000-row regime; patient-level aggregation avoids the within-patient autocorrelation that would make KS p-values meaningless; stratifying by device brand converts the 'new brand enters cohort' risk from a confounder into a monitored dimension.
- **Firmware/device-change step-shift protection (per-patient calibration drift)** — Deterministic guard, not statistics: ingest device_model and firmware_version with every observation; on any change for a patient, (a) emit a reason code DEVICE_CHANGED, (b) suppress EWMA/CUSUM out-of-control flags on affected metrics for 3 days, (c) re-estimate the patient's baseline offset as median(new-firmware days 1-7) - median(last 14 pre-change days) and apply as an additive correction, (d) reset CUSUM accumulators. Fleet-level: alarm if >20% of cohort changes firmware within 14 days (vendor push) and freeze cohort-level drift conclusions during that window. via `None (engine code); optionally whylogs>=1.3 for cheap per-batch distribution profiles to spot fleet-wide steps`
  - params: suppress_days=3, baseline_recalc_window=7 new/14 old days, cohort_firmware_alarm=20% in 14 days, CUSUM reset on change
  - needs: None beyond ingesting device metadata — works from the first patient
  - why: A calibration step-change inside one patient is indistinguishable from clinical deterioration to EWMA/CUSUM; no distributional test at n-of-1 daily data can separate them, but the metadata does it exactly. PSI/KS across the fleet needs hundreds of observations MedPull won't have per firmware pair.
- **Point-in-time-correct storage, backtesting, and exact reproduction of historical scores** — Bitemporal append-only observation store (SQLAlchemy, works on SQLite now and Postgres later): INSERT-only rows (patient_id, metric, effective_date, value, source, device_model, firmware_version, ingested_at, revision_seq); 'as-of' view = latest revision with ingested_at <= watermark. Every nightly scoring run records its watermark + engine git SHA + config version in the per-score audit event; audit events export daily as JSONL to S3 with bucket versioning + Object Lock (COMPLIANCE mode). Backtests replay day-by-day against the as-of view and report as-of vs fully-settled performance plus the data-latency curve. Skip Feast until >1 model consumer or ~10^5+ rows/day; copy its TTL-bounded as-of-join semantics. via `SQLAlchemy>=2.0 + boto3 (S3 Object Lock); NOT feast at this scale`
  - params: Object Lock retention 7 years compliance mode; watermark = scoring-run start timestamp; reproduction test = hash equality of re-run feature vector + tier; TTL analog: ignore observations with effective_date older than metric-specific staleness (e.g., 7 days)
  - needs: None — this is schema discipline from day one; retrofitting bitemporality later is the expensive path
  - why: Wearable vendors restate history (late syncs, reprocessing), so backtests on current data contain look-ahead bias by construction; the bitemporal store is the cheapest structure that makes 'what did we know on day X' a query. Object Lock gives WORM immutability satisfying HIPAA audit-control and future FDA design-history expectations without new infrastructure.
- **Label-free performance monitoring of the risk tier (labels are single-digit-percent)** — Monitor operational surrogates with the engine's own SPC machinery instead of CBPE: weekly Shewhart/EWMA control charts on (1) alerts per patient-week, (2) tier distribution shares, (3) clinician acknowledgment and override rates, (4) median time-in-elevated-tier, (5) coverage/confidence-gate failure rate; chart limits from a frozen 12-week reference. Adjudicate 100% of high-tier alerts (true concern / calibration artifact / data artifact) as a lightweight label stream. Adopt NannyML CBPE only if a calibrated probabilistic complication model is later built and chunks reach ~500 observations. via `Existing numpy/scipy EWMA-CUSUM code; nannyml>=0.10 deferred until a probabilistic model exists`
  - params: EWMA lambda=0.2, L=3 on weekly operational metrics; reference window 12 weeks frozen; alert-adjudication SLA 72h; CBPE prerequisites: isotonic-calibrated probabilities, chunk_size>=500
  - needs: ~12 weeks of operations for reference limits; adjudication works from alert #1
  - why: CBPE assumes calibrated probabilities and no concept drift — the rule-based tier emits neither probabilities nor enough volume; alert-burden and override-rate drift are the earliest observable symptoms of both model and population drift (the Epic sepsis case manifested as 18% alert rate), and adjudicated alerts become the rare-label store for future supervised work.
- **Scheduled recomputation, backfills, and reproducible batch scoring on AWS at 10-1000 patients** — EventBridge Scheduler -> nightly Lambda 'score-all' (idempotent, keyed on (patient_id, effective_date, engine_version) — re-running upserts a new revision, never mutates); backfills = Step Functions Map (or a simple SQS fan-out) over patient-date ranges invoking the same Lambda with an explicit as-of watermark parameter; engine version pinned via Lambda container image tag = git SHA; config (thresholds/weights) loaded from a versioned S3/SSM document whose version id is logged per score. All scoring reads go through the as-of view; outputs land in the audit store + S3. via `AWS EventBridge Scheduler, Lambda (container image), Step Functions (Map state, max concurrency ~10), boto3; no Airflow/Prefect needed at this scale`
  - params: Nightly cron after typical sync window (e.g., 11:00 UTC); Lambda timeout 300s, memory 1024MB; idempotency key (patient_id, date, engine_version, watermark); backfill concurrency 10; DLQ on failures
  - needs: None — scales from 10 patients; revisit (Batch/ECS) only past ~10^4 patients per nightly window
  - why: This is the smallest architecture where every score is reproducible (image tag + config version + watermark fully determine output) and backfills are the same code path as production, eliminating train/serve and backfill/live skew; it matches the existing Lambda deployment so it is an extension, not a migration.

## Open questions

- Session constraint disclosure: the shared WebSearch budget was exhausted before this task ran, so all evidence came from direct WebFetch of known sources; items marked 'moderate' that cite background knowledge (FDA PCCP final guidance text, GMLP principle wording, SPIRIT-AI/CONSORT-AI item counts, PSI conventions, Sjoding NEJM 2021, HTI-1 (b)(11) effective date of Jan 1 2025 vs the Dec 31 2027 date the fetched page showed for privacy/security criteria) should be spot-verified against the primary documents before being quoted in any regulatory or partner-facing artifact.
- Regulatory perimeter: does the ordered risk tier with typed reason codes plus displayed inputs actually satisfy all four CDS-exemption criteria of 21 USC 360j(o)(1)(E) as FDA interprets them in the Sept 2022 CDS guidance (which reads 'time-critical' and single-output recommendations restrictively)? A written regulatory rationale memo is needed; if the answer is no, the PCCP/GMLP scaffolding recommended here becomes mandatory rather than prudent.
- What silent-run duration is achievable given actual census? If concurrent patients stay near 10-30, accruing 5 high-tier events may take longer than 6 months — decide whether to lower the event gate or extend the pilot, and pre-register that choice.
- Skin-tone data: MedPull likely will not collect Fitzpatrick type; can subgroup monitoring of SpO2/PPG reliability use race/ethnicity as an imperfect proxy (with the known limitations), or should self-reported skin tone be added to intake?
- When the cohort crosses ~1000 patients and a supervised complication model becomes feasible, revisit: NannyML CBPE (needs calibrated probabilities, chunk>=500), PSI-based device-mix dashboards, and whether Feast (or the Postgres-native equivalent) is justified by multiple model consumers.
- Vendor restatement magnitude is assumed but unmeasured: instrument the ingestion pipeline now to quantify how often and by how much Fitbit/Apple/Garmin restate prior-day values, since that number determines how conservative the as-of scoring watermark must be.