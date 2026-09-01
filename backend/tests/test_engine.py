"""Unit tests for the deterministic analytics, on synthetic series."""

from datetime import date, datetime

import numpy as np
import pandas as pd

from app.engine.baseline import compute_baseline
from app.engine.composite import composite_index
from app.engine.confidence import coverage
from app.engine.curves import curve_mid, expected_curve
from app.engine.deviation import analyze_metric, ewma_cusum
from app.engine.metrics_cards import build_cards
from app.engine.risk import score_risk
from app.engine.trajectory import compare, functional_index, is_anchored
from app.engine.types import AdherenceResult, Baseline, DeviationResult
from app.models.enums import ConfidenceLevel, MetricStatus
from app.models.enums import MetricType as M
from app.models.enums import ProcedureType, RiskLevel, TrajectoryState

SURGERY_DATE = date(2026, 1, 1)
NO_ADHERENCE = AdherenceResult(rate=0.0, verified=0, assigned=0, self_attested=0, days=[])


def _series(pre: list[float], post: list[float]) -> pd.Series:
    index = list(range(-len(pre), 0)) + list(range(len(post)))
    return pd.Series(pre + post, index=index, dtype=float)


def _flat(days: list[int], value: float) -> pd.Series:
    return pd.Series([value] * len(days), index=days, dtype=float)


def _healthy_series(postop_day: int, procedure: ProcedureType) -> dict[str, pd.Series]:
    """All six key metrics reporting every day since pre-op, steps exactly on
    the expected curve — a patient the engine can see completely and has
    nothing to say about, so a single perturbed metric is the only variable."""
    days = list(range(-10, postop_day + 1))
    series = {
        str(M.RESTING_HR): _flat(days, 62.0),
        str(M.HRV_RMSSD): _flat(days, 45.0),
        str(M.SLEEP_DURATION): _flat(days, 7.2),
        str(M.SKIN_TEMP): _flat(days, 36.5),
        str(M.SPO2): _flat(days, 97.5),
    }
    series[str(M.STEPS)] = pd.Series(
        [5000.0 if d < 0 else 5000.0 * float(curve_mid(procedure, d)) for d in days],
        index=days,
        dtype=float,
    )
    return series


def _analyze(
    series: dict[str, pd.Series], procedure: ProcedureType
) -> tuple[dict[str, Baseline], dict[str, DeviationResult]]:
    baselines: dict[str, Baseline] = {}
    deviations: dict[str, DeviationResult] = {}
    for key, s in series.items():
        result = analyze_metric(M(key), s, procedure)
        if result is not None:
            baselines[key], deviations[key] = result
    return baselines, deviations


def test_ewma_flags_rhr_ramp():
    rng = np.random.default_rng(1)
    pre = list(62 + rng.normal(0, 1.0, 10))
    post = list(62 + rng.normal(0, 1.0, 6)) + [64.5, 67.0, 70.0]
    baseline, dev = analyze_metric(M.RESTING_HR, _series(pre, post), ProcedureType.TKA)
    assert dev.flagged
    assert dev.direction == "up"


def test_ewma_ignores_stable_vitals():
    rng = np.random.default_rng(2)
    pre = list(62 + rng.normal(0, 1.0, 10))
    post = list(62 + rng.normal(0, 1.0, 12))
    _, dev = analyze_metric(M.RESTING_HR, _series(pre, post), ProcedureType.TKA)
    assert not dev.flagged
    assert not dev.drifting


def test_favorable_direction_never_flags():
    # steps well ABOVE the expected curve: adverse only when below
    pre = [8000.0] * 10
    curve = expected_curve(ProcedureType.MENISCUS, np.arange(0, 12))
    post = [8000 * point["mid"] * 1.3 for point in curve]
    _, dev = analyze_metric(M.STEPS, _series(pre, post), ProcedureType.MENISCUS)
    assert not dev.flagged


def test_cusum_catches_slow_drift():
    z = pd.Series([-(0.4 + 0.35 * i) for i in range(9)], index=range(2, 11))
    result = ewma_cusum(M.STEPS, z)
    assert result.drifting


def test_expected_curve_monotonic_and_bounded():
    for procedure in ProcedureType:
        curve = expected_curve(procedure, np.arange(0, 60))
        mids = [point["mid"] for point in curve]
        assert all(b >= a for a, b in zip(mids, mids[1:]))
        assert 0.0 < mids[0] < 1.0 and mids[-1] <= 1.0


