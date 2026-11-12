"""The metric dictionary: every reading MedPull stores, what it is measured
in, where it comes from and what the engine does with it.

Assembled from the modules that own each fact rather than restated here, so
the dictionary cannot drift from the engine it describes:

* the vocabulary        ``MetricType`` and ``SourceProvider`` (models/enums)
* storage units         ``connectors/mock.UNITS`` (the one table every writer
                        and the seed share)
* labels, shown units   the signal cards (``metrics_cards.CARD_ORDER``), and
                        the short table below for the types with no card
* tier                  ``pipeline.ANALYZED_METRICS`` (scored in the risk
                        read), the cards (display only), a declared writer
                        (stored), or nothing (declared, no writer yet)
* aggregation, source   ``dataload.ADDITIVE`` and ``dataload.source_rank``
  precedence
* direction, reference  ``deviation.ADVERSE_UP`` / ``ADVERSE_DOWN`` /
                        ``CURVE_SCALED``
* recency, SD floors    ``deviation.RECENCY_WINDOW_DAYS``, the cards' slow
                        windows, ``baseline.SD_FLOORS_*``
* plausible range       ``connectors/ingest.PLAUSIBLE_RANGE``
* providers             ``connectors/capabilities.CAPABILITIES``
* in-house methods      ``engine/mobility`` (one sentence per metric below,
                        with its constants read from the module that uses
                        them) and ``mobility.VERSION``
* care metrics          ``care/catalog`` and the glossary (``engine/explain``)

``family_of`` is also what the Data tab's roster and raw-reading views group
by. Nothing here touches the database.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.connectors.capabilities import CAPABILITIES
from app.connectors.ingest import PLAUSIBLE_RANGE
from app.connectors.mock import UNITS as STORAGE_UNITS
from app.connectors.registry import PROVIDERS
from app.engine import ENGINE_VERSION
from app.engine.baseline import (
    ANCHOR_DAYS,
    FIRM_BASELINE_DAYS,
    MIN_BASELINE_DAYS,
    SD_FLOORS_ABS,
    SD_FLOORS_REL,
    SKIP_EARLY_DAYS,
)
from app.engine.care import CARE_VERSION
from app.engine.care.catalog import CATALOG, CATALOG_ORDER, FAMILY_NAME, families_payload
from app.engine.dataload import ADDITIVE, source_rank
from app.engine.deviation import (
    ADVERSE_DOWN,
    ADVERSE_UP,
    CURVE_SCALED,
    CUSUM_H,
    CUSUM_K,
    CUSUM_WINDOW,
    EWMA_L,
    EWMA_LAMBDA,
    RECENCY_WINDOW_DAYS,
)
from app.engine.explain import METRICS as CARE_EXPLAINED
from app.engine.explain import SIGNALS as SIGNALS_EXPLAINED
from app.engine.metrics_cards import (
    CARD_ORDER,
    DOUBLE_SUPPORT_FLAG_PCT,
    DOUBLE_SUPPORT_OK_PCT,
    GAIT_OK_PCT,
    SLOW_RECENCY_DAYS,
    STEADINESS_LOW,
    STEADINESS_VERY_LOW,
    STRESS_FLAG,
    STRESS_WATCH,
)
from app.engine.mobility import VERSION as MOBILITY_VERSION
from app.engine.mobility import active, spatial, stability, stairs, stress
from app.engine.pipeline import ANALYZED_METRICS, DISPLAY_METRICS
from app.engine.risk import GAIT_FLAG_AFTER_DAY, GAIT_FLAG_PCT
from app.engine.sources import MEASURE_TEST
from app.models.enums import Granularity
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider as P

# --- families ------------------------------------------------------------------------
#
# The eight columns of the roster view, in display order. Seven are groups of
# observation types; the eighth is the exercise calendar's own table (what a
# patient did against what the therapist put on their day), which is not an
# observation and has no MetricType.

EXERCISE_SESSIONS = "exercise_sessions"

FAMILIES: list[tuple[str, str, tuple[M, ...]]] = [
    ("sleep", "Sleep", (M.SLEEP_DURATION, M.SLEEP_STAGES)),
    ("cardiac", "Heart and autonomic", (
        M.RESTING_HR, M.HR_SAMPLE, M.HRV_RMSSD, M.HRV_SDNN, M.SPO2, M.RESPIRATORY_RATE,
        M.SKIN_TEMP, M.SKIN_TEMP_DELTA, M.STRESS_INDEX, M.VO2_MAX, M.HR_RECOVERY_1MIN,
    )),
    ("activity", "Activity", (
        M.STEPS, M.ACTIVE_ENERGY, M.CALORIES, M.EXERCISE_SESSION, M.FLIGHTS_CLIMBED,
        M.SIT_TO_STAND, M.WEAR_TIME_MINUTES,
    )),
    ("mobility", "Mobility and gait", (
        M.WALKING_SPEED, M.STEP_LENGTH, M.CADENCE, M.DOUBLE_SUPPORT_PCT,
        M.WALKING_ASYMMETRY_PCT, M.WALKING_STEADINESS, M.STAIR_SPEED_UP, M.STAIR_SPEED_DOWN,
        M.SIX_MIN_WALK, M.ROM_FLEXION, M.ROM_EXTENSION, M.ROM_ABDUCTION, M.RANGE_OF_MOTION,
    )),
    ("body", "Body and chronic care", (
        M.BODY_WEIGHT, M.BLOOD_PRESSURE_SYSTOLIC, M.BLOOD_PRESSURE_DIASTOLIC, M.BLOOD_GLUCOSE,
    )),
    ("reported", "Reported", (
        M.PAIN_NRS, M.BREATHLESSNESS, M.FATIGUE, M.THERAPY_ADHERENCE, M.EXERCISE_REPS,
        M.PROM_SCORE,
    )),
    ("training_load", "Training load", (M.SESSION_LOAD, M.PROGRAM_DONE)),
]
FAMILY_KEYS: tuple[str, ...] = tuple(key for key, _, _ in FAMILIES) + (EXERCISE_SESSIONS,)
FAMILY_NAMES: dict[str, str] = {key: name for key, name, _ in FAMILIES} | {
    EXERCISE_SESSIONS: "Exercise sessions",
}
# The families a stored reading can belong to (everything but the calendar's).
OBSERVATION_FAMILIES: tuple[str, ...] = tuple(key for key, _, _ in FAMILIES)
_FAMILY_OF: dict[str, str] = {str(m): key for key, _, members in FAMILIES for m in members}


def family_of(metric_type: str) -> str | None:
    """The family a stored metric type belongs to. None for a name this
    build does not know (a row written by a newer one)."""
    return _FAMILY_OF.get(str(metric_type))


def family_metrics(family: str) -> list[str]:
    return [str(m) for key, _, members in FAMILIES if key == family for m in members]


# --- labels and shown units -----------------------------------------------------------

# Types with no signal card: (label, unit as shown). Where the patient app's
# portfolio shows the same type (api/mobile.PORTFOLIO_METRICS) the words match
# it; tests/test_data_api.py holds the two in step.
_UNCARDED: dict[M, tuple[str, str]] = {
    M.HR_SAMPLE: ("Heart rate sample", "bpm"),
    M.SLEEP_STAGES: ("Sleep stages", "h"),
    M.FLIGHTS_CLIMBED: ("Flights climbed", "flights"),
    M.SIT_TO_STAND: ("Sit-to-stands", "rises"),
    M.WEAR_TIME_MINUTES: ("Wear time", "min"),
    M.VO2_MAX: ("VO2 max", "mL/kg/min"),
    M.HR_RECOVERY_1MIN: ("Heart rate recovery", "bpm"),
    M.RANGE_OF_MOTION: ("Range of motion", "°"),
    M.BODY_WEIGHT: ("Weight", "kg"),
    M.BLOOD_PRESSURE_SYSTOLIC: ("Blood pressure (systolic)", "mmHg"),
    M.BLOOD_PRESSURE_DIASTOLIC: ("Blood pressure (diastolic)", "mmHg"),
    M.BLOOD_GLUCOSE: ("Blood glucose", "mg/dL"),
    M.PAIN_NRS: ("Pain", "/10"),
    M.BREATHLESSNESS: ("Breathlessness", "0–4"),
    M.FATIGUE: ("Fatigue", "/10"),
    M.THERAPY_ADHERENCE: ("Therapy sessions done", "fraction"),
    M.EXERCISE_REPS: ("Exercise repetitions", "reps"),
    M.PROM_SCORE: ("Outcome questionnaire score", "score"),
    M.SESSION_LOAD: ("Session load (effort × minutes)", "au"),
    M.PROGRAM_DONE: ("Program done", "of the day"),
}
_CARDS: dict[M, tuple[str, str, bool]] = {m: (name, unit, guarded)
                                          for m, name, unit, guarded in CARD_ORDER}


def label_unit(metric: M) -> tuple[str, str]:
    """(label, unit as shown) for a metric type: the signal card's when it
    has one."""
    if metric in _CARDS:
        name, unit, _ = _CARDS[metric]
        return name, unit
    return _UNCARDED[metric]


# --- tiers ---------------------------------------------------------------------------

SCORED, DISPLAY, STORED, DECLARED = "scored", "display", "stored", "declared"
TIERS: list[dict[str, str]] = [
    {"key": SCORED, "label": "Scored in the risk read",
     "description": "Judged against the person's own baseline or the expected recovery "
                    "curve, and able to move the risk tier."},
    {"key": DISPLAY, "label": "Display only",
     "description": "Charted and judged on its own card for the clinician; never an input "
                    "to the risk tier, the composite or the trajectory."},
    {"key": STORED, "label": "Stored only",
     "description": "Kept with its provenance and read by the care metrics that name it; "
                    "no signal card of its own."},
    {"key": DECLARED, "label": "Declared, no writer yet",
     "description": "In the vocabulary so its unit and range are settled; nothing writes "
                    "it yet."},
]

# What the reported risk read takes from the observation table, for a chart
# followed by text check-in with no wearable (engine/reported.py): the two
# training answers, and pain where it was logged as a number.
REPORTED_INPUTS: tuple[M, ...] = (M.SESSION_LOAD, M.PROGRAM_DONE, M.PAIN_NRS)

# Types a person reports rather than a device: the lifter check-in writes the
# two training rows (tasks/reported.py); pain and chair-rise counts arrive as
# logged numbers. CAPABILITIES covers devices only, so these are named here.
_REPORTED_WRITERS: dict[M, tuple[P, ...]] = {
    M.SESSION_LOAD: (P.PATIENT_REPORTED,),
    M.PROGRAM_DONE: (P.PATIENT_REPORTED,),
    M.PAIN_NRS: (P.PATIENT_REPORTED,),
    M.SIT_TO_STAND: (P.PATIENT_REPORTED,),
}


def _providers(metric: M) -> list[str]:
    """Who can supply this type: the capability map (the demo connector left
    out), MedPull for what it computes, and a person for what they report."""
    supplied = [str(p) for p, metrics in CAPABILITIES.items() if metric in metrics and p is not P.MOCK]
    supplied += [str(p) for p in _REPORTED_WRITERS.get(metric, ())]
    return sorted(set(supplied), key=lambda p: (source_rank(p), p))


def _tier(metric: M, providers: list[str]) -> str:
    if metric in ANALYZED_METRICS or metric in REPORTED_INPUTS:
        return SCORED
    if metric in _CARDS:
        return DISPLAY
    return STORED if providers else DECLARED


# --- how a metric is judged -----------------------------------------------------------


def _reference(metric: M) -> str | None:
    """What a day is compared with: the expected recovery curve for the
    procedure, the person's own baseline, or nothing (not judged)."""
    if metric not in ANALYZED_METRICS and metric not in DISPLAY_METRICS:
        return None
    return "curve" if metric in CURVE_SCALED else "baseline"


