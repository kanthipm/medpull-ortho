"""Engine orchestration: observations in, RiskAssessment out.

Results are stored, not computed per request. Every read path does a cheap
staleness check (input hash over the observation set + engine version) and
recomputes lazily only when data actually changed — which, in v1, happens only
on webhook ingest or re-seed.
"""

import hashlib
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engine import ENGINE_VERSION
from app.engine.adherence import compute_adherence
from app.engine.baseline import compute_baseline
from app.engine import baseline_store
from app.engine.composite import composite_index
from app.engine.confidence import coverage
from app.engine.dataload import load_daily_series
from app.engine.deviation import analyze_metric
from app.engine.metrics_cards import build_cards
from app.engine.risk import score_risk
from app.engine.trajectory import compare, functional_index, is_anchored
from app.engine.types import AnalyticsBundle, Baseline, DeviationResult
from app.models.enums import MetricType as M
from app.models.enums import RiskLevel
from app.models.insight import RiskAssessment
from app.models.observation import Observation
from app.models.patient import Patient

ANALYZED_METRICS = [
    M.STEPS, M.WALKING_SPEED, M.RESTING_HR, M.HRV_RMSSD, M.SLEEP_DURATION,
    M.SKIN_TEMP, M.SPO2, M.RESPIRATORY_RATE, M.WALKING_ASYMMETRY_PCT,
]


def compute_input_hash(db: Session, patient_id: str) -> str:
    count, latest = db.execute(
        select(func.count(Observation.id), func.max(Observation.ingested_at)).where(
            Observation.patient_id == patient_id
        )
    ).one()
    # today's date is part of the hash: postop_day and the recent-window stats
    # shift at midnight even when no new data arrives, so the first request of
    # each day lazily recomputes every assessment.
    payload = f"{patient_id}:{count}:{latest}:{date.today()}:{ENGINE_VERSION}"
    return hashlib.sha256(payload.encode()).hexdigest()


def latest_assessment(db: Session, patient_id: str) -> RiskAssessment | None:
    return db.scalar(
        select(RiskAssessment)
        .where(RiskAssessment.patient_id == patient_id)
        .order_by(RiskAssessment.computed_at.desc(), RiskAssessment.id.desc())
        .limit(1)
    )


