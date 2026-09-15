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
    HospitalSpec("hosp_medpull", "MedPull Orthopedic Institute", "Houston", "TX"),
    HospitalSpec("hosp_methodist", "Houston Methodist Hospital", "Houston", "TX",
                 "Houston Methodist"),
    HospitalSpec("hosp_hermann", "Memorial Hermann Orthopedic & Spine", "Houston", "TX",
                 "Memorial Hermann"),
    HospitalSpec("hosp_stlukes", "Baylor St. Luke's Medical Center", "Houston", "TX",
                 "CommonSpirit"),
    HospitalSpec("hosp_utsw", "UT Southwestern Medical Center", "Dallas", "TX"),
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
    _spec("linda", "Linda Park", 58, "F", ProcedureType.ROTATOR_CUFF,
          "Rotator Cuff Repair", 10, SourceProvider.FITBIT, "Fitbit Charge 6", 0, "hosp_methodist"),
    _spec("robert", "Robert Hale", 66, "M", ProcedureType.LUMBAR,
          "Lumbar Decompression", 6, SourceProvider.OURA, "Oura Ring Gen4", 1, "hosp_hermann"),
    _spec("sofia", "Sofia Marino", 47, "F", ProcedureType.ANKLE,
          "Ankle Fracture ORIF", 21, SourceProvider.OURA, "Oura Ring Gen4", 1, "hosp_stlukes"),
    _spec("aisha", "Aisha Bello", 71, "F", ProcedureType.THA,
          "Total Hip Replacement (THA)", 15, SourceProvider.APPLE, "Apple Watch SE 3", 2, "hosp_methodist"),
    _spec("priya", "Priya Nair", 64, "F", ProcedureType.THA,
          "Total Hip Replacement (THA)", 9, SourceProvider.WITHINGS, "Withings ScanWatch 2", 2, "hosp_utsw"),
    _spec("grace", "Grace Kim", 69, "F", ProcedureType.THA,
          "Total Hip Replacement (THA)", 3, SourceProvider.WHOOP, "WHOOP 5.0", 2, "hosp_hermann"),
    _spec("david", "David Osei", 24, "M", ProcedureType.ACL,
          "ACL Reconstruction", 34, SourceProvider.APPLE, "Apple Watch Ultra 3", 0, "hosp_stlukes"),
    _spec("james", "James Whitfield", 70, "M", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 40, SourceProvider.FITBIT, "Fitbit Sense 3", 2, "hosp_utsw"),
    _spec("elena", "Elena Ruiz", 33, "F", ProcedureType.MENISCUS,
          "Meniscus Repair", 19, SourceProvider.APPLE, "Apple Watch Series 10", 0, "hosp_methodist"),
]


def get_spec(patient_id: str) -> PatientSpec | None:
    return next((p for p in PATIENTS if p.id == patient_id), None)
