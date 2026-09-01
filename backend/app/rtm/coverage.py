"""RTM monitoring-day coverage: distinct days with device data per rolling
30-day window, counted **from RTM enrollment onward** (SPEC.md §2).

Device data collected before enrollment completes (the CPT 98975 setup +
education + baseline event) feeds the engine's pre-op baselines but never
counts toward the 98985/98977 monitoring thresholds — a patient can't accrue
billable monitoring days before they are enrolled in monitoring.

The window is bounded on BOTH sides. A backdated or future-dated delivery must
not lift a patient over the 16-of-30 cliff, and the upper bound is what makes
"days out of 30" a count that cannot exceed 30 — readiness.py relies on that
to read `>= 16` as the spec's "16–30".
"""

from datetime import date, datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.observation import Observation
from app.models.rtm import EnrollmentStatus, MonitoringWindow

WINDOW_DAYS = 30
QUALIFY_DAYS = 16


def monitoring_start(db: Session, patient_id: str, today: date | None = None) -> date | None:
    """First date that can count as a monitoring day, or None if the patient
    is not yet enrolled. Never earlier than the rolling window itself."""
    today = today or date.today()
    enrollment = db.get(EnrollmentStatus, patient_id)
    if enrollment is None or not enrollment.complete or enrollment.enrolled_at is None:
        return None
    window_floor = today - timedelta(days=WINDOW_DAYS - 1)
    return max(window_floor, enrollment.enrolled_at.date())


def update_window(db: Session, patient_id: str, today: date | None = None) -> MonitoringWindow:
    today = today or date.today()
    window_start = today - timedelta(days=WINDOW_DAYS - 1)

    start = monitoring_start(db, patient_id, today)
    if start is None:
        days = 0
    else:
        # Only rows flagged at normalize() as RTM-qualifying count: mock/demo
        # data and unsigned deliveries are structurally incapable of accruing
        # a billable day. Days are the MATERIALIZED patient-local calendar
        # date — func.date() on a naive instant puts a West Coast patient's
        # evening activity on the wrong day, and 16-of-30 is a cliff.
        days = db.scalar(
            select(func.count(distinct(Observation.local_date))).where(
                Observation.patient_id == patient_id,
                Observation.local_date >= start,
                Observation.local_date <= today,
                Observation.qualifies_for_rtm.is_(True),
                Observation.deleted_at.is_(None),
            )
        ) or 0

    # Oldest first, so a table that already holds twins resolves to one row
    # deterministically instead of to whichever copy the planner returned.
    rows = db.scalars(
        select(MonitoringWindow)
        .where(
            MonitoringWindow.patient_id == patient_id,
            MonitoringWindow.window_start == window_start,
        )
        .order_by(MonitoringWindow.id)
    ).all()
    row = rows[0] if rows else None
    if row is None:
        row = MonitoringWindow(
            patient_id=patient_id, window_start=window_start, window_end=today,
            days_with_data=int(days), qualifies_16_of_30=days >= QUALIFY_DAYS,
        )
        db.add(row)
    else:
        row.window_end = today
        row.days_with_data = int(days)
        row.qualifies_16_of_30 = days >= QUALIFY_DAYS
        row.computed_at = datetime.now()
    # The model now carries a unique constraint on (patient_id, window_start),
    # but there are no migrations and create_all is additive, so a database
    # written before it keeps the old schema and can already hold twins from a
    # lost select-then-upsert race. Collapse them onto the row just refreshed,
    # or get_current() goes on serving whichever copy won the id race.
    for twin in rows[1:]:
        db.delete(twin)
    db.commit()
    return row


def get_current(db: Session, patient_id: str) -> MonitoringWindow | None:
    return db.scalar(
        select(MonitoringWindow)
        .where(MonitoringWindow.patient_id == patient_id)
        .order_by(MonitoringWindow.window_end.desc(), MonitoringWindow.id.desc())
        .limit(1)
    )
