"""Inbound Sendblue texts.

Sendblue posts every message on the account's numbers here — inbound patient
texts and status callbacks for our own outbound ones. Sendblue does not sign
the body; it echoes the account's configured signing secret in an
``sb-signing-secret`` header. The route accepts that header, or the same
secret as the URL's last path segment (for an account with no header secret
set), and nothing else; with no secret configured it answers 503 and no
inbound text is processed. The number is matched to a patient through
``patients.phone`` and nothing else: a text from an unknown number is logged
and dropped, never stored.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.tasks.service import handle_inbound_sms

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])


def _check_secret(request: Request, path_secret: str | None) -> None:
    configured = settings.sendblue_webhook_secret
    if not configured:
        raise HTTPException(
            status_code=503,
            detail="Inbound SMS is not configured: set SENDBLUE_WEBHOOK_SECRET and register "
            "/api/webhooks/sendblue at Sendblue with that signing secret.",
        )
    header = request.headers.get("sb-signing-secret", "")
    for candidate in (header, path_secret or ""):
        if candidate and hmac.compare_digest(candidate.encode(), configured.encode()):
            return
    raise HTTPException(status_code=401, detail="Bad webhook secret")


@router.post("/webhooks/sendblue")
def inbound_sms_header(
    request: Request,
    body: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    """The URL to register at Sendblue when the account has a signing secret."""
    _check_secret(request, None)
    return _handle(request, body, db)


@router.post("/webhooks/sendblue/{secret}")
def inbound_sms(
    secret: str,
    request: Request,
    body: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    _check_secret(request, secret)
    return _handle(request, body, db)


def _handle(request: Request, body: dict[str, Any], db: Session) -> dict:

    if body.get("is_outbound") is True:
        # A delivery status for something we sent. Nothing to do yet.
        return {"handled": False, "reason": "outbound_status"}
    from_number = body.get("from_number") or body.get("number")
    content = body.get("content") or ""
    if not isinstance(from_number, str) or not isinstance(content, str) or not content.strip():
        return {"handled": False, "reason": "empty"}

    base = settings.checkin_base_url or str(request.base_url).rstrip("/")
    outcome = handle_inbound_sms(db, from_number, content, base_url=base)
    return {
        "handled": outcome.handled,
        "kind": outcome.kind,
        "replied": bool(outcome.delivery and outcome.delivery.sent),
        "matched_patient": outcome.patient_id is not None,
    }
