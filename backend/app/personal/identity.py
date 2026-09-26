"""Personal accounts: creating one, pairing it with a clinic chart, and
moving between the two.

A person who both subscribes and is a hospital's patient holds two rows.
Both keep their own tasks, thread, insights and check-ins — the clinic's
side is the care team's business and the personal side is nobody's but
theirs — while the wearable stream is shared: the phone's Health SDK is
signed into one aggregator user, the clinic chart's, and the personal
profile reads through it (``Patient.observations_from``). Pairing moves any
readings the personal profile had already collected onto the chart, using
the same dedupe-aware merge the console's app-link uses.
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity import _merge_connections, _merge_observations
from app.models.mobile import PatientSession
from app.models.patient import Patient
from app.models.personal import GOALS, PersonalProfile
from app.personal import subscription
from app.personal.scope import PERSONAL, ensure_coach_member, is_personal

logger = logging.getLogger(__name__)


class PersonalIdentityError(ValueError):
    def __init__(self, detail: str, status: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _slug(name: str, db: Session) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "member"
    candidate = f"{base}-me"
    while db.get(Patient, candidate) is not None:
        candidate = f"{base}-{secrets.token_hex(2)}"
    return candidate


def _age(dob: date | None) -> int:
    if dob is None:
        return 0
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def create_personal_account(
    db: Session, *, name: str, phone: str | None, goal: str, sport: str | None = None,
    weekly_target_minutes: int | None = None, sleep_target_hours: float | None = None,
    injury: str | None = None, anchor_date: date | None = None,
    procedure_type: str | None = None, sex: str | None = None,
    date_of_birth: date | None = None, units: str = "metric", sms_briefs: bool = True,
) -> tuple[Patient, PersonalProfile]:
    """A personal profile with its trial, no hospital and no care team."""
    from app.api.mobile import PROCEDURE_DISPLAY

    if goal not in GOALS:
        raise PersonalIdentityError(f"Unknown goal {goal!r}", 422)
    name = " ".join(name.split())
    if len(name) < 2:
        raise PersonalIdentityError("Enter your name", 422)
    coach = ensure_coach_member(db)
    # The engine's anchor: the surgery or injury date for a recovery goal
    # (so the recovery curve and post-op day mean something), else today.
    procedure = "NONE"
    if goal == "recovery" and procedure_type in PROCEDURE_DISPLAY and procedure_type != "NONE":
        procedure = procedure_type
    anchor = anchor_date if (goal == "recovery" and anchor_date and anchor_date <= date.today()) \
        else date.today()
    parts = name.split()
    patient = Patient(
        id=_slug(name, db), name=name,
        initials="".join(part[0] for part in parts[:2]).upper(),
        age=_age(date_of_birth), sex=(sex or "U")[:1].upper(),
        procedure_type=procedure, procedure_display=PROCEDURE_DISPLAY[procedure],
        surgery_date=anchor, discharge_date=anchor,
        surgeon_id=coach, assigned_provider_id=coach, hospital_id=None,
        date_of_birth=date_of_birth, phone=phone,
        care_pathway=None if procedure != "NONE" else "general_recovery",
        account_kind=PERSONAL,
    )
    db.add(patient)
    db.flush()
    profile = PersonalProfile(
        patient_id=patient.id, goal=goal, sport=(sport or "").strip()[:60] or None,
        weekly_target_minutes=weekly_target_minutes, sleep_target_hours=sleep_target_hours,
        injury=(injury or "").strip()[:120] or None, anchor_date=anchor_date,
        units="imperial" if units == "imperial" else "metric", sms_briefs=sms_briefs,
    )
    db.add(profile)
    subscription.start_trial(db, patient)
    db.commit()
    return patient, profile


def profile_of(db: Session, patient: Patient) -> PersonalProfile | None:
    return db.get(PersonalProfile, patient.id)


# --- pairing -----------------------------------------------------------------------------


def linked(db: Session, patient: Patient) -> Patient | None:
    if not patient.linked_patient_id:
        return None
    return db.get(Patient, patient.linked_patient_id)


def link(db: Session, clinic: Patient, personal: Patient) -> dict[str, Any]:
    """Pair a clinic chart with a personal profile of the same person."""
    if is_personal(clinic) or not is_personal(personal):
        raise PersonalIdentityError("A link pairs one clinic chart with one personal profile", 422)
    if clinic.linked_patient_id and clinic.linked_patient_id != personal.id:
        raise PersonalIdentityError("That hospital record already has a personal space")
    if personal.linked_patient_id and personal.linked_patient_id != clinic.id:
        raise PersonalIdentityError("This personal space is already paired with a record")
    # Whatever the personal profile collected on its own moves to the chart,
    # which becomes the one stream both rows read.
    connections = _merge_connections(db, clinic, personal)
    moved = _merge_observations(db, clinic, personal, connections.get("kept"))
    from app.models.patient import Device

    for device in db.scalars(select(Device).where(Device.patient_id == personal.id)).all():
        device.patient_id = clinic.id
    clinic.linked_patient_id = personal.id
    personal.linked_patient_id = clinic.id
    personal.observations_from = clinic.id
    if not clinic.phone and personal.phone:
        clinic.phone = personal.phone
    elif clinic.phone and not personal.phone:
        personal.phone = clinic.phone
    db.commit()
    # Both sides re-score: the chart may have gained readings, the profile
    # now reads a different stream.
    try:
        from app.engine.pipeline import run_patient

        run_patient(db, clinic.id, force=True)
        run_patient(db, personal.id, force=True)
    except Exception:  # noqa: BLE001
        logger.exception("Recompute after linking %s <-> %s failed", clinic.id, personal.id)
    logger.info("Linked personal %s with chart %s: %s", personal.id, clinic.id, moved)
    return {"clinic_id": clinic.id, "personal_id": personal.id, "observations": moved,
            "wearable": connections}


def profiles_view(db: Session, current: Patient) -> list[dict[str, Any]]:
    """The spaces this person can switch between, current first."""
    rows = [current]
    other = linked(db, current)
    if other is not None:
        rows.append(other)
    out = []
    for p in rows:
        personal = is_personal(p)
        out.append({
            "patient_id": p.id,
            "kind": "personal" if personal else "clinic",
            "label": "Personal" if personal else (p.hospital.name if p.hospital else "Care team"),
            "detail": ("Your own stats and plan" if personal
                       else p.procedure_display if str(p.procedure_type) != "NONE"
                       else "Followed by your care team"),
            "current": p.id == current.id,
        })
    return out


def switch_target(db: Session, current: Patient, target_id: str) -> Patient:
    if target_id == current.id:
        return current
    other = linked(db, current)
    if other is None or other.id != target_id:
        raise PersonalIdentityError("That space is not yours to switch to", 403)
    return other


def has_live_session(db: Session, patient_id: str) -> bool:
    return db.scalar(
        select(PatientSession.id).where(
            PatientSession.patient_id == patient_id, PatientSession.revoked_at.is_(None)
        ).limit(1)
    ) is not None