def test_trajectory_behind_for_sustained_deficit():
    days = np.arange(0, 15)
    curve = expected_curve(ProcedureType.THA, days)
    index = pd.Series([point["mid"] * 0.82 for point in curve], index=days)
    result = compare(index, ProcedureType.THA, 14)
    assert result.state == TrajectoryState.BEHIND
    assert result.pct is not None and result.pct <= -12


def test_trajectory_unknown_with_thin_history():
    index = pd.Series([0.3, 0.32], index=[0, 1])
    result = compare(index, ProcedureType.THA, 1)
    assert result.state == TrajectoryState.UNKNOWN


def test_change_point_on_residual_not_normal_recovery():
    days = np.arange(0, 40)
    curve = expected_curve(ProcedureType.TKA, days)
    on_track = pd.Series([point["mid"] * 1.02 for point in curve], index=days)
    assert compare(on_track, ProcedureType.TKA, 39).change_point_day is None

    # deficit appearing at day 25
    values = [point["mid"] * (1.0 if point["day"] < 25 else 0.72) for point in curve]
    shifted = pd.Series(values, index=days)
    change_day = compare(shifted, ProcedureType.TKA, 39).change_point_day
    assert change_day is not None and 23 <= change_day <= 28


def _dev(metric: M, raw_z: float, last_day: int = 10) -> DeviationResult:
    return DeviationResult(
        metric_type=str(metric), flagged=False, direction="up" if raw_z > 0 else "down",
        latest_z=raw_z, raw_z=raw_z, consecutive_out=0, drifting=False, last_day=last_day,
    )


def test_composite_high_for_coupled_deterioration():
    deviations = {
        str(M.RESTING_HR): _dev(M.RESTING_HR, 4.0),
        str(M.SKIN_TEMP): _dev(M.SKIN_TEMP, 4.0),
        str(M.HRV_RMSSD): _dev(M.HRV_RMSSD, -3.0),
        str(M.STEPS): _dev(M.STEPS, -3.5),
        str(M.RESPIRATORY_RATE): _dev(M.RESPIRATORY_RATE, 0.5),
    }
    result = composite_index(deviations)
    assert result.level == "high"
    assert result.drivers[0]["metric_type"] in (str(M.RESTING_HR), str(M.SKIN_TEMP))


def test_composite_normal_for_noise():
    deviations = {
        str(M.RESTING_HR): _dev(M.RESTING_HR, 0.8),
        str(M.SKIN_TEMP): _dev(M.SKIN_TEMP, -0.4),
        str(M.HRV_RMSSD): _dev(M.HRV_RMSSD, 0.6),
    }
    assert composite_index(deviations).level == "normal"


def test_baseline_falls_back_without_preop_data():
    series = pd.Series([70.0, 68.0, 62.0, 63.0, 61.5, 62.5], index=[0, 1, 2, 3, 4, 5])
    baseline = compute_baseline(str(M.RESTING_HR), series)
    assert baseline is not None
    assert "no pre-op" in baseline.window
    assert baseline.is_preop is False
    # the acute perturbation on days 0-1 must not anchor the baseline
    assert baseline.mean < 65


def test_baseline_window_names_the_days_it_actually_used():
    # device connected at day 20: the label must not claim days 2-4
    series = pd.Series([4100.0, 4300.0, 4250.0, 4400.0], index=[20, 21, 22, 23])
    baseline = compute_baseline(str(M.STEPS), series)
    assert baseline is not None
    assert baseline.window == "post-op days 20-22 (no pre-op data)"
    assert baseline.is_preop is False


def test_preop_baseline_is_marked_as_one():
    baseline = compute_baseline(str(M.RESTING_HR), _series([62.0] * 10, [63.0] * 4))
    assert baseline is not None
    assert baseline.is_preop is True
    assert baseline.window == "pre-op days -10..-1"


def test_drift_alarm_requires_an_adverse_direction():
    # the same sliding series: falling steps is a finding, falling gait
    # asymmetry is a patient walking more evenly again
    z = pd.Series([-(0.4 + 0.35 * i) for i in range(9)], index=range(2, 11))
    assert ewma_cusum(M.STEPS, z).drifting
    assert not ewma_cusum(M.WALKING_ASYMMETRY_PCT, z).drifting


