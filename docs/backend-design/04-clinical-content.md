# Section 4 — The Clinical Content Layer: What to Measure and What to Say

*Owner: clinical engineering. Depends on: nothing. Blocks: everything else in the engine that claims to be about orthopedics.*

---

## 4.0 The headline reorientation: the engine is currently measuring the wrong thing

The current engine is a physiologic-wearable deviation detector. Every analyzed channel in `engine/pipeline.py:ANALYZED_METRICS` is a vital sign or an activity count, every weight in `engine/composite.py:WEIGHTS` is a vital sign or steps, and every reason code in `engine/risk.py:_FLAG_REASONS` is derived from one. The literature says that architecture has a hard ceiling, and the ceiling is measured in **hours**:

| Signal family | Best quantified lead time | Source |
|---|---|---|
| Continuous HR + temperature telemetry | median **14 hours** before chart documentation, flagging 78% of infectious complications (single 2023 feasibility study, graded *weak*) | colorectal/mixed-surgical systematic review, PMC12428718 |
| Prospective wearable post-op cohort | **7–11 hours**, with HR +14 bpm, RR +5 bpm, SpO₂ −4%, skin temp +1.2 °C | Eur J Cardiovasc Med prospective cohort |
| Patient-reported wound drainage | **days**, inside a 30-day window, with acute PJI presenting at median **POD 14 (IQR 10–18)** | Wouthuyzen-Bakker et al. 2023, n=1,019, PMC10015257 |
| Activity trajectory | days-to-weeks; return-to-baseline activity AUROC **0.76** (sens 75%, spec 69%) for 30-day readmission | PMC12428718 |

**No study anywhere in the corpus quantifies a day-scale physiologic lead time for PJI in arthroplasty patients.** The corpus says so explicitly (open question 1 in `clinical--post-operative-complication-surveillance`). So the product must stop implying it. Concretely:

1. **The composite deviation index is not, and must never be described as, an infection detector.** It is a *general deterioration* signal with an hours-scale lead time. Rename `CompositeResult` semantics accordingly in the UI copy and in `llm/prompts.py`; keep the math.
2. **Wound drainage becomes a separate, higher-precedence pathway** — not a weighted term inside `composite.py`. The research's own open question 9 asks whether drainage should be diluted into the composite; the answer is no. At the published effect sizes (week-2 any drainage 88%/88%; week-3 moderate-heavy OR 103), folding a 0.15-weight drainage z-score into a sum with resting-HR and steps destroys the signal by construction. **Adjudication: separate pathway, evaluated first, able to set tier on its own.**
3. **This also fixes gap G5.** RTM (98975–98981) is defined by CMS as monitoring *non-physiologic* data — musculoskeletal status, therapy adherence, therapy response. `models/enums.py` already declares `PAIN_NRS`, `RANGE_OF_MOTION`, `THERAPY_ADHERENCE`, `EXERCISE_REPS`, `PROM_SCORE`, and grep confirms none is referenced outside that file. The clinical content layer *is* the fix for the substance-over-form problem in the billing story. Ship it before you ship another vitals feature.

New package: `backend/app/clinical/`. It owns all domain knowledge; `engine/` keeps the statistics. Nothing in `clinical/` calls an LLM.

---

## 4.1 Wound capture and week-conditional drainage logic

### 4.1.1 The evidence, and its honesty problem

The source study (n=1,019; 46% knee, 54% hip; daily self-reported wound status POD 0–30; 16 PJIs, 1.6%) reports:

| Rule | Sens | Spec | OR (95% CI) | PPV / NPV |
|---|---|---|---|---|
| Any drainage, post-op **week 2** | 88% | 88% | — | — |
| Moderate–heavy drainage, **week 2** | — | — | 51.22 (15.84–165.65) | — |
| Moderate–heavy drainage, **week 3** | — | — | 103.23 (26.08–408.57) | **PPV 83%** |
| New-onset drainage appearing in week 2 | — | — | 80.71 (9.12–714.52) | — |
| Cumulative >5 drainage days, weeks 1–3 | 63% | 87% | 9.20 (3.37–25.14) | — |
| >10 drainage days | 27% | 97% | — | — |
| **No drainage at all** | — | — | — | **NPV >98%** (1 PJI in 467) |
| Drainage prevalence, non-PJI vs PJI | wk1 50/63%, **wk2 12/88%**, wk3 8/64%, wk4 3/25% | | | |

The adversarial verification flags this as *the highest-risk item in the whole clinical corpus* and could not locate the source: every OR rests on ≤16 events, and OR 80.71 with CI 9.12–714.52 is a two-order-of-magnitude interval.

**Adjudication.** Build the *capture channel* and the *week-conditional shape* now — they are cheap, they are what surgeons asked for (the Mayo interview cohort explicitly requested wound photography), and they are the only thing in the corpus with day-scale lead time. But:
- **Never display an odds ratio to a clinician.** Display the prevalence contrast (week 2: 12% of non-PJI patients vs 88% of PJI patients had drainage) — same information, no false precision.
- Treat the **rule-in** rungs as *provisional thresholds pending local re-derivation* (§4.9), and the **rule-out** arm (NPV >98%) as the load-bearing, immediately shippable use. Rule-out is where the throughput money is and where a 16-event study is least fragile.
- The study's own flat alerts caught **6 of 16 PJIs**. That is the design argument: a single "any drainage → alert" threshold applied across all 30 days is worse than useless, because week-1 drainage is present in 50% of *uncomplicated* patients.

### 4.1.2 Capture

New model `backend/app/models/wound.py`:

```sql
CREATE TABLE wound_reports (
  id                INTEGER PRIMARY KEY,
  patient_id        TEXT NOT NULL REFERENCES patients(id),
  local_date        DATE NOT NULL,              -- G2: local_date, never start_time.date()
  postop_day        INTEGER NOT NULL,
  drainage          TEXT NOT NULL,              -- none|minimal|mild|moderate|heavy
  dressing_area_gt_2x2cm BOOLEAN,               -- the ICM operational definition
  erythema_mm       INTEGER,                    -- patient estimate, nullable
  dehiscence        BOOLEAN NOT NULL DEFAULT 0,
  odor              BOOLEAN NOT NULL DEFAULT 0,
  fever_selfreport_c REAL,                      -- oral temp if taken
  photo_asset_id    TEXT,                       -- stored, NOT inferred on (see §4.10)
  source            TEXT NOT NULL,              -- app|sms|ivr|clinician
  deleted_at        TIMESTAMP,
  UNIQUE(patient_id, local_date)
);
```

Ordinal encoding: `none=0, minimal=1, mild=2, moderate=3, heavy=4`. "Moderate-to-heavy" = `>=3`. The ICM persistent-wound-drainage definition is `dressing_area_gt_2x2cm = true` on a day with `postop_day > 3`.

