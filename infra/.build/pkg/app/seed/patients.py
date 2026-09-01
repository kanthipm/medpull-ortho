"""The seeded roster. Nine patients ported from the orthopedic-demo domain
model plus one new early-post-op case (Grace Kim)."""

from dataclasses import dataclass

from app.models.enums import CareRole, ProcedureType, SourceProvider


@dataclass(frozen=True)
class CareTeamSpec:
    id: str
    name: str
    role: CareRole


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
    provider: SourceProvider
    device_model: str
    surgeon_id: str
    # discharge N days after surgery (joint replacements 1-2, others 0-1)
    discharge_offset: int = 1


def _surgeon_for(procedure: ProcedureType) -> str:
    if procedure in (ProcedureType.TKA, ProcedureType.THA, ProcedureType.MENISCUS):
        return "ct_alvarez"
    return "ct_chen"


def _spec(
    pid: str, name: str, age: int, sex: str, proc: ProcedureType, display: str,
    day: int, provider: SourceProvider, model: str, discharge: int = 1,
) -> PatientSpec:
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    return PatientSpec(
        id=pid, name=name, initials=initials, age=age, sex=sex, procedure=proc,
        procedure_display=display, postop_day=day, provider=provider,
        device_model=model, surgeon_id=_surgeon_for(proc), discharge_offset=discharge,
    )


PATIENTS: list[PatientSpec] = [
    _spec("marcus", "Marcus Reyes", 63, "M", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 8, SourceProvider.APPLE, "Apple Watch Series 10", 2),
    _spec("linda", "Linda Park", 58, "F", ProcedureType.ROTATOR_CUFF,
          "Rotator Cuff Repair", 10, SourceProvider.FITBIT, "Fitbit Charge 6", 0),
    _spec("robert", "Robert Hale", 66, "M", ProcedureType.LUMBAR,
          "Lumbar Decompression", 6, SourceProvider.OURA, "Oura Ring Gen4", 1),
    _spec("sofia", "Sofia Marino", 47, "F", ProcedureType.ANKLE,
          "Ankle Fracture ORIF", 21, SourceProvider.OURA, "Oura Ring Gen4", 1),
    _spec("aisha", "Aisha Bello", 71, "F", ProcedureType.THA,
          "Total Hip Replacement (THA)", 15, SourceProvider.APPLE, "Apple Watch SE 3", 2),
    _spec("priya", "Priya Nair", 64, "F", ProcedureType.THA,
          "Total Hip Replacement (THA)", 9, SourceProvider.WITHINGS, "Withings ScanWatch 2", 2),
    _spec("grace", "Grace Kim", 69, "F", ProcedureType.THA,
          "Total Hip Replacement (THA)", 3, SourceProvider.WHOOP, "WHOOP 5.0", 2),
    _spec("david", "David Osei", 24, "M", ProcedureType.ACL,
          "ACL Reconstruction", 34, SourceProvider.APPLE, "Apple Watch Ultra 3", 0),
    _spec("james", "James Whitfield", 70, "M", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 40, SourceProvider.FITBIT, "Fitbit Sense 3", 2),
    _spec("elena", "Elena Ruiz", 33, "F", ProcedureType.MENISCUS,
          "Meniscus Repair", 19, SourceProvider.APPLE, "Apple Watch Series 10", 0),
]


def get_spec(patient_id: str) -> PatientSpec | None:
    return next((p for p in PATIENTS if p.id == patient_id), None)
