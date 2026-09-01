# 4. The Statistical Engine

This section specifies the engine end to end: baselines → transforms → detectors → composite → trajectory → episodes → serving. It is written in dependency order because that is also the correct build order — every layer below consumes the layer above, and shipping a downstream layer on top of a broken baseline layer is how the current engine acquired the defects catalogued in §4.0.

Two global adjudications govern everything that follows, and both contradict parts of the research corpus:

1. **The corpus assumes per-patient compute is free in the request path. It is not.** `GET /worklist` (`api/worklist.py:34-56`) loops every patient calling `ensure_fresh_assessment()`, and `compute_input_hash()` (`engine/pipeline.py:44`) folds `date.today()` into the hash, so the first console load each morning recomputes the entire panel — including LLM narrative regeneration — inside one 30 s Lambda behind a 30 s CloudFront origin timeout. No statistical work in this section may land before that is split. See §4.7.
2. **The corpus repeatedly proposes `statsmodels`, `scikit-learn`, `pymc`, `ruptures`, and `stumpy` "in Lambda".** `infra/build-lambda.sh` line 37 deliberately excludes scipy from the artifact and lines 43-46 hard-fail the build if `app/` imports it. Every method below is therefore specified twice: a **fit** form (offline, any library) and a **serve** form (numpy + pandas arithmetic on frozen JSON coefficients). If a method has no serve form, it is not in this design.

---

## 4.0 Preconditions — bugs that must be fixed before any new statistics

These are not research items. They are defects that make every downstream number meaningless, and they are ordered by severity.

| # | Defect | File | Fix |
|---|---|---|---|
| P1 | Baseline anchors on post-op days 2–4 when no pre-op data exists — the acute surgical perturbation, RHR elevated 10–15 bpm. A patient whose RHR stays legitimately elevated scores z≈0 ("on track"); a patient who normalizes scores **negative**. The engine reads deterioration as improvement. | `engine/baseline.py:37-40` | **Delete the fallback.** Return `insufficient_baseline` and fall through to the population prior (§4.1). |
| P2 | `len(pre) >= 3` with `std(ddof=1)`. At n=3 the sampling SD of s/σ is ≈0.52 and P(s < 0.5σ) ≈ 0.16 — one patient in six gets a baseline SD under half the truth, doubling every downstream z. | `engine/baseline.py:30` | `MIN_PREOP_DAYS = 7`; refuse to emit a numeric deviation below it. |
| P3 | EWMA/CUSUM recursions iterate a Series indexed by post-op day with missing days simply **absent**. A patient wearing Mon/Thu gets effective λ ≈ 1−(1−0.3)^(1/3) ≈ 0.11 per observation but 0.3 per *observed* step, i.e. the filter runs ~3× too fast in wall-clock time. `z.iloc[-CUSUM_WINDOW:]` is the last 14 **observations**, not 14 days. | `engine/deviation.py:84-86, 106` | Reindex to a complete daily grid; carry state forward without update on gaps; make the CUSUM window day-indexed. |
| P4 | Apple patients lose 45% of the composite. `ANALYZED_METRICS` lists `HRV_RMSSD`/`SKIN_TEMP`; Apple ships `HRV_SDNN`/`SKIN_TEMP_DELTA` (`connectors/capabilities.py:28-29`). Apple weight sums to 0.55 against thresholds calibrated for 1.00 — an Apple patient needs ~1.8× the derangement to trip the same tier. Masked by `seed/generators.py:170-173` emitting canonical series for Apple patients. | `engine/pipeline.py`, `composite.py` | §4.3 weight renormalization + minimum-metrics gate. |
| P5 | **Circular validation.** `seed/generators.py:20` imports `curve_mid`/`recovery_progress` from `engine/curves.py`; line 125 generates step levels *from the engine's own expected curve*. Every golden-tier test, every ARL estimate, every threshold measures the RNG. | `seed/generators.py` | CI test that hard-fails on any import edge `app.seed → app.engine`. Regenerate with a **different** functional form (Mitscherlich, §4.4), per-patient AR(1) noise φ~U(0.3,0.7), and MNAR non-wear gaps. |
| P6 | `dataload.py` filters only `value_num IS NOT NULL` — not `deleted_at IS NULL` (which `rtm/coverage.py` correctly honours) and not `revision`. Deleted HealthKit data drives risk scores forever. Also computes post-op day from `start_time.date()`, not `local_date`, so RTM billing and analytics disagree on which day an observation belongs to. | `engine/dataload.py:31` | One-line filter + switch to `local_date`. |

**None of the sections below are shippable until P1–P3 and P5 are done.** P1 is a patient-safety defect, not a statistics defect.

---

## 4.1 Baselines — parametric empirical Bayes replaces the SD floors, the confidence gate, and the no-pre-op case

### 4.1.1 The formula

Røys et al., *Clinical Chemistry* 2025 (PMC12582661) give the exact closed form. Two-level normal model: `X_n | μ_I ~ N(μ_I, σ_I²)`, `μ_I ~ N(μ_pop, σ_G²)`.

**Shrunk personal set point:**

```
Ŷ = μ_pop + (X̄_n − μ_pop) · B_n
B_n = B1·n / (B1·n + 1 − B1)          where  B1 = σ_G² / (σ_G² + σ_I²)  (the ICC)
```

**Alert threshold for the next observation:**

```
flag when |x_{n+1} − Ŷ| > Z · sqrt(1 − B1·B_n) · σ_pop,     σ_pop = sqrt(σ_G² + σ_I²)
```

This is not an approximation of the current design — it *is* the current design's three separate hacks collapsed into one continuous quantity:

- **n = 0** → `B_n = 0`, `Ŷ = μ_pop`, threshold = `Z·σ_pop`. That is exactly "no pre-op data → judge against the population," which is what P1 should have been doing instead of anchoring on the surgical perturbation. No branch needed.
- **n → ∞** → `B_n → 1`, threshold → `Z·σ_I`. Pure personal baseline.
- **n = 1** → a *narrower and more correct* reference change value than the classical RCV, because it corrects for regression to the mean.
- **The SD floor disappears.** A short baseline no longer needs an artificial variance floor to stop it exploding; `sqrt(1 − B1·B_n)` automatically widens the interval when n is small.
- **The coverage gate collapses into it.** `confidence.py`'s "≥3 of 6 metrics" + "<40% of last 7 days" and `baseline.py`'s SD floor are three ad-hoc encodings of one number: how much this patient is being judged against themselves. Surface `B_n` as `baseline_confidence` (0–1) in the API. When `B_n < 0.4` the clinical statement is *"this patient is being judged mostly against people like them, not against themselves"* — a materially different claim, and the LLM must be given that distinction explicitly so it does not overstate personalization.

Published validation: flagging rates against a 5% nominal target moved from 4.7%→0.3% (albumin), 5.4%→3.7% (phosphate), 7.1%→3.9% (cortisone), and 12.4%→5.3% for serial 17-OHP pairs versus classical log-normal RCV, on 30 healthy adults with ~10 weekly samples each, parameters from 1,986–185,488 samples/analyte.

### 4.1.2 Where B1 comes from

`B1 = 1/(1 + II²)` where `II = CV_I/CV_G` is the clinical-chemistry index of individuality. Ship these as **borrowed, labelled priors**:

| Metric | Seed B1 | Implied II | Source |
|---|---|---|---|
| Resting HR | 0.64 | 0.75 | Takano, JMIR Form Res 2026 (PMC12954691): ~64% of HR variance interindividual. N=7 — a placeholder, not an estimate. |
| ln(HRV RMSSD) | 0.50 | 1.00 | Assumed until measured |
| Skin temp | 0.55 | 0.90 | **No published within-person CV located.** See §4.1.7. |
| Respiratory rate | 0.45 | 1.11 | Assumed |
| Sleep duration | 0.70 | 0.65 | Assumed |
| ln1p(steps) | 0.60 | 0.82 | Consistent with Murphy 2026 ICC≥0.80 at 2–6 days |

Every row carries `prior_source='literature_placeholder_v0'` in the prior table and is rendered in the UI as borrowed. Replace with a cohort estimate at **≥30 patients × ≥7 valid pre-op days per metric** (≈210 patient-days) via a nightly `statsmodels` MixedLM:

```python
# OFFLINE ONLY — batch job, never Lambda
res = smf.mixedlm("value_t ~ 1 + C(procedure) + age_c + C(sex) + bmi_c",
                  data=df, groups=df.patient_id, re_formula="1").fit(reml=True)
sigma_g2 = float(res.cov_re.iloc[0, 0])
sigma_i2 = float(res.scale)
B1 = 0.0 if sigma_g2 < 1e-8 else sigma_g2 / (sigma_g2 + sigma_i2)   # boundary guard
```

Do **not** report uncertainty on the variance components below 50 patients (Maas & Hox: level-2 variance SEs underestimated ~15% below 50 groups). Below 20 patients the RE variance collapses to zero routinely — do not fit at all.

### 4.1.3 The within-person variance: moderated, not floored

The SD floor is the right instinct with the wrong functional form — it is discontinuous, applies equally at n=3 and n=30, and cannot correct an *over*-estimated variance. Replace with the limma moderated estimator (Smyth 2004):

```
σ̂²_i = (ν₀·σ̄²_pop + (n_i − 1)·s_i²) / (ν₀ + n_i − 1),     ν₀ = 8 pseudo-observations
```

- `s_i` = **robust** scale: `median_abs_deviation(x, scale='normal')` (constant 1.4826) at n<5; Huber Proposal 2 with c=1.345 (≈95% Gaussian efficiency) at n≥5. MAD's 37% efficiency is too lossy on a 7-day window to be the primary estimator.
- Baseline **centre is the median**, not the mean. Three points plus one bad night currently move the mean by a third of the effect being chased.
- Hard floors survive **only at device resolution**, so they fire on sensor pathology (a constant-value stream giving s=0) and never as a variability guard: 0.5 bpm RHR, 0.03 ln-RMSSD units, 0.05 °C skin temp, 0.3% SpO2, 0.4 br/min RR, 12 min sleep. Note that today's floors (`baseline.py:13-26`: 1.5 bpm RHR, 0.12 °C skin temp) sit *below* plausible free-living within-person SD (~2.5–4 bpm; ~0.3–0.5 °C) — a floor that never binds is not a guard.

`ν₀=8` may itself be estimated from the cohort by matching the observed dispersion of the `s_i²` to a scaled-χ², once ≥30 patients exist.

### 4.1.4 Transforms — ship them *with* a threshold recalibration, never alone

The PEB model "assumes log-normality (or Box-Cox transformability)". A right-skewed metric z-scored raw produces far more than the nominal rate of high-side exceedances — so a nominally 2.66-σ EWMA on raw RMSSD is **not** running at the false-alarm rate we believe.

- `ln(RMSSD)` — near-universal convention. **Caveat the research is explicit about: no paper was located stating RMSSD is log-normal.** Verify with `scipy.stats.boxcox_normmax(x, method='mle')` on our own pooled pre-op RMSSD and only accept λ=0 if the MLE lands in [−0.2, 0.2].
- `ln(1+steps)`.
- Yeo-Johnson for `SKIN_TEMP_DELTA` (signed, can be negative).
- RHR, RR, SpO2, sleep: estimate λ from ≥500 pooled baseline observations (≈70 patients × 7 days), **round to nearest 0.5**, freeze in the versioned prior table. Below 500 observations, leave untransformed — a wrong λ is worse than λ=1.

