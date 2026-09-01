"""Verified adherence over the last 14 days."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.types import AdherenceResult
from app.models.adherence import AdherenceRecord
from app.models.enums import AdherenceStatus

WINDOW = 14


def compute_adherence(db: Session, patient_id: str, today: date) -> AdherenceResult:
    start = today - timedelta(days=WINDOW - 1)
    records = db.scalars(
        select(AdherenceRecord).where(
            AdherenceRecord.patient_id == patient_id,
            AdherenceRecord.date >= start,
        )
    ).all()

    verified = sum(1 for r in records if r.status == AdherenceStatus.VERIFIED)
    self_attested = sum(1 for r in records if r.status == AdherenceStatus.SELF_ATTESTED)
    assigned = len(records)
    rate = (verified + 0.5 * self_attested) / assigned if assigned else 0.0

    days: list[float] = []
    by_day: dict[date, list[AdherenceRecord]] = {}
    for r in records:
        by_day.setdefault(r.date, []).append(r)
    for i in range(WINDOW):
        d = start + timedelta(days=i)
        day_records = by_day.get(d, [])
        if not day_records:
            days.append(0.0)
            continue
        score = sum(
            1.0 if r.status == AdherenceStatus.VERIFIED
            else 0.5 if r.status == AdherenceStatus.SELF_ATTESTED
            else 0.0
            for r in day_records
        ) / len(day_records)
        days.append(1.0 if score >= 0.75 else 0.5 if score >= 0.35 else 0.0)

    return AdherenceResult(
        rate=round(rate, 2),
        verified=verified,
        assigned=assigned,
        self_attested=self_attested,
        days=days,
    )
