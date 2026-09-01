# Section 12 — Completeness Review: What the Corpus and the Plan Are Missing

*Scope: this section does not design a layer. It names what 49 research agents and the current plan did not address, ranked by how likely each is to decide whether the product works. Every gap below was checked against the corpus by grep and by reading; where the corpus does contain the material but nobody assembled it into a decision, that is stated.*

---

## Severity 1 — The pre-operative window is the product's single point of failure and nobody sized it

**The gap.** `grep -ril "preoperative window\|pre-op wear\|14 days before"` across the corpus returns **zero files**. The entire engine rests on a personal pre-op baseline (`engine/baseline.py`), and four independent product functions all draw on the same pre-op capture:

| Function | Pre-op requirement | Source |
|---|---|---|
| EWMA/CUSUM z-scores | ≥7 valid pre-op days (n=3 gives SD sampling SD ≈ 0.52 of σ; P(s < 0.5σ) ≈ 0.16 — 1 patient in 6 gets a baseline SD under half the truth) | methods critique |
| Trajectory class membership | Pre-op step count dominates (Olanrewaju); ratio-to-own-pre-op beats ratio-to-cohort-curve | methods critique, "Endorsed" |
| MCID prediction / PROM state | Baseline PROM is the dominant feature in every model (c 0.70–0.77); higher pre-op KOOS JR predicts *failure* to reach MCID | risk-prediction file |
| CMS PRO-PM compliance | HOOS JR/KOOS JR within **0–90 days before** surgery, on ≥50% of eligible patients, or the FY2028 IQR annual payment update is at risk | PROMs file |

Nobody asked the operational question: **how many days of pre-op wear can you actually get?** With TKA off the inpatient-only list since Jan 2018 and inpatient TKA volume down 85.4%, a growing share of patients are ASC same-day-discharge cases scheduled on short notice. If the median enrollment-to-surgery interval is 5 days, the ≥7-day gate fails for most of the panel and the engine falls back to — currently — post-op days 2–4, when RHR is elevated 10–15 bpm. That fallback makes the engine read *genuine sustained deterioration as z≈0 (on track)* and *normal recovery as negative deviation on a metric whose adverse direction is up.* It will reassure.

**Ship NOW.**
1. Delete the post-op days 2–4 fallback in `baseline.py`. Replace with a population prior for the `(procedure, age_band, sex)` stratum, `baseline_confidence = 0.0`, surfaced in the API as a typed code `INSUFFICIENT_BASELINE`.
2. Hard gate: refuse to emit a numeric deviation below 7 valid pre-op days for that metric.
3. Add an `enrollment` table and instrument the funnel as a first-class business metric:

```sql
CREATE TABLE enrollment (
  patient_id            TEXT PRIMARY KEY,
  enrolled_at           TIMESTAMP NOT NULL,
  scheduled_surgery_date DATE NOT NULL,
  target_preop_days     INTEGER NOT NULL DEFAULT 14,
  actual_preop_days_by_metric JSON,   -- {"RESTING_HR": 11, "HRV_SDNN": 4, ...}
  baseline_mode         TEXT CHECK (baseline_mode IN ('PERSONAL','BORROWED_PRIOR')),
  preop_prom_captured   BOOLEAN NOT NULL DEFAULT 0,   -- CMS PRO-PM window
  device_provisioned_at TIMESTAMP
);
```

**RESEARCH (2 weeks, no patients needed).** Ask three partner practices for the distribution of `surgery_scheduled_date → surgery_date` intervals for TKA/THA/ACLR over the last 12 months, stratified by inpatient vs ASC. That single number decides whether the personal-baseline architecture is viable or whether the product must ship in borrowed-prior mode by default.

---

## Severity 2 — The physical therapist is the missing user, the missing data stream, and the missing distribution channel

**The gap.** `grep -ril "Medbridge"` → **0 files**. `"home exercise"` → **1 file**, and only as a cost line. The corpus contains exactly one relevant sentence — that RTM data review is done by "Care Navigators — licensed physical therapist assistants" and that 98980/98981 are billable by PTs/OTs as non-E/M practitioners — and then nobody followed it anywhere.

**Why it matters, concretely.**
- **83% of the >$2,500 of 90-day post-TKA Medicare outpatient spend is physical therapy.** That is the money the buyer cares about and the PT is the person spending it.
- **The PT sees the patient 2–3×/week and holds a goniometer.** TracPatch (n=435, two 9-DOF IMUs) captured steps for all 435 patients but usable flexion/extension ROM to 6 weeks in only **186/435 (42.8%)**. Passive ROM capture loses more than half the cohort. Yet ROM is the metric with the hardest, most surgeon-credible trigger in all of orthopedics: **flexion <90° at 6 weeks post-TKA → MUA evaluation**, 4.3–4.6% incidence, best outcomes if performed <12 weeks, revision-for-stiffness costs $65,771 vs $48,287 non-stiff. The signal that carries the clearest dollar value cannot be obtained from the wrist. It can be obtained from a PT in eight seconds.
- **The PT knows first.** Sling-weaning retear after rotator cuff repair peaks between week 6 and month 3 and its signature is "loss of previously-gained ACTIVE elevation with preserved PASSIVE ROM" — a distinction only a hands-on examiner can make.
- `engine/adherence.py` reads a private `AdherenceRecord` table that is connected to no actual treating therapist. The product currently claims to monitor therapy adherence while having no relationship with the person delivering the therapy.

**Ship NOW.** A magic-link, no-login, 60-second PT web form (`POST /pt-checkin/{token}`) writing to a new table. Do not attempt EHR federation for this.

