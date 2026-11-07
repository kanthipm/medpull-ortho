"""The seeded roster. Nine patients ported from the orthopedic-demo domain
model plus one new early-post-op case (Grace Kim).

Demo orgs
---------
The shipped seed is two organizations, each of which a demo can be given on
its own (the console token is minted per hospital):

* ``hosp_demo`` — MedPull Demo Hospital, the surgical and general-care
  roster with wearables (``PATIENTS`` here, filled out by
  ``app.seed.demo_fill`` for a filmed demo);
* ``hirt`` — H.I.R.T. Physical Therapy, a cash-pay PT clinic inside a gym
  whose five lifters are followed by text check-in alone, no wearable
  (``app.seed.hirt``). Their tiers come from what they report.

The nine-patient ortho roster below is the test suite's, seeded only through
``full_roster()``.
"""

from app.models.enums import CareRole, ProcedureType, SourceProvider
from app.seed import hirt
from app.seed.specs import CareTeamSpec, HospitalSpec, PatientSpec

__all__ = [
    "CareTeamSpec", "HospitalSpec", "PatientSpec", "HOSPITALS", "CARE_TEAM", "PATIENTS",
    "BLANK_CHART_FIXTURES", "ORTHO_DEMO_HOSPITALS", "ORTHO_DEMO_PATIENTS", "full_roster",
    "get_spec",
]


# The hospital list the app's first screen shows.
HOSPITALS: list[HospitalSpec] = [
    # The demo org: anyone can join it from the app as a general patient, so
    # a demo works with no roster entry. Rename to the partner org's name.
    HospitalSpec("hosp_demo", "MedPull Demo Hospital", "Houston", "TX", "Demo organization"),
    # The PT clinic whose lifters are followed by text alone (app/seed/hirt.py).
    hirt.HIRT_HOSPITAL,
]


CARE_TEAM: list[CareTeamSpec] = [
    CareTeamSpec("ct_alvarez", "Dr. Alvarez", CareRole.SURGEON),
    CareTeamSpec("ct_chen", "Dr. Chen", CareRole.SURGEON),
    CareTeamSpec("ct_torres", "Maya Torres, RN", CareRole.NURSE),
    CareTeamSpec("ct_wooley", "Sam Wooley, PT", CareRole.PT),
    *hirt.HIRT_CARE_TEAM,
]


def _surgeon_for(procedure: ProcedureType) -> str:
    if procedure in (ProcedureType.TKA, ProcedureType.THA, ProcedureType.MENISCUS):
        return "ct_alvarez"
    return "ct_chen"


def _spec(
    pid: str, name: str, age: int, sex: str, proc: ProcedureType, display: str,
    day: int, provider: SourceProvider | None, model: str, discharge: int = 1,
    hospital: str = "hosp_demo",
) -> PatientSpec:
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    return PatientSpec(
        id=pid, name=name, initials=initials, age=age, sex=sex, procedure=proc,
        procedure_display=display, postop_day=day, provider=provider,
        device_model=model, surgeon_id=_surgeon_for(proc), discharge_offset=discharge,
        hospital_id=hospital,
    )


# What the demo stack seeds. No real person belongs here: real charts are
# created in the app or by the clinic on the real deployment, never by a seed.
PATIENTS: list[PatientSpec] = [
    # The seeded high-risk case: a TKA at day 8 with a coupled vitals shift
    # and activity collapse (see scenarios.py), so the demo worklist always
    # has one patient in the HIGH tier.
    _spec("reyes", "Marcus Reyes", 63, "M", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 8, SourceProvider.APPLE, "Apple Watch Series 10", 2, "hosp_demo"),
    # Demo patients for MedPull Demo Hospital
    _spec("medha", "Medha Rao", 35, "F", ProcedureType.NONE,
          "General care", 0, None, "", 0, "hosp_demo"),
    _spec("ana", "Ana Lee", 28, "F", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 5, SourceProvider.APPLE, "Apple Watch Series 9", 1, "hosp_demo"),
    # H.I.R.T. Physical Therapy: five lifters, no wearables, fourteen days of
    # text check-ins (app/seed/hirt.py writes their history).
    *hirt.HIRT_PATIENTS,
]