def _score(series: dict[str, pd.Series], procedure: ProcedureType, postop_day: int):
    """The per-patient path pipeline.run_patient runs, minus the database.

    Gait is derived from the series here exactly as pipeline.run_patient
    derives it — value *and* day. Handing score_risk a bare number would let a
    test assert a tier the real pipeline could never produce.
    """
    baselines, deviations = _analyze(series, procedure)
    confidence = coverage(series, postop_day)
    composite = composite_index(deviations, postop_day=postop_day)
    trajectory = compare(
        functional_index(series, baselines, procedure), procedure, postop_day,
        anchored=is_anchored(baselines),
    )
    gait = series.get(str(M.WALKING_ASYMMETRY_PCT))
    gait_postop = gait[gait.index >= 0] if gait is not None else None
    gait_latest = float(gait_postop.iloc[-1]) if gait_postop is not None and len(gait_postop) else None
    gait_day = int(gait_postop.index[-1]) if gait_postop is not None and len(gait_postop) else None
    risk = score_risk(
        postop_day, deviations, trajectory, composite, confidence, NO_ADHERENCE,
        gait_latest, gait_day,
    )
    cards = build_cards(
        series, baselines, deviations, confidence, procedure, postop_day, SURGERY_DATE
    )
    return deviations, confidence, composite, risk, {c.metric_key: c for c in cards}


def _vital_ramp(last_day: int, base: float, step: float, from_day: int) -> pd.Series:
    days = list(range(-10, last_day + 1))
    return pd.Series(
        [base if d < from_day else base + step * (d - from_day + 1) for d in days],
        index=days,
        dtype=float,
    )


def test_stale_vitals_cannot_flag_or_raise_the_tier():
    postop_day = 14
    series = _healthy_series(postop_day, ProcedureType.TKA)
    # RHR and skin temp ramp hard through day 6, then the sensor goes dark
    series[str(M.RESTING_HR)] = _vital_ramp(6, 62.0, 4.0, 4)
    series[str(M.SKIN_TEMP)] = _vital_ramp(6, 36.5, 0.3, 4)

    deviations, confidence, composite, risk, cards = _score(
        series, ProcedureType.TKA, postop_day
    )

    # the ramp itself is real and still detected — it is simply eight days old
    assert deviations[str(M.RESTING_HR)].flagged
    assert deviations[str(M.RESTING_HR)].last_day == 6

    codes = {r.code for r in risk.reasons}
    assert risk.level is not RiskLevel.HIGH
    assert not {"RHR_RISING", "TEMP_RISING", "COMPOSITE_HIGH"} & codes
    assert composite.level == "normal"
    # the gap is reported rather than passed over in silence
    assert "LOW_COVERAGE" in codes
    assert confidence.level is not ConfidenceLevel.HIGH
    assert set(confidence.dark_metrics) == {str(M.RESTING_HR), str(M.SKIN_TEMP)}
    # header and cards now tell the same story
    assert cards[str(M.RESTING_HR)].status is MetricStatus.NODATA
    assert cards[str(M.SKIN_TEMP)].status is MetricStatus.NODATA


def test_the_same_ramp_still_pages_when_it_is_current():
    postop_day = 14
    series = _healthy_series(postop_day, ProcedureType.TKA)
    series[str(M.RESTING_HR)] = _vital_ramp(postop_day, 62.0, 4.0, 12)
    series[str(M.SKIN_TEMP)] = _vital_ramp(postop_day, 36.5, 0.3, 12)

    _, confidence, composite, risk, cards = _score(series, ProcedureType.TKA, postop_day)

    assert risk.level == RiskLevel.HIGH
    assert {"RHR_RISING", "TEMP_RISING"} <= {r.code for r in risk.reasons}
    assert composite.index > 0  # the identical stale readings above score 0.0
    assert confidence.level == ConfidenceLevel.HIGH
    assert cards[str(M.RESTING_HR)].status is MetricStatus.FLAG


def test_composite_drops_a_signal_that_stopped_reporting():
    deviations = {
        str(M.RESTING_HR): _dev(M.RESTING_HR, 4.0, last_day=6),
        str(M.SKIN_TEMP): _dev(M.SKIN_TEMP, 4.0, last_day=6),
        str(M.STEPS): _dev(M.STEPS, -0.2, last_day=14),
    }
    assert composite_index(deviations, postop_day=6).level == "high"
    assert composite_index(deviations, postop_day=14).level == "normal"
    # with no day supplied, the latest reporting day stands in for today
    assert composite_index(deviations).level == "normal"


