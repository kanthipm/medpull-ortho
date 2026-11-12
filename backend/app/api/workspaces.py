"""What the console's workspace menu lists: the versions of the product
this console may open and the rows under each.

One read (``GET /api/console/workspaces``, wired beside the session route in
``app/api/auth.py``) so the menu, the tab bar and the first redirect all come
from the same answer:

* **clinic**: the active hospitals that have at least one clinic chart, most
  charts first. A hospital credential sees its own and no other.
* **personal**: the demo members (``app/personal/showcase.py``), on the demo
  stack and for staff only. A real subscriber's space is never listed here.
* **sports**: the teams with at least one linked athlete that the scope may
  see.

Grouped counts only: nothing here loads a chart, runs the engine or commits.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import ConsoleScope, acting_clinic
from app.api.scope import scope_teams
from app.config import settings
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.models.personal import GOAL_LABELS, PersonalProfile
from app.models.sports import SportsOrg, SportsProfile, SportsTeam
from app.personal.scope import clinic_filter

VERSION_ORDER = ("clinic", "personal", "sports")


def _clinics(db: Session, scope: ConsoleScope) -> list[dict[str, Any]]:
    """Hospitals with their chart counts. Staff get every active hospital
    that has a chart; a hospital credential its own row whatever the count,
    because an empty roster is still its clinic."""
    if not scope.clinic:
        return []
    charts = dict(
        db.execute(
            clinic_filter(select(Patient.hospital_id, func.count(Patient.id)))
            .where(Patient.hospital_id.is_not(None))
            .group_by(Patient.hospital_id)
        ).all()
    )
    exercises: set[str] = set()
    if settings.hep_enabled:
        from app.hep.models import ExerciseAssignment

        exercises = set(db.scalars(select(ExerciseAssignment.hospital_id).distinct()).all())
    if scope.kind == "hospital":
        own = db.get(Hospital, scope.org_id)
        hospitals = [own] if own is not None else []
    else:
        hospitals = [
            h for h in db.scalars(select(Hospital).where(Hospital.active.is_(True))).all()
            if charts.get(h.id, 0) > 0
        ]
    hospitals.sort(key=lambda h: (-charts.get(h.id, 0), h.id))
    return [
        {"id": h.id, "name": h.name, "patients": int(charts.get(h.id, 0)),
         # Whether the exercise calendar has anything on it for this clinic.
         "hep": h.id in exercises}
        for h in hospitals
    ]


def _members(db: Session, scope: ConsoleScope) -> list[dict[str, Any]]:
    """The demo members of MedPull Personal: demo stack and staff only."""
    if not settings.demo_mode or not scope.staff:
        return []
    from app.personal.showcase import members
    from app.seed.showcase import persona

    rows = members(db)
    if not rows:
        return []
    goals = dict(
        db.execute(
            select(PersonalProfile.patient_id, PersonalProfile.goal)
            .where(PersonalProfile.patient_id.in_([p.id for p in rows]))
        ).all()
    )
    out = []
    for patient in rows:
        goal = goals.get(patient.id) or "everyday"
        registered = persona(patient.id)
        out.append({
            "id": patient.id,
            "name": patient.name,
            "goal": goal,
            # The registry's line for this persona; the goal in words for a
            # member the registry does not describe.
            "tagline": (registered.tagline if registered and registered.tagline
                        else GOAL_LABELS.get(goal, goal)),
        })
    return out


def _teams(db: Session, scope: ConsoleScope) -> list[dict[str, Any]]:
    """Teams with a roster that this scope may see, biggest roster first."""
    if not scope.sports:
        return []
    roster = dict(
        db.execute(
            select(SportsProfile.team_id, func.count())
            .where(SportsProfile.team_id.is_not(None), SportsProfile.coach_linked.is_(True))
            .group_by(SportsProfile.team_id)
        ).all()
    )
    rows = db.execute(
        scope_teams(
            scope,
            select(SportsTeam, SportsOrg.short_name).join(SportsOrg, SportsOrg.id == SportsTeam.org_id),
        )
    ).all()
    teams = [
        {"id": team.id, "name": team.name, "org_id": team.org_id, "org_name": org_name,
         "sport": team.sport, "roster": int(roster.get(team.id, 0))}
        for team, org_name in rows
        if roster.get(team.id, 0) >= 1
    ]
    teams.sort(key=lambda t: (-t["roster"], t["id"]))
    return teams


def workspaces(db: Session, scope: ConsoleScope) -> dict[str, Any]:
    clinics = _clinics(db, scope)
    members = _members(db, scope)
    teams = _teams(db, scope)
    # A credential always has its own version, even with nothing in it yet;
    # staff get Clinic, and the other two only when there is something to open.
    listed = {
        "clinic": scope.clinic,
        "personal": bool(members),
        "sports": bool(teams) if scope.staff else scope.sports,
    }
    return {
        "demo": bool(settings.demo_mode),
        "versions": [v for v in VERSION_ORDER if listed[v]],
        "clinics": clinics,
        "acting_clinic": acting_clinic(db, scope),
        "members": members,
        "teams": teams,
    }