def _adverse(metric: M) -> str | None:
    if metric in ADVERSE_UP:
        return "up"
    if metric in ADVERSE_DOWN:
        return "down"
    return None


# Metrics read on absolute bands rather than (or as well as) a control chart.
_BANDS: dict[M, dict[str, float]] = {
    M.WALKING_ASYMMETRY_PCT: {"ok_at_or_below": GAIT_OK_PCT, "flag_above": GAIT_FLAG_PCT,
                              "flag_after_day": float(GAIT_FLAG_AFTER_DAY)},
    M.DOUBLE_SUPPORT_PCT: {"ok_at_or_below": DOUBLE_SUPPORT_OK_PCT,
                           "flag_above": DOUBLE_SUPPORT_FLAG_PCT,
                           "flag_after_day": float(GAIT_FLAG_AFTER_DAY)},
    M.WALKING_STEADINESS: {"ok_at_or_above": STEADINESS_LOW, "flag_below": STEADINESS_VERY_LOW},
    M.STRESS_INDEX: {"watch_at_or_above": STRESS_WATCH, "flag_at_or_above": STRESS_FLAG},
}


def _sd_floor(metric: M) -> dict[str, float] | None:
    key = str(metric)
    floor: dict[str, float] = {}
    if key in SD_FLOORS_ABS:
        floor["absolute"] = SD_FLOORS_ABS[key]
    if key in SD_FLOORS_REL:
        floor["fraction_of_mean"] = SD_FLOORS_REL[key]
    return floor or None


