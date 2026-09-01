"""Integrations: the provider list the console reads, the aggregator's health,
and the per-patient wearable connection lifecycle (link, inspect, back-fill,
disconnect) that Junction is driven through.

Every Junction-backed route answers 503 when JUNCTION_API_KEY is unset, 409
when the patient's account belongs to the other environment, and 502 when
Junction itself could not be reached — three different problems that a
provider staring at a "Connect" button should be able to tell apart.
"""

from collections import Counter
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.connectors.capabilities import CAPABILITIES, GAIT
from app.connectors.ingest import ingest_in_batches, partition_by_window
from app.connectors.junction import JunctionConnector
from app.connectors.junction_client import (
    JunctionError,
    JunctionNotConfigured,
    resolved_base_url,
)
from app.connectors.registry import (
    PROVIDERS,
    get_provider_info,
    junction_connector,
    provider_status,
)
from app.database import get_db
from app.models.connection import WearableConnection
from app.models.enums import ConnectionStatus, SourceProvider
from app.models.observation import WebhookEvent
from app.models.patient import Device, Patient

router = APIRouter(tags=["integrations"])

WEBHOOK_PATH = "/api/webhooks/wearables/junction"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _connection_view(conn: WearableConnection | None) -> dict[str, Any] | None:
    if conn is None:
        return None
    return {
        "status": str(conn.status),
        "environment": conn.environment,
        "external_user_id": conn.external_user_id,
        "providers": conn.providers or [],
        "created_at": _iso(conn.created_at),
        "last_link_issued_at": _iso(conn.last_link_issued_at),
        "last_event_at": _iso(conn.last_event_at),
        "last_data_at": _iso(conn.last_data_at),
        "last_backfill_at": _iso(conn.last_backfill_at),
        "last_error": conn.last_error,
    }


def _device_view(device: Device) -> dict[str, Any]:
    return {
        "id": device.id,
        "provider": str(device.source_provider),
        "model": device.device_model,
        "status": device.status,
        "connected_at": _iso(device.connected_at),
        "last_sync_at": _iso(device.last_sync_at),
        "via_junction": device.id.startswith("junction:"),
    }


def _aggregator_status(db: Session) -> dict[str, Any]:
    connections = db.scalars(
        select(WearableConnection).where(
            WearableConnection.aggregator == SourceProvider.JUNCTION
        )
    ).all()
    by_status = Counter(str(c.status) for c in connections)
    last_delivery = db.scalar(
        select(func.max(WebhookEvent.received_at)).where(WebhookEvent.provider == "junction")
    )
    last_processed = db.scalar(
        select(func.max(WebhookEvent.processed_at)).where(
            WebhookEvent.provider == "junction", WebhookEvent.status == "processed"
        )
    )
    try:
        base_url: str | None = resolved_base_url()
    except JunctionError:
        base_url = None
    return {
        "key": "junction",
        "name": "Junction",
        "configured": JunctionConnector.is_configured(),
        "environment": settings.junction_environment,
        "region": settings.junction_region,
        "base_url": base_url,
        "webhook_secret_configured": bool(settings.junction_webhook_secret),
        "webhook_path": WEBHOOK_PATH,
        "link_redirect_url": settings.junction_link_redirect_url or None,
        "heart_rate_samples": settings.junction_ingest_heart_rate_samples,
        "connections": {
            "total": len(connections),
            "linked": by_status.get(str(ConnectionStatus.LINKED), 0),
            "pending": by_status.get(str(ConnectionStatus.PENDING_LINK), 0),
            "error": by_status.get(str(ConnectionStatus.ERROR), 0),
            "disconnected": by_status.get(str(ConnectionStatus.DISCONNECTED), 0),
        },
        "last_delivery_at": _iso(last_delivery),
        "last_processed_at": _iso(last_processed),
    }


@router.get("/integrations")
def list_integrations(db: Session = Depends(get_db)) -> dict:
    device_counts = dict(
        db.execute(
            select(Device.source_provider, func.count(Device.id))
            .where(Device.status != "revoked")
            .group_by(Device.source_provider)
        ).all()
    )
    providers = []
    for info in PROVIDERS:
        capabilities = CAPABILITIES.get(info.key, [])
        providers.append(
            {
                "key": str(info.key),
                "name": info.name,
                "status": provider_status(info),
                "junction_slug": info.junction_slug,
                "capabilities": [str(m) for m in capabilities],
                "connected_patients": int(device_counts.get(info.key, 0)),
                "gait_capable": any(m in capabilities for m in GAIT),
            }
        )
    return {"providers": providers, "aggregator": _aggregator_status(db)}


@router.get("/integrations/junction/status")
def junction_status(limit: int = 10, db: Session = Depends(get_db)) -> dict:
    limit = max(1, min(limit, 50))
    events = db.scalars(
        select(WebhookEvent)
        .where(WebhookEvent.provider == "junction")
        .order_by(WebhookEvent.id.desc())
        .limit(limit)
    ).all()
    recent = [
        {
            "id": e.id,
            "received_at": _iso(e.received_at),
            "event_type": (e.payload or {}).get("event_type") if isinstance(e.payload, dict) else None,
            "status": e.status,
            "signature_valid": e.signature_valid,
            "error": e.error,
        }
        for e in events
    ]
    return {**_aggregator_status(db), "recent_events": recent}


@router.get("/integrations/junction/webhook-portal")
def junction_webhook_portal() -> dict:
    """Junction registers webhook endpoints in its dashboard (a Svix portal);
    this fetches the portal URL for the team so an operator can get there
    from the console."""
    _require_configured()
    try:
        url = junction_connector().webhook_portal_url()
    except JunctionError as e:
        raise HTTPException(status_code=502, detail=f"Junction call failed: {e}")
    return {"url": url, "webhook_path": WEBHOOK_PATH}


