# Section 2 — Data Acquisition, Ingestion and Signal Processing

## 2.0 Adjudications up front

The corpus contradicts itself in six places that change the design. Resolving them first, because several downstream decisions depend on which number you believe.

| # | Conflict | Ruling |
|---|---|---|
| A1 | Walker step error: `datasources--signal-processing` cites "Apple Watch recorded 2.2±5.6 of 24.7 actual steps in n=23 TKA patients" (PMC11247726). `datasources--VERIFICATIONS` could not locate that study and says the retrievable source is Kooner 2021 in **healthy** individuals. | **Do not use 2.2/24.7.** Use the two verified figures: Apple Watch S8 **−36.4%** with a rolling walker (PeerJ 2026, PMID 42004701, n=42, ages 51–80, DOI 10.7717/peerj.20690 — the −36.4% and p<.001 are confirmed; the "6MWT" framing and the Omron +4.3% are **not** in the abstract) and Fitbit Inspire 3 wrist **31.2%** error pushing a two-wheeled walker vs 1.5% at hip/ankle (IJERPH 22(7):1100, PMID 40724167, n=11). The design conclusion is unchanged; the magnitude is 30–40%, not 91%. |
| A2 | CADENCE: slow-speed MAPE "50.1%", wrist "23%". | **Wrong cohort.** Those are CADENCE-**Kids** (117 youth, mean age 13.1). CADENCE-**Adults** (21 devices, ages 21–85) gives slow-speed (0.8–3.2 km/h) MAPE **40%**, normal speed **7%**, and by location at normal speed **ankle 1% / thigh 1% / waist 3% / wrist 15%**. Use the adults numbers; they are the defensible source for a TKA cohort and they are *gentler*, which matters because we are using them to justify suppression. |
| A3 | Apple walking-asymmetry MDC "2.06–2.12%". | **Mislabelled.** Those are Apple's **double-support-time** MDCs (white paper Table 6; validation 2.12 / 3.18 / 4.51). Apple publishes **no** σ_error and **no** MDC for walking asymmetry — only a classification (35% threshold → PPV 83.4%, FN 9.8%). Coding 2.06% as an asymmetry alarm would be coding a double-support number into an asymmetry gate. **Ship no asymmetry gate.** |
| A4 | "Gait speed barely moves across a year, so it is a poor short-horizon signal." | **Half wrong.** The same Duke cohort (Arthroplasty Today 2025, PMC12398885 — *not* Rothman/J Arthroplasty) shows a real **6-week nadir**: TKA gait speed 0.97 → **0.86 m/s**, THA 0.97 → **0.88**; steps 3,755 → **2,973 ± 1,463** (TKA) and 3,571 → **3,384 ± 1,943** (THA). Gait speed moves ~0.11 m/s, which is *below* Apple's median MDC of 0.14 m/s. So the correct statement is: the signal exists but is smaller than single-day measurement error → **7-day means only, never a single day**. |
| A5 | Fitbit Web API is the Android/Fitbit cloud path. | **Superseded and urgent.** dev.fitbit.com now carries a **September 2026 sunset** notice for the legacy Fitbit Web API, with migration to the **Google Health API** (developers.google.com/health). Today is 2026-07-31. Any design premised on Fitbit intraday endpoints has ~2 months. This kills the HR-sample-count wear proxy as a launch feature and is the single strongest argument for putting an aggregator between us and the vendors. |
| A6 | Choi 2011 non-wear allowance requires 30-min zero windows "upstream AND downstream". | **OR, not AND** (Med Sci Sports Exerc 2011;43(2):357-64). The AND version classifies less non-wear than the published algorithm. Irrelevant at launch (we have no count data) but must be right when we port it. |

Also carried forward from the codebase gap list, and **verified true**: `engine/dataload.py` uses `start_time.date()` not `local_date` (G2), ignores `deleted_at` (G3), and ignores `revision`. `TIER_ORDER` is `{HIGH:0, MEDIUM:1, MISSING_DATA:2, LOW:3}` — MISSING_DATA already outranks LOW; the deployment critic's claim was wrong and is not repeated here.

---

## 2.1 The canonical Observation store

The current `Observation` model is already 70% right. It has `local_date` materialized at ingest, `external_id` / `revision` / `source_updated_at` / `payload_hash` for restatement, `deleted_at` for tombstones, `body_site` / `side`, and a unique `dedupe_key`. What it lacks is (a) a device epoch, (b) value semantics, (c) an append-only revision chain, and (d) the surrounding tables that make a step count interpretable.

### 2.1.1 New enums

```python
# app/models/enums.py

class ValueSemantics(StrEnum):
    ABSOLUTE = "absolute"              # value is on the metric's natural scale
    BASELINE_DELTA = "baseline_delta"  # vendor already subtracted ITS OWN baseline
    VENDOR_SCORE = "vendor_score"      # proprietary index (readiness, steadiness) — no units

class Provenance(StrEnum):
    MEASURED = "measured"              # sensor-derived, unmodified
    VENDOR_DERIVED = "vendor_derived"  # vendor model output (sleep stages, RHR, steadiness)
    IMPUTED = "imputed"                # WE filled it — display only, NEVER detection
    EXTRAPOLATED = "extrapolated"

class ArrivalClass(StrEnum):
    LIVE = "live"                # webhook within the freshness SLA
    BACKFILL = "backfill"        # historical pull on connect / trailing sweep
    RESTATEMENT = "restatement"  # provider changed a value we already held

class WearLocation(StrEnum):
    WRIST_DOMINANT = "wrist_dominant"
    WRIST_NONDOMINANT = "wrist_nondominant"
    FINGER = "finger"
    HIP = "hip"          # iPhone in pocket/clip — the only placement Apple validated
    CHEST = "chest"
    UNKNOWN = "unknown"

class AssistiveDeviceType(StrEnum):
    NONE = "none"
    CANE = "cane"                        # −1.9% step error — no suppression needed
    CRUTCHES_FOREARM = "crutches_forearm"
    CRUTCHES_AXILLARY = "crutches_axillary"
    WALKER = "walker"                    # both hands fixed to frame — 31–36% error
    ROLLATOR = "rollator"
    WHEELCHAIR = "wheelchair"
    UNKNOWN = "unknown"

class SurgicalEventType(StrEnum):
    INDEX = "index"
    CONTRALATERAL = "contralateral"      # the other knee/hip — resets everything
    REVISION = "revision"
    MANIPULATION = "manipulation"        # MUA under anesthesia
    IRRIGATION_DEBRIDEMENT = "i_and_d"
    UNRELATED = "unrelated"
```

### 2.1.2 `device_epochs` — the unit that owns a baseline

**Why load-bearing:** shaker-table MAE is 16.9 mg (ActiGraph) / 21.6 (Apple) / 22.0 (Fitbit) / **32.5 (Garmin)**, and free-living step totals differ by **24 percentage points** between Fitbit (+18.0%) and Oura (−6.2%) against the same reference. Nocturnal RMSSD limits of agreement are **−11.43 to +6.43 ms (Oura Gen3)**, **−12.50 to +10.94 (WHOOP)**, **−15.22 to +11.60 (Garmin Fenix 6)**, **−14.30 to +23.60 (Polar Grit X Pro)** — a 38 ms span for Polar. There is no defensible cross-brand conversion. A device change is therefore an **episode boundary**, not a continuation. Firmware matters too: Apple moved SpO2 computation to the paired iPhone in watchOS 11.6.1 / iOS 18.6.1 (2025-08-14), which changes the HealthKit source device and sync latency.

```python
class DeviceEpoch(Base):
    __tablename__ = "device_epochs"
    __table_args__ = (Index("ix_epoch_patient_open", "patient_id", "ended_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    source_provider: Mapped[SourceProvider] = mapped_column(String)
    api_channel: Mapped[str] = mapped_column(String)       # "junction" | "healthkit" | "google_health"
    device_model: Mapped[str] = mapped_column(String)      # "Apple Watch Series 10"
    firmware_version: Mapped[str | None] = mapped_column(String, nullable=True)
    os_version: Mapped[str | None] = mapped_column(String, nullable=True)
    wear_location: Mapped[WearLocation] = mapped_column(String, default=WearLocation.UNKNOWN)
    # HRV/temp contracts are per-device, not per-provider — they gate comparability.
    hrv_statistic: Mapped[str | None] = mapped_column(String, nullable=True)   # "sdnn"|"rmssd"
    hrv_sampling_window_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 300 Oura
    hrv_sampling_context: Mapped[str | None] = mapped_column(String, nullable=True)
    #   "sleep_full" (Oura/Garmin) | "sleep_last_sws" (WHOOP) | "sleep_first_4h" (Polar)
    #   | "sleep_background" (Apple watchOS 11 Vitals) | "unknown_24h" (Garmin RHR — excluded)
    temp_semantics: Mapped[ValueSemantics | None] = mapped_column(String, nullable=True)
    # Device measurement noise, in the metric's own units, used as a variance FLOOR.
    noise_sd: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    baseline_state: Mapped[str] = mapped_column(String, default="warming")  # warming|established|superseded
```