```sql
CREATE TABLE clinic_measurement (
  id SERIAL PRIMARY KEY,
  patient_id TEXT NOT NULL,
  measured_on DATE NOT NULL,
  measured_by_npi TEXT,
  acquisition_channel TEXT NOT NULL
      CHECK (acquisition_channel IN ('CLINIC_VISIT','GUIDED_IN_APP','PASSIVE_WEARABLE')),
  knee_flexion_deg NUMERIC,       -- MUA gate: <90 at wk6
  knee_extension_deg NUMERIC,     -- ACLR gate: must reach 0 by wk4-6
  active_elevation_deg NUMERIC,   -- RCR retear gate wk6-12
  passive_elevation_deg NUMERIC,
  extension_lag_deg NUMERIC,      -- >5-10 deg = quad inhibition
  hep_completion TEXT CHECK (hep_completion IN ('none','partial','full','unknown')),
  sessions_attended INT, sessions_scheduled INT,
  pt_concern_free_text TEXT,
  protocol_version TEXT NOT NULL
);
```

Then: **the ROM alarm must project, not report.** Alert at week 3–4 on *projected* failure to cross 90° by week 6, using a two-point linear extrapolation on clinic-measured flexion, because MUA outcomes degrade after 12 weeks and intensified physio at week 4 can still change the result. Reporting <90° at week 6 is reporting the diagnosis, not the warning.

**RESEARCH.** Nobody has established whether WebPT, Raintree, Prompt, or MedBridge expose HEP-completion or flowsheet APIs, or what a partner PT group's data-sharing posture is. This is the highest-leverage unresearched integration in the plan — larger than Epic, because ModMed/Epic give you the operative note once and the PT gives you the trajectory weekly.

---

## Severity 3 — Nobody designed for the second surgery

**The gap.** `"bilateral"` appears in 4 files, all incidental (CMS eligibility text; a Fitbit worn on both wrists). `"contralateral"` appears in 3, and only the methods critique names it as a hole. `"staged"` appears twice. There is no design anywhere for a patient who has a second operation.

**Why it matters.** Three distinct cases, all common, all currently catastrophic:

1. **Staged contralateral.** Patient has the other knee done at week 8. `engine/dataload.py` computes `postop_day = start_time.date() - surgery_date` from a single `surgery_date`. The engine therefore sees, on post-op day 56, a step-count collapse and an RHR rise of exactly the magnitude and shape it expects on post-op day 2 — and calls it HIGH. Or worse, the clinician learns that trajectory codes mean nothing and generalizes.
2. **Simultaneous bilateral TKA.** There is **no published week-by-week step or gait curve for bilateral arthroplasty anywhere in the corpus.** Applying the unilateral TKA curve (wk1 ≈1,439 → wk6 ≈4,781 → wk20 ≈6,344 steps/day) to a bilateral patient labels every one of them BEHIND, permanently.
3. **Revision.** PJI incidence by 1 year: primary THA 0.94%, primary TKA 1.05%, **revision THA 4.39%, revision TKA 5.33%** — a 4–5× prior. And 53.78% of revision-TKA PJIs declare by day 90, vs 74.12% for revision THA. Revision patients need a different prior, a different horizon, and exclusion from the PRO-PM cohort (CMS excludes revisions, fractures, malignancy, partial procedures, *and staged procedures*).

**Ship NOW.**

```sql
CREATE TABLE surgical_event (
  id SERIAL PRIMARY KEY,
  patient_id TEXT NOT NULL,
  event_date DATE NOT NULL,
  cpt_code TEXT NOT NULL,           -- 27447 TKA, 27130 THA, 29888 ACLR, 29827 RCR
  laterality TEXT NOT NULL CHECK (laterality IN ('LEFT','RIGHT','BILATERAL')),
  is_revision BOOLEAN NOT NULL DEFAULT 0,
  revision_of_event_id INT REFERENCES surgical_event(id),
  approach TEXT,                    -- posterior/DA/lateral: drives dislocation prior
  tear_size_cm NUMERIC,             -- RCR: >3cm shifts phase gates 4-8 weeks
  UNIQUE (patient_id, event_date, laterality)
);
```

`postop_day` becomes a function of `MAX(event_date)`. On insert of a second event: invalidate the baseline, restart in borrowed-prior mode, mark 14 days low-confidence, emit `SECOND_PROCEDURE_REBASELINE`, and set the PJI prior from the revision table above.

**REFUSE.** Do not synthesize an expected-recovery curve for BILATERAL or for revision procedures. There is no published curve. Return `TRAJECTORY_UNAVAILABLE_NO_REFERENCE_CURVE` and show the raw series only. Inventing a curve here is exactly the unfalsifiability problem the gap list already flags for `curves.py` (G6), except with no literature to point at at all.

---

## Severity 4 — The patient's own words are probably the strongest signal, and the architecture treats them as a garnish

**The gap.** This one is half-present in the corpus and completely absent from the plan.

The single strongest quantified remote predictor in the entire 49-agent corpus is **patient-reported wound drainage** (n=1,019 multicentre telemonitoring cohort, 5-point scale, daily for 30 days):

| Rule | Performance |
|---|---|
| Any drainage in post-op **week 2** | sens 88% / spec 88% |
| Moderate-to-heavy drainage **week 3** | OR 103.23 (26.08–408.57), **PPV 83%** |
| New-onset drainage appearing week 2 | OR 80.71 (9.12–714.52) |
| Cumulative >5 drainage days, weeks 1–3 | sens 63% / spec 87% |
| **No drainage across all 30 days** | **NPV >98%** (1 PJI in 467) |

Compare the best vital-sign figure anywhere in the corpus: **median 14 hours** of lead time for continuous HR+temperature telemetry (single 2023 feasibility study, rated *weak*), and 7–11 hours in a prospective wearable cohort. **Days versus hours.** And the corpus's own conclusion is blunt: "Days-scale lead time comes from wound reports and activity trajectories, not vitals."

Meanwhile, `models/enums.py` defines `PAIN_NRS`, `RANGE_OF_MOTION`, `THERAPY_ADHERENCE`, `EXERCISE_REPS`, `PROM_SCORE` — and grep confirms **none of them is referenced anywhere outside `enums.py`.** The composite index puts 100% of its weight on physiologic channels while the product bills RTM codes that CMS defines as monitoring *non-physiologic* data.

