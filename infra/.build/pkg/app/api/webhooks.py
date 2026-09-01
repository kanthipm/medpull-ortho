"""Wearable webhook ingestion — the seam where real providers will plug in.

Flow: verify signature (stubbed permissive in v1) -> persist the raw event ->
normalize via the provider's connector -> idempotent upsert -> recompute the
affected patients' assessments.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.ingest import ingest_observations
from app.connectors.registry import get_provider_info
from app.database import get_db
from app.models.enums import SourceProvider
from app.models.observation import WebhookEvent
from app.models.patient import Patient

router = APIRouter(tags=["webhooks"])


def verify_signature(provider: SourceProvider, payload: dict) -> bool:
    """Placeholder. Real connectors verify provider-specific signatures here
    (Terra: HMAC terra-signature header; Junction: Svix headers)."""
    return True


@router.post("/webhooks/wearables/{provider}")
def ingest_webhook(provider: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    try:
        key = SourceProvider(provider)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    info = get_provider_info(key)
    if info is None or info.connector is None:
        raise HTTPException(
            status_code=501,
            detail=f"{info.name if info else provider} webhooks are scaffolded but not yet implemented — POST to /api/webhooks/wearables/mock for the demo path.",
        )

    event = WebhookEvent(
        provider=provider, signature_valid=verify_signature(key, payload), payload=payload
    )
    db.add(event)
    db.commit()

    try:
        observations = info.connector.normalize(payload)
        # Validate BEFORE ingesting — otherwise a payload naming an unknown
        # patient would commit orphaned observation rows and then crash the
        # recompute loop.
        patient_ids = {o.patient_id for o in observations}
        known = set(db.scalars(select(Patient.id).where(Patient.id.in_(patient_ids))).all())
        unknown = patient_ids - known
        if unknown:
            raise ValueError(f"Unknown patient(s): {', '.join(sorted(unknown))}")
        ingested, duplicates = ingest_observations(db, observations)
    except (ValueError, KeyError) as e:
        event.status = "failed"
        event.error = str(e)
        db.commit()
        raise HTTPException(status_code=422, detail=f"Payload rejected: {e}")

    event.status = "processed"
    event.processed_at = datetime.now()
    db.commit()

    from app.engine.pipeline import run_patient

    for patient_id in patient_ids:
        run_patient(db, patient_id)

    return {"accepted": True, "ingested": ingested, "duplicates": duplicates}
