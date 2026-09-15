"""Care pathways: which metrics lead for which kind of patient.

The platform monitors any recovering or chronically ill patient; orthopedic
recovery is one pathway among several. A pathway names the domain the
patient is on, the order its headline tiles are chosen in, the primary
patient-reported symptom for the symptom-load slope, and whether progress is
judged against a procedure recovery curve (ortho) or only against the
patient's own baseline (chronic).

Headline rationale (ortho): load tolerance (M1) and the load→pain
dose-response (M2) are the progression-vs-overload decision every
orthopedic follow-up turns on; the deterioration index (M12) is the safety
net; shoulder pivots to night pain (M9), spine to sitting/walking tolerance
change-points (M18), fracture to asymmetry (M3). Chronic pathways lead with
the condition's own vital (weight for heart failure, SpO₂ for COPD, glucose
for diabetes, blood pressure for hypertension) and keep engagement and
coverage close behind, because a chronic program lives or dies on both.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import ProcedureType


@dataclass(frozen=True)
class Pathway:
    key: str            # "ortho_tka", ..., "heart_failure", "copd", "general_recovery"
    name: str
    domain: str         # "ortho" | "cardiac" | "pulmonary" | "metabolic" | "pain" | "general"
    headline: list[str] = field(default_factory=list)  # metric ids in priority order
    symptom_key: str = "pain"   # "pain" | "breathlessness" | "fatigue"
    uses_expected_curve: bool = True  # ortho: compare to the procedure curve


PATHWAYS: dict[str, Pathway] = {
    "ortho_tka": Pathway(
        "ortho_tka", "Total knee replacement recovery", "ortho",
        ["M1", "M2", "M12", "M3", "M17", "M9", "M10", "M14"],
    ),
    "ortho_tha": Pathway(
        "ortho_tha", "Total hip replacement recovery", "ortho",
        ["M1", "M2", "M12", "M3", "M17", "M9", "M10", "M14"],
    ),
    "ortho_acl": Pathway(
        "ortho_acl", "ACL reconstruction recovery", "ortho",
        ["M1", "M2", "M3", "M17", "M12", "M7", "M14"],
    ),
    "ortho_meniscus": Pathway(
        "ortho_meniscus", "Meniscus repair recovery", "ortho",
        ["M1", "M2", "M3", "M17", "M12", "M7", "M14"],
    ),
    "ortho_ankle": Pathway(
        "ortho_ankle", "Ankle fracture recovery", "ortho",
        ["M1", "M3", "M12", "M2", "M17", "M10", "M14"],
    ),
    "ortho_shoulder": Pathway(
        "ortho_shoulder", "Rotator cuff repair recovery", "ortho",
        ["M9", "M2", "M12", "M10", "M15", "M1", "M14"],
    ),
    "ortho_spine": Pathway(
        "ortho_spine", "Lumbar decompression recovery", "ortho",
        ["M1", "M2", "M18", "M9", "M12", "M17", "M14"],
    ),
    "heart_failure": Pathway(
        "heart_failure", "Heart failure program", "cardiac",
        ["C1", "M12", "M1", "M15", "M10", "M16"], "breathlessness", False,
    ),
    "copd": Pathway(
        "copd", "COPD program", "pulmonary",
        ["C2", "M2", "M1", "M9", "M15", "M12"], "breathlessness", False,
    ),
    "diabetes": Pathway(
        "diabetes", "Diabetes program", "metabolic",
        ["C3", "M1", "M14", "M15", "M16"], "fatigue", False,
    ),
    "hypertension": Pathway(
        "hypertension", "Hypertension program", "cardiac",
        ["C4", "M1", "M14", "M15", "M16"], "fatigue", False,
    ),
    "chronic_pain": Pathway(
        "chronic_pain", "Chronic pain and deconditioning program", "pain",
        ["M2", "M1", "M9", "M15", "M14"], "pain", False,
    ),
    "general_recovery": Pathway(
        "general_recovery", "General recovery", "general",
        ["M1", "M12", "M15", "M16", "M17"], "fatigue", False,
    ),
}

_BY_PROCEDURE: dict[ProcedureType, str] = {
    ProcedureType.TKA: "ortho_tka",
    ProcedureType.THA: "ortho_tha",
    ProcedureType.ACL: "ortho_acl",
    ProcedureType.MENISCUS: "ortho_meniscus",
    ProcedureType.ANKLE: "ortho_ankle",
    ProcedureType.ROTATOR_CUFF: "ortho_shoulder",
    ProcedureType.LUMBAR: "ortho_spine",
}

LOWER_LIMB = {
    ProcedureType.TKA, ProcedureType.THA, ProcedureType.ACL,
    ProcedureType.MENISCUS, ProcedureType.ANKLE,
}


def pathway_for(patient) -> Pathway:
    """The patient's pathway: an explicit ``care_pathway`` when the roster
    carries one (a column another module may add), else derived from the
    procedure; anything unknown is general recovery."""
    explicit = getattr(patient, "care_pathway", None)
    if explicit and explicit in PATHWAYS:
        return PATHWAYS[explicit]
    procedure = getattr(patient, "procedure_type", None)
    try:
        key = _BY_PROCEDURE.get(ProcedureType(procedure)) if procedure else None
    except ValueError:
        key = None
    return PATHWAYS[key or "general_recovery"]


def pathway_by_key(key: str | None) -> Pathway:
    return PATHWAYS.get(key or "", PATHWAYS["general_recovery"])