**The adjudication the corpus asked for and did not make.** The complication-surveillance file ends with the open question: *"whether the composite deviation index should include the patient-reported wound channel at all, or whether wound findings should drive a SEPARATE, higher-precedence infection pathway."*

**Adjudicated: separate, higher-precedence pathway. Never inside the composite.** The arithmetic is decisive. Inside `composite.py`, a wound term would carry ~0.15 weight; a clipped one-sided z of 3.0 contributes 0.45, which is 38% of the ELEVATED threshold (1.2) and 22% of HIGH (2.0). You would need three other correlated channels to co-fire before an OR-103, PPV-83% observation could raise a tier. That converts a standalone rule with the best PPV in the literature into a subordinate clause. Wound drainage sets the tier directly.

**The architectural consequence nobody wrote down.** If text is the primary instrument, four things invert, and no one in 49 reports said so:

1. **The primary ingest path is the check-in, not the wearable webhook.** The webhook becomes the confirmatory channel.
2. **The coverage/confidence gate must be text-first.** Today `confidence.py` scores "≥3 of 6 *metrics* present." A patient with a perfect Apple Watch stream and no check-in for 5 days should read as LOW confidence, not HIGH coverage.
3. **EWMA/CUSUM demote from engine to corroborator.** They earn their place by adding specificity to a wound/pain flag, not by originating tiers.
4. **RTM billing stops being a substance-over-form problem.** The engine finally computes the non-physiologic data the 9897x family is defined around.

**Ship NOW.** Week-conditional wound rules as a precedence-0 pathway that bypasses the composite entirely:

```python
# engine/wound.py — precedence 0, evaluated before composite
DRAINAGE = {"none": 0, "minimal": 1, "mild": 2, "moderate": 3, "heavy": 4}

def wound_pathway(series, postop_day):
    """series: {postop_day: drainage_ordinal}. Returns typed codes, not a z-score."""
    wk = lambda lo, hi: [v for d, v in series.items() if lo <= d <= hi]
    codes = []
    w2, w3 = wk(8, 14), wk(15, 21)
    if w3 and max(w3) >= DRAINAGE["moderate"]:
        codes.append(("WOUND_DRAINAGE_MODHEAVY_WK3", "HIGH", {"or": 103.23, "ppv": 0.83}))
    elif w2 and max(w2) >= DRAINAGE["moderate"]:
        codes.append(("WOUND_DRAINAGE_MODHEAVY_WK2", "HIGH", {"or": 51.22}))
    elif w2 and max(w2) >= DRAINAGE["minimal"] and not any(v >= 1 for v in wk(0, 7)):
        codes.append(("WOUND_DRAINAGE_NEW_ONSET_WK2", "HIGH", {"or": 80.71}))
    elif w2 and max(w2) >= DRAINAGE["minimal"]:
        codes.append(("WOUND_DRAINAGE_ANY_WK2", "MEDIUM", {"sens": 0.88, "spec": 0.88}))
    if sum(1 for d, v in series.items() if 0 <= d <= 21 and v >= 1) > 5:
        codes.append(("WOUND_DRAINAGE_CUMULATIVE_GT5D", "MEDIUM", {"sens": 0.63, "spec": 0.87}))
    # NPV >98% (1 of 467): absence actively lowers infection concern. Report it.
    if postop_day >= 30 and all(v == 0 for v in series.values()) and len(series) >= 21:
        codes.append(("WOUND_CLEAN_30D", "REASSURING", {"npv": 0.98}))
    return codes
```

Every reason code carries its **interval-specific PPV** in the payload and it renders in the UI. That is the anti-Epic-Sepsis-Model discipline: the corpus's canonical failure was AUC 0.63, sensitivity 33%, PPV 12%, alerts on 18% of all hospitalizations, and it shipped without publishing an operating point.

**REFUSE.** Do not build an autonomous wound-photo SSI classifier. Photo-only telemedicine SSI detection pools at **sensitivity 63.9%** (95% CI 30.4–87.8) versus 87.8% for full telemedicine with a symptom questionnaire. The best published app (RedScar, NCT05485233) reports 100% sensitivity on **5 infections in 41 patients**, Android-only, with **42.9% of patients hitting upload failures** and no Fitzpatrick skin-tone stratification on a red-pixel-proportion feature. Capture the photo, fuse it with the questionnaire, route to a human, and never emit "looks fine."

---

## Severity 5 — Disengagement: the corpus is right about the mechanism, wrong about the remedy, and silent on the confounders

**Adjudication first, because the corpus contains a verified error.** `methods--CRITIQUES.md` asserts that `TIER_ORDER` "ranks [MISSING_DATA] at position 2, BELOW both HIGH and MEDIUM" and lists "change TIER_ORDER so MISSING_DATA never sorts below LOW" in its **Must change** list. Verified from source: `TIER_ORDER = {HIGH:0, MEDIUM:1, MISSING_DATA:2, LOW:3}` — MISSING_DATA **already** outranks LOW. The critique's headline remedy is already shipped. Do not schedule that work; do not repeat the claim to a clinician.

**The corpus also contradicts itself and never resolves it.** One report says non-wear must "suppress the SCORE, never the ALERT"; another says non-wear must be a covariate that RAISES risk. **Adjudicated: both, at different layers.** The confidence gate suppresses the *reassuring statement* (a UI invariant: LOW confidence renders as "we cannot see this patient," never as "Stable"). The hazard/composite layer takes `coverage_7d`, `coverage_slope`, and `days_since_last_sync` as *features that can raise risk*. These are not in conflict; they are different functions.

**The real gap: three causes of a coverage drop with opposite meanings, and nobody separated them.**

