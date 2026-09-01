"""Ask-the-roster: natural-language questions answered over the live analytics.

The LLM sees ONLY the deterministic engine's outputs (never raw data), answers
in plain language, and cites patient ids — the UI filters the worklist to
those patients. A keyword-based deterministic fallback keeps the feature
functional with no LLM.
"""

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.insights import BANNED, _cached, _persist
from app.llm.prompts import PROMPT_VERSION
from app.llm.provider import LLMError, complete_json, provider_name
from app.models.checkin import Checkin
from app.models.enums import GUARDRAIL_SENTENCE, InsightKind
from app.models.insight import RiskAssessment
from app.models.patient import Patient

logger = logging.getLogger(__name__)

ASK_SYSTEM = f"""You are the clinical monitoring assistant inside MedPull Recovery Copilot. \
A clinician asks a question about their post-surgical patient roster. Answer ONLY from the \
data provided — never invent values, and never use diagnostic language (no "detected", \
"diagnosis"; say "signals", "reported", "monitoring shows"). The disclaimer used by the \
product is: "{GUARDRAIL_SENTENCE}"

How to read each PATIENT block:
- "said:" lines are the patient's own words from check-ins. Symptoms mentioned there COUNT \
as reported symptoms (e.g. "I felt feverish", "chills" = reported fever; "pain woke me up" \
= reported pain).
- "monitoring:" lines are wearable findings (e.g. elevated skin temperature is a \
fever-consistent signal).
- Procedures: knee = TKA / ACL / meniscus; hip = THA; shoulder = rotator cuff.

Method — follow exactly:
1. Go through the PATIENT blocks one at a time.
2. Include a patient ONLY if their OWN block contains evidence matching the question. \
Never attribute one patient's symptoms or data to another. If unsure, leave them out.
3. Name only the matching patients in the answer, citing their evidence briefly.

Respond with a single JSON object exactly matching:
{{"answer": "<direct answer, max 80 words, naming only the matching patients>",
 "patient_ids": ["<ONLY the ids of patients that MATCH the question>"]}}
patient_ids drives a filtered list, so it must contain only true matches. If nothing
matches, say so plainly and return []."""

# bump to invalidate cached /ask answers when the prompt above changes
ASK_PROMPT_VERSION = "7"

VERIFY_SYSTEM = """You check whether ONE patient's monitoring block supports a clinician's \
question. "said:" lines are the patient's own words; "monitoring:" lines are wearable \
findings. Be strict about INVENTION — cite only data that appears in this block, and answer \
false when the block is about something else entirely.
- Reported symptoms count as evidence: "I felt feverish" or "chills" matches a fever \
question; "pain woke me up" matches a pain or sleep question; elevated skin temperature is \
a fever-consistent signal.
- Judgment questions count too: for "who should I call / see / prioritize", match when this \
patient's priority or signals justify it (high priority or urgent multi-signal changes = \
yes; stable and on-track = no), citing those signals as evidence.
Reply with a single JSON object: {"match": true or false, "evidence": "<if true, one short \
phrase citing the supporting data; if false, empty string>"}"""

COMPOSE_SYSTEM = f"""You are the clinical monitoring assistant inside MedPull Recovery \
Copilot. You are given the patients VERIFIED to match the clinician's question, each with \
their evidence. Write a direct answer (max 70 words) naming each patient and why they \
match. Never use diagnostic language (no "detected"/"diagnosis" — say "signals", \
"reported"). Product disclaimer, do not repeat it: "{GUARDRAIL_SENTENCE}"
Reply with a single JSON object: {{"answer": "<the answer>"}}"""


def _render_block(p: dict[str, Any]) -> str:
    lines = [
        f"PATIENT id={p['id']} | {p['name']}, {p['age']} | {p['procedure']} | "
        f"post-op day {p['postop_day']} | priority: {p['priority']} | "
        f"trajectory: {p['trajectory']} ({p['trajectory_pct']}% vs expected) | "
        f"adherence: {p['adherence_rate']} | data confidence: {p['data_confidence']}"
    ]
    if p["reasons"]:
        lines.append("  monitoring: " + "; ".join(p["reasons"]))
    for signal in p["notable_signals"]:
        lines.append(f"  monitoring: {signal}")
    for quote in p["patient_said_recently"]:
        lines.append(f'  said: "{quote}"')
    return "\n".join(lines)