def test_confidence_counts_which_metrics_are_dark_not_only_the_days():
    postop_day = 14
    series = _healthy_series(postop_day, ProcedureType.TKA)
    full = coverage(series, postop_day)
    assert full.score == 1.0
    assert full.level == ConfidenceLevel.HIGH
    assert full.dark_metrics == []

    gone = {str(M.RESTING_HR), str(M.SKIN_TEMP), str(M.HRV_RMSSD)}
    for key in gone:
        series[key] = series[key][series[key].index <= 6]
    dark = coverage(series, postop_day)

    # the surviving three metrics still clear MIN_METRICS_PER_DAY every day, so
    # the day count is untouched: only the panel shrank
    assert dark.days_with_data == full.days_with_data
    assert dark.score == 0.5
    assert dark.level == ConfidenceLevel.MEDIUM
    assert set(dark.dark_metrics) == gone


def _steps_only(procedure: ProcedureType, postop_day: int, plateau_at: int | None):
    """Steps on the expected curve from a device connected the day of surgery,
    optionally frozen at plateau_at — a collapse that never recovers."""
    days = list(range(0, postop_day + 1))
    values = [
        5000.0 * float(curve_mid(procedure, d if plateau_at is None else min(d, plateau_at)))
        for d in days
    ]
    return {str(M.STEPS): pd.Series(values, index=days, dtype=float)}


def _trajectory(series, procedure, postop_day):
    baselines, deviations = _analyze(series, procedure)
    result = compare(
        functional_index(series, baselines, procedure), procedure, postop_day,
        anchored=is_anchored(baselines),
    )
    return baselines, deviations, result


def test_no_preop_baseline_never_reads_an_on_curve_recovery_as_ahead():
    """Anchored on post-op days 2-4, this exactly-on-curve patient read
    AHEAD +171.6: the anchor sits at 36% of pre-op capacity and was divided
    into the curve as though it were 100%."""
    postop_day = 12
    series = _steps_only(ProcedureType.TKA, postop_day, plateau_at=None)
    baselines, _, result = _trajectory(series, ProcedureType.TKA, postop_day)
    assert baselines[str(M.STEPS)].is_preop is False
    assert result.anchored is True
    assert result.state == TrajectoryState.ON_TRACK
    assert abs(result.pct) < 1.0


def test_an_anchored_index_may_report_behind_but_never_ahead():
    """The anchored comparison rests on the patient's early post-op level
    being normal — enough to raise a concern, never enough to reassure."""
    postop_day = 12
    fast = {
        str(M.STEPS): pd.Series(
            [5000.0 * float(curve_mid(ProcedureType.TKA, d)) * (1.0 if d < 5 else 1.6)
             for d in range(0, postop_day + 1)],
            index=list(range(0, postop_day + 1)), dtype=float,
        )
    }
    _, _, result = _trajectory(fast, ProcedureType.TKA, postop_day)
    assert result.pct > 10.0  # would have been AHEAD on a pre-op index
    assert result.state == TrajectoryState.ON_TRACK


def test_no_preop_baseline_still_flags_a_collapse():
    """The collapse used to score +11.98 in the favorable direction, where
    steps can never flag; leaving it unscored instead made it invisible — the
    patient read LOW "tracking as expected", identical to a patient recovering
    exactly on curve. The curve's SHAPE needs no pre-op norm, so it is scored
    against that."""
    postop_day = 12
    series = _steps_only(ProcedureType.TKA, postop_day, plateau_at=4)
    baselines, deviations, result = _trajectory(series, ProcedureType.TKA, postop_day)
    dev = deviations[str(M.STEPS)]
    assert dev.reference == "anchored_curve"
    assert dev.raw_z < -1.0
    assert dev.last_day == postop_day
    assert dev.direction == "down"
    assert result.state == TrajectoryState.BEHIND

    card = build_cards(
        series, baselines, deviations, coverage(series, postop_day),
        ProcedureType.TKA, postop_day, SURGERY_DATE,
    )[0]
    assert card.status in (MetricStatus.FLAG, MetricStatus.WATCH)
    # the dashed line is the curve projected from the anchor, never a raw
    # fraction of an acute-phase level
    assert card.baseline_mean is not None
    assert card.baseline_mean > baselines[str(M.STEPS)].mean
    assert "not capacity" in card.finding