| Cause | Evidence | Correct response |
|---|---|---|
| **Expected decay** | Shoulder-surgery cohort: device compliance 84% at surgery → 46% (RCR) / 52% (TSA) at week 6, ≈5–6 points/week | Baseline. Must not alert. |
| **Structural non-signal** | US Apple Watch SpO2 disabled 2024-01-18 → 2025-08-14; Apple Mobility metrics absent during stairs/running/Wheelchair mode; walker gait suppresses steps −36.4%; `confidence.py` `KEY_METRICS` includes SPO2 and SKIN_TEMP that several providers never supply | Distinct code (`SPO2_UNAVAILABLE_REGULATORY`), renormalize, never penalize the patient |
| **Informative censoring** | "A post-op patient with a developing infection is exactly the patient who stops charging their watch" | The alert |

A naive `COVERAGE_COLLAPSE` rule fires on causes 1 and 2 constantly, gets muted within a month, and takes cause 3 with it. That is how alert fatigue becomes structural.

**Ship NOW — coverage *residual*, not coverage level:**

```python
# engine/confidence.py
def expected_coverage(postop_week: int) -> float:
    """Wear-decay prior, seeded from the shoulder cohort (84% -> 46-52% by wk6)."""
    return min(0.95, max(0.35, 0.86 - 0.055 * postop_week))

def coverage_collapse(obs_7d, prior_7d, postop_week, structural_causes):
    if structural_causes:                     # SpO2 regulatory gap, walker, device swap
        return None
    exp_now  = expected_coverage(postop_week)
    exp_prev = expected_coverage(max(0, postop_week - 1))
    if prior_7d >= exp_prev - 0.10 and obs_7d < exp_now - 0.25:
        return "COVERAGE_COLLAPSE"            # rank at MEDIUM or above
    return None
```

Escalate the ladder: coverage collapse **plus** a missed check-in is a materially stronger signal than either. Passive streams have <1% missing daily recordings while weekly PROMs average 16.2% missing and thrice-daily exercise tasks run 32.3% compliance — so simultaneous failure of a passive and an active channel is not coincidence.

**RESEARCH.** No TKA/THA-specific wear-decay curve exists in the corpus (explicitly noted: "Ghomrawi's Fitbit work ... was not retrieved"). Measure it on your own first 50 patients before hard-coding those coefficients; the shoulder curve is a proxy, not a fact about your cohort.

---

## Severity 6 — Nobody wrote the 30-second surgeon artifact, and the constraint numbers say it is the whole product

**The gap.** The corpus has every constraint and no specification.

- Median **direct surgeon–patient time: 7 min 52 s** per encounter (15 surgeons, 1,248 encounters), at 30–50 patients/day.
- Specialists already process **29.1 EHR notifications/day**; PCPs 76.9.
- Clinicians override **49–96%** of interruptive alerts; CPOE alert PPVs "usually below 20% and as low as 5%."
- Surgeons abandon systems that are "five clicks deep" or "onerous to access during clinic visit."
- 72–99% of continuous physiologic monitor alarms are false or non-actionable.

Not one of the 49 reports specifies the artifact. "Surgeon-facing output should be a single glance" is an aspiration, not a contract.

**Ship NOW — a literal contract, and a budget enforced in CI.**

```json
{
  "patient": "R. M.", "postop_day": 13, "procedure": "TKA-L",
  "tier": "HIGH",
  "reasons": [
    {"code":"WOUND_DRAINAGE_MODHEAVY_WK2","raw":"moderate, 4 of last 5 days","ppv":0.83},
    {"code":"RHR_EWMA_2CONSEC","raw":"71 bpm vs baseline 58 (+13)","ppv":null},
    {"code":"STEPS_BELOW_EXPECTED","raw":"640/d vs 1,900 expected wk2","ppv":null}
  ],
  "data_as_of": "2026-07-31T04:12Z",
  "coverage_7d": 0.71,
  "not_watched": ["no wound photo since d7", "SpO2 unavailable (device)"],
  "episode_days_remaining": 17,
  "basis": "expert_weighted_v3", "calibrated": false, "horizon_days": 14
}
```

Three non-negotiables the corpus implies but never states: **(a)** every reason code renders with its **raw value and unit** — surgeons distrust unadjusted, un-shown numbers; **(b)** worklist ordering is driven **exclusively** by the deterministic tier, never by any property of LLM text; **(c)** a hard budget of **≤3 surgeon-facing items per clinic day**, enforced by a pytest that replays LifeSnaps (n=71, Fitbit Sense, DOI 10.5281/zenodo.6826244) and PMData (n=16) — ~9,000 person-days where every alert is false by construction — and fails the build if exceeded. The budget then constrains the parameters, instead of the parameters silently contradicting the budget.

**RESEARCH (one afternoon, highest ROI in the plan).** Nobody asked a surgeon to rank the reason codes. Run a card-sort with ≥2 surgeons over the ~20 typed codes: (i) would you act on this today, (ii) rank them. That elicitation is the *only* defensible provenance for the composite weight vector, and the methods critique already says weights must be "explicitly elicited from ≥2 surgeons and documented as elicited." Right now RHR .25 / temp .25 / HRV .20 / RR .15 / steps .15 has no author.

---

## Severity 7 — There is no negative scope statement: nobody wrote down what the product does not watch

**The gap.** `grep -ril "not monitored\|does not monitor\|scope of monitoring"` returns hits only in the SMS-disclaimer context. Across 49 reports there is no artifact enumerating what the product is blind to — and the blindness list is long, specific, and entirely derivable from the corpus:

