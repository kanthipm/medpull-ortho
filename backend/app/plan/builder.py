"""The AI task builder: a clinician's free-text plan → structured tasks.

The LLM is asked to prefer library keys and to keep patient-facing wording
plain and number-free; the validator COERCES rather than rejects (unknown
params dropped, enums defaulted, lengths clamped) and only counts a strike
against the provider on a total contract failure, because the strike
counter is shared with the worklist and briefing (§9.6). The deterministic
keyword matcher is the fallback and the zero-key path, so the builder works
with no LLM at all.

PHI: the free text goes to the model verbatim — it is the request — with
anything that looks like a phone number or an email address removed; the
patient context is first name, day in program, pathway, reason texts and
the top findings, never a full name, a date or a device id.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.engine.care.pathways import PATHWAYS, Pathway, pathway_by_key, pathway_for
from app.llm.insights import BANNED
from app.llm.prompts import PATIENT_STYLE
from app.llm.provider import (
    LLMError,
    complete_json,
    note_invalid_output,
    note_valid_output,
    provider_name,
)
from app.models.library import TaskTemplate
from app.models.patient import Patient
from app.plan.library import applies_to, templates_for_pathway
from app.plan.verify_kinds import (
    KIND_INFO,
    PHASES,
    SCHEDULES,
    TASK_KINDS,
    VerifyKind,
    default_task_kind,
    params_for,
)

logger = logging.getLogger(__name__)

MAX_TASKS = 6
TITLE_MAX, WHY_MAX, TARGET_MAX, RATIONALE_MAX = 90, 160, 160, 200
EARLY_DAYS, MID_DAYS = 14, 42

TASK_BUILDER_SYSTEM = f"""You turn a clinician's free-text care plan into structured tasks for \
a patient on a monitored care pathway ("care plan", not "recovery plan": the patient may be \
recovering from surgery or living with a chronic condition). You are given the verification \
vocabulary (what data confirms each kind of task and its parameters), the library entries \
for this pathway, and the patient's context. Rules:
- Prefer a library entry (return its "template_key") whenever one fits; adjust its "params" \
when the clinician gave a number ("5 walks" -> bouts 5).
- "title" is what the patient sees on their task card: a short instruction starting with a \
verb, e.g. "Take three short walks today". "why" is one sentence telling them what it does \
for them, e.g. "Walking keeps the swelling down and gets the knee bending." Neither may \
contain metric values, scores, percentages or clinical numbers; a count inside the \
instruction ("three short walks") is fine. "clinical_target" is for the provider and can use \
clinical terms.
- Never use diagnostic language (no "detect", "diagnos...").
- At most 6 tasks.

{PATIENT_STYLE}

