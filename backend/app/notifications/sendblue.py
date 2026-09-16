"""Sendblue SMS/iMessage delivery — care-team alerts (``SendblueChannel``),
patient check-in invitations (``send_checkin_message``) and every other text
the patient app's backend sends a patient (``send_sms``: task invitations,
verification codes, conversation replies, care-team messages). Inbound texts
arrive through ``api/sendblue_webhook.py``.

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

# Sendblue rejects a send for two quite different reasons and the product has
# to tell them apart. A DELIVERY fault is about this recipient (a landline, a
# number that cannot receive). A CONFIGURATION fault is about us: the account
# has no sending number, or the one configured is not one Sendblue issued, in
# which case NOTHING will send to anybody until an operator fixes the account.
# Silence looked identical either way, which is how a deployment ran for a day
# believing it could text.
_CONFIG_FAULTS = (
    "phone number is not defined",      # from_number is not provisioned on the account
    'missing required parameter: "from_number"',
    "missing required parameter: from_number",
    "not authorized",
    "unauthorized",
    "invalid api key",
    "plan",
)

# Last configuration fault seen in this process, for the health endpoint.
# Per-instance and deliberately not persisted: it is re-learned on the next
# send, and a stale copy must never outlive the fix.
_last_config_fault: str | None = None


def _note_fault(reason: str) -> None:
    global _last_config_fault
    lowered = reason.lower()
    if any(marker in lowered for marker in _CONFIG_FAULTS):
        _last_config_fault = reason
        logger.error(
            "Sendblue cannot send at all: %s. SENDBLUE_FROM_NUMBER=%r must be a number "
            "Sendblue issued to this account.", reason, settings.sendblue_from_number,
        )


def status() -> dict:
    """What the deployment can actually do about texting, for /api/health and
    the integrations screen."""
    return {
        "configured": configured(),
        "from_number": settings.sendblue_from_number or None,
        "webhook_secret_set": bool(settings.sendblue_webhook_secret),
        # None until a send has been attempted in this process.
        "config_fault": _last_config_fault,
    }


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


# Deliberately carries no patient data: Sendblue sees a phone number, this
# sentence, and an opaque one-time URL. The page greets by name server-side.
CHECKIN_TEMPLATE = (
    "Your MedPull recovery check-in is ready. Tap here to begin: {checkin_url}"
)


@dataclass(frozen=True)
class CheckinSendResult:
    sent: bool
    detail: str
    status_code: int | None = None
    # Sendblue's id for the outbound message, when it answered with one.
    message_handle: str | None = None
    # True when the failure is about this deployment's Sendblue account rather
    # than about the recipient: nothing will send until it is fixed.
    config_fault: bool = False


def configured() -> bool:
    """Both keys present. Read per call: on Lambda they land from SSM after import."""
    return bool(settings.sendblue_api_key and settings.sendblue_api_secret)


def normalize_phone(phone_number: str) -> str | None:
    """Public spelling of the E.164 normalizer, for callers that store numbers."""
    return _e164(phone_number)


def send_sms(phone_number: str, content: str) -> CheckinSendResult:
    """Text a patient. With either key unset, sends nothing and says so.

    The one outbound primitive every patient-facing text goes through; the
    result is a value, never an exception, because a failed text must not
    fail the request that produced it — the task, message or code it
    carried is already stored and reachable in the app.
    """
    if not configured():
        return CheckinSendResult(sent=False, detail="Sendblue keys not configured")

    phone = _e164(phone_number)
    if phone is None:
        return CheckinSendResult(
            sent=False, detail=f"not a usable phone number: {phone_number!r}"
        )

    try:
        response = _post_message(phone, content)
    except httpx.HTTPStatusError as exc:
        reason = _error_reason(exc.response)
        logger.warning("Sendblue send to %s failed: %s %s", phone, exc, reason or "")
        if reason:
            _note_fault(reason)
        return CheckinSendResult(
            sent=False,
            detail=f"Sendblue answered {exc.response.status_code}"
            + (f": {reason}" if reason else ""),
            status_code=exc.response.status_code,
            config_fault=bool(reason) and any(
                m in reason.lower() for m in _CONFIG_FAULTS
            ),
        )
    except httpx.HTTPError as exc:
        logger.warning("Sendblue send to %s failed: %s", phone, exc)
        return CheckinSendResult(sent=False, detail=f"request failed: {exc}")

    handle: str | None = None
    body: dict | None = None
    try:
        parsed = response.json()
        body = parsed if isinstance(parsed, dict) else None
        if body and isinstance(body.get("message_handle"), str):
            handle = body["message_handle"]
    except (ValueError, AttributeError, TypeError):
        body = None  # no body, or not JSON: the send still happened

    # A 2xx is not proof: Sendblue echoes the message object with
    # "status": "ERROR" for a rejection it decided before queueing.
    if body and str(body.get("status", "")).upper() == "ERROR":
        reason = _error_reason(response) or "Sendblue rejected the message"
        _note_fault(reason)
        logger.warning("Sendblue rejected a send to %s: %s", phone, reason)
        return CheckinSendResult(
            sent=False,
            detail=reason,
            status_code=response.status_code,
            config_fault=any(m in reason.lower() for m in _CONFIG_FAULTS),
        )
    return CheckinSendResult(sent=True, detail="sent", message_handle=handle)


def _error_reason(response: httpx.Response) -> str:
    """Sendblue's own words for a refused send ("Cannot send messages to
    self", an unverified number...), so the console can show why rather
    than a bare status code. Empty when the body is not JSON or says nothing."""
    try:
        body = response.json()
    except (ValueError, AttributeError, TypeError):
        return ""
    if not isinstance(body, dict):
        return ""
    for key in ("message", "error_message", "error", "detail"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:160]
    return ""


def send_checkin_message(phone_number: str, checkin_url: str) -> CheckinSendResult:
    """Text a patient their check-in link. With either key unset, sends nothing."""
    return send_sms(phone_number, CHECKIN_TEMPLATE.format(checkin_url=checkin_url))


# Task invitations carry the title only — no name, no clinical detail. "1" is
# the reply the inbound webhook treats as "walk me through it by text".
TASK_TEMPLATE = (
    "MedPull: a new task is ready — {title}.\n"
    "Open it: {task_url}\n"
    "Or reply 1 to do it right here by text."
)

VERIFICATION_TEMPLATE = "Your MedPull verification code is {code}. It expires in 10 minutes."


# Onboarding texts. Like every other patient text these carry no name and no
# clinical detail. Both are placeholders until the product copy is settled.
WELCOME_TEMPLATE = (
    "Welcome to MedPull. Your care team can now see your check-ins and send you "
    "tasks in the app. Reply to this number any time to reach them."
)
INVITE_TEMPLATE = (
    "Your care team set you up on MedPull to follow your recovery. Get the app "
    "here to start: {app_url}"
)


def send_welcome_message(phone_number: str) -> CheckinSendResult:
    """The first text a patient gets after they finish onboarding in the app."""
    return send_sms(phone_number, WELCOME_TEMPLATE)


def send_invite_message(phone_number: str) -> CheckinSendResult:
    """Text a patient a clinician just added, pointing them at the app."""
    return send_sms(phone_number, INVITE_TEMPLATE.format(app_url=settings.app_download_url))


def send_task_message(phone_number: str, title: str, task_url: str) -> CheckinSendResult:
    return send_sms(phone_number, TASK_TEMPLATE.format(title=title[:80], task_url=task_url))


def send_verification_code(phone_number: str, code: str) -> CheckinSendResult:
    return send_sms(phone_number, VERIFICATION_TEMPLATE.format(code=code))
