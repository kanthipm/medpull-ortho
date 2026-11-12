"""Care pathways: which metrics lead for which kind of patient.

The platform monitors any recovering or chronically ill patient; orthopedic
recovery is one pathway among several. A pathway names the domain the
patient is on, the order its headline tiles are chosen in, the primary
patient-reported symptom for the symptom-load slope, and whether progress is
judged against a procedure recovery curve (ortho) or only against the
patient's own baseline (chronic).

Headline: SIX fixed tiles per archetype, in a fixed order, so a clinician
who reads two knee patients finds the same stat in the same rectangle on
both pages. Every orthopedic pathway shares one set — the recovery curve
(M17), load this week (M1), the deterioration safety net (M12), the
load→pain dose-response (M2), nights (M9) and adherence (M14) — because
those are the six questions every post-surgical follow-up turns on
whatever the joint. Chronic pathways lead with the condition's own vital
(weight for heart failure, SpO₂ for COPD, glucose for diabetes, blood
pressure for hypertension) and keep engagement and coverage close behind,
because a chronic program lives or dies on both. The first and last slots
are the wide tiles. Anything outside the six that the engine flags is
brought to attention beside the grid (headline.select_attention), never by
reshuffling it.

A person on a clinic's own training program (``clinic_program``) has no
operation to recover from and usually no watch. The care metrics read them
on ``TRAINING``, whose six are the ones an exercise calendar and an evening
check-in fill; everything else about them (the plan builder, the next
steps) still reads ``pathway_for``.
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


# The one orthopedic set. Slot 0 and slot 5 are the wide tiles: the recovery
# curve (a band chart) and adherence (a task-by-day grid) are the two that
# need the width.
ORTHO_SIX = ("M17", "M1", "M12", "M2", "M9", "M14")
HEADLINE_SIZE = 6

PATHWAYS: dict[str, Pathway] = {
    "ortho_tka": Pathway("ortho_tka", "Total knee replacement recovery", "ortho", list(ORTHO_SIX)),
    "ortho_tha": Pathway("ortho_tha", "Total hip replacement recovery", "ortho", list(ORTHO_SIX)),
    "ortho_acl": Pathway("ortho_acl", "ACL reconstruction recovery", "ortho", list(ORTHO_SIX)),
    "ortho_meniscus": Pathway("ortho_meniscus", "Meniscus repair recovery", "ortho", list(ORTHO_SIX)),
    "ortho_ankle": Pathway("ortho_ankle", "Ankle fracture recovery", "ortho", list(ORTHO_SIX)),
    "ortho_shoulder": Pathway("ortho_shoulder", "Rotator cuff repair recovery", "ortho", list(ORTHO_SIX)),
    "ortho_spine": Pathway("ortho_spine", "Lumbar decompression recovery", "ortho", list(ORTHO_SIX)),
    "heart_failure": Pathway(
        "heart_failure", "Heart failure program", "cardiac",
        ["C1", "M1", "M12", "M10", "M14", "M15"], "breathlessness", False,
    ),
    "copd": Pathway(
        "copd", "COPD program", "pulmonary",
        ["C2", "M1", "M12", "M2", "M9", "M14"], "breathlessness", False,
    ),
    "diabetes": Pathway(
        "diabetes", "Diabetes program", "metabolic",
        ["C3", "M1", "M12", "M17", "M14", "M15"], "fatigue", False,
    ),
    "hypertension": Pathway(
        "hypertension", "Hypertension program", "cardiac",
        ["C4", "M1", "M12", "M17", "M14", "M15"], "fatigue", False,
    ),
    "chronic_pain": Pathway(
        "chronic_pain", "Chronic pain and deconditioning program", "pain",
        ["M2", "M1", "C5", "M9", "M14", "M15"], "pain", False,
    ),
    "general_recovery": Pathway(
        "general_recovery", "General recovery", "general",
        ["M17", "M1", "M12", "C5", "M14", "M15"], "fatigue", False,
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


# --- a clinic's own training program -----------------------------------------------
#
# The six a lifter's chart leads with. Slot 0 and slot 5 are the wide tiles:
# what was done of what was set (M14, an exercise-by-day grid) and whether
# the person is still answering (M15). Between them: load this week (M1),
# what load costs in next-day pain (M2), symptoms (C5) and how the chart is
# being followed (M16). The wearable metrics are still computed, and still
# come to attention beside the grid when a watch is connected and one flags.
TRAINING_SIX = ("M14", "M1", "M2", "C5", "M16", "M15")

# Not in PATHWAYS on purpose: a chart is never assigned to it by key, and the
# plan library has no tasks tagged for it. It is what the care metrics read a
# clinic-program chart on, and nothing else.
TRAINING = Pathway(
    "training_program", "Training program", "general", list(TRAINING_SIX), "pain", False,
)


def clinic_program(patient) -> str | None:
    """The clinic-authored program a non-surgical person is on, when there
    is one.

    ``care_pathway`` normally holds one of the keys above. A clinic that
    writes its own program name there instead ("Patellar tendinopathy ·
    progressive loading", the H.I.R.T. roster) is saying this person trains
    between visits. A surgical patient is never on one: they keep the
    recovery pathway of their operation.
    """
    program = (getattr(patient, "care_pathway", None) or "").strip()
    if not program or program in PATHWAYS:
        return None
    if str(getattr(patient, "procedure_type", None)) != "NONE":
        return None
    return program


def care_pathway_for(patient) -> Pathway:
    """The pathway the care metrics read this patient on: ``TRAINING`` for a
    person on a clinic's own program, otherwise ``pathway_for``."""
    return TRAINING if clinic_program(patient) is not None else pathway_for(patient)


def care_pathway_by_key(key: str | None) -> Pathway:
    """The pathway a stored care bundle names (it may name ``TRAINING``)."""
    return TRAINING if key == TRAINING.key else pathway_by_key(key)