def test_a_collapse_and_an_on_curve_recovery_are_not_the_same_patient():
    """The engine's whole job. Both patients lack a pre-op norm; only one of
    them has stopped recovering, and the tier has to say so."""
    postop_day = 12
    healthy = _healthy_series(postop_day, ProcedureType.TKA)
    collapsed = dict(healthy)
    collapsed[str(M.STEPS)] = pd.Series(
        [5000.0 * float(curve_mid(ProcedureType.TKA, min(d, 4))) if d <= 3 else 330.0
         for d in range(0, postop_day + 1)],
        index=list(range(0, postop_day + 1)), dtype=float,
    )
    on_curve = dict(healthy)
    on_curve[str(M.STEPS)] = pd.Series(
        [5000.0 * float(curve_mid(ProcedureType.TKA, d)) for d in range(0, postop_day + 1)],
        index=list(range(0, postop_day + 1)), dtype=float,
    )
    # strip the pre-op history from both so neither has a pre-op norm
    for bundle in (collapsed, on_curve):
        for key, values in list(bundle.items()):
            if key != str(M.STEPS):
                bundle[key] = values[values.index >= 0]

    _, _, _, good, good_cards = _score(on_curve, ProcedureType.TKA, postop_day)
    _, _, _, bad, bad_cards = _score(collapsed, ProcedureType.TKA, postop_day)
    assert good.level is RiskLevel.LOW
    assert bad.level is RiskLevel.MEDIUM
    assert {r.code for r in bad.reasons} & {"STEPS_FALLING", "TRAJECTORY_BEHIND"}
    assert good_cards["steps"].status is MetricStatus.OK
    assert bad_cards["steps"].status is MetricStatus.FLAG


def test_the_same_collapse_flags_when_a_preop_baseline_exists():
    postop_day = 12
    post = [
        5000.0 * float(curve_mid(ProcedureType.TKA, min(d, 4)))
        for d in range(0, postop_day + 1)
    ]
    _, dev = analyze_metric(M.STEPS, _series([5000.0] * 10, post), ProcedureType.TKA)
    assert dev.flagged
    assert dev.direction == "down"


def test_gait_threshold_is_shared_by_the_card_and_the_tier():
    postop_day = 12
    days = list(range(-10, postop_day + 1))

    for latest, flagged in ((10.5, True), (9.5, False)):
        series = _healthy_series(postop_day, ProcedureType.TKA)
        series[str(M.WALKING_ASYMMETRY_PCT)] = pd.Series(
            [4.0 if d < 0 else latest for d in days], index=days, dtype=float
        )
        _, _, _, risk, cards = _score(series, ProcedureType.TKA, postop_day)
        card = cards[str(M.WALKING_ASYMMETRY_PCT)]
        assert ("GAIT_ASYMMETRY_HIGH" in {r.code for r in risk.reasons}) is flagged
        assert (card.status is MetricStatus.FLAG) is flagged


def test_webhook_unknown_patient_rejected_without_orphans(client, db):
    from sqlalchemy import func, select

    from app.models import Observation

    before = db.scalar(select(func.count(Observation.id)))
    response = client.post(
        "/api/webhooks/wearables/mock",
        json={
            "patient_id": "ghost",
            "provider": "fitbit",
            "records": [
                {"metric_type": "steps", "date": "2030-06-01", "value": 5000.0, "unit": "count"}
            ],
        },
    )
    assert response.status_code == 422
    after = db.scalar(select(func.count(Observation.id)))
    assert after == before  # nothing committed for the unknown patient


def test_golden_tiers(db):
    from app.engine.pipeline import latest_assessment

    expected = {
        "marcus": RiskLevel.HIGH,
        "priya": RiskLevel.MISSING_DATA,
        "linda": RiskLevel.MEDIUM,
        "robert": RiskLevel.MEDIUM,
        "sofia": RiskLevel.MEDIUM,
        "aisha": RiskLevel.MEDIUM,
        "grace": RiskLevel.LOW,
        "david": RiskLevel.LOW,
        "james": RiskLevel.LOW,
        "elena": RiskLevel.LOW,
    }
    for patient_id, tier in expected.items():
        assessment = latest_assessment(db, patient_id)
        assert assessment is not None, patient_id
        assert assessment.risk_level == tier, (
            f"{patient_id}: got {assessment.risk_level}, want {tier}"
        )