A change in λ is a **breaking change to every stored z-score and threshold**. The transform migration and the recalibration of EWMA L, CUSUM h, and the composite cutoffs must ship in one commit with golden-tier tests regenerated in the same commit.

### 4.1.5 Days-of-baseline requirements, per metric

Computed via Spearman–Brown `n_days = R·II²/(1−R)`, and cross-checked against measured ICCs:

| Metric | Minimum valid days | Comfortable | Evidence |
|---|---|---|---|
| Steps | **4** | 7 (11+ to represent a month) | Murphy, JMIR mHealth 2026 (PMID 41666367): 2–6 days for ICC≥0.80 in a 7-day window, 6–11 for a 28-day-representative estimate. Espin & Júdice, Scand J Med Sci Sports 2026 (N=106): 4 days for step count at ICC≥0.85. |
| Sleep duration | **3** | 7 | Soon & Chee, *Sleep* 2026;49(6):zsag083 — reliably captured in 3–7 nights. |
| **Sleep variability / regularity** | **DO NOT SHIP** | — | Same paper, from 3.7M person-nights: 7-day variability estimates correlate only **0.50–0.58** with reference; 2 weeks gives 0.61–0.67, still below the 0.80 threshold; **41–65 nights** required. A 7-night TST estimate can be off by 50 min; sleep-onset-variability LoA span >2 h. Any regularity feature on a 1–4 week pre-op window is noise that manufactures alerts. |
| Resting HR | **6** (R=0.90) | 11 (R=0.95) | ρ≈0.64 from Takano 2026, N=7 — placeholder. |
| HRV, skin temp, SpO2, RR | 7 (by the global `MIN_PREOP_DAYS`) | — | No reliable published figure; the COPD study (JMIR mHealth 2024, N=146, median 56.5 nights) found HRV means keep improving out to 30 days. |

Global rule: `MIN_PREOP_DAYS = 7` for a *personal* baseline; below that, `B_n` handles it gracefully but `baseline_provenance` must say so. Field-realistic completion is worse than planned — Aesthet Surg J Open Forum 2025 required ≥5 pre-op days and got complete data on 21 of 51 enrolled (**41%**). Design for a dual path, not for compliance.

The classical instantiation for setting D per metric: `n = (1.96·CV_I/D)²`. For RHR with D = 3 bpm on 60 bpm (5%) and CV_I ≈ 6%: `n = (1.96·6/5)² ≈ 5.5 → 6 days`.

### 4.1.6 The pre-op activity-decline bias — this one changes alert *direction*

Sensors 2026 (PMC13259192), N=238 (147 TKA, 91 THA), piecewise linear mixed-effects over a four-year perioperative period, explicitly contrasts activity measured immediately before surgery against a remote habitual baseline. **Patients decline for months before arthroplasty.** Dividing post-op steps by a baseline captured in the last 1–2 weeks pre-op inflates the recovery ratio and **systematically under-alerts on poor recovery.**

Fix, in priority order:
1. If ≥90 days of pre-op history exist, use the **90th percentile of daily steps over the 3–6 months pre-op** as the functional baseline denominator.
2. Otherwise multiply the short-window baseline by a procedure-specific decline correction factor estimated from the cohort (initialize at 1.0 and log it, so the correction is visible and falsifiable).
3. Record which was used in a new `baseline_provenance` field: `PRE_OP_REMOTE_P90`, `PRE_OP_N_DAYS=7`, `POPULATION_ONLY`. Never `POST_OP_ANCHORED` — that path is deleted (P1).

### 4.1.7 Two guards the PEB paper's own failures demand

**Heteroscedasticity guard.** The paper attributes its worst results — cortisol flagging 16.4% and 17-OHP 11.5% against a 5% target — to CVI heteroscedasticity violating the model. Independently, Hyun et al., BMC Med Res Methodol 2026, report GLMM type-I error up to **47.2%** when within-cluster correlation varies across subgroups. A single global σ_I per metric is wrong for patients on beta-blockers, in AF, with poor sensor contact, or on shift work. Concretely: compute each patient's `s_i` against the cohort `σ_i`; if `s_i > 2·σ_i`, widen that patient's thresholds proportionally and drop their confidence tier rather than letting them emit a stream of alerts.

**Autocorrelation guard.** The PEB source requires ≥24 h between samples to avoid autocorrelation. Daily wearable aggregates are autocorrelated, so calendar n overstates effective n and `B_n` is optimistic. Apply `n_eff = n·(1−ρ)/(1+ρ)` using lag-1 autocorrelation of the baseline residuals, and use `n_eff` in `B_n`. Whether this is well-calibrated for wearable series is an open question worth a simulation; log both n and n_eff.

**Skin temperature demotion.** No reliable published within-person CV for wrist skin temperature was located, it is the metric most confounded by ambient temperature, bedding and wear position, and at today's 0.12 °C floor a 0.4 °C ambient excursion produces z=+3.3 and contributes 0.83 to the composite — **70% of the elevated threshold from one confounded metric**, and it will do so across the whole panel simultaneously in a cold snap. Until an ambient correction exists: score skin temp against the patient's own trailing 7-day median with a 0.25 °C floor, and reduce its composite weight (§4.3).

### 4.1.8 The code

`engine/baseline.py`, rewritten. numpy only, request-path safe, microseconds.

```python
# engine/baseline.py — parametric empirical Bayes personal baselines (Røys 2025)
import numpy as np

PRIOR_VERSION = "peb_v1"
MIN_PREOP_DAYS = 7
Z_PRIMARY, Z_WATCH = 3.0, 2.0
NU0 = 8.0                       # moderated-variance prior strength, pseudo-obs
DEVICE_FLOOR = {                # sensor pathology only, NOT a variability guard
    "resting_hr": 0.5, "hrv_rmssd_ln": 0.03, "skin_temp": 0.05,
    "spo2": 0.3, "respiratory_rate": 0.4, "sleep_duration": 0.2,
}

def _huber_scale(x, c=1.345, tol=1e-6, max_iter=30):
    """Huber Proposal 2 joint location/scale. ~95% Gaussian efficiency."""
    mu = float(np.median(x))
    s = float(np.median(np.abs(x - mu))) * 1.4826
    if s <= 0:
        return mu, 0.0
    for _ in range(max_iter):
        r = np.clip((x - mu) / s, -c, c)
        mu_new = mu + s * r.mean()
        # E[psi_c(Z)^2] under N(0,1) for the consistency correction
        beta = 2 * ((1 + c**2) * _std_norm_cdf(c) - c * _std_norm_pdf(c) - 0.5) - c**2
        s_new = s * np.sqrt((r**2).mean() / beta)
        if abs(mu_new - mu) < tol * s and abs(s_new - s) < tol * s:
            mu, s = mu_new, s_new
            break
        mu, s = mu_new, s_new
    return float(mu), float(s)

def shrunk_baseline(x_valid, prior):
    """
    x_valid : np.ndarray of TRANSFORMED valid pre-op daily values (>=18h wear)
    prior   : dict with mu_pop, sigma_g2, sigma_i2, B1, metric, rho (lag-1 ac)
    returns : dict — the single object every downstream consumer reads
    """
    n = int(x_valid.size)
    B1 = float(prior["B1"])
    sigma_pop = float(np.sqrt(prior["sigma_g2"] + prior["sigma_i2"]))

    if n == 0:
        return dict(y_hat=prior["mu_pop"], sd_alert=Z_PRIMARY * sigma_pop / Z_PRIMARY,
                    sigma_alert=sigma_pop, B_n=0.0, n=0, n_eff=0.0,
                    provenance="POPULATION_ONLY", prior_version=PRIOR_VERSION,
                    heteroscedastic=False)

    # effective n: daily aggregates are autocorrelated; calendar n is optimistic
    rho = float(np.clip(prior.get("rho", 0.0), 0.0, 0.95))
    n_eff = max(1.0, n * (1.0 - rho) / (1.0 + rho))

    B_n = (B1 * n_eff) / (B1 * n_eff + 1.0 - B1)
    centre, s_i = (float(np.median(x_valid)), 0.0) if n < 5 else _huber_scale(x_valid)
    if n < 5:
        s_i = float(np.median(np.abs(x_valid - centre))) * 1.4826

    y_hat = prior["mu_pop"] + (centre - prior["mu_pop"]) * B_n

    # moderated within-person variance (limma / Smyth 2004) replaces the SD floor
    sigma_i2_mod = (NU0 * prior["sigma_i2"] + (n - 1) * s_i**2) / (NU0 + n - 1)
    sigma_i_mod = max(np.sqrt(sigma_i2_mod), DEVICE_FLOOR.get(prior["metric"], 1e-6))

    # PEB alert scale — automatically wide at small n, tight as baseline accrues
    sigma_alert = np.sqrt(1.0 - B1 * B_n) * sigma_pop

    # heteroscedasticity guard: this patient is intrinsically noisier than cohort
    het = s_i > 2.0 * np.sqrt(prior["sigma_i2"])
    if het:
        sigma_alert *= s_i / np.sqrt(prior["sigma_i2"])

    return dict(y_hat=float(y_hat), sigma_alert=float(sigma_alert),
                sigma_within=float(sigma_i_mod), B_n=float(B_n),
                n=n, n_eff=float(n_eff), heteroscedastic=bool(het),
                provenance=f"PRE_OP_N_DAYS={n}", prior_version=PRIOR_VERSION)
```

`Z = 3.0`, not 1.96. At 6 metrics × 365 days a nominal 1.96 yields roughly **110 flags per patient-year**, which destroys clinician trust long before any outcome label arrives; Z=3.0 yields ~6. Z=2.0 is the amber/watch tier and does not notify.

### 4.1.9 The prior table

Persist, never mutate in place:

```sql
CREATE TABLE metric_prior (
  prior_version   TEXT    NOT NULL,     -- 'peb_v1'; alerts must be re-derivable
  metric          TEXT    NOT NULL,
  procedure       TEXT    NOT NULL,
  age_band        TEXT    NOT NULL,     -- '<55','55-64','65-74','75+'
  sex             TEXT    NOT NULL,
  bmi_band        TEXT    NOT NULL,
  mu_pop          REAL    NOT NULL,
  sigma_g2        REAL    NOT NULL,
  sigma_i2        REAL    NOT NULL,
  B1              REAL    NOT NULL,
  lambda_bc       REAL,                 -- frozen Box-Cox / 0 for ln / NULL untransformed
  rho_lag1        REAL    NOT NULL DEFAULT 0.0,
  prior_source    TEXT    NOT NULL,     -- 'literature_placeholder_v0' | 'cohort_mixedlm'
  n_patients      INTEGER NOT NULL,
  fit_date        TEXT    NOT NULL,
  PRIMARY KEY (prior_version, metric, procedure, age_band, sex, bmi_band)
);
```

Lambda reads it; the nightly batch writes it. An alert issued last month must be re-derivable from `prior_version` alone.

---

## 4.2 Deviation detection — adjudicating EWMA/CUSUM vs NightSignal