def _roster_context(db: Session) -> list[dict[str, Any]]:
    patients = db.scalars(select(Patient).order_by(Patient.id)).all()
    roster: list[dict[str, Any]] = []
    for patient in patients:
        assessment = db.scalar(
            select(RiskAssessment)
            .where(RiskAssessment.patient_id == patient.id)
            .order_by(RiskAssessment.computed_at.desc(), RiskAssessment.id.desc())
            .limit(1)
        )
        if assessment is None:
            continue
        analytics = assessment.analytics
        notable = [
            f"{m['name']}: {m['finding']}"
            for m in analytics.get("metrics", [])
            if m["status"] in ("flag", "watch")
        ]
        recent = db.scalars(
            select(Checkin)
            .where(Checkin.patient_id == patient.id)
            .order_by(Checkin.occurred_at.desc())
            .limit(2)
        ).all()
        quotes = [
            m.text for c in recent for m in c.messages if m.who == "patient"
        ][-6:]
        roster.append(
            {
                "id": patient.id,
                "name": patient.name,
                "age": patient.age,
                "procedure": patient.procedure_display,
                "postop_day": analytics.get("postop_day"),
                "priority": str(assessment.risk_level),
                "reasons": [r["text"] for r in assessment.reasons],
                "trajectory": analytics.get("trajectory", {}).get("state"),
                "trajectory_pct": analytics.get("trajectory", {}).get("pct"),
                "data_confidence": analytics.get("confidence", {}).get("level"),
                "adherence_rate": analytics.get("adherence", {}).get("rate"),
                "notable_signals": notable,
                "patient_said_recently": quotes,
                "_hash": assessment.input_hash,
            }
        )
    return roster


# ---------------------------------------------------------------------------
# Deterministic fallback: keyword → roster-field matching
# ---------------------------------------------------------------------------

_TERM_GROUPS: list[tuple[tuple[str, ...], Any]] = [
    (("fever", "temperature", "temp", "hot", "chills", "infection"),
     lambda p: any("temp" in r.lower() or "fever" in r.lower() for r in p["reasons"])
     or any("fever" in q.lower() or "chills" in q.lower() for q in p["patient_said_recently"])),
    (("pain",),
     lambda p: any("pain" in q.lower() for q in p["patient_said_recently"])),
    (("sleep", "insomnia", "night"),
     lambda p: any("sleep" in r.lower() for r in p["reasons"])),
    (("heart", "hr", "tachy"),
     lambda p: any("hr " in r.lower() or "heart" in r.lower() for r in p["reasons"])),
    (("limp", "gait", "asymmetry", "favoring"),
     lambda p: any("asymmetry" in r.lower() or "favoring" in r.lower() for r in p["reasons"])),
    (("behind", "plateau", "slow", "stalled", "lagging"),
     lambda p: p["trajectory"] == "behind"),
    (("adherence", "exercises", "compliance", "skipping"),
     lambda p: (p["adherence_rate"] or 1) < 0.7),
    (("device", "data", "wearing", "missing", "sync", "gap"),
     lambda p: p["priority"] == "missing_data"),
    (("review", "urgent", "high", "worried", "attention", "worst"),
     lambda p: p["priority"] == "high"),
    (("stable", "fine", "well", "good"),
     lambda p: p["priority"] == "low"),
    (("knee",), lambda p: "knee" in p["procedure"].lower() or "meniscus" in p["procedure"].lower()
     or "acl" in p["procedure"].lower()),
    (("hip",), lambda p: "hip" in p["procedure"].lower()),
    (("shoulder", "cuff"), lambda p: "cuff" in p["procedure"].lower()),
    (("ankle",), lambda p: "ankle" in p["procedure"].lower()),
    (("back", "spine", "lumbar"), lambda p: "lumbar" in p["procedure"].lower()),
]


def fallback_ask(question: str, roster: list[dict[str, Any]]) -> dict[str, Any]:
    q = question.lower()
    predicates = [pred for terms, pred in _TERM_GROUPS if any(t in q for t in terms)]
    if not predicates:
        return {
            "answer": (
                "I couldn't match that to the monitoring data. Try asking about symptoms "
                "(fever, pain, sleep), progress (behind, stable), procedures (knee, hip), "
                "adherence, or data gaps."
            ),
            "patient_ids": [],
        }
    matches = [p for p in roster if all(pred(p) for pred in predicates)]
    if not matches:
        return {"answer": "No patients on the roster match that right now.", "patient_ids": []}
    parts = [f"{p['name']} ({p['reasons'][0] if p['reasons'] else p['priority']})" for p in matches]
    plural = "patient matches" if len(matches) == 1 else "patients match"
    return {
        "answer": f"{len(matches)} {plural}: " + "; ".join(parts) + ".",
        "patient_ids": [p["id"] for p in matches],
    }


