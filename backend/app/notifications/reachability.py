"""Which numbers a text can reach — so no admin ever approves one by hand.

Sendblue's free shared-line plan refuses any recipient who has not texted
the line first: the send comes back "This contact must be verified before
sending messages to it", and the API offers no call that verifies a number
on our behalf. The person texting the line once is the only key. A paid plan
(or Twilio, Telnyx, ...) has no such rule.

This module is the one place that knows a number's state, and it learns it
instead of being told:

* **verified** — the person texted MedPull (the inbound webhook marks it), a
  text to them went through, or the provider's own verified-contact list
  says so. Persisted in ``verified_contacts`` by E.164 number, so a cold
  Lambda knows what a warm one learned.
* **unverified** — the provider's list says pending/absent, or a send was
  just refused for that reason. Cached in-process for a short while so a
  retry a few seconds later does not hammer the provider.
* **unknown** — nothing on file. The send is attempted and the answer learned
  from it; nothing here ever refuses to try.

The code paths that must decide *before* sending (a one-time code the app is
waiting on) call ``lookup``; every send path reports back through
``note_sent`` / ``note_refused`` via ``sendblue.send_sms``. All network calls
are bounded, optional and faked in the suite.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.mobile import VerifiedContact

logger = logging.getLogger(__name__)

API_BASE = "https://api.sendblue.co"
TIMEOUT_S = 4.0
# How long a provider answer (contact state, plan) is trusted before it is
# asked again. Short: the person is texting the line right now.
CONTACTS_TTL_S = 30.0
PLAN_TTL_S = 600.0
# A refusal is remembered this long so a retry tapped a moment later does not
# cost a second refused call — the webhook, not the retry, flips the state.
REFUSAL_TTL_S = 30.0

# The provider's words for "this recipient has not texted the line yet".
_REFUSAL_MARKERS = (
    "must be verified",
    "no contact found",
    "not a verified",
    "not verified",
    "unverified",
)

# Process-local memory. Deliberately not persisted: a cold start re-learns
# from the table and the provider, and a stale negative must never outlive
# the inbound text that cleared it.
_confirmed: dict[str, float] = {}      # phone -> when a text went through
_refused: dict[str, float] = {}        # phone -> when a send was refused
_contacts: dict[str, tuple[float, bool | None]] = {}  # phone -> (when, verified)
_line_for: dict[str, tuple[float, str | None]] = {}   # phone -> (when, the line to text)
_plan: tuple[float, str | None] | None = None


def reset_caches() -> None:
    """For tests, and for the health check after a configuration change."""
    global _plan
    _confirmed.clear()
    _refused.clear()
    _contacts.clear()
    _line_for.clear()
    _plan = None


# --- what we know ----------------------------------------------------------------


def is_verification_refusal(reason: str | None) -> bool:
    """Whether a send failed because the recipient has never texted the
    line, as opposed to a landline, a bad key or a broken account."""
    if not reason:
        return False
    lowered = reason.lower()
    return any(marker in lowered for marker in _REFUSAL_MARKERS)


def text_first_body() -> str:
    return (settings.sendblue_text_first_body or "Hi MedPull").strip() or "Hi MedPull"


def line_number(phone: str | None = None) -> str | None:
    """The number the person has to text: the line Sendblue named when the
    contact was registered, else the account's configured sending number."""
    if phone:
        cached = _line_for.get(phone)
        if cached and cached[1]:
            return cached[1]
    return settings.sendblue_from_number or None


def text_first_instructions(phone: str | None = None) -> dict[str, Any]:
    """The fields the apps turn into one tap: open Messages to ``text_to``
    with ``text_body`` pre-filled."""
    return {
        "text_first": True,
        "text_to": line_number(phone),
        "text_body": text_first_body(),
    }


def known_verified(db: Session, phone: str) -> bool:
    """Whether the table or this process already knows the number is reachable."""
    if phone in _confirmed:
        return True
    return db.get(VerifiedContact, phone) is not None


def mark_verified(db: Session, phone: str, *, source: str = "inbound") -> VerifiedContact:
    """Record that texts can reach ``phone``. Idempotent; the caller commits.

    An inbound text is the strongest evidence and refreshes ``last_inbound_at``
    on a row that already exists; a successful send or a contact-list answer
    only adds a row that was missing.
    """
    now = datetime.now()
    row = db.get(VerifiedContact, phone)
    if row is None:
        row = VerifiedContact(phone=phone, source=source, verified_at=now,
                              last_inbound_at=now if source == "inbound" else None)
        db.add(row)
    elif source == "inbound":
        row.last_inbound_at = now
    db.flush()
    _confirmed[phone] = time.monotonic()
    _refused.pop(phone, None)
    _contacts.pop(phone, None)
    return row


