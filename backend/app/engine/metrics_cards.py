"""Build the 'supporting signals' metric cards from analytics results.

The cards and the risk header are read side by side, so they share their
thresholds rather than restating them: the recency window and the gait rule
below are the same ones the engine judged the patient by.
"""

from datetime import date, timedelta

import pandas as pd

from app.engine.deviation import (
    CURVE_SCALED,
    RECENCY_WINDOW_DAYS,
    REF_ANCHORED_CURVE,
    expected_functional,
)
from app.engine.risk import GAIT_FLAG_AFTER_DAY, GAIT_FLAG_PCT
from app.engine.types import Baseline, ConfidenceResult, DeviationResult, MetricInsight
from app.models.enums import ConfidenceLevel, MetricStatus
from app.models.enums import MetricType as M
from app.models.enums import ProcedureType

# Asymmetry at or under this is reported as improving rather than watched; the
# flag threshold above it lives in risk.py, which owns the rule.
GAIT_OK_PCT = 8.0

CARD_ORDER: list[tuple[M, str, str, bool]] = [
    # metric, display name, unit label, guarded
    (M.STEPS, "Daily steps", "steps", False),
    (M.RESTING_HR, "Resting heart rate", "bpm", False),
    (M.HRV_RMSSD, "HRV (RMSSD)", "ms", False),
    (M.SLEEP_DURATION, "Sleep duration", "h", False),
    (M.SKIN_TEMP, "Skin temperature", "°C", True),
    (M.SPO2, "Blood oxygen", "%", False),
    (M.RESPIRATORY_RATE, "Respiratory rate", "br/min", True),
    (M.WALKING_SPEED, "Walking speed", "m/s", False),
    (M.WALKING_ASYMMETRY_PCT, "Walking asymmetry", "%", True),
    # --- the in-house mobility set (engine/mobility) and the derived signals ---
    (M.STEP_LENGTH, "Step length", "m", False),
    (M.CADENCE, "Cadence", "spm", False),
    (M.DOUBLE_SUPPORT_PCT, "Double support", "%", True),
    (M.WALKING_STEADINESS, "Walking steadiness", "score", True),
    (M.STAIR_SPEED_UP, "Stair speed up", "m/s", False),
    (M.STAIR_SPEED_DOWN, "Stair speed down", "m/s", False),
    (M.SIX_MIN_WALK, "Six-minute walk", "m", False),
    (M.ROM_FLEXION, "Flexion (ROM)", "°", False),
    (M.ROM_EXTENSION, "Extension deficit (ROM)", "°", False),
    (M.ROM_ABDUCTION, "Abduction (ROM)", "°", False),
    (M.EXERCISE_SESSION, "Exercise minutes", "min", False),
    (M.ACTIVE_ENERGY, "Active energy", "kcal", False),
    (M.CALORIES, "Total calories", "kcal", False),
    (M.STRESS_INDEX, "Stress index", "score", True),
    # variant statistics: charted only when the canonical series is absent
    (M.HRV_SDNN, "HRV (SDNN)", "ms", False),
    (M.SKIN_TEMP_DELTA, "Skin temperature change", "°C", True),
]

# Where a metric comes from, for the card a patient has never produced: the
# clinician sees the whole panel and what would fill each gap.
WEARABLE = "Comes from the patient's wearable once it is connected and worn."
GUIDED_WALK = ("Measured by the guided walk in the MedPull app (an iPhone carried in a pocket "
               "also reports Apple's estimate).")