Respond with a single JSON object:
{{"tasks": [{{"template_key": "<key or null>", "title": "...", "why": "...", \
"clinical_target": "...", "verify_kind": "<kind>", "task_kind": "<checkin|exercise|walk|\
medication|wound_check|custom>", "params": {{...}}, "schedule": "<daily|am_pm|weekly|once|\
ongoing>", "phase": "<early|mid|late|ongoing>", "feeds": ["M1"], \
"rationale": "<one plain sentence for the clinician: which finding or instruction this task \
answers>"}}]}}"""

SUGGEST_SYSTEM = """You pick 3 to 5 tasks from a care-plan library for one patient, given their \
pathway, day in program, risk reasons and top findings. Prefer tasks whose data would answer \
the open findings, then the basics for this phase. Never use diagnostic language. Each \
"rationale" is one plain sentence a clinician reads in a glance, naming the finding it \
addresses, e.g. "Temperature has been up three mornings; a daily reading will show whether \
it settles." No hedging, no filler. Respond with a single JSON object: \
{"tasks": [{"template_key": "<key>", "rationale": "<one sentence>"}]}"""

_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d\-().\s]{7,}\d)(?!\w)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

NUMBER_WORDS = {
    "one": 1, "once": 1, "two": 2, "twice": 2, "three": 3, "thrice": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "sixty": 60,
}
_AM_PM = re.compile(r"morning and evening|am and pm|am & pm|am/pm|twice a day|twice daily|"
                    r"two times a day|2x", re.IGNORECASE)
_PRECAUTION = re.compile(r"^\s*(no|avoid|don'?t|do not|never|keep off|stay off|not to)\b",
                         re.IGNORECASE)
_MODIFIER_ONLY = re.compile(
    r"^\s*(twice|once|three times|\d+ ?times|every|each|daily|by |for |in the|morning|"
    r"evening|am\b|pm\b|per |a day|weekly|after|before)", re.IGNORECASE)

# (keywords, verify kind) — first match wins, so the specific comes first.
KEYWORDS: list[tuple[tuple[str, ...], VerifyKind]] = [
    (("weigh", "weight", "scale"), VerifyKind.WEIGHT_LOG),
    (("blood pressure", "bp ", "bp,", " bp", "pressure", "cuff"), VerifyKind.BP_LOG),
    (("glucose", "sugar", "cgm"), VerifyKind.GLUCOSE_LOG),
    (("oxygen", "spo2", "pulse ox", "saturation", "oximeter"), VerifyKind.SPO2_CHECK),
    (("inhaler", "puffer"), VerifyKind.INHALER_LOG),
    (("breath", "dyspn", "short of"), VerifyKind.BREATHLESSNESS_LOG),
    (("fluid", "salt", "sodium"), VerifyKind.FLUID_NOTE),
    (("feet", "foot"), VerifyKind.FOOT_CHECK),
    (("photo", "incision", "wound", "picture", "scar"), VerifyKind.INCISION_PHOTO),
    (("medication", "meds", "medicine", "pills", "tablet", "dose"), VerifyKind.MEDICATION_LOG),
    (("questionnaire", "prom", "survey", "koos", "hoos", "oxford"), VerifyKind.PROM_WEEKLY),
    (("stair", "flight", "steps up"), VerifyKind.STAIRS),
    (("sit-to-stand", "sit to stand", "sit/stand", "chair rise", "chair stand", "sit stand"),
     VerifyKind.SIT_TO_STAND),
    (("watch overnight", "overnight", "sleep", "wear the watch", "wear your watch", "wear it",
      "ring at night"), VerifyKind.OVERNIGHT_WEAR),
    (("sitting", "sit longer", "sedentary", "sit for"), VerifyKind.SEDENTARY_LIMIT),
    (("hourly", "every hour", "each hour"), VerifyKind.MOVE_HOURLY),
    (("guided", "in-app walk", "app walk"), VerifyKind.GUIDED_WALK),
    (("pain", "swelling", "symptom", "how it feels", "log"), VerifyKind.PAIN_LOG),
    (("step band", "step range", "band", "within", "steps"), VerifyKind.STEPS_BAND),
    (("mile", "distance", "km", "kilomet"), VerifyKind.DISTANCE_TARGET),
    (("continuous", "without stopping", "non-stop", "nonstop", "in one go", "minute walk",
      "minutes walk", "min walk"), VerifyKind.CONTINUOUS_WALK),
    (("walk",), VerifyKind.WALK_BOUTS),
    (("range of motion", "rom", "lift the arm", "raise the arm", "bend the knee", "flexion"),
     VerifyKind.ROM_MILESTONE),
    (("pt ", "physio", "therap", "exercise", "session", "stretch", "rehab", "hep"),
     VerifyKind.THERAPY_SESSION),
    (("check-in", "checkin", "check in", "how you feel"), VerifyKind.SYMPTOM_LOG),
]


def strip_phi(text: str) -> str:
    """Remove phone numbers and email addresses from free text before it
    leaves the process. Everything else is the clinician's own request."""
    text = _EMAIL.sub("[email]", text or "")
    return _PHONE.sub("[phone]", text)


def phase_for(postop_day: int | None) -> str:
    if postop_day is None:
        return "ongoing"
    if postop_day < EARLY_DAYS:
        return "early"
    if postop_day < MID_DAYS:
        return "mid"
    return "late"


def _postop_day(patient: Patient | None, today: date | None = None) -> int | None:
    if patient is None or getattr(patient, "surgery_date", None) is None:
        return None
    return ((today or date.today()) - patient.surgery_date).days


# --- library lookup ------------------------------------------------------------------------