Seed `noise_sd` from the paired-difference SDs in Physiological Reports 2025 (PMC12367097, 536 nights, Polar H10 1000 Hz reference):

```python
DEVICE_NOISE_SD = {  # SD of the paired difference vs ECG — the irreducible floor
    ("oura", "gen4"):   {"hrv_rmssd": 5.52, "resting_hr": 1.43},
    ("oura", "gen3"):   {"hrv_rmssd": 4.56, "resting_hr": 1.00},
    ("whoop", "4.0"):   {"hrv_rmssd": 5.98, "resting_hr": 1.69},
    ("garmin", "fenix6"): {"hrv_rmssd": 6.86},   # RHR excluded: undisclosed timestamp semantics
    ("polar", "gritxpro"): {"hrv_rmssd": 9.67, "resting_hr": 2.13},
}
```

Control limits then use `σ_eff = sqrt(σ_personal² + σ_device²)`. This is a one-line change in `baseline.py` that replaces the current arbitrary relative SD floor (0.06) with a physically-grounded one, and it automatically makes Polar patients alert less than Oura patients — which is correct.

**Rule: on a new device epoch, reset EWMA and CUSUM state, mark the prior personal baseline `superseded`, and re-enter the shrinkage warm-up.** Do not attempt a conversion factor.

### 2.1.3 `Observation` — columns to add

```python
# app/models/observation.py — added columns

    device_epoch_id: Mapped[int | None] = mapped_column(
        ForeignKey("device_epochs.id"), index=True, nullable=True)

    # A delta metric IS ALREADY a deviation. compute_baseline() on it double-centers
    # and suppresses real fever signal. This column is what stops that.
    value_semantics: Mapped[ValueSemantics] = mapped_column(
        String, default=ValueSemantics.ABSOLUTE)

    # Detection reads MEASURED + VENDOR_DERIVED only. IMPUTED is display-only.
    provenance: Mapped[Provenance] = mapped_column(String, default=Provenance.MEASURED)
    arrival_class: Mapped[ArrivalClass] = mapped_column(String, default=ArrivalClass.LIVE)

    # Sleep-linked metrics belong to a noon-to-noon LOCAL window (GGIR includenightcrit),
    # not a calendar day — otherwise a 23:40→06:20 sleep episode splits across two rows.
    sleep_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # Bitemporal: (start_time, end_time) is VALID time; (ingested_at, superseded_at) is
    # DECISION time. Required to reconstruct what the engine saw when it emitted a
    # statement that was billed under 98980.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("observations.id"), nullable=True)
    restatement_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    tombstone_source: Mapped[str | None] = mapped_column(String, nullable=True)
    #   "provider" | "patient" | "ops_plausibility" | "ops_manual"

    # Ingestion-time plausibility results; never silently drop a row.
    quality_flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
```

And change the uniqueness contract from update-in-place to append-only:

```python
__table_args__ = (
    Index("ix_obs_patient_metric_localdate", "patient_id", "metric_type", "local_date"),
    Index("ix_obs_patient_epoch_time", "patient_id", "device_epoch_id", "start_time"),
    # Exactly one CURRENT row per identity; history lives beside it.
    Index("uq_obs_current", "dedupe_key", unique=True,
          sqlite_where=text("superseded_at IS NULL"),
          postgresql_where=text("superseded_at IS NULL")),
)
```

`connectors/ingest.py::_apply` currently mutates the row in place and bumps `revision`. Replace with: mark the existing row `superseded_at = now()`, insert a new row with `revision = old.revision + 1`, `supersedes_id = old.id`, `arrival_class = RESTATEMENT`. Byte-identical redelivery (same `payload_hash`) and out-of-order redelivery (`source_updated_at` older than held) still short-circuit as duplicates — that logic is already correct and stays.

The as-of query that makes an RTM audit answerable:

```sql
-- What did the engine see at the moment it emitted assessment X?
SELECT * FROM observations
WHERE patient_id = :pid
  AND deleted_at IS NULL
  AND ingested_at <= :as_of
  AND (superseded_at IS NULL OR superseded_at > :as_of);
```

### 2.1.4 `surgical_events` — because `Patient.surgery_date` is a scalar and recovery is not

Today `Patient` holds one `procedure_type` and one `surgery_date`. A staged bilateral TKA at week 7, an MUA at week 6, or an I&D at week 3 each invalidate the expected-recovery curve and the personal baseline, and there is currently nowhere to say so. This is not hypothetical: contralateral TKA within the episode window is common, and the steps series will crater for reasons that are not a complication.

```python
class SurgicalEvent(Base):
    __tablename__ = "surgical_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    event_type: Mapped[SurgicalEventType] = mapped_column(String)
    procedure_type: Mapped[ProcedureType | None] = mapped_column(String, nullable=True)
    cpt_code: Mapped[str | None] = mapped_column(String, nullable=True)      # 27447 / 27130 / 29888
    snomed_code: Mapped[str | None] = mapped_column(String, nullable=True)   # 609588000 TKA
    side: Mapped[str | None] = mapped_column(String, nullable=True)          # left|right|bilateral
    event_date: Mapped[date] = mapped_column(Date)
    is_index: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String)   # "ehr_fhir" | "clinician" | "patient_reported"
    fhir_reference: Mapped[str | None] = mapped_column(String, nullable=True)
```

Engine contract: `postop_day` is computed against `is_index` only, but **any non-index event resets the functional-metric baselines (steps, walking speed, ROM) and freezes trajectory scoring for 14 days**, emitting `TRAJECTORY_SUSPENDED_NEW_SURGICAL_EVENT`. Vitals (RHR/HRV/temp) are *not* reset — a contralateral surgery genuinely perturbs them and that perturbation is clinically real.

### 2.1.5 `assistive_device_periods` — the covariate that makes step counts meaningful

```python
class AssistiveDevicePeriod(Base):
    __tablename__ = "assistive_device_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    device_type: Mapped[AssistiveDeviceType] = mapped_column(String)
    started_on: Mapped[date] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    reported_by: Mapped[str] = mapped_column(String)  # "patient" | "pt" | "surgeon" | "inferred"
    confidence: Mapped[str] = mapped_column(String, default="reported")  # reported|inferred|assumed
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
```

Three capture channels, in priority order:

1. **Daily check-in question**, one tap, four picture buttons (walker / crutches / cane / nothing). This is patient-reported data, so it is RTM-qualifying under 98977 in its own right — it costs one row in the check-in schema and pays for itself twice.
2. **Clinician/PT entry** at each visit, which overrides patient report for the same date.
3. **Inference fallback** — if 7-day mean walking speed < 0.6 m/s with no recorded aid, write `UNKNOWN` with `confidence='inferred'`.

**Default when unknown:** POD 0–21 → assume `WALKER`; POD 22+ → `UNKNOWN`. Assuming the worst is the conservative direction here, because the failure mode of assuming `NONE` is a fabricated recovery curve.

### 2.1.6 `daily_coverage` — materialize the gate, do not recompute it

```python
class DailyCoverage(Base):
    __tablename__ = "daily_coverage"
    __table_args__ = (Index("uq_cov", "patient_id", "local_date", unique=True),)

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), primary_key=True)
    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    device_epoch_id: Mapped[int | None] = mapped_column(ForeignKey("device_epochs.id"))
    local_day_length_min: Mapped[int] = mapped_column(Integer)  # 1380/1440/1500 — DST-aware
    wear_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wear_evidence_score: Mapped[int] = mapped_column(Integer, default=0)
    night_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    metrics_present: Mapped[list[str]] = mapped_column(JSON)
    available_weight: Mapped[float] = mapped_column(Float, default=0.0)
    valid_day: Mapped[bool] = mapped_column(Boolean, default=False)
    gate_reasons: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
```

`local_day_length_min` is not decoration. Spring-forward gives a 23-hour local day and fall-back a 25-hour one; a hard-coded 1440 denominator will spuriously fail or pass the wear gate twice a year for every patient.

### 2.1.7 Immediate fixes to `engine/dataload.py` (G2 + G3)

```python
def load_daily_series(db, patient_id, surgery_date) -> dict[str, pd.Series]:
    rows = db.execute(
        select(Observation.metric_type, Observation.local_date, Observation.sleep_date,
               Observation.value_num, Observation.value_semantics)
        .where(
            Observation.patient_id == patient_id,
            Observation.value_num.is_not(None),
            Observation.deleted_at.is_(None),        # G3: tombstones
            Observation.superseded_at.is_(None),     # G3: restatement chain
            Observation.provenance.in_([Provenance.MEASURED, Provenance.VENDOR_DERIVED]),
        ).order_by(Observation.local_date)
    ).all()
    ...
    # G2: post-op day from the PATIENT-LOCAL day, matching rtm/coverage.py.
    # Sleep-linked metrics use the noon-to-noon anchor instead.
    df["anchor"] = df["sleep_date"].fillna(df["local_date"])
    df["day"] = (df["anchor"] - surgery_date).dt.days
```

`groupby("day").mean()` is now safe: it can no longer average an original against its own correction, or a deleted row against a live one.

---

## 2.2 The step-count crisis

### 2.2.1 The finding, stated precisely

