# Alert design, multiple comparisons, and uncertainty quantification for low-prevalence post-operative remote monitoring

## Summary

At MedPull's event rates, alert credibility is a specificity problem: with 80% sensitivity, a PJI-specific alert at 1% prevalence has PPV 7.5% even at 90% specificity and needs 99.2% specificity to reach PPV 50%, so the product must alert on 'deviation from expected recovery' (~10% base rate, PPV ~45-50% achievable) and let the narrative discuss infection as a differential — the Epic Sepsis Model (AUC 0.63, PPV 12%, 67% of cases missed while alerting on 18% of all hospitalizations; Wong 2021) is the canonical failure to design against, and CDS override rates of 49-96% show what happens otherwise. Monte Carlo audit of the current engine shows the 2-consecutive-day EWMA rule is load-bearing (ARL0 ~780 vs ~171 single-hit) and CUSUM k=0.5/h=5 is well-tuned (ARL0 ~895, detects a 1-SD shift in ~10 days); thresholds should henceforth be expressed as a false-alarm budget (<=0.5 false episode-openings per patient-month) with an ARL simulation test in CI. The multiplicity stack for this scale is: one conformal p-value per patient-day (split-conformal on the composite score, calibrated on uneventful patient-days — this also replaces the ad-hoc confidence score), Benjamini-Hochberg at q=0.10 across the panel each morning, and — only after ~100 patients and episode-based alerting — a single SAFFRON/ADDIS online-FDR stream over episode openings (alpha=0.10, lambda=0.5, W0=alpha/2; Python 'online-fdr' 0.0.3, beta). Daily looking is legitimized by e-process/anytime-valid theory (the CUSUM is already a restart-at-zero SPRT), and Wald's two-boundary SPRT (log A=2.77, log B=-1.56 at alpha=.05/beta=.20) supplies a principled episode-close rule for hysteresis. Adaptive Conformal Inference (alpha_{t+1} = alpha_t + gamma(alpha - err_t), gamma=0.005, verified from the paper) yields drift-robust 90% expected-range bands for steps/walking speed. Tier thresholds should be derived from clinician-elicited harm ratios via decision-curve analysis (pt = 1/(R+1) from 'R false alarms tolerated per true catch') rather than the current 1.2/2.0 conventions, and an episode state machine (dedup key, hysteresis, expiring snooze voided by escalation, ack, full action logging) prevents daily re-alerting while building the label store the platform will need — since with single-digit event counts for years, supervised alert models are statistically off the table and the current SPC-plus-rules architecture is the defensible choice.

## Findings

### PPV arithmetic at MedPull's prevalences: specificity, not sensitivity, is the binding constraint
*[strong]*

PPV = sens*prev / (sens*prev + (1-spec)(1-prev)). Worked with our numbers at sensitivity 80%: PJI at 1% prevalence — spec 90% gives PPV 7.5% (1 true hit per ~13 alerts); spec 95% gives 13.9%; spec 99% gives 44.7%. Readmission at 5% — spec 90% gives PPV 29.6%; spec 95% gives 45.7%. 30-day complication at 10% — spec 90% gives PPV 47.1%. Inverting: to reach PPV 20% for PJI at sens 80% you need spec 96.8% (FPR 3.2%); PPV 33% needs 98.4%; PPV 50% needs 99.2%. Conclusion: a per-patient PJI-specific alert can never have decent PPV from wearables alone; the honest product framing is 'deviation from expected recovery' (10%-ish base rate, PPV ~40-50% achievable at spec 90-95%), with infection only as a differential in the narrative.

> Bayes' theorem; computed exactly (verified numerically in this session)

### Epic Sepsis Model external validation (Wong et al. 2021): the canonical cautionary tale
*[strong]*

27,697 patients / 38,455 hospitalizations at Michigan Medicine; sepsis prevalence 7%. Hospitalization-level AUC 0.63 (95% CI 0.62-0.64) vs vendor-claimed 0.76-0.83. At the deployed threshold (score >=6): sensitivity 33%, specificity 83%, PPV 12%, number needed to evaluate 8. It alerted on 18% of ALL hospitalizations while missing 67% of sepsis cases, and identified only 7% of sepsis patients missed by clinicians. Lessons for us: (1) vendor/internal validation does not transfer — validate on your own population; (2) an alert that fires on ~1 in 5 patients with 12% PPV generates fatigue without catching what clinicians miss; (3) report alert volume per census, PPV, and NNE — not AUC — as the deployment metrics.

