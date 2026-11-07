"""The console's door, and what it lets a caller see.

Every console router (and the sports team board) runs ``require_console``,
which turns the bearer token into a ``ConsoleScope``:

* the staff token (``CONSOLE_ACCESS_TOKEN``, compared in constant time) is
  scope ``all``: every hospital, every team;
* a minted credential (``app/console_credentials.py``) is the scope it was
  minted with: one hospital's charts, one sports org's boards, or one team's;
* no token at all is scope ``all`` only while the console is open (the
  public demo, token unset) and a 401 otherwise.

A token that matches neither is refused, open console or not, so an org's
credential narrows the view even on the demo stack, and a revoked one stops
working the moment it is revoked. Patient-app, token-link and webhook routes
have their own credentials and are never behind this.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app import console_credentials
from app.config import settings
from app.database import get_db


@dataclass(frozen=True)
class ConsoleScope:
    """What one console request may see.

    ``kind`` is ``all`` | ``hospital`` | ``sports_org`` | ``team``; ``org_id``
    is the hospital / sports org / team id for the three org kinds and None
    for ``all``. ``source`` says how the scope was established: ``open``
    (no token, console unlocked), ``global`` (the staff token) or
    ``credential`` (a minted org token).
    """

    kind: str = "all"
    org_id: str | None = None
    label: str = "MedPull"
    source: str = "open"

    @property
    def staff(self) -> bool:
        return self.kind == "all"

    @property
    def clinic(self) -> bool:
        """May see clinic charts at all (its own hospital's, or every one)."""
        return self.kind in ("all", "hospital")

    @property
    def sports(self) -> bool:
        """May see team boards at all (its own, its org's, or every one)."""
        return self.kind in ("all", "sports_org", "team")


def console_auth_enabled() -> bool:
    return bool(settings.console_access_token)


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


def require_console(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ConsoleScope:
    expected = settings.console_access_token
    token = _bearer(authorization)
    if token is None:
        if expected:
            raise HTTPException(status_code=401, detail="Sign in to the console to continue")
        scope = ConsoleScope(source="open")
    elif expected and secrets.compare_digest(token.encode(), expected.encode()):
        scope = ConsoleScope(source="global")
    else:
        credential = console_credentials.resolve(db, token)
        if credential is None:
            raise HTTPException(status_code=401, detail="That access token is not right")
        scope = ConsoleScope(
            kind=credential.kind, org_id=credential.org_id, label=credential.label,
            source="credential",
        )
    request.state.console_scope = scope
    return scope


def console_scope(scope: ConsoleScope = Depends(require_console)) -> ConsoleScope:
    """The request's scope, for a route to narrow its reads and writes by.
    Resolved once per request: the router-level ``require_console`` and this
    share FastAPI's dependency cache."""
    return scope


router = APIRouter(tags=["console"])


@router.get("/console/session")
def session(
    scope: ConsoleScope = Depends(console_scope), db: Session = Depends(get_db)
) -> dict:
    """Who the console is signed in as. The SPA reads it after a token is
    entered (or arrives in a sign-in link) to decide which pages to show and
    whose name to put beside the brand; a locked console answers 401 to a
    missing or wrong token like every other console route."""
    if scope.kind == "all":
        name = "MedPull"
    else:
        name = console_credentials.org_name(db, scope.kind, scope.org_id) or scope.label
    return {
        "scope": {
            "kind": scope.kind,
            "org_id": scope.org_id,
            "label": scope.label,
            "name": name,
        }
    }