# --- MedPull's own measurements -------------------------------------------------------

_STAIRS = (f"Vertical speed over a flight from the phone's barometer: a height change of at "
           f"least {stairs.FLIGHT_MIN_M:g} m with steps being taken, timed between its 10% and "
           f"90% crossings.")
_ROM = ("Phone inclinometer: the change in the phone's tilt between a reference hold and a "
        "movement hold, with the phone resting along the limb segment.")
IN_HOUSE_METHODS: dict[M, str] = {
    M.CADENCE: "Steps are found as peaks of the band-passed acceleration magnitude; cadence "
               "is 60 divided by the mean time between steps.",
    M.STEP_LENGTH: f"Inverted-pendulum model: each step's length from the body's vertical "
                   f"excursion and leg length ({spatial.LEG_LENGTH_RATIO:g} × height), scaled by "
                   f"K = {spatial.K_DEFAULT:g} or a K calibrated against a GPS distance.",
    M.WALKING_SPEED: "Distance walked in a bout (the sum of its inverted-pendulum step "
                     "lengths) divided by the bout's duration.",
    M.WALKING_ASYMMETRY_PCT: "The difference between the two legs' mean step times as a "
                             "percentage of the mean step time, with each foot contact assigned "
                             "to a leg from the thigh gyroscope's gait phases (alternate steps "
                             "are compared, unsigned, when the phases cannot be read).",
    M.DOUBLE_SUPPORT_PCT: "100 × (1 − 2 × swing ÷ stride), with swing and stride timed from "
                          "the thigh gyroscope's gait phases.",
    M.WALKING_STEADINESS: f"A 0–100 index: the weighted mean of step-time variability, stride "
                          f"regularity, harmonic ratio and walking speed, each mapped through a "
                          f"logistic; {stability.LOW:g} and above reads OK, under "
                          f"{stability.VERY_LOW:g} very low.",
    M.STAIR_SPEED_UP: _STAIRS,
    M.STAIR_SPEED_DOWN: _STAIRS,
    M.SIX_MIN_WALK: f"Distance over the timed six minutes from the best evidence the phone "
                    f"has: GPS path length, else the phone's pedometer distance, else steps × "
                    f"inverted-pendulum step length, else steps × "
                    f"{active.STEP_LENGTH_HEIGHT_RATIO:g} × height.",
    M.ROM_FLEXION: _ROM,
    M.ROM_EXTENSION: _ROM,
    M.ROM_ABDUCTION: _ROM,
    M.EXERCISE_SESSION: "The guided walk recorded as one session: its minutes, with cadence "
                        "and speed for each minute.",
    M.STRESS_INDEX: f"50 + 25 × the weighted strain z of ln(HRV) "
                    f"({stress.WEIGHTS['hrv']:g}), resting heart rate ({stress.WEIGHTS['rhr']:g}) "
                    f"and respiratory rate ({stress.WEIGHTS['rr']:g}) against the person's own "
                    f"trailing {stress.BASELINE_DAYS} days; computed on every engine run, never "
                    f"stored as a reading.",
}


