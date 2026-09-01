"""AI-drafted patient messages — clinician reviews and edits before queueing.

Grounded in the clinical literature on LLM draft replies (drafts are used in
~58% of clinician responses when offered); the draft is ALWAYS editable and
never sends itself.
"""

import json
import logging
from typing import Any

from app.llm.insights import BANNED, _transcript
from app.llm.provider import LLMError, complete_json, provider_name

logger = logging.getLogger(__name__)

DRAFT_SYSTEM = """You draft short check-in messages from an orthopedic care team to a \
recovering patient. Plain, warm, 6th-grade language. Reference what the patient reported \
and what the monitoring shows, in everyday words — no clinical jargon, no alarm, and \
absolutely no diagnostic claims (never "infection", "detected", "diagnosis"). One concrete \
ask or encouragement. Max 280 characters. Respond with a single JSON object:
{"message": "<the message text>"}"""

_FALLBACK_BY_CODE: list[tuple[str, str]] = [
    ("TEMP_RISING", "Hi {first} — checking in from Dr. {surgeon}'s team. Could you take your temperature this morning and tell the check-in assistant the reading? It helps us keep an eye on things."),
    ("RHR_RISING", "Hi {first} — it's Dr. {surgeon}'s team. How are you feeling today? Please do your check-in this morning so we can see how things are trending."),
    ("TRAJECTORY_BEHIND", "Hi {first} — Dr. {surgeon}'s team here. Recovery takes time, and we'd like to hear how your walking is going. A short check-in today would really help."),
    ("SLEEP_DISRUPTED", "Hi {first} — Dr. {surgeon}'s team. Sounds like nights have been rough. Tell us more in today's check-in so we can help you rest better."),
    ("LOW_COVERAGE", "Hi {first} — Dr. {surgeon}'s team. Your watch hasn't synced in a few days. Could you charge it and wear it today? It helps us follow your recovery."),
    ("ADHERENCE_LOW", "Hi {first} — Dr. {surgeon}'s team. Those daily exercises make a real difference. Anything getting in the way? Let us know in today's check-in."),
]

_DEFAULT_DRAFT = "Hi {first} — Dr. {surgeon}'s team. You're doing well — keep up the daily check-ins and exercises, and tell us right away if anything changes."


def _fallback_draft(patient: Any, reasons: list[dict[str, Any]]) -> str:
    first = patient.name.split()[0]
    surgeon = patient.surgeon.name.replace("Dr. ", "")
    codes = {r["code"] for r in reasons}
    for code, template in _FALLBACK_BY_CODE:
        if code in codes:
            return template.format(first=first, surgeon=surgeon)
    return _DEFAULT_DRAFT.format(first=first, surgeon=surgeon)


def draft_message(db, patient, assessment) -> dict[str, str]:
    provider = provider_name()
    if provider != "fallback":
        analytics = assessment.analytics
        context = {
            "patient_first_name": patient.name.split()[0],
            "procedure": patient.procedure_display,
            "postop_day": analytics.get("postop_day"),
            "priority": str(assessment.risk_level),
            "reasons": [r["text"] for r in assessment.reasons],
            "patient_said_recently": [m["text"] for m in _transcript(db, patient.id, 2) if m["who"] == "patient"][-5:],
            "care_team": patient.surgeon.name,
        }
        try:
            raw = complete_json(
                DRAFT_SYSTEM, f"Context:\n{json.dumps(context, default=str)}", num_predict=200
            )
            message = str(raw.get("message", "")).strip()
            if 20 <= len(message) <= 320 and not BANNED.search(message):
                return {"message": message, "provider": provider}
            logger.warning("Draft failed validation; using fallback")
        except LLMError as e:
            logger.warning("Draft LLM call failed: %s", e)
    return {"message": _fallback_draft(patient, assessment.reasons), "provider": "fallback"}
