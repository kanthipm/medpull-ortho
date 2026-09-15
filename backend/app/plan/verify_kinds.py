"""The verification vocabulary: how a care-plan task is confirmed.

A task the care team assigns is also a measurement instrument — the walk
task produces the step bouts M1 reads, the pain log anchors M2 and M9. The
``VerifyKind`` names what data confirms the task; ``KIND_INFO`` carries the
provider-facing label, the "verified by" chip, the parameter schema the AI
builder and the UI coerce against, which of the patient app's task kinds the
task is created as, and what the check-in asks when data cannot confirm it.

This lives in ``app/plan`` rather than ``models/enums.py`` because the
patient-app session owns the model enums; the verification vocabulary is
ours and stored as a string in ``AdherenceTask.payload["care"]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class VerifyKind(StrEnum):
    STEPS_MIN = "steps_min"
    STEPS_BAND = "steps_band"
    WALK_BOUTS = "walk_bouts"
    GUIDED_WALK = "guided_walk"
    CONTINUOUS_WALK = "continuous_walk"
    DISTANCE_TARGET = "distance_target"
    STAIRS = "stairs"
    SIT_TO_STAND = "sit_to_stand"
    MOVE_HOURLY = "move_hourly"
    SEDENTARY_LIMIT = "sedentary_limit"
    PAIN_LOG = "pain_log"
    SYMPTOM_LOG = "symptom_log"
    OVERNIGHT_WEAR = "overnight_wear"
    MEDICATION_LOG = "medication_log"
    PROM_WEEKLY = "prom_weekly"
    INCISION_PHOTO = "incision_photo"
    THERAPY_SESSION = "therapy_session"
    ROM_MILESTONE = "rom_milestone"
    PRECAUTION = "precaution"
    CUSTOM = "custom"
    # chronic-care pathways
    WEIGHT_LOG = "weight_log"
    BP_LOG = "bp_log"
    GLUCOSE_LOG = "glucose_log"
    SPO2_CHECK = "spo2_check"
    BREATHLESSNESS_LOG = "breathlessness_log"
    FLUID_NOTE = "fluid_note"
    FOOT_CHECK = "foot_check"
    INHALER_LOG = "inhaler_log"


SCHEDULES = ("daily", "am_pm", "weekly", "once", "ongoing")
PHASES = ("early", "mid", "late", "ongoing")
TASK_KINDS = ("checkin", "exercise", "walk", "medication", "wound_check", "custom")


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: str          # "int" | "float" | "bool" | "str" | "list"
    default: Any
    label: str


@dataclass(frozen=True)
class KindInfo:
    label: str
    verified_by: str
    params: tuple[ParamSpec, ...]
    task_kind: str                 # the patient app's task kind the task is created as
    checkin: str | None            # "yes_no" | "count" | None (data confirms it, nothing asked)
    data_verified: bool            # some data source can confirm it


_P = ParamSpec

KIND_INFO: dict[VerifyKind, KindInfo] = {
    VerifyKind.STEPS_MIN: KindInfo(
        "Daily step minimum", "step data", (_P("min_steps", "int", 2000, "Minimum steps"),),
        "walk", None, True),
    VerifyKind.STEPS_BAND: KindInfo(
        "Stay within the step band", "step data",
        (_P("band_low", "int", None, "Band low"), _P("band_high", "int", None, "Band high"),
         _P("auto", "bool", True, "Personalized band")),
        "walk", None, True),
    VerifyKind.WALK_BOUTS: KindInfo(
        "Short walks through the day", "walk sessions",
        (_P("bouts", "int", 3, "Walks per day"), _P("min_minutes", "int", 5, "Minutes each")),
        "walk", "count", True),
    VerifyKind.GUIDED_WALK: KindInfo(
        "In-app guided walk", "walk sessions", (_P("minutes", "int", 2, "Minutes"),),
        "walk", "yes_no", True),
    VerifyKind.CONTINUOUS_WALK: KindInfo(
        "Continuous walk", "walk sessions", (_P("minutes", "int", 10, "Minutes"),),
        "walk", "yes_no", True),
    VerifyKind.DISTANCE_TARGET: KindInfo(
        "Distance target", "step data", (_P("miles", "float", 0.5, "Miles"),),
        "walk", "yes_no", True),
    VerifyKind.STAIRS: KindInfo(
        "Stairs", "step data", (_P("flights", "int", 1, "Flights"),),
        "exercise", "count", True),
    VerifyKind.SIT_TO_STAND: KindInfo(
        "Sit-to-stands", "app entry",
        (_P("reps", "int", 5, "Reps"), _P("times", "int", 2, "Times per day")),
        "exercise", "count", True),
    VerifyKind.MOVE_HOURLY: KindInfo(
        "Move every hour", "step data", (_P("hours", "int", 8, "Hours with movement"),),
        "walk", "yes_no", True),
    VerifyKind.SEDENTARY_LIMIT: KindInfo(
        "Sitting limit", "step data", (_P("max_minutes", "int", 45, "Longest sit, minutes"),),
        "custom", "yes_no", True),
    VerifyKind.PAIN_LOG: KindInfo(
        "Pain log", "app entry", (_P("times", "int", 2, "Times per day"),),
        "checkin", None, True),
    VerifyKind.SYMPTOM_LOG: KindInfo(
        "Symptom log", "app entry", (_P("fields", "list", ["swelling", "fever"], "Fields"),),
        "checkin", None, True),
    VerifyKind.OVERNIGHT_WEAR: KindInfo(
        "Wear the device overnight", "overnight data",
        (_P("nights_per_week", "int", 5, "Nights per week"),),
        "custom", None, True),
    VerifyKind.MEDICATION_LOG: KindInfo(
        "Medication log", "self-report", (), "medication", "yes_no", False),
    VerifyKind.PROM_WEEKLY: KindInfo(
        "Weekly questionnaire", "app entry", (_P("instrument", "str", "PROM", "Instrument"),),
        "custom", "yes_no", False),
    VerifyKind.INCISION_PHOTO: KindInfo(
        "Incision photo", "camera → review", (_P("cadence", "str", "weekly", "Cadence"),),
        "wound_check", "yes_no", False),
    VerifyKind.THERAPY_SESSION: KindInfo(
        "Therapy session", "in-app timer", (_P("minutes", "int", 15, "Minutes"),),
        "exercise", "yes_no", True),
    VerifyKind.ROM_MILESTONE: KindInfo(
        "Range-of-motion milestone", "self-report", (), "custom", "yes_no", False),
    VerifyKind.PRECAUTION: KindInfo(
        "Precaution", "self-report", (), "custom", "yes_no", False),
    VerifyKind.CUSTOM: KindInfo("Task", "self-report", (), "custom", "yes_no", False),
    VerifyKind.WEIGHT_LOG: KindInfo(
        "Daily weight", "scale data", (), "checkin", "yes_no", True),
    VerifyKind.BP_LOG: KindInfo(
        "Blood-pressure log", "cuff data", (_P("times", "int", 2, "Times per day"),),
        "checkin", "yes_no", True),
    VerifyKind.GLUCOSE_LOG: KindInfo(
        "Glucose log", "glucose data", (_P("times", "int", 2, "Times per day"),),
        "checkin", "yes_no", True),
    VerifyKind.SPO2_CHECK: KindInfo(
        "Oxygen check", "pulse-ox data", (), "checkin", "yes_no", True),
    VerifyKind.BREATHLESSNESS_LOG: KindInfo(
        "Breathlessness log", "app entry", (_P("times", "int", 2, "Times per day"),),
        "checkin", None, True),
    VerifyKind.FLUID_NOTE: KindInfo(
        "Fluid and salt note", "self-report", (), "custom", "yes_no", False),
    VerifyKind.FOOT_CHECK: KindInfo(
        "Foot check", "self-report", (), "wound_check", "yes_no", False),
    VerifyKind.INHALER_LOG: KindInfo(
        "Inhaler log", "self-report", (), "medication", "yes_no", False),
}

# Kinds where a day without data is a missed day (daily logs and daily
# quantities), as opposed to kinds where the data only ever confirms.
MISSED_WHEN_ABSENT: frozenset[VerifyKind] = frozenset({
    VerifyKind.PAIN_LOG, VerifyKind.SYMPTOM_LOG, VerifyKind.OVERNIGHT_WEAR,
    VerifyKind.WEIGHT_LOG, VerifyKind.BP_LOG, VerifyKind.GLUCOSE_LOG, VerifyKind.SPO2_CHECK,
    VerifyKind.BREATHLESSNESS_LOG,
})


def as_kind(value: Any, default: VerifyKind = VerifyKind.CUSTOM) -> VerifyKind:
    try:
        return VerifyKind(str(value))
    except ValueError:
        return default


def verified_by_label(kind: VerifyKind | str) -> str:
    return KIND_INFO[as_kind(kind)].verified_by


def default_task_kind(kind: VerifyKind | str) -> str:
    return KIND_INFO[as_kind(kind)].task_kind


def _coerce(spec: ParamSpec, value: Any) -> Any:
    if value is None:
        return spec.default
    try:
        if spec.type == "int":
            if isinstance(value, bool):
                return spec.default
            return int(round(float(value)))
        if spec.type == "float":
            if isinstance(value, bool):
                return spec.default
            return float(value)
        if spec.type == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if spec.type == "str":
            return str(value)[:60]
        if spec.type == "list":
            if isinstance(value, str):
                value = [v.strip() for v in value.split(",")]
            return [str(v)[:40] for v in list(value)[:12]]
    except (TypeError, ValueError):
        return spec.default
    return spec.default


def params_for(kind: VerifyKind | str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """The kind's parameters: defaults filled, values coerced to the schema's
    type, unknown keys dropped. Never raises — an off-contract LLM draft
    should be repaired, not rejected (see §9.6 on validator strikes)."""
    info = KIND_INFO[as_kind(kind)]
    overrides = overrides if isinstance(overrides, dict) else {}
    out: dict[str, Any] = {}
    for spec in info.params:
        value = _coerce(spec, overrides.get(spec.name))
        if spec.type in ("int", "float") and isinstance(value, (int, float)) and value < 0:
            value = spec.default
        out[spec.name] = value
    return out


def kinds_payload() -> list[dict[str, Any]]:
    return [
        {
            "kind": str(kind),
            "label": info.label,
            "verified_by": info.verified_by,
            "task_kind": info.task_kind,
            "checkin": info.checkin,
            "data_verified": info.data_verified,
            "params_schema": [
                {"name": p.name, "type": p.type, "default": p.default, "label": p.label}
                for p in info.params
            ],
        }
        for kind, info in KIND_INFO.items()
    ]