def _ask_llm(
    question: str, roster: list[dict[str, Any]], valid_ids: set[str]
) -> dict[str, Any] | None:
    """Retrieve -> verify -> compose. Small local models bind facts to the
    wrong patient when they see the whole roster at once, so every candidate
    is re-checked against ONLY its own block before it can appear in the
    answer or the filter."""
    by_id = {p["id"]: p for p in roster}

    # 1. Candidate retrieval (over-inclusion is fine — verification prunes).
    blocks = "\n\n".join(_render_block(p) for p in roster)
    raw = complete_json(
        ASK_SYSTEM,
        f"Roster:\n\n{blocks}\n\nQuestion: {question}",
        num_predict=500,
        temperature=0.1,
    )
    retrieved = _validate_ask(raw, valid_ids)
    candidate_ids = list(dict.fromkeys(
        (retrieved["patient_ids"] if retrieved else [])
        + fallback_ask(question, roster)["patient_ids"]
    ))[:8]

    # 2. Per-patient verification with single-patient context.
    verified: list[tuple[dict[str, Any], str]] = []
    for cid in candidate_ids:
        patient = by_id.get(cid)
        if patient is None:
            continue
        try:
            check = complete_json(
                VERIFY_SYSTEM,
                f"{_render_block(patient)}\n\nQuestion: {question}",
                num_predict=140,
                temperature=0.0,
            )
        except LLMError:
            continue
        evidence = str(check.get("evidence", "")).strip()
        if check.get("match") is True and evidence and not BANNED.search(evidence):
            verified.append((patient, evidence))

    if not verified:
        return {"answer": "No patients on the roster match that right now.", "patient_ids": []}

    # 3. Compose the answer from verified evidence only.
    evidence_lines = "\n".join(
        f"- {p['name']} (id={p['id']}, {p['procedure']}, day {p['postop_day']}): {evidence}"
        for p, evidence in verified
    )
    answer: str | None = None
    try:
        composed = complete_json(
            COMPOSE_SYSTEM,
            f"Question: {question}\n\nVerified matches:\n{evidence_lines}",
            num_predict=250,
            temperature=0.2,
        )
        candidate_answer = str(composed.get("answer", "")).strip()
        if candidate_answer and len(candidate_answer) <= 700 and not BANNED.search(candidate_answer):
            answer = candidate_answer
    except LLMError:
        pass
    if answer is None:
        answer = f"{len(verified)} match: " + "; ".join(
            f"{p['name']} — {evidence}" for p, evidence in verified
        )
    return {"answer": answer, "patient_ids": [p["id"] for p, _ in verified]}


def _validate_ask(raw: dict[str, Any], valid_ids: set[str]) -> dict[str, Any] | None:
    try:
        answer = str(raw["answer"]).strip()
        ids = [str(i) for i in raw.get("patient_ids", []) if str(i) in valid_ids][:10]
    except (KeyError, TypeError):
        return None
    if not answer or len(answer) > 700:
        return None
    if BANNED.search(answer.replace(GUARDRAIL_SENTENCE, "")):
        return None
    return {"answer": answer, "patient_ids": ids}


def ask(db: Session, question: str) -> dict[str, Any]:
    roster = _roster_context(db)
    valid_ids = {p["id"] for p in roster}

    roster_digest = hashlib.sha256(
        ";".join(f"{p['id']}:{p['_hash']}" for p in roster).encode()
    ).hexdigest()[:16]
    cache_hash = hashlib.sha256(
        f"ask:{question.strip().lower()}:{roster_digest}:{PROMPT_VERSION}."
        f"{ASK_PROMPT_VERSION}:{provider_name()}".encode()
    ).hexdigest()
    cached = _cached(db, None, InsightKind.ASK, cache_hash)
    if cached is not None:
        return {**cached.content, "provider": cached.llm_provider,
                "generated_at": cached.generated_at.isoformat()}

    content: dict[str, Any] | None = None
    provider = provider_name()
    if provider != "fallback":
        try:
            content = _ask_llm(question, roster, valid_ids)
        except LLMError as e:
            logger.warning("Ask LLM call failed: %s", e)

    if content is None:
        provider = "fallback"
        content = fallback_ask(question, roster)

    insight = _persist(db, None, InsightKind.ASK, content, cache_hash, provider)
    return {**content, "provider": provider, "generated_at": insight.generated_at.isoformat()}
