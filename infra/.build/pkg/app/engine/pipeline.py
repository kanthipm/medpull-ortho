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
from app.engine.composite import composite_index
from app.engine.confidence import coverage
from app.engine.dataload import load_daily_series
from app.engine.deviation import analyze_metric
from app.engine.metrics_cards import build_cards
from app.engine.risk import score_risk
from app.engine.trajectory import compare, functional_index
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
        return previous

    today = date.today()
    postop_day = (today - patient.surgery_date).days
    series = load_daily_series(db, patient_id, patient.surgery_date)

    baselines: dict[str, Baseline] = {}
    deviations: dict[str, DeviationResult] = {}
    for metric in ANALYZED_METRICS:
        s = series.get(str(metric))
        if s is None:
            continue
        result = analyze_metric(metric, s, patient.procedure_type)
        if result is None:
            continue
        baselines[str(metric)], deviations[str(metric)] = result

    confidence = coverage(series, postop_day)
    index = functional_index(series, baselines)
    trajectory = compare(index, patient.procedure_type, postop_day)
    composite = composite_index(deviations)
    adherence = compute_adherence(db, patient_id, today)

    gait_series = series.get(str(M.WALKING_ASYMMETRY_PCT))
    gait_latest = (
        float(gait_series[gait_series.index >= 0].iloc[-1])
        if gait_series is not None and len(gait_series[gait_series.index >= 0]) > 0
        else None
    )

    risk = score_risk(
        postop_day, deviations, trajectory, composite, confidence, adherence, gait_latest
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


def run_all(db: Session, force: bool = False) -> list[RiskAssessment]:
    patient_ids = db.scalars(select(Patient.id)).all()
    return [run_patient(db, pid, force=force) for pid in patient_ids]