A wrist device measures arm swing. A patient with both hands on a walker frame has no arm swing. Verified magnitudes:

- Apple Watch Series 8, rolling walker: **−36.4%** (PeerJ 2026, PMID 42004701, n=42, ages 51–80, p<.001)
- Fitbit Inspire 3 at the wrist, two-wheeled walker: **31.2%** error vs **1.5%** at hip/ankle (IJERPH 2025, PMID 40724167, n=11)
- Same Fitbit study, single-point cane: **−1.9%** — and the abstract notes wider limits of agreement at the wrist even for cane and no-device trials, so a cane is *not* free, just not disqualifying
- Wrist step error is not monotonic in speed: Apple Watch **−16.3%** at 0.45 m/s, **−0.1%** at 0.89 m/s, **−6.9%** at 1.34 m/s. A constant correction factor is mathematically wrong.
- CADENCE-Adults: **40%** MAPE at 0.8–3.2 km/h, **7%** at 4.0–6.4 km/h; wrist **15%** vs waist **3%** at normal speed.

Against this, the recovery signal we are trying to detect: TKA steps go from 3,755 preop to a **2,973 ± 1,463** nadir at 6 weeks (Arthroplasty Today 2025). The between-patient SD (1,463) and the device artifact (30–40%, i.e. ~900–1,500 steps at these volumes) are the same size as the effect. **In weeks 0–3 the step series has a signal-to-artifact ratio below 1.**

### 2.2.2 The decision

**Steps are demoted from a primary signal to a suppressed one for POD 0–28, unconditionally, and for any day where `assistive_device ∈ {WALKER, ROLLATOR, CRUTCHES_*, UNKNOWN}` regardless of POD.**

Concretely, in `engine/composite.py` and `engine/deviation.py`:

```python
# app/engine/steps_gate.py  (new)

SUPPRESSING_AIDS = {AssistiveDeviceType.WALKER, AssistiveDeviceType.ROLLATOR,
                    AssistiveDeviceType.CRUTCHES_FOREARM,
                    AssistiveDeviceType.CRUTCHES_AXILLARY,
                    AssistiveDeviceType.UNKNOWN, AssistiveDeviceType.WHEELCHAIR}

STEP_SUPPRESSION_POD_MAX = 28          # hard floor, aid-independent
STEP_SEGMENT_MIN_VALID_DAYS = 7        # before steps may re-enter after a transition
STEP_TRANSITION_HALO_DAYS = 3          # ± window around an aid change

def step_eligibility(pod: int, aid: AssistiveDeviceType,
                     days_in_segment: int) -> tuple[bool, str | None]:
    if pod <= STEP_SUPPRESSION_POD_MAX:
        return False, "STEP_SUPPRESSED_EARLY_POSTOP"
    if aid in SUPPRESSING_AIDS:
        return False, "STEP_SUPPRESSED_GAIT_AID"
    if days_in_segment < STEP_SEGMENT_MIN_VALID_DAYS:
        return False, "STEP_BASELINE_WARMING_AFTER_AID_CHANGE"
    return True, None
```

Suppressed means: weight 0 in the composite (weights renormalized over what remains, subject to the `available_weight ≥ 0.60` gate), no step reason codes, no contribution to `TrajectoryState`. The value is still stored, still charted for the patient, still counts toward RTM monitoring days.

### 2.2.3 What replaces steps as the primary functional signal in weeks 0–3

Ranked, and this is the ranking we build in:

**1. Patient-measured joint ROM (phone inclinometer).** The best-validated smartphone measure in exactly our population: PLOS One 2024, PMID 39361563, n=30 primary unilateral TKA, median age **66.0**, phone strapped to the limb segment vs extendable-arm goniometry — **MAD 4.5° flexion (ICC 0.97), 2.2° extension (ICC 0.98)**, intra/inter-session ICC > 0.97, **MDC95 3.1–9.0°**, and all patients could comprehend and execute the assessment. Note the corpus presented this as two studies; verification confirms it is **one** study of n=30, which is thin — but it is still the strongest evidence in the whole smartphone corpus and it is our exact cohort. For TKA, extension (flexion contracture) is the clinically decisive metric and it is the one measured best (MAD 2.2°, MDC95 3.1°).

**2. Pain NRS + HEP adherence, daily.** `PAIN_NRS`, `THERAPY_ADHERENCE`, `EXERCISE_REPS` are already in `MetricType` and — per the gap list G5 — referenced **nowhere outside `enums.py`**. This is the RTM-qualifying non-physiologic stream that CMS 98975–98981 is actually defined around, and it costs a check-in form plus a series loader. Building this closes both a clinical gap and a billing substance-over-form exposure.

**3. Walking-bout minutes / upright time**, where the provider exposes it. Duration of detected walking is far less sensitive to arm swing than step *count*, because bout detection needs only to see that ambulation is occurring.

**4. 30-second chair stand, weekly from POD 10.** Waist-mounted phone, amplitude-adaptive threshold plus dominant-frequency segmentation. (Reported at 99% cycle detection, <40 ms event error — **unverified**, flag as such.) This is a lower-limb strength proxy that a walker cannot corrupt because the hands leave the frame.

**5. Apple walking speed and step length**, as 7-day means only, within-patient. ICC 0.85 / 0.76 in seniors vs APDM (Sci Rep 2023; note the "adults" group in that paper has mean age 31.3, so only the seniors row transfers). MDC for walking speed **0.08 / 0.14 / 0.23 m/s** at the 10th/50th/90th percentile. Since the true 6-week dip is ~0.11 m/s, single-day speed changes are uninterpretable and only multi-day aggregates are usable.

**Not used:** double support time (Apple's own ICC(A,1) **0.53** validation / 0.59 design; independent seniors ICC **0.42**, PE 31.6%) and walking asymmetry (validated only as a classifier on n=51 able-bodied adults, mean age 37.5, wearing a knee brace locked to 30°/10°; Apple's own Discussion warns the mechanics "could differ substantially" from real pathology; no published MDC). Both are ingested and shown to clinicians labelled **exploratory**; neither enters tier logic.

### 2.2.4 The walker-to-cane gating rule

This is the specific failure the design must prevent: on the day a TKA patient drops the walker, wrist step count jumps 30–50% from pure instrumentation change, and a curve-fit reads a recovery inflection that did not happen.

```python
def step_segment_key(patient_id, local_date) -> tuple:
    """Steps are only ever compared WITHIN one (device epoch, aid period) segment."""
    return (device_epoch_id_on(patient_id, local_date),
            assistive_period_id_on(patient_id, local_date))
```

Four rules, all enforced in the data layer, not the model layer:

1. **Segment isolation.** Baseline, EWMA and CUSUM state for `STEPS` and `WALKING_SPEED` are keyed on `(patient_id, metric_type, device_epoch_id, assistive_period_id)`. A step value from a walker segment can never be a comparator for a cane segment. There is no cross-segment normalization and we will not build one.
2. **Reset, don't carry.** On any aid transition, emit `STEP_BASELINE_RESET_GAIT_AID`, discard the prior step control-chart state, and require 7 valid days in the new segment before steps re-enter the composite.
3. **Halo suppression.** Any step change > 25% occurring within ±3 days of a recorded aid transition is labelled `STEP_ARTIFACT_DEVICE_TRANSITION` and is **structurally incapable of producing `TrajectoryState.AHEAD`** — the improvement direction is where the artifact points, so the artifact can only ever manufacture false reassurance. It may still contribute to a *deterioration* signal, since a step drop at a transition is not explained by the artifact.
4. **Narrate the artifact.** When the patient-facing chart shows the jump, the deterministic renderer annotates it: "Your step count changed because you changed walking aids, not because your recovery changed." This is a fallback-renderer string, not an LLM output.

**What we refuse to build:** a per-(device, aid, speed-band) step correction factor. The error is non-monotonic in speed (−16.3% / −0.1% / −6.9%), the only walker data is n=42 non-surgical and n=11 healthy young adults, and there is **no published measurement of wrist step error in a post-arthroplasty cohort below 0.8 m/s with a walker**. Gate on data volume: revisit only after an internal substudy of **≥60 patients × ≥14 paired days** with a hip- or ankle-worn reference. Until then, suppress; do not correct.

---

## 2.3 Metric taxonomy correctness

### 2.3.1 HRV_SDNN vs HRV_RMSSD

The gap list G1 is correct and it is the most consequential live defect: `connectors/capabilities.py` correctly declares Apple supplies `HRV_SDNN` and `SKIN_TEMP_DELTA`, but `engine/pipeline.py:ANALYZED_METRICS`, `deviation.py:ADVERSE_UP/DOWN` and `composite.py:WEIGHTS` reference only the canonical `HRV_RMSSD` / `SKIN_TEMP`. An Apple patient's composite is computed from **0.55 of the intended 1.00 weight** against thresholds calibrated at 1.00, so they need ~1.8× the derangement to trip the same tier, and skin temperature — one of the two strongest early infection signals — contributes zero. `seed/generators.py:170-173` maps the variants back to canonical for Apple patients, so the golden-tier tests pass and the defect appears only when a real Apple Watch connects.

**Normalization rules:**

