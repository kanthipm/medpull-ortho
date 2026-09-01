"""Wearable webhook ingestion — the seam where real providers plug in.

Flow: verify the signature against the RAW request bytes -> persist the event
-> normalize via the provider's connector -> idempotent upsert -> recompute the
affected patients.

Signature verification is a per-provider strategy table, and it fails closed:
an unverifiable delivery is recorded and rejected before a single observation
row is written. Verification MUST run on the raw bytes — re-serializing parsed
JSON does not reproduce the original body (key order, whitespace, unicode
escaping all differ), which makes HMAC over a dict mathematically meaningless.
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.connectors.ingest import ingest_observations
from app.connectors.registry import get_provider_info
from app.database import get_db
from app.models.enums import SourceProvider
from app.models.observation import WebhookEvent
from app.models.patient import Patient

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])

SKEW_TOLERANCE_S = 300  # accept timestamps ±5 minutes from server receipt


def _verify_svix(secret: str, headers: Mapping[str, str], body: bytes) -> bool:
    """Junction delivers through Svix: HMAC-SHA256 over "{id}.{timestamp}.{body}"
    with the base64 payload of the whsec_ secret; svix-signature carries a
    space-separated list of "v1,<base64sig>" candidates (key rotation)."""
    msg_id = headers.get("svix-id", "")
    timestamp = headers.get("svix-timestamp", "")
    signatures = headers.get("svix-signature", "")
    if not (msg_id and timestamp and signatures):
        return False
    try:
        if abs(time.time() - int(timestamp)) > SKEW_TOLERANCE_S:
            return False
        key = base64.b64decode(secret.removeprefix("whsec_"))
    except (ValueError, TypeError):
        return False
    signed = f"{msg_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return any(
        candidate.startswith("v1,")
        and hmac.compare_digest(candidate.removeprefix("v1,"), expected)
        for candidate in signatures.split(" ")
    )


def _verify_terra(secret: str, headers: Mapping[str, str], body: bytes) -> bool:
    """Terra signs in Stripe form: "t=<unix>,v1=<hex>[,v1=<hex>...]" over
    "{timestamp}.{raw_body}". Multiple v1 values are legal (rotation); any
    non-v1 prefix is ignored (downgrade protection)."""
    header = headers.get("terra-signature", "")
    if not header:
        return False
    parts = dict(
        part.split("=", 1) for part in header.split(",") if "=" in part
    )
    timestamp = parts.get("t", "")
    try:
        if abs(time.time() - int(timestamp)) > SKEW_TOLERANCE_S:
            return False
    except ValueError:
        return False
    signed = f"{timestamp}.".encode() + body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return any(
        hmac.compare_digest(value, expected)
        for part in header.split(",")
        if "=" in part
        for key, value in [part.split("=", 1)]
        if key == "v1"
    )


def _verify_mock(secret: str, headers: Mapping[str, str], body: bytes) -> bool:
    """The demo connector has no signature by design. Its deliveries are
    accepted — and everything it produces is structurally non-qualifying for
    RTM (qualifies_for_rtm stays False at normalize), so an unsigned demo
    payload can never move a billing number."""
    return True


@dataclass(frozen=True)
class SignatureScheme:
    verify: Callable[[str, Mapping[str, str], bytes], bool]
    secret: Callable[[], str]  # read at request time so tests can monkeypatch
    requires_secret: bool = True


SIGNATURE_SCHEMES: dict[SourceProvider, SignatureScheme] = {
    SourceProvider.JUNCTION: SignatureScheme(
        _verify_svix, lambda: settings.junction_webhook_secret
    ),
    SourceProvider.TERRA: SignatureScheme(
        _verify_terra, lambda: settings.terra_signing_secret
    ),
    SourceProvider.MOCK: SignatureScheme(
        _verify_mock, lambda: "", requires_secret=False
    ),
}


def verify_signature(provider: SourceProvider, headers: Mapping[str, str], body: bytes) -> bool:
    """Fail closed: no scheme for the provider, or a scheme whose secret is not
    configured, is a rejection — never a pass-through."""
    scheme = SIGNATURE_SCHEMES.get(provider)
    if scheme is None:
        return False
    secret = scheme.secret()
    if scheme.requires_secret and not secret:
        logger.error("No webhook signing secret configured for %s — rejecting", provider)
        return False
    return scheme.verify(secret, headers, body)


async def _raw_body(request: Request) -> bytes:
    """Reading the body is the one asynchronous step, so it is the only part
    that belongs on the event loop — the handler itself stays synchronous."""
    return await request.body()


@router.post("/webhooks/wearables/{provider}")
def ingest_webhook(
    provider: str,
    request: Request,
    body: bytes = Depends(_raw_body),
    db: Session = Depends(get_db),
) -> dict:
    """Synchronous like every other route, and deliberately so: normalize,
    upsert and run_patient are blocking SQLAlchemy and pandas work, and FastAPI
    only moves plain `def` handlers to the threadpool. As a coroutine this
    handler held the event loop for the whole pipeline."""
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

    headers = {k.lower(): v for k, v in request.headers.items()}
    signature_valid = verify_signature(key, headers, body)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Body is not valid JSON")

    event = WebhookEvent(provider=provider, signature_valid=signature_valid, payload=payload)
    db.add(event)
    db.commit()

    if not signature_valid:
        event.status = "rejected"
        event.error = "signature verification failed"
        db.commit()
        raise HTTPException(status_code=401, detail="Signature verification failed")

    try:
        observations = info.connector.normalize(payload)
        # Validate BEFORE ingesting — otherwise a payload naming an unknown
        # patient would commit orphaned observation rows and then crash the
        # recompute loop. (Real connectors must resolve patients from the
        # (provider, provider_user_id) connection mapping, never trust ids in
        # the body — wired in with the connections table.)
        patient_ids = {o.patient_id for o in observations}
        known = set(db.scalars(select(Patient.id).where(Patient.id.in_(patient_ids))).all())
        unknown = patient_ids - known
        if unknown:
            raise ValueError(f"Unknown patient(s): {', '.join(sorted(unknown))}")
        ingested, updated, duplicates = ingest_observations(db, observations)
    except (ValueError, KeyError) as e:
        event.status = "failed"
        event.error = str(e)
        db.commit()
        raise HTTPException(status_code=422, detail=f"Payload rejected: {e}")

    event.status = "processed"
    event.processed_at = datetime.now()
    db.commit()

    # Restatements change already-scored days, so a batch that only *updated*
    # rows still invalidates the affected assessments.
    if ingested or updated:
        from app.engine.pipeline import run_patient

        for patient_id in patient_ids:
            run_patient(db, patient_id)

    return {
        "accepted": True,
        "ingested": ingested,
        "updated": updated,
        "duplicates": duplicates,
    }
