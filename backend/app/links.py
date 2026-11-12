"""Minting and resolving the links a text carries into the app.

``mint`` returns the URL to put in a text; ``resolve`` turns a token back
into its row, or None when it is unknown or expired. Neither commits: the
caller's transaction carries the new row with the message it belongs to.
The routes are in ``app/api/links.py``; the model and the kinds a link can
name are in ``app/models/links.py``.
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
    if kind not in KINDS:
        raise ValueError(f"Unknown link kind: {kind}")
    token = secrets.token_urlsafe(9)  # 12 characters: short enough to read in a text
    now = datetime.now()
    db.add(
        AppLink(
            token_hash=_hash(token),
            patient_id=patient.id,
            kind=kind,
            ref_id=None if ref_id is None else str(ref_id),
            day=day,
            message_id=message_id,
            created_at=now,
            expires_at=None if ttl is None else now + ttl,
        )
    )
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
