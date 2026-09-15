"""Static definitions of every care metric: identity, family, method
template, feasibility, guardrail flag, inputs, what unlocks it, and which
pathway domains it is meaningful for. The metric modules fill in the
computed fields; the API and the tests read the catalog for shape.

Families are generic (a pathway, not a specialty, decides which lead) and
listed in display order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import MetricType as M


@dataclass(frozen=True)
class MetricDef:
    id: str
    key: str
    name: str
    family: str
    template: str
    feasibility: str
    tier: int
    guarded: bool
    inputs: list[str]
    unlock: str
    feeds_from_tasks: list[str]
    method_short: str
    domains: list[str] = field(default_factory=lambda: ["all"])


FAMILIES: list[tuple[str, str, list[str]]] = [
    ("load", "Activity & load tolerance", ["M1", "M2", "M3"]),
    ("function", "Functional capacity", ["M4", "M5", "M6", "M7", "M8"]),
    ("quality", "Recovery quality & systemic state", ["M9", "M10", "M11", "C1", "C2"]),
    ("surveillance", "Deterioration surveillance", ["M12", "M13", "C4"]),
    ("metabolic", "Metabolic control", ["C3"]),
    ("symptoms", "Symptoms & burden", ["C5", "C6"]),
    ("engagement", "Adherence & engagement", ["M14", "M15", "M16"]),
    ("trajectory", "Trajectory & benchmarking", ["M17", "M18"]),
]

FAMILY_NAME = {key: name for key, name, _ in FAMILIES}


def family_of(metric_id: str) -> str:
    for key, _, ids in FAMILIES:
        if metric_id in ids:
            return key
    return "load"


_DEFS: list[MetricDef] = [
    MetricDef(
        "M1", "acute_chronic_load", "Acute:chronic load ratio", "load", "T-A", "Derived", 1,
        False, [str(M.STEPS)],
        "Needs at least a week of daily activity (steps, active energy or exercise minutes).",
        ["steps_min", "steps_band", "walk_bouts", "distance_target"],
        "7-day mean load divided by the 28-day mean, judged against the tolerance band.",
    ),
    MetricDef(
        "M2", "load_pain_slope", "Symptom–load sensitivity", "load", "T-D", "Derived+App", 1,
        False, [str(M.STEPS), str(M.PAIN_NRS)],
        "Needs daily pain logs — the check-in collects them; assign the *Log pain AM & PM* task.",
        ["pain_log", "symptom_log", "steps_min", "steps_band"],
        "OLS regression of next-day symptom score on same-day load, last 21 days.",
    ),
    MetricDef(
        "M3", "asymmetry_decay", "Loading asymmetry decay", "load", "T-B+T-A", "Derived/Raw", 1,
        False, [str(M.WALKING_ASYMMETRY_PCT)],
        "Needs Apple gait metrics (iPhone/Watch via the patient app) or an in-app guided walk.",
        ["guided_walk", "continuous_walk"],
        "Exponential-decay fit of daily walking asymmetry with a change-point on the plateau.",
        ["ortho"],
    ),
    MetricDef(
        "M4", "walking_economy", "Walking economy", "function", "T-D", "Derived", 2,
        False, [str(M.EXERCISE_SESSION), str(M.RESTING_HR)],
        "Needs heart rate and cadence during walks — captured by the *In-app guided walk* "
        "task, or Junction heart-rate samples plus walking speed.",
        ["guided_walk", "continuous_walk"],
        "Heart-rate reserve per unit of cadence across recent walks, trended by session.",
    ),
    MetricDef(
        "M5", "endurance_fade", "Endurance-fade index", "function", "T-B+T-C", "Derived/Raw", 2,
        False, [str(M.EXERCISE_SESSION)],
        "Needs heart rate and cadence during walks — captured by the *In-app guided walk* "
        "task, or Junction heart-rate samples plus walking speed.",
        ["guided_walk", "continuous_walk"],
        "Slope of per-minute cadence within each walk, as % of the opening cadence per minute.",
    ),
    MetricDef(
        "M6", "sit_to_stand", "Sit-to-stand frequency", "function", "T-B", "Raw/App", 2,
        False, [str(M.SIT_TO_STAND)],
        "Needs the *5 sit-to-stands AM & PM* task (counted in the check-in) or the patient "
        "app's motion capture.",
        ["sit_to_stand"],
        "Daily chair-rise counts, last 7 days against the 7 before.",
        ["ortho", "general", "pain"],
    ),
    MetricDef(
        "M7", "cadence_recovery", "Cadence recovery curve", "function", "T-A", "Derived", 1,
        False, [str(M.WALKING_SPEED), str(M.STEP_LENGTH)],
        "Needs walking speed (Apple gait) or the guided-walk task.",
        ["guided_walk", "continuous_walk"],
        "Self-selected cadence (or pace) against the expected curve and the patient's own trend.",
    ),
    MetricDef(
        "M8", "stairs", "Stair reintroduction & flight tolerance", "function", "T-A+T-B",
        "Derived/Raw", 1, False, [str(M.FLIGHTS_CLIMBED), str(M.STAIR_SPEED_UP)],
        "Needs flights climbed (Apple Watch/iPhone via the patient app) or the *Climb one "
        "flight of stairs* task's self-report.",
        ["stairs"],
        "First day stairs re-enter the routine, then weekly flight totals for a plateau.",
        ["ortho", "general", "cardiac", "pulmonary", "pain"],
    ),
    MetricDef(
        "M9", "nocturnal_disruption", "Nocturnal disruption", "quality", "T-B+T-A+T-D",
        "Derived+App", 1, False, [str(M.SLEEP_STAGES), str(M.PAIN_NRS)],
        "Needs overnight wear (sleep stages) and evening pain logs — the *Wear your watch "
        "overnight* and *Log pain AM & PM* tasks.",
        ["overnight_wear", "pain_log"],
        "Nightly awake fraction vs the patient's baseline, correlated with evening symptom score.",
    ),
    MetricDef(
        "M10", "autonomic_recovery", "Autonomic recovery trend", "quality", "T-A+T-D",
        "Derived", 1, False, [str(M.HRV_RMSSD), str(M.RESTING_HR)],
        "Needs overnight HRV and resting heart rate — wear the watch overnight.",
        ["overnight_wear"],
        "Mean of the HRV and resting-HR EWMA z-scores (adverse-positive), last 7 days.",
    ),
    MetricDef(
        "M11", "circadian_amplitude", "Circadian rest–activity amplitude", "quality",
        "T-C+T-A", "Derived", 3, False, [str(M.STEPS), str(M.HR_SAMPLE)],
        "Needs hourly activity or heart-rate samples — enable Junction heart-rate samples, or "
        "the patient app's hourly activity sync.",
        ["move_hourly", "overnight_wear"],
        "Per-day 24 h cosinor on hourly activity: relative amplitude and interdaily stability.",
    ),
    MetricDef(
        "M12", "deterioration_index", "Multi-signal deterioration index", "surveillance",
        "T-D", "Derived", 1, True,
        [str(M.RESTING_HR), str(M.RESPIRATORY_RATE), str(M.SKIN_TEMP), str(M.HRV_RMSSD),
         str(M.SPO2)],
        "Needs at least three overnight vitals (resting HR, HRV, skin temperature, SpO₂, "
        "respiratory rate) reporting within the last 5 days.",
        ["overnight_wear"],
        "Mahalanobis distance of today's z-scores from the patient's own 14-day multivariate "
        "baseline (shrinkage covariance), alongside the weighted composite used for the risk "
        "tier.",
    ),
    MetricDef(
        "M13", "thermal_cardiac_coupling", "Thermal–cardiac coupling", "surveillance",
        "T-D", "Derived", 2, True, [str(M.SKIN_TEMP), str(M.RESTING_HR), str(M.HRV_RMSSD)],
        "Needs skin temperature and resting heart rate from an overnight-worn device.",
        ["overnight_wear"],
        "Correlation and lag between skin-temperature and resting-HR z-scores over the last "
        "7 nights, counting nights where both rise with HRV suppressed.",
    ),
    MetricDef(
        "M14", "verified_adherence", "Verified adherence", "engagement", "T-A", "App+Derived", 1,
        False, ["adherence_records"],
        "Assign tasks from the plan builder — completion is verified against wearable data "
        "where possible.",
        [],
        "Verified and self-reported completions over assigned task-days, last 14 days.",
    ),
    MetricDef(
        "M15", "disengagement_risk", "Disengagement risk", "engagement", "T-A+T-D",
        "App+Derived", 1, False, ["checkins", str(M.STEPS), "adherence_records"],
        "Needs check-ins or assigned tasks to measure engagement against.",
        ["pain_log", "symptom_log"],
        "Weighted score of check-in latency, shrinking replies, falling movement and missed "
        "tasks.",
    ),
    MetricDef(
        "M16", "data_confidence", "Data confidence", "engagement", "T-A", "Derived", 1,
        False, ["device_sync", str(M.WEAR_TIME_MINUTES)],
        "Connect a wearable — coverage is measured from what it reports.",
        ["overnight_wear"],
        "Share of the last 7 days with at least three key signals, panel coverage, and sync "
        "freshness.",
    ),
    MetricDef(
        "M17", "trajectory_fit", "Recovery-trajectory fit", "trajectory", "T-D", "Derived", 1,
        False, [str(M.STEPS), str(M.WALKING_SPEED)],
        "Needs a few more days of steps (and walking speed) with a pre-op or early post-op "
        "anchor.",
        ["steps_min", "steps_band"],
        "Saturating-exponential fit of the functional index; recovery rate vs the expected "
        "curve's own rate.",
    ),
    MetricDef(
        "M18", "change_point", "Plateau / regression change-point", "trajectory", "T-A",
        "Derived", 1, False,
        [str(M.STEPS), str(M.WALKING_SPEED), str(M.SLEEP_DURATION), str(M.RESTING_HR)],
        "Needs at least eight days of daily steps or walking speed.",
        ["steps_min", "steps_band"],
        "CUSUM binary segmentation of each daily series over the last 28 days; the most recent "
        "adverse mean shift.",
    ),
    MetricDef(
        "C1", "weight_trend", "Weight trend & fluid-gain signal", "quality", "T-A",
        "Derived", 1, True, [str(M.BODY_WEIGHT)],
        "Needs a connected scale (Withings) or a daily weight log — assign the *Weigh yourself "
        "every morning* task.",
        ["medication_log", "symptom_log"],
        "Daily weight against its 14-day median; 24 h and 7-day gains.",
        ["cardiac", "general", "metabolic"],
    ),
    MetricDef(
        "C2", "spo2_burden", "Oxygen saturation & desaturation burden", "quality", "T-A",
        "Derived", 1, True, [str(M.SPO2)],
        "Needs overnight SpO₂ from a wearable or a pulse-oximeter log.",
        ["overnight_wear", "symptom_log"],
        "Days in the last 7 with mean SpO₂ under 90 %, with the EWMA control chart vs baseline.",
        ["pulmonary", "cardiac", "general"],
    ),
    MetricDef(
        "C3", "glucose_tir", "Glucose time-in-range", "metabolic", "T-A", "Derived", 1,
        False, [str(M.BLOOD_GLUCOSE)],
        "Needs a CGM (Dexcom via Junction) or a glucose log.",
        ["medication_log", "symptom_log"],
        "Share of the last 14 days' readings between 70 and 180 mg/dL; readings under 70 "
        "counted.",
        ["metabolic"],
    ),
    MetricDef(
        "C4", "bp_control", "Blood-pressure control", "surveillance", "T-A", "Derived", 1,
        True, [str(M.BLOOD_PRESSURE_SYSTOLIC), str(M.BLOOD_PRESSURE_DIASTOLIC)],
        "Needs a connected cuff (Withings) or an AM/PM blood-pressure log.",
        ["medication_log"],
        "7-day mean and the share of readings at or above 140/90 mmHg.",
        ["cardiac", "metabolic", "general"],
    ),
    MetricDef(
        "C5", "symptom_burden", "Symptom burden trend", "symptoms", "T-A", "App", 1,
        False, [str(M.PAIN_NRS), str(M.BREATHLESSNESS), str(M.FATIGUE), "checkins"],
        "Needs daily symptom logs — the check-in collects them.",
        ["pain_log", "symptom_log"],
        "Daily symptom score from logs and check-in answers; level and slope over 14 days.",
    ),
    MetricDef(
        "C6", "sedentary_burden", "Sedentary burden", "symptoms", "T-A", "Derived", 2,
        False, [str(M.STEPS)],
        "Needs daily steps (hourly buckets from the patient app give the finer picture).",
        ["move_hourly", "sedentary_limit"],
        "Waking hours under 50 steps per day from hourly buckets, else days under 1,500 steps.",
    ),
]

CATALOG: dict[str, MetricDef] = {d.id: d for d in _DEFS}
CATALOG_ORDER: list[str] = [d.id for d in _DEFS]


def families_payload() -> list[dict[str, object]]:
    return [{"key": key, "name": name, "metric_ids": list(ids)} for key, name, ids in FAMILIES]
