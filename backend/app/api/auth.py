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

A staff scope may also be looking at one clinic at a time: the workspace
menu's choice arrives as ``X-MedPull-Clinic: <hospital id>`` and becomes
``ConsoleScope.acting_hospital_id``. It narrows what the console lists (the
worklist, its briefing, Ask, notifications, the Data tab's roster) and names
the clinic the exercise calendar acts for; it never widens anything, an org
credential ignores it, and staff may still open any clinic chart by id.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, replace

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app import console_credentials
from app.config import settings
from app.database import get_db
from app.models.hospital import Hospital


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
    # A staff console looking at one clinic at a time (the workspace menu's
    # choice, sent as X-MedPull-Clinic): roster reads narrow to this hospital,
    # and the exercise calendar acts for it. It narrows lists only; a staff
    # scope may still open any chart by id. None for every org credential.
    acting_hospital_id: str | None = None

    @property
    def staff(self) -> bool:
        return self.kind == "all"

    @property
    def whole_roster(self) -> bool:
        """Staff looking at every clinic at once. The briefing, Ask and the
        warm pass treat this as the default roster (``patients=None``); a
        staff console acting for one clinic passes that clinic's charts
        instead, so it reads and fills the very cache rows a credential for
        that hospital does."""
        return self.kind == "all" and self.acting_hospital_id is None

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


# The header the console sends with the clinic picked in the workspace menu.
ACTING_CLINIC_HEADER = "X-MedPull-Clinic"


def _acting(db: Session, scope: ConsoleScope, clinic: str | None) -> ConsoleScope:
    """The scope with the acting clinic applied. Only a staff scope can act
    for a clinic, and only for a hospital that exists: an org credential,
    "all", an empty value and an unknown id all leave the scope as it was,
    so a stale id in a browser's storage reads as "All clinics", never as
    an empty console."""
    clinic = (clinic or "").strip()
    if not scope.staff or not clinic or clinic.lower() == "all":
        return scope
    if db.get(Hospital, clinic) is None:
        return scope
    return replace(scope, acting_hospital_id=clinic)


def acting_clinic(db: Session, scope: ConsoleScope) -> dict | None:
    """``{"id", "name"}`` of the clinic a staff console is acting for."""
    if scope.acting_hospital_id is None:
        return None
    hospital = db.get(Hospital, scope.acting_hospital_id)
    if hospital is None:
        return None
    return {"id": hospital.id, "name": hospital.name}


def require_console(
    request: Request,
    authorization: str | None = Header(default=None),
    acting: str | None = Header(default=None, alias=ACTING_CLINIC_HEADER),
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
    scope = _acting(db, scope, acting)
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
        },
        # The clinic a staff console is looking at (X-MedPull-Clinic), or
        # null for "All clinics" and for every org credential.
        "acting_clinic": acting_clinic(db, scope),
    }


@router.get("/console/workspaces")
def console_workspaces(
    scope: ConsoleScope = Depends(console_scope), db: Session = Depends(get_db)
) -> dict:
    """What the workspace menu lists for this console: the versions it may
    open (clinic, personal, sports) and the clinics, demo members and teams
    under them (app/api/workspaces.py). Read-only."""
    # Imported here: the builder reads app/api/scope.py, which imports this
    # module for ConsoleScope.
    from app.api.workspaces import workspaces

    return workspaces(db, scope)