> Wong A, et al. External Validation of a Widely Implemented Proprietary Sepsis Prediction Model in Hospitalized Patients. JAMA Intern Med. 2021;181(8):1065-1070 (PMC8218233)

### Alert override rates: 49-96% of CDS alerts are overridden; overriding is often justified
*[strong]*

Systematic review of drug-safety alert overriding in CPOE found override rates of 49% to 96%, driven by low specificity, unclear information content, and workflow interruption; the authors conclude fixes must target the alert-generating conditions, not clinician behavior. Related literature (Murphy et al., JAMA Intern Med 2016, from background knowledge) found primary-care physicians process ~77 EHR notifications/day. Design target for MedPull: total alert volume per clinician per day must be counted and capped at design time, and override/dismiss rate must be instrumented from day one as the primary product-health KPI (target: keep 'no action taken' below ~70%, far below the 90%+ typical of interruptive CDS).

> van der Sijs H, et al. Overriding of drug safety alerts in computerized physician order entry. J Am Med Inform Assoc. 2006;13(2):138-147 (PMID 16357358)

### Number needed to alert (NNA) is the right headline metric
*[strong]*

NNA = 1/PPV: how many alerts a clinician must work through per true finding. ESM's NNE of 8 at 18%-of-census alert volume was judged a failure. A tolerable RTM product target: NNA <= 5 for 'review this patient' tier (PPV >= 20%) and NNA <= 2-3 for 'call the patient / escalate' tier (PPV >= 33-50%). At our prevalences (finding #1) this pins the required specificity per tier: escalation-tier composite must run at spec >= 95% against 'clinically actionable deviation' (~10% base rate), which is achievable; any infection-specific claim is not.

> Derived from Wong 2021 NNE framing + Bayes arithmetic

### Monte Carlo audit of the CURRENT engine settings: single-hit EWMA fires ~1 false alarm per patient-month
*[strong]*

Simulated under i.i.d. Gaussian nulls (4,000 reps, this session): EWMA lambda=0.3, L=2.66 single-day flag has in-control ARL0 ~= 171 days per metric; with 6 monitored metrics that is ~1.06 expected false out-of-control signals per patient-month (P(>=1) ~= 0.65) from EWMA alone. The existing '>= 2 consecutive OOC days' rule raises ARL0 to ~780 (~0.23 false signals/patient/metric-set/month) — so the 2-consecutive rule is load-bearing and must never be bypassed. One-sided CUSUM k=0.5, h=5.0 has ARL0 ~= 895 (~0.20/patient-month across 6 metrics) and detects a sustained 1-SD shift in ~10.5 days; the EWMA(2-consec) detects 1 SD in ~13 days and 1.5 SD in ~6 days. Caveat: real vitals are autocorrelated and baselines are estimated from small pre-op windows, both of which INFLATE false alarms versus these idealized numbers (Lucas & Saccucci 1990; Montgomery SPC) — so treat these as lower bounds and validate ARL on retrospective patient data.

> Own simulation (this session), consistent with Lucas & Saccucci, Technometrics 1990 and Montgomery, Introduction to Statistical Process Control (Ch. 9)

### ARL framing: set control limits from a false-alarm budget per patient-month, not from convention
*[strong]*

The SPC discipline is: pick target in-control ARL0 first, derive L and h from it. Budget: <= 0.5 false alerts/patient-month across all metrics implies per-metric ARL0 >= 6*30/0.5 = 360 days if 6 independent metrics (fewer effective tests since RHR/HRV/temp are correlated; effective number ~3-4). Current settings meet this only WITH the 2-consecutive rule. To tune: for EWMA lambda=0.3, moving L from 2.66 to 3.0 with the 2-consec rule pushes ARL0 from ~780 to ~2,700 (for post-launch de-escalation if volume is too high). These knobs should be config values validated by a Monte Carlo ARL test in CI, not magic numbers.

> Montgomery SPC; own simulations

### Cross-sectional multiplicity: Benjamini-Hochberg daily across patients; BY only if you need worst-case dependence
*[strong]*