def pick_template(
    templates: list[TaskTemplate], pathway: Pathway, kind: VerifyKind | str,
    phase: str | None = None, *, schedule: str | None = None, any_pathway: bool = False,
) -> TaskTemplate | None:
    """The library entry for a verify kind: a wanted schedule (AM & PM) wins
    first, then the entry naming this pathway beats one naming its domain
    beats one open to all, then a phase match beats an ongoing entry. With
    ``any_pathway`` an entry from another pathway is the last resort — its
    wording is generic enough to reuse, and better than a bare custom task."""
    kind = str(kind)

    def specificity(t: TaskTemplate) -> int:
        tags = {str(p) for p in (t.pathways or [])}
        if pathway.key in tags:
            return 3
        if pathway.domain in tags:
            return 2
        return 1 if not tags or "all" in tags else 0

    def phase_rank(t: TaskTemplate) -> int:
        if phase is not None and t.phase == phase:
            return 2
        return 1 if t.phase == "ongoing" else 0

    pool = [t for t in templates if t.verify_kind == kind and not t.archived]
    candidates = [t for t in pool if specificity(t) > 0] or (pool if any_pathway else [])
    if not candidates:
        return None
    return max(candidates, key=lambda t: (
        schedule is not None and t.schedule == schedule, specificity(t), phase_rank(t), -t.id,
    ))


def item_from_template(t: TaskTemplate, *, params: dict[str, Any] | None = None,
                       rationale: str = "", title: str | None = None,
                       why: str | None = None) -> dict[str, Any]:
    return {
        "template_id": t.id,
        "template_key": t.key,
        "source_template_key": t.key,
        "title": title or t.title,
        "why": why or t.why,
        "clinical_target": t.clinical_target,
        "task_kind": t.task_kind,
        "verify_kind": t.verify_kind,
        "params": params_for(t.verify_kind, {**(t.params or {}), **(params or {})}),
        "schedule": t.schedule,
        "phase": t.phase,
        "feeds": list(t.feeds or []),
        "due_at": None,
        "rationale": rationale[:RATIONALE_MAX],
    }


def _custom_item(kind: VerifyKind, title: str, why: str, target: str, *, params=None,
                 rationale: str = "", phase: str = "ongoing", schedule: str | None = None,
                 feeds: list[str] | None = None) -> dict[str, Any]:
    info = KIND_INFO[kind]
    return {
        "template_id": None, "template_key": None, "source_template_key": None,
        "title": title[:TITLE_MAX], "why": why[:WHY_MAX], "clinical_target": target[:TARGET_MAX],
        "task_kind": info.task_kind, "verify_kind": str(kind),
        "params": params_for(kind, params), "schedule": schedule or (
            "ongoing" if kind in (VerifyKind.PRECAUTION, VerifyKind.ROM_MILESTONE) else "daily"),
        "phase": phase, "feeds": list(feeds or []), "due_at": None,
        "rationale": rationale[:RATIONALE_MAX],
    }


# --- deterministic parsing --------------------------------------------------------------------


def _clauses(text: str) -> list[str]:
    # "3,000 steps" is one number, not a clause boundary.
    text = re.sub(r"(\d),(\d{3})\b", r"\1\2", text or "")
    parts = [p.strip(" -•*\t") for p in re.split(r"[.;\n,]+|\band then\b", text)]
    out: list[str] = []
    for part in parts:
        if len(part) < 3:
            continue
        if out and _MODIFIER_ONLY.match(part):
            out[-1] = f"{out[-1]}, {part}"
        else:
            out.append(part)
    return out[:MAX_TASKS * 2]


def _first_number(clause: str, *, allow_words: bool = True) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", clause)
    if m:
        return float(m.group())
    if allow_words:
        for word, value in NUMBER_WORDS.items():
            if re.search(rf"\b{word}\b", clause, re.IGNORECASE):
                return float(value)
    return None


def _count_before(clause: str, noun: str) -> float | None:
    """The number right before a noun ("three short walks", "5 sit-to-stands")."""
    m = re.search(rf"(\d+|{'|'.join(NUMBER_WORDS)})\b[\w\s-]{{0,20}}?\b{noun}", clause,
                  re.IGNORECASE)
    if not m:
        return None
    token = m.group(1).lower()
    return float(token) if token.isdigit() else float(NUMBER_WORDS.get(token, 0)) or None


def _times(clause: str) -> int:
    if _AM_PM.search(clause):
        return 2
    m = re.search(r"(\d+|three|four)\s*(?:x|times)\s*(?:a|per)?\s*day", clause, re.IGNORECASE)
    if m:
        token = m.group(1).lower()
        return int(token) if token.isdigit() else NUMBER_WORDS.get(token, 1)
    return 1