# --- sources -------------------------------------------------------------------------

_PROVIDER_NAMES: dict[P, str] = {info.key: info.name for info in PROVIDERS} | {
    P.TERRA: "Terra",
    P.GOOGLE_HEALTH: "Google Health",
    P.PATIENT_REPORTED: "Reported by the patient",
    P.CLINICIAN_ENTERED: "Entered by a clinician",
    P.MEDPULL: "MedPull",
}
RANK_LABELS: dict[int, str] = {
    0: "MedPull's own measurement",
    1: "The device maker's cloud",
    2: "The phone's health store",
    3: "Typed by a person",
}
PRECEDENCE_RULE = ("One source per metric and day: the best-ranked source that reported that "
                   "day supplies the day's value. Readings from the other sources stay in the "
                   "table for comparison and never enter the series.")
AGGREGATION_RULES = {
    "mean": "The day's value is the mean of that day's readings from the winning source.",
    "additive": "The day's value is the source's daily summary when it sent one, otherwise "
                "the sum of that day's readings.",
}


def source_name(provider: str) -> str:
    try:
        return _PROVIDER_NAMES[P(provider)]
    except ValueError:
        return str(provider)


# --- the care metrics ---------------------------------------------------------------

# What each care metric's headline value is measured in, and the short
# labels the metric itself prints beside that value (``CareMetric.unit``; a
# metric has more than one when it can read a different load source or fall
# back to fewer inputs). The metric functions own the labels
# (engine/care/*.py pass them to ``build``); tests/test_data_api.py holds
# this table in step with every stored assessment.
CARE_UNITS: dict[str, tuple[str, tuple[str, ...]]] = {
    "M1": ("ratio", ("ratio",)),
    "M2": ("points per 1,000 steps",
           ("pts / 1k steps", "pts / 100 kcal", "pts / 10 min", "pts / 100 load")),
    "M3": ("%", ("%",)),
    "M4": ("bpm per step/min", ("bpm / spm", "bpm / 0.1 m/s")),
    "M5": ("% per minute", ("%/min",)),
    "M6": ("rises per day", ("rises/day",)),
    "M7": ("steps/min", ("spm", "m/s")),
    "M8": ("flights per day", ("flights/day",)),
    "M9": ("% of the night awake", ("fragmented", "sleep duration only")),
    "M10": ("σ", ("σ",)),
    "M11": ("relative amplitude, 0–1", ("rel. amplitude",)),
    "M12": ("σ", ("σ",)),
    "M13": ("nights of the last 7", ("coupled nights",)),
    "M14": ("% of task-days", ("verified",)),
    "M15": ("0–100", ("/100",)),
    "M16": ("% of days", ("coverage", "check-ins")),
    "M17": ("% vs expected", ("vs expected", "per week")),
    "M18": ("post-op day", ("",)),
    "C1": ("kg", ("kg",)),
    "C2": ("%", ("%",)),
    "C3": ("% of readings", ("%",)),
    "C4": ("mmHg", ("mmHg",)),
    "C5": ("0–10", ("/10",)),
    "C6": ("hours per day", ("sedentary h/day", "inactive days / 7")),
}


