"""RTM documentation generation (SPEC.md §7): encounter notes and monthly
summaries. Same discipline as insights.py — the LLM drafts, validation
enforces the clinical-safety rules, the deterministic template replaces any
violation, and nothing is ever auto-approved: providers review every draft.
"""

import json
import logging
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.llm.insights import BANNED, _strings, _transcript
from app.llm.prompts import SYSTEM
from app.llm.provider import LLMError, complete_json, model_name, provider_name
from app.models.enums import GUARDRAIL_SENTENCE, DocumentKind, DocumentStatus
from app.models.insight import RiskAssessment
from app.models.patient import Patient
from app.models.rtm import ProviderTimeLog, RtmDocument, RtmInteraction

logger = logging.getLogger(__name__)

CONTRACTS: dict[DocumentKind, str] = {
    DocumentKind.ENCOUNTER_NOTE: (
        '{"title": "<max 60 chars, e.g. \\"RTM encounter note — postop day 14\\">", '
        '"body": "<120-220 words: current recovery status with the signals that moved, '
        "what the patient reported, treatment-management activity this month (minutes, "
        "interactions), and the plan. Written as a clinical note a provider signs. End "
        f'with exactly this sentence: {GUARDRAIL_SENTENCE}">}}'
    ),
    DocumentKind.MONTHLY_SUMMARY: (
        '{"title": "<max 60 chars, e.g. \\"RTM monthly summary — July 2026\\">", '
        '"body": "<120-220 words: monitoring coverage for the month (days, adherence), '
        "recovery trend against the expected curve, provider review time and patient "
        "interactions, and readiness against CMS RTM requirements. End with exactly "
        f'this sentence: {GUARDRAIL_SENTENCE}">}}'
    ),
}


def _validate(content: dict[str, Any]) -> dict[str, Any] | None:
    try:
        title = str(content["title"]).strip()[:60]
        body = str(content["body"]).strip()
    except (KeyError, TypeError):
        return None
    if not title or len(body) < 80:
        return None
    if not body.endswith(GUARDRAIL_SENTENCE):
        body = f"{body.rstrip()} {GUARDRAIL_SENTENCE}"
    normalized = {"title": title, "body": body}
    for text in _strings(normalized):
        if BANNED.search(text.replace(GUARDRAIL_SENTENCE, "")):
            return None
    return normalized