SOURCE_HINT: dict[M, str] = {
    M.STEPS: WEARABLE, M.RESTING_HR: WEARABLE, M.HRV_RMSSD: WEARABLE, M.HRV_SDNN: WEARABLE,
    M.SLEEP_DURATION: "Comes from the wearable when it is worn overnight.",
    M.SKIN_TEMP: "Comes from a wearable with a skin-temperature sensor, worn overnight.",
    M.SKIN_TEMP_DELTA: "Comes from a wearable with a skin-temperature sensor, worn overnight.",
    M.SPO2: "Comes from a wearable with a blood-oxygen sensor, worn overnight.",
    M.RESPIRATORY_RATE: "Comes from the wearable when it is worn overnight.",
    M.WALKING_SPEED: GUIDED_WALK, M.WALKING_ASYMMETRY_PCT: GUIDED_WALK, M.STEP_LENGTH: GUIDED_WALK,
    M.CADENCE: "Measured by the guided walk in the MedPull app.",
    M.DOUBLE_SUPPORT_PCT: GUIDED_WALK, M.WALKING_STEADINESS: GUIDED_WALK,
    M.STAIR_SPEED_UP: "Measured when a walk recorded in the app includes a flight of stairs "
                      "(an Apple Watch also reports its estimate).",
    M.STAIR_SPEED_DOWN: "Measured when a walk recorded in the app includes a flight of stairs "
                        "(an Apple Watch also reports its estimate).",
    M.SIX_MIN_WALK: "Measured by the six-minute walk test in the MedPull app.",
    M.ROM_FLEXION: "Measured by the range-of-motion test in the MedPull app.",
    M.ROM_EXTENSION: "Measured by the range-of-motion test in the MedPull app (knee: straighten).",
    M.ROM_ABDUCTION: "Measured by the range-of-motion test in the MedPull app (shoulder: raise sideways).",
    M.EXERCISE_SESSION: "Comes from workouts on the wearable or a guided walk in the app.",
    M.ACTIVE_ENERGY: WEARABLE, M.CALORIES: WEARABLE,
    M.STRESS_INDEX: "Derived once the wearable has reported HRV or resting heart rate on three "
                    "days in the last six weeks.",
}
# Readings the sparkline keeps: the last two weeks, or the last eight readings
# when the metric is measured less often than daily (a weekly test would
# otherwise draw one point).
MIN_SPARKLINE_POINTS = 8

# A device measures vitals nightly and the phone measures gait on every walk,
# but the six-minute walk and a joint angle are tests the patient performs
# every few days: they keep a longer window before the card calls them stale.
SLOW_RECENCY_DAYS: dict[M, int] = {
    M.SIX_MIN_WALK: 14, M.ROM_FLEXION: 10, M.ROM_EXTENSION: 10, M.ROM_ABDUCTION: 10,
    M.STAIR_SPEED_UP: 7, M.STAIR_SPEED_DOWN: 7,
}
VARIANT_OF: dict[M, M] = {M.HRV_SDNN: M.HRV_RMSSD, M.SKIN_TEMP_DELTA: M.SKIN_TEMP}
# Absolute bands (engine/mobility/stress, /stability): 50 is "at baseline",
# 75 one SD of strain; the steadiness bands mirror Apple's three levels.
STRESS_FLAG = 75.0
STRESS_WATCH = 62.5
STEADINESS_LOW = 60.0
STEADINESS_VERY_LOW = 40.0
# Double support rises for everyone after a lower-limb operation and falls
# back over months (Fary 2023: week 24 after TKA), so like asymmetry it reads
# on absolute bands rather than against the pre-op norm. Healthy walking
# sits near 20 %; Apple's typical range is 20-40 %.
DOUBLE_SUPPORT_OK_PCT = 28.0
DOUBLE_SUPPORT_FLAG_PCT = 40.0
# Baseline days behind a stress reading before its band may flag.
STRESS_FIRM_DAYS = 7
AUTONOMIC_INPUTS = (M.HRV_RMSSD, M.HRV_SDNN, M.RESTING_HR, M.RESPIRATORY_RATE)


def _autonomic_baseline_days(series: dict[str, pd.Series], day: int, window: int = 42) -> int:
    """The most days any autonomic input reported in the window before `day`
    — how much history the stress index's baseline actually rests on."""
    best = 0
    for metric in AUTONOMIC_INPUTS:
        s = series.get(str(metric))
        if s is None:
            continue
        best = max(best, int(((s.index < day) & (s.index >= day - window)).sum()))
    return best

STATUS_TEXT = {
    ("up", True): "Rising vs baseline",
    ("down", True): "Falling vs baseline",
}

NEXT_STEPS: dict[M, str] = {
    M.RESTING_HR: "Consider contacting the patient about how they feel today.",
    M.SKIN_TEMP: "Ask about fever, chills, and the incision site.",
    M.HRV_RMSSD: "Review alongside heart rate and temperature.",
    M.STEPS: "Ask what is limiting activity — pain, fatigue, or fear of movement.",
    M.WALKING_SPEED: "Review activity progression with PT.",
    M.SLEEP_DURATION: "Ask about pain at night and sleeping position.",
    M.SPO2: "Ask about breathing comfort; verify device fit.",
    M.RESPIRATORY_RATE: "Review alongside temperature and heart rate.",
    M.WALKING_ASYMMETRY_PCT: "Consider a gait review with PT.",
    M.STEP_LENGTH: "Review stride progression with PT.",
    M.CADENCE: "Review activity progression with PT.",
    M.DOUBLE_SUPPORT_PCT: "Ask about confidence on the operated leg; consider a gait review.",
    M.WALKING_STEADINESS: "Ask about balance and near-falls; review assistive-device use.",
    M.STAIR_SPEED_UP: "Ask about stairs at home; review stair training with PT.",
    M.STAIR_SPEED_DOWN: "Ask about descending stairs; review eccentric control with PT.",
    M.SIX_MIN_WALK: "Review endurance goals with PT.",
    M.ROM_FLEXION: "Review the home exercise programme; consider a PT visit for motion.",
    M.ROM_EXTENSION: "Check for a flexion contracture; review extension exercises.",
    M.ROM_ABDUCTION: "Review the home exercise programme for the shoulder.",
    M.EXERCISE_SESSION: "Ask what is limiting exercise — pain, fatigue, or confidence.",
    M.ACTIVE_ENERGY: "Ask what is limiting activity — pain, fatigue, or fear of movement.",
    M.STRESS_INDEX: "Review alongside sleep, pain and the vitals; ask how they are coping.",
    M.HRV_SDNN: "Review alongside heart rate and temperature.",
    M.SKIN_TEMP_DELTA: "Ask about fever, chills, and the incision site.",
}