1. **SDNN and RMSSD are never interchangeable and there is no conversion constant.** Add both to `ANALYZED_METRICS` and to the adverse-direction sets. Keep **separate baselines per statistic**. The comparable quantity across statistics is the z-score, not the raw value.
2. **Log-transform before standardizing.** HRV is log-normally distributed; the current fixed relative SD floor of 0.06 in `baseline.py` is doing distributional work it was not designed for. Ship `z = (ln(x) − mean(ln x)) / sd(ln x)` for `HRV_RMSSD`, `HRV_SDNN`, and `CRP`. This is a three-line change and it removes the skew that currently makes low-HRV excursions look bigger than high-HRV ones.
3. **Never mix providers in one control chart.** The sampling contracts are incompatible by construction: Oura computes RMSSD in **5-minute windows averaged across the whole sleep period** (and Gen3 first averages HR into 10-minute segments); WHOOP **weights toward the last slow-wave episode**; Polar restricts to the **first 4 hours after sleep onset** (for both RHR and HRV); Garmin uses 5-min windows over detected sleep, and its RHR ("lowest 30-min average in 24 h") has undisclosed timestamp semantics and was **excluded outright** from the 2025 validation. Apple's HRV is SDNN; per verification, the corpus's "Breathe-sessions and opportunistic daytime reads" characterization is outdated — **watchOS 11 (Sept 2024) records overnight HRV during sleep via the Vitals app as routine background measurement**. The cross-device non-comparability conclusion survives regardless. Enforce via `device_epoch_id` on every chart.
4. **Refuse the composite across a mid-episode device family change** until the new epoch has established a baseline. Emit `DEVICE_EPOCH_WARMING`.

Implementation: `WEIGHTS` becomes a mapping over *metric families*, resolved per patient from the capability map.

```python
# app/engine/composite.py
FAMILY_WEIGHTS = {
    "rhr":        0.25,
    "skin_temp":  0.25,   # SKIN_TEMP or SKIN_TEMP_DELTA — whichever this device ships
    "hrv":        0.20,   # HRV_RMSSD or HRV_SDNN
    "resp_rate":  0.15,
    "function":   0.15,   # STEPS when eligible; otherwise redistributed
}
FAMILY_MEMBERS = {
    "hrv":       [M.HRV_RMSSD, M.HRV_SDNN],
    "skin_temp": [M.SKIN_TEMP, M.SKIN_TEMP_DELTA],
    ...
}
MIN_AVAILABLE_WEIGHT = 0.60   # renormalize above this; refuse below it
```

Renormalizing alone is a hazard — it makes one deviating metric look like a whole-body signal — so it ships **only** paired with the `MIN_AVAILABLE_WEIGHT = 0.60` gate and a `COMPOSITE_PARTIAL_WEIGHT` reason code carrying the actual fraction.

### 2.3.2 SKIN_TEMP vs SKIN_TEMP_DELTA

Apple's `appleSleepingWristTemperature` is an **absolute °C** wrist temperature (Series 8/Ultra, watchOS 9+, requires ~5 nights to establish the Health-app baseline). Fitbit splits into Temperature (Core), user-logged, and **Temperature (Skin)**, device-recorded during sleep as a **relative nightly variation from the user's personal baseline** — four endpoints total, by-date and by-interval for each. Oura and WHOOP: Oura ships **deviation**, WHOOP ships **absolute °C**.

**Rules:**

- Absolute and delta are different quantities with different units and different baseline semantics. They live in different `metric_type` values (already correct in `enums.py`) and are additionally tagged `value_semantics`.
- **A delta metric bypasses `compute_baseline()` entirely.** Running our baseline on top of the vendor's double-subtracts and suppresses real fever signal. Instead: `z_delta = (delta − rolling_personal_mean_of_delta) / rolling_personal_sd_of_delta` over a 14-day trailing window, where the mean is near zero by construction but not exactly zero.
- A delta-only vendor gives no way to reconstruct absolutes. Never coerce, never impute the missing direction.
- Plausibility: reject skin-temp deltas outside **±5 °C** of the personal median as `IMPLAUSIBLE_TEMP_DELTA` (tombstone with `tombstone_source='ops_plausibility'`, never a silent drop).

### 2.3.3 SpO2 — absence is regulatory, not behavioural

Apple sold Series 9 / Series 10 / Ultra 2 in the US with Blood Oxygen **disabled from 2024-01-18**, restored **2025-08-14** via iOS 18.6.1 / watchOS 11.6.1 with computation moved to the paired iPhone. Non-US units and pre-Series-9 units were never affected.

- Encode a `spo2_available` window per `(device_model, region, date_range)` in the capability table.
- Map absence to `SPO2_UNAVAILABLE_REGULATORY`, **not** to non-adherence, and do not let it depress the coverage score.
- Remove `SPO2` from `confidence.py:KEY_METRICS`. Several providers do not ship it at all, so the current gate penalizes coverage by device brand rather than by wear (gap list G8).
- Derate SpO2 weight generally: MAE **2.2%** (Apple S7), **3.8%** (Garmin Fenix 6 Pro), **4.0%** (Withings ScanWatch), **5.8%** (Garmin Venu 2s), with unsuccessful-measurement rates of **11 / 28 / 31 / 14%** (PLOS Digital Health, 12 July 2023, n=49). Note the corpus mis-stated the Fenix and ScanWatch rows; those are the corrected values. Only 3 of 49 participants averaged <90%, so the range that matters for post-op pulmonary complications is untested.

### 2.3.4 Sleep

TST bias **+6.31 min (Fitbit Sense)** to **+39.87 min (Withings ScanWatch)** with limits of agreement reaching **±150 min**; epoch-by-epoch wake **specificity 29–52%** across all six major devices (Sleep Advances 6(2):zpaf021, 22 Mar 2025, n=62 — note 84% male, sleep-clinic-shaped, and **no night in that study was disrupted by post-operative pain**). The devices systematically call wake "sleep," which inflates TST precisely in the patient who wakes repeatedly from pain — i.e. they smooth over our earliest signal.

**Ruling:** `SLEEP_DURATION` stays in `deviation.py` for display and RTM day-counting but its composite weight is **0** at launch. Vendor sleep *stages* are never ingested as clinical fact. Prefer nocturnal HR/HRV-derived fragmentation, which rests on ±1–1.4 bpm accuracy rather than κ 0.21–0.53.

### 2.3.5 Cross-brand step offsets

Free-living step totals vs ActiGraph: Apple **+2.12%**, Oura **−6.24%**, Fitbit **+18.00%** — a 24-percentage-point spread. (Flagged unverified in the verification pass; treat as directional.) **No conversion factor.** Device change → new epoch → re-baseline. The spread exceeds any correction we could justify.

---

## 2.4 Wear time, non-wear detection, and minimum-data rules

### 2.4.1 The problem

Choi 2011 (≥90 consecutive zero-count minutes, 2-min non-zero allowance with a flanking 30-min zero window **upstream OR downstream**), Troiano 2008 (60 min / <100 cpm), and van Hees/GGIR (per-axis SD < 13 mg and range < 50 mg on ≥2 of 3 axes) all require raw or count-level accelerometry at ≤1-min epochs. Consumer PPG wearables do not expose it. Fitbit intraday could have supported a port — and **the Fitbit Web API sunsets September 2026**, and commercial intraday access was case-by-case and revocable anyway. So the classical algorithms are unavailable at launch and we build a proxy.

### 2.4.2 The daily-aggregate wear proxy

```python
# app/engine/wear.py  (new)

def wear_evidence(day_rows, device_epoch) -> tuple[int, bool, list[str]]:
    """Score 0-4 from vendor daily aggregates. No validated equivalent exists;
    these are reasoned analogues of Choi's parameters, not validated numbers."""
    score, flags = 0, []

    sleep = day_rows.get(M.SLEEP_DURATION)
    night_valid = (sleep is not None and sleep >= 4.0
                   and day_rows.get("max_sleep_gap_min", 0) <= 30)
    if night_valid and (day_rows.get(M.HRV_RMSSD) or day_rows.get(M.HRV_SDNN)
                        or day_rows.get(M.RESTING_HR)):
        score += 2
    else:
        flags.append("NO_VALID_NIGHT")

    if (day_rows.get(M.STEPS) or 0) > 0:
        score += 1
    if day_rows.get(M.HR_SAMPLE) is not None or day_rows.get(M.ACTIVE_ENERGY):
        score += 1

    wt = day_rows.get(M.WEAR_TIME_MINUTES)
    if wt is not None:                       # vendor gave us the truth — prefer it
        return (4 if wt >= 600 else 1 if wt >= 240 else 0), night_valid, flags
    return score, night_valid, flags

VALID_DAY_MIN_SCORE = 3
```

Requiring `sleep >= 4h` with `max gap <= 30 min` before accepting a vendor nightly HRV directly implements the corpus's artifact rule and costs nothing.

