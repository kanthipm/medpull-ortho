"""The seeded roster. Nine patients ported from the orthopedic-demo domain
model plus one new early-post-op case (Grace Kim)."""

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


# The hospital list the app's first screen shows. The real patients (Steve,
# Guest, Kanthi) sit under the MedPull demo institute; the seeded roster is
# spread over the others so every hospital has someone to find.
HOSPITALS: list[HospitalSpec] = [
    # The demo org: anyone can join it from the app as a general patient, so
    # a demo works with no roster entry. Rename to the partner org's name.
    HospitalSpec("hosp_demo", "MedPull Demo Hospital", "Houston", "TX", "Demo organization"),
]


CARE_TEAM: list[CareTeamSpec] = [
    CareTeamSpec("ct_alvarez", "Dr. Alvarez", CareRole.SURGEON),
    CareTeamSpec("ct_chen", "Dr. Chen", CareRole.SURGEON),
    CareTeamSpec("ct_torres", "Maya Torres, RN", CareRole.NURSE),
    CareTeamSpec("ct_wooley", "Sam Wooley, PT", CareRole.PT),
]


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
    hospital_id: str = "hosp_medpull"


def _surgeon_for(procedure: ProcedureType) -> str:
    if procedure in (ProcedureType.TKA, ProcedureType.THA, ProcedureType.MENISCUS):
        return "ct_alvarez"
    return "ct_chen"


def _spec(
    pid: str, name: str, age: int, sex: str, proc: ProcedureType, display: str,
    day: int, provider: SourceProvider | None, model: str, discharge: int = 1,
    hospital: str = "hosp_medpull",
) -> PatientSpec:
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    return PatientSpec(
        id=pid, name=name, initials=initials, age=age, sex=sex, procedure=proc,
        procedure_display=display, postop_day=day, provider=provider,
        device_model=model, surgeon_id=_surgeon_for(proc), discharge_offset=discharge,
        hospital_id=hospital,
    )


PATIENTS: list[PatientSpec] = [
    # The real patients: no synthetic device, observations, check-ins or
    # adherence history — data arrives only through the live Junction path.
    # ("Guest" is a placeholder display name; age 45 is a decade-level guess.)
    _spec("steve", "Steve", 19, "M", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 1, None, "", 1),
    _spec("guest", "Guest", 45, "M", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 1, None, "", 1),
    _spec("kanthi", "Kanthi", 21, "F", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 1, None, "", 1),
    # Demo patients for MedPull Demo Hospital
    _spec("medha", "Medha Rao", 35, "F", ProcedureType.NONE,
          "General care", 0, None, "", 0, "hosp_demo"),
    _spec("ana", "Ana Lee", 28, "F", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 5, SourceProvider.APPLE, "Apple Watch Series 9", 1, "hosp_demo"),
]


def get_spec(patient_id: str) -> PatientSpec | None:
    return next((p for p in PATIENTS if p.id == patient_id), None)