def _care_metric(metric_id: str) -> dict[str, Any]:
    d = CATALOG[metric_id]
    explained = CARE_EXPLAINED.get(metric_id, {})
    unit, value_units = CARE_UNITS[metric_id]
    return {
        "id": d.id,
        "key": d.key,
        "name": d.name,
        "family": d.family,
        "family_name": FAMILY_NAME[d.family],
        "unit": unit,
        "value_units": list(value_units),
        "guarded": d.guarded,
        "what": explained.get("what"),
        "method": d.method_short,
        "inputs": list(d.inputs),
        "inputs_text": explained.get("inputs"),
        "shows_after": explained.get("shows_after"),
        "needs": d.unlock,
        "pathways": list(d.domains),
    }


# --- the dictionary ------------------------------------------------------------------


def _metric(metric: M) -> dict[str, Any]:
    key = str(metric)
    label, unit = label_unit(metric)
    providers = _providers(metric)
    judged = _reference(metric) is not None
    explained = SIGNALS_EXPLAINED.get(key, {})
    in_house = metric in IN_HOUSE_METHODS
    return {
        "key": key,
        "label": label,
        "family": _FAMILY_OF[key],
        "unit": unit,
        "storage_unit": STORAGE_UNITS[metric],
        "tier": _tier(metric, providers),
        # "device": one of the wearable signals the tier is built on;
        # "reported": read by the tier only for a chart followed by check-ins
        # with no wearable.
        "scored_on": ("device" if metric in ANALYZED_METRICS
                      else "reported" if metric in REPORTED_INPUTS else None),
        "on_panel": metric in _CARDS,
        "guarded": _CARDS[metric][2] if metric in _CARDS else False,
        "aggregation": "additive" if key in ADDITIVE else "mean",
        "adverse": _adverse(metric),
        "reference": _reference(metric),
        "bands": _BANDS.get(metric),
        "recency_days": SLOW_RECENCY_DAYS.get(metric, RECENCY_WINDOW_DAYS) if judged else None,
        "sd_floor": _sd_floor(metric),
        "plausible": list(PLAUSIBLE_RANGE[key]) if key in PLAUSIBLE_RANGE else None,
        "providers": providers,
        "in_house": in_house,
        "method": IN_HOUSE_METHODS.get(metric),
        "method_version": MOBILITY_VERSION if in_house else None,
        "measured_by": MEASURE_TEST.get(metric),
        "computed": metric is M.STRESS_INDEX,
        "what": explained.get("what"),
        "explain_key": key if key in SIGNALS_EXPLAINED else None,
        "care_metrics": [d.id for d in CATALOG.values() if key in d.inputs],
    }


