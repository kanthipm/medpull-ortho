"""Applying a ``ConsoleScope`` to the data a console route reads or writes.

Three rules, and every console route goes through one of them:

* A **hospital** scope sees clinic charts on its own hospital's roster and
  nothing else: no other hospital's patients, no subscribers, no athletes,
  no team boards.
* A **team** scope sees its own team's board; a **sports_org** scope every
  board in its org. Neither sees a clinic chart.
* **all** (the staff token, or an open console) sees everything.

A staff scope **acting for one clinic** (``acting_hospital_id``, set from
the console's ``X-MedPull-Clinic`` header) lists that hospital's charts
only: ``scope_patients`` and ``scoped_clinic_patients`` narrow to it, so
the worklist, its briefing, Ask, the bell and the Data roster are that
clinic's. It narrows lists and nothing else: ``patient_visible`` is
unchanged, so staff may still open any clinic chart by id.

A chart a console route opens by id is a clinic chart. A personal
subscriber's profile and an athlete's row are never on a clinic screen, so
``require_patient`` answers 404 for them whatever the scope: the member's
space has its own routes (``app/api/console_personal.py``) and the athlete's
its own (``app/sports/api.py``).

A patient or team outside the scope answers 404, never 403, so an id's
existence does not leak to a console that cannot see it. The staff-only
surfaces (integrations, notification settings, library edits) answer 403
with a plain sentence, because there the caller is allowed to know the page
exists and is not theirs.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy import false, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.api.auth import ConsoleScope, console_scope
from app.models.patient import Patient
from app.models.sports import SportsTeam
from app.personal.scope import CLINIC, clinic_filter, is_clinic

UNKNOWN_PATIENT = "Unknown patient"
UNKNOWN_TEAM = "Unknown team"


# --- patients ----------------------------------------------------------------------


def patient_visible(scope: ConsoleScope, patient: Patient | None) -> bool:
    """Whether this scope may see this chart at all."""
    if patient is None:
        return False
    if scope.kind == "all":
        return True
    if scope.kind == "hospital":
        return (patient.account_kind or CLINIC) == CLINIC and patient.hospital_id == scope.org_id
    # team / sports_org: no clinic chart is theirs
    return False


def scope_patients(scope: ConsoleScope, stmt: Select) -> Select:
    """Add the scope's WHERE clauses to a ``select`` that has ``Patient`` in
    its FROM (``select(Patient)``, or a join that includes it)."""
    if scope.kind == "all":
        if scope.acting_hospital_id is not None:
            # Staff acting for one clinic list what its credential would.
            return clinic_filter(stmt).where(Patient.hospital_id == scope.acting_hospital_id)
        return stmt
    if scope.kind == "hospital":
        return clinic_filter(stmt).where(Patient.hospital_id == scope.org_id)
    return stmt.where(false())


def scoped_clinic_patients(db: Session, scope: ConsoleScope, order_by=None) -> list[Patient]:
    """The clinic roster this scope may list: every clinic chart for ``all``
    (one hospital's while staff are acting for it), one hospital's for a
    hospital credential, none for a sports credential."""
    stmt = scope_patients(scope, clinic_filter(select(Patient)))
    if order_by is not None:
        stmt = stmt.order_by(order_by)
    return list(db.scalars(stmt).all())


def require_patient(db: Session, scope: ConsoleScope, patient_id: str) -> Patient:
    """The clinic chart a route is about, or 404 when it does not exist *for
    this scope* (same answer either way, on purpose). A subscriber's or an
    athlete's row is not a chart: on a staff or open console ``patient_visible``
    is true for any id, and this is the check that keeps those rows off the
    clinic pages."""
    patient = db.get(Patient, patient_id)
    if not patient_visible(scope, patient) or not is_clinic(patient):
        raise HTTPException(status_code=404, detail=UNKNOWN_PATIENT)
    return patient


# --- teams -------------------------------------------------------------------------


def team_visible(scope: ConsoleScope, team: SportsTeam | None) -> bool:
    if team is None:
        return False
    if scope.kind == "all":
        return True
    if scope.kind == "sports_org":
        return team.org_id == scope.org_id
    if scope.kind == "team":
        return team.id == scope.org_id
    return False


def scope_teams(scope: ConsoleScope, stmt: Select) -> Select:
    """Add the scope's WHERE clauses to a ``select`` with ``SportsTeam`` in it."""
    if scope.kind == "all":
        return stmt
    if scope.kind == "sports_org":
        return stmt.where(SportsTeam.org_id == scope.org_id)
    if scope.kind == "team":
        return stmt.where(SportsTeam.id == scope.org_id)
    return stmt.where(false())


def require_team(db: Session, scope: ConsoleScope, team_id: str) -> SportsTeam:
    team = db.get(SportsTeam, team_id)
    if not team_visible(scope, team):
        raise HTTPException(status_code=404, detail=UNKNOWN_TEAM)
    return team


# --- staff-only surfaces ------------------------------------------------------------


def require_staff(scope: ConsoleScope = Depends(console_scope)) -> ConsoleScope:
    """A dependency for the routes only MedPull staff use: the integrations
    page, notification settings, and edits to the shared task and message
    library. An org credential is told so rather than shown a blank page."""
    if scope.kind != "all":
        raise HTTPException(
            status_code=403,
            detail=f"That page is for MedPull staff; this console is signed in as {scope.label}",
        )
    return scope