def _month_context(db: Session, patient_id: str, today: date) -> dict[str, Any]:
    from datetime import datetime, time, timedelta

    since = datetime.combine(today - timedelta(days=29), time.min)
    seconds = db.scalar(
        select(func.coalesce(func.sum(ProviderTimeLog.seconds), 0)).where(
            ProviderTimeLog.patient_id == patient_id, ProviderTimeLog.occurred_at >= since
        )
    ) or 0
    interactions = db.scalars(
        select(RtmInteraction)
        .where(RtmInteraction.patient_id == patient_id)
        .order_by(RtmInteraction.occurred_at.desc())
        .limit(8)
    ).all()
    return {
        "provider_minutes": int(seconds // 60),
        "recent_interactions": [
            {"kind": str(i.kind), "detail": i.detail, "at": i.occurred_at.date().isoformat()}
            for i in interactions
        ],
    }


def _fallback(
    kind: DocumentKind,
    patient: Patient,
    analytics: dict[str, Any],
    month_ctx: dict[str, Any],
    readiness: dict[str, Any],
    month: str,
) -> dict[str, Any]:
    postop = analytics.get("postop_day", "?")
    reasons = [r["text"] for r in analytics.get("risk", {}).get("reasons", [])[:3]]
    findings = "; ".join(reasons) if reasons else "recovery tracking as expected"
    minutes = month_ctx["provider_minutes"]
    days = readiness["monitoring"]["days"]

    if kind == DocumentKind.ENCOUNTER_NOTE:
        title = f"RTM encounter note — postop day {postop}"
        body = (
            f"{patient.name}, {patient.procedure_display}, postop day {postop}. "
            f"Monitoring signals this period: {findings}. "
            f"Remote therapeutic monitoring active with {days} monitoring days in the "
            f"current 30-day window. Treatment management this month: {minutes} minutes "
            f"of provider review"
            + (
                " including live patient interaction. "
                if readiness["treatment_management"]["interactive_communication"]
                else "; no live interaction logged yet. "
            )
            + "Plan: continue daily therapeutic check-ins per assigned recovery pathway. "
            f"{GUARDRAIL_SENTENCE}"
        )
    else:
        title = f"RTM monthly summary — {month}"
        body = (
            f"{patient.name} ({patient.procedure_display}) completed {days} monitoring "
            f"days in the current 30-day window "
            f"({'meets' if readiness['monitoring']['eligible'] else 'below'} the "
            f"16-day threshold). Monitoring signals: {findings}. Provider review time: "
            f"{minutes} minutes"
            + (
                " with live patient interaction. "
                if readiness["treatment_management"]["interactive_communication"]
                else "; live interaction still required. "
            )
            + f"Suggested next step: {readiness['suggested_action']} "
            f"{GUARDRAIL_SENTENCE}"
        )
    return {"title": title, "body": body}


def get_document(
    db: Session, patient: Patient, kind: DocumentKind, today: date | None = None,
    force: bool = False,
) -> RtmDocument:
    """Return this month's draft (or approved) document, generating on demand."""
    from app.engine.pipeline import latest_assessment
    from app.rtm.readiness import compute_readiness

    today = today or date.today()
    month = f"{today.year:04d}-{today.month:02d}"

    existing = db.scalar(
        select(RtmDocument)
        .where(
            RtmDocument.patient_id == patient.id,
            RtmDocument.kind == kind,
            RtmDocument.month == month,
        )
        .order_by(RtmDocument.id.desc())
        .limit(1)
    )
    if existing is not None and not force:
        return existing
    if existing is not None and existing.status == DocumentStatus.APPROVED:
        # Approved documentation is signed — regeneration would falsify it.
        return existing

    assessment: RiskAssessment | None = latest_assessment(db, patient.id)
    analytics = assessment.analytics if assessment else {}
    month_ctx = _month_context(db, patient.id, today)
    readiness = compute_readiness(db, patient, today)

    content: dict[str, Any] | None = None
    provider = provider_name()
    if provider != "fallback":
        payload = {
            "patient": {
                "name": patient.name,
                "procedure": patient.procedure_display,
                "postop_day": analytics.get("postop_day"),
            },
            "analytics_risk": analytics.get("risk"),
            "trajectory": analytics.get("trajectory"),
            "month": month,
            "treatment_management": month_ctx,
            "rtm_readiness": {
                "monitoring_days": readiness["monitoring"]["days"],
                "interactive_communication": readiness["treatment_management"][
                    "interactive_communication"
                ],
                "suggested_action": readiness["suggested_action"],
            },
            "recent_checkin_messages": _transcript(db, patient.id)[-16:],
        }
        try:
            raw = complete_json(
                SYSTEM,
                f"Data:\n{json.dumps(payload, default=str)}\n\n"
                f"Produce JSON matching exactly this contract:\n{CONTRACTS[kind]}",
                num_predict=900,  # docs run longer than insights; avoid Ollama truncation
                temperature=0.4,
            )
            content = _validate(raw)
            if content is None:
                logger.warning("Doc LLM output failed validation for %s/%s", patient.id, kind)
        except LLMError as e:
            logger.warning("Doc LLM call failed for %s/%s: %s", patient.id, kind, e)

    if content is None:
        provider = "fallback"
        content = _fallback(kind, patient, analytics, month_ctx, readiness, month)

    if existing is not None:
        existing.content = content
        existing.llm_provider = provider
        existing.model = model_name() if provider != "fallback" else None
        db.commit()
        return existing

    document = RtmDocument(
        patient_id=patient.id,
        kind=kind,
        content=content,
        llm_provider=provider,
        model=model_name() if provider != "fallback" else None,
        status=DocumentStatus.DRAFT,
        month=month,
    )
    db.add(document)
    db.commit()
    return document