def _stale(dev: DeviationResult, postop_day: int, recency: int) -> bool:
    return dev.last_day is None or postop_day - dev.last_day > recency


def _fmt(value: float, metric: M) -> str:
    if metric in (M.STEPS, M.ACTIVE_ENERGY, M.SIX_MIN_WALK):
        return f"{value:,.0f}"
    if metric in (M.CADENCE, M.WALKING_STEADINESS, M.STRESS_INDEX, M.EXERCISE_SESSION):
        return f"{value:.0f}"
    if metric in (M.WALKING_SPEED, M.STEP_LENGTH, M.STAIR_SPEED_UP, M.STAIR_SPEED_DOWN):
        return f"{value:.2f}"
    return f"{value:.1f}"


def build_cards(
    series: dict[str, pd.Series],
    baselines: dict[str, Baseline],
    deviations: dict[str, DeviationResult],
    confidence: ConfidenceResult,
    procedure: ProcedureType,
    postop_day: int,
    surgery_date: date,
) -> list[MetricInsight]:
    cards: list[MetricInsight] = []
    variants_present = {str(v) for v in VARIANT_OF if str(v) in series}
    for metric, name, unit, guarded in CARD_ORDER:
        key = str(metric)
        s = series.get(key)
        canonical = VARIANT_OF.get(metric)
        if canonical is not None and (s is None or str(canonical) in series):
            continue  # a variant is charted only in place of an absent canonical
        if s is None and any(VARIANT_OF[v] is metric for v in VARIANT_OF if str(v) in variants_present):
            continue  # the device ships the variant statistic instead
        if s is None:
            # Never measured for this patient: the card stays on the panel so
            # the clinician sees the whole set and what would fill the gap.
            cards.append(MetricInsight(
                metric_key=key, name=name, status=MetricStatus.NODATA,
                status_text="Not measured yet",
                finding=SOURCE_HINT.get(metric, WEARABLE),
                confidence=ConfidenceLevel.LOW,
                coverage_text=f"0 of {confidence.window_days or 7} days of data",
                next_step=None, guarded=guarded, unit=unit, series=[], baseline_mean=None,
            ))
            continue
        post = s[s.index >= 0]
        baseline = baselines.get(key)
        dev = deviations.get(key)
        recency = SLOW_RECENCY_DAYS.get(metric, RECENCY_WINDOW_DAYS)

        has_recent = len(post[post.index >= postop_day - recency]) > 0

        anchored = dev is not None and dev.reference == REF_ANCHORED_CURVE
        if not has_recent or baseline is None or dev is None or _stale(dev, postop_day, recency):
            status = MetricStatus.NODATA
            status_text, finding = _no_reading_text(
                metric, post if len(post) else s, baseline, has_recent, procedure, postop_day,
                building=(has_recent and (baseline is None or dev is None)),
                surgery_date=surgery_date,
            )
            next_step = None
        elif dev.flagged:
            status = MetricStatus.FLAG
            # An anchored comparison never claims a level, only a pace, so the
            # card says which of the two it is measuring.
            status_text = (
                "Behind its post-op pace"
                if anchored
                else STATUS_TEXT.get((dev.direction, True), "Outside expected range")
            )
            finding = _finding(metric, post, baseline, procedure)
            next_step = NEXT_STEPS.get(metric)
        elif dev.drifting or abs(dev.latest_z) > 1.2:
            status = MetricStatus.WATCH
            status_text = "Drifting from baseline" if dev.drifting else "Nearing expected limits"
            finding = _finding(metric, post, baseline, procedure)
            next_step = NEXT_STEPS.get(metric)
        else:
            status = MetricStatus.OK
            status_text = "Stable"
            finding = _finding(metric, post, baseline, procedure)
            next_step = None

        # special-case gait asymmetry: absolute threshold, not baseline z
        if metric == M.WALKING_ASYMMETRY_PCT and has_recent and len(post) > 0:
            latest = float(post.iloc[-1])
            if postop_day > GAIT_FLAG_AFTER_DAY and latest > GAIT_FLAG_PCT:
                status = MetricStatus.FLAG
                status_text = "Favoring one side"
                next_step = NEXT_STEPS[metric]
            elif status is not MetricStatus.NODATA:
                status = MetricStatus.OK if latest <= GAIT_OK_PCT else MetricStatus.WATCH
                status_text = "Improving" if latest <= GAIT_OK_PCT else "Still elevated"
        # The two 0-100 indices read on absolute bands, which are what their
        # construction promises (engine/mobility/stress, /stability), not on
        # a control chart over the index itself.
        # The band-read cards judge any CURRENT reading on their absolute
        # bands, whether or not a control-chart baseline exists yet.
        if metric == M.STRESS_INDEX and has_recent and len(post) > 0:
            latest = float(post.iloc[-1])
            if latest >= STRESS_FLAG:
                status, status_text, next_step = MetricStatus.FLAG, "Elevated strain", NEXT_STEPS[metric]
            elif latest >= STRESS_WATCH:
                status, status_text, next_step = MetricStatus.WATCH, "Above own baseline", NEXT_STEPS[metric]
            else:
                status, status_text, next_step = MetricStatus.OK, "Near own baseline", None
            finding = (f"Latest {latest:.0f} on a 0-100 scale where 50 is the patient's own "
                       "baseline and 75 is one standard deviation of strain.")
            n_days = _autonomic_baseline_days(series, int(post.index[-1]))
            if n_days < STRESS_FIRM_DAYS:
                # Three noisy sync days can put one reading two SD out; until a
                # week of baseline exists the card says so and never flags.
                if status is MetricStatus.FLAG:
                    status = MetricStatus.WATCH
                status_text = "Early estimate"
                finding += (f" Estimated from {n_days} baseline day{'s' if n_days != 1 else ''}; "
                            f"the band firms up after {STRESS_FIRM_DAYS}.")
        if metric == M.WALKING_STEADINESS and has_recent and len(post) > 0:
            latest = float(post.iloc[-1])
            if latest < STEADINESS_VERY_LOW:
                status, status_text, next_step = MetricStatus.FLAG, "Very low steadiness", NEXT_STEPS[metric]
            elif latest < STEADINESS_LOW:
                status, status_text, next_step = MetricStatus.WATCH, "Low steadiness", NEXT_STEPS[metric]
            else:
                status, status_text, next_step = MetricStatus.OK, "Steady", None
            band = ("OK" if latest >= STEADINESS_LOW else "Low" if latest >= STEADINESS_VERY_LOW
                    else "Very low")
            finding = f"Latest {latest:.0f} of 100 ({band} band; OK is 60 and above)"
            finding += f", from a baseline of {baseline.mean:.0f}." if baseline else "."
        if metric == M.DOUBLE_SUPPORT_PCT and has_recent and len(post) > 0:
            latest = float(post.iloc[-1])
            if postop_day > GAIT_FLAG_AFTER_DAY and latest > DOUBLE_SUPPORT_FLAG_PCT:
                status, status_text, next_step = MetricStatus.FLAG, "Both feet down most of the time", NEXT_STEPS[metric]
            elif latest > DOUBLE_SUPPORT_OK_PCT:
                status, status_text, next_step = MetricStatus.WATCH, "Still elevated", NEXT_STEPS[metric]
            else:
                status, status_text, next_step = MetricStatus.OK, "Improving", None
            finding = (f"Latest {latest:.1f}% of the stride with both feet on the ground "
                       "(healthy walking is near 20%"
                       + (f"; baseline {baseline.mean:.1f}%)." if baseline else ")."))

        window = confidence.window_days or 1
        covered = min(
            window, len(post[post.index > postop_day - window])
        )
        last14 = post[post.index > postop_day - 14]
        if len(last14) < MIN_SPARKLINE_POINTS:
            last14 = (post if len(post) else s).tail(MIN_SPARKLINE_POINTS)
        cards.append(
            MetricInsight(
                metric_key=key,
                name=name,
                status=status,
                status_text=status_text,
                finding=finding,
                confidence=confidence.level if status is not MetricStatus.NODATA else ConfidenceLevel.LOW,
                coverage_text=f"{covered} of {window} days of data",
                next_step=next_step,
                guarded=guarded,
                unit=unit,
                series=[
                    {
                        "date": (surgery_date + timedelta(days=int(d))).isoformat(),
                        "value": round(float(v), 2),
                    }
                    for d, v in last14.items()
                ],
                baseline_mean=_reference(metric, baselines.get(key), procedure, postop_day),
            )
        )
    return cards


