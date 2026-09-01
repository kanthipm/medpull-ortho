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
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.llm import fallback
from app.llm.prompts import PROMPT_VERSION, SYSTEM, briefing_prompt, patient_prompt
from app.llm.provider import (
    LLMError,
    complete_json,
    model_name,
    note_invalid_output,
    note_valid_output,
    provider_name,
)
from app.models.checkin import Checkin
from app.models.enums import GUARDRAIL_SENTENCE, InsightKind
from app.models.insight import Insight, RiskAssessment
from app.models.patient import Patient

logger = logging.getLogger(__name__)

# Word-prefix match: catches detect/detected/detection, diagnose/diagnosis/...
BANNED = re.compile(r"\b(detect|diagnos)", re.IGNORECASE)

# Rows are keyed by an input hash that turns over on every engine recompute
# (and, because date.today() is in it, at least once a calendar day), so only
# the newest few of a (patient, kind) series can ever be read again. The rest
# are dead cache entries, and on Lambda the whole SQLite file is re-uploaded
# whenever they accumulate — so each write trims its own series.
KEEP_PER_SERIES = 6

# /ask is the exception, and treating it like the others was a cost regression
# in the shape of a cleanup. Every answer to every question lives in ONE
# (patient_id=NULL, kind='ask') series, so a cap of 6 evicts by recency across
# unrelated questions: with eight questions in rotation nothing is ever a hit
# again, and each round costs a fresh set of LLM calls forever. The rows are
# tiny and a clinician's rotation is not, so the cap is a bound on the table
# rather than a bound on the working set — and the real garbage, answers whose
# roster digest has turned over, is collected by age instead.
ASK_KEEP = 250
ASK_MAX_AGE_DAYS = 3


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


def _cached(
    db: Session,
    patient_id: str | None,
    kind: InsightKind,
    cache_hash: str,
    key_provider: str,
) -> Insight | None:
    """Reads the row for one cache key. `key_provider` is the provider the key
    was built from, which is what separates the two kinds of fallback row."""
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
    # A fallback row under a REAL-provider key is degraded output — written
    # during a transient LLM failure (e.g. a rate-limit burst) — and must not
    # satisfy that key permanently; treat it as a miss so the next read
    # retries the LLM. A fallback row under a fallback key is the intended
    # output of a deliberate skip and caches like any other row.
    if row is not None and row.llm_provider == "fallback" and key_provider != "fallback":
        return None
    return row


def _prune(db: Session, patient_id: str | None, kind: InsightKind) -> None:
    """Drops superseded rows of one (patient, kind) series, newest kept."""
    if kind == InsightKind.ASK:
        _prune_ask(db)
        return
    superseded = db.scalars(
        select(Insight.id)
        .where(Insight.patient_id == patient_id, Insight.kind == kind)
        .order_by(Insight.id.desc())
        .offset(KEEP_PER_SERIES)
    ).all()
    if superseded:
        db.execute(delete(Insight).where(Insight.id.in_(superseded)))


def _prune_ask(db: Session) -> None:
    """Age first, then a ceiling.

    An ask row dies when the roster digest baked into its key turns over,
    which happens at least daily — so anything a few days old is unreachable
    whatever question produced it. Recency across questions is NOT a proxy for
    that: the oldest surviving row is simply the question asked least
    recently, and evicting it is throwing away a cache hit."""
    cutoff = datetime.now() - timedelta(days=ASK_MAX_AGE_DAYS)
    db.execute(
        delete(Insight).where(
            Insight.kind == InsightKind.ASK, Insight.generated_at < cutoff
        )
    )
    overflow = db.scalars(
        select(Insight.id)
        .where(Insight.kind == InsightKind.ASK)
        .order_by(Insight.id.desc())
        .offset(ASK_KEEP)
    ).all()
    if overflow:
        db.execute(delete(Insight).where(Insight.id.in_(overflow)))


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
    db.flush()  # sessions run autoflush=False; the prune must see this row
    _prune(db, patient_id, kind)
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
    analytics = assessment.analytics

    # Stable patients' worklist reasons are pure status lines ("tracking as
    # expected") — the deterministic text is already exact, and skipping the
    # LLM keeps the worklist fast on cold caches. A deliberate skip is keyed
    # as what it produces, so the row it writes is a cache hit next time
    # rather than a fallback row sitting under a key that expects an LLM.
    skip_llm = (
        kind == InsightKind.WORKLIST_REASON
        and analytics.get("risk", {}).get("level") == "low"
    )
    provider = "fallback" if skip_llm else provider_name()

    digest = hashlib.sha256(json.dumps(transcript).encode()).hexdigest()[:16]
    # risk_level is included so prose can never lag a tier change, even if an
    # assessment is somehow regenerated under an unchanged input hash.
    cache_hash = hashlib.sha256(
        f"{kind}:{assessment.input_hash}:{assessment.risk_level}:{digest}:"
        f"{PROMPT_VERSION}:{provider}".encode()
    ).hexdigest()

    cached = _cached(db, patient_id, kind, cache_hash, provider)
    if cached is not None:
        return cached

    header = _header(patient, analytics.get("postop_day", 0))

    content: dict[str, Any] | None = None
    if provider != "fallback":
        try:
            # warm enough that a manual Refresh visibly rewrites the narrative
            raw = complete_json(
                SYSTEM, patient_prompt(kind, header, analytics, transcript), temperature=0.6
            )
            content = _validate(kind, raw)
            if content is None:
                logger.warning("LLM output for %s/%s failed validation; using fallback", patient_id, kind)
                note_invalid_output(provider)
            else:
                note_valid_output(provider)
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
    assessments = [(patient, _latest_assessment(db, patient.id)) for patient in patients]

    provider = provider_name()
    cache_hash = hashlib.sha256(
        (
            ";".join(f"{p.id}:{a.input_hash}:{a.risk_level}" for p, a in assessments)
            + f":{PROMPT_VERSION}:{provider}"
        ).encode()
    ).hexdigest()

    # The cache is consulted before the roster is built: each roster entry
    # costs a per-patient insight lookup, so a warm briefing has to be free.
    cached = _cached(db, None, InsightKind.DAILY_BRIEFING, cache_hash, provider)
    if cached is not None:
        return cached

    roster: list[dict[str, Any]] = []
    for patient, assessment in assessments:
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

    # sort: high first for the prompt/template
    order = {"high": 0, "medium": 1, "missing_data": 2, "low": 3}
    roster.sort(key=lambda p: order.get(p["priority"], 4))

    content: dict[str, Any] | None = None
    if provider != "fallback":
        try:
            raw = complete_json(SYSTEM, briefing_prompt(roster), temperature=0.6)
            content = _validate(InsightKind.DAILY_BRIEFING, raw)
            if content is None:
                logger.warning("LLM briefing output failed validation; using fallback")
                note_invalid_output(provider)
            else:
                note_valid_output(provider)
        except LLMError as e:
            logger.warning("LLM briefing failed: %s", e)

    if content is None:
        provider = "fallback"
        content = fallback.daily_briefing(roster)

    return _persist(db, None, InsightKind.DAILY_BRIEFING, content, cache_hash, provider)