def note_sent(phone: str) -> None:
    """A text to ``phone`` went through: it is reachable (process memory; the
    next code-path with a session persists it)."""
    _confirmed[phone] = time.monotonic()
    _refused.pop(phone, None)


def note_refused(phone: str) -> None:
    """The provider refused ``phone`` for not having texted the line."""
    _refused[phone] = time.monotonic()
    _confirmed.pop(phone, None)


def _recently_refused(phone: str) -> bool:
    when = _refused.get(phone)
    return when is not None and time.monotonic() - when < REFUSAL_TTL_S


def lookup(db: Session, phone: str) -> str:
    """``verified`` | ``unverified`` | ``unknown`` for an E.164 number.

    Order: what we already know (table, confirmed sends, a fresh refusal),
    then — only when the account's rules make the question meaningful — the
    provider's own verified-contact list. A provider error is ``unknown``,
    which callers treat as "try, and learn".
    """
    if known_verified(db, phone):
        return "verified"
    if _recently_refused(phone):
        return "unverified"
    mode = (settings.sendblue_verified_contacts_only or "auto").strip().lower()
    if mode in ("false", "0", "no", "never"):
        return "unknown"
    if mode not in ("true", "1", "yes", "always"):
        # auto: a paid plan has no verified-contact rule, so its unknown
        # numbers are simply unknown. Only a free account is asked further.
        plan = account_plan()
        if plan is not None and not _plan_requires_verified_contacts(plan):
            return "unknown"
    verified = contact_verified(phone)
    if verified is True:
        mark_verified(db, phone, source="contacts")
        return "verified"
    if verified is False:
        return "unverified"
    return "unknown"


def _plan_requires_verified_contacts(plan: str) -> bool:
    lowered = plan.lower()
    return "free" in lowered or "sandbox" in lowered or "trial" in lowered


# --- the provider ------------------------------------------------------------------


def _configured() -> bool:
    return bool(settings.sendblue_api_key and settings.sendblue_api_secret)


def _request(method: str, path: str, json: dict | None = None) -> httpx.Response:
    """One bounded call to Sendblue's account API; raises httpx.HTTPError.
    The single seam the suite fakes."""
    return httpx.request(
        method,
        f"{API_BASE}{path}",
        headers={
            "sb-api-key-id": settings.sendblue_api_key,
            "sb-api-secret-key": settings.sendblue_api_secret,
        },
        json=json,
        timeout=TIMEOUT_S,
    )


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except (ValueError, AttributeError, TypeError):
        return None


def _dig(body: Any, *keys: str) -> Any:
    """The first of ``keys`` found at the top level or one level down under
    the usual envelopes (``data``, ``account``, ``contact``)."""
    if not isinstance(body, dict):
        return None
    for key in keys:
        if key in body:
            return body[key]
    for envelope in ("data", "account", "contact", "result"):
        inner = body.get(envelope)
        if isinstance(inner, dict):
            found = _dig(inner, *keys)
            if found is not None:
                return found
    return None


def _contact_verified_flag(contact: Any) -> bool | None:
    """Read a contact object's verification state, whatever shape it took.

    v3 ``verified-contacts`` carries ``verified`` (bool) and
    ``verification_status`` (pending | verified). The older contact list
    carries neither, in which case being listed is the best we know.
    """
    if not isinstance(contact, dict):
        return None
    flag = contact.get("verified")
    if isinstance(flag, bool):
        return flag
    status = contact.get("verification_status") or contact.get("status")
    if isinstance(status, str):
        return status.strip().lower() == "verified"
    return True


def _contact_number(contact: Any) -> str | None:
    if not isinstance(contact, dict):
        return None
    for key in ("phone_number", "number", "phone", "phoneNumber"):
        value = contact.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def contact_verified(phone: str) -> bool | None:
    """Ask Sendblue whether ``phone`` is a verified contact on the account.

    ``GET /v3/verified-contacts/{phone}`` answers for one number; an account
    whose API predates it falls back to the whole legacy contact list
    (``GET /accounts/contacts``). ``None`` when the provider could not say.
    Cached briefly per number.
    """
    if not _configured():
        return None
    cached = _contacts.get(phone)
    if cached and time.monotonic() - cached[0] < CONTACTS_TTL_S:
        return cached[1]
    verified = _fetch_contact(phone)
    _contacts[phone] = (time.monotonic(), verified)
    return verified