- **Mechanical events have no prodrome.** THA dislocation: 91% within 6 weeks (posterior approach); 75% of direct-anterior first dislocations in the first 3 weeks. "An acute mechanical event with no physiologic prodrome." Periprosthetic fracture: same. Running EWMA over these "is a category error and will always fire late."
- **PE.** Median POD 3 (IQR 2–7). **80% of CT-confirmed PE after TKA was asymptomatic.** SpO2 is a screening trigger whose source study reported no sensitivity, specificity, or AUC.
- **Infection after day 90.** Only **57.67%** of primary TKA PJIs are diagnosed by day 90; ~42% declare between day 91 and 365.
- **CRP.** Proven non-discriminative POD 0–6.
- **SpO2 at all** on US Apple Watches sold 2024-01-18 through 2025-08-14.
- **Anything at night**, if check-in cadence honors 8am–9pm TCPA quiet hours.
- **Falls, medication errors, DVT in the non-operative leg**, and everything that happens while the watch is on the charger.

Against this: **~90% of TJA patients report "peace of mind" from continuous tracking**, and the dominant theme in Mayo's qualitative interviews was reassurance that "the data collected were being reviewed" — i.e. **patients assume a human is watching.** An undocumented blindness list plus a documented patient belief in continuous human surveillance is the exhibit in the first lawsuit.

**Ship NOW.** A machine-readable manifest, versioned with the engine SHA, rendered into three surfaces (patient consent, console footer, per-worklist-row `not_watched` field):

```yaml
# config/coverage_manifest.yaml — engine_version: 3.2.0
watched:
  - id: INFECTION_TREND
    channels: [wound_drainage_selfreport, resting_hr, skin_temp]
    window_days: {TKA: 365, THA: 180, ACLR: 90}
    evidence: "wound drainage wk2 sens 0.88/spec 0.88; vitals lead time hours not days"
not_watched:
  - id: DISLOCATION
    reason: "Acute mechanical event, no physiologic prodrome. 91% of posterior-approach
             dislocations occur within 6 weeks and are not detectable by trend."
    patient_instruction: "If you hear a pop or cannot bear weight, call the practice now."
  - id: PULMONARY_EMBOLISM
    reason: "80% of post-TKA PE is asymptomatic; consumer SpO2 MAE 2.2-5.8% with
             11-31% failed reads. Screening-grade only."
  - id: OVERNIGHT
    reason: "Check-ins are sent 09:00-10:00 local. This line is not monitored at night."
```

---

## Severity 8 — The seed data masks four real-world failures; only one was caught

The corpus caught the circularity (`app/seed/generators.py:20` imports `curve_mid` from the engine; `curves.py` admits "on track is on track by construction"). The independent gap list caught the Apple metric-variant masking (G1). **Four more are unaddressed, and each is invisible in the demo and fatal in the field:**

1. **No assistive-device period.** Real week-1 TKA patients push a walker. Apple Watch Series 8 undercounts steps **−36.4%** during a 6MWT with a rolling walker; Fitbit at the wrist shows **31.2% error** with a two-wheeled walker vs 1.5% at hip/ankle. A cane is nearly harmless (−1.9%). The day the walker is dropped, wrist step count jumps 35–50% from *pure artifact* — and `curves.py` will fit a phantom recovery inflection to it. The seed emits smooth logistic recovery.
2. **No autocorrelation.** Daily RHR/HRV/sleep carry lag-1 φ ≈ 0.4–0.7. At φ=0.5, λ=0.3, EWMA variance inflates by (1+φ(1−λ))/(1−φ(1−λ)) ≈ 2.08 → true SD ≈1.44× assumed → the nominal 2.66σ limit operates at ~1.85σ. ARL0 plausibly falls from ~780 to 80–150 days. The 2-consecutive-day rule is the worst casualty, because serial correlation is exactly what makes consecutive exceedances co-occur.
3. **No non-wear gaps.** `deviation.py` iterates a Series indexed by post-op day without reindexing to a complete daily grid. A Mon/Thu wearer gets an effective per-calendar-day smoothing constant near 1−(1−0.3)^(1/3) — the filter runs ~3× too fast. And `z.iloc[-CUSUM_WINDOW:]` takes the last 14 *observations*, not 14 days. Alert probability becomes a function of wear adherence, in the wrong direction, on exactly the patients most likely to be sick.
4. **No device change, no timezone, no second surgery, no quitter.**

**Ship NOW, in this order (one sprint):**
1. CI test that hard-fails on any import edge `app.seed → app.engine` (AST walk over `app/seed/`).
2. Rewrite the generator with a **different functional form** than the engine's logistic — Mitscherlich `r(d) = A(1 − exp(−k(d − t₀)))`, with A, k, t₀ drawn per patient from literature-anchored distributions (week-1 median ~360 steps, week-6 ~3,739, only ~1 in 3 exceeding pre-op by week 6) — so misspecification exists **by construction**, as in production.
3. Add per-patient AR(1) φ ~ U(0.3, 0.7) per metric; MCAR + MNAR non-wear gaps; an assistive-device timeline applying a ×0.64 step multiplier while `walker`; one contralateral-surgery patient; one device-swap patient; one quitter.
4. Replay LifeSnaps + PMData. **Zero cost, zero patients, no IRB.** Move every specificity/ARL/threshold calibration off seed data onto these cohorts, bootstrapping per-participant.

---

## Severity 9 — Business failure modes: nobody modeled why a practice cancels or a patient uninstalls

The corpus's economics is entirely revenue-side: ~$345–427 direct RTM billing per Medicare TJA patient over 90 days; ~$170–210k/yr gross for a 500-TJA practice. The cost side and the churn side are **absent**. `grep` returns **0 files** for `BYOD`, `loaner`, `device cost`, `who pays`.

**Missing 1 — the labor math.** 98980 requires **at least one real-time synchronous audio interaction per calendar month per patient**; an SMS thread does not qualify. At 500 active patients that is 500 calls/month ≈ 167 hours ≈ **1.0 FTE navigator before a single alert is reviewed.** The corpus explicitly concedes "Published staffing ratios (patients per navigator/nurse FTE for ortho RPM) were not found." Gross margin survives one navigator; it does not survive two. **Therefore alert volume is not an annoyance metric, it is the P&L.** Every extra 30 alerts/day is a hiring decision.

