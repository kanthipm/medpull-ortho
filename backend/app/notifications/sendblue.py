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
import re
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
# Last failure of any kind, so an operator reading /api/health can see that
# texting is failing even when the cause is one recipient rather than the
# account. Silence is not evidence of health.
_last_failure: str | None = None

# Sendblue's own wording, and what an operator has to do about it. The reason
# alone reads as a dead end ("must be verified" — by whom, how?), and it is
# the one thing standing between a configured deployment and a delivered text.
_HINTS: tuple[tuple[str, str], ...] = (
    (
        "must be verified",
        "This number is not a verified Sendblue contact. Have them text {sender} once, "
        "or verify it in the Sendblue dashboard.",
    ),
    (
        "no contact found",
        "This number is not a Sendblue contact yet. Have them text {sender} once, "
        "or add it in the Sendblue dashboard.",
    ),
    (
        "phone number is not defined",
        "SENDBLUE_FROM_NUMBER ({sender}) is not a number this Sendblue account owns. "
        "Set it to the account's sending number and redeploy.",
    ),
    (
        "cannot send messages to self",
        "This number is the account's own sending number ({sender}), so Sendblue "
        "refuses it. Use a different number for this patient.",
    ),
    (
        "from_number",
        "Sendblue requires a sending number: set SENDBLUE_FROM_NUMBER and redeploy.",
    ),
)


def _hint_for(reason: str) -> str:
    lowered = reason.lower()
    sender = settings.sendblue_from_number or "the account's Sendblue number"
    for marker, hint in _HINTS:
        if marker in lowered:
            return hint.format(sender=sender)
    return ""


def _note_fault(reason: str) -> None:
    global _last_config_fault, _last_failure
    _last_failure = reason
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
        "last_failure": _last_failure,
        "hint": _hint_for(_last_failure) if _last_failure else None,
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
    "Your MedPull recovery check-in is ready."
)


# --- composition: attribution, the tappable link, and name redaction ---------
#
# Three rules every outbound patient text obeys, applied in one place so a new
# send path cannot quietly opt out of them.
#
# 1. Attribution. A message the copilot wrote on its own carries no tag — that
#    is the default and the patient already knows they are talking to an app.
#    A message a clinician wrote, approved or triggered is tagged with their
#    name, because "your surgeon says this" and "the app says this" are not
#    the same claim and the patient must be able to tell them apart.
# 2. No name. Sendblue, the carrier and anyone reading the lock screen see a
#    phone number and a sentence, never who the patient is. The app greets
#    them by name behind their session; a text never does.
# 3. One tappable link, labelled, on its own line, so iMessage renders it as a
#    link preview rather than burying it mid-sentence.

CARE_TEAM_TAG = "{name} (your care team)"


def clinician_tag(member: CareTeamMember | None) -> str:
    """The attribution prefix for a clinician-sanctioned text, or "" for the
    copilot's own words. Names already carry their credential ("Dr. Chen",
    "Maya Torres, RN"), so the role is not repeated."""
    if member is None or not (member.name or "").strip():
        return ""
    return CARE_TEAM_TAG.format(name=member.name.strip())