@router.post("/integrations/{provider}/connect")
def connect(provider: str, db: Session = Depends(get_db)) -> dict:
    try:
        key = SourceProvider(provider)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    info = get_provider_info(key)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    status = provider_status(info)
    if key is SourceProvider.JUNCTION:
        return {
            "status": status,
            "configured": JunctionConnector.is_configured(),
            "hint": "Devices are linked per patient: open a patient record and use "
            "Connect wearable to issue a Junction Link.",
        }
    if info.connector is None:
        if status == "via_junction":
            raise HTTPException(
                status_code=409,
                detail=f"{info.name} connects through Junction — issue a Link from the "
                "patient's record rather than here.",
            )
        if status == "needs_app":
            raise HTTPException(
                status_code=501,
                detail=f"{info.name} is an on-device store; it reaches Junction only "
                "through its mobile SDK inside a patient app, which does not exist yet.",
            )
        raise HTTPException(
            status_code=501,
            detail=f"{info.name} integration is scaffolded but not yet implemented.",
        )
    return {"status": status}


# --- per-patient wearable connections -----------------------------------------


def _require_configured() -> None:
    if not JunctionConnector.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Junction is not configured: set JUNCTION_API_KEY (and "
            "JUNCTION_WEBHOOK_SECRET) to enable live wearable connections.",
        )


def _patient_or_404(db: Session, patient_id: str) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_id}")
    return patient


def _raise_for(e: Exception) -> None:
    if isinstance(e, JunctionNotConfigured):
        raise HTTPException(status_code=503, detail=str(e))
    if isinstance(e, JunctionError):
        if e.status == 409:
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=502, detail=f"Junction call failed: {e}")
    if isinstance(e, ValueError):
        raise HTTPException(status_code=409, detail=str(e))
    raise e


@router.get("/patients/{patient_id}/wearables")
def patient_wearables(
    patient_id: str, refresh: bool = False, db: Session = Depends(get_db)
) -> dict:
    """The patient's aggregator account and device rows. ``refresh=true`` asks
    Junction what it currently reports as connected and updates the snapshot."""
    patient = _patient_or_404(db, patient_id)
    connector = junction_connector()
    conn = connector.connection_for(db, patient_id)
    refresh_error: str | None = None
    if refresh and conn is not None and conn.status != ConnectionStatus.DISCONNECTED:
        try:
            connector.sync_providers(db, patient_id)
        except (JunctionError, ValueError) as e:
            refresh_error = str(e)
        db.refresh(patient)
    devices = [_device_view(d) for d in patient.devices]
    return {
        "patient_id": patient.id,
        "aggregator": {
            "configured": JunctionConnector.is_configured(),
            "environment": settings.junction_environment,
        },
        "connection": _connection_view(conn),
        "devices": devices,
        "refresh_error": refresh_error,
    }


@router.post("/patients/{patient_id}/wearables/junction/link")
def create_junction_link(patient_id: str, db: Session = Depends(get_db)) -> dict:
    """Mint a Junction Link for the patient. The URL is one-time and
    short-lived; the clinic hands it to the patient, who signs in to their
    device's cloud account on Junction's hosted page."""
    _require_configured()
    _patient_or_404(db, patient_id)
    try:
        session = junction_connector().create_link(db, patient_id)
    except (JunctionError, ValueError) as e:
        _raise_for(e)
    return {
        "link_url": session.url,
        "expires_at": session.expires_at,
        "connection": _connection_view(session.connection),
    }


class BackfillBody(BaseModel):
    since: date | None = None
    until: date | None = None
    # Ask Junction to re-pull from every connected provider before we read —
    # the manual form of the nightly trailing re-pull the data-layer design
    # calls for.
    refresh: bool = False


@router.post("/patients/{patient_id}/wearables/junction/backfill")
def junction_backfill(
    patient_id: str, body: BackfillBody | None = None, db: Session = Depends(get_db)
) -> dict:
    _require_configured()
    patient = _patient_or_404(db, patient_id)
    body = body or BackfillBody()
    connector = junction_connector()
    try:
        conn = connector.active_connection(db, patient_id)
        if body.refresh:
            connector.request_refresh(conn)
        report = connector.pull(db, conn, patient, start=body.since, end=body.until)
    except (JunctionError, ValueError) as e:
        _raise_for(e)
    inside, outside = partition_by_window(db, report.observations)
    ingested, updated, duplicates = ingest_in_batches(db, inside)
    now = datetime.now()
    conn.last_backfill_at = now
    if ingested or updated:
        conn.last_data_at = now
        connector.mark_synced(db, conn, inside)
    db.commit()
    if ingested or updated:
        from app.engine.pipeline import run_patient

        run_patient(db, patient_id)
    return {
        "ok": True,
        "start": report.start.isoformat() if report.start else None,
        "end": report.end.isoformat() if report.end else None,
        "resources": report.resources,
        "skipped_resources": report.skipped,
        "complete": report.complete,
        "ingested": ingested,
        "updated": updated,
        "duplicates": duplicates,
        "skipped_out_of_window": len(outside),
        "dropped_implausible": report.dropped,
        "connection": _connection_view(conn),
    }


@router.delete("/patients/{patient_id}/wearables/junction")
def disconnect_junction(patient_id: str, db: Session = Depends(get_db)) -> dict:
    """Deregister the patient at Junction and retire the mapping. Ingested
    observations stay — they are the patient's history."""
    _patient_or_404(db, patient_id)
    try:
        result = junction_connector().disconnect(db, patient_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "ok": True,
        "remote": result["remote"],
        "connection": _connection_view(result["connection"]),
    }