Each morning you effectively test N_patients hypotheses ('is this patient deviating today'). Controlling per-test alpha gives N*alpha expected false alarms. BH at q=0.10 controls the expected fraction of today's alert list that is false at 10%, is valid under positive regression dependence (PRDS — plausible for correlated physiologic metrics), and costs one line: statsmodels.stats.multitest.multipletests(pvals, alpha=0.10, method='fdr_bh'). Benjamini-Yekutieli ('fdr_by') is valid under arbitrary dependence but pays a log(m) penalty (~factor 3-6 at m=20-1000) and will kill power at our scale — use only if adversarial dependence is demonstrated. Important design point: apply BH to ONE composite p-value per patient per day (max one alert per patient-day), not to 6 metric-level tests, which both reduces m and matches the clinical unit of action.

> Benjamini & Hochberg, JRSS-B 1995; Benjamini & Yekutieli, Ann Statist 2001; statsmodels.stats.multitest docs

### Online FDR over time: LORD++/SAFFRON/ADDIS — powerful but their independence assumptions clash with daily re-testing of the same patient
*[strong]*

These procedures control FDR over an unbounded stream of tests by managing alpha-wealth. Alpha-investing (Foster & Stine 2008): start with wealth W0, spend alpha_t <= W_t/(1+W_t) per test, earn back alpha on each rejection. LORD++ (Javanmard & Montanari 2018; Ramdas 2017): alpha_t = gamma_t*W0 + (alpha-W0)*gamma_{t-tau_1} + alpha*sum over later rejections, with decaying sequence gamma_j proportional to log(max(j,2))/(j*exp(sqrt(log j))), default W0=alpha/10. SAFFRON (Ramdas et al., ICML 2018, arXiv:1802.09098): adaptive analogue of Storey-BH; candidate threshold lambda=0.5, W0=alpha/2, gamma_j proportional to j^{-1.6}; provably controls FDR at every time for independent p-values and is uniformly more powerful than LORD in simulations. ADDIS (Tian & Ramdas 2019) adds discarding of conservative nulls (tau=0.5, lambda=0.25) — best when most days are 'clearly fine', which matches our stream. Python: package 'online-fdr' 0.0.3 on PyPI (July 2025, beta; implements GAI, SAFFRON, ADDIS, LORD family, LOND, alpha-spending, BatchBH/BatchBY with test_one()/test_batch() API); the reference implementation is the R onlineFDR package (Robertson et al.). CRITICAL CAVEAT: guarantees assume independent (or specific local-dependence) p-values across tests; testing the SAME patient's autocorrelated vitals daily violates this badly. Correct use at our scale: run one online-FDR stream at the EPISODE level (each candidate alert episode contributes one p-value, across all patients over time, ~1-10 tests/day at 100-1000 patients), not at the patient-day-metric level. At <100 patients, skip online FDR entirely — the ARL budget plus daily BH is sufficient and simpler.

> Ramdas et al., SAFFRON, arXiv:1802.09098; Foster & Stine 2008; Javanmard & Montanari, Ann Statist 2018; Robertson et al., onlineFDR (dsrobertson.github.io/onlineFDR); PyPI online-fdr 0.0.3

### Anytime-valid inference: e-processes and Ville's inequality legitimize looking at the data every day
*[strong]*

Classical p-values are invalid under continuous monitoring (sampling to a foregone conclusion). An e-process is a nonnegative process with E[E_t] <= 1 under H0 at any stopping time (a test supermartingale); Ville's inequality gives P(sup_t E_t >= 1/alpha) <= alpha, so 'alert when E_t >= 1/alpha' is valid no matter how often you look, with no alpha-spending schedule. Likelihood ratios are the canonical e-process — meaning the engine's CUSUM is already (a maximized) sequential LR test, which is why the ARL framing works. E-values also compose: the product of independent patients' e-values is an e-value, and 'e-BH' (Wang & Ramdas 2022) runs BH directly on e-values with FDR control under ARBITRARY dependence — an elegant future replacement for the daily BH step. Library: 'confseq' (Howard/Ramdas, pip install confseq) for confidence sequences on baseline means (e.g., anytime-valid pre-op baseline intervals instead of fixed SD floors). Adoption cost is real: you must specify an alternative (e.g., 1-SD shift) to define the LR; recommend phase 2, after the ARL budget is in place.

