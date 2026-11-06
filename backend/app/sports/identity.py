"""Sports accounts: creating one, joining a program, the staff behind it.

An athlete's row is a ``Patient`` with ``account_kind="sports"``: no
hospital, the synthetic MedPull coach row as surgeon and provider (the
schema needs both), the same email/password credential as a personal
space, and a ``SportsProfile`` beside it. An athlete who has had surgery
carries the procedure and its date on the Patient row so the clinic
engine's recovery curve and care metrics (M1–M18) run for them unchanged;
everyone else sits on the general pathway anchored at the day they joined.
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.sports import (
    LEVEL_LABELS,
    LEVELS,
    SPORT_LABELS,
    SPORTS,
    STATUS_LABELS,
    SportsOrg,
    SportsProfile,
    SportsStaff,
    SportsTeam,
)
from app.personal.scope import SPORTS as SPORTS_KIND
from app.personal.scope import ensure_coach_member, is_sports

logger = logging.getLogger(__name__)


class SportsIdentityError(ValueError):
    def __init__(self, detail: str, status: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _slug(name: str, db: Session) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "athlete"
    candidate = f"{base}-ath"
    while db.get(Patient, candidate) is not None:
        candidate = f"{base}-{secrets.token_hex(2)}"
    return candidate


def _age(dob: date | None) -> int:
    if dob is None:
        return 0
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def profile_of(db: Session, patient: Patient) -> SportsProfile | None:
    return db.get(SportsProfile, patient.id)


def create_sports_account(
    db: Session, *, name: str, sport: str, phone: str | None = None, sex: str | None = None,
    date_of_birth: date | None = None, org_id: str | None = None, team_id: str | None = None,
    position: str | None = None, jersey: str | None = None, class_year: str | None = None,
    level: str | None = None, height_cm: float | None = None, weight_kg: float | None = None,
    wingspan_cm: float | None = None, standing_reach_cm: float | None = None,
    dominant_side: str | None = None, units: str = "imperial", cycle_tracking: bool = False,
    join_code: str | None = None, patient_id: str | None = None,
) -> tuple[Patient, SportsProfile]:
    if sport not in SPORTS:
        raise SportsIdentityError("Pick a sport", 422)
    name = " ".join(name.split())
    if len(name) < 2:
        raise SportsIdentityError("Enter your name", 422)
    org = db.get(SportsOrg, org_id) if org_id else None
    if org_id and org is None:
        raise SportsIdentityError("Unknown organization", 404)
    team = db.get(SportsTeam, team_id) if team_id else None
    if team_id and (team is None or (org and team.org_id != org.id)):
        raise SportsIdentityError("Unknown team", 404)
    if team is not None and team.sport != sport:
        raise SportsIdentityError(f"That team plays {SPORT_LABELS.get(team.sport, team.sport)}", 422)
    linked = False
    if org is not None:
        if org.join_code and join_code and secrets.compare_digest(org.join_code.lower(), join_code.strip().lower()):
            linked = True
        elif not org.join_code:
            linked = True
    coach = ensure_coach_member(db)
    today = date.today()
    parts = name.split()
    patient = Patient(
        id=patient_id or _slug(name, db), name=name,
        initials="".join(part[0] for part in parts[:2]).upper(),
        age=_age(date_of_birth), sex=(sex or "U")[:1].upper(),
        procedure_type="NONE", procedure_display="No surgery",
        surgery_date=today, discharge_date=today,
        surgeon_id=coach, assigned_provider_id=coach, hospital_id=None,
        date_of_birth=date_of_birth, phone=phone, care_pathway="general_recovery",
        account_kind=SPORTS_KIND, timezone=org.timezone if org else "America/Chicago",
    )
    db.add(patient)
    db.flush()
    lvl = level if level in LEVELS else (org.level if org else "club")
    profile = SportsProfile(
        patient_id=patient.id, sport=sport, org_id=org.id if org else None,
        team_id=team.id if team else None, coach_linked=linked and team is not None,
        position=(position or "").strip()[:40] or None, jersey=(jersey or "").strip()[:4] or None,
        class_year=(class_year or "").strip()[:8] or None, level=lvl,
        height_cm=height_cm, weight_kg=weight_kg, wingspan_cm=wingspan_cm,
        standing_reach_cm=standing_reach_cm,
        dominant_side=dominant_side if dominant_side in ("left", "right") else None,
        units="metric" if units == "metric" else "imperial", cycle_tracking=cycle_tracking,
        settings={"devices": {}},
    )
    db.add(profile)
    db.commit()
    return patient, profile


def join_org(db: Session, profile: SportsProfile, *, org_id: str, team_id: str | None,
             join_code: str | None, position: str | None = None) -> SportsProfile:
    org = db.get(SportsOrg, org_id)
    if org is None:
        raise SportsIdentityError("Unknown organization", 404)
    team = db.get(SportsTeam, team_id) if team_id else None
    if team_id and (team is None or team.org_id != org.id):
        raise SportsIdentityError("Unknown team", 404)
    if team is not None and team.sport != profile.sport:
        raise SportsIdentityError(f"That team plays {SPORT_LABELS.get(team.sport, team.sport)}", 422)
    if org.join_code and not (join_code and secrets.compare_digest(org.join_code.lower(), join_code.strip().lower())):
        raise SportsIdentityError("That join code isn't right. Ask your staff for the team code.", 403)
    profile.org_id = org.id
    profile.team_id = team.id if team else None
    profile.coach_linked = team is not None
    if position:
        profile.position = position.strip()[:40]
    if org.level in LEVELS:
        profile.level = org.level
    db.commit()
    return profile


def leave_org(db: Session, profile: SportsProfile) -> SportsProfile:
    profile.org_id = None
    profile.team_id = None
    profile.coach_linked = False
    db.commit()
    return profile


# --- views ----------------------------------------------------------------------------------------


def org_view(org: SportsOrg, teams: list[SportsTeam] | None = None) -> dict[str, Any]:
    return {
        "id": org.id, "name": org.name, "short_name": org.short_name, "kind": org.kind,
        "city": org.city, "state": org.state, "conference": org.conference, "level": org.level,
        "level_label": LEVEL_LABELS.get(org.level, org.level), "colors": org.colors or {},
        "requires_code": bool(org.join_code),
        "teams": [team_view(t) for t in (teams or [])],
    }


def team_view(team: SportsTeam) -> dict[str, Any]:
    return {"id": team.id, "org_id": team.org_id, "name": team.name, "sport": team.sport,
            "sport_label": SPORT_LABELS.get(team.sport, team.sport), "sex": team.sex,
            "season": team.season, "phase": team.phase}


def staff_view(member: SportsStaff) -> dict[str, Any]:
    return {"id": member.id, "name": member.name, "role": member.role,
            "role_label": STAFF_ROLE_LABELS.get(member.role, member.role.replace("_", " ").title()),
            "athlete_facing": member.athlete_facing}


STAFF_ROLE_LABELS = {
    "head_coach": "Head coach", "assistant_coach": "Assistant coach",
    "strength": "Strength & conditioning", "athletic_trainer": "Athletic trainer",
    "sports_scientist": "Sports scientist", "physician": "Team physician",
    "nutritionist": "Nutritionist", "physical_therapist": "Physical therapist",
}


def staff_for(db: Session, profile: SportsProfile) -> list[SportsStaff]:
    if not profile.org_id or not profile.coach_linked:
        return []
    stmt = select(SportsStaff).where(SportsStaff.org_id == profile.org_id, SportsStaff.athlete_facing.is_(True))
    rows = list(db.scalars(stmt).all())
    # The athlete's own team's staff first, then org-wide staff (no team).
    mine = [s for s in rows if s.team_id == profile.team_id]
    shared = [s for s in rows if s.team_id is None and profile.team_id is not None]
    return mine + shared


def profile_view(db: Session, patient: Patient, profile: SportsProfile) -> dict[str, Any]:
    org = db.get(SportsOrg, profile.org_id) if profile.org_id else None
    team = db.get(SportsTeam, profile.team_id) if profile.team_id else None
    settings = profile.settings or {}
    return {
        "sport": profile.sport, "sport_label": SPORT_LABELS.get(profile.sport, profile.sport),
        "org": org_view(org) if org else None, "team": team_view(team) if team else None,
        "coach_linked": profile.coach_linked, "position": profile.position, "jersey": profile.jersey,
        "class_year": profile.class_year, "level": profile.level,
        "level_label": LEVEL_LABELS.get(profile.level, profile.level),
        "height_cm": profile.height_cm, "weight_kg": profile.weight_kg,
        "wingspan_cm": profile.wingspan_cm, "standing_reach_cm": profile.standing_reach_cm,
        "dominant_side": profile.dominant_side, "status": profile.status,
        "status_label": STATUS_LABELS.get(profile.status, profile.status), "status_note": profile.status_note,
        "units": profile.units, "cycle_tracking": profile.cycle_tracking,
        "sex": patient.sex, "age": patient.age,
        "devices": settings.get("devices", {}),
        "staff": [staff_view(s) for s in staff_for(db, profile)],
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }


def orgs_view(db: Session, query: str = "") -> list[dict[str, Any]]:
    q = query.strip().lower()
    orgs = sorted(db.scalars(select(SportsOrg)).all(),
                  key=lambda o: ({"college": 0, "pro": 1, "club": 2, "academy": 3}.get(o.kind, 9), o.name))
    teams = list(db.scalars(select(SportsTeam).order_by(SportsTeam.name)).all())
    by_org: dict[str, list[SportsTeam]] = {}
    for t in teams:
        by_org.setdefault(t.org_id, []).append(t)
    out = []
    for org in orgs:
        if q and q not in org.name.lower() and q not in org.short_name.lower() and q not in org.city.lower():
            continue
        out.append(org_view(org, by_org.get(org.id, [])))
    return out


def is_athlete(patient: Patient | None) -> bool:
    return is_sports(patient)
