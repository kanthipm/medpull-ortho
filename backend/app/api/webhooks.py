"""Wearable webhook ingestion — the seam where real providers plug in.

Flow: verify the signature against the RAW request bytes -> persist the event
-> ask the connector which patient the delivery belongs to -> hand it to the
connector -> idempotent upsert -> recompute the affected patient.

Signature verification is a per-provider strategy table, and it fails closed:
an unverifiable delivery is recorded and rejected before a single observation
row is written. Verification MUST run on the raw bytes — re-serializing parsed
JSON does not reproduce the original body (key order, whitespace, unicode
escaping all differ), which makes HMAC over a dict mathematically meaningless.

Patient resolution is the connector's, never the body's. The demo connector's
body *is* its identity (the endpoint is unsigned and for developers); the
Junction connector resolves the delivery's user id through the connections
table and answers None for a user it never issued, which is recorded as
``ignored`` and answered 202 — a 4xx would only make Junction retry a delivery
that can never map to anyone.
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
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.connectors.base import PatientContext
from app.connectors.ingest import ingest_in_batches, ingest_observations, partition_by_window
from app.connectors.junction_client import JunctionError
from app.connectors.registry import get_provider_info
from app.database import get_db
from app.models.enums import SourceProvider
from app.models.observation import WebhookEvent
from app.models.patient import Patient

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])

SKEW_TOLERANCE_S = 300  # accept timestamps ±5 minutes from server receipt
# The largest legitimate delivery is a sleep summary with its stream, well
# under 100 KB; the ingest ceiling bounds rows, this bounds bytes, and both
# apply before anything is parsed or stored.
MAX_BODY_BYTES = 1_000_000


def _safe_compare(candidate: str, expected: str) -> bool:
    """hmac.compare_digest refuses non-ASCII str operands with a TypeError.
    Header bytes reach here decoded as latin-1, so a hostile byte in a
    signature header must read as "does not match", not as a 500."""
    try:
        return hmac.compare_digest(candidate.encode("latin-1"), expected.encode("ascii"))
    except (TypeError, UnicodeEncodeError, UnicodeDecodeError):
        return False


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
        candidate.startswith("v1,") and _safe_compare(candidate.removeprefix("v1,"), expected)
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
        _safe_compare(value, expected)
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


def _fail(db: Session, event: WebhookEvent, status: str, error: str) -> None:
    event.status = status
    event.error = error
    db.commit()


@router.post("/webhooks/wearables/{provider}")
def ingest_webhook(
    provider: str,
    request: Request,
    body: bytes = Depends(_raw_body),
    db: Session = Depends(get_db),
):
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
    connector = info.connector

    if len(body) > MAX_BODY_BYTES:
        # Refused before verification, parsing or storage: a body this size is
        # not a delivery, and nothing about it deserves a row.
        raise HTTPException(status_code=413, detail="Body exceeds the webhook size limit")

    headers = {k.lower(): v for k, v in request.headers.items()}
    signature_valid = verify_signature(key, headers, body)

    if not signature_valid:
        # Recorded, but not stored: an unverified body is untrusted bytes from
        # anyone who knows the URL, so the row keeps what an operator needs to
        # debug a misconfigured secret (when, how big, which Svix message) and
        # none of the content, which would otherwise fill the table and the
        # console's recent-deliveries list with whatever the sender chose.
        event = WebhookEvent(
            provider=provider,
            signature_valid=False,
            payload={
                "rejected": True,
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "svix_id": headers.get("svix-id"),
            },
        )
        db.add(event)
        db.commit()
        _fail(db, event, "rejected", "signature verification failed")
        raise HTTPException(status_code=401, detail="Signature verification failed")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Body is not valid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Body must be a JSON object")

    event = WebhookEvent(provider=provider, signature_valid=True, payload=payload)
    db.add(event)
    db.commit()

    # Who is this for? The connector decides, never the body (see module doc).
    try:
        patient_id = connector.resolve_patient(db, payload)
    except (ValueError, KeyError) as e:
        _fail(db, event, "failed", str(e))
        raise HTTPException(status_code=422, detail=f"Payload rejected: {e}")
    if patient_id is None:
        _fail(db, event, "ignored", "no connection for this user")
        return JSONResponse(
            status_code=202,
            content={
                "accepted": False,
                "ignored": True,
                "reason": "unmapped_user",
                "ingested": 0,
                "updated": 0,
                "duplicates": 0,
            },
        )
    patient = db.get(Patient, patient_id)
    if patient is None:
        _fail(db, event, "failed", f"Unknown patient(s): {patient_id}")
        raise HTTPException(status_code=422, detail=f"Payload rejected: Unknown patient(s): {patient_id}")

    skipped = 0
    try:
        delivery = connector.receive(db, payload, PatientContext(patient.id, patient.timezone))
        observations = delivery.observations
        # A connector may only ever write under the patient it was resolved to.
        foreign = {o.patient_id for o in observations} - {patient.id}
        if foreign:
            raise ValueError(
                f"Connector emitted rows for {', '.join(sorted(foreign))} while "
                f"processing a delivery for {patient.id}"
            )
        if observations and connector.drops_out_of_window_rows:
            observations, outside = partition_by_window(db, observations)
            skipped = len(outside)
            ingested, updated, duplicates = ingest_in_batches(db, observations)
        else:
            ingested, updated, duplicates = ingest_observations(db, observations)
    except JunctionError as e:
        # The delivery itself is fine; a pull it triggered could not complete.
        # A 5xx makes the aggregator retry later, which is the right thing for
        # a transient outage on its side.
        _fail(db, event, "failed", f"aggregator call failed: {e}")
        raise HTTPException(status_code=502, detail=f"Aggregator call failed: {e}")
    except (ValueError, KeyError) as e:
        _fail(db, event, "failed", str(e))
        raise HTTPException(status_code=422, detail=f"Payload rejected: {e}")

    event.status = "processed"
    event.processed_at = datetime.now()
    db.commit()
    if skipped or delivery.note:
        logger.info(
            "Webhook %s/%s (%s): %s%s",
            provider, event.id, delivery.kind,
            f"skipped {skipped} out-of-window row(s); " if skipped else "",
            delivery.note or "",
        )

    # Restatements change already-scored days, so a batch that only *updated*
    # rows still invalidates the affected assessments.
    if ingested or updated:
        from app.engine.pipeline import run_patient

        run_patient(db, patient.id)

    return {
        "accepted": True,
        "kind": delivery.kind,
        "ingested": ingested,
        "updated": updated,
        "duplicates": duplicates,
        "skipped_out_of_window": skipped,
        "note": delivery.note,
    }
