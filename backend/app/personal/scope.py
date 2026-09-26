"""Where the line between the clinic product and the personal tier is drawn.

Two questions every other module asks:

* **Is this row a clinic chart or a personal profile?** — ``is_personal``.
  Every console enumeration of the roster (worklist, briefing, Ask, the
  link-candidate list, the startup hospital fixer) goes through
  ``clinic_patients`` so a subscriber can never land on a clinician's screen.
* **Whose observations does this row read?** — ``data_patient_id``. A
  personal profile linked to a clinic chart carries no wearable stream of
  its own; the chart's is the one the phone delivers to, and the personal
  readouts are computed over it. Every reader of the observation table for
  the app's benefit resolves the id here first.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.models.patient import Patient

PERSONAL = "personal"
CLINIC = "clinic"

# The synthetic care-team row every personal profile is assigned to: the
# schema requires a surgeon and an assigned provider, and a subscriber has
# neither. Nothing routes a notification to it and no text is ever tagged
# with it (tasks/service.dispatch tags only a real clinician).
COACH_MEMBER_ID = "ct_medpull"
COACH_MEMBER_NAME = "MedPull Coach"


def is_personal(patient: Patient | None) -> bool:
    return patient is not None and (patient.account_kind or CLINIC) == PERSONAL


def clinic_filter(stmt: Select) -> Select:
    """Restrict a ``select(Patient…)`` to clinic charts. NULL counts as
    clinic: every row written before the column existed is one."""
    return stmt.where((Patient.account_kind.is_(None)) | (Patient.account_kind != PERSONAL))


def clinic_patients(db: Session, order_by=None) -> list[Patient]:
    stmt = clinic_filter(select(Patient))
    if order_by is not None:
        stmt = stmt.order_by(order_by)
    return list(db.scalars(stmt).all())


def clinic_patient_ids(db: Session) -> list[str]:
    return list(db.scalars(clinic_filter(select(Patient.id)).order_by(Patient.id)).all())


def data_patient_id(patient: Patient) -> str:
    """The id whose observation rows this patient's readouts are built from."""
    return patient.observations_from or patient.id


def data_patient(db: Session, patient: Patient) -> Patient:
    """The row that owns the wearable stream (the patient itself, or the
    clinic chart a personal profile is linked to)."""
    if not patient.observations_from:
        return patient
    owner = db.get(Patient, patient.observations_from)
    return owner or patient


def ensure_coach_member(db: Session) -> str:
    """The care-team row personal profiles are assigned to, created on
    first use. Idempotent, and never texted (no phone)."""
    from app.models.enums import CareRole
    from app.models.patient import CareTeamMember

    if db.get(CareTeamMember, COACH_MEMBER_ID) is None:
        db.add(CareTeamMember(id=COACH_MEMBER_ID, name=COACH_MEMBER_NAME, role=CareRole.ADMIN))
        db.flush()
    return COACH_MEMBER_ID