`WEAR_TIME_MINUTES` already exists in `MetricType` and — per gap list G4 — the confidence gate does not consult it. That is the single highest value-per-line fix in the whole data layer: right now a provider that back-fills zeros and a watch worn 20 minutes a day both score as full coverage, and the coverage gate is the product's entire defense against saying "Stable" about a patient nobody can see. Since **every** metric we use is general-wellness rather than FDA-cleared, that gate is not a nicety — it is the regulatory posture.

### 2.4.3 The two-stage gate

**Stage 1 — per day.** `valid_day = wear_evidence_score >= 3` (or vendor `wear_minutes >= 600`, being GGIR-adjacent but relaxed from `includedaycrit=16h` because a post-op patient charges during the day). Additionally require the largest contiguous gap outside a single ≤2 h charging window to be ≤ 90 min once minute-level data exists.

**Stage 2 — per clinical statement.** Replace `confidence.py`'s single "≥3 of 6 key metrics on ≥40% of 7 days" with per-statement-class minimums:

| Statement class | Requirement | Basis |
|---|---|---|
| RHR / HRV trend | ≥2 valid days in last 7, **and** device epoch ≥5 valid days total | reliability 0.86 at 2 days × 10 h |
| Skin-temp deviation | ≥3 valid **nights** in last 7 | delta needs a nightly series |
| Activity volume (steps) | ≥4 valid days **and** step eligibility per §2.2.2 | ICC 0.7 at 3–4 days for MVPA |
| Walking speed change | ≥5 valid days in each of two 7-day windows; change ≥ **0.14 m/s** | median MDC |
| Knee flexion ROM change | change ≥ **9.0°**; extension ≥ **3.1°** | MDC95 3.1–9.0° |
| Circadian (IS/IV/RA/M10/L5/SRI) | ≥7 valid noon-to-noon nights **and** minute-level data | GGIR convention |
| Any composite / risk tier | `available_weight ≥ 0.60` **and** ≥3 valid days in last 7 | §2.3.1 |

Every failure emits a typed reason code carrying the observed numbers — `INSUFFICIENT_COVERAGE(wear_hours=4.2, valid_days=1)` — never a silent low-confidence number.

### 2.4.4 Two non-negotiables

**Never impute into the detection path.** GGIR's defaults (`do.imp=TRUE`, `imputeTimegaps=TRUE`, time-of-day-matched within-person imputation) are correct for descriptive physical-activity epidemiology and exactly wrong here: imputing yesterday's same-hour value manufactures a "normal" reading and suppresses the deviation the surveillance index exists to detect. Non-wear in a post-op cohort is **not** missing-at-random — the febrile, hospitalized, or readmitted patient generates the non-wear. `provenance=IMPUTED` rows are display-only and visually distinguished; the detection filter is `provenance IN (MEASURED, VENDOR_DERIVED)`.

**Coverage collapse is itself an alertable event.** If 7-day median wear ≥ 600 min drops below 360 min for two consecutive days, fire `DATA_LOSS_DISENGAGEMENT` as a first-class reason code. And **do not let a non-wear day reset a CUSUM** — freeze CUSUM state across non-wear rather than feeding it a zero or an imputed normal. The current `deviation.py` 14-day CUSUM window will otherwise silently discount a patient who stops wearing the device *because* they are sick.

---

## 2.5 Aggregator choice and ingestion topology

### 2.5.1 Aggregator

**Ship: Junction (fka Vital) as the launch aggregator, plus our own native HealthKit / Health Connect collection in the companion app.**

- Junction: HIPAA-native, SOC 2 Type 2 + ISO 27001 + GDPR, **BAA available at the floor price**, ~$0.50/user/mo with a **$300/mo minimum**, self-serve sandbox at app.junction.com, Svix webhooks (HMAC-SHA256 `svix-signature` with timestamp replay protection), and nationwide lab ordering on the same API — an adjacency that matters for §2.6. Caveats from verification: the $0.50/user figure is third-party, not published, and Junction's docs state **no** default backfill window (the "180 days" in the corpus is unconfirmed). **Get both in writing in the sales call before signing.**
- **Terra is disqualified at startup pricing**: a signed BAA is listed only under custom-priced Enterprise. The $399–499/mo tier does not include one, which is fatal for PHI. The "~200 credits/user" assumption is also unverified and the one published per-user figure (Streaming API at 1,000 credits ≈ $5/user) points 5× the other way.
- **Revisit ROOK at ≥5,000 patients**, where Business at $1,999/mo flat to 15,000 users undercuts per-user pricing. Confirm ROOK will sign a BAA — its pricing page does not mention one.
- Direct-build alternative: ~6–8 integrations × 2–6 eng-weeks each ≈ **$150–250k** plus ~0.25 FTE ongoing, against a **$3.6k/yr** aggregator bill at 100 patients. The churn rate alone settles it: Whoop v1 removal, Oura PAT deprecation, Google Fit REST shutdown and now the **Fitbit Web API September 2026 sunset**, all inside 18 months.

**The Fitbit sunset is the most actionable fact in this section.** Do not build a direct Fitbit connector. Make the aggregator own the Google Health API migration. In our schema, a Fitbit tracker whose cloud API changes from `dev.fitbit.com` to `developers.google.com/health` is the **same device epoch with a new `api_channel`** — the hardware and its measurement properties are unchanged, so the baseline must not reset. `SourceProvider.GOOGLE_HEALTH` already exists in `enums.py` and is correctly documented there as not-a-rename.

Keep the connector interface provider-agnostic (already scaffolded correctly in `connectors/base.py` + `registry.py`) so the aggregator swap is config, not a rewrite.

### 2.5.2 Topology

```
provider webhook
  → API Gateway (POST /webhooks/{provider})
  → Lambda: per-provider signature verifier behind one interface
        Junction: Svix HMAC-SHA256 + timestamp replay window
        Terra:    terra-signature HMAC-SHA256
        WHOOP:    X-WHOOP-Signature (HMAC-SHA256 over timestamp+body)
        Fitbit:   X-Fitbit-Signature HMAC-SHA1        [retire by Sept 2026]
        Oura:     GET challenge-echo handshake
  → raw body → S3 (immutable, KMS, 7-year retention) + WebhookEvent row
  → SQS FIFO   MessageGroupId = patient_id     ← per-patient ordering
  → normalize Lambda → CanonicalObservation[]  → ingest_observations()
  → on any insert/supersede: publish {patient_id, min_affected_local_date}
       to recompute-queue (FIFO, MessageGroupId = patient_id, 60 s debounce)
  → recompute worker: pipeline.run(patient, from_day=min_affected)
```

`MessageGroupId = patient_id` is the load-bearing detail. Without per-patient FIFO ordering, a restatement and a live delivery for the same day can race, and the append-only supersede chain will record them in the wrong order.

**Idempotency.** The dedupe key must include the device epoch (two watches, one per wrist, otherwise collide) and must **not** include the value (or restatements become new rows instead of revisions):

```python
dedupe_key = sha256("|".join([
    provider, str(device_epoch_id), external_id or "-", metric_type,
    effective_start.isoformat(), effective_end.isoformat(), granularity,
]).encode()).hexdigest()
```

WHOOP v2 keys recovery events to the **UUID of the associated sleep** and replaced integer IDs with UUIDs, so any stored v1 identifiers need a mapping table. HealthKit may not expose a stable UUID surviving a phone migration — for Apple, fall back to a content-derived `external_id` and accept a small duplicate rate at migration boundaries.

**Backfill.** On connect, request full history into a **separate lower-priority queue** with `arrival_class=BACKFILL`. Backfilled rows never fire notifications and never trigger `notify_high_priority`. A 180-day backfill can be thousands of events in minutes, which is precisely why SQS sits in front of Lambda.

**Restatement.** Vendors restate: Fitbit stress scores change up to a week later; sleep records commonly restate 2–3 times within 24 h; resting HR and readiness are recomputed on late-arriving partial syncs or a vendor model update. Terra's and Junction's restatement-webhook semantics are **unverified** — we could not confirm whether either emits an update event when an upstream vendor restates a historical day. Therefore ship a **nightly trailing re-pull sweep of the last 14 days per patient**, and treat push as an optimization rather than the contract. Cost is trivial (14 days × N patients of daily aggregates).

**Recompute correctness (fixes the verified `/worklist` bug).** `compute_input_hash()` currently includes `date.today()` and `max(ingested_at)`, so (a) the first request each day synchronously recomputes every patient *and regenerates LLM narratives* inside one HTTP request, and (b) an in-place restatement that changes neither count nor `ingested_at` does not invalidate the cache. Fix both:

```python
def compute_input_hash(db, patient_id) -> str:
    row = db.execute(select(
        func.count(Observation.id),
        func.max(Observation.revision),
        func.max(Observation.source_updated_at),
        func.max(Observation.ingested_at),
    ).where(Observation.patient_id == patient_id,
            Observation.deleted_at.is_(None),
            Observation.superseded_at.is_(None))).one()
    return sha256(f"{row}|{ENGINE_VERSION}|{PRIOR_TABLE_VERSION}".encode()).hexdigest()
```

No `date.today()`. `GET /worklist` **reads materialized assessments only** and returns a `stale` flag; freshness is the ingestion pipeline's job, plus a scheduled sweep for patients whose devices went quiet.