def _due_at(clause: str, today: date) -> datetime | None:
    lowered = clause.lower()
    if "next week" in lowered or "within a week" in lowered or "in a week" in lowered:
        return datetime.combine(today + timedelta(days=7), datetime.min.time())
    if "tomorrow" in lowered:
        return datetime.combine(today + timedelta(days=1), datetime.min.time())
    m = re.search(r"(?:within|in)\s+(\d+)\s+days?", lowered)
    if m:
        return datetime.combine(today + timedelta(days=int(m.group(1))), datetime.min.time())
    return None


def _match_kind(clause: str) -> VerifyKind | None:
    lowered = f" {clause.lower()} "
    for keywords, kind in KEYWORDS:
        if any(k in lowered for k in keywords):
            return kind
    return None


def _params_from(kind: VerifyKind, clause: str) -> dict[str, Any]:
    if kind is VerifyKind.WALK_BOUTS:
        n = _count_before(clause, "walk") or _first_number(clause)
        return {"bouts": int(n)} if n else {}
    if kind is VerifyKind.CONTINUOUS_WALK:
        n = _first_number(clause)
        return {"minutes": int(n)} if n else {}
    if kind is VerifyKind.STAIRS:
        n = _count_before(clause, "flight") or _first_number(clause)
        return {"flights": int(n)} if n else {}
    if kind is VerifyKind.SIT_TO_STAND:
        n = _count_before(clause, "sit")
        return {**({"reps": int(n)} if n else {}), "times": _times(clause)}
    if kind is VerifyKind.DISTANCE_TARGET:
        n = _first_number(clause, allow_words=False)
        return {"miles": float(n)} if n else {}
    if kind is VerifyKind.SEDENTARY_LIMIT:
        n = _first_number(clause, allow_words=False)
        return {"max_minutes": int(n)} if n else {}
    if kind is VerifyKind.MOVE_HOURLY:
        n = _first_number(clause, allow_words=False)
        return {"hours": int(n)} if n and n <= 16 else {}
    if kind is VerifyKind.STEPS_BAND:
        m = re.search(r"(\d[\d,]*)\s*(?:-|–|to|and)\s*(\d[\d,]*)\s*steps", clause,
                      re.IGNORECASE)
        if m:
            low, high = (int(x.replace(",", "")) for x in m.groups())
            return {"band_low": low, "band_high": high, "auto": False}
        return {"auto": True}
    if kind is VerifyKind.STEPS_MIN:
        n = _first_number(clause, allow_words=False)
        return {"min_steps": int(n)} if n else {}
    if kind in (VerifyKind.PAIN_LOG, VerifyKind.BP_LOG, VerifyKind.GLUCOSE_LOG,
                VerifyKind.BREATHLESSNESS_LOG):
        return {"times": _times(clause)}
    if kind is VerifyKind.THERAPY_SESSION:
        n = re.search(r"(\d+)\s*min", clause, re.IGNORECASE)
        return {"minutes": int(n.group(1))} if n else {}
    return {}


def _sentence(clause: str) -> str:
    clause = " ".join(clause.split())
    return (clause[:1].upper() + clause[1:]).rstrip(".") if clause else clause