**Missing 2 — the coinsurance.** Standard Part B 20% coinsurance applies to every RTM code: **~$8–11/month billed to a 66-year-old who may not remember consenting.** That is the single most predictable source of patient complaints routed to the surgeon's front desk, and one angry call to the surgeon ends the pilot. It appears once in the corpus as a compliance footnote and never as a churn mechanism. Build the disclosure into enrollment and log its acknowledgment.

**Missing 3 — the device.** Pew: **61–65% smartphone ownership at 65+, with an 81% vs 27% ownership gradient by income.** Median TJA age ≈66. The corpus frames this as equity; it is also unit economics. Supply watches and you carry $250–400 CapEx per patient against ~$400 of billing plus reverse logistics; don't, and you exclude ~35–40% of the panel and bias the analytics cohort young/affluent (the Mayo RPM cohort was 93.3% White, mean age 56.3). Neither branch was costed.

**Missing 4 — you may be competing on the wrong axis.** mymobility's actual commercial win was **substitution economics** — patients needing ≥1 outpatient PT visit 60.6% vs 94.6% (p<0.001) — with 1-year KOOS JR *equivalent* (84.1 vs 83.8, p=0.88) and readmissions non-significant. The definitive readmission RCT (n=4,736) is **null** (RR 1.02). Nobody has demonstrated earlier complication detection from consumer wearables. If your ROI story is detection, you are selling the thing no vendor has ever proven.

**Ship NOW.** `time_log` and `interactive_communication` tables (they are simultaneously billing evidence, the medico-legal "data was reviewed" record, and the ops metric), plus a per-practice dashboard with the three churn leading indicators the corpus implies: **median alert-acknowledgment latency**, **alerts per navigator per day**, **patient opt-out rate**. The 2026 alert-fatigue systematic review's recommended operational definition — "sustained decrease in appropriate alert response rate from an established baseline" — is your SLO, and a breach should **auto-tighten thresholds**, not page an engineer.

---

## Severity 10 — Four clocks that disagree, and nobody arbitrated

| Clock | Boundary | Consequence of ignoring |
|---|---|---|
| CMS **TEAM** episode (mandatory, live 2026-01-01, ~700–741 hospitals) | 30 days post-discharge | The buyer's money stops at day 30 |
| CMS **RSCR / NQF #1550** | 7d AMI/pneumonia/sepsis · 30d bleed/PE/death · 90d mechanical + PJI | Alerts outside these windows are illegible to quality staff |
| **PJI biology** | Only 57.67% of primary TKA PJIs by day 90 | Stopping at 90 days misses ~42% of TKA infections |
| **RTM billing** | 30-day supply periods, calendar-month management | Revenue stops ≈ month 3 |
| **PRO-PM** | Post-op capture 300–425 days | You must touch the patient again at ~1 year regardless |

**Adjudicated three-mode design:**
- **Days 0–42, full intensity.** Daily check-in, all detectors, wound channel at maximum weight. This is where TEAM dollars, PE (POD 2–7), dislocation (91% within 6 weeks), delirium (POD 1–3), and MUA runway (alert wk 3–4 for the wk-6 gate) all live.
- **Days 43–90, tapered.** 3×/week to weekly. Covers 90-day RSCR windows and the tail of RTM billing.
- **Days 91–365, TAIL mode (TKA and revision only).** One monthly wound question + one PROM push. Near-zero marginal cost, and it is funded by the PRO-PM capture you must perform at 300–425 days anyway. Give TAIL its own confidence semantics: it is *not* monitoring, it is a scheduled question, and the coverage manifest must say so.

Store the horizon on every tier: `{"tier":"elevated","horizon_days":14,"basis":"expert_weighted_v3","calibrated":false}`. Shipping `calibrated: false` is not a weakness — it is what lets you later ship `calibrated: true` without breaking clients or overclaiming today.

---

## Severity 11 — The engine has no concept of "the surgeon's own protocol," and orthopedics is protocol-heterogeneous

`grep` returns **0 files** for `surgeon variation` and `surgeon preference`. Yet the corpus is full of evidence that protocols legitimately and defensibly differ:

- **THA hip precautions do not reduce dislocation** — 2.2% with vs 2.0% without across 6,900 posterior-approach patients — so precautions are surgeon preference, not standard of care.
- **VTE prophylaxis is actively contested**: EPCAT II (n=3,424) found aspirin 81 mg non-inferior after rivaroxaban to POD5; CRISTAL (n=9,711) found aspirin 100 mg **inferior** to enoxaparin; the 2022 ICM recommends aspirin 81 mg BID. Duration 14–35 days, procedure-dependent.
- **MSIS 2018 and EBJIS 2021 disagree**: synovial WBC >3,000/µL is a 3-point *minor criterion* under MSIS and *confirmatory* under EBJIS. The same patient classifies differently.
- **Rotator cuff phase gates shift 4–8 weeks** for tears >3 cm or >1 tendon.
- **MUA timing**: 6–8 weeks in one source, 6–12 in another.

A hard-coded rule that contradicts the operating surgeon's own protocol is not "wrong by 5%." The surgeon says *"that's not my protocol,"* closes the tab, and the account is lost — the same mechanism as the "questionable data utility / inability to tailor software to clinical context" finding in the JMIR Human Factors study.

**Ship NOW.** A `practice_protocol` table keyed on `(practice_id, cpt_code)`, version-stamped with `effective_date` and `approving_clinician_npi`, holding: per-week ROM gates, weight-bearing status, VTE agent + duration, precaution policy, MUA referral threshold, and **which PJI definition to display (MSIS vs EBJIS — store which system produced a verdict and never blend them)**. Every reason code renders the `protocol_version` it was evaluated against. Safety-critical patient-facing text (weight-bearing, medication, wound care) renders **verbatim** from this record and is never LLM-paraphrased — the failure mode is "non-weight-bearing 6 weeks" becoming "take it easy on that leg." Any protocol edit invalidates all derived caches.

---