def _no_reading_text(
    metric: M,
    post: pd.Series,
    baseline: Baseline | None,
    has_recent: bool,
    procedure: ProcedureType,
    postop_day: int,
    building: bool = False,
    surgery_date: date | None = None,
) -> tuple[str, str]:
    """Why this card carries no verdict — the two reasons look identical on
    screen otherwise, and 'No recent data' is a lie for a patient whose device
    reports faithfully but who cannot be measured against anything."""
    if not has_recent and len(post) > 0:
        # The metric has history (post-op, or only pre-op — the caller hands
        # over the whole series then) but nothing current: say what the last
        # reading was and when, instead of hiding the data that exists.
        last_day = int(post.index[-1])
        ago = postop_day - last_day
        when = (
            (surgery_date + timedelta(days=last_day)).strftime("%b %-d") if surgery_date
            else f"post-op day {last_day}"
        )
        latest = _fmt(float(post.iloc[-1]), metric)
        return (
            "No recent data",
            f"Last reading {latest} on {when}, {ago} days ago. Nothing newer has arrived "
            "from the patient's device.",
        )
    if building and len(post) > 0:
        # Reporting, but not yet enough readings for a reference: the
        # six-minute walk or a joint angle two tests in.
        latest = _fmt(float(post.iloc[-1]), metric)
        return (
            "Building baseline",
            f"Latest {latest}; a comparison needs three readings from post-op day 2 on.",
        )
    if (
        has_recent
        and baseline is not None
        and metric in CURVE_SCALED
        and expected_functional(baseline, procedure, postop_day) is None
    ):
        latest = _fmt(float(post.iloc[-1]), metric)
        return (
            "No comparison available",
            f"Latest {latest}, but this metric has no baseline days the "
            "expected curve can be anchored to.",
        )
    return "No recent data", "Not enough recent data from the patient's device."