**Per-source freshness SLAs**, because latency is structurally different per channel and a global threshold is wrong:

| Channel | Freshness gate | Why |
|---|---|---|
| Cloud webhook (Junction/Oura/Garmin/WHOOP) | 6 h | fires on device→cloud sync |
| Apple HealthKit via companion app | 24–36 h | background delivery is per-type throttled (step count hourly), requires the app to wake, stalls entirely if force-quit |
| Health Connect (Android) | 36 h | OEM battery managers (Samsung/Xiaomi/OnePlus) throttle background sync; Samsung Health→Health Connect cadence varies by data type |
| Fitbit (legacy) | 6 h | 15-min Bluetooth sync, best-effort; **retire by Sept 2026** |

**Timezones.** Store three representations plus the offset: `start_time` (UTC), local wall clock, `timezone` (IANA), `utc_offset_seconds`. Fitbit returns local wall clock with **no IANA zone** — only a point-in-time offset from Get Profile, which does not describe historical travel — so a single representation makes DST and travel unrecoverable. `local_date` is materialized at ingest (already correct) and `sleep_date` uses the noon-to-noon local window.

---

## 2.6 EHR and lab ingestion

### 2.6.1 Staging — be realistic

The API is never the pacing item; **per-customer governance is**. Every production Epic or Oracle connection requires that health system's own approval, security review and InterConnect build — weeks to months.

- **Stage 0 (now, ~$0):** register on open.epic and Oracle Code Console. Build one SMART Backend Services client (JWT client-credentials, **RS384 or ES384**, hosted JWKS) and one SMART standalone patient launch. Ship patient-mediated ingestion: Apple Health Records (`HKClinicalRecord`, FHIR R4) forwarded by the companion app, plus MyChart standalone launch. **No health-system approval required.** Note Apple Health Records is iPhone/iPad-only, which is a real limitation in a mean-age-66 cohort.
- **Stage 1 (first 1–3 customers, ~$2–5k/yr):** per-customer Epic Backend Services under each surgeon group's sponsorship. Read `Condition`, `Procedure`, `Encounter`, `Observation(category=laboratory)`, `DiagnosticReport`, `MedicationRequest`, `DocumentReference`. Write back only via **flowsheet observation filing**, `DocumentReference.Create` for weekly PDFs, and `QuestionnaireResponse` for PROs. There is **no** order or CarePlan write path through open APIs; do not design one. Epic Vendor Services is optionally ~$1,900/yr (unverified).
- **Stage 2 (readmission signal):** ADT e-notifications via Bamboo Pings, PointClickCare/Audacious ENS, or a state HIE, under customer NPIs. Hospitals have been required to send A01/A03/A04/A08 to established care providers since **2021-05-01** (CMS-9115-F Condition of Participation). **An ED-visit or readmission ADT is the highest-specificity signal available to this product** and it is cheaper than anything else in this section.
- **Stage 3 (>$60k/yr):** TEFCA IAS via a QHIN, or a treatment-purpose aggregator. Only after measuring what fraction of enrolled patients Stage 0/1 already covers. Price in channel risk: Epic cut Particle's Carequality connection in March 2024 over purpose-of-use disputes.

**Do not build on Bulk `$export`.** Per JAMIA 2024 (doi:10.1093/jamia/ocae040), Epic sites exported 1.0–45.4 M resources at **1,555–2,500 resources/min** and supported **neither `_since` nor `_typeFilter`**; Oracle Cerner supported `_since`/`_type`/`_typeFilter` at 7,300–10,838 res/min. Vendors advise Group sizes ≤1,000 at Epic and ≤10,000 at Cerner, split per resource type. For an RTM cohort of hundreds, per-patient incremental synchronous reads on `_lastUpdated` win outright — and a 15-minute Lambda cap would break an `$export` polling loop anyway.

Version floor: **US Core 6.1.0 / USCDI v3** (US Core 3.1.1 / USCDI v1 expired as a permitted certification standard after 2025-12-31). SMART App Launch **2.0.0** is the (g)(10) requirement as of 2025-12-31; 2.2.0 is only an SVAP alternative. Anything USCDI v4/v5-only must be nullable and channel-annotated until ~2028. There are **11** designated QHINs (the corpus said 10, omitting Kno2).

### 2.6.2 `lab_observations`

```python
class LabObservation(Base):
    __tablename__ = "lab_observations"
    __table_args__ = (Index("ix_lab_patient_loinc_time",
                            "patient_id", "loinc_code", "effective_datetime"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    loinc_code: Mapped[str] = mapped_column(String)
    local_code: Mapped[str | None] = mapped_column(String, nullable=True)
    display: Mapped[str] = mapped_column(String)
    value_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    canonical_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    canonical_unit: Mapped[str] = mapped_column(String)     # UCUM
    reference_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    specimen_type: Mapped[str] = mapped_column(String)      # serum|plasma|synovial|whole_blood
    effective_datetime: Mapped[datetime] = mapped_column(DateTime)
    post_op_day: Mapped[int | None] = mapped_column(Integer, index=True)
    source_system: Mapped[str] = mapped_column(String)      # OID / assigning authority
    source_id: Mapped[str] = mapped_column(String)          # resource id
    version_id: Mapped[str | None] = mapped_column(String, nullable=True)  # meta.versionId
    code_system_version: Mapped[str | None] = mapped_column(String, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

Dedupe key: `(source_system_oid, resource_type, resource_id, meta.versionId)`. Labs have the same duplicate-delivery problem as wearables — a result gets amended, re-sent, and arrives from both the hospital and the reference lab.

`post_op_day` is a stored column because **every threshold in this domain is indexed on POD, not calendar time**.

### 2.6.3 LOINC / code sets

```python
LOINC = {
    "CRP":            "1988-5",   # verified on loinc.org — mass/volume, serum/plasma
    "CRP_HS":         "30522-7",  # NEVER conflate: cardiac-risk scale, 100x hazard
    "ESR":            "30341-2",
    "ESR_WESTERGREN": "4537-7",
    "PROCALCITONIN":  "33959-8",  # verified; deprioritize — no advantage over CRP
    "IL6":            "26881-3",  # peaks ~24h before CRP but rarely ordered outpatient
    "WBC":            "6690-2",
    "NEUT_ABS":       "751-8",
    "HGB":            "718-7",
    "PLT":            "777-3",
    "CREATININE":     "2160-0",
    "EGFR_CKDEPI_2021": "98979-8",
    "ALBUMIN":        "1751-7",
    "PREALBUMIN":     "14338-8",  # NOT 2882-1 — corpus was wrong; 2882-x is pleural protein
    "HBA1C":          "4548-4",
    "GLUCOSE":        "2345-7",
    "DDIMER_FEU":     "48065-7",
    "DDIMER_DDU":     "48066-5",  # differ ~2x — reject ambiguity, never guess
    "INR":            "6301-6",
    "FERRITIN":       "2276-4",
}
CPT_INDEX = {"TKA": "27447", "THA": "27130", "ACL": "29888",
             "ROTATOR_CUFF": "29827", "LUMBAR": "22633",
             "ANKLE": "27702", "MENISCUS": "29881"}
