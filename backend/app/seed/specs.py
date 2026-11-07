"""The dataclasses a seeded roster is written in.

Kept apart from ``app.seed.patients`` so a demo org that lives in its own
module (``app.seed.hirt``) can describe its hospital, care team and patients
without importing the roster that is about to import it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import CareRole, ProcedureType, SourceProvider


@dataclass(frozen=True)
class CareTeamSpec:
    id: str
    name: str
    role: CareRole


@dataclass(frozen=True)
class HospitalSpec:
    id: str
    name: str
    city: str
    state: str
    system: str | None = None
    timezone: str = "America/Chicago"


@dataclass(frozen=True)
class PatientSpec:
    id: str
    name: str
    initials: str
    age: int
    sex: str
    procedure: ProcedureType
    procedure_display: str
    postop_day: int
    provider: SourceProvider | None  # None = real patient, no seeded device
    device_model: str
    surgeon_id: str
    # discharge N days after surgery (joint replacements 1-2, others 0-1)
    discharge_offset: int = 1
    hospital_id: str = "hosp_demo"
    # An explicit pathway for the engine and the check-in to read
    # (Patient.care_pathway). None derives it from the procedure.
    care_pathway: str | None = None
    # The clinician on the worklist row, when not the surgeon.
    assigned_id: str | None = None