def _fetch_contact(phone: str) -> bool | None:
    try:
        response = _request("GET", f"/v3/verified-contacts/{quote(phone, safe='')}")
    except httpx.HTTPError as exc:
        logger.info("Sendblue contact lookup for %s failed: %s", phone, exc)
        return None
    if response.status_code == 200:
        body = _json(response)
        contact = _dig(body, "contact") or body
        if _contact_number(contact) is not None or isinstance(contact, dict) and (
            "verified" in contact or "verification_status" in contact
        ):
            return _contact_verified_flag(contact)
        return None
    if response.status_code == 404:
        # Either the number is not a contact, or this account's API has no
        # v3 route. The legacy list tells the two apart.
        listed = _fetch_legacy_contacts()
        if listed is None:
            return False if _json(response) is not None else None
        return listed.get(phone, False)
    logger.info("Sendblue contact lookup for %s answered %s", phone, response.status_code)
    return None


def _fetch_legacy_contacts() -> dict[str, bool] | None:
    """Every contact on the account by E.164 number -> verified flag, from
    the older ``/accounts/contacts`` list. ``None`` when it cannot be read."""
    from app.notifications.sendblue import normalize_phone

    try:
        response = _request("GET", "/accounts/contacts")
    except httpx.HTTPError as exc:
        logger.info("Sendblue contact list failed: %s", exc)
        return None
    if response.status_code != 200:
        return None
    body = _json(response)
    rows = body if isinstance(body, list) else _dig(body, "contacts", "data", "items")
    if not isinstance(rows, list):
        return None
    out: dict[str, bool] = {}
    for contact in rows:
        number = _contact_number(contact)
        normalized = normalize_phone(number) if number else None
        if normalized:
            out[normalized] = bool(_contact_verified_flag(contact))
    return out


def register_pending(phone: str) -> str | None:
    """Tell Sendblue to expect ``phone``'s first text, and learn which line
    it has to text (``POST /v3/verified-contacts``). Optional: the inbound
    text verifies the number whether or not this ran. Returns the line's
    number when the provider named one; failures are logged and swallowed.
    Cached per number so a retry does not re-register."""
    if not _configured():
        return None
    cached = _line_for.get(phone)
    if cached and time.monotonic() - cached[0] < PLAN_TTL_S:
        return cached[1]
    line: str | None = None
    try:
        response = _request("POST", "/v3/verified-contacts", json={"phone_number": phone})
        if response.status_code < 300:
            body = _json(response)
            found = _dig(body, "line")
            number = _contact_number(found) if isinstance(found, dict) else None
            if number:
                line = number
            flag = _contact_verified_flag(_dig(body, "contact"))
            if flag is True:
                _contacts[phone] = (time.monotonic(), True)
        else:
            logger.info("Sendblue would not register %s: %s", phone, response.status_code)
    except httpx.HTTPError as exc:
        logger.info("Sendblue contact registration for %s failed: %s", phone, exc)
    _line_for[phone] = (time.monotonic(), line)
    return line


def account_plan() -> str | None:
    """The account's plan name as Sendblue reports it (``free_api`` on the
    free tier), or None when it cannot be read. Cached for ten minutes."""
    global _plan
    if not _configured():
        return None
    if _plan is not None and time.monotonic() - _plan[0] < PLAN_TTL_S:
        return _plan[1]
    plan: str | None = None
    try:
        response = _request("GET", "/accounts")
        if response.status_code == 200:
            found = _dig(_json(response), "plan", "plan_name", "tier")
            if isinstance(found, dict):
                found = found.get("name") or found.get("id")
            if isinstance(found, str) and found.strip():
                plan = found.strip()
    except httpx.HTTPError as exc:
        logger.info("Sendblue account lookup failed: %s", exc)
    _plan = (time.monotonic(), plan)
    return plan


def status(db: Session | None = None) -> dict[str, Any]:
    """For /api/health and the integrations screen: the rule in force and
    what has been learned. Reads only caches and the table — never the network."""
    plan = _plan[1] if _plan is not None else None
    count: int | None = None
    if db is not None:
        from sqlalchemy import func, select

        count = db.scalar(select(func.count()).select_from(VerifiedContact))
    return {
        "mode": (settings.sendblue_verified_contacts_only or "auto").strip().lower(),
        "plan": plan,
        "text_to": line_number(),
        "text_body": text_first_body(),
        "verified_contacts": count,
    }
