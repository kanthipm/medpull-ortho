"""Idempotent persistence of canonical observations.

Wearable providers re-deliver webhooks and back-fill late data as a matter of
course, so ingestion must tolerate duplicates: rows are keyed by dedupe_key and
re-delivery is counted, not inserted twice.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import CanonicalObservation
from app.models.observation import Observation


def ingest_observations(
    db: Session, observations: list[CanonicalObservation]
) -> tuple[int, int]:
    """Returns (ingested, duplicates)."""
    if not observations:
        return (0, 0)

    keys = [o.dedupe_key for o in observations]
    existing: set[str] = set(
        db.scalars(select(Observation.dedupe_key).where(Observation.dedupe_key.in_(keys))).all()
    )

    ingested = 0
    duplicates = 0
    seen: set[str] = set()
    for o in observations:
        key = o.dedupe_key
        if key in existing or key in seen:
            duplicates += 1
            continue
        seen.add(key)
        db.add(
            Observation(
                patient_id=o.patient_id,
                source_provider=o.source_provider,
                source_device_id=o.source_device_id,
                metric_type=o.metric_type,
                unit=o.unit,
                value_num=o.value_num,
                value_json=o.value_json,
                start_time=o.start_time,
                end_time=o.end_time,
                timezone=o.timezone,
                granularity=o.granularity,
                dedupe_key=key,
                raw_payload=o.raw_payload,
            )
        )
        ingested += 1
    db.commit()
    return (ingested, duplicates)
