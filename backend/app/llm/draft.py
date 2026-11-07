"""AI-drafted patient messages — clinician reviews and edits before queueing.

Grounded in the clinical literature on LLM draft replies (drafts are used in
~58% of clinician responses when offered); the draft is ALWAYS editable and
never sends itself.
"""

import json
import logging
from typing import Any

from app.llm.insights import BANNED, _transcript
from app.llm.prompts import PATIENT_STYLE
from app.llm.provider import (
    LLMError,
    complete_json,
    note_invalid_output,
    note_valid_output,
    provider_name,
)

logger = logging.getLogger(__name__)

DRAFT_SYSTEM = f"""You draft a short text message from an orthopedic care team to a \
recovering patient. Use the patient's first name and the care team name given. Mention \
one thing they reported or one thing the monitoring showed, in everyday words. Then make \
one clear ask (a check-in, a temperature reading, a walk) or one honest word of \
encouragement tied to something they did. Max 280 characters. No clinical terms, no \
alarm, and never "infection", "detected" or "diagnosis".

{PATIENT_STYLE}

Respond with a single JSON object:
{{"message": "<the message text>"}}"""

_FALLBACK_BY_CODE: list[tuple[str, str]] = [
    ("TEMP_RISING", "Hi {first} — checking in from Dr. {surgeon}'s team. Could you take your temperature this morning and tell the check-in assistant the reading? It helps us keep an eye on things."),
    ("RHR_RISING", "Hi {first} — it's Dr. {surgeon}'s team. How are you feeling today? Please do your check-in this morning so we can see how things are trending."),
    ("TRAJECTORY_BEHIND", "Hi {first} — Dr. {surgeon}'s team here. Recovery takes time, and we'd like to hear how your walking is going. A short check-in today would really help."),
    ("SLEEP_DISRUPTED", "Hi {first} — Dr. {surgeon}'s team. Sounds like nights have been rough. Tell us more in today's check-in so we can help you rest better."),
    ("LOW_COVERAGE", "Hi {first} — Dr. {surgeon}'s team. Your watch hasn't synced in a few days. Could you charge it and wear it today? It helps us follow your recovery."),
    ("ADHERENCE_LOW", "Hi {first} — Dr. {surgeon}'s team. Those daily exercises make a real difference. Anything getting in the way? Let us know in today's check-in."),
    # What the patient reported by check-in (engine/reported.py), in the
    # words of a clinic whose patients train between visits.
    ("LOAD_SPIKE", "Hi {first} — Dr. {surgeon}'s team here. Your training load jumped this week — hold at last week's numbers until your session with Dr. {surgeon}. Reply with how the {site} feels today."),
    ("WENT_QUIET", "Hi {first} — Dr. {surgeon}'s team here. Haven't heard from you in a few days — one tap: how's it going?"),
    ("NEW_PAIN", "Hi {first} — Dr. {surgeon}'s team here. You said the {site} is hurting more this week. Where exactly, and what sets it off? Reply here so Dr. {surgeon} can look before your next session."),
    ("PAIN_RISING", "Hi {first} — Dr. {surgeon}'s team here. You said the {site} is hurting more this week. Where exactly, and what sets it off? Reply here so Dr. {surgeon} can look before your next session."),
    ("PROGRAM_SLIPPING", "Hi {first} — Dr. {surgeon}'s team here. The program's slipped the last few days — what's getting in the way? Reply here and we'll fit it around your week."),
]

_DEFAULT_DRAFT = "Hi {first} — Dr. {surgeon}'s team. You're doing well — keep up the daily check-ins and exercises, and tell us right away if anything changes."


def _fallback_draft(patient: Any, reasons: list[dict[str, Any]]) -> str:
    from app.plan.messages import site_word, surname_for_dr

    first = patient.name.split()[0]
    surgeon = surname_for_dr(patient.surgeon.name)
    site = site_word(patient)
    codes = {r["code"] for r in reasons}
    for code, template in _FALLBACK_BY_CODE:
        if code in codes:
            return template.format(first=first, surgeon=surgeon, site=site)
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
                note_valid_output(provider)
                return {"message": message, "provider": provider}
            logger.warning("Draft failed validation; using fallback")
            note_invalid_output(provider)
        except LLMError as e:
            logger.warning("Draft LLM call failed: %s", e)
    return {"message": _fallback_draft(patient, assessment.reasons), "provider": "fallback"}