## Severity 12 — Nobody specified how the product finds out it was wrong

Outcome capture is correctly named as the binding constraint with a multi-year lead time. But the *mechanism* is unspecified, and two pieces sitting in different corpus files were never connected:

1. **HL7v2 ADT e-notifications have been a hospital Condition of Participation since May 1, 2021** (CMS-9115-F). A01 admit / A03 discharge / A04 ED registration / A08 update, delivered as webhooks via Bamboo Pings, PointClickCare ENS, a state HIE, or Redox. **Your surgeon customers qualify as the "established care practitioner" entitled to receive them.** This is a near-free, high-specificity readmission/ED-visit label — the single cheapest source of ground truth in the entire plan.
2. **Epic write-back is limited** to flowsheet observations, `DocumentReference.Create`, and `QuestionnaireResponse`. No order or CarePlan writes. So you cannot read the surgeon's *decision* back out of Epic. The label must come from the ADT feed or from the surgeon's own click.

**Ship NOW.**

```sql
CREATE TABLE adjudicated_event (
  id SERIAL PRIMARY KEY, patient_id TEXT NOT NULL, event_date DATE NOT NULL,
  event_type TEXT CHECK (event_type IN
    ('PJI','SSI_SUPERFICIAL','VTE','PE','DISLOCATION','PPF','MUA','READMISSION',
     'ED_VISIT','DELIRIUM','AKI','REVISION','DEATH','OTHER')),
  definition_system TEXT,                  -- 'MSIS_2018' | 'EBJIS_2021' | NULL
  adjudicator_npi TEXT, adjudication_date DATE,
  source TEXT CHECK (source IN ('ADT_FEED','CHART_REVIEW','PATIENT_REPORT','SURGEON_CLICK')),
  engine_sha TEXT, config_version TEXT
);
ALTER TABLE patient ADD COLUMN last_known_contact DATE;
ALTER TABLE patient ADD COLUMN follow_up_complete BOOLEAN DEFAULT 0;
```

And the cheapest label channel nobody proposed: a **one-click "this alert was right / wrong / unknown"** control on every worklist row, writing `source='SURGEON_CLICK'`.

**Correct a logical error in the corpus while you are here.** One report claims Mondrian conformal calibration "needs ZERO adverse-outcome labels — that is the point." That is wrong. Knowing a patient completed recovery uneventfully **is a negative label** and requires the same 90-day follow-up and chart review as a positive one. The `follow_up_complete` column above is what makes conformal calibration possible; without it the calibration pool is not small, it is *unknowable*.

---

## Severity 13 — Language, literacy, and the caregiver are absent as data-model entities

`grep` returns **0 files** for `interpreter` and `health literacy`.

The corpus contains the pieces: sixth-grade reading level is the AMA/NIH standard and only 3.9% of orthopedic patient materials meet it; ACA §1557 obligates meaningful language access; the CMS PRO-PM **requires the SILS-2 literacy screener** as a submitted risk variable; RAPT item 6 is *caregiver at home after discharge* — worth **3 of 12 points, the single largest item in the instrument**. And the adversarial critique names the most probable severe-harm pathway in the whole product: a Spanish-speaking patient reports `"me duele el pecho y no puedo respirar"` on POD 6, matches zero English keywords, gets classified as "general discomfort," receives a cheerful acknowledgment, and — falsely reassured that the practice saw it — dies of a PE at home.

**The entity nobody proposed: the caregiver.** In a 66-year-old post-op cohort the person who sees the wound and notices the confusion is the spouse. Post-op delirium after primary TJA is **13.6% pooled** (35 studies, >29,000 patients), onset POD 1–3, **42.3% in frail vs 7.8% in non-frail** patients — and a delirious patient cannot self-report. The corpus proposes a nocturnal sleep-fragmentation detector paired with "a caregiver-facing CAM or 4AT prompt," which is unimplementable because there is no caregiver in the data model.

**Ship NOW.**

```sql
ALTER TABLE patient ADD COLUMN preferred_language TEXT DEFAULT 'en';  -- BCP-47
ALTER TABLE patient ADD COLUMN sils2_score INTEGER;                   -- CMS PRO-PM risk var
CREATE TABLE caregiver (
  id SERIAL PRIMARY KEY, patient_id TEXT NOT NULL, relationship TEXT,
  consent_scope TEXT NOT NULL, can_submit_checkin BOOLEAN DEFAULT 0,
  notify_on_tier TEXT, granted_at TIMESTAMP, revoked_at TIMESTAMP
);
```

**Fail-closed triage rule, enforced in code:** any inbound free text that matches no deterministic branch/keyword — including detected non-English, misspelled, or unparseable — routes to a human queue with a same-business-day SLA and receives a **static** reply directing the patient to call the practice or 911. It is never silently dropped, never handed to an LLM classifier alone, and **all acknowledgment templates are suppressed whenever any flag fires or any reply is unclassified.** Outbound clinical questions are human-translated once (Spanish first), never machine-translated at runtime.

---

## Severity 14 — Nobody asked whether the six chosen vitals are the right six

The composite is RHR .25 · skin temp .25 · HRV .20 · RR .15 · steps .15. The evidence against this specific weight vector is scattered across the corpus and was never assembled:

