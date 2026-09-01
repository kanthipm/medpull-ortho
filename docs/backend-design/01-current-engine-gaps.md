# Recovery Copilot — engine gap analysis (read from source, 2026-07-31)

Findings from reading `backend/app/` directly, independent of the literature research.

## G1. The Apple cohort silently loses half the composite index — CRITICAL

`models/enums.py` correctly separates the statistics Apple actually ships:
- `HRV_SDNN` (Apple has no RMSSD identifier)
- `SKIN_TEMP_DELTA` (Apple/Oura/Garmin/Health Connect ship a delta from personal
  baseline, which can be negative; WHOOP/Withings ship absolute °C)

`connectors/capabilities.py:28-29` declares Apple supplies exactly those two variants.

But the engine only ever analyzes the canonical forms:
- `engine/pipeline.py:ANALYZED_METRICS` lists `HRV_RMSSD` and `SKIN_TEMP` — not the variants
- `engine/deviation.py:ADVERSE_UP/ADVERSE_DOWN` reference only `SKIN_TEMP` / `HRV_RMSSD`
- `engine/composite.py:WEIGHTS` references only `SKIN_TEMP` (0.25) and `HRV_RMSSD` (0.20)

Consequence: for a real Apple patient, the composite deviation index is computed from
only RHR (0.25) + RR (0.15) + steps (0.15) = **0.55 of the intended 1.00 weight**, while
the tier thresholds (`HIGH > 2.0`, `ELEVATED > 1.2`) were calibrated against full weight.
An Apple-only patient needs roughly **1.8× the physiological derangement** to trip the same
tier. Skin temperature — one of the two strongest early infection signals — contributes
nothing at all.

This is masked in testing on purpose. `seed/generators.py:170-173` maps
`SKIN_TEMP -> {SKIN_TEMP, SKIN_TEMP_DELTA}` and `HRV_RMSSD -> {HRV_RMSSD, HRV_SDNN}` and
emits the *canonical* series for Apple patients, with a comment saying "in production
normalize() would land it in its own metric type". So the golden-tier tests pass and the
demo looks right, and the failure appears only when a real Apple Watch connects.

Fix requires two things, not one:
1. Route the variants into the analysis (add to `ANALYZED_METRICS`, adverse-direction sets).
2. **Do not treat SDNN and RMSSD as interchangeable** — there is no conversion constant, and
   their distributions differ. Either keep separate baselines per statistic (a z-score is
   comparable across statistics even when the raw value is not), or weight them as separate
   entries. Same for delta vs absolute temperature: a delta metric already *is* a deviation,
   so passing it through `compute_baseline` double-centers it.
3. Renormalize composite weights over the metrics actually present, or the threshold is
   device-dependent. (Renormalizing has its own hazard — it makes a single deviating metric
   look like a whole-body signal — so the honest fix is probably weight renormalization
   *plus* a minimum-metrics-present gate.)

## G2. Two different definitions of "a day" in one system

`models/observation.py` materializes `local_date` at ingest specifically so that
timezone handling is auditable, and `rtm/coverage.py` correctly counts monitoring days on
`local_date`.

But `engine/dataload.py:31` computes the post-op day as
`start_time.date() - surgery_date`, using the naive instant, ignoring `local_date` entirely.

So RTM billing-day counting and clinical analytics disagree about which day an observation
belongs to for any patient not in the server's timezone. The RTM 16-of-30 threshold is a
cliff, so this was fixed there; the analytics kept the bug.

## G3. Tombstoned and deleted observations still drive the analytics

`engine/dataload.py` selects observations filtering only `value_num IS NOT NULL`. It does
not filter `deleted_at IS NULL`.

HealthKit and Health Connect deliver deletions, and the model has a tombstone column
precisely so historical RTM counts don't inflate. `rtm/coverage.py` honors it
(`Observation.deleted_at.is_(None)`); the engine does not. A patient who deletes erroneous
data from their Health app keeps that data in their risk score forever.

