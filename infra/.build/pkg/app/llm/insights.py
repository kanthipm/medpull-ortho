"""Insight generation: cache -> LLM -> validate -> (fallback) -> persist.

Validation is the enforcement point for the product's clinical-safety rules —
prompt compliance is never trusted. Any contract or phrasing violation swaps
in the deterministic renderer silently; the UI shows which provider produced
each insight.
"""

import hashlib
import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import fallback
from app.llm.prompts import PROMPT_VERSION, SYSTEM, briefing_prompt, patient_prompt
from app.llm.provider import LLMError, complete_json, model_name, provider_name
from app.models.checkin import Checkin
from app.models.enums import GUARDRAIL_SENTENCE, InsightKind
from app.models.insight import Insight, RiskAssessment
from app.models.patient import Patient

logger = logging.getLogger(__name__)

# Word-prefix match: catches detect/detected/detection, diagnose/diagnosis/...
BANNED = re.compile(r"\b(detect|diagnos)", re.IGNORECASE)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _validate(kind: InsightKind, content: dict[str, Any]) -> dict[str, Any] | None:
    """Returns normalized content, or None when it must be replaced."""
    try:
        if kind == InsightKind.WORKLIST_REASON:
            reason = str(content["reason"]).strip()
            if not reason or len(reason) > 110:
                return None
            content = {"reason": reason[:90]}
        elif kind == InsightKind.PATIENT_SUMMARY:
            summary = str(content["summary"]).strip()
            if not summary or len(summary) < 40:
                return None
            if not summary.endswith(GUARDRAIL_SENTENCE):
                summary = f"{summary.rstrip()} {GUARDRAIL_SENTENCE}"
            content = {"summary": summary}
        elif kind == InsightKind.SUGGESTED_ACTIONS:
            actions = content["actions"]
            if not isinstance(actions, list) or not actions:
                return None
            normalized = []
            for a in actions[:4]:
                urgency = a.get("urgency", "routine")
                if urgency not in ("today", "this_week", "routine"):
                    urgency = "routine"
                normalized.append(
                    {"title": str(a["title"])[:60], "detail": str(a.get("detail", "")), "urgency": urgency}
                )
            content = {"actions": normalized}
        elif kind == InsightKind.DAILY_BRIEFING:
            briefing = str(content["briefing"]).strip()
            if not briefing or len(briefing) < 30:
                return None
            content = {"briefing": briefing}
    except (KeyError, TypeError):
        return None

    # The guardrail sentence itself is exempt from the banned-phrase scan.
    for text in _strings(content):
        if BANNED.search(text.replace(GUARDRAIL_SENTENCE, "")):
            return None
    return content


def _cached(db: Session, patient_id: str | None, kind: InsightKind, cache_hash: str) -> Insight | None:
    row = db.scalar(
        select(Insight)
        .where(
            Insight.patient_id == patient_id,
            Insight.kind == kind,
            Insight.input_hash == cache_hash,
        )
        .order_by(Insight.id.desc())
        .limit(1)
    )
    # A fallback row written during a transient LLM failure (e.g. a rate-limit
    # burst) must not permanently satisfy a real-provider cache key — treat it
    # as a miss so the next read retries the LLM.
    if row is not None and row.llm_provider == "fallback" and provider_name() != "fallback":
        return None
    return row


def _persist(
    db: Session,
    patient_id: str | None,
    kind: InsightKind,
    content: dict[str, Any],
    cache_hash: str,
    provider: str,
) -> Insight:
    insight = Insight(
        patient_id=patient_id,
        kind=kind,
        content=content,
        input_hash=cache_hash,
        llm_provider=provider,
        model=model_name() if provider != "fallback" else None,
    )
    db.add(insight)
    db.commit()
    return insight


def _latest_assessment(db: Session, patient_id: str) -> RiskAssessment:
    assessment = db.scalar(
        select(RiskAssessment)
        .where(RiskAssessment.patient_id == patient_id)
        .order_by(RiskAssessment.computed_at.desc(), RiskAssessment.id.desc())
        .limit(1)
    )
    if assessment is None:
        raise ValueError(f"No risk assessment for patient {patient_id} — run the engine first")
    return assessment