> Ramdas, Grunwald, Vovk, Shafer. Game-Theoretic Statistics and Safe Anytime-Valid Inference. Statistical Science 2023 (arXiv:2210.01948); Howard et al., Ann Statist 2021; github.com/gostevehoward/confseq

### SPRT: the concrete sequential test for 'is this patient's recovery off-track', with exact boundaries
*[strong]*

Wald's SPRT for H0 'on expected curve' vs H1 'shifted by delta': accumulate log-likelihood ratio Lambda_t = sum log[f1(x_i)/f0(x_i)]; alert when Lambda_t >= log A = log((1-beta)/alpha), clear when Lambda_t <= log B = log(beta/(1-alpha)). At alpha=0.05, beta=0.20: log A = log(16) = 2.77, log B = log(0.21) = -1.56. For Gaussian data with a 1-SD shift alternative, the per-day increment is (x_t - mu0)/sigma - 0.5, i.e., structurally identical to the existing CUSUM increment with k=0.5 — the CUSUM is a restart-at-zero SPRT. Practical recommendation: do NOT add a separate SPRT; instead document the CUSUM h in SPRT terms (h=5 corresponds to alpha ~= e^{-h}-ish crossing odds under Wald's approximation) and use the two-boundary form only for the RECOVERY/clear decision (hysteresis): declare an episode resolved when the downward LR crosses log B, which gives a principled 'back in control' rule instead of an ad-hoc one.

> Wald, Sequential Analysis, 1945/1947; standard SPC texts (Hawkins & Olwell, Cumulative Sum Charts, Springer)

### Adaptive Conformal Inference (Gibbs & Candes 2021): exact recipe for calibrated daily 'expected range' bands
*[strong]*

Verified from the full paper PDF: maintain miscoverage target alpha_t updated as alpha_{t+1} = alpha_t + gamma*(alpha - err_t), where err_t = 1 if today's observation fell outside the conformal set C_t(alpha_t) built from trailing conformity-score quantiles. They use gamma = 0.005 ('found to give relatively stable trajectories while still adapting to observed shifts'; theory says gamma should scale as sqrt of the distribution-shift size). Distribution-free guarantee (Prop 4.1): |T^{-1} sum err_t - alpha| <= (max{alpha_1, 1-alpha_1} + gamma)/(T*gamma) — long-run empirical coverage hits 1-alpha for ANY data-generating process. For us: score = |observed - expected_recovery_curve(d)| / scale; ~30-line implementation; gives honest per-patient 'this steps count is outside the 90% band' statements that remain valid as the patient's recovery drifts. At daily resolution, alpha=0.1 and gamma=0.005-0.01 (T=90-day episode gives coverage error bound ~(1+gamma)/(90*gamma) — with gamma=0.01, ~1.1/0.9 ~= worse than ideal; accept that per-episode coverage is approximate and pool calibration across patients per procedure).

> Gibbs & Candes, Adaptive Conformal Inference Under Distribution Shift, NeurIPS 2021 (arXiv:2106.00170; equations verified from PDF pp. 4-8)

### Conformal PID control (Angelopoulos, Candes, Tibshirani 2023): stronger online conformal when trends/seasonality matter
*[moderate]*

Extends ACI: P = quantile tracking (ACI-like integrator on the quantile itself), I = error integration (running sum of coverage errors), D = 'scorecaster' (a forecaster of future conformity scores, e.g., Theta/AR model, handling trend — relevant to recovery trajectories which trend by construction). Long-run coverage guarantee irrespective of distribution; beat the CDC COVID-forecast ensemble's coverage. Code: github.com/aangelopoulos/conformal-time-series (research code, not a maintained package — vendor the ~200 lines rather than depend on it). Recommendation for MedPull: start with plain ACI (simpler, sufficient since the expected-recovery-curve model already removes most trend); revisit conformal PID only if empirical coverage plots show systematic drift with day-since-surgery.

> Angelopoulos, Candes, Tibshirani. Conformal PID Control for Time Series Prediction. NeurIPS 2023 (arXiv:2307.16895)

### Conformal anomaly detection: replace the ad-hoc composite 'confidence' with a conformal p-value
*[moderate]*