Also unfiltered: `revision`. If restatements are stored as new rows rather than in-place
updates, `groupby("day").mean()` averages the original and the correction together.

## G4. `WEAR_TIME_MINUTES` exists but the confidence gate ignores it

`engine/confidence.py` scores coverage as "≥3 of 6 key metrics present on a day". The
`WEAR_TIME_MINUTES` metric type was added to distinguish "not worn" from "worn 40 minutes"
from "not synced" — and the confidence gate, which is the product's entire defense against
saying "Stable" about a patient nobody can see, doesn't consult it.

A provider that back-fills zeros, or a watch worn for 20 minutes a day, both score as full
coverage.

## G5. The RTM-qualifying data stream is stored but never analyzed — STRATEGIC

`models/enums.py` defines the patient-reported metrics that RTM codes are actually about:
`PAIN_NRS`, `RANGE_OF_MOTION`, `THERAPY_ADHERENCE`, `EXERCISE_REPS`, `PROM_SCORE`.

Grep confirms **none of them is referenced anywhere outside `enums.py`.** Not in
`ANALYZED_METRICS`, not in `deviation.py`, not in `composite.py`, not in `risk.py`, not in
`metrics_cards.py`.

Meanwhile the entire engine is built on heart rate, HRV, skin temperature, SpO2,
respiratory rate — physiologic data.

This matters beyond completeness: RTM (98975–98981) is defined by CMS as monitoring
**non-physiologic** data — musculoskeletal system status, therapy adherence, therapy
response. Physiologic data monitoring is RPM (99453–99458), a different code family. A
product that bills RTM while its analytics engine reads almost exclusively physiologic
signals has a substance-over-form problem worth confirming with the billing research.

`engine/adherence.py` does read a separate `AdherenceRecord` table, so adherence is covered
— but pain, ROM and PROMs, which are the clinically load-bearing therapeutic measures, are
not computed at all.

## G6. The expected recovery curves are unfalsifiable as currently validated

`engine/curves.py` hand-parameterizes a logistic per procedure (floor, r, d50) and the
docstring states plainly: "The seed generator shapes on-track patients along these same
curves, so 'on track' is on track by construction."

That is honest and fine for a demo. But it means the trajectory feature currently has
**zero empirical content** — the test suite cannot distinguish a well-calibrated curve from
an arbitrary one, and `TrajectoryState.BEHIND` at `-12%` is a threshold with no derivation.
`CI_WIDTH = 0.08` is a flat band, not a prediction interval, so it does not widen with
uncertainty or narrow with data.

## G7. Composite index has no multiplicity control and no hysteresis

`composite.py` sums weighted raw (unsmoothed) z-scores daily. `risk.py` re-evaluates every
run. Across ~9 analyzed metrics × N patients × daily recomputation, there is no false
discovery rate control and no debouncing: a patient can flip HIGH→MEDIUM→HIGH on
consecutive days, and each transition to HIGH fires a notification
(`pipeline.py` fires `notify_high_priority` on any not-HIGH → HIGH edge).

## G8. Smaller items

- `pipeline.py:compute_input_hash` uses `count + max(ingested_at) + date.today()`. A
  restatement that updates a row in place without changing the count and without advancing
  `ingested_at` would not invalidate the cache.
- `baseline.py` applies an SD floor, but HRV is log-normally distributed — z-scores on the
  raw scale are skewed, so a fixed relative floor (0.06) is doing distributional work it
  isn't designed for. Log-transform before standardizing is the standard fix.
- `deviation.py` `FUNCTIONAL_RATIO_SD = 0.10` is a single hard-coded constant applied to
  every patient and both functional metrics; real between-day variability in step counts is
  much larger and highly person-specific.
- `confidence.py` `KEY_METRICS` includes `SPO2` and `SKIN_TEMP`, which several providers
  don't supply at all — so coverage is systematically penalized by device brand rather than
  by actual wear.