def _check_complete() -> None:
    """Every type in the vocabulary has a family, a label and a storage unit,
    and every in-house metric a method. Run at import: a MetricType added
    without them should stop the process, not leave a hole in the dictionary."""
    for metric in M:
        if str(metric) not in _FAMILY_OF:
            raise RuntimeError(f"data_catalog: {metric} has no family")
        if metric not in STORAGE_UNITS:
            raise RuntimeError(f"data_catalog: {metric} has no storage unit")
        if metric not in _CARDS and metric not in _UNCARDED:
            raise RuntimeError(f"data_catalog: {metric} has no label")
    for metric in CAPABILITIES[P.MEDPULL]:
        if metric not in IN_HOUSE_METHODS:
            raise RuntimeError(f"data_catalog: {metric} is computed in-house and has no method")
    for provider in P:
        if provider not in _PROVIDER_NAMES:
            raise RuntimeError(f"data_catalog: {provider} has no name")
    for metric_id in CATALOG_ORDER:
        if metric_id not in CARE_UNITS:
            raise RuntimeError(f"data_catalog: {metric_id} has no unit")


_check_complete()


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    """The whole dictionary as plain JSON. Static for the life of a process."""
    return {
        "versions": {"engine": ENGINE_VERSION, "care": CARE_VERSION, "mobility": MOBILITY_VERSION},
        "tiers": TIERS,
        "families": [
            {"key": key, "name": name, "stored_in": "observations",
             "metrics": [str(m) for m in members]}
            for key, name, members in FAMILIES
        ] + [
            {"key": EXERCISE_SESSIONS, "name": FAMILY_NAMES[EXERCISE_SESSIONS],
             "stored_in": "exercise_assignments", "metrics": []},
        ],
        "metrics": [_metric(m) for _, _, members in FAMILIES for m in members],
        "granularities": [str(g) for g in Granularity],
        "sources": [
            {"key": str(p), "name": _PROVIDER_NAMES[p], "rank": source_rank(str(p)),
             "rank_label": RANK_LABELS[source_rank(str(p))]}
            for p in sorted(P, key=lambda p: (source_rank(str(p)), str(p)))
        ],
        "precedence": {
            "rule": PRECEDENCE_RULE,
            "ranks": [{"rank": rank, "label": label} for rank, label in RANK_LABELS.items()],
        },
        "aggregation": AGGREGATION_RULES,
        "baseline": {
            "min_days": MIN_BASELINE_DAYS,
            "firm_days": FIRM_BASELINE_DAYS,
            "anchor_days": ANCHOR_DAYS,
            "scored_from_day": SKIP_EARLY_DAYS,
        },
        "control_chart": {
            "ewma_lambda": EWMA_LAMBDA,
            "ewma_limit_sigmas": EWMA_L,
            "cusum_k": CUSUM_K,
            "cusum_h": CUSUM_H,
            "cusum_window_days": CUSUM_WINDOW,
            "recency_days": RECENCY_WINDOW_DAYS,
        },
        "care_families": families_payload(),
        "care_metrics": [_care_metric(metric_id) for metric_id in CATALOG_ORDER],
    }
