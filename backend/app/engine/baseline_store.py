"""Established pre-op baselines: computed once, then held.

The engine measures a patient against their own pre-op normal. That reference
has to be stable, because everything downstream is a comparison TO it: a
z-score, a flag, a tier, a page to the care team. `compute_baseline()` reads
every day with a negative post-op index as pre-op, so anything that adds
pre-op-dated days later does not lengthen the pre-op record — it moves the
reference, and every past finding silently becomes a different finding.

That is not hypothetical. Posting fourteen backdated days of resting HR 95 and
skin temp 38.5 for a post-op-day-8 patient — dates inside the ordinary pre-op
window, values inside any plausible physiological range, delivered through the
demo webhook — moved one seeded patient's resting-HR baseline from 64.4 to
84.1 and his temperature baseline from 36.6 to 37.8, which dropped him from
HIGH 91.1 with RHR_RISING + TEMP_RISING + COMPOSITE_HIGH to MEDIUM 60.0 with
none of them. The response was 200 {"ingested": 28}. Nothing on any screen
said the reference had moved.

No date window fixes that, because the attack is dated exactly where the truth
lives. What fixes it is refusing to treat the reference as a running
statistic:

* the FIRST time enough pre-op history exists to compute a pre-op baseline for
  a metric, it is written here and that is the patient's baseline;
* later data — new, restated, or back-filled — is stored and charted as
  usual, but does not move it;
* a post-op ANCHOR (`is_preop=False`) is never stored: it is a stand-in, and
  it must stay free to be replaced the day real pre-op history arrives;
* if a patient's pre-op history is withdrawn entirely (provider tombstones),
  the stored row goes with it — deleted data may not keep driving the engine;
* `run_patient(force=True)` clears the stored rows first, so re-establishing a
  baseline is a deliberate operator action with an obvious trigger, rather
  than something an inbound webhook can do by accident.
"""

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.engine import ENGINE_VERSION
from app.engine.types import Baseline
from app.models.insight import EstablishedBaseline

logger = logging.getLogger(__name__)

# How far a freshly computed pre-op baseline may drift from the established one
# before it is worth a line in the log. Small restatements are routine; a shift
# this size is the signature of a back-fill rewriting the reference, and an
# operator looking into "why did this patient's tier move" should be able to
# find it.
DRIFT_WARN_SDS = 1.0


def _to_baseline(row: EstablishedBaseline) -> Baseline:
    return Baseline(
        metric_type=row.metric_type,
        mean=row.mean,
        sd=row.sd,
        n_days=row.n_days,
        window=row.window,
        is_preop=True,
        window_days=[int(d) for d in (row.window_days or [])],
    )


def load_established(db: Session, patient_id: str) -> dict[str, Baseline]:
    """metric_type -> the patient's established pre-op baseline."""
    rows = db.scalars(
        select(EstablishedBaseline).where(EstablishedBaseline.patient_id == patient_id)
    ).all()
    return {row.metric_type: _to_baseline(row) for row in rows}


def clear(db: Session, patient_id: str, metric_types: list[str] | None = None) -> None:
    """Drop established baselines so the next run re-establishes them."""
    statement = delete(EstablishedBaseline).where(
        EstablishedBaseline.patient_id == patient_id
    )
    if metric_types is not None:
        if not metric_types:
            return
        statement = statement.where(EstablishedBaseline.metric_type.in_(metric_types))
    db.execute(statement)


def establish(db: Session, patient_id: str, baselines: dict[str, Baseline]) -> None:
    """Store any pre-op baseline this patient does not have one for yet.

    Idempotent and additive: a metric that already has a row keeps it, and a
    post-op anchor is never written.
    """
    existing = {
        row.metric_type
        for row in db.scalars(
            select(EstablishedBaseline).where(
                EstablishedBaseline.patient_id == patient_id
            )
        )
    }
    added = False
    for metric_type, baseline in baselines.items():
        if not baseline.is_preop or metric_type in existing:
            continue
        db.add(
            EstablishedBaseline(
                patient_id=patient_id,
                metric_type=metric_type,
                mean=baseline.mean,
                sd=baseline.sd,
                n_days=baseline.n_days,
                window=baseline.window,
                window_days=list(baseline.window_days),
                engine_version=ENGINE_VERSION,
            )
        )
        added = True
    if added:
        db.flush()


def ensure_established(db: Session, patient_id: str) -> None:
    """Establish this patient's pre-op baselines from the record as it stands
    right now, if they have not been established yet.

    Ingestion calls this BEFORE it writes, which is what makes the guarantee
    hold on a database that predates this table: the reference is whatever the
    record said before the delivery arrived, never something the delivery
    itself created. Without it the first back-fill to reach an upgraded
    deployment would establish the baseline out of its own contents.

    A patient with no pre-op history for a metric establishes nothing, and is
    re-examined on the next delivery — which is correct: their pre-op record
    is still open, and real pre-op history arriving later should fill it.
    """
    # Local imports: pipeline imports this module.
    from app.engine.baseline import compute_baseline
    from app.engine.dataload import load_daily_series
    from app.engine.pipeline import ANALYZED_METRICS
    from app.models.patient import Patient

    patient = db.get(Patient, patient_id)
    if patient is None:
        return
    stored = {
        row.metric_type
        for row in db.scalars(
            select(EstablishedBaseline).where(
                EstablishedBaseline.patient_id == patient_id
            )
        )
    }
    wanted = [m for m in ANALYZED_METRICS if str(m) not in stored]
    if not wanted:
        return
    series = load_daily_series(db, patient_id, patient.surgery_date)
    fresh: dict[str, Baseline] = {}
    for metric in wanted:
        s = series.get(str(metric))
        if s is None:
            continue
        baseline = compute_baseline(str(metric), s)
        if baseline is not None:
            fresh[str(metric)] = baseline
    if fresh:
        establish(db, patient_id, fresh)


def note_drift(patient_id: str, metric_type: str, held: Baseline, fresh: Baseline) -> None:
    """Log when the data now on file would have produced a materially
    different pre-op baseline than the one being used."""
    if held.sd <= 0:
        return
    shift = abs(fresh.mean - held.mean) / held.sd
    if shift >= DRIFT_WARN_SDS:
        logger.warning(
            "%s/%s: pre-op data on file now implies mean %.3f (%s), %.1f SD from the "
            "established baseline %.3f (%s) — keeping the established one; force a "
            "recompute to adopt it",
            patient_id, metric_type, fresh.mean, fresh.window, shift, held.mean,
            held.window,
        )