def draft_tasks_fallback(
    text: str, templates: list[TaskTemplate], pathway: Pathway, postop_day: int | None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    today = today or date.today()
    phase = phase_for(postop_day)
    items: list[dict[str, Any]] = []
    for clause in _clauses(text):
        if len(items) >= MAX_TASKS:
            break
        due_at = _due_at(clause, today)
        if _PRECAUTION.match(clause):
            item = _custom_item(
                VerifyKind.PRECAUTION, _sentence(clause), "Your care team asked you to keep to this.",
                "Precaution set by the clinician",
                rationale="A do/don't rule stays in the clinician's own words.", phase=phase,
            )
            items.append(item)
            continue
        kind = _match_kind(clause)
        if kind is VerifyKind.STEPS_BAND and re.search(r"at least|minimum|min\b", clause, re.I):
            kind = VerifyKind.STEPS_MIN
        if kind is None:
            items.append(_custom_item(
                VerifyKind.CUSTOM, _sentence(clause), "Your care team asked for this.",
                "Clinician instruction", rationale="No library match — kept as written.",
                phase=phase,
            ))
            continue
        params = _params_from(kind, clause)
        template = pick_template(
            templates, pathway, kind, phase,
            schedule="am_pm" if params.get("times") == 2 else None, any_pathway=True,
        )
        if template is not None:
            item = item_from_template(
                template, params=params,
                rationale=f"“{_sentence(clause)}” matches the {template.use_case} library task.",
            )
        else:
            info = KIND_INFO[kind]
            item = _custom_item(kind, _sentence(clause), "Your care team asked for this.",
                                info.label, params=params, phase=phase,
                                rationale="No library entry for this kind on the pathway.")
        if due_at is not None:
            item["due_at"] = due_at
            if kind in (VerifyKind.STAIRS, VerifyKind.CONTINUOUS_WALK,
                        VerifyKind.DISTANCE_TARGET, VerifyKind.ROM_MILESTONE):
                item["schedule"] = "once"
        items.append(item)
    return items


# --- validation (coercing) ------------------------------------------------------------------


def _clamp(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def coerce_draft(
    raw: Any, templates: list[TaskTemplate], pathway: Pathway, postop_day: int | None,
) -> list[dict[str, Any]] | None:
    """Normalize an LLM draft to the PlanItem shape. None only on a total
    contract failure (not an object, no ``tasks`` list); an individual task
    that cannot be repaired is dropped."""
    if not isinstance(raw, dict) or not isinstance(raw.get("tasks"), list):
        return None
    by_key = {t.key: t for t in templates if t.key}
    phase_default = phase_for(postop_day)
    out: list[dict[str, Any]] = []
    for entry in raw["tasks"][:MAX_TASKS]:
        if not isinstance(entry, dict):
            continue
        template = by_key.get(str(entry.get("template_key") or ""))
        kind_value = entry.get("verify_kind") or (template.verify_kind if template else "custom")
        try:
            kind = VerifyKind(str(kind_value))
        except ValueError:
            kind = VerifyKind(template.verify_kind) if template else VerifyKind.CUSTOM
        raw_params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
        base_params = dict(template.params or {}) if template and template.verify_kind == str(kind) \
            else {}
        params = params_for(kind, {**base_params, **raw_params})
        title = _clamp(entry.get("title"), TITLE_MAX) or (template.title if template else "")
        why = _clamp(entry.get("why"), WHY_MAX) or (template.why if template else "")
        target = _clamp(entry.get("clinical_target"), TARGET_MAX) or (
            template.clinical_target if template else KIND_INFO[kind].label)
        if not title or BANNED.search(title) or BANNED.search(why) or BANNED.search(target):
            continue
        task_kind = str(entry.get("task_kind") or (template.task_kind if template else ""))
        if task_kind not in TASK_KINDS:
            task_kind = default_task_kind(kind)
        schedule = str(entry.get("schedule") or (template.schedule if template else "daily"))
        if schedule not in SCHEDULES:
            schedule = "daily"
        phase = str(entry.get("phase") or (template.phase if template else phase_default))
        if phase not in PHASES:
            phase = phase_default
        feeds = entry.get("feeds") if isinstance(entry.get("feeds"), list) else (
            list(template.feeds or []) if template else [])
        feeds = [str(f)[:8] for f in feeds][:8]
        rationale = _clamp(entry.get("rationale"), RATIONALE_MAX)
        if BANNED.search(rationale):
            rationale = ""
        out.append({
            "template_id": template.id if template else None,
            "template_key": template.key if template else None,
            "source_template_key": template.key if template else None,
            "title": title, "why": why, "clinical_target": target, "task_kind": task_kind,
            "verify_kind": str(kind), "params": params, "schedule": schedule, "phase": phase,
            "feeds": feeds, "due_at": None, "rationale": rationale,
        })
    return out


# --- context for the model --------------------------------------------------------------


def _headline(assessment) -> list[dict[str, Any]]:
    if assessment is None:
        return []
    care = (assessment.analytics or {}).get("care_metrics") or {}
    by_id = {m.get("id"): m for m in care.get("metrics", []) if isinstance(m, dict)}
    out = []
    for metric_id in care.get("headline", [])[:3]:
        m = by_id.get(metric_id)
        if m:
            out.append({"id": metric_id, "name": m.get("name"), "status": m.get("status"),
                        "status_text": m.get("status_text"), "finding": m.get("finding")})
    return out


def patient_context(db: Session, patient: Patient | None, pathway: Pathway) -> dict[str, Any]:
    """What the model may know about the patient: first name, day in program,
    pathway, reason texts, top findings — no full name, no dates."""
    if patient is None:
        return {"pathway": pathway.name, "pathway_key": pathway.key}
    from app.engine.pipeline import latest_assessment

    assessment = latest_assessment(db, patient.id)
    day = _postop_day(patient)
    return {
        "patient_first_name": (patient.name or "").split()[0] if patient.name else "",
        "pathway": pathway.name,
        "pathway_key": pathway.key,
        "day_in_program": day,
        "phase": phase_for(day),
        "priority": str(assessment.risk_level) if assessment else None,
        "reasons": [r.get("text") for r in (assessment.reasons if assessment else [])][:6],
        "top_findings": _headline(assessment),
    }


def _vocabulary() -> list[dict[str, Any]]:
    return [
        {"verify_kind": str(k), "label": v.label, "verified_by": v.verified_by,
         "task_kind": v.task_kind,
         "params": {p.name: p.default for p in v.params}}
        for k, v in KIND_INFO.items()
    ]


def _library_context(templates: list[TaskTemplate]) -> list[dict[str, Any]]:
    return [
        {"key": t.key, "title": t.title, "clinical_target": t.clinical_target,
         "verify_kind": t.verify_kind, "task_kind": t.task_kind, "phase": t.phase,
         "use_case": t.use_case}
        for t in templates if t.key
    ]


def _resolve_pathway(patient: Patient | None, pathway: str | None) -> Pathway:
    if pathway and pathway in PATHWAYS:
        return pathway_by_key(pathway)
    if patient is not None:
        return pathway_for(patient)
    return PATHWAYS["general_recovery"]


# --- public API --------------------------------------------------------------------------


def draft_tasks(
    db: Session, text: str, patient: Patient | None = None, pathway: str | None = None,
) -> dict[str, Any]:
    resolved = _resolve_pathway(patient, pathway)
    templates = templates_for_pathway(db, resolved)
    every = templates_for_pathway(db, None)
    postop_day = _postop_day(patient)
    clean = strip_phi(text)[:2000]
    provider = provider_name()
    if provider != "fallback" and clean.strip():
        user = json.dumps({
            "clinician_plan": clean,
            "vocabulary": _vocabulary(),
            "library": _library_context(templates),
            "patient": patient_context(db, patient, resolved),
        }, default=str)
        try:
            raw = complete_json(TASK_BUILDER_SYSTEM, user, num_predict=900, temperature=0.3)
            tasks = coerce_draft(raw, templates, resolved, postop_day)
            if tasks is None:
                logger.warning("Task builder draft failed the contract; using fallback")
                note_invalid_output(provider)
            elif tasks:
                note_valid_output(provider)
                return {"tasks": tasks, "provider": provider, "pathway": resolved.key}
        except LLMError as e:
            logger.warning("Task builder LLM call failed: %s", e)
    return {
        "tasks": draft_tasks_fallback(clean, every, resolved, postop_day),
        "provider": "fallback",
        "pathway": resolved.key,
    }


# Rule table for suggestions: (reason codes, metric ids with non-OK status,
# verify kinds to add, rationale). Order is priority.
_SUGGEST_RULES: list[tuple[tuple[str, ...], tuple[str, ...], tuple[VerifyKind, ...], str]] = [
    (("SLEEP_DISRUPTED",), ("M9",), (VerifyKind.OVERNIGHT_WEAR, VerifyKind.PAIN_LOG),
     "Nights look disrupted — overnight wear and an evening pain log pair the two."),
    (("LOW_COVERAGE",), ("M16",), (VerifyKind.OVERNIGHT_WEAR,),
     "Coverage is thin — overnight wear unlocks the surveillance stack."),
    (("TRAJECTORY_BEHIND", "STEPS_FALLING", "WALKING_SLOWING"), ("M1", "M17", "M18"),
     (VerifyKind.STEPS_BAND, VerifyKind.WALK_BOUTS, VerifyKind.GUIDED_WALK),
     "Activity is behind the expected pace — a step band and structured walks restart it."),
    (("TEMP_RISING", "COMPOSITE_HIGH"), ("M12", "M13"), (VerifyKind.INCISION_PHOTO,),
     "Signals are deviating from baseline — a wound photo gives the team a look."),
    (("GAIT_ASYMMETRY_HIGH",), ("M3",), (VerifyKind.GUIDED_WALK,),
     "Walking asymmetry is elevated — the guided walk captures clean gait."),
    (("ADHERENCE_LOW",), ("M14", "M15"), (VerifyKind.PAIN_LOG,),
     "Engagement is slipping — a two-a-day pain log is the lightest daily touchpoint."),
    ((), ("C1",), (VerifyKind.WEIGHT_LOG, VerifyKind.FLUID_NOTE),
     "Weight is moving — a daily weight and fluid note track it."),
    ((), ("C2",), (VerifyKind.SPO2_CHECK, VerifyKind.BREATHLESSNESS_LOG),
     "Oxygenation is drifting — a morning check and breathlessness log follow it."),
    ((), ("C3",), (VerifyKind.GLUCOSE_LOG,), "Time-in-range is below target — log glucose."),
    ((), ("C4",), (VerifyKind.BP_LOG,), "Blood pressure is above target — log it AM and PM."),
]


def suggest_tasks_fallback(
    db: Session, patient: Patient, templates: list[TaskTemplate], pathway: Pathway,
    assessment, active_keys: set[str],
) -> list[dict[str, Any]]:
    postop_day = _postop_day(patient)
    phase = phase_for(postop_day)
    codes = {r.get("code") for r in (assessment.reasons if assessment else [])}
    care = ((assessment.analytics or {}).get("care_metrics") or {}) if assessment else {}
    flagged = {m.get("id") for m in care.get("metrics", [])
               if isinstance(m, dict) and m.get("status") in ("flag", "watch")}
    picked: list[dict[str, Any]] = []
    seen: set[str] = set(active_keys)

    def add(t: TaskTemplate | None, rationale: str) -> None:
        if t is None or t.key in seen or len(picked) >= 5:
            return
        seen.add(t.key)
        picked.append(item_from_template(t, rationale=rationale))

    for reason_codes, metric_ids, kinds, rationale in _SUGGEST_RULES:
        if codes.intersection(reason_codes) or flagged.intersection(metric_ids):
            for kind in kinds:
                add(pick_template(templates, pathway, kind, phase), rationale)
    if len(picked) < 3:
        basics = [t for t in templates if t.phase in (phase, "ongoing") and t.key]
        basics.sort(key=lambda t: (not t.pinned, t.phase != phase, t.id))
        for t in basics:
            add(t, f"A {t.phase} basic for the {pathway.name.lower()}.")
            if len(picked) >= 3:
                break
    return picked[:5]


def suggest_tasks(db: Session, patient: Patient) -> dict[str, Any]:
    from app.engine.pipeline import ensure_current
    from app.plan.service import active_template_keys

    pathway = pathway_for(patient)
    templates = templates_for_pathway(db, pathway)
    assessment = ensure_current(db, patient.id)
    active = active_template_keys(db, patient.id)
    provider = provider_name()
    if provider != "fallback":
        candidates = [t for t in templates if t.key and t.key not in active]
        user = json.dumps({
            "patient": patient_context(db, patient, pathway),
            "library": _library_context(candidates),
            "already_assigned": sorted(active),
        }, default=str)
        try:
            raw = complete_json(SUGGEST_SYSTEM, user, num_predict=500, temperature=0.3)
            by_key = {t.key: t for t in candidates}
            picked: list[dict[str, Any]] = []
            if isinstance(raw, dict) and isinstance(raw.get("tasks"), list):
                for entry in raw["tasks"][:5]:
                    if not isinstance(entry, dict):
                        continue
                    t = by_key.get(str(entry.get("template_key") or ""))
                    rationale = _clamp(entry.get("rationale"), RATIONALE_MAX)
                    if t is None or any(p["template_key"] == t.key for p in picked):
                        continue
                    if BANNED.search(rationale):
                        rationale = ""
                    picked.append(item_from_template(t, rationale=rationale))
                if len(picked) >= 3:
                    note_valid_output(provider)
                    return {"tasks": picked, "provider": provider, "pathway": pathway.key}
                logger.warning("Suggestion draft too thin; using rule table")
            else:
                note_invalid_output(provider)
        except LLMError as e:
            logger.warning("Suggestion LLM call failed: %s", e)
    return {
        "tasks": suggest_tasks_fallback(db, patient, templates, pathway, assessment, active),
        "provider": "fallback",
        "pathway": pathway.key,
    }


__all__ = [
    "TASK_BUILDER_SYSTEM", "draft_tasks", "draft_tasks_fallback", "suggest_tasks",
    "suggest_tasks_fallback", "coerce_draft", "strip_phi", "pick_template", "phase_for",
    "applies_to",
]