- **Skin temperature carries the joint-largest weight and is the least trustworthy channel.** Free-living wrist skin temp is dominated by ambient conditions and bedding. At the current `SD_FLOORS` of 0.12 °C, a 0.4 °C ambient excursion yields z ≈ +3.3, contributing **0.83 by itself — 70% of the ELEVATED threshold from one confounded metric.** Compounding it: Apple ships an *absolute* nightly wrist temperature in °C, Fitbit ships a *relative nightly variation from the user's own baseline*, Oura/WHOOP ship deviation. These are not one quantity. Running `compute_baseline` on a delta-vendor's series **double-centers it** and suppresses real fever signal.
- **Steps are −36.4% wrong with a walker**, in exactly the weeks 0–4 window the product claims to watch, and the wrist error is non-monotone in speed (−16.3% at 0.45 m/s, −0.1% at 0.89 m/s, −6.9% at 1.34 m/s), so no constant correction factor is valid.
- **Respiratory rate carries 0.15 weight on a metric with no known accuracy.** The corpus states plainly: "Respiratory rate validation numbers for consumer wearables ... were not retrievable in this pass, despite RR being one of the six vitals in our composite deviation index."
- **HRV RMSSD LOA is ±11–15 ms** — large relative to the deviations CUSUM is chasing — and Apple ships **SDNN, sampled opportunistically during daytime Breathe sessions**, a completely different noise structure and diurnal composition than Oura's nocturnal 5-minute-window RMSSD or WHOOP's slow-wave-weighted value.
- **Sleep duration should not be a pain or recovery proxy at all.** A CCJR Award study plus a 12-week Fitbit study both found recorded total sleep time **unchanged from baseline at 30/60/90 days and uncorrelated with VAS at every timepoint**; wake-detection specificity is 29–52% across all six major devices, so TST is biased +6 to +40 min with LOA up to ±150 min — the device smooths over exactly the pain-driven awakenings that would be the earliest signal.

**Adjudication: 0.55 of the weight vector sits on channels that are device-dependent artifacts or unvalidated in the exact window the product claims to watch.**

**Ship NOW.**
1. Split `SKIN_TEMP` into `skin_temperature_absolute_c` and `skin_temperature_deviation_c` as distinct metric codes with distinct baseline semantics. Never coerce. Raise the skin-temp SD floor from 0.12 °C to **0.25 °C** and score against the patient's own trailing 7-day median.
2. Cut RR weight from 0.15 to **0.05** and emit `RR_UNVALIDATED_CHANNEL` in the basis panel until you have a validation number.
3. Gate steps on `assistive_device` type (walker/rollator ⇒ suppress step-based escalation; cane ⇒ no correction needed at −1.9%). Record the device timeline as dated patient-reported intervals and emit `STEP_ARTIFACT_DEVICE_TRANSITION` when a step jump falls within ±2 days of a recorded transition.
4. Baselines are **provider-scoped**. Refuse to compute a composite if the patient switched device families mid-episode.
5. Replace HIGH>2.0 / ELEVATED>1.2 with **empirical quantiles of the LifeSnaps null distribution**, not round numbers. Note also that the clip `min(max(z,0),4.0)` makes each term a censored half-normal with null mean ≈0.399σ, so the index's null mean is ≈0.40 and "normal ≤1.2" is barely two null-SDs up.

---

## Consolidated: what to refuse to build

| Refuse | Because |
|---|---|
| Autonomous wound-photo SSI classifier | Photo-only sens **63.9%**; best app validated on 5 infections / 41 patients, Android-only, 42.9% upload failures, no skin-tone stratification |
| Automated exercise **form** grading from pose | No peer-reviewed accuracy literature exists. Rep *counting* via amplitude-adaptive peak detection is fine (99% cycle detection, <40 ms error) |
| Expected-recovery curves for **bilateral** or **revision** | No published curve exists for either |
| Conversationally decomposed KOOS JR / HOOS JR | ISPOR "substantial modification" → full psychometric revalidation; scores become unreportable |
| Any learned risk model before **≥100 adjudicated events** | At 1,000 patients × 3% = ~30 events, 10 EPV buys ~3 parameters. Below that, ship the expert-weighted composite (BVS3 precedent: AUC 0.88, 74% sens @ 85% spec, 4.4±3.1 d lead, **unsupervised**, n=220/42 events) |
| MEWMA, BOCPD, SAFFRON/ADDIS online FDR | Unverified control limits; between-patient covariance substituted for within-patient; alpha-wealth depends on a test ordering that lazy-on-read scoring makes non-reproducible |
| Double-support time and walking asymmetry in **automated tier logic** | ICC 0.53 (Apple) / 0.42–0.58 (independent); asymmetry validated on 51 young adults in a locked knee brace |
| Readmission-reduction claims, anywhere | The definitive RCT (n=4,736) is null: RR 1.02 (0.92–1.13) |
| Object Lock COMPLIANCE mode on the DB prefix | Creates an undeletable 7-year archive of full PHI databases on every S3 sync |

---

## Sequencing — the order these should land

**Sprint 1 (schema + honesty; no algorithms).** `surgical_event`, `adjudicated_event` + `last_known_contact` + `follow_up_complete`, `enrollment`, `clinic_measurement`, `caregiver`, `practice_protocol`, `coverage_manifest.yaml`. Stamp `engine_sha` + `config_version` on every RiskAssessment. Delete the post-op-days-2–4 baseline fallback. All of this is days of work with multi-year lead times, and nothing downstream is honest without it.

**Sprint 2 (make the demo lie less).** Sever the `app.seed → app.engine` import edge in CI; Mitscherlich generator; AR(1) noise; non-wear gaps; walker period; contralateral patient; device-swap patient; quitter. Replay LifeSnaps + PMData and pin the alert-budget test.

**Sprint 3 (the actual signal).** Wound check-in channel with week-conditional precedence-0 rules; PT magic-link form; coverage-residual disengagement detector; text-arm confidence gate.

**Sprint 4 (make it legible).** The 30-second worklist contract with raw values and PPVs; the ≤3-items/day budget enforced in CI; `not_watched` rendering; surgeon card-sort to establish weight provenance.

**Gated on volume, stated explicitly.** Platt recalibration of the composite at **≥30–50 adjudicated events**. Discrete-time pooled-logistic hazard on person-day rows, served as a frozen numpy dot product, at **≥30 events / 3 parameters**. Component unpacking of the composite at **≥100 events**. Landmark LightGBM at **≥1,000 patients / ≥100 events**. Put the current adjudicated-event count on an internal dashboard so the gate is observable rather than remembered.