def _transcript(db: Session, patient_id: str, n_checkins: int = 3) -> list[dict[str, str]]:
    checkins = db.scalars(
        select(Checkin)
        .where(Checkin.patient_id == patient_id)
        .order_by(Checkin.occurred_at.desc())
        .limit(n_checkins)
    ).all()
    messages: list[dict[str, str]] = []
    for checkin in reversed(checkins):
        for m in checkin.messages:
            messages.append({"who": m.who, "text": m.text})
    return messages


def _header(patient: Patient, postop_day: int) -> dict[str, Any]:
    return {
        "name": patient.name,
        "age": patient.age,
        "sex": patient.sex,
        "procedure": patient.procedure_display,
        "postop_day": postop_day,
    }


def get_patient_insight(db: Session, kind: InsightKind, patient_id: str) -> Insight:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ValueError(f"Unknown patient: {patient_id}")
    assessment = _latest_assessment(db, patient_id)
    transcript = _transcript(db, patient_id)

    digest = hashlib.sha256(json.dumps(transcript).encode()).hexdigest()[:16]
    # risk_level is included so prose can never lag a tier change, even if an
    # assessment is somehow regenerated under an unchanged input hash.
    cache_hash = hashlib.sha256(
        f"{kind}:{assessment.input_hash}:{assessment.risk_level}:{digest}:"
        f"{PROMPT_VERSION}:{provider_name()}".encode()
    ).hexdigest()

    cached = _cached(db, patient_id, kind, cache_hash)
    if cached is not None:
        return cached

    analytics = assessment.analytics
    header = _header(patient, analytics.get("postop_day", 0))

    content: dict[str, Any] | None = None
    provider = provider_name()
    # Stable patients' worklist reasons are pure status lines ("tracking as
    # expected") — the deterministic text is already exact, and skipping the
    # LLM keeps the worklist fast on cold caches.
    skip_llm = (
        kind == InsightKind.WORKLIST_REASON
        and analytics.get("risk", {}).get("level") == "low"
    )
    if provider != "fallback" and not skip_llm:
        try:
            # warm enough that a manual Refresh visibly rewrites the narrative
            raw = complete_json(
                SYSTEM, patient_prompt(kind, header, analytics, transcript), temperature=0.6
            )
            content = _validate(kind, raw)
            if content is None:
                logger.warning("LLM output for %s/%s failed validation; using fallback", patient_id, kind)
        except LLMError as e:
            logger.warning("LLM call failed for %s/%s: %s", patient_id, kind, e)

    if content is None:
        provider = "fallback"
        if kind == InsightKind.WORKLIST_REASON:
            content = fallback.worklist_reason(analytics)
        elif kind == InsightKind.PATIENT_SUMMARY:
            content = fallback.patient_summary(header, analytics)
        else:
            content = fallback.suggested_actions(analytics)

    return _persist(db, patient_id, kind, content, cache_hash, provider)


def get_daily_briefing(db: Session) -> Insight:
    patients = db.scalars(select(Patient).order_by(Patient.id)).all()
    roster: list[dict[str, Any]] = []
    hash_parts: list[str] = []
    for patient in patients:
        assessment = _latest_assessment(db, patient.id)
        reason = get_patient_insight(db, InsightKind.WORKLIST_REASON, patient.id)
        roster.append(
            {
                "name": patient.name,
                "priority": str(assessment.risk_level),
                "reason": reason.content.get("reason", ""),
                "postop_day": assessment.analytics.get("postop_day"),
                "procedure": patient.procedure_display,
            }
        )
        hash_parts.append(f"{patient.id}:{assessment.input_hash}:{assessment.risk_level}")

    cache_hash = hashlib.sha256(
        (";".join(hash_parts) + f":{PROMPT_VERSION}:{provider_name()}").encode()
    ).hexdigest()

    cached = _cached(db, None, InsightKind.DAILY_BRIEFING, cache_hash)
    if cached is not None:
        return cached

    # sort: high first for the prompt/template
    order = {"high": 0, "medium": 1, "missing_data": 2, "low": 3}
    roster.sort(key=lambda p: order.get(p["priority"], 4))

    content: dict[str, Any] | None = None
    provider = provider_name()
    if provider != "fallback":
        try:
            raw = complete_json(SYSTEM, briefing_prompt(roster), temperature=0.6)
            content = _validate(InsightKind.DAILY_BRIEFING, raw)
        except LLMError as e:
            logger.warning("LLM briefing failed: %s", e)

    if content is None:
        provider = "fallback"
        content = fallback.daily_briefing(roster)

    return _persist(db, None, InsightKind.DAILY_BRIEFING, content, cache_hash, provider)
