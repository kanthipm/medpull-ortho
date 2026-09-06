"""Sendblue SMS/iMessage delivery — care-team alerts (``SendblueChannel``) and
patient check-in invitations (``send_checkin_message``). Outbound only.

Phone numbers live in the DB or the environment, never in code. With the keys
unset nothing sends. One bounded attempt, no retries: on Lambda a send runs
inside the 25 s S3 write-lock TTL, and the in-app alert is the durable fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import settings
from app.database import SessionLocal
from app.models.enums import NotificationStatus
from app.models.notification import Notification
from app.models.patient import CareTeamMember

logger = logging.getLogger(__name__)

SEND_URL = "https://api.sendblue.co/api/send-message"
TIMEOUT_S = 5.0


def _e164(phone: str) -> str | None:
    """Normalize a stored phone to E.164, or None if it can't be one.

    Rows are operator-entered, so accept the common shapes: bare 10-digit US
    numbers, 11 digits with a leading 1, or an already-prefixed +number.
    """
    digits = "".join(c for c in phone if c.isdigit())
    if phone.strip().startswith("+") and len(digits) >= 8:
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def _recipient_phone(recipient_id: str | None) -> str | None:
    if recipient_id is None:
        return None
    # A fresh short-lived session: send() runs before the caller's session has
    # committed the Notification row, and this lookup must not entangle itself
    # with that transaction.
    with SessionLocal() as db:
        member = db.get(CareTeamMember, recipient_id)
    if member is None or not member.phone:
        return None
    return _e164(member.phone)


class SendblueChannel:
    def send(self, notification: Notification) -> NotificationStatus:
        if not (settings.sendblue_api_key and settings.sendblue_api_secret):
            logger.info(
                "SMS stub -> %s: %s", notification.recipient_id, notification.title
            )
            return NotificationStatus.SENT_STUB

        phone = _recipient_phone(notification.recipient_id)
        if phone is None:
            logger.warning(
                "SMS not sent — recipient %s has no usable phone number",
                notification.recipient_id,
            )
            return NotificationStatus.FAILED

        try:
            _post_message(phone, f"{notification.title}\n{notification.body}")
        except httpx.HTTPError as exc:
            logger.warning("Sendblue send to recipient %s failed: %s",
                           notification.recipient_id, exc)
            return NotificationStatus.FAILED

        return NotificationStatus.SENT


def _post_message(phone: str, content: str) -> httpx.Response:
    """One bounded attempt; raises httpx.HTTPError on any failure."""
    payload = {"number": phone, "content": content}
    if settings.sendblue_from_number:
        payload["from_number"] = settings.sendblue_from_number
    response = httpx.post(
        SEND_URL,
        headers={
            "sb-api-key-id": settings.sendblue_api_key,
            "sb-api-secret-key": settings.sendblue_api_secret,
        },
        json=payload,
        timeout=TIMEOUT_S,
    )
    response.raise_for_status()
    return response


CHECKIN_TEMPLATE = (
    "Hi {patient_name}, your MedPull recovery check-in is ready. "
    "Tap here to begin: {checkin_url}"
)


@dataclass(frozen=True)
class CheckinSendResult:
    sent: bool
    detail: str
    status_code: int | None = None


def send_checkin_message(
    phone_number: str, patient_name: str, checkin_url: str
) -> CheckinSendResult:
    """Text a patient their check-in link. With either key unset, sends nothing."""
    if not (settings.sendblue_api_key and settings.sendblue_api_secret):
        return CheckinSendResult(sent=False, detail="Sendblue keys not configured")

    phone = _e164(phone_number)
    if phone is None:
        return CheckinSendResult(
            sent=False, detail=f"not a usable phone number: {phone_number!r}"
        )

    content = CHECKIN_TEMPLATE.format(patient_name=patient_name, checkin_url=checkin_url)
    try:
        _post_message(phone, content)
    except httpx.HTTPStatusError as exc:
        logger.warning("Sendblue check-in send to %s failed: %s", phone, exc)
        return CheckinSendResult(
            sent=False,
            detail=f"Sendblue answered {exc.response.status_code}",
            status_code=exc.response.status_code,
        )
    except httpx.HTTPError as exc:
        logger.warning("Sendblue check-in send to %s failed: %s", phone, exc)
        return CheckinSendResult(sent=False, detail=f"request failed: {exc}")

    return CheckinSendResult(sent=True, detail="sent")