Capture cadence: **once daily, POD 0–30, one question.** The corpus is unambiguous that any patient-facing task cadence above 1×/day fails (thrice-daily exercise compliance 32.3% vs once-daily 52.4%). SMS/IVR fallback is mandatory — 65+ smartphone ownership is now ~78% (Pew 2025 — the corpus's 61–65% figure is stale per verification), so the low-tech tier serves the residual ~20%, not a majority, but it is still the difference between an enrollable and unenrollable Medicare cohort.

### 4.1.3 The week-conditional rule ladder

`backend/app/clinical/wound.py`:

```python
from dataclasses import dataclass

DRAINAGE = {"none": 0, "minimal": 1, "mild": 2, "moderate": 3, "heavy": 4}

@dataclass(frozen=True)
class WoundRule:
    code: str
    week: tuple[int, int]      # inclusive postop-week bounds (week 1 = POD 1-7)
    tier: str                  # WATCH | CONTACT | ESCALATE
    evidence: str              # rendered verbatim to the navigator
    grade: str                 # "provisional" until locally re-derived

RULES = [
    # --- rule-out / de-escalation (ship first, highest confidence) ---
    WoundRule("WOUND_DRY_THROUGH_D14", (2, 2), "DEESCALATE",
              "No drainage reported on any day through POD 14. In the reference cohort "
              "1 of 467 patients with no drainage developed a PJI.", "provisional"),
    # --- week 1: DO NOT ALERT ON DRAINAGE ALONE ---
    WoundRule("WOUND_PERSISTENT_ICM", (1, 4), "CONTACT",
              "Drainage >2x2 cm on the dressing beyond 72 h — the ICM definition of "
              "persistent wound drainage. ICM mandates monitoring past 72 h.", "guideline"),
    # --- week 2: the discriminating week ---
    WoundRule("WOUND_ANY_WEEK2", (2, 2), "CONTACT",
              "Any drainage in post-op week 2. Reference cohort: present in 12% of "
              "uncomplicated patients and 88% of patients who developed PJI.", "provisional"),
    WoundRule("WOUND_NEW_ONSET_WEEK2", (2, 2), "ESCALATE",
              "Drainage newly appeared in week 2 after a dry week 1.", "provisional"),
    WoundRule("WOUND_MODHEAVY_WEEK2", (2, 2), "ESCALATE",
              "Moderate-to-heavy drainage in week 2.", "provisional"),
    # --- week 3: the highest-precision rung ---
    WoundRule("WOUND_MODHEAVY_WEEK3", (3, 3), "ESCALATE",
              "Moderate-to-heavy drainage in post-op week 3. Reference cohort PPV 83%.",
              "provisional"),
    # --- cumulative burden, evaluated at end of week 3 ---
    WoundRule("WOUND_CUM_GT5_DAYS", (3, 3), "CONTACT",
              "More than 5 drainage-days across weeks 1-3 (sens 63% / spec 87%).",
              "provisional"),
    WoundRule("WOUND_CUM_GT10_DAYS", (3, 4), "ESCALATE",
              "More than 10 drainage-days (spec 97%).", "provisional"),
    # --- ICM escalation ladder on consecutive persistent days ---
    WoundRule("WOUND_PWD_GT3D", (1, 4), "CONTACT",
              "Persistent drainage >3 consecutive days (62.9% sens / 90.6% spec for "
              "acute high-grade PJI in the inpatient series).", "provisional"),
    WoundRule("WOUND_PWD_GT5D", (1, 4), "ESCALATE",
              "Persistent drainage >5 days — ICM published ladder moves to incisional "
              "NPWT at days 3-5 and debridement beyond day 7.", "guideline"),
]
```

`postop_week(d) = ((d - 1) // 7) + 1` for `d >= 1`; POD 0 is week 1.

The evaluator returns **the highest-tier matching rule plus every matching code**, never a score. Drainage is ordinal-categorical; a z-score on it is meaningless.

### 4.1.4 The PPV arithmetic, published next to the alert

This is the anti-Epic-Sepsis-Model discipline. Compute and persist it per rule per cohort:

At 1.0% 90-day PJI prevalence, the week-2 any-drainage rule (88%/88%):

```
PPV = (0.88 × 0.010) / (0.88 × 0.010 + 0.12 × 0.990) = 0.0088 / 0.1276 = 6.9%
NNE = 1 / 0.069 ≈ 14.5 patients contacted per PJI found
```

The Epic Sepsis Model was judged unusable at PPV 12% / NNE 8. Ours is worse. **Therefore `WOUND_ANY_WEEK2` may never be an interruptive alert to a surgeon.** It goes into the navigator's daily queue, where the cost of evaluation is a two-minute phone call, not a physician workup. Only `ESCALATE`-tier codes reach the surgeon.

For a rule to justify surgeon interruption at 1% prevalence and a PPV target of 25%, with sensitivity 0.88, it needs specificity:

```
0.0088 / (0.0088 + (1-spec)·0.99) ≥ 0.25  ⟹  spec ≥ 97.3%
```

No single published drainage rule reaches that. The path there is **conjunction** — drainage rule AND ≥2 concordant physiologic flags AND a functional decline — and the conjunction's specificity must be *measured on our own cohort*, not assumed. Until measured, ship the ladder as watch/contact/escalate with the NNE printed on the card.

### 4.1.5 The de-escalation lane is the business case

`WOUND_DRY_THROUGH_D14` should:
- drop the patient's infection-pathway precedence to zero,
- reduce daily check-in to every other day for POD 15–30 (keeping ≥16 transmitting days/30 for 98977),
- and be surfaced to the navigator as *"low-yield, deprioritize"*.

At ~500 TJA/yr and a 1.6% PJI rate, this moves ~460 of 500 patients out of the wound queue with an evidence-backed NPV. That is what makes a one-navigator-to-many-patients ratio viable.

---

## 4.2 Complication-by-complication surveillance spec

`backend/app/clinical/complications.py` — a registry, one entry per complication, consumed by the risk engine and by the narrative layer. Every entry carries: `incidence`, `window_days`, `detector_class`, `first_moving_signal`, `reason_codes`, `evidence_grade`, `surveillance_intensity`.

**The single most important field is `detector_class`, which has exactly two values:**

- **`TREND`** — EWMA/CUSUM on continuous channels is appropriate. PJI/SSI, VTE, delirium, AKI, general deterioration.
- **`EVENT`** — a step-change detector. Dislocation, periprosthetic fracture, acute graft/repair failure. Running EWMA over a discrete mechanical catastrophe is a category error and will always fire late. The correct rule is a same-day cliff: `steps_today < 0.30 × median(steps, last 7 days)` co-occurring with a ≥3-point NRS spike.

### 4.2.1 The registry

| Complication | Incidence | Presentation window | First signal to move | Engine watches | Detector | Says |
|---|---|---|---|---|---|---|
| **PJI (primary THA)** | 0.94% @1yr; **76.8% dx by day 90** | median POD 14 (IQR 10–18) | patient-reported drainage | wound ladder (§4.1); vitals as *corroboration only* | TREND + wound | "Wound drainage pattern that warrants a call today" |
| **PJI (primary TKA)** | 1.05% @1yr; **only 57.7% dx by day 90** — ~42% present day 91–365 | median POD 14, long tail | drainage; late cases present with pain + function regression | wound ladder to D30; then pain re-escalation + function plateau to **D365** | TREND | as above; low-intensity monthly tail |
| **PJI (revision)** | THA 4.39%, TKA 5.33% | same | same | same, with prior-to-tier bump | TREND | — |
| **SSI (all)** | ~60% within 30 d, 74% within 90 d | POD 5–30 | drainage, erythema, dehiscence | wound ladder | TREND | — |
| **Symptomatic PE** | 90-day 0.71%; VTE after THA on ASA 1.11% | **median POD 3 (IQR 2–7)** | SpO₂ drop / HR rise | SpO₂ persistent <95% or sudden drop, **weighted maximally POD 0–7** | TREND | "Oxygen saturation has dropped — screening-grade signal, needs clinical assessment" |
| **DVT** | 0.59% symptomatic @90 d | POD 2–14 | unilateral calf pain, activity drop | pain-location item + step cliff | TREND | — |
| **Arthrofibrosis → MUA** | MUA in ~4% of TKA | decision at **weeks 6–12**, best gains <12 wk | knee flexion trajectory | projected week-6 flexion (§4.3.2) | TREND | "Flexion is tracking to miss 90° at week 6 — PT intensification window is now" |
| **THA dislocation** | posterior 1.1%, DA 0.7%, lateral 0.5%; **91% within 6 weeks** (posterior), 75% of DA first-time in first 3 weeks | POD 0–42 | none — acute mechanical event | step cliff + acute pain spike; fall signal if available | **EVENT** | "Sudden drop in activity with a pain spike — call now" |
| **Periprosthetic fracture** | ~1.7% @10 yr primary THA | any | acute fall | fall detection + step cliff | **EVENT** | — |
| **Post-op delirium** | **13.6%** pooled (95% CI 12.2–15.0); frail 42.3% vs non-frail 7.8% | **POD 1–3** | nocturnal activity fragmentation / sleep-wake reversal | overnight movement + sleep fragmentation, **only for age ≥65 or mFI-5 ≥2** | TREND | caregiver-facing 4AT/CAM prompt — never an autonomous verdict |
| **AKI** | 2–15% (definition-dependent) | POD 1–7 | none wearable-visible | KDIGO from lab feed only if labs are connected | TREND | — |
| **ACLR cyclops / extension loss** | symptomatic 1–9.8% | symptomatic at **2–3 months**; mean deficit 19° at 5.9 mo | terminal extension | extension fails to reach 0° by wk 4–6, then plateaus/regresses wks 6–12 | TREND | — |
| **Rotator cuff retear** | 12–57% across series; **46.3% of within-1-yr retears occur between wk 6 and mo 3** (Yamaura 2023, n=638, 41 retears) | wks 6–12, at sling weaning | loss of previously-gained **ACTIVE** elevation with preserved **PASSIVE** ROM; reversal of pain trajectory | paired active/passive ROM + pain re-rise | TREND | — |
| **Lumbar pseudarthrosis** | judged at **12–24 months**; reoperation 29% vs 5% for ASD | >3 mo | pain curve stops improving after month 3 | pain slope flattening + mechanical (activity-dependent) pain | TREND | never before month 3 |
| **Lumbar ASD** | 5–27% (SR narrows to 2–14%) | years | **new** pain after a sustained good plateau | pain re-rise after plateau | TREND | — |
| **30-day readmission** | 3.3–4.5% | POD 0–30 | activity failure to return to baseline (AUROC 0.76) | return-to-baseline activity | TREND | — |

Two corrections from the corpus's own text, adjudicated:

- **The 52.6%-medical-TKA / 50.7%-surgical-THA readmission cause split is unsourced** and the verification could not locate it. **Do not display it and do not weight the model on it.** Use the CMS/MIPS #480 complication ontology instead, which is a real published spec.
- **CRPS: do not build a flag at all.** The zero-cases-in-100 Budapest study was a single 6-week timepoint, so it cannot support a "suppress before week 12" rule either. The operationally useful number is the one the verification surfaced: **17 of 100 patients reported excessive pain at 6 weeks with zero meeting Budapest criteria.** That 17% sizes the disproportionate-early-pain triage queue. Rank infection above CRPS in every differential the narrative layer renders.

### 4.2.2 The TKA/THA surveillance-window difference is a config field, not a constant

`Patient` gains `surveillance_horizon_days` and a per-procedure intensity schedule:

```python
SURVEILLANCE = {
    ProcedureType.TKA: Horizon(days=365, phases=[
        Phase(1, 30,  "daily",     "full"),      # 57.7% of TKA PJIs are NOT dx by day 90
        Phase(31, 90, "daily",     "vitals+pain"),
        Phase(91, 365,"biweekly",  "pain+function+PROM"),
    ]),
    ProcedureType.THA: Horizon(days=180, phases=[   # 76.8% dx by day 90
        Phase(1, 30,  "daily",    "full"),
        Phase(31, 90, "daily",    "vitals+pain"),
        Phase(91, 180,"monthly",  "PROM"),
    ]),
}
```

A surveillance program that closes at day 90 misses ~23% of THA and **>42% of primary TKA** infections. This is a differentiating, defensible product claim and it costs one config table.

### 4.2.3 Diagnostic definitions: encode both, blend never

`clinical/definitions/msis.py` and `clinical/definitions/ebjis.py`. The main research file states both incorrectly; the verification is correct. Encode the verified versions:

**MSIS 2018 (Parvizi).** Major criteria (either alone ⇒ infected): sinus tract communicating with the joint/prosthesis; two positive periprosthetic cultures of the same organism. Minor criteria: serum CRP >1 mg/dL = 2; serum D-dimer >860 ng/mL = 2; ESR >30 mm/h = 1; synovial WBC >3,000 cells/µL = 3; synovial α-defensin S/CO >1.0 = 3; leukocyte esterase ++ = 3; synovial PMN% >80% = 2; synovial CRP >6.9 mg/L = 1.

> **Correction to the research text.** The corpus says ">5 infected, 3–5 inconclusive, <3 not infected." That is wrong on both arms. **Preoperative arm: ≥6 infected, 2–5 inconclusive, 0–1 not infected. Combined preop+intraop arm: ≥6 infected, 4–5 inconclusive, ≤3 not infected**, with intraoperative weights positive histology 3, purulence 3, single positive culture 2. Encoding the corpus version would classify every patient scoring 2 as ruled out when MSIS calls them inconclusive — a classification bug.

**EBJIS 2021 (McNally).**
> **Correction:** the rule-out is **AND, not OR**. "Infection unlikely" requires synovial WBC <1,500/µL **AND** PMN <65% **AND** no other listed feature positive. Under the corpus's OR version a patient with synovial WBC 10,000/µL and PMN 60% is classified "unlikely." Confirmatory half is correct: >3,000 cells/µL or PMN >80% confirms; serum CRP >10 mg/L is *suggestive* only.

Store `definition_system` on every verdict. Never blend. Never display MSIS's 97.7%/99.5% performance next to a surveillance alert — those figures come from revision patients against a culture/sinus-tract gold standard, not from acute post-op surveillance. That would be a spec-transfer error.

**CRP kinetics.** Encode only what verifies:
- 90-day cutoff **serum CRP 39.8 mg/L, sens 91%, spec 87%** (the corpus's 95% specificity is wrong). Companions at 90 days: synovial WBC 6,130 cells/µL (91%/83%), ESR 39.5 mm/h (76%/67%), PMN 79.5% (95%/59%). At 30 days synovial WBC is **10,170 cells/µL** — roughly 2× the 90-day value, which is why every threshold constant must carry its window as a field.
- The 50.7 mg/L (≤30 d) and 44.9 mg/L (≤45 d) values are **unverified**; do not ship them.
- The "first 6 post-op days" suppression is real but the source is **TKA, first 5 days**, not THA: "neither the absolute post-op CRP value nor its course in the first 5 days after TKA is suitable for detecting an early infection." Suppress CRP-based infection logic POD 0–5 after TKA.
- Free win the corpus discarded: **preoperative CRP >5 mg/L predicts later septic revision after TKA.** Add it to the pre-op risk profile (§4.6).

---

## 4.3 Per-procedure clinical clocks

### 4.3.1 The data structure

The current `engine/curves.py` hand-parameterizes one logistic per procedure over an abstract "fraction of pre-op functional capacity," with a flat `CI_WIDTH = 0.08` band, and its own docstring admits the seed generator shapes patients along the same curves so "on track is on track by construction" (gap G6). Replace it with **metric-specific, procedure-specific, milestone-anchored clocks**.

`backend/app/clinical/clocks.py`:

```python
from dataclasses import dataclass
from typing import Literal

Channel = Literal["passive_wearable", "guided_in_app", "clinic_visit", "patient_reported"]

@dataclass(frozen=True)
class Milestone:
    metric: str                 # MetricType value
    day_lo: int                 # window opens (post-op day)
    day_hi: int                 # window closes — the day the gate is judged
    comparator: Literal["gte", "lte", "ratio_gte", "delta_lte"]
    target: float
    unit: str
    channel: Channel
    action_code: str            # typed reason code emitted on failure
    lead_day: int | None        # day to raise the PROJECTED-miss warning
    evidence: str               # rendered verbatim
    grade: Literal["strong", "moderate", "consensus", "provisional"]

@dataclass(frozen=True)
class ProcedureClock:
    procedure: str
    variant: str | None          # e.g. "small_medium" vs "large_massive" cuff tear
    milestones: tuple[Milestone, ...]
    reference_curves: dict[str, "ReferenceCurve"]  # metric -> week-indexed anchors
    nadir_week: int
```

A `ReferenceCurve` is a table of **week-indexed published anchors with published SDs**, linearly interpolated — not a logistic. This is falsifiable in a way the logistic is not: each anchor has a citation and a cohort size.

### 4.3.2 TKA

Gait (mymobility/Apple Watch, n=686; baseline speed 1.01 ± 0.15 m/s, step length 0.60 ± 0.08 m, double support 31.4 ± 1.5%, asymmetry 12.5 ± 17.6%):

| Metric | Baseline | **Week-2 nadir** | Returns to baseline |
|---|---|---|---|
| Walking speed | 1.01 m/s | **0.79 m/s (−21.8%)** | week **21** |
| Step length | 0.60 m | 0.55 m (−8.3%) | not within 24 wk (0.59 m, p=0.004 — authors call it not clinically relevant) |
| Double support | 31.4% | 32.8% | week **24** |
| Walking asymmetry | 12.5% | **52.6% (+321%)** | week **13** |

Steps: week 1 ≈ **1,439**/day → week 6 ≈ **4,781** → week 20 ≈ **6,344**. Sex-stratify: men rose 4,970 → 6,185 post-TKA while women fell 5,532 → 4,652. A pooled curve systematically mislabels women as under-recovering.

Meaningful-change floors (Redfern et al., J Arthroplasty 2026, n=2,146, EQ-5D-5L anchored — flag as brand-new and unreplicated): **gait speed MCID 0.067 m/s, SCB 0.067 m/s; step count MCID 1,227/day, SCB 1,630/day.** Suppress any "meaningful improvement" claim below these. Do **not** apply generic 10MWT MCIDs of 0.10–0.16 m/s to TKA — the paper explicitly says TKA's meaningful change is smaller.

ROM gates: ≥90° flexion by end of week 1; ≥100° flexion and full 0° extension by weeks 2–3; 110–120° by weeks 4–6; **<90° flexion at week 6 ⇒ MUA discussion.**

The MUA rule is the single most actionable ROM alarm in the product, and the point is to fire it at **week 3–4 with runway**, not at week 6 when the decision is already forced:

```python
def projected_week6_flexion(points: list[tuple[int, float]]) -> tuple[float, float] | None:
    """points = [(postop_day, flexion_deg)] from POD >= 10. Returns (projection, slope)."""
    if len(points) < 3:
        return None
    import numpy as np
    from scipy.stats import theilslopes          # add scipy; median-of-slopes is robust
    d = np.array([p[0] for p in points], float)
    f = np.array([p[1] for p in points], float)
    slope, intercept, _, _ = theilslopes(f, d)   # single bad goniometry reading must not steer it
    return float(intercept + slope * 42.0), float(slope)
```

Emit `ROM_MUA_RISK_PROJECTED` when `postop_day` is in **[21, 35]**, ≥3 measurements exist since POD 10, and the projection is **<90°**. Narrative: *"Flexion is tracking toward roughly 82° at week 6. MUA is typically discussed below 90°, and manipulation performed within 12 weeks yields the best flexion gains. Intensified PT now is the intervention window."*

> **Adjudications.** (a) The corpus's MUA incidence of 4.3–4.6% from "3,244 and 800 knees" is unverified; use **~4%** and cite the Finnish register study of **154,883 patients** (2026, PMID 42329270) once retrieved rather than the small cohorts. (b) A 2026 paper (PMID 42448249) finds MUA patients recover mobility but have *worse functional outcomes* — so the narrative must say "flag the trajectory early to try to avoid MUA," never "MUA will fix this." (c) Goniometry stays `clinic_visit` or `guided_in_app` with an explicit ±3–5° error band; smartphone goniometry has no large post-op validation and must not silently drive the alarm — require a clinician-confirmed value before `ESCALATE`.

### 4.3.3 THA

Same four gait metrics, **roughly 2× faster**: nadir week 2 (speed 0.79 m/s, asymmetry 42.0%), asymmetry recovers week 7, step length week 8 (0.58 ± 0.06 m vs 0.59 baseline), speed week 9, double support week 10.

> **The research contradicts itself here and the product must not pick the optimistic branch.** The Sensors n=612 paper reports THA metrics *exceeding* baseline by weeks 10–18 (speed 1.03 m/s at week 13). The larger Utah multicenter cohort (Sato et al., J Arthroplasty 2023, **n=1,898 THA**) reports gait speed and asymmetry returning to baseline by 3 months but **not reaching an MCID of improvement by 1 year**. Two credible sources disagree. **Adjudication: encode the Sensors curve as the *reference trajectory* but set the "ahead of schedule" band at the Utah result, i.e. never tell a patient or surgeon that supra-baseline gait by week 13 is the expectation.** Store both as `reference_curve` and `reference_curve_conservative` and render the conservative one in surgeon-facing copy.

Hip precautions are a **surgeon-configurable flag, not a rule**: 6,900 posterior-approach patients, dislocation 2.2% with precautions vs 2.0% without.

### 4.3.4 ACL reconstruction

Extension first: full passive extension 0° by weeks 1–2; flexion ~90° by weeks 1–2, 120–130° by weeks 4–6. **Extension deficit >5–10° persisting past week 4–6 ⇒ `ROM_EXTENSION_DEFICIT` (arthrofibrosis/cyclops).** Running gate ~week 12: full pain-free ROM, no effusion, quad LSI ≥70%.

Return-to-sport gate as an explicit checklist object, all fields `clinic_visit`:

```python
RTS_ACL = AllOf(
    months_since_surgery >= 9,
    quad_strength_index >= 0.90,          # isokinetic dynamometry
    hop_lsi_single >= 0.90, hop_lsi_triple >= 0.90,
    hop_lsi_crossover >= 0.90, hop_lsi_6m_timed >= 0.90,
)
```

Evidence to render: Grindem 2016 — reinjury **5.6%** among those who passed discharge criteria vs **38.2%** among those who failed (an 84% risk reduction); Beischer 2020 — returning to knee-strenuous sport before 9 months, **HR 6.7 (95% CI 2.6–16.7)**.

> **Corrections.** The corpus's "75–84% reduction" is a fabricated band — quote 84% with the 5.6%/38.2% absolutes. The "39.5% vs 19.4%" pair is not in Beischer; use the HR with its CI. The "3% reinjury increase per 1% quad symmetry below 90%" is not in the abstract — do not encode a dose-response. Also note LSI overestimates function because the uninvolved limb also weakens; capture absolute knee-extension torque (proposed ≥3.0 Nm/kg) alongside LSI where available.

### 4.3.5 Rotator cuff repair — a phase state machine, not a curve

Keyed on `weeks_since_surgery` **and** `tear_size` (large/massive shifts phases **4–8 weeks later**; AAROM phase moves from wks 8–10 to wks 14–18 for tears >3 cm or >1 tendon). MGH 2020 gates:

| Phase | Weeks | PROM caps | AROM | Exit criteria |
|---|---|---|---|---|
| I | 0–3 | ER <20° scapular plane, FE <90° | none | 90° PROM elevation, 20° PROM ER, 0° PROM IR |
| II | 4–6 | unchanged | AAROM begins | + pain <4/10 |
| III | 7–8 | FE <120°, ER <30°; sling off | AROM begins | 120° PROM FE, 30° ER/IR |
| IV | 9–10 | FE <155°, ER/IR 45°, ER@90abd 60° | — | AROM FE 120° |
| V | 11–12 | full PROM | full AROM | — |
| VI | 13–16 | — | strengthening | ER/IR strength ≥85% of uninvolved, ER/IR ratio ≥60% |
| VII | 4–6 mo | — | return to sport | — |

> The verification flags this entire chain as **unverified**, attributed to one institutional protocol, and warns that if slightly off it produces unsafe PROM caps. **Adjudication: ship these as `grade="consensus"`, display them as "your surgeon's protocol, defaulted from MGH 2020," and make every degree value site-overridable in a `protocol_overrides` table before the first customer.** Never render a cap as a patient instruction without a surgeon having approved the protocol.

The retear detector is the phase machine's real payoff: emit `RC_ACTIVE_ROM_REGRESSION` when active elevation drops ≥15° from the patient's own 14-day max **while passive is preserved**, between week 6 and month 3 — the window containing **46.3% of all within-1-year retears** (Yamaura 2023, n=638 shoulders, 41 retears).

### 4.3.6 Lumbar fusion, ankle, meniscus

Lumbar: **do not track spine ROM** — it is intentionally not a rehab target early. Track walking volume: target ~3,500 steps/day in weeks 1–2, building to 20–30 min continuous walks; no BLT ×6 weeks; light activity 4–6 weeks. Pain-curve rules only: failure to keep improving after month 3 (pseudarthrosis), and a **new** rise after a sustained good plateau (ASD).

**Ankle ORIF and meniscus have no published week-by-week wearable curves anywhere in the corpus.** Ship them with `grade="consensus"` clocks, percent-of-preop-baseline milestones with deliberately wide bands, and **no ROM or gait alarms at all**. Refuse to fabricate a curve to make the demo symmetric — the current `EXPECTED_CURVES` table's `MENISCUS: CurveParams(0.40, 0.15, 10)` is exactly the kind of unfalsifiable parameter that will be caught in the first clinical review.

### 4.3.7 Acquisition channel is a first-class column

Add `acquisition_channel` to `observations`: `passive_wearable | guided_in_app | clinic_visit | patient_reported`. Passive: steps, gait speed, step length, asymmetry, double support (trend-only), cadence, stair speed. Guided in-app: TUG, 30-s chair stand, single-leg stance, 10-m walk. Clinic-only: goniometric ROM, extension lag, isokinetic strength, hop battery, Y-Balance, 40-m fast walk, formal 6MWT. Clinic-only fields are sparse visit-dated observations and must never be interpolated.

Apple double-support-time is **within-patient trend only**, never compared to lab norms. (The corpus's "reads ~2× lab values" claim is unverified per verification — keep the operational guidance, drop the number.)

---

## 4.4 Pain and opioid

### 4.4.1 The non-monotonic curve

`backend/app/clinical/pain.py`. Piecewise-linear interpolation over published anchors, with an explicit rebound window:

```python
PAIN_ANCHORS = {                                  # (postop_day, mean NRS)
    ProcedureType.TKA: [(1, 5.8), (8, 4.6), (9, 4.8), (29, 3.0)],
    ProcedureType.THA: [(1, 3.1), (8, 2.3), (9, 2.6), (12, 2.3)],
}
REBOUND_WINDOW = {ProcedureType.TKA: (8, 12), ProcedureType.THA: (8, 12)}
REBOUND_BAND_WIDENING = 1.5        # NRS points added to the alert band inside the window
BASE_BAND = 2.0                    # acute-pain MCID is ~1.5-2.0 NRS points
```

The deviation rule that does not fire on the normal POD9 rebound:

```python
def pain_deviation(procedure, postop_day, nrs_series) -> str | None:
    """nrs_series: {postop_day: nrs}. Uses a 2-day median to kill single-day noise."""
    obs = _median2(nrs_series, postop_day)
    if obs is None:
        return None
    exp = _interp(PAIN_ANCHORS[procedure], postop_day)
    lo, hi = REBOUND_WINDOW[procedure]
    band = BASE_BAND + (REBOUND_BAND_WIDENING if lo <= postop_day <= hi else 0.0)
    # persistence: two consecutive days above band, never a single day
    if obs - exp >= band and _prev_day_also_above(nrs_series, procedure, postop_day, band):
        return "PAIN_ABOVE_EXPECTED"
    # re-escalation is the infection / mechanical channel, and it is day-gated
    if postop_day >= 14:
        floor7 = min(v for d, v in nrs_series.items() if postop_day - 7 <= d < postop_day)
        if obs - floor7 >= 2.0:
            return "PAIN_REESCALATION"
    return None
```

Inside the TKA rebound window an NRS of 6.3 on POD 9 does not fire (expected 4.8, band 3.5). Outside it, an NRS of 6.6 on POD 20 fires (expected ~3.8, band 2.0), two days running.

> **Adjudications.** (a) The POD 9 value of 4.8 and the p-values for sex/BMI/valgus are **not in the published abstract** — the verified anchors are 5.8 (POD 1), 4.6 (POD 8), 3.0 (POD 29). Ship the shape; label the rebound magnitude `provisional` and make `REBOUND_WINDOW` and `REBOUND_BAND_WIDENING` **per-site config**, because rebound timing depends on local rehab scheduling (inpatient rehab vs home PT vs same-day discharge). (b) The TKA paper's female-sex and *lower*-BMI pain modifiers must **not** be carried to THA — the THA paper explicitly found age, sex, BMI and surgery duration did *not* correlate. (c) The two cohorts are n=103 each, same single center, same protocol; the TKA−THA offset is 2.7 at POD 1 and 2.3 at POD 8, so a single additive offset is wrong at the ends — interpolate each procedure separately.

### 4.4.2 The two latent classes, correctly used

Latent class growth analysis, n=227 TKA: **C1 "Moderate-High Persistent Pain" 101/227 (44.5%), NRS intercept 6.956, slope −0.494/day; C2 "Rapid Relief" 126/227 (55.5%), intercept 5.631, slope −0.631/day.** Posteriors 0.980 / 0.972. C1 predictors: pre-op NRS **OR 3.546** (1.819–6.914), PCS **OR 1.092/point** (1.022–1.167), age OR 1.052/yr, Family Care Index OR 0.763 (protective). C1 membership predicted worse 3-month function (β=0.32, +6.2% explained variance).

> **The corpus proposes a "slope shallower than −0.5 NRS/day over POD 1–5" rule. Reject it.** The two class slopes differ by only 0.137 NRS/day and −0.5 sits essentially on top of C1's slope, so that threshold splits the high-risk class roughly in half. The classes separate on **intercept** (6.96 vs 5.63, a 1.3-point gap). **Implement the class prior from pre-op NRS + PCS (the published ORs) and the POD-1 intercept**, not the slope. And note the classes are 45/55 — this is not a rare tail. Do not emit an alert on class membership; use it to **shift the expected curve** and to set the check-in cadence.

Derived features to compute and store deterministically (no LLM):
- `pain_intercept_pod1`, `pain_slope_pod1_5`
- `days_to_PASS` — first day NRS ≤3 and stays there. ARCR benchmark POD 2 for low-catastrophizing patients; failure within week 1 flags the catastrophizing phenotype.
- `nrs_at_pod3, pod7, pod14, pod30` — the four days with published association to chronic post-surgical pain after TKA. Down-weight POD 0–2 (does not predict CPSP after THA).

CPSP base rates for calibration: TKA 8–34% (~20%), THA ~10%, ARCR 24% at 6 months, ACLR up to 26% at 2 years, lumbar fusion ~20%.

ARCR uses a **strictly monotone** curve — no rebound: VAS recovery 43.7% at 3 mo, 69.9% at 6 mo, ~85% at 12 mo.

### 4.4.3 Opioid module

`backend/app/clinical/opioid.py`. Store `cumulative_MME`, `MME_per_day`, `days_since_last_dose`. Conversions: oxycodone 5 mg = 7.5 OME; hydrocodone 5 mg = 5 OME.

Per-procedure consumption envelopes:

| Procedure | Prescribed | Consumed | Window | Cap (Michigan OPEN, opioid-naive) |
|---|---|---|---|---|
| TKA | 88.4 pills / 632 mg OME | **65.0 pills / 416 mg OME** | 6 weeks | **0–40** oxycodone 5 mg tabs |
| THA | 64.0 pills | **29.8 pills** | 12 weeks | **0–30** tabs |
| ACLR | median 15 | **median 2** (38% take zero; 96% ≤15) | — | — |
| ARCR | — | ~90 MME (~12 tabs) | — | — |
| Shoulder arthroplasty | — | ~67.5 MME (~9 tabs) | — | — |

> **Do not encode "TKA patients consume 75% of prescription, THA 50%" as a procedure effect.** TKA's ratio is measured at 6 weeks and THA's at 12 weeks, from different study subsets — the gap is a measurement artifact. Also note the 88.4-pill TKA baseline predates the Michigan OPEN reductions (which cut prescription size 76% with no change in pain or satisfaction), so it is a historical, not current, norm.

Weaning ladder (day-indexed, all thresholds product-defined and labeled as such):

| Day | Condition | Code | Tier |
|---|---|---|---|
| POD 30 | still taking daily opioids (median cessation POD 30, 95% CI 29–31) | `OPIOID_BEYOND_MEDIAN` | WATCH |
| POD 42 | still taking daily opioids | `OPIOID_BEYOND_6WK` | CONTACT |
| POD 90–180 | any fill in an opioid-naive patient | `OPIOID_NEW_PERSISTENT` | formal flag |

Brummett definition is the one to name in the schema: fill between 90 and 180 days post-op in an opioid-naive adult; incidence **5.9% minor / 6.5% major vs 0.4% in non-surgical controls**. **But Brummett's own conclusion is that persistence is *not* significantly different between minor and major surgery — it tracks behavioral and pain disorders.** Do not encode minor-vs-major as a stratifier. Encode instead: tobacco, substance-use disorder, mood disorders, anxiety, pre-op back/neck pain, arthritis, centralized pain. Pooled persistence at 3 months: **TKA 26%, THA 20%**; at 6 months 20%/17%. (The 12-month figures are non-monotonic and one has an implausibly narrow CI — use 3- and 6-month for calibration only.)

Risk modifiers that shift the expected MME curve rather than fire alerts: prior narcotic use **+86% MME**, benzodiazepine **+81%**, smoking **+90%**, tramadol-only **+38%**; depression OR 1.27–1.59; pre-op opioid fill OR up to 4.34; **pre-op acetaminophen use OR 2.05** (surfaced by the SORG-MLA external validation and absent from the corpus's own risk list — cheap to capture from a med list).

**Refuse to encode CDC MME caps as hard blocks.** The 2022 CDC guideline removed day-supply and MME/day caps from the formal recommendations. Keep 50 and 90 MME/day as advisory review triggers with provenance labels, and put state day-supply limits in a **per-state configuration table** (~half of states retain a 7-day initial acute-pain limit).

### 4.4.4 VTE prophylaxis adherence

A medication-adherence subsystem distinct from `engine/adherence.py`'s exercise-session rate. Window **14–35 days** (THA long end, TKA short). Regimens: aspirin 81 mg qd or bid; rivaroxaban 10 mg qd; enoxaparin 40 mg qd; **EPCAT II hybrid** — rivaroxaban 10 mg to POD 5, then aspirin 81 mg for 9 more days (TKA) or 30 more days (THA).

Two distinct alert classes, because the corpus distinguishes them: **17.0% non-adherence overall — 13.9% missed ≥1 dose, and 3.1% took MORE than prescribed.** Over-anticoagulation is a bleeding-risk class, not an adherence miss. Emit `VTE_PROPHYLAXIS_MISSED` and `VTE_PROPHYLAXIS_OVERTAKEN` separately.

The live controversy the product must be able to state without taking a side: EPCAT II found aspirin non-inferior; **CRISTAL (n=9,711, cluster-randomized) found aspirin 100 mg INFERIOR to enoxaparin 40 mg** for 90-day symptomatic VTE; the 2022 ICM recommended aspirin 81 mg bid for standard-risk patients. Render all three. A surgeon who sees the product state one side as settled will stop trusting it.

Antibiotic prophylaxis is a **perioperative event record**, not a home medication: cefazolin IV within 60 min of incision; 1 g <80 kg, 2 g 80–120 kg, 3 g ≥120 kg; discontinue within 24 h.

### 4.4.5 Sleep: a documented negative result to respect

**Do not build a pain proxy on wearable total sleep time.** Gibian et al. (J Arthroplasty 2023, n=110) found recorded sleep duration unchanged at 30/60/90 days and uncorrelated with VAS at every timepoint. Build on **fragmentation, efficiency, WASO, awakening count, deep-sleep fraction (reduced only in post-op week 1), and daytime-nap fraction**.

The corpus undersells one positive result: **patient-reported sleep quality DID track pain** — patients rating sleep "very bad" had significantly worse VAS than those rating it "bad" at 30 days. So: drop objective duration as a pain proxy; keep a one-item subjective sleep-quality question in the daily check-in. Expect subjective sleep to trough at ~30 days and normalize by 90 — that trough is physiologic and must not alert.

HRV-pain coupling: **do not ship.** Published direction is inconsistent (HF-HRV inversely predicts post-op pain and adds 18% of variance in one study; higher RMSSD/pNN50/HF associates with *higher* pain in another; a scoping review calls the link unestablished). Build the internal validation harness, gate the feature behind it.

---

## 4.5 PROMs — an analytics feature and a compliance product surface

### 4.5.1 Instrument per procedure

| Procedure | Primary | Secondary | License |
|---|---|---|---|
| TKA | **KOOS JR** (7 items, 0–100, higher better) | PROMIS-10 / VR-12 | free (HSS) |
| THA | **HOOS JR** (6 items, 0–100) | PROMIS-10 / VR-12 | free |
| ACL | IKDC-SKF, Lysholm, Tegner, KOOS | PROMIS PF/PI/Depression CAT | free |
| Rotator cuff | ASES (0–100), SANE | QuickDASH (**inverted direction**) | free |
| Lumbar | ODI (0–100%, **higher = worse**) | NRS back / leg | free |
| Ankle | FAAM ADL + Sports | PROMIS PF | free |
| Meniscus | KOOS JR, IKDC | — | free |

**Licensing guardrails: ship KOOS/HOOS/JR versions, PROMIS, ASES, FAAM, DASH/QuickDASH, ODI, Lysholm, SANE, VR-12 (all free). Do not ship WOMAC (per-study license — derive its subscores from full KOOS/HOOS instead). Oxford scores and SF-12/EQ-5D-5L require license agreements before inclusion.**

### 4.5.2 The threshold table

```sql
CREATE TABLE prom_thresholds (
  instrument      TEXT NOT NULL,
  subscale        TEXT,
  procedure       TEXT NOT NULL,
  timepoint_days  INTEGER NOT NULL,       -- nominal follow-up
  method          TEXT NOT NULL,          -- anchor|distribution|roc
  mcid            REAL, scb REAL, pass_value REAL, mdc REAL,
  score_min       REAL NOT NULL, score_max REAL NOT NULL,
  higher_better   BOOLEAN NOT NULL,
  citation        TEXT NOT NULL, grade TEXT NOT NULL,
  PRIMARY KEY (instrument, subscale, procedure, timepoint_days, method)
);
```

Seed values (anchor-based only; **never expose distribution-based MCIDs as clinical claims** — they fall below MDC):

| Instrument | MCID | SCB | PASS | MDC | Note |
|---|---|---|---|---|---|
| KOOS JR | anchor 14.0–30.7 | **20** (CMS) | 63.7–71.0 | 7–16 across HOOS/KOOS | distribution MCID 4.0–8.7 = below noise floor |
| HOOS JR | anchor 14.8–38.1 | **22** (CMS) | 73.5–81.0 | 7–16 | " |
| ODI | **12.8** | — | ≤18.1 @6 mo, ≤15.3 @2 yr | — | n=454 (not 497); MDC-derived, not anchor; companions SF-36 PCS 4.9, back pain 1.2, leg pain 1.6 |
| ASES | **11.1** | **17.5** | **86.7** | — | ARCR ~1 yr |
| SANE | 16.9 | — | — | — | ARCR |
| IKDC | *unverified* | — | **75.9** (Muller) | — | see below |
| FAAM ADL / Sports | 8 / 9 | — | — | 5.7 / 12.3 | 2005 derivation |
| PROMIS PF / PI | ~4–7 T-points | — | — | — | procedure-specific |

> **Corrections.** IKDC MCID 13.8 is **unverified** (published values span ~6–17); ship PASS 75.9 and leave MCID null until sourced. Lysholm MCID 9.9 and Tegner 0.5 are **unverified**; commonly cited are 8.9 and 1 — and a 0.5 MCID on an integer ordinal scale is an engineering red flag, since no single respondent can move by 0.5. EQ-5D-5L MCIDs are unverified and the index floor is value-set dependent (US ≈ −0.57, not a universal −0.6) — store range per country value set.
>
> **Thresholds are diagnosis-, timepoint-, and demographically conditioned.** Meniscectomy KOOS JR MCID is 10.7 at 6–7 months and 25.2 at 1 year. Younger men after THA required larger change scores; older women after TKA had higher PASS thresholds. A single stored PASS per instrument — even within one procedure — is indefensible. The primary key above is the design response.

Per capture, compute three booleans plus the threshold-set identifier: `delta_ge_mcid`, `delta_ge_scb`, `absolute_ge_pass`. Normalize direction at ingestion — store a 0–100 higher-is-better value alongside the raw score, because ODI/NDI/DASH/WOMAC invert.

### 4.5.3 Collection schedule

Pre-op (in-clinic tablet — the highest-yield single tactic), 2 wk, 6 wk, 3 mo, 6 mo, 12 mo, then annually at 10–14-month spacing (ICHOM). Add 9 months for ACL/meniscus (return-to-sport). Spine adds 6 wk and 3 mo.

Response-rate reality: portal-only **29–53%**; phone 71.5% vs paper 57.6% vs electronic 53.2%; multimodal reminders with staff follow-up reach **70–95%**. Layer channels push → SMS/email → staff phone call. Target the ISAR ≥60% benchmark and the CMS ≥50% matched-pair floor. (Both of those benchmark figures are flagged unverified in the corpus — cite them internally, not to customers, until sourced.) Monitor completion by age and race subgroups; very young, very old, and non-White patients respond less, and the compliance gap becomes a measured equity signal.

### 4.5.4 CMS THA/TKA PRO-PM — this is a compliance product, not analytics

Encode a state machine per THA/TKA episode in `backend/app/clinical/propm.py`:

- **Eligibility:** elective primary THA/TKA, inpatient, **Medicare FFS Parts A and B continuously enrolled for the 12 months prior to admission** (this lookback is load-bearing and the corpus omits it entirely); exclusions: revisions, fractures, malignancy, partial procedures, **staged procedures**. The age ≥65 criterion is unconfirmed — do not filter on it without the rule text.
- **Windows:** pre-op `[surgery_date − 90d, surgery_date]`; post-op `[surgery_date + 300d, surgery_date + 425d]`.
- **Bundle:** HOOS JR (hip) or KOOS JR (knee) **plus** PROMIS-Global or VR-12, SILS-2, and the Oswestry back-pain items — at **both** timepoints, or the pair does not count.
- **Completeness:** matched pairs on **≥50%** of eligible patients; **≥25 matched pairs** required for a reportable risk-standardized rate.
- **SCB thresholds:** KOOS JR **≥20**-point improvement; HOOS JR **≥22**.
- **Deadlines:** the mandatory cohort (procedures 7/1/2024–6/30/2025) had a **pre-op submission deadline of 9/30/2025** and post-op due **9/30/2026**.

> **Adjudication with commercial consequences.** As of today (2026-07-31) **the pre-op deadline for the first mandatory cohort has already passed.** A hospital onboarding now cannot retroactively satisfy it. The pitch is therefore *"we guarantee your next cohort,"* not *"we fix your current exposure."* Additionally, the FY2027-vs-FY2028 payment-determination year is contested across secondary sources and neither is a primary rule citation — **do not put a fiscal-year payment claim in customer-facing material.** The procedure window and the 50% threshold are the parts that consistently corroborate. The outpatient/ASC dates (procedures CY2027, CY2030 payment) are unverified.

Emit typed codes the risk tier and RTM layer both consume: `CMS_PREOP_WINDOW_OPEN`, `CMS_PREOP_WINDOW_CLOSING_7D`, `CMS_PREOP_MISSED`, `CMS_POSTOP_WINDOW_OPEN`, `CMS_POSTOP_WINDOW_CLOSING_30D`, `CMS_PAIR_COMPLETE`, `COMPLETENESS_BELOW_50PCT`, `PROM_BELOW_PASS`, `PROM_SCB_ACHIEVED`.

`CMS_PREOP_WINDOW_CLOSING_7D` is the single highest-ROI notification in the entire product. It is deterministic, it has zero false positives, and missing it costs the hospital a quarter of its market-basket update.

---

## 4.6 Risk factors and pre-op optimization as first-class fields

`backend/app/models/riskprofile.py` — one versioned record per patient, computed once pre-operatively.

### 4.6.1 Re-implementable vs proprietary

| Tool | Status | Discrimination (best use) | Action |
|---|---|---|---|
| **RAPT** | fully open, 6 items, 1–12 | non-home discharge **AUC 0.772**; complications 0.535 | re-implement natively |
| **mFI-5** | open, 5 binaries | non-home discharge **AUC 0.720**; complications 0.525 | re-implement |
| **Charlson / Quan ICD-10** | open, weights 1/2/3/6 | non-home discharge 0.729; complications 0.645 | re-implement |
| **Elixhauser + van Walraven** | open; AHRQ ICD-10 software free | in-hospital death **c 0.763** (Ontario, n=345,795) | re-implement |
| **LACE** | open, max 19 | 30-day death/readmission c **0.684** external | re-implement, calibrate cut locally |
| **HOSPITAL** | open, 7 items | c 0.72 — **derived in medical, not surgical, patients** | optional |
| **ASA class** | open | model c **0.74** mortality (not 0.79/0.82) | capture |
| **Tan PJI score** | integer weights published, 17 factors | AUC 0.83/0.84 — **calibrated only below 3–4% predicted risk** | capture inputs; do not surface a probability |
| **ACS NSQIP SRC** | **coefficients never published**; live tool is v4.0.4, params updated April 2026, undocumented | PJI 0.743 (30 d) / 0.713 (90 d); 90-day readmission 0.63 | **deep-link only**; if you record an output, record retrieval date + version string |

RAPT items and weights, verbatim: age 50–65 = 2, 65–75 = 1, >75 = 0; male = 2, female = 1; walks ≥2 blocks = 2, 1–2 = 1, housebound = 0; no gait aid = 2, single stick = 1, crutches/frame = 0; community support none-or-≤1×/wk = 1, ≥2×/wk = 0; caregiver at home = 3, none = 0. Bands >9 low / 6–9 intermediate / <6 high. Non-home discharge by band: **1.63% / 9.95% (OR 4.87) / 37.2% (OR 27.2)**. The intermediate band is only 62.3% accurate — that is exactly where longitudinal monitoring adds value, and it should be the enrollment target.

mFI-5 items: non-independent functional status; diabetes; COPD or current pneumonia; CHF within 30 days; hypertension requiring medication.

> **Blunt adjudication the corpus half-concedes but never states.** The 858-patient ERAS cohort that underpins three separate claims is **one paper, one academic center**, and its own conclusion is that these indices are "poor independent predictors of complications, readmissions, and prolonged length of stay (all AUC < 0.7)." So: **use RAPT/mFI-5/CCI to set the starting tier for roughly the first 72 hours** — while the coverage gate is still failing on thin sensor history — **and let deviations dominate thereafter.** Do not present them as a complication engine, and do not present RAPT/mFI-5/CCI comparisons as replicated. Also: Oldmeadow's RAPT validation set was **130 patients**, not 650.

### 4.6.2 Modifiable pre-op thresholds — each emits `OPTIMIZATION_GAP`

| Field | Threshold | Effect size |
|---|---|---|
| BMI | <40 kg/m² | morbid obesity PJI OR 3.27–4.33; 15-yr absolute PJI risk 1% normal → 2% class III → 4% class IV |
| HbA1c | ≤7.5% (**store the raw value** — 7.5 vs 7.7 vs 8.0 is actively argued) | ≥7.5% deep infection **OR 2.6 (1.9–3.4)** |
| Albumin | ≥3.5 g/dL | any complication 7.3% vs 4.0%, adjusted **RR 1.5**; revision: 4.32× wound infection |
| Hemoglobin | >12 g/dL F, >13 g/dL M | pre-op anemia ~15% TKA, ~23% THA, 46.6% revision |
| Smoking | cessation ≥4 weeks pre-op | opioid OR 1.34–2.09; MME +90% |
| Pre-op opioids | ≥50% reduction by 4 weeks pre-op | MME +86% |
| S. aureus | carrier status + decolonization-completed flag | mupirocin: S. aureus SSI **RR 0.67**, nasal colonization RR 0.22; ortho SSI RR 0.80 |
| **Pre-op CRP** | **>5 mg/L** | predicts later septic revision after TKA (Windisch 2017) — cheap and currently discarded |
| Pre-op NRS + PCS | PCS >30 clinically relevant; >20 gives OR 3.5 for pain >30/100 at 1 yr | pre-op NRS **OR 3.546** for the persistent-pain class |
| SDOH | 9-digit-ZIP ADI percentile, payer, rurality, prior 6-mo ED visits (also LACE's E term), caregiver availability | periprosthetic fracture **OR 2.07**; readmission HR 1.74; ED HR 1.83 |

CSI ≥40 is capturable but flag it as a **fibromyalgia-derived cutoff** contested in orthopedic populations. **Never use the revision-TKA dissatisfaction OR of 39.081 as a coefficient** — 95% CI 6.9–220.5 from n=68 total.

Capture all 21 ACS NSQIP inputs regardless — they simultaneously feed CCI, Elixhauser, mFI-5, and any future in-house model.

---

## 4.7 The surgeon's attention budget

The constraint set, stated as engineering requirements:

- Direct surgeon–patient time is roughly **8 minutes** per encounter (the specific 7 min 52 s median is unverified — the constraint holds regardless), at 30–50 patients/day.
- Clinicians override **49–96%** of interruptive CDS alerts; 88.2% of even "very severe" DDI alerts; ~4 of 5 overrides are judged *clinically appropriate* — the alerts were wrong, not the clinicians.
- CPOE alert PPVs run **below 20%, as low as 5%**.
- PCPs already absorb ~77 EHR notifications/day; specialists ~29.
- **72–99%** of continuous physiologic monitor alarms are false or non-actionable.
- The people who actually review RTM data are **care navigators (licensed PTAs) and treating therapists**, not surgeons.

Therefore:

**The worklist must show, per patient, in one glance:** tier + confidence, the **top 3 typed reason codes with their raw values and post-op day**, days remaining in the episode window, and the last review timestamp. Nothing else above the fold. Target: a navigator parses a row in <10 seconds and a surgeon parses an escalation card in <30.

**The escalation ladder must be three-tiered, never binary:** `WATCH` (navigator queue, no notification), `CONTACT` (navigator calls today, logged as RTM interactive communication), `ESCALATE` (surgeon-visible). Only `ESCALATE` produces a push.

**Delivery is a once-daily digest.** Never interruptive per-event pings. The current `pipeline.py` behavior — firing `notify_high_priority` on any not-HIGH → HIGH edge with no hysteresis (gap G7) — will reproduce hospital telemetry alarm fatigue exactly. Add: ≥2 consecutive days out-of-control, multi-signal concordance, and a per-patient cool-down after acknowledgment.

**Instrument the precision budget.** Persist rolling PPV, number-needed-to-evaluate, and acknowledged-vs-dismissed rate **per reason code**. Target PPV ≥20–30% for anything that reaches a surgeon. Treat a sustained decline in appropriate-response rate as an SLO violation that auto-tightens thresholds — that is the only operational definition of alert fatigue the literature offers.

**What the product must never do:**
1. Never send an interruptive alert whose published NNE exceeds ~10 (that is the Epic Sepsis Model's operating point, and it destroyed clinician trust permanently).
2. Never present a PJI point probability. Externally validated PJI models are calibrated only below 3–4% predicted risk (Tan slope 0.51, Del Toro 0.74, Bülow 1.23).
3. Never show a model output without its calibration metadata (c-statistic, intercept, slope, Brier, derivation cohort, validation cohort) available one click away.
4. Never require more than one patient task per day.
5. Never route a first-pass review to a surgeon. Build the packet for the navigator tier; the surgeon sees escalations only.
6. Never claim earlier complication detection from consumer wearables. **Nobody has demonstrated it** — not mymobility (n=452 RCT: PT use 94.4% vs 59.3%, ED visits 8.2% vs 2.5%, but **90-day KOOS JR was significantly *worse* in the app arm, 70.4 vs 73.6, p=0.026**), not the Mayo RPM comparative study (30-day readmission 19.7% vs 20.7%, p=0.84; no difference in DVT/PE/SSI/UTI/pneumonia). Position as *surveillance and PT substitution*, not detection.
7. Never treat week-5 data sparsity as anomalous. Device compliance falls **84% → 46–52% by week 6** (~5–6 points/week). Encode that decay curve as the coverage gate's prior (fixes gap G4's cousin), weight passive channels (<1% missing) above active tasks (PROMs ~16% missing, thrice-daily exercise 32% compliance).

**Log "data was reviewed" as a first-class audit record.** It is simultaneously the RTM billing evidence trail, the medico-legal defense (patients assume a human is watching — that is their stated value proposition), and a trust signal to display back to the patient.

### 4.7.1 The narrative contract — what the engine is allowed to say

The clinical layer owns the vocabulary; `llm/` renders only from reason codes plus raw numbers. Per code, define four fields in `clinical/phrasing.py`:

| Field | Example (`WOUND_MODHEAVY_WEEK3`) |
|---|---|
| `surgeon_line` (≤12 words) | "Moderate drainage, POD 19. Reference PPV 83%." |
| `navigator_script` | "Call today. Confirm drainage volume, dressing changes since Friday, fever, and current antibiotic status." |
| `patient_line` | "Your care team wants to look at your incision today — please expect a call." |
| `forbidden` | "infection", "infected", "PJI", "you have", "diagnosis", "likely" |

Extend the existing banned-diagnostic-language filter in `llm/` with the per-code `forbidden` list, and keep the mandatory guardrail sentence (`GUARDRAIL_SENTENCE` in `models/enums.py`). The LLM's job is tone and assembly. It must not select which finding matters — that is `clinical/`'s job, deterministically.

---

## 4.8 The commercial frame

### 4.8.1 CMS TEAM — mandatory since January 1, 2026

~700–741 hospitals in 188 CBSAs, two-sided risk, **30-day** episodes, five episode families including LEJR, SHFFT, and spinal fusion. Runs PY1–PY5 through 2030. BPCI-Advanced ended December 31, 2025; CJR ended earlier. **TEAM is the only mandatory bundle.**

- LEJR episodes = IPPS discharge under MS-DRG **469, 470, 521, or 522** plus OPPS-billed anchor procedures. (The corpus omits 521/522 — hip/knee replacement with a principal diagnosis of hip fracture — which undercounts the population.)
- Target price: rolling 3-year regional baseline, HCC v28 risk adjustment, **2.0% built-in CMS discount on LEJR/SHFFT/FUSION**. Milliman's worked DRG-469 example: $20,000 baseline year 1 → $25,000 baseline year 3.
- **Track corridors (corrected):** Track 1 stop-gain **10%**, no downside; **Track 2 ±5%** (the corpus says ±10% — wrong); Track 3 ±20%. PY2–5 default assignment is **Track 3** unless CMS approves otherwise.
- **CQS multiplier (corrected):** Track 1 up to +10% on positive amounts only; Track 2 +10%/−15%; **Track 3 +10%/−10%**. Modeling −15% relief for a Track 3 hospital overstates the quality lever by 50%.
- **Quality measure set changes at PY2.** PY1: Hybrid HWR, PSI-90, THA/TKA PRO-PM. Per the FY2026 IPPS final rule (90 FR 37204, Aug 4 2025), PSI-90 drops after PY1 and Hospital Harm–Falls with Injury, Hospital Harm–Postoperative Respiratory Failure, and Failure-to-Rescue are added for PY2+, with Information Transfer PRO-PM added PY3–5. **The THA/TKA PRO-PM persists PY1–PY5 for LEJR** — which is why the PRO-PM subsystem is the durable hook. Scoring is percentile benchmarking against a national cohort, not fixed point weights.
- **Post-episode guardrail (42 CFR 512.550(f)):** average 30-day post-episode spending more than 3 SD above regional average is subtracted from the reconciliation amount and is **not** protected by stop-loss. Hospitals cannot push cost to day 31. Day-31–60 utilization data is financially relevant — an argument for the TKA 365-day surveillance tail.
- **Episode day 0 quirk:** if an anchor hospitalization begins the same day as or within 3 days after an outpatient procedure of the same category, the episode starts at the *outpatient* procedure date. Get this right in analytics timestamping.

### 4.8.2 Episode cost structure — the four line items monitoring can move

| Line item | Amount | Incidence |
|---|---|---|
| 90-day LEJR episode | median TKA **$15,587**; CJR-era averages $20,000–25,000 | — |
| Post-acute care share | **~25–40%** of episode; median PAC $3,817–4,195 | — |
| SNF/IRF vs home | **>$20,000** per facility stay vs ~$0 marginal at home; CJR participants moved ~50% → ~10% SNF discharge; 2026 SNF coinsurance days 21–100 = **$217.00/day** | — |
| 30/90-day readmission | $9,335 avg (bundled-payment analysis) to $45k–52k for surgical-complication readmissions | 90-day 5.6–12.7% |
| **PJI** | **$38,865** (two-stage succeeds) to **$79,223** (further revision required); $1.85B national by 2030 | 1–2% |
| MUA / stiffness | revision-for-stiffness **$65,771** vs $48,287 non-stiff (≈$17.5k delta) | MUA ~4% of TKA |

Within 90 days post-TKA, Medicare spends >$3,000/patient of which >$2,500 is outpatient services and **83% of that is physical therapy** — the exact spend RTM-guided home exercise substitutes for. That is the mymobility result (PT visits 9.75 → 5.40; ~$186/patient net 90-day cost reduction, JMIR 2025) and it is the only peer-reviewed economic claim in this space.

**One PJI inside the 30-day TEAM window wipes out the reconciliation surplus of 20–40 clean episodes.** That is the actuarial argument, and it is worth making even though the detection claim is not yet supportable — the framing is *"surveillance plus documented review,"* not *"we catch it."*

### 4.8.3 RTM revenue math per patient (CY2026, non-facility national averages, GPCI-varying)

| Code | Description | ~Rate |
|---|---|---|
| 98975 | initial setup + patient education, once per episode | $22 |
| 98977 | **MSK** device supply, 16–30 days of data per 30-day period | $40 |
| **98985** | **MSK** device supply, **2–15 days** per 30-day period (new 2026) | $51–52 |
| 98979 | treatment management, **10–19 min**/month, ≥1 real-time interactive communication (new 2026) | $26 |
| 98980 | treatment management, first 20 min/calendar month, ≥1 interactive communication | $54 |
| 98981 | each additional 20 min | $41 |

> **Correction:** 98984 = respiratory, **98985 = musculoskeletal**, 98986 = CBT. An MSK program bills **98985**, not 98984. The corpus's revenue example uses the wrong code.

Per Medicare TJA patient on a 90-day program: `98975 ×1 ($22) + 98977 ×3 ($120) + 98980 ×3 ($162) + 98981 ×1–3 ($41–123)` = **~$345–427 direct billing**. At 500 TJA/yr: **~$170k–210k/yr gross**. The 2026 change that matters most: patients who drop out early now yield **$51–52 per period via 98985 instead of $0** — which is exactly the population the 84%→46% wear-decay curve produces.

Hard billing constraints to encode as engine state: device-supply codes once per 30-day period regardless of device count; management codes once per calendar month; **cannot bill 98979 and 98980 in the same month**; cannot combine 2–15-day and 16–30-day supply codes; cannot bill RPM and RTM concurrently for the same patient in the same month; one practitioner per period; consent captured with timestamp and method; 20% Part B coinsurance (~$8–11/month) disclosed at enrollment.

**The three-legged pitch:** (1) direct RTM billing $345–427/patient; (2) TEAM reconciliation from avoided PAC, readmissions, and complications, against a target price that already embeds a 2% discount; (3) PRO-PM compliance protecting both the IQR annual payment update and the TEAM CQS multiplier. Leg 3 is the one no competitor's vitals dashboard can claim, and it is deterministic software.

---

## 4.9 Order of work

**Phase 0 — ship now (2–3 weeks). No new data, no ML, no model risk.**
1. `clinical/wound.py` + `models/wound.py` + daily one-question capture (app + SMS). Week-conditional ladder, de-escalation lane, NNE published per rule.
2. Route `PAIN_NRS`, `RANGE_OF_MOTION`, `THERAPY_ADHERENCE`, `PROM_SCORE` into `ANALYZED_METRICS`. Fixes gap G5 and the RTM substance-over-form problem.
3. `clinical/pain.py` — anchored non-monotonic curves with the rebound window; `PAIN_ABOVE_EXPECTED` and `PAIN_REESCALATION`.
4. `clinical/propm.py` — the CMS state machine and the `CMS_PREOP_WINDOW_CLOSING_7D` notification.
5. Split `detector_class` TREND vs EVENT; implement the step-cliff rule for dislocation and periprosthetic fracture.
6. Per-procedure `surveillance_horizon_days` (TKA 365 / THA 180) and phase intensities.
7. Three-tier ladder (WATCH/CONTACT/ESCALATE), daily digest, hysteresis, per-code PPV/NNE ledger.

**Phase 1 — 4–8 weeks.**
8. `clinical/clocks.py` with the full milestone tables; replace `engine/curves.py` for TKA/THA/ACL/RC; keep the logistic only for ankle/meniscus, labeled `consensus`.
9. MUA projection (`ROM_MUA_RISK_PROJECTED`, fires POD 21–35).
10. `clinical/riskprofile.py` — RAPT, mFI-5, Charlson/Quan, Elixhauser/van Walraven, LACE, all native Python; pre-op optimization gap codes.
11. `clinical/opioid.py` and `clinical/meds.py` (VTE prophylaxis, missed vs over-taken).
12. `prom_thresholds` table seeded; three clinical-significance booleans per capture.
13. MSIS 2018 / EBJIS 2021 as separately-labeled, inspectable functions.
14. `clinical/phrasing.py` and the extended banned-language filter.

**Phase 2 — gated on data volume. Do not start earlier.**

| Work | Gate | Why that number |
|---|---|---|
| Re-derive week-conditional drainage thresholds locally | **≥1,000 completed 30-day episodes AND ≥15 adjudicated PJI/SSI events** | matches the source cohort's own event count; below it you are re-fitting noise |
| Validate the step-cliff rule for dislocation/fracture | **≥1,500 THA episodes** (≈15 dislocations at 1.1%) | sensitivity/specificity/FP rate are entirely unvalidated today |
| Calibrate the MUA projection threshold | **≥500 TKA episodes** (≈20 MUAs at 4%) | enough events to move off 90°/week-6 if the data disagrees |
| Wearable → above/below-PASS binary classifier | **≥200 matched pre-op + 1-yr PROM pairs per procedure**, plus a temporal holdout | binary AUC 0.62–0.92 is achievable; continuous regression is not |
| Any risk model surfaced to a surgeon | **external or temporal validation with reported calibration intercept, slope, and Brier** | only 10 of 59 published ortho ML models have any external validation, and surgeons know it |
| HRV–pain coupling feature | passes an internal validation harness on our own cohort | published direction is contradictory |

---

## 4.10 What to refuse to build

1. **A PJI probability.** Restrict to deviation surveillance plus a labeled "elevated PJI risk profile" flag. Miscalibration above 3–4% predicted risk is documented for all three published calculators.
2. **A CRPS flag.** Legacy literature claims up to 21%; prospective Budapest-criteria screening of 100 TKA patients found zero. Misdiagnosis is hazardous because it delays infection and loosening workup.
3. **Image-based wound inference.** Store photos; show them to humans; do not classify them. Automated inference on a wound image is a regulatory posture the corpus explicitly flags as unresolved.
4. **A TUG >13.5 s fall alarm.** The meta-analysis usually cited as its source is the paper that *refutes* it: sensitivity 0.32 (0.14–0.57), specificity 0.73 (0.51–0.88), with the authors concluding TUG "should not be used in isolation to identify individuals at high risk of falls." As an alarm it fires on ~27% of non-fallers while missing ~68% of fallers. Capture TUG; use it rule-in only; suppress entirely in the early post-op window where nearly every patient exceeds 13.5 s.
5. **A blended MSIS/EBJIS verdict.** They disagree on the same patient by construction. Show both, labeled.
6. **The 1.34 m/s "good walking outcome" benchmark and the 37% attainment figure.** Not in the paper they are attributed to, and no source could be found. That paper's own headline is the opposite: 79% achieved the gait-speed MCID at 1 year.
7. **Continuous PROM score prediction.** No externally validated model exists. Binary above/below-PASS only, with explicit uncertainty, behind the coverage gate.
8. **Hard hip-precaution rules.** 2.2% vs 2.0% dislocation across 6,900 patients. Surgeon-configurable flag.
9. **Minor-vs-major surgery as an opioid-persistence stratifier.** Brummett's own conclusion contradicts it.
10. **A flat 6MWT MCID of 74.3 m.** The source achieved AUC >0.70 only in lower-baseline walking-ability groups and reports poor discrimination for better-functioning patients. Stratify by baseline quartile or suppress.
11. **Any customer-facing claim of a fiscal-year PRO-PM payment impact** until it is confirmed against the IPPS final rule text.
12. **Any claim that wearables detect complications earlier.** The strongest published RCT in this space showed the app arm's 90-day KOOS JR was significantly *worse*. Sell PT substitution, PRO-PM compliance, documented review, and a wound channel with day-scale lead time. Those are all true.