def test_marcus_reasons_tell_the_story(db):
    from app.engine.pipeline import latest_assessment

    codes = {r["code"] for r in latest_assessment(db, "marcus").reasons}
    assert {"RHR_RISING", "TEMP_RISING", "COMPOSITE_HIGH"} <= codes


def test_stale_gait_cannot_flag_even_with_no_baseline_to_go_stale():
    """The gait rule is the only one fed a bare number instead of a
    DeviationResult, so it is the only one that can miss the engine-wide
    recency window.

    Two readings on days 3-4 are too few for a baseline, so walking asymmetry
    never gets a DeviationResult at all — which means it appears in neither
    `deviations` nor `stale`, and a `not in stale` check waves it straight
    through. Twenty-six days later that limp is not news, and the pipeline
    hands the rule the reading's own day so it can say so.
    """
    postop_day = 30
    series = _healthy_series(postop_day, ProcedureType.TKA)
    series[str(M.WALKING_ASYMMETRY_PCT)] = pd.Series(
        [22.0, 22.0], index=[3, 4], dtype=float
    )

    _, deviations_and_more = None, _score(series, ProcedureType.TKA, postop_day)
    deviations, _, _, risk, _ = deviations_and_more

    assert str(M.WALKING_ASYMMETRY_PCT) not in deviations, (
        "two readings should not produce a baseline — the premise of this test"
    )
    assert "GAIT_ASYMMETRY_HIGH" not in {r.code for r in risk.reasons}

    # Same value, still reporting today: the gate is recency, not suppression.
    fresh = _healthy_series(postop_day, ProcedureType.TKA)
    fresh[str(M.WALKING_ASYMMETRY_PCT)] = pd.Series(
        [4.0 if d < 0 else 22.0 for d in range(-10, postop_day + 1)],
        index=list(range(-10, postop_day + 1)),
        dtype=float,
    )
    _, _, _, fresh_risk, _ = _score(fresh, ProcedureType.TKA, postop_day)
    assert "GAIT_ASYMMETRY_HIGH" in {r.code for r in fresh_risk.reasons}


def test_composite_uses_the_calendar_day_the_pipeline_knows():
    """pipeline.run_patient knows today's post-op day; composite_index must be
    told it. Left to infer a reference day from the newest reading present, a
    patient whose signals all went dark together looks perfectly current
    relative to themselves — the B3 failure one level down, and the reason
    pipeline.run_patient passes postop_day rather than relying on the
    fallback."""
    postop_day = 20
    series = _healthy_series(6, ProcedureType.TKA)  # every signal stops at day 6
    series[str(M.RESTING_HR)] = _vital_ramp(6, 62.0, 4.0, 4)
    series[str(M.SKIN_TEMP)] = _vital_ramp(6, 36.5, 0.3, 4)
    _, deviations = _analyze(series, ProcedureType.TKA)

    # Told the real day, every contributor is two weeks stale and drops out.
    assert composite_index(deviations, postop_day=postop_day).level == "normal"
    # Left to infer it, a fortnight-old ramp still scores as movement today.
    assert composite_index(deviations).level == "elevated"


# --- the established pre-op baseline (mutations; each one puts marcus back) ---

def _backdated_rhr(patient, days: int, value: float):
    """`days` pre-op days of resting HR, dated inside the ordinary window and
    carrying a value any body could produce — the shape of the back-fill that
    used to rewrite a patient's reference."""
    from app.connectors.mock import daily_observation
    from app.models.enums import SourceProvider
    from datetime import timedelta

    return [
        daily_observation(
            patient.id, SourceProvider.MOCK, M.RESTING_HR,
            patient.surgery_date - timedelta(days=offset), value,
        )
        for offset in range(1, days + 1)
    ]


def _drop(db, rows) -> None:
    from sqlalchemy import delete

    from app.engine.pipeline import run_patient
    from app.models.observation import Observation

    db.execute(
        delete(Observation).where(
            Observation.dedupe_key.in_([r.dedupe_key for r in rows])
        )
    )
    db.commit()
    run_patient(db, "marcus", force=True)


