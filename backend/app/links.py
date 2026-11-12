"""Minting and resolving the links a text carries into the app.

``mint`` returns the URL to put in a text; ``resolve`` turns a token back
into its row, or None when it is unknown or expired. Neither commits: the
caller's transaction carries the new row with the message it belongs to.
The routes are in ``app/api/links.py``; the model and the kinds a link can
name are in ``app/models/links.py``.

A link names a place, and the same place is described three ways here so
the text, the app and the browser cannot drift: ``url_for`` (the https URL
the association file hands to the app), ``app_url`` (the app's own scheme,
for a browser's "Open in the app" button) and ``web_path`` (where the
browser continues when there is no app).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.links import KINDS, AppLink
from app.models.patient import Patient

# Long enough that last week's text still opens; short enough that a phone
# number handed to someone else does not inherit a year of links.
DEFAULT_TTL = timedelta(days=14)

# The path the association file claims for the app (IOS_LINK_PATHS).
PATH_PREFIX = "/a/"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def url_for(token: str, base_url: str | None = None) -> str:
    """The https URL for a token. ``base_url`` is the request's own base when
    CHECKIN_BASE_URL is not set (a laptop); on AWS the setting always is."""
    base = (settings.checkin_base_url or base_url or "").rstrip("/")
    return f"{base}{PATH_PREFIX}{token}"


def app_scheme() -> str:
    """The URL scheme of the app this stack's links open: the demo app on
    the demo stack, the patient app everywhere else."""
    return settings.demo_app_scheme if settings.demo_mode else settings.mobile_app_scheme


def app_url(token: str) -> str:
    """The same link in the app's own scheme (``medpulldemo://a/<token>``)."""
    return f"{app_scheme()}://a/{token}"


def web_path(token: str) -> str:
    """Where a browser continues with the link: the patient web app, which
    redeems the token from its hash on boot."""
    return f"/patient/#link={token}"


def text_url(token: str, base_url: str | None = None) -> str:
    """What a text carries: the https URL when there is a host to name, else
    the app's own scheme (a server with no public address, as with the task
    links in ``tasks.dispatch``)."""
    if settings.checkin_base_url or base_url:
        return url_for(token, base_url)
    return app_url(token)


def signin_allowed(db: Session, patient: Patient) -> bool:
    """Whether redeeming a link may start an app session as ``patient``.
    Only on the demo stack, and only as a person the showcase wrote: a demo
    stack can hold real charts beside the fictional ones, and for those a
    link names a place and the person signs in the way they always do."""
    if not settings.demo_mode:
        return False
    from app.seed import showcase

    return showcase.resolve(db, patient.id) is not None


def target(link: AppLink) -> dict:
    """The place a link opens, as the apps read it."""
    return {
        "kind": link.kind,
        "ref_id": link.ref_id,
        "day": link.day.isoformat() if link.day else None,
    }


def _new_token() -> str:
    """Twelve URL-safe characters ending in a letter or digit: short enough
    to read in a text, and Messages' link detection leaves a trailing "-"
    or "_" out of the tap target."""
    while True:
        token = secrets.token_urlsafe(9)
        if token[-1].isalnum():
            return token


def mint_link(
    db: Session,
    patient: Patient,
    kind: str = "today",
    *,
    ref_id: str | int | None = None,
    day: date | None = None,
    ttl: timedelta | None = DEFAULT_TTL,
    message_id: int | None = None,
) -> tuple[AppLink, str]:
    """A new link for ``patient`` to ``kind``: the row (added to the session,
    not committed) and its token, for a caller that sets ``message_id`` once
    the thread line exists."""
    if kind not in KINDS:
        raise ValueError(f"Unknown link kind: {kind}")
    token = _new_token()
    now = datetime.now()
    row = AppLink(
        token_hash=_hash(token),
        patient_id=patient.id,
        kind=kind,
        ref_id=None if ref_id is None else str(ref_id),
        day=day,
        message_id=message_id,
        created_at=now,
        expires_at=None if ttl is None else now + ttl,
        open_count=0,
    )
    db.add(row)
    return row, token


def mint(
    db: Session,
    patient: Patient,
    kind: str = "today",
    *,
    ref_id: str | int | None = None,
    day: date | None = None,
    base_url: str | None = None,
    ttl: timedelta | None = DEFAULT_TTL,
    message_id: int | None = None,
) -> str:
    """A new link for ``patient`` to ``kind``; returns its URL. Adds the row
    to the session without committing."""
    _row, token = mint_link(db, patient, kind, ref_id=ref_id, day=day, ttl=ttl,
                            message_id=message_id)
    return url_for(token, base_url)


def resolve(db: Session, token: str, now: datetime | None = None) -> AppLink | None:
    """The live link for a token, or None (unknown, or past its expiry)."""
    if not token or len(token) > 64:
        return None
    row = db.scalar(select(AppLink).where(AppLink.token_hash == _hash(token)))
    if row is None:
        return None
    if row.expires_at is not None and row.expires_at < (now or datetime.now()):
        return None
    return row


def stamp_opened(link: AppLink, now: datetime | None = None) -> None:
    """Record one redeem. The caller commits. A link is not used up by it:
    the same text is tapped again tomorrow."""
    now = now or datetime.now()
    if link.first_opened_at is None:
        link.first_opened_at = now
    link.last_opened_at = now
    link.open_count = (link.open_count or 0) + 1