def _reference(
    metric: M, baseline: Baseline | None, procedure: ProcedureType, postop_day: int
) -> float | None:
    """Dashed reference for the sparkline: expected-today for functional
    metrics, personal baseline for vitals.

    Functional metrics read the one shared definition of "expected", so the
    line under the chart is the number the flag was raised against — including
    for a patient with no pre-op history, whose line is the curve's shape
    projected from their own early post-op level rather than a fraction of a
    pre-op norm they never recorded."""
    if metric == M.STRESS_INDEX:
        return 50.0
    if baseline is None:
        return None
    if metric in CURVE_SCALED:
        expected = expected_functional(baseline, procedure, postop_day)
        return None if expected is None else round(expected, 2)
    if metric == M.WALKING_ASYMMETRY_PCT:
        return None
    return round(baseline.mean, 2)


def _finding(metric: M, post: pd.Series, baseline: Baseline, procedure: ProcedureType) -> str:
    latest = float(post.iloc[-1])
    latest_str = _fmt(latest, metric)
    if metric in CURVE_SCALED:
        day = int(post.index[-1])
        expected = expected_functional(baseline, procedure, day)
        if expected is None:
            return f"Latest {latest_str}."
        pct = (latest / expected - 1.0) * 100 if expected > 0 else 0.0
        rel = f"{abs(pct):.0f}% {'below' if pct < 0 else 'above'} expected for day {day}"
        if baseline.is_preop:
            return f"Latest {latest_str} — {rel}."
        # Say out loud that the expectation is a projection from this
        # patient's own early post-op level: it is a claim about pace, and
        # reading it as a claim about capacity would overstate it.
        anchor_days = [d for d in baseline.window_days if d >= 0]
        span = (
            f"post-op day{'s' if len(anchor_days) > 1 else ''} "
            f"{min(anchor_days)}-{max(anchor_days)}"
            if anchor_days
            else "the early post-op days"
        )
        return (
            f"Latest {latest_str} — {rel}, projecting the recovery curve from "
            f"their own {span} level. No pre-op history, so this tracks pace, "
            "not capacity."
        )
    if metric == M.WALKING_ASYMMETRY_PCT:
        return f"Latest {latest_str}% of walking time favoring one side."
    delta = latest - baseline.mean
    sign = "+" if delta >= 0 else "−"
    return f"Latest {latest_str} vs baseline {_fmt(baseline.mean, metric)} ({sign}{_fmt(abs(delta), metric)})."