def redact_name(content: str, patient_name: str | None) -> str:
    """Take the patient's own name back out of an outbound text.

    The templates never add one, but a clinician typing in the console and a
    model writing a reply both reach for "Hi Marcus" without thinking, and
    that is the one thing these texts must not carry. Matches the full name
    and each part of it on a word boundary, case-insensitively, and repairs
    the punctuation the removal leaves behind ("Hi , how" -> "Hi, how").
    """
    if not content or not patient_name:
        return content
    parts = [p for p in re.split(r"\s+", patient_name.strip()) if len(p) > 2]
    candidates = sorted({patient_name.strip(), *parts}, key=len, reverse=True)
    out = content
    for candidate in candidates:
        out = re.sub(rf"\b{re.escape(candidate)}\b", "", out, flags=re.IGNORECASE)
    # Repair what the cut leaves behind: "Hi , how" -> "Hi, how", a line that
    # now opens on the dash that followed the name, and a sentence whose first
    # word lost its capital because the name was carrying it.
    out = re.sub(r"[ \t]+([,.!?;:])", r"\1", out)
    out = re.sub(r"(?m)^[ \t]*[,–—-][ \t]*", "", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = out.strip()
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out


def compose(
    body: str,
    *,
    patient_name: str | None = None,
    member: CareTeamMember | None = None,
    link: str | None = None,
    link_label: str = "Open in MedPull",
) -> str:
    """One outbound text: attribution, then the message, then the link.

    ``member`` set means a clinician stands behind this message and it is
    tagged with their name; left unset it is the copilot's own words and
    carries no tag, which is the default state of every automated text.
    """
    text = redact_name((body or "").strip(), patient_name)
    tag = clinician_tag(member)
    if tag:
        text = f"{tag}: {text}" if text else tag
    if link:
        text = f"{text}\n\n{link_label}: {link}" if text else f"{link_label}: {link}"
    return text


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
        hint = _hint_for(reason) if reason else ""
        return CheckinSendResult(
            sent=False,
            detail=(f"Sendblue answered {exc.response.status_code}"
                    + (f": {reason}" if reason else "")
                    + (f" {hint}" if hint else "")),
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
        hint = _hint_for(reason)
        return CheckinSendResult(
            sent=False,
            detail=reason + (f" {hint}" if hint else ""),
            status_code=response.status_code,
            config_fault=any(m in reason.lower() for m in _CONFIG_FAULTS),
        )
    global _last_failure
    _last_failure = None  # a delivered message clears the banner
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


def send_checkin_message(
    phone_number: str, checkin_url: str, *, member: CareTeamMember | None = None
) -> CheckinSendResult:
    """Text a patient their check-in link. With either key unset, sends nothing.

    ``member`` tags the text when a clinician asked for this check-in; left
    unset it is the copilot's routine invitation and carries no tag.
    """
    return send_sms(
        phone_number,
        compose(CHECKIN_TEMPLATE, member=member, link=checkin_url,
                link_label="Start your check-in"),
    )


# Task invitations carry the title only — no name, no clinical detail. "1" is
# the reply the inbound webhook treats as "walk me through it by text".
TASK_TEMPLATE = (
    "A new task is ready — {title}.\n"
    "Or reply 1 to do it right here by text."
)

VERIFICATION_TEMPLATE = "Your MedPull verification code is {code}. It expires in 10 minutes."


# The daily check-in a clinician started from the console.
#
# Two shapes, because a patient with the app and a patient without one are
# being asked to do two different things. Somebody who has never enrolled
# needs the tokenized web page, so their text carries the link. Somebody who
# has the app already holds the check-in behind their own session, and a
# second copy of it on a public URL is a worse answer to the same question —
# so their text carries no link at all and simply tells them it is waiting.
# The tap they need is the button on the message in the app, which is a row
# in their thread rather than anything a carrier can render.
CHECKIN_TASK_TEMPLATE = "Time for your daily check-in — it takes about a minute."
CHECKIN_IN_APP_TEMPLATE = (
    "Time for your daily check-in — it takes about a minute. "
    "It's waiting for you in MedPull."
)


def daily_checkin_text(link: str | None, member: CareTeamMember | None = None) -> str:
    """The exact words of the check-in text, composed once so the row stored
    on the patient's thread and the bytes handed to Sendblue cannot drift."""
    return compose(
        CHECKIN_TASK_TEMPLATE if link else CHECKIN_IN_APP_TEMPLATE,
        member=member,
        link=link,
        link_label="Start your check-in",
    )


def send_daily_checkin_message(
    phone_number: str,
    *,
    link: str | None = None,
    member: CareTeamMember | None = None,
) -> CheckinSendResult:
    """Text a patient that their daily check-in is ready.

    ``link`` is the tokenized web page for a patient without the app, and
    None for one who has it. ``member`` tags the text when a clinician
    pressed the button, which is the usual case for this one.
    """
    return send_sms(phone_number, daily_checkin_text(link, member))


# Onboarding texts. Like every other patient text these carry no name and no
# clinical detail. Both are placeholders until the product copy is settled.
WELCOME_TEMPLATE = (
    "Welcome to MedPull. Your care team can now see your check-ins and send you "
    "tasks in the app. Reply to this number any time to reach them."
)
INVITE_TEMPLATE = (
    "Your care team set you up on MedPull to follow your recovery."
)


def send_welcome_message(phone_number: str) -> CheckinSendResult:
    """The first text a patient gets after they finish onboarding in the app."""
    return send_sms(phone_number, compose(WELCOME_TEMPLATE))


def send_invite_message(
    phone_number: str, *, member: CareTeamMember | None = None
) -> CheckinSendResult:
    """Text a patient a clinician just added, pointing them at the app.

    A clinician did this by hand, so the invitation says who — an unexplained
    text about a medical app is exactly the kind a patient ignores.
    """
    return send_sms(
        phone_number,
        compose(INVITE_TEMPLATE, member=member, link=settings.app_download_url,
                link_label="Get the app"),
    )


def send_task_message(
    phone_number: str,
    title: str,
    task_url: str,
    *,
    member: CareTeamMember | None = None,
    patient_name: str | None = None,
) -> CheckinSendResult:
    """Text a patient about a task. Tagged when a clinician assigned it, which
    is the usual case; an automatically scheduled task carries no tag."""
    return send_sms(
        phone_number,
        compose(
            TASK_TEMPLATE.format(title=title[:80]),
            patient_name=patient_name,
            member=member,
            link=task_url,
            link_label="Open the task",
        ),
    )


def send_care_team_message(
    phone_number: str,
    text: str,
    *,
    member: CareTeamMember | None = None,
    patient_name: str | None = None,
    link: str | None = None,
    link_label: str = "Get the app",
) -> CheckinSendResult:
    """A message written in the console, or by the copilot on the thread.

    The one send path where the body is free text somebody typed, so it is
    also the one most likely to carry the patient's name — ``compose`` takes
    it back out.
    """
    return send_sms(
        phone_number,
        compose(text, patient_name=patient_name, member=member, link=link,
                link_label=link_label),
    )


def send_verification_code(phone_number: str, code: str) -> CheckinSendResult:
    return send_sms(phone_number, VERIFICATION_TEMPLATE.format(code=code))
