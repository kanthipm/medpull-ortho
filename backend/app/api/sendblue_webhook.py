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

from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.models.mobile import Message
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


# Sendblue's lifecycle statuses for a message we sent. Only the terminal
# ones move the thread line: QUEUED/SENT stay "sent", ERROR is "failed", and
# DELIVERED/READ mean the phone has it.
_DELIVERED = {"DELIVERED", "READ"}
_FAILED = {"ERROR", "UNDELIVERED", "FAILED"}


def _outbound_status(body: dict[str, Any], db: Session) -> dict:
    handle = body.get("message_handle")
    status = str(body.get("status") or "").upper()
    if not isinstance(handle, str) or not handle:
        return {"handled": False, "reason": "outbound_status", "status": status}
    message = db.scalar(
        select(Message).where(Message.external_handle == handle, Message.sender != "patient")
    )
    if message is None:
        return {"handled": False, "reason": "outbound_status", "status": status}
    new = "delivered" if status in _DELIVERED else "failed" if status in _FAILED else None
    if new is None or message.delivery_status == new:
        return {"handled": False, "reason": "outbound_status", "status": status}
    if new == "failed":
        logger.warning("Sendblue reports message %s failed: %s %s", handle,
                       body.get("error_code"), body.get("error_message"))
    message.delivery_status = new
    db.commit()
    return {"handled": True, "reason": "outbound_status", "status": status,
            "message_id": message.id}


# Sendblue documents a single ``media_url`` on an inbound message; the list
# forms are accepted because a provider that adds one should not become a
# silently dropped photo.
_MEDIA_KEYS = ("media_url", "media_urls", "mediaURL", "mediaURLs", "media")


def _media_urls(body: dict[str, Any]) -> list[str]:
    """Every attachment link in an inbound payload, whatever shape it took."""
    found: list[str] = []
    for key in _MEDIA_KEYS:
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            found.append(value.strip())
        elif isinstance(value, list):
            found.extend(v.strip() for v in value if isinstance(v, str) and v.strip())
    # Keep the order, drop repeats: several keys often carry the same link.
    return list(dict.fromkeys(found))[:4]


def _handle(request: Request, body: dict[str, Any], db: Session) -> dict:
    if body.get("is_outbound") is True:
        return _outbound_status(body, db)
    from_number = body.get("from_number") or body.get("number")
    content = body.get("content") or ""
    media = _media_urls(body)
    if not isinstance(from_number, str) or not isinstance(content, str):
        return {"handled": False, "reason": "empty"}
    # A photograph with no caption is a message. Requiring text dropped it
    # before any handler saw it: no row, no notification, nobody told.
    if not content.strip() and not media:
        return {"handled": False, "reason": "empty"}
    handle = body.get("message_handle")
    if not isinstance(handle, str) or not handle:
        handle = None

    base = settings.checkin_base_url or str(request.base_url).rstrip("/")
    outcome = handle_inbound_sms(db, from_number, content, base_url=base, message_handle=handle,
                                 media_urls=media)
    return {
        "handled": outcome.handled,
        "kind": outcome.kind,
        "replied": bool(outcome.delivery and outcome.delivery.sent),
        "matched_patient": outcome.patient_id is not None,
        "attachments": outcome.attachments,
    }