Split-conformal anomaly detection (Laxhammar & Falkman 2015 pattern): treat the composite deviation index as a nonconformity score; calibrate on a reference set of 'uneventful recovery' patient-days matched on day-since-surgery (pooled across patients per procedure); the conformal p-value is (1 + #{calibration scores >= today's score})/(n_cal + 1) — a distribution-free, uniformly-distributed-under-null quantity, i.e., exactly the p-value the BH/online-FDR layers need, and a calibrated 'confidence = 1 - p' for the UI. Needs n_cal >= 19 for alpha=0.05 resolution and n_cal >= 99 to report p to 0.01; at 10 patients x 60 uneventful days you already have hundreds. Libraries: crepes 0.7+ (Bostrom; wraps any sklearn-style scorer, actively maintained) or MAPIE 1.4.1 (v1 API, released June 2026, split conformal/CV+/jackknife+/CQR) — though for a plain scalar score the 3-line p-value formula needs no library. Failure mode: exchangeability breaks if the calibration pool mixes procedures or acute-phase days with late-recovery days — stratify by procedure and day-bucket (e.g., days 1-7, 8-21, 22-90).

> Laxhammar & Falkman, Ann Math Artif Intell 2015; Vovk et al., Algorithmic Learning in a Random World; PyPI MAPIE 1.4.1; crepes (github.com/henrikbostrom/crepes)

### Cost-sensitive thresholds via decision curve analysis: elicit the harm ratio, don't guess it
*[strong]*

Vickers & Elkin: Net Benefit = TP/n - (FP/n)*(pt/(1-pt)), where the threshold probability pt encodes the harm:benefit trade — acting at pt=10% asserts a missed case is 9x worse than an unnecessary action. Elicitation protocol that works with surgeons: ask 'how many patients would you accept calling/seeing to catch one real deteriorating patient?' — an answer of R:1 implies pt = 1/(R+1) (e.g., '10 calls per catch' -> pt ~= 9%; '3 in-person evals per catch' -> pt ~= 25%). Equivalent Bayes-decision form: optimal alert threshold on predicted probability p* = C_FP/(C_FP + C_FN). Use different pt per response tier (message-based check-in pt~5%, phone call pt~10%, clinic visit pt~25%) — this directly yields the composite-index thresholds per tier and replaces the current arbitrary 1.2/2.0 cutoffs once ~50+ adjudicated alert episodes exist to estimate the score-to-probability calibration curve.

> Vickers & Elkin, Decision curve analysis. Med Decis Making 2006;26(6):565-574 (PMC2577036)

### Escalation, hysteresis, and deduplication: episode state machines prevent the daily re-alert problem
*[moderate]*

Borrow from SRE alerting practice (Google SRE Workbook ch.5 'alerting on SLOs', multiwindow multi-burn-rate alerts) and clinical alarm-management guidance (Joint Commission NPSG.06.01.01 on alarm fatigue): (1) alert on EPISODES, not days — dedup key (patient_id, metric_family, direction); an open episode absorbs subsequent daily signals as severity updates, never new notifications; (2) hysteresis — open at a high threshold (e.g., CUSUM > h=5 or tier HIGH), close only at a distinctly lower one (CUSUM back to 0, or SPRT lower boundary crossed, or 3 consecutive in-control days) so borderline patients don't flap; (3) re-notify only on tier ESCALATION (elevated -> high) or on new independent metric family joining the episode; (4) snooze = clinician-set suppression with mandatory expiry (24h/72h/7d) that auto-void if severity escalates a tier — snooze must never mute an escalation; (5) acknowledgement moves episode to 'owned' state and stops reminders; unacknowledged high-tier episodes re-remind once at +24h then escalate to a fallback contact; (6) log (episode, action_taken, outcome) — this is simultaneously the fatigue KPI and the future label store. Evidence strength for exact parameters is practice-based, not RCT-based; the framework (interruption budget, tiered response) is standard.

> Google SRE Workbook ch. 5 (sre.google/workbook/alerting-on-slos); The Joint Commission, National Patient Safety Goal on clinical alarm safety; van der Sijs 2006 design recommendations

### Small-data reality check: with 10-1000 patients and 1-10% event rates, supervised alerting models are off the table
*[strong]*

Expected labelled events: at 100 patients — ~1 PJI, ~5 readmissions, ~10 complications; at 1000 — ~10/~50/~100. Rules of thumb for prediction-model development need >=10-20 events per candidate parameter (Riley et al. 2020, pmid 30357870, minimum sample size for prediction models) and external validation needs >=100 events (Collins et al.) — MedPull will not clear these bars for 2+ years. Therefore the current architecture (deterministic SPC + reference-curve ratios + rule tiers + conformal calibration on UNLABELLED 'normal recovery' data) is the correct choice, not a stopgap: every method recommended here (ARL budgets, BH, conformal p-values, decision-curve thresholds) works with zero or tiny outcome-label counts, using labels only for periodic PPV/NNA audits (which need only ~20-50 adjudicated alerts). The Epic lesson applies in reverse: do not license or bolt on a pretrained 'complication model' without local validation you cannot yet perform.

> Riley et al., BMJ 2020 (minimum sample size for clinical prediction models); Wong 2021; arithmetic


## Implications for backend

- Kill the single-hit EWMA pathway if any code path still allows it: L=2.66 with a 1-day flag is ARL0 ~171 (~1 false alarm per patient-month over 6 metrics); the >=2-consecutive-days rule (ARL0 ~780) must be structurally unbypassable. Add a Monte Carlo ARL0 test to CI (simulate 4k Gaussian null runs, assert ARL0 within [600, 1000] for EWMA-2consec and [700, 1100] for CUSUM k=0.5 h=5) so any threshold edit shows its false-alarm cost in the PR.
- Restructure alerting around an episode state machine (new tables: alert_episode with dedup key (patient_id, metric_family, direction), states OPEN/ACKED/SNOOZED/RESOLVED, and alert_event log of every notification + clinician response). Daily engine output feeds episodes; notifications fire only on episode open or tier escalation; close requires CUSUM back to 0 or 3 consecutive in-control days (hysteresis); snooze has mandatory expiry and is voided by tier escalation.
- Insert a multiplicity layer between the engine and notifications: compute one conformal p-value per patient-day from the composite deviation score (calibration pool = uneventful patient-days, stratified by procedure and day-bucket 1-7/8-21/22-90), then run Benjamini-Hochberg at q=0.10 across today's patients (statsmodels multipletests 'fdr_bh') to produce the day's ranked alert list. Max one alert per patient per day; metric-level signals become reason codes inside it, never separate notifications.
- Replace the ad-hoc coverage-based 'confidence' with two separate fields: data_sufficiency (the existing >=3-of-6 / 40%-of-7-days gate, unchanged) and statistical_confidence = 1 - conformal p-value; optionally add ACI bands (alpha=0.1, gamma=0.005, alpha_{t+1} = alpha_t + gamma*(alpha - err_t)) on steps and walking-speed ratio-to-expected for the patient-facing 'expected range' UI. LLM continues to narrate only.
- Derive the composite tier thresholds (currently 1.2/2.0) from elicited costs instead of convention: run the Vickers-Elkin elicitation with 2-3 surgeons ('how many phone calls per true catch is acceptable?'), map R:1 answers to pt = 1/(R+1) per response tier, and once ~50 adjudicated episodes exist, fit the score-to-probability calibration and set tier cutoffs to the pt values. Until then, publish the implied NNA of current thresholds on retrospective data.
- Instrument for the future NOW: log every episode with clinician action and 90-day outcome adjudication. This yields (a) the alert-fatigue KPI (override rate, alerts/clinician/day — cap total interruptive volume and treat >70% no-action rate as a sev-2 product bug per the CDS literature), (b) the ~20-50 adjudicated alerts needed for PPV/NNA audits, and (c) the label store that will eventually (>=100 events, years away) permit supervised models. Do not adopt any pretrained complication model without local validation — the Epic Sepsis Model (AUC 0.63, PPV 12%, 67% of cases missed, 18% of census alerted) is the standing warning.
- Defer online-FDR (SAFFRON/ADDIS via the beta 'online-fdr' PyPI package) until patient count exceeds ~100 AND alerting is episode-based; then run one SAFFRON stream (alpha=0.10, lambda=0.5, W0=alpha/2) over episode-opening p-values across the whole panel. Applying it per patient-day today would violate its independence assumptions and add a beta dependency for no benefit — the ARL budget + daily BH already bound the false-alarm rate at our scale.

## Recommended stack

- **Per-metric change detection with a controlled false-alarm rate (keep, but re-frame)** — EWMA control chart + one-sided CUSUM, limits chosen by target in-control ARL, verified by Monte Carlo in CI via `numpy/scipy (existing in-house engine); no new dependency`
  - params: EWMA lambda=0.3, L=2.66 WITH mandatory >=2-consecutive-day rule (measured ARL0 ~780 days; detects 1-SD sustained shift in ~13 days, 1.5-SD in ~6). CUSUM k=0.5, h=5.0, one-sided (ARL0 ~895; 1-SD shift in ~10.5 days). Escape hatch if alert volume too high: L=3.0 + 2-consec gives ARL0 ~2700. Budget: <=0.5 false episode-openings/patient-month across all metrics.
  - needs: 7-14 pre-op baseline days per patient (existing); retrospective pilot data (any size) to check autocorrelation-driven ARL inflation
  - why: Already implemented and methodologically sound; the only gap is that thresholds were conventions, not derived from a false-alarm budget — the ARL framing plus a CI simulation test closes that gap with zero new code risk.
- **Calibrated per-patient-day p-value / confidence score from the composite deviation index** — Split-conformal anomaly detection: conformal p = (1 + #{calibration scores >= today})/(n_cal + 1), calibration pool = uneventful patient-days stratified by procedure and day-since-surgery bucket via `3-line in-house implementation; crepes >=0.7 or MAPIE >=1.4 (v1 API) if wrapping richer models later`
  - params: Strata: days 1-7, 8-21, 22-90 per procedure; n_cal >= 99 per stratum before reporting p<0.01 (>=19 for p<0.05); refresh calibration pool monthly; exclude any day belonging to a later-adjudicated adverse episode
  - needs: ~100+ uneventful patient-days per stratum; achievable with 10-20 pilot patients within 2 months
  - why: Distribution-free, exchangeability-only guarantee; converts the ad-hoc composite score into exactly the uniformly-distributed-under-null p-value the FDR layer needs, and a defensible 'confidence' for the UI — with no outcome labels required
- **Daily cross-patient multiplicity control (the morning alert list)** — Benjamini-Hochberg FDR on one conformal p-value per patient per day; switch to e-BH (BH on e-values, valid under arbitrary dependence) in phase 2 via `statsmodels >=0.14, statsmodels.stats.multitest.multipletests`
  - params: method='fdr_bh', alpha=0.10 (i.e., <=10% of today's alert list expected false); use method='fdr_by' only if dependence diagnostics look adversarial (costs ~3-6x power at m=20-1000). Max one alert per patient-day; rank list by p ascending.
  - needs: None beyond the p-values; valid at any panel size
  - why: One line of mature, battle-tested code; PRDS assumption plausible for physiologic metrics; directly bounds the fraction of the clinician's list that is wasted effort — the quantity alert fatigue actually depends on
- **Panel-level false-discovery control over time, once episode-based alerting exists and N>100 patients** — SAFFRON online FDR on episode-opening p-values (ADDIS variant if most p-values are conservative) via `online-fdr==0.0.3 (PyPI, beta — pin and property-test against R onlineFDR reference) or vendored ~100-line implementation`
  - params: SAFFRON: alpha=0.10, lambda=0.5, W0=alpha/2, gamma_j proportional to j^{-1.6} (normalized). ADDIS: alpha=0.10, tau=0.5, lambda=0.25. One stream for the whole panel; one p-value per candidate episode, never per patient-day.
  - needs: >=100 patients / >=1 episode-test per day on average; below that, ARL budget + daily BH suffice
  - why: Purpose-built for an unending stream of hypothesis tests with FDR control at every stopping time; earns back alpha-wealth on discoveries so power grows with a busy panel — but its independence assumptions mean it must sit at the episode level, and below ~100 patients it adds complexity without measurable benefit
- **Anytime-valid daily monitoring semantics and principled episode-close (hysteresis)** — Treat CUSUM as the e-process it is (restart-at-zero SPRT); add Wald two-boundary logic for episode resolution; confidence sequences for pre-op baselines via `confseq (pip install confseq) for baseline confidence sequences; SPRT boundaries in-house (2 lines)`
  - params: SPRT alpha=0.05, beta=0.20: open/upper boundary log A = log(16) = 2.77 on the cumulative LLR (Gaussian 1-SD-shift alternative: daily increment (x-mu0)/sigma - 0.5); RESOLVE episode when downward LLR crosses log B = log(0.21) = -1.56, or CUSUM returns to 0, or 3 consecutive in-control days — whichever policy tests best on pilot replays
  - needs: Same baselines as EWMA/CUSUM; requires committing to an alternative effect size (1 SD sustained shift is the standard default)
  - why: Ville's inequality makes daily looks legitimate without alpha-spending; the two-boundary SPRT gives a non-arbitrary 'patient is back on track' rule, which is the missing half of hysteresis and prevents flapping re-alerts
- **Patient-facing calibrated 'expected range' bands on steps and walking speed under recovery drift** — Adaptive Conformal Inference on ratio-to-expected residuals; upgrade to Conformal PID only if coverage drifts with day-since-surgery via `~30-line in-house ACI (update rule from the paper); vendored code from github.com/aangelopoulos/conformal-time-series if PID needed`
  - params: alpha=0.10 (90% bands), gamma=0.005 (paper's recommended stable value; raise toward 0.01 if empirical coverage plots lag shifts), alpha_1=alpha, conformity score = |observed - f(d)*baseline| / rolling MAD; guarantee |avg miscoverage - alpha| <= (1+gamma)/(T*gamma)
  - needs: ~20-30 days of a patient's own post-op stream to stabilize (warm-start from procedure-level pooled scores before that)
  - why: Verified update rule alpha_{t+1} = alpha_t + gamma*(alpha - err_t) gives correct long-run coverage for ANY data-generating process — the honest way to say 'outside expected range' while the patient's own distribution shifts throughout recovery
- **Setting and defending tier thresholds from clinical costs** — Decision curve analysis / net benefit with elicited threshold probabilities per response tier via `Custom ~20 lines (net_benefit = TP/n - FP/n * pt/(1-pt)); sklearn.metrics for the confusion counts`
  - params: Elicit R ('acceptable false alarms per true catch') per tier from >=2 surgeons; pt = 1/(R+1). Expected starting points: message check-in pt ~0.05 (R~19), phone call pt ~0.10 (R~9), clinic visit pt ~0.25 (R~3). Recompute tier cutoffs once >=50 adjudicated episodes exist; report NNA per tier quarterly.
  - needs: 2-3 clinician elicitation sessions now; ~50 adjudicated alert episodes for the first calibration (feasible in pilot year 1)
  - why: Replaces the arbitrary 1.2/2.0 composite cutoffs with thresholds that encode what clinicians actually said about harm trade-offs, and produces the PPV/NNA audit numbers that keep the product trusted

## Open questions

- What are the actual elicited cost ratios from MedPull's pilot surgeons (false-alarm calls tolerated per true catch, per response tier)? The whole threshold stack keys off these 2-3 numbers and they cannot be found in literature.
- What is the effective number of independent tests among the 6 metrics (RHR/HRV/temp are strongly correlated)? An empirical correlation matrix from pilot data would justify a smaller multiplicity correction (effective m ~3-4 instead of 6) and sharpen the ARL budget.
- How autocorrelated are the daily wearable aggregates in-cohort? AR(1) in residuals inflates EWMA/CUSUM false alarms beyond the simulated ARL0; if phi > ~0.3, thresholds need re-tuning on residuals from a per-patient AR model (or wider limits validated by block-bootstrap ARL simulation on real pilot data).
- Is the 'online-fdr' PyPI package (0.0.3, beta, July 2025) production-trustworthy, or should the needed SAFFRON/ADDIS routines (~100 lines) be vendored and property-tested against the R onlineFDR reference outputs?
- How many uneventful patient-days per (procedure, day-bucket) stratum will the pilot actually produce, and is pooling across procedures acceptable for conformal calibration in the first months (exchangeability risk vs n_cal >= 99)?
- When intraday data streams arrive, does the multiplicity design hold if the engine moves from 1 test/patient/day to many — i.e., should intraday be aggregated to daily features (recommended) rather than tested per-window?
- What snooze durations and re-reminder cadence do clinicians actually tolerate in RTM billing workflows (CPT 98975-98981 monthly-review rhythm may argue for a weekly digest tier below the interruptive tier)?