```

ICD-10-CM to ingest: `T84.5-` (PJI, laterality-specific: T84.53XA right knee, T84.54XA left knee, T84.51/.52 hip), `T84.7XXA` (spinal instrumentation / ACL graft fixation), `T84.0-` (mechanical), `T81.4-` (SSI: .41 superficial, .42 deep, .43 organ/space, .44 sepsis), `T81.31XA/.32XA` (dehiscence), `I82.4-` (DVT), `I26.-` (PE), `N17.9`, `D62`. **Correction to carry:** `M48.061` is lumbar stenosis **WITHOUT** neurogenic claudication and `M48.062` is **WITH** — the corpus had these reversed, and any cohort logic keyed on claudication would be inverted.

Crosswalks live in **data-driven tables loaded from official release files with a `code_system_version` column**, not Python dicts. ICD-10-CM updates annually 10-01, CPT 01-01, LOINC twice yearly, RxNorm monthly. A hard-coded dict silently breaks complication detection every October. Unmapped LOINCs go to an explicit `unmapped` bucket surfaced in ops — never silently dropped, because local labs routinely send site-specific codes alongside LOINC.

### 2.6.4 Unit normalization — the #1 correctness hazard

CRP is reported in mg/L in Europe and mg/dL in much of US practice — a **10× difference** — and published papers mislabel their own tables. Implement a UCUM normalizer canonicalizing CRP → mg/L, creatinine → mg/dL, hemoglobin → g/dL, ESR → mm/h, D-dimer → ng/mL FEU (rejecting DDU/FEU ambiguity rather than guessing), synovial WBC → cells/µL. Plausibility gate: **reject any CRP > 500 mg/L or < 0**, and flag any post-op CRP that is 10× or 0.1× the patient's own adjacent value as a probable unit error.

### 2.6.5 Fusing a sparse lab series with the dense wearable stream

**What actually arrives when:**

- *Near-real-time* (minutes–hours, via FHIR, legally required to be released without delay under 45 CFR Part 171): inpatient POD 0–3 CBC, BMP, INR if anticoagulated, and any CRP the surgeon happened to order.
- *Only at scheduled visits, or never*: post-discharge CRP and ESR (2-week wound check, 6-week visit, or when someone is already worried), albumin/prealbumin, HbA1c (8–12 week lookback; will not move within an episode), D-dimer (elevated in essentially everyone post-op and uninterpretable for VTE in the first weeks).
- *Outcome labels, never inputs*: synovial WBC/PMN%, alpha-defensin, leukocyte esterase, cultures, histology. These exist only after an aspiration or revision.

**Architecture:** labs are a **sparse, irregularly-sampled, informatively-missing** channel whose job is to confirm or refute a wearable-derived deviation and to supply hard outcome labels. Concretely:

1. **Never run EWMA or CUSUM on a 2–4-point series.** Compare each observed CRP against a **per-procedure POD-indexed expected band**, exactly parallel to `curves.py` for steps.
2. **Do not impute CRP forward**, ever. Represent `days_since_last_crp` as a first-class feature and let the coverage gate suppress the term entirely rather than degrade into noise.
3. **Informative missingness is a leakage hazard.** A post-discharge CRP exists mostly because a clinician was already concerned. `crp_was_ordered` must be **excluded from any trained model's feature set** — it leaks the outcome — while remaining available as clinician-facing display context. Adjudicated.

**Adjudicating the CRP numbers.** The corpus's headline THA curve (Kuhn et al., n=7,042: POD1 56.9, POD3 134.1, POD5 70.4 mg/L; POD3 threshold 152.1 mg/L, AUC 0.714) **could not be located in PubMed** by the verification pass. Do not hard-code it. Use PubMed-verifiable sources:

- **THA/TKA:** Wasko et al. 2017, *J Orthop Translat*, n=387 — THA day 0 **7.7**, day 3 **184.8**, day 5 **115.9 mg/L**.
- **TKA under ERAS:** Zhu et al. 2020, *BMC Musculoskelet Disord*, n=100 — pre-op 3.35 ± 2.11; 12 h **25.17 ± 20.47**; 48 h **66.57 ± 43.11**; **72 h peak 75.97 ± 40.04**; 2 weeks **6.67 ± 5.23** (back to baseline, p=0.816). IL-6 peaks 24 h earlier, at 48 h.
- **TKA normalization:** 35% (140/400) below 5 mg/L at 2 weeks, **80.8% (323/400) at 4 weeks**.
- **Shoulder arthroplasty:** peak POD3 at ~**9.6 mg/dL (96 mg/L)**; peak on POD2–3 in 92% of patients.

Note the day-3 disagreement: **134.1 vs 184.8 mg/L**, a ~50 mg/L spread between sources for the same procedure. That is not a defect in the sources, it is the effect of ERAS protocol, tourniquet use, TXA, navigation and bone-work extent — which is exactly why we ship a **procedure- and protocol-specific band with trajectory features**, not a threshold. Ship bands for TKA (ERAS), THA and shoulder arthroplasty. Ship **no band** for ACL, arthroscopic rotator cuff, meniscectomy or ankle — no per-POD reference curve exists — and return `CRP_NO_VALIDATED_BAND` rather than a fabricated one.

**Features to compute** (deterministic Python, no LLM tokens — every rule here is a numeric comparison):

```python
fraction_of_peak      = crp_now / crp_max_observed
days_since_peak       = pod_now - pod_at_max
second_rise           = crp_now > 1.25 * running_min_after_pod5 and n_confirming >= 2
failure_to_decline    = fraction_of_peak > 0.5 and pod_now >= 7
```

**Calibration, hard-coded into the tier logic.** At a 0.5–1.5% acute PJI base rate, the best published single-timepoint rule (sens 75% / spec 67%) gives PPV ≈ **1–3%**. Therefore: **CRP can never independently escalate a patient to HIGH.** Reason codes are `CRP_FAILURE_TO_DECLINE`, `CRP_SECOND_RISE`, `CRP_ABOVE_PROCEDURE_BAND`, `CRP_INSUFFICIENT_SAMPLES`, all typed as "obtain confirmatory labs / contact the surgical team," never as an infection assertion. Log the PPV estimate alongside each fired rule so the console can display it. There is **no published second-rise rule with sensitivity/specificity** — ours is a heuristic and must be labelled one.

**PJI adjudication (labels table).** MSIS 2018 as pure deterministic code: serum CRP >10 mg/L = 2, D-dimer >860 ng/mL = 2, ESR >30 mm/h = 1, synovial WBC >3,000/µL = 3, alpha-defensin S/CO >1 = 3, leukocyte esterase ++ = 3, PMN% >80 = 2, synovial CRP >6.9 mg/L = 1; ≥6 infected, 2–5 inconclusive (sens 97.7% / spec 99.5%). EBJIS 2021 three-level, with two corrections the corpus got wrong: rule-out is WBC <1,500/µL **AND** PMN <65% (**not OR** — an OR rule-out is materially less specific), and sonication-fluid culture confirms only above **>50 CFU/mL non-concentrated / >200 CFU/mL concentrated**, otherwise it stays "likely."

**KDIGO AKI** as a deterministic function over serial creatinine, with an explicitly documented baseline policy (most recent pre-op creatinine, falling back to lowest in the prior 7 days — the choice materially changes staging). Both the 48-h absolute rule (≥0.3 mg/dL) and the 7-day ratio rule (≥1.5×) on a sliding window; return the triggering rule so the reason code is explainable. **Document that our staging is creatinine-only and therefore under-detects**, because urine output is not obtainable in RTM.

---

## 2.7 Patient-reported and app-mediated measurement

The phone measures four things the wrist structurally cannot: **joint angle, guided performance-test scores, spatiotemporal gait quality, and wound appearance.**

### 2.7.1 New table

```python
class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    assessment_type: Mapped[str] = mapped_column(String)
    #   KNEE_ROM_FLEX | KNEE_ROM_EXT | HIP_ROM | TUG_5REP | CST_30S
    #   | SIT_TO_STAND_POWER | GAIT_SPEED_GUIDED | WOUND_PHOTO
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String)
    baseline_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    capture_modality: Mapped[str] = mapped_column(String)
    #   PHONE_IMU | PHONE_CAMERA_POSE | GPS | APPLE_MOBILITY | MANUAL
    # Accuracy is model-version dependent: a MoveNet Lightning result and a
    # MoveNet Thunder result are NOT interchangeable and must not share a series.
    pose_model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    app_version: Mapped[str] = mapped_column(String)
    device_model: Mapped[str] = mapped_column(String)
    phone_placement: Mapped[str | None] = mapped_column(String, nullable=True)
    #   POCKET_FRONT | WAIST | LIMB_STRAP | TRIPOD
    rep_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    surgical_event_id: Mapped[int | None] = mapped_column(ForeignKey("surgical_events.id"))
    side: Mapped[str | None] = mapped_column(String, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime)
    local_date: Mapped[date] = mapped_column(Date, index=True)
    dedupe_key: Mapped[str] = mapped_column(String, unique=True)
