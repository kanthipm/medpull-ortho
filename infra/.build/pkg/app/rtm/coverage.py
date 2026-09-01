"""RTM monitoring-day coverage: distinct days with device data per rolling
30-day window, counted **from RTM enrollment onward** (SPEC.md §2).

Device data collected before enrollment completes (the CPT 98975 setup +
education + baseline event) feeds the engine's pre-op baselines but never
counts toward the 98985/98977 monitoring thresholds — a patient can't accrue
billable monitoring days before they are enrolled in monitoring.
"""

from datetime import date, datetime, time, timedelta

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
        days = db.scalar(
            select(func.count(distinct(func.date(Observation.start_time)))).where(
                Observation.patient_id == patient_id,
                Observation.start_time >= datetime.combine(start, time.min),
            )
        ) or 0

    row = db.scalar(
        select(MonitoringWindow)
        .where(
            MonitoringWindow.patient_id == patient_id,
            MonitoringWindow.window_start == window_start,
        )
        .limit(1)
    )
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
    db.commit()
    return row


def get_current(db: Session, patient_id: str) -> MonitoringWindow | None:
    return db.scalar(
        select(MonitoringWindow)
        .where(MonitoringWindow.patient_id == patient_id)
        .order_by(MonitoringWindow.window_end.desc(), MonitoringWindow.id.desc())
        .limit(1)
    )