def run_patient(db: Session, patient_id: str, force: bool = False) -> RiskAssessment:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ValueError(f"Unknown patient: {patient_id}")

    input_hash = compute_input_hash(db, patient_id)
    previous = latest_assessment(db, patient_id)
    if previous is not None and previous.input_hash == input_hash and not force:
        # The assessment is current, but the RTM monitoring window is a second
        # stored output of this function and it can be missing or stale on its
        # own (an empty table, a window that ended yesterday). Nothing else
        # writes it, so returning here without a look left every RTM surface
        # agreeing on a count that no longer matched the observations.
        _refresh_window(db, patient_id, date.today())
        return previous

    today = date.today()
    if force:
        # An operator-triggered recompute is the one place a pre-op baseline
        # may be re-established from whatever is on file now.
        baseline_store.clear(db, patient_id)
        db.commit()
    postop_day = (today - patient.surgery_date).days
    series = load_daily_series(db, patient_id, patient.surgery_date)

    # The patient's established pre-op norms. Data that arrives later is
    # stored, charted and scored against these — it does not redefine them
    # (engine/baseline_store.py).
    established = baseline_store.load_established(db, patient_id)
    withdrawn = [
        metric_type
        for metric_type in established
        if str(metric_type) not in series
        or not (series[str(metric_type)].index < 0).any()
    ]
    if withdrawn:
        # The pre-op history behind these rows is gone (tombstoned or purged);
        # a reference with no evidence left under it is not a reference.
        baseline_store.clear(db, patient_id, withdrawn)
        db.commit()
        for metric_type in withdrawn:
            established.pop(metric_type, None)

    baselines: dict[str, Baseline] = {}
    deviations: dict[str, DeviationResult] = {}
    for metric in ANALYZED_METRICS:
        s = series.get(str(metric))
        if s is None:
            continue
        held = established.get(str(metric))
        if held is not None:
            fresh = compute_baseline(str(metric), s)
            if fresh is not None and fresh.is_preop:
                baseline_store.note_drift(patient_id, str(metric), held, fresh)
        result = analyze_metric(metric, s, patient.procedure_type, baseline=held)
        if result is None:
            continue
        baselines[str(metric)], deviations[str(metric)] = result

    baseline_store.establish(db, patient_id, baselines)

    confidence = coverage(series, postop_day)
    index = functional_index(series, baselines, patient.procedure_type)
    trajectory = compare(
        index, patient.procedure_type, postop_day, anchored=is_anchored(baselines)
    )
    composite = composite_index(deviations, postop_day=postop_day)
    adherence = compute_adherence(db, patient_id, today)

    # The gait rule in risk.py takes an absolute threshold rather than a
    # control chart, so it gets the raw latest value — and its day with it,
    # which is what lets that rule apply the same recency window every other
    # rule gets for free through its DeviationResult.
    gait_series = series.get(str(M.WALKING_ASYMMETRY_PCT))
    gait_postop = (
        gait_series[gait_series.index >= 0] if gait_series is not None else None
    )
    gait_latest = float(gait_postop.iloc[-1]) if gait_postop is not None and len(gait_postop) else None
    gait_day = int(gait_postop.index[-1]) if gait_postop is not None and len(gait_postop) else None

    risk = score_risk(
        postop_day, deviations, trajectory, composite, confidence, adherence,
        gait_latest, gait_day,
    )
    cards = build_cards(
        series, baselines, deviations, confidence, patient.procedure_type,
        postop_day, patient.surgery_date,
    )

    bundle = AnalyticsBundle(
        patient_id=patient_id,
        postop_day=postop_day,
        risk=risk,
        confidence=confidence,
        trajectory=trajectory,
        composite=composite,
        adherence=adherence,
        metrics=cards,
        baselines=list(baselines.values()),
    )

    assessment = RiskAssessment(
        patient_id=patient_id,
        risk_level=risk.level,
        risk_score=risk.score,
        reasons=[
            {"code": r.code, "text": r.text, "metric_type": r.metric_type, "severity": r.severity}
            for r in risk.reasons
        ],
        data_confidence=confidence.score,
        trajectory_state=trajectory.state,
        trajectory_pct=trajectory.pct,
        analytics=bundle.to_dict(),
        input_hash=input_hash,
        engine_version=ENGINE_VERSION,
    )
    db.add(assessment)
    db.commit()

    was_high = previous is not None and previous.risk_level == RiskLevel.HIGH
    if risk.level == RiskLevel.HIGH and not was_high:
        try:
            from app.notifications.service import notify_high_priority

            notify_high_priority(db, patient, assessment)
        except ImportError:
            pass

    from app.rtm.coverage import update_window

    update_window(db, patient_id, today)
    return assessment


def ensure_current(db: Session, patient_id: str) -> RiskAssessment:
    """The read path's staleness check — assessment AND monitoring window.

    Every surface that renders a patient goes through here, so it owns both of
    run_patient's stored outputs. Checking only the assessment left a real
    hole: the input hash is fresh for the rest of the calendar day, so with a
    monitoring window that was missing or ended yesterday, the worklist chip,
    the patient page and the RTM card all agreed on a day count that no longer
    matched the observations — consistent, and consistently wrong, with
    nothing to make it self-heal until the observation set changed.
    """
    current = latest_assessment(db, patient_id)
    if current is None or current.input_hash != compute_input_hash(db, patient_id):
        return run_patient(db, patient_id)
    _refresh_window(db, patient_id, date.today())
    return current


def _refresh_window(db: Session, patient_id: str, today: date) -> None:
    """Bring the RTM monitoring window up to today if it is not already.

    One indexed read on the hot path; it writes only when the stored window is
    missing or does not cover today, which is at most once per patient per day.
    """
    from app.rtm.coverage import WINDOW_DAYS, get_current, update_window

    from datetime import timedelta

    current = get_current(db, patient_id)
    if (
        current is not None
        and current.window_end == today
        and current.window_start == today - timedelta(days=WINDOW_DAYS - 1)
    ):
        return
    update_window(db, patient_id, today)


def run_all(db: Session, force: bool = False) -> list[RiskAssessment]:
    patient_ids = db.scalars(select(Patient.id)).all()
    return [run_patient(db, pid, force=force) for pid in patient_ids]