def test_a_backdated_batch_cannot_move_an_established_baseline(db):
    """The B2 reproduction, end to end through the ingest path.

    Fourteen pre-op days of resting HR 95 — real dates, plausible values —
    used to move marcus's baseline from 64.4 to 84.1 and drop him from HIGH
    with RHR_RISING + TEMP_RISING + COMPOSITE_HIGH to MEDIUM with none of
    them, on a 200 OK, with nothing on any screen saying the reference had
    moved.
    """
    from app.connectors.ingest import ingest_observations
    from app.engine.baseline_store import load_established
    from app.engine.pipeline import run_patient
    from app.models.patient import Patient

    patient = db.get(Patient, "marcus")
    before = run_patient(db, "marcus")
    held = load_established(db, "marcus")[str(M.RESTING_HR)]
    rows = _backdated_rhr(patient, 14, 95.0)
    ingested, _, _ = ingest_observations(db, rows)
    try:
        assert ingested == 14  # the data is kept; it just is not the reference
        after = run_patient(db, "marcus")
        assert after.risk_level == before.risk_level == RiskLevel.HIGH
        assert after.risk_score == before.risk_score
        assert {r["code"] for r in after.reasons} == {r["code"] for r in before.reasons}
        means = {b["metric_type"]: b["mean"] for b in after.analytics["baselines"]}
        assert means[str(M.RESTING_HR)] == held.mean
    finally:
        _drop(db, rows)


def test_ingest_pins_the_baseline_before_it_applies_the_batch(db):
    """Order matters on a database that predates the baseline store: the
    first delivery to arrive must not be what establishes the reference it is
    then judged against."""
    from app.connectors.ingest import ingest_observations
    from app.engine import baseline_store
    from app.engine.baseline_store import load_established
    from app.models.patient import Patient

    patient = db.get(Patient, "marcus")
    clean = load_established(db, "marcus")[str(M.RESTING_HR)].mean
    baseline_store.clear(db, "marcus")  # as if this table had just been added
    db.commit()
    rows = _backdated_rhr(patient, 14, 95.0)
    try:
        assert load_established(db, "marcus") == {}
        ingest_observations(db, rows)
        assert load_established(db, "marcus")[str(M.RESTING_HR)].mean == clean
    finally:
        _drop(db, rows)


def test_a_forced_recompute_re_establishes_the_baseline(db):
    """The escape hatch. Adopting a corrected pre-op record is an operator
    action with an obvious trigger, never a side effect of a webhook."""
    from app.connectors.ingest import ingest_observations
    from app.engine.baseline_store import load_established
    from app.engine.pipeline import run_patient
    from app.models.patient import Patient

    patient = db.get(Patient, "marcus")
    clean = load_established(db, "marcus")[str(M.RESTING_HR)].mean
    rows = _backdated_rhr(patient, 14, 95.0)
    ingest_observations(db, rows)
    try:
        run_patient(db, "marcus")
        assert load_established(db, "marcus")[str(M.RESTING_HR)].mean == clean
        run_patient(db, "marcus", force=True)
        assert load_established(db, "marcus")[str(M.RESTING_HR)].mean > clean
    finally:
        _drop(db, rows)
        assert load_established(db, "marcus")[str(M.RESTING_HR)].mean == clean


def test_withdrawing_the_preop_history_withdraws_the_baseline(db):
    """A reference with no evidence left under it is not a reference.

    Holding the established baseline is what stops later data from moving it —
    but a provider tombstone is a statement that the readings never should
    have counted, and deleted data may not keep driving the engine from
    behind a stored row nothing can see.
    """
    from sqlalchemy import select

    from app.engine.baseline_store import load_established
    from app.engine.pipeline import run_patient
    from app.models.observation import Observation
    from app.models.patient import Patient

    patient = db.get(Patient, "marcus")
    held = load_established(db, "marcus")[str(M.RESTING_HR)].mean
    preop = db.scalars(
        select(Observation).where(
            Observation.patient_id == "marcus",
            Observation.metric_type == str(M.RESTING_HR),
            Observation.local_date < patient.surgery_date,
        )
    ).all()
    assert preop, "the premise: marcus has pre-op resting HR on file"
    saved = {o.id: (o.deleted_at, o.ingested_at) for o in preop}
    for observation in preop:
        # exactly what a provider tombstone does through ingest._apply
        observation.deleted_at = datetime.now()
        observation.ingested_at = datetime.now()
    db.commit()
    try:
        run_patient(db, "marcus", force=False)
        assert str(M.RESTING_HR) not in load_established(db, "marcus")
    finally:
        for observation in preop:
            observation.deleted_at, observation.ingested_at = saved[observation.id]
        db.commit()
        run_patient(db, "marcus", force=True)
        assert load_established(db, "marcus")[str(M.RESTING_HR)].mean == held
