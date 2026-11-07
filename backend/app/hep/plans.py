"""Exercise plans: drafts, the version-checked update, publish with
snapshots, supersession and the read-backs the console and the patient
app share."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.hep.models import (
    PLAN_STATUSES,
    SIDES,
    Exercise,
    ExerciseMedia,
    ExercisePlan,
    PlanExercise,
)
from app.hep.service import HepError, audit, exercise_payload, media_payload, visible_to
from app.models.mobile import PatientSession
from app.models.patient import CareTeamMember, Patient
from app.personal.scope import is_clinic

FREQUENCIES = (
    "daily", "twice_daily", "three_times_daily", "every_other_day", "three_per_week", "weekly",
)
FREQUENCY_LABELS = {
    "daily": "Once a day", "twice_daily": "Twice a day", "three_times_daily": "Three times a day",
    "every_other_day": "Every other day", "three_per_week": "Three times a week",
    "weekly": "Once a week",
}
SIDE_LABELS = {"left": "Left", "right": "Right", "both": "Both sides", "not_applicable": ""}
MAX_ITEMS = 20


class HepConflict(HepError):
    """The plan moved since the client read it; the router answers 409."""


@dataclass(frozen=True)
class PlanItemIn:
    exercise_id: int
    sets: int | None = None
    reps: int | None = None
    hold_seconds: int | None = None
    frequency: str = "daily"
    side: str = "not_applicable"
    clinician_instructions: str = ""
    precautions_override: str = ""


# --- reads ------------------------------------------------------------------------


def clinic_patient(db: Session, clinic: str, patient_id: str) -> Patient:
    p = db.get(Patient, patient_id)
    if p is None or not is_clinic(p) or p.hospital_id != clinic:
        raise HepError(f"Unknown patient: {patient_id}")
    return p


def get_plan(db: Session, clinic: str, plan_id: int) -> ExercisePlan | None:
    plan = db.get(ExercisePlan, plan_id)
    if plan is None or plan.hospital_id != clinic:
        return None
    return plan


def list_plans(db: Session, clinic: str, *, status: str | None = None,
               patient_id: str | None = None) -> list[ExercisePlan]:
    if status is not None and status not in PLAN_STATUSES:
        raise HepError(f"Unknown status: {status}")
    q = select(ExercisePlan).where(ExercisePlan.hospital_id == clinic)
    if status is not None:
        q = q.where(ExercisePlan.status == status)
    if patient_id is not None:
        q = q.where(ExercisePlan.patient_id == patient_id)
    return db.scalars(q.order_by(ExercisePlan.updated_at.desc(), ExercisePlan.id.desc())).all()


def plan_items(db: Session, plan: ExercisePlan) -> list[PlanExercise]:
    return db.scalars(
        select(PlanExercise).where(PlanExercise.plan_id == plan.id)
        .order_by(PlanExercise.sort_order, PlanExercise.id)
    ).all()


def active_plan_for(db: Session, patient_id: str) -> ExercisePlan | None:
    return db.scalar(
        select(ExercisePlan)
        .where(ExercisePlan.patient_id == patient_id, ExercisePlan.status == "active")
        .order_by(ExercisePlan.published_at.desc(), ExercisePlan.id.desc())
    )


# --- validation ---------------------------------------------------------------------


def _count(value: Any, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise HepError(f"{name} must be a whole number")
    if n < 0 or n > 999:
        raise HepError(f"{name} must be between 0 and 999")
    return n or None


def _validate_items(db: Session, clinic: str, items: list[PlanItemIn],
                    keep: set[int]) -> list[tuple[PlanItemIn, Exercise]]:
    if not items:
        raise HepError("Add at least one exercise")
    if len(items) > MAX_ITEMS:
        raise HepError(f"A plan holds at most {MAX_ITEMS} exercises")
    seen: set[int] = set()
    out = []
    for item in items:
        if item.exercise_id in seen:
            raise HepError("The same exercise is listed twice")
        seen.add(item.exercise_id)
        e = db.get(Exercise, item.exercise_id)
        if e is None or not visible_to(e, clinic):
            raise HepError(f"Unknown exercise: {item.exercise_id}")
        if e.status == "archived" and e.id not in keep:
            raise HepError(f"{e.title} is archived and cannot be added")
        if item.frequency not in FREQUENCIES:
            raise HepError(f"Unknown frequency: {item.frequency}")
        if item.side not in SIDES:
            raise HepError(f"Unknown side: {item.side}")
        if len(item.clinician_instructions) > 400 or len(item.precautions_override) > 400:
            raise HepError("Instructions and precautions are limited to 400 characters")
        out.append((PlanItemIn(
            exercise_id=e.id, sets=_count(item.sets, "Sets"), reps=_count(item.reps, "Reps"),
            hold_seconds=_count(item.hold_seconds, "Hold"), frequency=item.frequency,
            side=item.side, clinician_instructions=item.clinician_instructions.strip(),
            precautions_override=item.precautions_override.strip(),
        ), e))
    return out


def _snapshot(e: Exercise) -> dict[str, Any]:
    return {
        "key": e.key, "title": e.title, "instructions": e.instructions or "",
        "equipment": e.equipment or "", "precautions": e.precautions or "",
        "body_region": e.body_region, "category": e.category, "media_id": e.media_id,
        "version": int(e.version or 1),
    }


def _write_items(db: Session, plan: ExercisePlan,
                 validated: list[tuple[PlanItemIn, Exercise]], *, snapshot: bool) -> None:
    """Replace the plan's rows. A draft keeps live references; a published
    plan freezes the wording it was published with."""
    existing = {row.exercise_id: row for row in plan_items(db, plan)}
    kept: set[int] = set()
    for order, (item, e) in enumerate(validated):
        row = existing.get(e.id)
        if row is None:
            row = PlanExercise(plan_id=plan.id, exercise_id=e.id)
            db.add(row)
        row.sort_order = order
        row.sets, row.reps, row.hold_seconds = item.sets, item.reps, item.hold_seconds
        row.frequency, row.side = item.frequency, item.side
        row.clinician_instructions = item.clinician_instructions
        row.precautions_override = item.precautions_override
        if snapshot or row.snapshot is None and plan.status == "active":
            row.exercise_version = int(e.version or 1)
            row.snapshot = _snapshot(e)
        kept.add(e.id)
    for exercise_id, row in existing.items():
        if exercise_id not in kept:
            db.delete(row)


# --- writes -----------------------------------------------------------------------


def create_plan(db: Session, clinic: str, *, patient_id: str | None, title: str, notes: str,
                items: list[PlanItemIn], assigned_by: str, actor: str) -> ExercisePlan:
    if patient_id is not None:
        clinic_patient(db, clinic, patient_id)
    validated = _validate_items(db, clinic, items, keep=set()) if items else []
    plan = ExercisePlan(
        hospital_id=clinic, patient_id=patient_id, title=_title(title), notes=notes.strip()[:600],
        status="draft", assigned_by=assigned_by or "provider", version=1,
    )
    db.add(plan)
    db.flush()
    _write_items(db, plan, validated, snapshot=False)
    audit(db, clinic, actor, "plan.create", "plan", plan.id,
          {"patient_id": patient_id, "items": len(validated)})
    db.commit()
    return plan


def update_plan(db: Session, clinic: str, plan: ExercisePlan, *, version: int,
                patient_id: str | None, title: str | None, notes: str | None,
                items: list[PlanItemIn] | None, assigned_by: str | None, actor: str) -> ExercisePlan:
    if plan.status not in ("draft", "active"):
        raise HepError("This plan is closed; start a new one")
    if version != plan.version:
        raise HepConflict("This plan changed since you opened it — reload to see the latest")
    if patient_id is not None and patient_id != plan.patient_id:
        if plan.status == "active":
            raise HepError("A published plan stays with its patient")
        clinic_patient(db, clinic, patient_id)
        plan.patient_id = patient_id
    if title is not None:
        plan.title = _title(title)
    if notes is not None:
        plan.notes = notes.strip()[:600]
    if assigned_by is not None:
        plan.assigned_by = assigned_by or "provider"
    if items is not None:
        keep = {row.exercise_id for row in plan_items(db, plan)}
        validated = _validate_items(db, clinic, items, keep=keep) if items else []
        if plan.status == "active" and not validated:
            raise HepError("A published plan needs at least one exercise")
        _write_items(db, plan, validated, snapshot=plan.status == "active")
    plan.version += 1
    plan.updated_at = datetime.now()
    audit(db, clinic, actor, "plan.revise" if plan.status == "active" else "plan.update",
          "plan", plan.id, {"version": plan.version})
    db.commit()
    return plan


def publish_plan(db: Session, clinic: str, plan: ExercisePlan, *, version: int,
                 actor: str) -> dict[str, Any]:
    if plan.status != "draft":
        raise HepError("Only a draft can be published")
    if version != plan.version:
        raise HepConflict("This plan changed since you opened it — reload to see the latest")
    if plan.patient_id is None:
        raise HepError("Choose the patient this plan is for")
    patient = clinic_patient(db, clinic, plan.patient_id)
    rows = plan_items(db, plan)
    if not rows:
        raise HepError("Add at least one exercise before publishing")
    now = datetime.now()
    superseded: list[int] = []
    for other in db.scalars(select(ExercisePlan).where(
            ExercisePlan.patient_id == patient.id, ExercisePlan.status == "active",
            ExercisePlan.id != plan.id)).all():
        other.status = "superseded"
        other.updated_at = now
        superseded.append(other.id)
    for row in rows:
        e = db.get(Exercise, row.exercise_id)
        row.exercise_version = int(e.version or 1)
        row.snapshot = _snapshot(e)
        e.usage_count = int(e.usage_count or 0) + 1
    plan.status = "active"
    plan.published_at = now
    plan.updated_at = now
    plan.version += 1
    audit(db, clinic, actor, "plan.publish", "plan", plan.id,
          {"patient_id": patient.id, "items": len(rows), "superseded": superseded})
    db.commit()
    has_app = db.scalar(select(PatientSession.id).where(
        PatientSession.patient_id == patient.id, PatientSession.revoked_at.is_(None))) is not None
    return {
        "plan": plan_payload(db, plan),
        "superseded": superseded,
        # The spec keeps invitation state apart from plan state. An existing
        # patient needs no invitation; what they do need is the app.
        "invitation": {
            "needed": False, "status": "not_needed",
            "detail": "The patient already has a record here, so no invitation was sent.",
        },
        "delivery": {
            "channel": "app", "patient_has_app": has_app,
            "detail": ("The plan is live in their MedPull app." if has_app else
                       "They will see it as soon as they sign in to MedPull."),
        },
    }


def archive_plan(db: Session, clinic: str, plan: ExercisePlan, *, actor: str) -> ExercisePlan:
    if plan.status == "archived":
        return plan
    plan.status = "archived"
    plan.updated_at = datetime.now()
    plan.version += 1
    audit(db, clinic, actor, "plan.archive", "plan", plan.id)
    db.commit()
    return plan


def _title(title: str) -> str:
    t = " ".join((title or "").split())[:80]
    return t or "Home exercise plan"


# --- payloads -----------------------------------------------------------------------


def dose_line(row: PlanExercise) -> str:
    """The one-line prescription under an exercise ("3 sets × 10 reps · hold
    5 s · Twice a day · Left")."""
    parts = []
    if row.sets and row.reps:
        parts.append(f"{row.sets} sets × {row.reps} reps")
    elif row.sets:
        parts.append(f"{row.sets} sets")
    elif row.reps:
        parts.append(f"{row.reps} reps")
    if row.hold_seconds:
        parts.append(f"hold {row.hold_seconds} s")
    parts.append(FREQUENCY_LABELS.get(row.frequency, row.frequency))
    if SIDE_LABELS.get(row.side):
        parts.append(SIDE_LABELS[row.side])
    return " · ".join(p for p in parts if p)


def item_payload(db: Session, row: PlanExercise) -> dict[str, Any]:
    """What a plan item looks like to the console and the patient app. A
    published row reads from its snapshot; a draft reads the live library."""
    live = db.get(Exercise, row.exercise_id)
    snap = row.snapshot
    text = snap if snap else (_snapshot(live) if live else {})
    media_id = text.get("media_id") if snap else (live.media_id if live else None)
    media = db.get(ExerciseMedia, media_id) if media_id else None
    steps = [s for s in (text.get("instructions") or "").splitlines() if s.strip()]
    return {
        "id": row.id, "exercise_id": row.exercise_id, "exercise_version": row.exercise_version,
        "snapshotted": snap is not None, "sort_order": row.sort_order,
        "title": text.get("title", ""), "key": text.get("key"),
        "body_region": text.get("body_region"), "category": text.get("category"),
        "steps": steps, "equipment": text.get("equipment", ""),
        "precautions": row.precautions_override or text.get("precautions", ""),
        "library_precautions": text.get("precautions", ""),
        "sets": row.sets, "reps": row.reps, "hold_seconds": row.hold_seconds,
        "frequency": row.frequency, "frequency_label": FREQUENCY_LABELS.get(row.frequency, row.frequency),
        "side": row.side, "side_label": SIDE_LABELS.get(row.side, ""),
        "clinician_instructions": row.clinician_instructions or "",
        "precautions_override": row.precautions_override or "",
        "dose": dose_line(row),
        "media": media_payload(media),
        "library_current": exercise_payload(live) if live else None,
        "library_changed": bool(snap and live and int(live.version or 1) != row.exercise_version),
    }


def plan_payload(db: Session, plan: ExercisePlan, *, with_items: bool = True) -> dict[str, Any]:
    patient = db.get(Patient, plan.patient_id) if plan.patient_id else None
    member = db.get(CareTeamMember, plan.assigned_by) if plan.assigned_by else None
    rows = plan_items(db, plan)
    return {
        "id": plan.id, "clinic_id": plan.hospital_id, "title": plan.title, "notes": plan.notes or "",
        "status": plan.status, "version": plan.version,
        "patient": {"id": patient.id, "name": patient.name} if patient else None,
        "invitation_id": plan.invitation_id,
        "assigned_by": plan.assigned_by,
        "assigned_by_name": member.name if member else None,
        "exercise_count": len(rows),
        "items": [item_payload(db, r) for r in rows] if with_items else None,
        "published_at": plan.published_at.isoformat() if plan.published_at else None,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


def patient_plans_payload(db: Session, clinic: str, patient_id: str) -> dict[str, Any]:
    plans = list_plans(db, clinic, patient_id=patient_id)
    active = next((p for p in plans if p.status == "active"), None)
    return {
        "active": plan_payload(db, active) if active else None,
        "drafts": [plan_payload(db, p, with_items=False) for p in plans if p.status == "draft"],
        "history": [plan_payload(db, p, with_items=False) for p in plans
                    if p.status in ("superseded", "archived")],
    }


def options_payload(db: Session, clinic: str) -> dict[str, Any]:
    patients = db.scalars(
        select(Patient).where(Patient.hospital_id == clinic).order_by(Patient.name)
    ).all()
    members = db.scalars(select(CareTeamMember).order_by(CareTeamMember.name)).all()
    return {
        "frequencies": [{"key": k, "label": FREQUENCY_LABELS[k]} for k in FREQUENCIES],
        "sides": [{"key": k, "label": SIDE_LABELS[k] or "Not applicable"} for k in SIDES],
        "patients": [{"id": p.id, "name": p.name, "has_phone": bool(p.phone)}
                     for p in patients if is_clinic(p)],
        "care_team": [{"id": m.id, "name": m.name, "role": str(m.role)} for m in members],
        "max_items": MAX_ITEMS,
    }