### 4.2.1 The honest comparison

Alavi et al., *Nat Med* 2022 (PMC8799466). Overnight RHR only (mean over 00:00–07:00, zero-step minutes), streaming median baseline across all prior nights (stabilizes in ~7 nights for >80% of participants), a 6-state deterministic FSM: **yellow at baseline+3 bpm on one night, red at baseline+4 bpm on two consecutive nights**, reset to green below threshold. 3,318 enrolled, 2,155 with data, 84 confirmed cases. **80% sensitivity, 87.7% specificity, 3-day median lead.** Alarm burden 3.42 alert-days per COVID-positive person vs 1.15 for non-COVID stress events. In the authors' own head-to-head at matched false-positive rate it beat **CuSum (72%)** and the LOF-based RHRAD (69%).

That is a direct, unfavourable benchmark for our EWMA(0.3, 2.66)/CUSUM(0.5, 5.0) stack: a simpler machine won.

### 4.2.2 Adjudication

**We cannot implement NightSignal as published, and we must stop citing its numbers.** Two blockers:

- **Data.** NightSignal needs overnight HR restricted to zero-step **minutes** — intraday resolution. `engine/dataload.load_daily_series` loads daily aggregates. If our connectors return a daily resting-HR scalar, the published algorithm is unimplementable. **Verify intraday HR + per-minute steps per connector before scoping.**
- **Population transfer.** Every NightSignal validation is in ambulatory, non-surgical adults. Post-op patients have elevated resting HR for weeks from pain, opioids, beta-blocker interruption, anaemia and deconditioning. An absolute +3 bpm rule against a streaming median that is itself chasing the surgical perturbation is not the published algorithm applied to a new population — it is a different algorithm. This is the single biggest transfer risk in the corpus.

**Decision:**

| Component | Verdict | Detail |
|---|---|---|
| Nocturnal restriction of vitals | **SHIP NOW (if intraday exists)** | The cheapest accuracy win available. Natarajan, Alavi and Miller all independently restricted to sleep/night windows. Removes activity confounding from RHR/HRV/RR. |
| Two-threshold streaming-median FSM | **SHIP, renamed and re-parameterized** | Call it `RhrStepDetector`, not NightSignal. Express thresholds in **patient SD units** (`+1.2·σ_within` yellow, `+1.6·σ_within` two consecutive nights red), not absolute bpm. Seed the streaming median from the **pre-op median** and **exclude post-op days 0–14** from it, or the baseline chases the surgical perturbation. Do not quote 80%/87.7% for it. |
| EWMA λ=0.3, L=2.66, ≥2 consecutive | **KEEP** | Monte Carlo (4,000 reps, i.i.d. Gaussian null): single-day flag has ARL0 ≈ **171** days/metric — ~1.06 false signals/patient-month across 6 metrics. The ≥2-consecutive rule raises ARL0 to **~780**. The 2-consecutive rule is load-bearing and must be structurally unbypassable. |
| CUSUM k=0.5, h=5.0 one-sided | **KEEP** | ARL0 ≈ **895**; detects a sustained 1-SD shift in ~10.5 days (EWMA-2consec: ~13 days at 1 SD, ~6 at 1.5 SD). Well tuned. |
| Kalman local-level residuals | **SHIP as a REPLACEMENT, not a layer** | See 4.2.4. |
| BOCPD (hazard 1/30–1/45) | **REFUSE** | See 4.2.5. |
| MEWMA + Ledoit-Wolf | **REFUSE at this scale** | See 4.3.4. |

### 4.2.3 The autocorrelation correction — every ARL number above is a lower bound

ARL0 ≈ 780 and ≈ 895 are **i.i.d.-normal numbers**. Daily RHR, HRV, sleep and skin temperature carry lag-1 autocorrelation commonly 0.4–0.7. `deviation.py:81` uses `EWMA_L*sqrt(λ/(2−λ))`, the steady-state SD under independence only. Under AR(1) the EWMA statistic's variance inflates by

```
(1 + φ(1−λ)) / (1 − φ(1−λ))  =  2.08   at φ=0.5, λ=0.3
```

so the true SD is ~1.44× assumed and the nominal 2.66-σ limit is really operating at ~1.85 σ. **True in-control ARL is plausibly 80–150 days, not 780–895** — roughly one false alarm per patient per episode from EWMA alone. The "2-consecutive rule is load-bearing" finding is the worst casualty, because serial correlation is exactly what makes consecutive exceedances co-occur; its ARL0 multiplier collapses from ~4.6× toward ~1.5×.

**Interim fix, ship with the baseline work:**

```python
L_eff = EWMA_L * sqrt((1 + phi_hat*(1-LAM)) / (1 - phi_hat*(1-LAM)))
L_eff = float(np.clip(L_eff, EWMA_L, 4.0))
# 14 pre-op days will not estimate phi; shrink toward the metric-level pooled value
phi_hat = (n/(n+10)) * phi_patient + (10/(n+10)) * phi_pooled_metric
```

Publish the **ARL0 surface over φ ∈ {0, 0.3, 0.5, 0.7}**, not a single number. Estimate φ per metric from pre-op windows and from LifeSnaps, and log it on every score.

### 4.2.4 Kalman local level — replace the EWMA, do not stack on it

The corpus proposes running EWMA(λ=0.3) on Kalman innovations. **That is double smoothing.** A local-level filter with q = σ²_η/σ²_ε = 0.02 has steady-state gain `K = (sqrt(q²+4q) − q)/2 ≈ 0.13` — it *is* an EWMA with λ=0.13. Running a λ=0.3 EWMA on its innovations produces a filter whose ARL nobody has computed.

**Correct design:** the local-level filter *replaces* the raw-z stage, and EWMA/CUSUM run on its **standardized one-step-ahead innovations** `v_t / sqrt(F_t)`, which are i.i.d. N(0,1) under a correct model — which is the assumption `h=5.0` already depends on and currently violates. Three concrete wins:

1. **Missing days are marginalized natively.** Fixes P3 without a reindex hack: on a gap, propagate the state and *grow* `F_t`, so control limits widen honestly instead of the filter running 3× too fast.
2. **`CUSUM_WINDOW = 14` is deleted.** It exists solely as an anti-drift-latching hack; a filter that tracks legitimate post-op drift makes it unnecessary.
3. `F_t` is a principled, day-varying replacement for the coverage heuristic.

**Serving form** — ~25 lines of numpy, no statsmodels:

```python
def local_level(y, q, mu0, P0):
    """Scalar Kalman local level. y may contain np.nan (missing days).
       Returns standardized innovations, white under a correct model."""
    mu, P, out = mu0, P0, np.full(y.size, np.nan)
    for t in range(y.size):
        P = P + q                                # predict (sigma_eps^2 == 1 units)
        if np.isnan(y[t]):                       # gap: propagate, widen, no update
            continue
        F = P + 1.0
        v = y[t] - mu
        out[t] = v / np.sqrt(F)
        K = P / F
        mu = mu + K * v
        P  = (1.0 - K) * P
    return out
```

`q = 0.02` fixed for series <60 days (slow, credible physiological drift). Initialize `mu0` at the PEB `y_hat` and `P0 = sigma_alert²`. **Do not run MLE in the request path** — it activates late in recovery or never, and belongs in the nightly job if at all.

**Mandatory runtime gate:** the innovations are white only if `q` is right, and `q` is fixed by fiat. Ship a **Ljung-Box test at lag 10** on the innovations; if it rejects at α=0.05 (Q > 18.307 for df=10 — hardcode the critical value, scipy is banned from the artifact), fall back to the inflated-limit path of §4.2.3 and log `LJUNGBOX_REJECT`. Without this gate we have relocated the independence assumption, not satisfied it.

### 4.2.5 BOCPD — refuse

