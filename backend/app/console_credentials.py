"""Minting, resolving and revoking console credentials.

Shared by the API (``app/api/auth.py``) and the operator script
(``scripts/admin_db.py``), and bound to whatever ``DATABASE_URL`` the process
has, so the same functions run against the deployed file under the S3 write
lock and against a local copy.

A credential is ``kind`` + ``org_id``: ``all`` (staff, no org), ``hospital``
(a hospital id), ``sports_org`` (a sports org id) or ``team`` (a team id). The
token is ``mp_`` plus 32 url-safe characters, handed over exactly once by the
mint; the table keeps its SHA-256 and nothing else.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.credential import ConsoleCredential
from app.models.hospital import Hospital
from app.models.sports import SportsOrg, SportsTeam

KINDS = ("all", "hospital", "sports_org", "team")
TOKEN_PREFIX = "mp_"

# ``last_used_at`` is a coarse "still in use" marker, not an access log. On
# AWS every commit marks the database dirty and even a GET then re-uploads the
# whole file (app/aws/middleware.py), so the stamp moves at most once an hour
# per credential rather than once per request.
LAST_USED_GRANULARITY = timedelta(hours=1)


class CredentialError(ValueError):
    """A mint or revoke that cannot be done: an unknown kind, org or id."""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def org_name(db: Session, kind: str, org_id: str | None) -> str | None:
    """The display name behind a scope: the hospital's, the program's, or
    "<program> <team>" for a team. None when the org no longer exists."""
    if kind == "hospital" and org_id:
        hospital = db.get(Hospital, org_id)
        return hospital.name if hospital else None
    if kind == "sports_org" and org_id:
        org = db.get(SportsOrg, org_id)
        return org.name if org else None
    if kind == "team" and org_id:
        team = db.get(SportsTeam, org_id)
        if team is None:
            return None
        org = db.get(SportsOrg, team.org_id)
        return f"{org.short_name} {team.name}" if org else team.name
    return None


def mint(db: Session, kind: str, org_id: str | None, label: str) -> tuple[ConsoleCredential, str]:
    """Create a credential and return it with the one copy of its token."""
    if kind not in KINDS:
        raise CredentialError(f"Unknown credential kind {kind!r}; one of {', '.join(KINDS)}")
    org_id = (org_id or "").strip() or None
    if kind == "all":
        if org_id is not None:
            raise CredentialError("An 'all' credential is bound to no org; leave the id out")
    else:
        if org_id is None:
            raise CredentialError(f"A {kind} credential needs the {kind}'s id, as KIND:ORG_ID")
        if org_name(db, kind, org_id) is None:
            raise CredentialError(f"Unknown {kind}: {org_id}")
    label = " ".join(label.split())
    if not label:
        raise CredentialError("Give the credential a label (who holds it)")
    token = TOKEN_PREFIX + secrets.token_urlsafe(24)
    row = ConsoleCredential(
        kind=kind, org_id=org_id, label=label, token_hash=hash_token(token),
        created_at=datetime.now(),
    )
    db.add(row)
    db.commit()
    return row, token


def resolve(db: Session, token: str) -> ConsoleCredential | None:
    """The live credential behind a token, or None for an unknown or revoked
    one. Stamps ``last_used_at`` when the last stamp is an hour old."""
    if not token:
        return None
    row = db.scalar(
        select(ConsoleCredential).where(ConsoleCredential.token_hash == hash_token(token))
    )
    if row is None or row.revoked_at is not None:
        return None
    now = datetime.now()
    if row.last_used_at is None or now - row.last_used_at >= LAST_USED_GRANULARITY:
        row.last_used_at = now
        db.commit()
    return row


def revoke(db: Session, credential_id: int) -> ConsoleCredential:
    """Retire a credential. Idempotent: revoking twice keeps the first stamp."""
    row = db.get(ConsoleCredential, credential_id)
    if row is None:
        raise CredentialError(f"Unknown credential id: {credential_id}")
    if row.revoked_at is None:
        row.revoked_at = datetime.now()
        db.commit()
    return row


def list_credentials(db: Session) -> list[ConsoleCredential]:
    return list(db.scalars(select(ConsoleCredential).order_by(ConsoleCredential.id)).all())


def credential_view(row: ConsoleCredential, db: Session | None = None) -> dict[str, Any]:
    """One credential as the operator report prints it: never the hash."""
    view: dict[str, Any] = {
        "id": row.id,
        "kind": row.kind,
        "org_id": row.org_id,
        "label": row.label,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }
    if db is not None:
        view["name"] = "MedPull" if row.kind == "all" else org_name(db, row.kind, row.org_id)
    return view