```

Assessments are **within-patient trends against a per-patient baseline, never cross-patient absolutes**. The validation data are consistently *biased but stable*: Apple gait speed carries +0.06 m/s bias and 14.1% percentage error in seniors yet a one-week test-retest ICC of **0.88** (step length 0.93, double support 0.91). Store `value` and `baseline_delta`; risk tiers consume only the delta.

### 2.7.2 Build order

**Build first — knee/hip ROM by phone inclinometer.** MAD 4.5° flexion / 2.2° extension, ICC 0.97/0.98, MDC95 3.1–9.0°, in n=30 TKA patients of median age 66 (PLOS One 2024, PMID 39361563). This is the single best-validated smartphone measure in our exact population, it is a native IMU read with no ML dependency, and extension — the clinically decisive TKA metric — is the one measured best. Change gates: **flexion ≥ 9.0°, extension ≥ 3.1°** (the MDC95 range end appropriate to each motion; do not use a single 5° floor, which discards the tighter end of the paper's own range). Ceiling: cannot resolve >145° flexion or true 0° extension.

**Build second — daily check-in: PAIN_NRS, THERAPY_ADHERENCE, EXERCISE_REPS, assistive-device status.** Near-zero engineering cost, closes gap G5, supplies §2.2's aid timeline, and is the non-physiologic data that CMS defines RTM around. Note that the entire engine currently reads heart rate, HRV, skin temperature, SpO2 and respiratory rate — *physiologic* data, which is RPM (99453–99458) territory, a different code family. A product billing RTM whose analytics read almost exclusively physiologic signals has a substance-over-form problem, and this item is the cheapest fix for it.

**Build third — Apple Mobility passive ingest** (`walkingSpeed`, `walkingStepLength`, plus `appleWalkingSteadiness` as exploratory). Free, passive, no special approval. Constraints to encode: iPhone 8+/iOS 14+, phone at the hip (pocket/clip/waist bag), **current height required in the Health app** — walking speed derives from a center-of-mass model and step length from height, so a stale height silently degrades both. Metrics are absent during running and uphill hiking, and entirely unavailable under Wheelchair mode. >80% of eligible users get ≥5 estimates/day, so persist per-day estimate counts and require a **minimum bouts/day** before any Mobility metric touches a tier decision. Plausibility bounds from Apple's own reference distribution: 1.04 ± 0.18 m/s slow, 1.30 ± 0.18 self-selected, 1.46 ± 0.18 during 6MWT.

**Build fourth — 30s chair stand (weekly from POD 10) and 5-rep TUG.** Deterministic signal processing on the accelerometer series: amplitude-adaptive thresholds plus dominant-frequency segmentation. For TUG, **capture 5 reps and discard rep 1 server-side** — that single rule moves between-rep agreement from ICC 0.90 to 0.95. Two-week test-retest ICC 0.79 is the binding constraint, i.e. day-to-day noise, not sensor error. All numbers in this bullet were flagged unverified; treat the protocol as sound and the point estimates as provisional.

**Build fifth — structured wound-photo capture, triaged to a human.** Fixed distance, fiducial or ARKit scale, consistent white balance, prompts on POD 3 and POD 10 (RedScar protocol). Fuse with the symptom questionnaire.

### 2.7.3 Refuse to build

- **An autonomous SSI classifier.** Photograph-only telemedicine SSI detection pools at **sensitivity 63.9% (95% CI 30.4–87.8)** vs 87.8% for full telemedicine assessment — the gap *is* the questionnaire and the clinician. Missing 1 in 3 SSIs in a product patients read as reassurance is not a tolerable failure mode. The only safe outputs are `ESCALATE` and `NEEDS_CLINICIAN_REVIEW`; **never emit "looks normal."** Any redness feature we compute is an input to the composite, not a verdict. An autonomous classifier is almost certainly regulated SaMD rather than exempt CDS. Also: RedScar's best-in-class 100%/83.1% rests on **5 infections in 41 patients**, its core feature is a grayscale red-pixel proportion at a 0.63 cutoff that is mechanistically likely to underperform on darker skin with no Fitzpatrick stratification reported, and the confirmatory multicenter trial enrolls **abdominal** surgery patients — so waiting for it does not de-risk an arthroplasty feature.
- **GPS 6MWT reported as a distance.** Limits of agreement **−77.6 to +103.9 m** breach the prespecified 100 m bound, and the TKA MCID for 6MWD is well under 100 m — the noise swamps the effect. (Numbers unverified, conclusion robust.)
- **Camera pose ROM in v1.** OpenPose needs a GPU (server-side, so raw video leaves the phone — a BAA and storage blast radius we do not want), MediaPipe Pose Landmarker is still labelled "Preview / early release" and its docs URL has already 301'd once, and on-device models are joint-dependent in the worst possible way: shoulder rotation and elbow flexion — the movements that matter for rotator cuff repair — are exactly where monocular 2D pose fails. The phone-as-inclinometer gets us knee and hip for a fraction of the cost.
- **Continuous GPS digital phenotyping.** Real signal but weak (r ≈ −0.36 vs pain VAS) and it materially changes our breach posture. If it ever ships: separate revocable consent scope, separate table, on-device aggregation, daily aggregates only server-side, low weight as a covariate — never a trigger.
- **Automated exercise *form* grading.** Rep counting via periodicity on a joint-angle series is solved engineering; asserting "your form was incorrect" to a clinician without our own validation is a liability. Ship rep counts and cycle timing; withhold form quality.

---

## 2.8 Ranked backlog: clinical value ÷ engineering cost

**P0 — ship now, all of it is days-to-weeks and most is bug-fix-shaped**

| # | Work | File(s) | Cost | Why it ranks here |
|---|---|---|---|---|
| 1 | Filter `deleted_at`, `superseded_at`, `provenance` in the analytics loader; compute POD from `local_date`/`sleep_date` | `engine/dataload.py` | ~1 day | Two verified correctness bugs (G2, G3). RTM billing and analytics currently disagree about which day an observation belongs to, and deleted data drives risk scores forever. |
| 2 | Route `HRV_SDNN` and `SKIN_TEMP_DELTA` into the analysis; family-based weights + renormalization + `available_weight ≥ 0.60` gate | `pipeline.py`, `deviation.py`, `composite.py` | ~2 days | Every real Apple patient is currently scored at 0.55 of intended weight (G1). Masked by the seed generator, so it fails silently in production only. |
| 3 | Assistive-device capture + step suppression + segment isolation | new `assistive_device_periods`, `engine/steps_gate.py`, check-in form | ~3 days | Removes a 30–40% measurement artifact from the primary functional metric in exactly the window we monitor most. |
| 4 | Wear-time into the confidence gate; per-statement minimum-data rules; `daily_coverage` table | `engine/confidence.py`, `engine/wear.py` | ~3 days | The coverage gate is the regulatory posture for a stack of entirely general-wellness metrics, and it currently cannot distinguish "worn 20 minutes" from "worn all day" (G4). |
| 5 | Pain / ROM / adherence into the engine | `enums`-adjacent loaders, `metrics_cards.py` | ~3 days | Closes G5. RTM is defined around non-physiologic data; we currently analyze almost none of it. |
| 6 | Fix `compute_input_hash` (drop `date.today()`, add `max(revision)`); make `/worklist` read-only; ingestion-triggered recompute | `pipeline.py`, `api/worklist.py` | ~2 days | Verified performance bug: first request each day recomputes every patient *and regenerates LLM narratives* synchronously in one HTTP request. |
| 7 | `device_epochs` + `noise_sd` variance floors + baseline reset on device change | new model, `baseline.py` | ~3 days | Removes device-dependent alert rates; replaces the arbitrary 0.06 SD floor with published paired-difference SDs. |
| 8 | Append-only revision chain + partial unique index | `models/observation.py`, `connectors/ingest.py` | ~2 days | Without it, a restatement is unauditable and an RTM-billed statement cannot be reconstructed. |
| 9 | Log-transform HRV (and CRP) before standardizing | `baseline.py` | ~2 hours | Three lines; fixes a real distributional error (G8). |
| 10 | Drop `SPO2` from `KEY_METRICS`; add `SPO2_UNAVAILABLE_REGULATORY`; zero the sleep-duration composite weight | `confidence.py`, `composite.py` | ~1 day | Stops penalizing coverage by device brand; stops trusting a metric with 29–52% wake specificity. |

**P1 — next quarter**

11. `surgical_events` table + trajectory suspension on non-index events. 12. Junction connector + SQS FIFO topology + nightly 14-day trailing re-pull. 13. Phone-inclinometer ROM with MDC95 change gates. 14. Apple Mobility ingest with bouts-per-day gating and 7-day means. 15. ADT feed (Bamboo Pings / state HIE) — highest specificity per dollar in the entire section. 16. Lab connector + UCUM normalizer + CRP trajectory features with PPV logging.

**P2 — gated on data volume, with exact volumes**

| Capability | Gate |
|---|---|
| Empirical-Bayes priors μ_s, τ²_s per (procedure × age band × sex) | **≥200 patients per stratum with ≥7 pre-op valid days.** Below that, use a pooled-across-procedure prior with τ² inflated 2×, and gate statements on posterior SD, not day count. |
| Learned step-correction factor by (device, aid, speed band) | **≥60 patients × ≥14 paired days** against a hip/ankle reference. Until then: suppress, never correct. |
| Wear-proxy sensitivity/specificity | **≥30 patients × 14 days** against self-reported wear diaries. The 12-samples/hour and 90-minute thresholds are reasoned analogues of Choi's parameters, not validated numbers. |
| Recalibrated composite weights and tier thresholds | **≥300 episodes with ≥20 adjudicated complications.** Current weights (.25/.25/.20/.15/.15) and thresholds (>2.0, >1.2) have no empirical derivation. |
| Empirical CRP second-rise rule with sens/spec | **≥500 episodes with ≥2 CRPs and adjudicated PJI outcomes.** No published rule with numbers exists. |
| Circadian metrics (IS, IV, RA, M10/L5, SRI) | **Minute-level ingestion for ≥1,000 patient-days.** These are *uncomputable* from daily aggregates — RA, IS, IV, M10/L5 and SRI all require ≥hourly bins, and SRI needs 30-second epochs. Also unresolved: no study links any of them to SSI or PJI specifically; the delirium (amplitude Q1 vs Q4 HR 1.94) and mortality associations are in general populations. Treat as hypothesis, never as a claim in clinician-facing narrative. |
| Trajectory-curve empirical validation | **≥150 completed episodes per procedure.** Today `curves.py` is unfalsifiable by construction — the seed generator shapes on-track patients along the same curves, `CI_WIDTH = 0.08` is a flat band rather than a prediction interval, and `BEHIND` at −12% has no derivation (G6). |

**Refuse permanently:** cross-brand step or HR/HRV conversion factors; imputation into the detection path; autonomous SSI classification; GPS 6MWD reported as a distance; vendor sleep-stage percentages as clinical fact; double support time and walking asymmetry in tier logic; automated exercise-form grading; a direct Fitbit Web API connector (sunsets September 2026); a CRP band for ACL, arthroscopic rotator cuff, meniscectomy or ankle; and any FHIR write path beyond flowsheets, DocumentReference and QuestionnaireResponse.