The corpus recommends BOCPD with hazard λ=1/35 (correctly noting Adams & MacKay's 1/250 cannot fire within a 90-day episode) and a Normal-Inverse-Gamma prior (μ0=0, κ0=1, α0=2.0, β0=1.0), emitting when P(r_t<3)>0.5. **Do not build it.** Five reasons, any one sufficient:

1. Hazard 1/35 over 90 days carries a **prior expectation of ~2.6 changepoints per patient per episode before any data**; with a P(r<3)>0.5 emit rule it will fire on most patients most weeks.
2. `β0=1.0` assumes the innovations are truly unit-variance, which holds only if `q` is correctly specified — and `q` is fixed at 0.02 by fiat. BOCPD cannot distinguish variance misfit from a changepoint; it will read our filter tuning error as clinical events.
3. It sits **downstream of a filter designed to absorb the drift it detects**.
4. Six unadjusted streams per patient, no multiplicity handling.
5. **There is no ground truth for "recovery changed character on day 34."** It can never be measured at our scale, so it will never be tuned out — no metric would tell us to remove it. That is how alert fatigue becomes structural.

The legitimate version of this idea is **PELT offline, with a human analyst**: `rpt.Pelt(model='rbf', min_size=7, jump=1).fit(sig).predict(pen)` over completed recoveries, `pen = 2·σ̂²·log(n)` for `model='l2'` with σ̂ from MAD, sweeping `pen` and picking at the elbow. Purpose: characterize what normal trajectories look like per procedure and generate the in-control day sets that conformal calibration needs. Worth running at ~20–30 completed recoveries per procedure. If we later want online regime detection, first prove PELT boundaries correspond to something clinicians recognize, then derive the hazard from the observed empirical inter-changepoint distribution rather than from clinical intuition. Note that on unlabelled data a λ sweep over {1/20, 1/35, 1/60} can only show how output *changes*, not which setting is *right* — it is not a validation.

### 4.2.6 Deviation summary — final parameter set

```python
# engine/deviation.py
EWMA_LAMBDA = 0.3
EWMA_L      = 2.66          # inflated to L_eff by phi_hat; capped 4.0
MIN_CONSECUTIVE_OUT = 2     # structurally unbypassable
CUSUM_K, CUSUM_H = 0.5, 5.0
# CUSUM_WINDOW deleted — the local-level filter tracks legitimate drift
KALMAN_Q = 0.02             # steady-state gain K ≈ 0.13
SKIP_EARLY_DAYS = 2
LJUNG_BOX_LAG, LJUNG_BOX_CRIT = 10, 18.307
```

Also fix the EWMA warm-up: `e` initializes at 0.0, the correct asymptotic mean but a head-start artifact over the first ~1/λ observations — which, with `SKIP_EARLY_DAYS=2`, means the chart is least trustworthy in post-op week 1, precisely when infection presents. Apply the exact time-varying limit `λ/(2−λ)·(1−(1−λ)^{2i})` for the first ~15 points, or initialize at the first observation.

---

## 4.3 The composite index

### 4.3.1 What is wrong with it

`composite.py` sums weighted, clipped, one-sided **raw** z-scores with `HIGH=2.0`, `ELEVATED=1.2`. Four compounding defects:

1. **The null mean is not zero.** `min(max(z,0), 4.0)` makes each term a censored half-normal with mean ≈ 0.399σ. With weights summing to 1.0 the index has a null mean of **≈0.40**, so "normal ≤ 1.2" is barely two null-SDs up.
2. **The metrics are correlated.** RHR, RR, temp and inverted HRV co-move; typical pairwise ρ 0.3–0.6. `Var(Σ) = Σw_i²σ² + 2Σ_{i<j}w_iw_jρ_ijσ²` is roughly 2–2.5× the independence value, so the SD is ~1.5× larger than any independence-based intuition and 2.0 is a far lower quantile than believed. The composite **triple-counts a single autonomic disturbance**.
3. **The weights sum to 0.55 for Apple patients** (P4).
4. **The driver percentages are not attributions.** Reporting each metric's share of a *correlated* sum as an independent contribution, to a clinician, builds a mental model ("this one is temperature-driven") that does not survive a change of weight vector.

### 4.3.2 Weight renormalization + minimum-metrics gate

Ship now. This is the P4 fix and it is a day of work.

```python
# engine/composite.py
WEIGHTS = {                       # elicited, versioned, NOT asserted (see 4.3.5)
    "resting_hr":        (0.28, "up"),
    "hrv":               (0.24, "down"),   # HRV_RMSSD *or* HRV_SDNN, separate baselines
    "respiratory_rate":  (0.20, "up"),
    "steps":             (0.16, "down"),
    "skin_temp":         (0.12, "up"),     # demoted from 0.25 pending ambient correction
}
MIN_METRICS_PRESENT = 3
MIN_WEIGHT_PRESENT  = 0.60        # renormalizing 0.30 of weight to 1.0 is a lie

def composite_index(deviations, priors):
    present = {m: w for m, (w, d) in WEIGHTS.items() if _usable(deviations, m, priors)}
    w_sum = sum(present.values())
    if len(present) < MIN_METRICS_PRESENT or w_sum < MIN_WEIGHT_PRESENT:
        return CompositeResult(index=None, level="insufficient_metrics",
                               metrics_present=len(present), weight_present=round(w_sum, 2))
    total = sum((w / w_sum) * _adverse_z(deviations, m) for m, w in present.items())
    ...
```

Renormalization has its own hazard — it makes a single deviating metric look like a whole-body signal — which is exactly why the minimum-metrics gate and the minimum-weight gate must ship *together* with it. Emit `metrics_present` and `weight_present` on every score; a tier computed from 3 of 5 metrics is a different claim from one computed from 5.

**Metric-variant handling (P4), and it is two changes, not one:**
- Add `HRV_SDNN` and `SKIN_TEMP_DELTA` to `ANALYZED_METRICS` and to `ADVERSE_UP`/`ADVERSE_DOWN`.
- **Do not treat SDNN and RMSSD as interchangeable.** There is no conversion constant and their distributions differ. Keep **separate baselines and separate priors per statistic** — a z-score is comparable across statistics even when the raw value is not — and map both into the single `"hrv"` composite slot.
- **`SKIN_TEMP_DELTA` is already a deviation.** Passing it through `compute_baseline` double-centres it. Route it to a `delta` code path where `y_hat = 0` by construction and only the moderated variance is estimated.

### 4.3.3 Conformal p-values — and the negative-label problem, squarely

The replacement for 1.2/2.0 is the split-conformal p-value on the composite as nonconformity score:

```
p = (1 + #{i in calib : A_i >= A_new}) / (n_cal + 1)
```

Distribution-free, valid under exchangeability alone, no distributional assumption, and it is exactly the uniformly-distributed-under-null quantity the FDR layer needs. Three hard constraints:

**(a) The exchangeable unit is the PATIENT, not the patient-day.** The corpus contradicts itself here: the CQR row correctly specifies patient-level splitting with one summary score per calibration patient, while the alerting row uses patient-days and calls "20 patients × 90 days = 1,800 rows" ample. Under strong within-patient dependence the effective n is nearer the number of patients. **Adjudication: patient-level throughout.** One summary conformity score per calibration patient — the 90th percentile of that patient's daily scores (documented, and empirical coverage of the alternative "max" rule reported alongside). Therefore:

```
min attainable p = 1/(n_cal + 1)
alpha = 0.05  requires  n_cal >= 19 uneventful PATIENTS
alpha = 0.01  requires  n_cal >= 99 uneventful PATIENTS
```

Enforce in code; below the floor the tier degrades to an explicit `insufficient_calibration` state, never silently never-firing.

**(b) "Uneventful" is a NEGATIVE LABEL, not the absence of one.** This is the single most important correction in this section. The claim that conformal "needs ZERO adverse-outcome labels — that is the point" is a **logical error**. Knowing that a patient completed recovery with no adverse event requires the same 90-day follow-up, chart review and adjudication as knowing they had one. Today the schema records **no outcome of any kind**, so the set of uneventful completed recoveries is not merely small — it is *unknowable*. If we plan conformal calibration for month 2 on the belief it is label-free, we will discover at month 2 that we cannot construct the calibration pool, and the best idea in the research slips a year.

**What to do about it, in order:**

1. **Ship the outcomes schema this sprint.** It is days of work with a multi-year lead time and it is the highest-priority item in this entire design:

```sql
CREATE TABLE outcome_event (
  patient_id TEXT NOT NULL, event_type TEXT NOT NULL,   -- ssi_superficial|ssi_deep|
  event_date TEXT NOT NULL,                             -- organ_space|readmission_90d|
  source TEXT NOT NULL,                                 -- mua|ed_visit|unplanned_contact|
  adjudicator_id TEXT, adjudication_date TEXT, kappa REAL
);
CREATE TABLE follow_up (
  patient_id TEXT PRIMARY KEY,
  last_known_contact TEXT NOT NULL,
  follow_up_complete INTEGER NOT NULL DEFAULT 0        -- THIS is the negative label
);
-- every RiskAssessment additionally stamps: engine_git_sha, config_version,
-- prior_version, input_snapshot_hash. Without the frozen-at-emission score,
-- no retrospective evaluation is possible.
```

2. **In the interim, calibrate externally and label it as such.** Use **LifeSnaps (n=71, Fitbit Sense, DOI 10.5281/zenodo.6826244)** and **PMData (n=16)** — non-surgical cohorts where every alert is a false positive by construction, ~9,000 person-days, free, no IRB. n=71 patients clears the α=0.05 floor (≥19) but **not** α=0.01 (≥99). So: **α=0.05 only, `calibration_source='external_lifesnaps_v1'`, surfaced in the API**, and never described as calibrated on our own population. This is also the vehicle for setting `HIGH`/`ELEVATED` as **empirical quantiles of an external null** rather than round numbers, and for measuring the current engine's actual false-alarm rate — a number nobody currently has.

3. **Exchangeability is still violated by post-op trend.** Bucketing into days 1–7 / 8–21 / 22–90 reduces but does not remove it; day-22 and day-89 conditional distributions differ, making p-values anti-conservative early in each bucket and conservative late — so false alarms cluster in post-op week 1 and at day 8, exactly where clinicians are already most anxious. Mitigation: conformalize the **residual against the fitted expected curve** (§4.4), not the raw index, so the conditional distribution is closer to stationary in day. Measure and report empirical coverage on held-out patients; outside 85–95% for nominal 90%, declare exchangeability broken publicly.

4. **Drop the power martingale.** `M_t = Π ε·p_i^(ε−1)` with ε=0.92 alarming at M_t>100 under Ville's inequality bounds the trajectory false-alarm probability at 1/100 **only for i.i.d. U(0,1) null p-values**, which ours are not. Shipping a number labelled "guaranteed 1% false-alarm rate" that carries no such guarantee is *worse* than an admittedly arbitrary 2.0, because an arbitrary threshold makes no promise. The CUSUM we already have **is** a restart-at-zero SPRT and is the honest e-process here.

### 4.3.4 MEWMA — refuse at this scale

The corpus proposes MEWMA (λ=0.15, h4≈16.0 for p=6, pooled Ledoit-Wolf covariance) as the principled replacement for the hand-set weights. **Reject.** Three independent disqualifiers:

1. **The control limit is admittedly unverified.** Published Lowry/Prabhu-Runger tables are indexed at specific λ (p=6, λ=0.1 → h4=15.26; λ=0.2 → 16.57) and the ARL surface is not linear in λ. Interpolating h4 and shipping it is not defensible.
2. **The exact time-varying covariance form** — which the proposal correctly insists on, since the asymptotic limit is not reached until i≈30 — makes the chart **most sensitive at small i**, i.e. post-op days 2–6, when physiology is legitimately and massively perturbed. It will fire on essentially every patient.
3. **Ledoit-Wolf across patients estimates the BETWEEN-patient correlation structure; the chart needs the WITHIN-patient day-to-day residual structure.** These are different matrices — between-patient RHR/temp correlation is driven by body composition and demographics, within-patient by illness and ambient conditions, and they can differ in magnitude and sign. Substituting one for the other is the ecological fallacy in covariance form.

Plus: a Hotelling statistic is **non-diagnostic by construction**. It says "something is off" without saying what, destroying the typed reason codes, which are this product's most defensible asset and the FDA CDS criterion-4 argument.

**Revisit only past ~500 patients, and then correctly:** estimate each patient's own residual correlation matrix over their post-op days, Fisher-z transform, average across patients weighted by (n_i − 1), inverse-transform, shrink toward a diagonal target; simulate the control limit for our exact (p, λ, n) and pin the simulation in CI; gate to post-op day ≥14; always pair T² with an MYT decomposition so a reason code still exists.

### 4.3.5 Weights: elicited, not asserted

Until conformal calibration on our own cohort exists, the weights are a clinical judgement and must be documented as one. Run a **SHELF-roulette or pairwise-AHP elicitation with 8–12 orthopaedic surgeons/PAs**, elicit both the weights and the tier thresholds as an exchange rate, record inter-rater spread, and publish the spread as our uncertainty. Store `elicitation_provenance` (who, when, method, spread) alongside the weight vector as a versioned config row, not a constant in code.

**Delete the driver percentages or compute Shapley values.** Five metrics = 32 coalitions, trivially cheap in the request path. Shares of a correlated sum are not attributions and should not be shown to a clinician.

Once the prior table exists, the defensible data-driven variant is **inverse-variance weighting**: `w_m ∝ 1/(1 − B1_m·B_{n,m})`, normalized — metrics whose baseline is short or whose within-person variance is large contribute less automatically. Keep the elicited weights as the fallback when the prior table is unavailable, and **log which weighting produced each score**.

---

## 4.4 Trajectory

### 4.4.1 What is wrong with the hand-tuned logistic

`curves.py` hand-parameterizes `f(d) = floor + (1−floor)/(1+exp(−r(d−d50)))` per procedure and the docstring admits the seed generator shapes on-track patients along the same curves. The trajectory feature therefore has **zero empirical content** (P5). `CI_WIDTH = 0.08` is a flat band that is neither a confidence interval nor a prediction interval, and `TrajectoryState.BEHIND` at −12% is a threshold with no derivation.

`FUNCTIONAL_RATIO_SD = 0.10` (`deviation.py:36`) is worse. Observed day-to-day CV of daily step count in free-living adults is **30–50%**, so it understates the denominator by 3–5× and inflates every functional z by that factor. It is also constant in post-op day, which the code's own structure makes indefensible: `standardized_deviations` divides by `curve_mid(procedure, d)`, and for TKA at day 2 `curve_mid ≈ 0.26`, so the ratio's noise is amplified ~4× relative to day 60. A patient at 0.8× expected steps currently scores z = −2.0 and flags, when 0.8× is comfortably inside one day's normal variation for essentially everybody. And since the seed generator produces steps from that same `curve_mid`, 0.10 was almost certainly tuned to make seed patients behave — a fitted parameter of the circular loop, not a physiological quantity.

### 4.4.2 The scale correction — ship today, zero patients required

Olanrewaju et al., *Rheumatol Int* 2026;46(6) (DOI 10.1007/s00296-026-06135-y), n=82 wrist accelerometer, TKA and UKR, 1 week pre-op + 6 weeks post-op. LCGA fitted separately to absolute and relative step counts:

| Class | Absolute (wk1 → wk6 median steps) | Relative (% of pre-op at wk 6) |
|---|---|---|
| High | 37%: 991 → **6,606** | 47%: **92%** |
| Moderate | 29%: 360 → **3,739** | 32%: **64%** |
| Low | 34%: 29 → **1,452** | 21%: **31%** |

**Only 32% of the cohort exceeded their pre-operative step count by week 6.** Class membership was driven overwhelmingly by **pre-operative step count** and procedure (UKR vs TKA). Classes separated far better on the relative scale than the absolute one.

Three consequences, all shippable now:

1. **The comparand is ratio-to-own-pre-op-baseline**, and pre-op step count is a **covariate in the expected curve**, not a nuisance. An absolute-scale threshold systematically flags deconditioned patients and misses deteriorating athletic ones.
2. **Set "behind schedule" at the published LOW-class boundary** (~31% of pre-op at week 6), not at a fraction of the median.
3. Corroborating expectations: J Arthroplasty 2024 (n=566, first 6 weeks post-TKA) found greatest gains in **all** metrics in the first 3 weeks, with men out-stepping women and obese patients performing worse — so a curve conditioned only on (procedure, day) is misspecified. Sex, BMI and pre-op activity are first-order covariates.

**Interim, literature-anchored parameters** (zero patients): James-Stein shrink each procedure's mean toward the global mean at `w = n_p/(n_p + 25)`, so a procedure needs ~25 patients before it is trusted half as much as the pool.

**And fix `FUNCTIONAL_RATIO_SD` immediately:**

```python
# minimum viable fix: floor 0.25 and make the day-dependence explicit
def sd_ratio(day, procedure, sigma_patient, baseline_mean, sigma_curve_d):
    m = float(curve_mid(procedure, day))
    return max(0.25, sqrt((sigma_patient / (baseline_mean * m))**2 + sigma_curve_d**2))
```

Better, and the target state: model `log1p(steps)` and take the residual SD from the patient's own pre-op window with the same ν₀=8 moderated shrinkage used for vitals — **one estimator for all metrics, and the hand-set constant disappears.**

### 4.4.3 The replacement curve — Bayesian hierarchical Mitscherlich (20–30 patients/procedure)

Fit **offline in PyMC**, export coefficients. Mitscherlich / asymptotic regression, 3 parameters — more identifiable at small n than a 4-parameter logistic or Gompertz — on the **ratio scale**:

```
r_ij = A_i · (1 − exp(−k_i · (d_ij − t0_i)))
y_ij ~ StudentT(nu=4, mu=r_ij, sigma)          # t4, not Normal: non-wear + bad days
```

**Non-centred parameterization is mandatory.** The current hand-tuned floor/r/d50 values enter as the **prior means on the population hyperparameters**, so the model starts exactly where the engine is today and moves only as data accrues.

```python
# batch/fit_trajectory.py — AWS Batch / container-image Lambda, NEVER the API function
with pm.Model() as m:
    mu_logA = pm.Normal("mu_logA", np.log(1.0), 0.30)      # asymptote ~100% of pre-op
    sig_A   = pm.HalfNormal("sig_A", 0.40)
    zA      = pm.Normal("zA", 0, 1, shape=n_pat)           # non-centred
    logA    = mu_logA + sig_A * zA

    mu_logk = pm.Normal("mu_logk", np.log(1/21), 0.50)     # ~21-day time constant:
    sig_k   = pm.HalfNormal("sig_k", 0.50)                 # gains concentrate in wk 1-3
    zk      = pm.Normal("zk", 0, 1, shape=n_pat)
    logk    = mu_logk + sig_k * zk

    mu_t0   = pm.Normal("mu_t0", 2.0, 2.0)
    sig_t0  = pm.HalfNormal("sig_t0", 2.0)
    t0      = mu_t0 + sig_t0 * pm.Normal("zt", 0, 1, shape=n_pat)

    # covariates on log A and log k: standardized pre-op steps, sex, BMI, procedure
    b = pm.Normal("b", 0, 0.25, shape=(2, n_cov))
    mu  = pm.math.exp(logA[pid] + pm.math.dot(X, b[0])) * (
          1 - pm.math.exp(-pm.math.exp(logk[pid] + pm.math.dot(X, b[1])) *
                          (day - t0[pid])))
    sigma = pm.HalfNormal("sigma", 0.25)
    pm.StudentT("y", nu=4, mu=mu, sigma=sigma, observed=y)
    idata = pm.sample(draws=1500, tune=1500, chains=4, target_accept=0.95)
```

**Publication gate:** all R-hat < 1.01, ESS_bulk > 400 per parameter, **zero divergences**. Below 50 patients this will sample fine and produce a posterior that is essentially the prior — which is fine and correct behaviour, but must not be presented as learned.

**Data gate:** 20–30 patients per procedure with ≥14 days each for stable population hyperparameters (10 if procedures are pooled under a procedure-level hyperprior). Individual `A_i`/`k_i` become meaningful at ≥10 observed days for that patient; below that the patient is reading the population curve, which is correct and must be surfaced as low confidence.

### 4.4.4 Graduation to ExpectileGAM centiles (100–150 patients/procedure)

```python
from pygam import ExpectileGAM, s, l, f
terms = s(0, n_splines=8, spline_order=3, lam=0.6, constraints='monotonic_inc') \
        + l(1) + l(2) + f(3)          # sqrt(day), preop_activity_z, bmi_z, procedure
base = ExpectileGAM(terms).gridsearch(X, y, lam=np.logspace(-3, 3, 11))
LAM  = base.lam                       # FREEZE, then refit all five quantiles with it
curves = {q: ExpectileGAM(terms, lam=LAM).fit_quantile(X, y, quantile=q,
                                                       max_iter=50, tol=1e-4)
          for q in (0.10, 0.25, 0.50, 0.75, 0.90)}
```

- **Predictor is `sqrt(day)` or `log1p(day)`**, compressing the fast early phase — Cole's λ<1 sample-composition insight.
- `n_splines=8` over 0–90 days gives ~11-day effective knot spacing, deliberately coarse to avoid chasing noise at n<200.
- **Freeze `lam` across all five quantiles** so the bands stay parallel; then **post-hoc monotone rearrangement** (`np.sort` across the quantile axis at each day) because separately-fitted quantile curves cross.
- SE per centile per day by **patient-level bootstrap, 200 resamples, resampling PATIENTS not rows**.

**Never fit the 2nd/98th centiles.** Cole, *Stat Methods Med Res* 2021 (DOI 10.1177/0962280220958438), GAMLSS on 6,878 boys: achieved SE = 0.041 z for the median and 0.066 z for the 2nd/98th, and concludes optimally designed growth-reference studies need **7,000–25,000 subjects per sex**. Our domain is 0–90 days not 0–21 years, so the requirement is far lower — but the 2nd/98th centile is permanently off the table at our scale. Corroborating floor: Clinical Chemistry 2004 puts non-parametric time-specific reference centiles at n>120, "as high as 500" when parametric assumptions are uncertain; CLSI EP28-A3c requires n≥120.

**Derived staging** (asymptotic SE of a centile at standardized position z_p ≈ `sqrt(1 + z_p²/2)/sqrt(n_eff)`; factors 1.00 median, 1.11 at 25/75, 1.35 at 10/90, 1.76 at 2/98; design effect ~10.8 at ρ≈0.75 over a 14-day smoothing neighbourhood, partly offset by Cole's 2–3× borrowing-strength from smoothing):

| Patients per procedure | What may be shipped |
|---|---|
| < 30 | Hierarchical Bayesian Mitscherlich only, **no centiles** |
| 30–100 | Median curve + a single pooled dispersion (~35 patients for SE(z)≤0.15 on the median) |
| 100–250 | 10/25/50/75/90 centiles per procedure (~65 patients for SE(z)≤0.15 at 10/90; ~140 for ≤0.10) |
| 250–500 | add 5th/95th |
| ≥ 500 | *consider* 2nd/98th, and only then |

**Require ≥60% day-coverage per patient before that patient contributes to any fit**, and exclude patient-days with <10 wear-hours from both the fitting set and the scoring path. Uncorrected non-wear drags the fitted 10th centile down and then masks genuine deterioration — the dominant failure mode of a step-count centile system.

### 4.4.5 Prediction interval, not confidence interval — the single biggest statistical defect

Three uncertainty sources are currently conflated, and the flat `CI_WIDTH = 0.08` represents none of them:

- **(a)** uncertainty in the population mean curve — a *confidence* interval, width ∝ σ_between/√n, **shrinks to zero** as patients accrue;
- **(b)** between-patient variability — the marginal **prediction interval / centile band for a NEW patient**, which does **not** shrink with n, and **this is the correct comparand** for a first-week patient with no history;
- **(c)** within-patient day-to-day noise — which is what makes a single low day meaningless.

Because the curve is hand-parameterized rather than fitted, (a) is not merely unknown but *unbounded*.

**Required behaviour:**

```python
# 1. score against the marginal predictive distribution, on the ratio scale
centile = predictive_centile(ratio_obs, day, covariates, curve_artifact)

# 2. never flag a deviation smaller than the curve's own ignorance
if abs(ratio_obs - curve_mid_d) < 2.0 * se_curve[day]:
    return None                                  # suppressed: below model SE

# 3. no trajectory reason code before post-op day 7
# 4. none for a patient with < 4 of the last 7 days covered
# 5. once the patient has >= 10 days of their own history, switch to the
#    INDIVIDUALIZED predictive interval conditional on their posterior random
#    effects — materially narrower, and free from the hierarchical model
```

This is what stops a curve fitted on 30 patients from generating confident-sounding alerts it cannot support, and it makes the alert rate **automatically increase as the model earns it**. Until it is implemented, label the band in the UI as **"illustrative, not a statistical interval."**

### 4.4.6 Two-sided, not one-sided

Med Sci Sports Exerc 2026 (ACLR, accelerometry at 2/4/6/12 months) found two MVPA classes — "consistent" 74.5% and **"high-increasing" 25.5%** — and the high-increasing class showed significantly greater ΔT1ρ in the lateral femoral condyle (P=0.006), i.e. deleterious early cartilage change. A one-sided "ratio-to-expected below threshold" rule treats over-performance as safe. **For ACL and cartilage-loading procedures the trajectory alert must be two-sided with an asymmetric upper threshold.**

### 4.4.7 The versioned curve artifact

The curve must stop being a hard-coded function and become a versioned artifact. This is the change that makes everything else incremental — without it there is nowhere to put a fitted curve.

```sql
CREATE TABLE expected_curve (
  model_version TEXT, procedure TEXT, stratum TEXT, day INTEGER,
  c10 REAL, c25 REAL, c50 REAL, c75 REAL, c90 REAL,
  se_c50 REAL, se_c10 REAL, se_c90 REAL,
  n_patients INTEGER, method TEXT,       -- hand_tuned_v0|pymc_mitscherlich_v1|expectile_gam_v2
  fit_date TEXT,
  PRIMARY KEY (model_version, procedure, stratum, day)
);
```

Every emitted trajectory reason code carries `model_version` and `se_c50` at that day. A few thousand floats; Lambda loads it at cold start and interpolates.

### 4.4.8 "Days behind expected" — the cheapest genuinely new signal

DTW lag against the fitted median needs only a median curve (~35 patients) and 14 days of the patient's data:

```python
path, _ = dtw_path(smooth7(patient_ratio), median_curve,
                   global_constraint='sakoe_chiba', sakoe_chiba_radius=7)
lag_days = np.mean([i - j for i, j in path])
```

A 7-day Sakoe-Chiba radius encodes "up to one week ahead or behind" and blocks pathological warping. **Do not z-normalize per series** — level *is* the clinical signal. *"You are about 9 days behind the typical recovery for your procedure"* is far more actionable than "composite deviation index 1.4," and it decomposes deviation into timing versus magnitude, which have different clinical meanings: a patient tracking the right shape 9 days late is a different problem from one who has plateaued. Fit offline (`tslearn`), serve the lag as a scalar.

---

## 4.5 Alerting — the episode state machine

### 4.5.1 Why this must be built before any FDR machinery

Nobody added up the detectors. Running simultaneously: the RHR step detector (yellow on a *single* night), EWMA-2-consecutive, CUSUM, trajectory deviation, absolute-threshold rules in `risk.py`, a conformal test at p≤0.05 which **by construction averages 1 flag per 20 patient-days ≈ 1.5/patient-month on uneventful patients** — that alone is 3× the budget before anything else fires — and a red-flag text matcher tuned to recall ≥0.95. Per patient per day the engine evaluates ~8 metrics × 2 detectors plus composite plus trajectory plus rules ≈ **20+ decision points daily × 90 days ≈ 1,800 decision opportunities per episode.**

At 100 patients this is plausibly **100–300 notifications per week**. The documented endpoint is CDS override rates of **49–96%** (van der Sijs, JAMIA 2006). Ghomrawi 2023 logged **387 and 438 false positives across 162 patients**.

**Benjamini-Hochberg across the morning list controls the wrong axis.** It bounds the false-discovery proportion among patients flagged *today* and does nothing about one patient generating forty alerts across an episode — which is the mechanism that actually kills clinical products. The episode state machine **is** the multiplicity control; FDR is a refinement on top of it. Build it first.

### 4.5.2 The state machine

**Detectors emit typed evidence. Only episodes alert.**

```sql
CREATE TABLE alert_episode (
  id TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL,
  dedup_key TEXT NOT NULL,          -- (patient_id, metric_family, direction)
  state TEXT NOT NULL,              -- OPEN|ACKED|SNOOZED|RESOLVED
  tier  TEXT NOT NULL,              -- ELEVATED|HIGH
  opened_at TEXT, tier_changed_at TEXT, resolved_at TEXT,
  snooze_until TEXT,
  engine_git_sha TEXT NOT NULL, config_version TEXT NOT NULL,
  prior_version TEXT NOT NULL, curve_version TEXT
);
CREATE TABLE alert_evidence (          -- append-only; detectors write here
  episode_id TEXT, as_of_date TEXT, detector TEXT, reason_code TEXT,
  metric TEXT, direction TEXT, magnitude REAL, p_conformal REAL
);
CREATE TABLE alert_action (            -- the fatigue KPI *and* the label store
  episode_id TEXT, actor TEXT, at TEXT,
  action TEXT,                        -- viewed|acked|snoozed|called|scheduled|escalated|dismissed
  note TEXT, outcome_adjudication TEXT
);
```

Rules, in force:

1. **One open episode per patient.** An open episode absorbs subsequent daily signals as severity updates — never a new notification.
2. **Notify only on episode open or tier escalation** (ELEVATED → HIGH), or when a new independent metric family joins the episode.
3. **Hysteresis.** Open at HIGH (CUSUM > h=5, or conformal p ≤ α_high, or tier HIGH). Close only at a distinctly lower bar: CUSUM back to 0, **or** the Wald two-boundary lower crossing, **or** 3 consecutive in-control days — whichever tests best on replay. Wald at α=0.05, β=0.20: `log A = log(16) = 2.77` to open, `log B = log(0.21) = −1.56` to close. The daily increment for a 1-SD-shift alternative is `(x−μ0)/σ − 0.5` — **structurally identical to the existing CUSUM increment at k=0.5**, so the CUSUM *is* a restart-at-zero SPRT. Do not add a second sequential test; use the two-boundary form only for the resolve decision, which is the missing half of hysteresis.
4. **Snooze has mandatory expiry** (24 h / 72 h / 7 d) and is **auto-voided by tier escalation**. Snooze must never mute an escalation.
5. **Acknowledgement** moves the episode to `owned` and stops reminders. Unacknowledged HIGH re-reminds once at +24 h, then escalates to a fallback contact.
6. **Escalations fail OPEN.** Low confidence suppresses the *reassuring* statement and never suppresses an alert.
7. **Every detector is a pure function of (observation history, as-of date)**, so replay equals production. This rule permits EWMA, CUSUM, the streaming-median detector, conformal and ACI, and **forbids SAFFRON/ADDIS and any alpha-wealth-accumulating scheme** — their guarantees depend on the actual ordered sequence of tests performed, which under lazy-on-read scoring depends on which charts a clinician happened to open. That is not reproducible and voids the FDR guarantee outright.

### 4.5.3 The disengagement detector

**Correction to a claim in the deployment critique:** it asserts `TIER_ORDER` sorts `MISSING_DATA` below `LOW`. That is **wrong** — `worklist.py:14` has `{HIGH:0, MEDIUM:1, MISSING_DATA:2, LOW:3}`, so MISSING_DATA already outranks LOW. The sort order is fine.

The real defect is that **disengagement is an absence of a detector rather than a detector.** The most likely silent failure of this product is a patient who feels unwell, stops wearing the device, and thereby stops generating deviations. Add:

```python
COVERAGE_COLLAPSE:  coverage_7d drops >= 40 percentage points vs the prior 7 days
                    in a patient whose prior coverage was >= 0.60
                    -> opens an episode at MEDIUM or above, on its own
DECLINING_ADHERENCE: coverage_7d falls below 0.50 after having exceeded 0.80
```

*"We have lost visibility on this patient"* is actionable; silence is not. Also raise `confidence.py`'s `GATE` from 0.4 (3 of 7 days — not enough to say anything) to **5 of 7 days** for MEDIUM, consult `WEAR_TIME_MINUTES` (currently ignored entirely, so a back-filled zero or a watch worn 20 minutes both score as full coverage), and drop `SPO2`/`SKIN_TEMP` from `KEY_METRICS` gating or weight the gate by what the patient's device actually supplies — otherwise coverage is penalized by device brand rather than by wear. Log `coverage_7d`, `coverage_slope` and `days_since_last_sync` as first-class fields on every score, and add `last_known_contact` to the schema **today** — it cannot be reconstructed retrospectively.

### 4.5.4 The false-alarm budget and the CI test that enforces it

**Budget: ≤ 0.5 false episode-openings per patient-month, across all detectors combined.**

With 6 metrics that implies per-metric ARL0 ≥ 6·30/0.5 = **360 days** (fewer effective tests since RHR/HRV/temp are correlated; effective m is nearer 3–4). Current settings meet it **only with** the 2-consecutive rule, and only under i.i.d. assumptions (§4.2.3). The de-escalation knob if field volume is too high: L=3.0 with 2-consecutive pushes ARL0 from ~780 to ~2,700.

```python
# tests/test_alert_budget.py — FAILS THE BUILD when the budget is exceeded
BUDGET_EPISODES_PER_PATIENT_MONTH = 0.5

@pytest.mark.parametrize("cohort", ["lifesnaps", "pmdata", "synthetic_uneventful_100x90"])
def test_false_episode_budget(cohort):
    """Every alert on these cohorts is false by construction:
       LifeSnaps n=71 and PMData n=16 are non-surgical; the synthetic cohort is
       generated by a DIFFERENT functional form than the engine's (see P5)."""
    episodes, patient_months = replay_full_stack(load_cohort(cohort))
    rate = episodes / patient_months
    lo, hi = participant_bootstrap_ci(episodes_per_patient, B=2000)   # bootstrap
    assert rate <= BUDGET_EPISODES_PER_PATIENT_MONTH, (               # PATIENTS, not days
        f"{cohort}: {rate:.2f} false episode-openings/patient-month "
        f"(95% CI {lo:.2f}-{hi:.2f}) exceeds budget {BUDGET_EPISODES_PER_PATIENT_MONTH}")

def test_arl0_surface_under_autocorrelation():
    """The i.i.d. ARL0 is a lower bound. Publish the surface, assert the floor."""
    for phi in (0.0, 0.3, 0.5, 0.7):
        arl = monte_carlo_arl0(n_reps=4000, phi=phi, lam=0.3, L=effective_L(phi),
                               min_consecutive=2)
        record_metric(f"arl0_ewma2_phi{phi}", arl)
        assert arl >= 360, f"phi={phi}: ARL0={arl:.0f} below the 360-day floor"
```

The budget then **constrains the parameters** instead of being contradicted by them. Every threshold-changing PR must show its effect on this number. Bootstrap **per participant, never per day.**

The synthetic cohort must not be generated from `curves.py` (P5): Mitscherlich form, literature-anchored parameters (Olanrewaju week-1 median ~360 steps, week-6 ~3,739, only ~1 in 3 exceeding pre-op by week 6), per-patient AR(1) noise φ~U(0.3,0.7) per metric, MCAR and MNAR non-wear gaps.

### 4.5.5 The PPV arithmetic, worked — and what the product may therefore alert on

`PPV = sens·prev / (sens·prev + (1−spec)(1−prev))`. At sensitivity 80%:

| Target | Prevalence | Spec 90% | Spec 95% | Spec 99% |
|---|---|---|---|---|
| **PJI** | **1%** | **PPV 7.5%** (1 true hit per ~13 alerts) | **13.9%** | **44.7%** |
| Readmission | 5% | 29.6% | 45.7% | — |
| 30-day complication | 10% | 47.1% | — | — |

Inverting for PJI at sens 80%: PPV 20% requires **spec 96.8%**; PPV 33% requires **98.4%**; PPV 50% requires **99.2%**.

**Therefore:**

> **The product may not ship a PJI-specific alert.** A per-patient infection-specific alert can never have decent PPV from wearables alone. The product alerts on **"deviation from expected recovery"** — a ~10% base rate where PPV ~45–50% is achievable at spec 90–95% — and infection is discussed **only as a differential in the narrative**, never as the alert's subject.

The number needed to alert (NNA = 1/PPV) targets: **NNA ≤ 5 (PPV ≥ 20%)** for the "review this patient" tier; **NNA ≤ 2–3 (PPV ≥ 33–50%)** for "call the patient / escalate."

The standing cautionary benchmark is the **Epic Sepsis Model** (Wong, *JAMA Intern Med* 2021, 27,697 patients / 38,455 hospitalizations, 7% prevalence): hospitalization-level **AUC 0.63** against a vendor claim of 0.76–0.83; at the deployed threshold sensitivity 33%, specificity 83%, **PPV 12%, NNE 8**. It alerted on **18% of all hospitalizations while missing 67% of sepsis cases**, and identified only 7% of the cases clinicians missed. Report alert volume per census, PPV, and NNE — **not AUC** — as the deployment metrics.

### 4.5.6 Setting the tier thresholds from elicited costs, not conventions

Vickers & Elkin net benefit: `NB = TP/n − (FP/n)·(p_t/(1−p_t))`. The elicitation protocol that works with surgeons: *"How many patients would you accept calling or seeing to catch one real deteriorating patient?"* An answer of R:1 implies `p_t = 1/(R+1)`.

| Response tier | Expected R | Implied p_t |
|---|---|---|
| Message-based check-in | ~19 | 0.05 |
| Phone call | ~9 | 0.10 |
| Clinic visit | ~3 | 0.25 |

Elicit from ≥2 surgeons **per tier**, store `threshold_high`/`threshold_elevated` **per site** with the harm ratio that generated them, and recompute the score→probability calibration once ≥50 adjudicated episodes exist. Until then, publish the *implied* NNA of the current thresholds on retrospective data. `dcurves` (MSKCC) does the arithmetic; bootstrap the net-benefit curve with 500 **patient-level** resamples and plot the CI band — at <100 events the band will be wide and *that is the finding*.

### 4.5.7 Multiplicity, after the state machine

Apply **Benjamini-Hochberg at q=0.10** across today's **episode-opening candidates** — one conformal p-value per patient, computed by the nightly batch so the test sequence is deterministic and replayable. One line: `statsmodels.stats.multitest.multipletests(pvals, alpha=0.10, method='fdr_bh')` (offline; the request path receives the already-ranked list).

BH requires independence or PRDS. Per-patient conformal p-values on a given morning share device model, firmware version, weather and season — a cold snap moving skin temperature across 30% of the panel is a plausible PRDS violation producing **correlated bursts**. **Measure cross-patient p-value dependence on LifeSnaps before choosing BH over e-BH**, and know the answer before January rather than during it. Benjamini-Yekutieli (`fdr_by`) is valid under arbitrary dependence but costs a log(m) penalty (~3–6× at m=20–1000) that will kill power at our scale; **e-BH** (BH on e-values, valid under arbitrary dependence) is the right phase-2 upgrade.

**Defer SAFFRON/ADDIS online FDR indefinitely.** It controls the wrong axis, its independence assumptions are violated by daily re-testing of the same patient, its alpha-wealth is not replayable under our architecture, and the only Python implementation (`online-fdr` 0.0.3, beta, July 2025) is not a defensible dependency in the alerting path of a clinical product at n<100 patients.

### 4.5.8 Patient-facing "expected range" bands

Adaptive Conformal Inference (Gibbs & Candès, NeurIPS 2021), update rule verified from the paper:

```
alpha_{t+1} = alpha_t + gamma·(alpha − err_t),   err_t = 1{y_t outside C_t(alpha_t)}
alpha = 0.10 (90% bands),  gamma = 0.005 (paper's stable value; 0.01 if coverage lags)
score = |observed − f(d)·baseline| / rolling MAD
```

Distribution-free long-run coverage for **any** data-generating process, with `|T⁻¹Σerr_t − α| ≤ (max{α₁, 1−α₁} + γ)/(Tγ)`. At T=90 days and γ=0.005 the per-episode coverage bound is loose — accept that per-episode coverage is approximate and **pool calibration across patients per procedure**. ~30 lines, no dependency. Warm-start from procedure-level pooled scores until the patient has ~20–30 days of their own stream. Skip Conformal PID unless coverage plots show systematic drift with day-since-surgery; the expected-recovery-curve model already removes most trend.

---

## 4.6 What not to build, and the exact volume that unlocks each

These are **standing policy**, written down so they are not relitigated. Put `MIN_ADJUDICATED_EVENTS_FOR_SUPERVISED_FIT = 100` in a single module, assert on it at **every** model-fitting entry point, enforce it in CI, and put the current adjudicated-event count on an internal dashboard so the gate is observable rather than remembered.

| Method | Verdict | Unlock condition |
|---|---|---|
| **Supervised risk prediction (any multivariable model)** | **REFUSE NOW** | Riley: at φ=0.05, C=0.75, p=6 parameters → max R²_CS=0.328, anticipated R²_CS=0.041 → **n=1,288 patients / 64 events / 10.7 EPP**. p=10 → 2,148. **p=3 → 661 / 33 events.** At φ=0.03, p=6 → **2,121**. Also demand MoE=0.01 on the overall risk (the default 0.05 is vacuous at low prevalence), which alone requires n=1,825. **A defensible target for any 6-parameter model at 5% prevalence is ~1,800–2,100 patients.** "10 EPV" is not conservative-but-safe, it is the wrong functional form — Riley's own examples range 4.84 to 23 EPP. |
| **Discrete-time pooled logistic hazard** | **THE eventual learned model — but not yet** | Person-day rows, restricted cubic spline baseline in post-op day, **composite index entered as ONE scalar covariate** (buys all six metrics for one degree of freedom), cluster-robust SEs on `patient_id`, horizons 7/14/30 all derived from one fitted daily hazard. Discretization is robust: Gensheimer got an identical C-index 0.66 across four schemes. Serves as a frozen numpy dot product. Unlock at **≥100 adjudicated events**. **Build the person-day feature table NOW** — the engine already computes everything; it just computes it transiently. |
| **Penalized regression as the rescue** | **REFUSE as a substitute for data** | Riley, J Clin Epidemiol 2021 (PMID 33307188): tuning parameters "are estimated with large uncertainty… most concern when development data sets have a small effective sample size and the model's Cox-Snell R² is low… **They perform worse when most needed.**" At n=300/15 events the CV lambda varies wildly and the calibration slope can land anywhere from 0.4 to 1.6. The answer is fewer parameters + informative priors, not a tuned penalty. When we do fit: **Firth-penalized logistic on 3 pre-specified clinician-chosen predictors**, profile-likelihood CIs (`wald=False`). Note `firthlogist` declares `requires-python >=3.8,<3.11` against our `>=3.12` — it will not resolve; use L2 logistic in Python or R `logistf` offline. |
| **GBTM / LCGA / growth mixture models** | **REFUSE below 200 subjects** | Published studies cluster at n=200–2,423. Enumeration recovers 2–3 classes reliably; **4+ classes are artifacts**. Gates: entropy ≥0.80, mean posterior assignment ≥0.7, min class ≥5%. Yang 2019 at n=107 supported only 2 classes. Omran 2025 at n=700 found a degenerate 95.4/4.6 split on PROMs — **if we cluster, cluster wearable streams, never PROMs.** Small-data substitute: **FPCA + 2–3 component GaussianMixture on the first 2–3 scores** (Yakdan, *Spine J* 2025, n=129 — poor pain-recovery cluster had a 23% vs 7% complication rate). Needs ≥50 patients with ≥21 days at ≥60% coverage. |
| **Balanced Random Forest / XGBoost / LightGBM** | **DELETE FROM THE ROADMAP** | Christodoulou 2019, 71 studies, median n=1,250, median EPV=8: in the 145 **low-risk-of-bias** comparisons the difference in logit(AUC) between ML and logistic regression was **0.00 (95% CI −0.18 to 0.18)**. The entire apparent ML advantage lived in the 137 high-risk-of-bias comparisons (+0.34). BRF with 500 trees at depth 6 admits up to 64 leaves per tree against 30 events — unbounded overfitting. It also cannot be served: a 500-tree pickle needs sklearn + scipy in the artifact (§4.7). Two independent post-surgical studies chose BRF (Ghomrawi, Hua) — and got **AUPRC 0.36 and 0.14** against AUROC 0.80/0.86, internally cross-validated at a single site, which is an *optimistic* ceiling. |
| **SMOTE / undersampling / oversampling / `class_weight='balanced'`** | **REFUSE, permanently** | van den Goorbergh, *JAMIA* 2022: calibration intercept moved from ~0.00 to **−1.32…−1.50** (case study) and to **≤ −4.5** at 1% event fraction; median AUROC of uncorrected models was **never lower**; decision curves showed **negative net benefit at thresholds ≥0.3**. "Outcome imbalance is not a problem in itself; imbalance correction may even worsen model performance." Corroborated by Carriero/van Calster/van Smeden, *Stat Med* 2025. **Shift the threshold instead.** Adding `imbalanced-learn` to `pyproject.toml` is the single clearest signal to a reviewing biostatistician that the team has not read the calibration literature. |
| **Deep survival (DeepSurv / DeepHit / pycox) & joint models** | **REFUSE, permanently at this scale** | pycox benchmarks run n=1,904 to 2.8M; even at n=9,105 (SUPPORT), nnet-survival scored C=0.732 vs 0.734 for plain Cox PH — **no gain at 10× our best case**. Joint models: with <~70 events convergence was low and bias persisted even in converged fits; no maintained Python implementation. `CoxTimeVaryingFitter` cannot predict survival for new subjects (lifelines' own docs) — it is an inference tool, not a rolling score. |
| **Wearable foundation models / SSL pretraining / LLM forecasters** | **REFUSE** | Modality mismatch is decisive: they are trained on raw accelerometry/PPG; we hold daily aggregates. No fine-tuning of any foundation model in year one. |
| **Per-patient HMM/HSMM** | **REFUSE below 300 completed recoveries** | K=4, d=6 Gaussian HMM has 16 + 24 + 84 = **124 free parameters against 90 daily observations**. Baum-Welch converges to a degenerate solution. Pooled with `covariance_type='diag'` cuts covariance parameters 84→24 and needs ~100+ patients. HSMM is the *right* model (phase durations are emphatically not geometric) but Python support is thin and unmaintained. |
| **Matrix profile / STUMPY on daily data** | **REFUSE until intraday lands** | m=7 over ~90 daily points leaves 84 subsequences, most consumed by the exclusion zone; discord scores are noise. Becomes genuinely informative at 1,440 points/day. Also numba/llvmlite: batch only, never Lambda. |
| **Isotonic calibration** | **REFUSE below 1,000 events** | Needs ~1,000+ calibration points; produces unstable step functions below that. Use **Platt** — 2-parameter at ≥100 events, **intercept-only recalibration-in-the-large at <100 events** (1 degree of freedom). `method='sigmoid'`, `cv=GroupKFold(groups=patient_id)`, never calibrated on training data. |
| **Any probability output at all** | **REFUSE until ≥100 adjudicated events** | Rename `risk_tier`/`risk_score` → `deviation_tier`/`deviation_index`; add `evidence_basis: 'rule_based_unvalidated'` to the API response. Add a lexical guard in the narrative post-processor, with a unit test, banning "likely / X% chance / high risk of infection." This is the boundary that plausibly keeps us inside FDA's non-device CDS carve-out (21st Century Cures §520(o)(1)(E), criterion 4 — the clinician can independently review the basis). **This is a monitoring instrument, not risk prediction.** |
| **LMS / GAMLSS growth-reference centiles** | **REFUSE permanently at our n** | Cole 2021: 7,000–25,000 subjects per sex. Python GAMLSS is immature (`scikit-normod`, `PyNM`, an in-progress port). ExpectileGAM is the production path (§4.4.4). |

**Effective sample size, stated once so it is never forgotten:** with ~90 rows per patient and within-patient ICC ρ≈0.3, the design effect is `1 + (90−1)·0.3 = 27.7`. **1,000 patient-days carry roughly the information of 36 independent observations.** Every number in this table is in **patients**, not patient-days. Consequences, enforced by a lint that fails if any evaluation code calls `train_test_split` or `KFold` without `groups`: bootstrap resamples **patients**; day-level models need GEE or mixed-effects; reporting "50,000 observations from 400 patients" in any material is misleading and PROBAST+AI-flaggable.

**Non-negotiable evaluation discipline when anything is eventually fit:** patient-level grouping in every split (`LeaveOneGroupOut`/`StratifiedGroupKFold` on `patient_id` — a random split of patient-days inflates AUC by 0.05–0.20); **Harrell enhanced bootstrap** optimism correction with the **full pipeline inside the loop** (variable selection, knot placement, penalty tuning, threshold choice — omitting any of these is the commonest source of optimism bias), B=500, resampling patients; report AUPRC with the prevalence baseline drawn, calibration slope and intercept, ICI/E50/E90, alerts per 100 patient-weeks and NNE — **AUROC strictly secondary**. Adjudication must be **blinded to the alert**; if the same nurse sees the tier and then records the infection, every estimate is circular and PROBAST+AI rates it high risk of bias in the outcome domain.

---

## 4.7 The serving contract

### 4.7.1 The rule

> **Models are FIT offline. They are EXPORTED as coefficient JSON. They are EVALUATED in Lambda as numpy dot products.**
>
> **The request-path artifact is numpy + pandas only. Forever.**

Write it into `CLAUDE.md` and enforce it in the build. `infra/build-lambda.sh` line 37 already excludes scipy (the comment calls it "the single largest wheel in the tree") and lines 43-46 grep-guard `app/` against importing it; line ~50 exits 1 above 250 MB unzipped. **Extend the guard:**

```bash
# infra/build-lambda.sh — the referee, not a code-review convention
BANNED='scipy|sklearn|scikit_learn|statsmodels|pymc|pytensor|numpyro|jax|torch|
lightgbm|xgboost|catboost|ruptures|stumpy|numba|llvmlite|tslearn|pygam|skfda|
imblearn|imbalanced_learn|mapie|crepes|arviz'
if grep -rnE "^\s*(import|from)\s+($BANNED)" backend/app/ ; then
  echo "FAIL: request-path artifact is numpy+pandas only. Fit offline, serve JSON."
  exit 1
fi
```

The first PR that adds `import statsmodels` to `app/engine/` would otherwise fail the deploy with a cryptic grep error; the "fix" (un-excluding scipy) costs ~90–110 MB unzipped for scipy plus ~40 MB sklearn plus ~25 MB statsmodels on aarch64, blowing the 250 MB limit or adding 3–6 s of cold-start import against a 30 s timeout. Someone will spend two days on this and then revert. Encode the rule instead.

### 4.7.2 What may and may not enter the deployment artifact

| May be served (numpy arithmetic on frozen JSON) | May **not** enter the artifact |
|---|---|
| PEB shrinkage `B_n`, `Ŷ`, `sqrt(1−B1·B_n)·σ_pop` — 10 lines | PyMC/PyTensor posteriors (needs a runtime C++ compiler + writable cache; a zip Lambda has neither) |
| Moderated variance, median/MAD/Huber scale — hand-rolled | NumPyro/JAX (jaxlib + scipy + pandas exceeds 250 MB; seconds of JIT per cold start) |
| Scalar Kalman local-level recursion, ~25 lines | statsmodels `UnobservedComponents.fit()` (0.2–1 s per metric per patient) |
| EWMA, CUSUM, streaming-median FSM | `GaussianProcessRegressor` (0.5–3 s per patient across 6 metrics with `n_restarts_optimizer=3`) |
| Conformal p-value: `(1 + #{A_i ≥ A_new})/(n_cal+1)` against a frozen calibration quantile vector | Any sklearn/BRF/LightGBM pickle (drags sklearn + scipy) |
| Expected-curve lookup table (day × stratum × centile) + linear interpolation | pyGAM `gridsearch` (fit-time only; the *fitted centiles* serialize to the lookup table) |
| Spline basis evaluation + dot product with frozen coefficients | `ruptures` PELT, `stumpy` FLOSS (batch analyst tools) |
| Platt (a, b) recalibration | TabPFN, torch, anything transformer-shaped |
| ACI `alpha_t` update — 30 lines | `online-fdr` (beta) |

### 4.7.3 The artifact format and lifecycle

```json
{
  "artifact_version": "engine_2026_08_r3",
  "created_at": "2026-08-14T03:12:00Z",
  "fit_commit": "a1b3c9d",
  "priors": { "resting_hr|TKA|65-74|F|obese":
              {"mu_pop": 66.2, "sigma_g2": 41.0, "sigma_i2": 23.1,
               "B1": 0.64, "lambda_bc": null, "rho_lag1": 0.48,
               "prior_source": "cohort_mixedlm", "n_patients": 34} },
  "curves":  { "TKA|female_bmi30plus": { "day": [0,1,...,90],
               "c10": [...], "c25": [...], "c50": [...], "c75": [...], "c90": [...],
               "se_c50": [...], "method": "pymc_mitscherlich_v1", "n_patients": 27 } },
  "conformal": { "TKA|d08-21": {"quantiles": [...], "n_cal_patients": 71,
                                "calibration_source": "external_lifesnaps_v1",
                                "alpha_supported": 0.05} },
  "composite": { "weights": {...}, "elicitation_provenance": {...},
                 "high": 2.41, "elevated": 1.36, "threshold_source": "lifesnaps_empirical_q" }
}
```

Versioned in S3, never mutated. Lambda loads it at cold start into module scope. Every `RiskAssessment` row stamps `artifact_version`, `engine_git_sha`, `config_version`, `prior_version`, `curve_version` and `input_snapshot_hash`. **Any alert must be re-derivable from those five strings alone** — that is a TRIPOD+AI requirement, and it is the thing that makes any future retrospective analysis possible at all.

### 4.7.4 Compute split and hard budgets

```
EventBridge Scheduler (nightly, 02:00 patient-local)
  → ScoringFunction   (Timeout 900, clone of the existing SeedFunction pattern,
                       infra/cloudformation.yaml:249-266)
     → writes RiskAssessment + alert_evidence + person_day_features rows
GET /worklist  → PURE READ.  Delete ensure_fresh_assessment() from the loop
                (api/worklist.py:34-56); drop date.today() from compute_input_hash
                (engine/pipeline.py:44).
```

**Enforce a hard per-patient request-path budget of 50 ms with a pytest benchmark that fails CI.** Anything exceeding it goes in the nightly job. Set batch/backfill **concurrency to 1** while the store is a whole-file SQLite database synced under a global S3 lock (`main.py:68-72`) — ten concurrent writers each download, mutate and re-upload the whole DB, last writer wins, and the other nine backfills vanish silently with no error. Write it into the Step Functions definition, not a comment.

Finally: **there is currently no scheduler anywhere in the infrastructure.** Every lead-time claim in the research ("3-day median lead", "4.4 ± 3.1 days") presupposes an alert that fires when data arrives. Today an alert exists only if a clinician opens a page, so measured lead time is bounded by browsing habits, not by the detector. Instrument **time-from-observation-timestamp to time-of-clinician-acknowledgement** as a first-class metric and report **that**. Do not quote any published lead-time figure in a clinical conversation until that metric exists.

---

## 4.8 Order of work

**Sprint 1 — plumbing and bug fixes. No new statistics.**
1. Nightly EventBridge → scoring Lambda; `/worklist` becomes a pure read; drop `date.today()` from the input hash. *(Nothing else is safe until this lands.)*
2. Outcomes + follow-up schema (`outcome_event`, `follow_up.last_known_contact`, `follow_up_complete`); stamp `engine_git_sha`/`config_version`/`prior_version` on every `RiskAssessment`. **Days of work, multi-year lead time, highest priority on the list — conformal calibration depends on it because "uneventful" is a negative label.**
3. P1 (delete the post-op baseline fallback), P2 (`MIN_PREOP_DAYS=7`), P3 (daily-grid reindex, day-indexed CUSUM window), P5 (sever `app.seed → app.engine`, regenerate with Mitscherlich + AR(1) + MNAR gaps), P6 (`deleted_at`, `local_date`).
4. Extend the `build-lambda.sh` guard to the full banned list.
5. Device metadata: `device_model`, `firmware_version`, `metric_source`, patient IANA timezone; `surgical_event` table so a contralateral procedure resets `postop_day` and forces re-baselining. **Treat a vendor change as baseline INVALIDATION** — restart in population-prior mode, 14-day low-confidence period, `DEVICE_CHANGED` reason code. Firmware-only changes get 3-day suppression; vendor changes do not. Never compare HRV, skin temp or SpO2 across vendors at all.

**Sprint 2 — the baseline layer.** PEB + moderated variance + robust median centre + device-resolution floors + prior table + `baseline_confidence` in the API. P4 (metric variants + weight renormalization + minimum-metrics gate). Coverage-collapse detector; raise the confidence gate to 5-of-7; `WEAR_TIME_MINUTES` consulted.

**Sprint 3 — the episode arbiter.** State machine, hysteresis, snooze, ack, action log. The CI budget test replaying LifeSnaps + PMData + the synthetic uneventful cohort. **This is the largest available reduction in effective multiplicity and it must precede any second detector.**

**Sprint 4 — detectors.** Kalman innovations replacing raw z (with the Ljung-Box gate), AR(1)-inflated limits, the ARL0 surface over φ, the renamed streaming-median RHR detector (only if intraday HR + per-minute steps are confirmed per connector). Transforms + threshold recalibration + regenerated golden tiers, in one commit.

**Sprint 5 — trajectory.** Ratio-to-own-pre-op scale, day-varying functional SD, versioned curve artifact, `2·SE_curve` suppression, no-flags-before-day-7. Fit the Mitscherlich hierarchical model offline the moment any procedure reaches 20–30 patients.

**Then, gated:** conformal at α=0.05 on external calibration (now, labelled as external) → conformal on our own cohort (≥19 uneventful adjudicated patients) → per-procedure ExpectileGAM centiles (100–150 patients/procedure) → discrete-time pooled logistic hazard (**≥100 adjudicated events**).

**Every engine version — including parameter-only changes to EWMA L, CUSUM h, or the composite weights — ships in shadow mode first**, with pre-registered promotion criteria: ≥90 days, ≥30 completed episodes, ≥5 high-tier events, alert burden within budget, and clinician case-by-case review of the disagreements against the current path. The Kwong hydronephrosis precedent — AUROC 0.90 retrospective collapsing to 0.50 prospective — is the motivating example, and it applies directly to our device mix and firmware risk.