# Blank charts with no device, used by the test suite as the "real person with
# no data yet" case. They were once in the shipped seed; they are not any more,
# so the demo never carries a real name and the real app never gets them from
# a reseed. Seeded only through ``full_roster()``.
BLANK_CHART_FIXTURES: list[PatientSpec] = [
    _spec("steve", "Steve", 19, "M", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 1, None, "", 1),
    _spec("guest", "Guest", 45, "M", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 1, None, "", 1),
    _spec("kanthi", "Kanthi", 21, "F", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 1, None, "", 1),
]


# --- the ortho demo roster ------------------------------------------------------
#
# Nine synthetic post-surgical patients across five Houston/Dallas hospitals,
# with hand-tuned scenarios in seed/scenarios.py, transcripts in
# seed/conversations.py and adherence in seed/adherence.py. They were the
# original demo roster and are what the engine's golden-tier tests, the
# baseline-stability tests and most of the API tests are calibrated against.
#
# They are deliberately NOT part of PATIENTS: the shipped seed is the single
# demo hospital above. Anything that wants the full roster asks for it —
# `full_roster()` — which is what the test suite seeds.
ORTHO_DEMO_HOSPITALS: list[HospitalSpec] = [
    HospitalSpec("hosp_medpull", "MedPull Orthopedic Institute", "Houston", "TX"),
    HospitalSpec("hosp_methodist", "Houston Methodist Hospital", "Houston", "TX",
                 "Houston Methodist"),
    HospitalSpec("hosp_hermann", "Memorial Hermann Orthopedic & Spine", "Houston", "TX",
                 "Memorial Hermann"),
    HospitalSpec("hosp_stlukes", "Baylor St. Luke's Medical Center", "Houston", "TX",
                 "CommonSpirit"),
    HospitalSpec("hosp_utsw", "UT Southwestern Medical Center", "Dallas", "TX"),
]

ORTHO_DEMO_PATIENTS: list[PatientSpec] = [
    _spec("linda", "Linda Park", 58, "F", ProcedureType.ROTATOR_CUFF,
          "Rotator Cuff Repair", 10, SourceProvider.FITBIT, "Fitbit Charge 6", 0, "hosp_methodist"),
    _spec("robert", "Robert Hale", 66, "M", ProcedureType.LUMBAR,
          "Lumbar Decompression", 6, SourceProvider.OURA, "Oura Ring Gen4", 1, "hosp_hermann"),
    _spec("sofia", "Sofia Marino", 47, "F", ProcedureType.ANKLE,
          "Ankle Fracture ORIF", 21, SourceProvider.OURA, "Oura Ring Gen4", 1, "hosp_stlukes"),
    _spec("aisha", "Aisha Bello", 71, "F", ProcedureType.THA,
          "Total Hip Replacement (THA)", 15, SourceProvider.APPLE, "Apple Watch SE 3", 2,
          "hosp_methodist"),
    _spec("priya", "Priya Nair", 64, "F", ProcedureType.THA,
          "Total Hip Replacement (THA)", 9, SourceProvider.WITHINGS, "Withings ScanWatch 2", 2,
          "hosp_utsw"),
    _spec("grace", "Grace Kim", 69, "F", ProcedureType.THA,
          "Total Hip Replacement (THA)", 3, SourceProvider.WHOOP, "WHOOP 5.0", 2, "hosp_hermann"),
    _spec("david", "David Osei", 24, "M", ProcedureType.ACL,
          "ACL Reconstruction", 34, SourceProvider.APPLE, "Apple Watch Ultra 3", 0, "hosp_stlukes"),
    _spec("james", "James Whitfield", 70, "M", ProcedureType.TKA,
          "Total Knee Replacement (TKA)", 40, SourceProvider.FITBIT, "Fitbit Sense 3", 2,
          "hosp_utsw"),
    _spec("elena", "Elena Ruiz", 33, "F", ProcedureType.MENISCUS,
          "Meniscus Repair", 19, SourceProvider.APPLE, "Apple Watch Series 10", 0,
          "hosp_methodist"),
]


def full_roster() -> tuple[list[HospitalSpec], list[PatientSpec]]:
    """Every hospital and patient the seed knows how to build: the shipped
    demo hospital plus the blank charts and the ortho demo roster. What the
    test suite seeds, so the fixtures the engine tests are calibrated against
    exist whatever the shipped roster is trimmed to."""
    return (
        HOSPITALS + ORTHO_DEMO_HOSPITALS,
        PATIENTS + BLANK_CHART_FIXTURES + ORTHO_DEMO_PATIENTS,
    )


def get_spec(patient_id: str) -> PatientSpec | None:
    _, patients = full_roster()
    return next((p for p in patients if p.id == patient_id), None)
