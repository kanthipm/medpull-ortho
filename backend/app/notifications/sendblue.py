"""Sendblue SMS/iMessage delivery for care-team notifications.

Deliberately thin, like ``connectors/junction_client.py``: this module knows
the host, the auth headers, and the one endpoint it uses. Who gets notified
and through which channels is decided in ``notifications/service.py``.

Contract (Sendblue REST API):

* ``POST https://api.sendblue.co/api/send-message`` with the
  ``sb-api-key-id`` / ``sb-api-secret-key`` headers and a JSON body of
  ``{"number": <E.164>, "content": <text>}``. A 2xx answer means Sendblue
  accepted the message for delivery (its own status lifecycle continues via
  optional callbacks the app does not register).
* Recipients are resolved at send time: ``Notification.recipient_id`` names a
  ``CareTeamMember`` and the phone lives on that row — never in code, so a
  number can't leak into the public repo.

With the keys unset the channel behaves exactly like the old stub (logs the
intent, answers SENT_STUB), which is also what pins the test suite's baseline:
``conftest.py`` blanks the keys so a developer's ``.env`` cannot send a real
text from a test run.

One attempt, bounded socket timeout, no retries: on Lambda a notification is
written while the request holds the S3 write lock (25 s TTL — see
``app/aws/config.py``), and a retrying send would spend budget the ingest and
recompute behind it still need. A failed or timed-out call records FAILED and
moves on; the in-app copy of the same alert is the durable fallback.
"""

from __future__ import annotations

import logging

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

        payload = {
            "number": phone,
            "content": f"{notification.title}\n{notification.body}",
        }
        if settings.sendblue_from_number:
            payload["from_number"] = settings.sendblue_from_number

        try:
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
        except httpx.HTTPError as exc:
            logger.warning("Sendblue send to recipient %s failed: %s",
                           notification.recipient_id, exc)
            return NotificationStatus.FAILED

        return NotificationStatus.SENT
