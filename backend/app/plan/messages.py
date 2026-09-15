"""Message templates and the intent/tone-aware draft.

The template library is the console's quick picks (``{first}`` and
``{surgeon}`` are filled at draft time). ``draft_patient_message`` extends
the existing ``app/llm/draft.py`` draft — the same prompt register, the same
deterministic fallback by reason code, reused by import — with what the
clinician wants said (``intent``), how (``tone``) and, optionally, a template
to personalize. Sending stays the patient-app session's ``/actions/message``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.draft import DRAFT_SYSTEM, _fallback_draft
from app.llm.insights import BANNED, _transcript
from app.llm.provider import (
    LLMError,
    complete_json,
    note_invalid_output,
    note_valid_output,
    provider_name,
)
from app.models.library import MessageTemplate
from app.models.patient import Patient

logger = logging.getLogger(__name__)

TONES = ("warm", "direct", "encouraging")
MESSAGE_MAX = 320
MESSAGE_MIN = 20


@dataclass(frozen=True)
class MessageSpec:
    key: str
    title: str
    body: str
    tags: tuple[str, ...]
    tone: str = "warm"
    pinned: bool = False


MESSAGE_LIBRARY: list[MessageSpec] = [
    MessageSpec("msg_checkin_nudge", "Check-in nudge",
                "Hi {first} — Dr. {surgeon}'s team here. We haven't heard from you in a couple "
                "of days. Could you do a quick check-in today so we know how you're getting on?",
                ("engagement",), pinned=True),
    MessageSpec("msg_temperature_ask", "Ask about temperature and the incision",
                "Hi {first} — Dr. {surgeon}'s team here. Could you take your temperature this "
                "morning and let us know how the incision looks — any warmth, redness or "
                "drainage? Reply here; it helps us keep a close eye on things.",
                ("surveillance", "wound"), pinned=True),
    MessageSpec("msg_walk_encourage", "Encourage walking",
                "Hi {first} — Dr. {surgeon}'s team. Recovery takes time, and short walks are the "
                "best medicine right now. How is the walking going? A few extra minutes today "
                "would be great.",
                ("activity",), "encouraging", pinned=True),
    MessageSpec("msg_ice_elevate", "Ice and elevate",
                "Hi {first} — a quick reminder from Dr. {surgeon}'s team: after each walk, put "
                "your feet up and ice for a little while. It keeps the swelling down and makes "
                "the next walk easier.",
                ("pain", "swelling"), pinned=True),
    MessageSpec("msg_sleep_position", "Night pain and positioning",
                "Hi {first} — Dr. {surgeon}'s team. Sounds like nights have been rough. Try a "
                "pillow to support the leg and take your evening pain medicine before bed. Tell "
                "us in today's check-in how last night went.",
                ("pain", "sleep")),
    MessageSpec("msg_device_sync", "Device sync reminder",
                "Hi {first} — Dr. {surgeon}'s team. Your watch hasn't synced in a few days. "
                "Could you charge it and wear it tonight? It helps us follow your recovery.",
                ("device",)),
    MessageSpec("msg_exercise_nudge", "Exercise nudge",
                "Hi {first} — Dr. {surgeon}'s team. Those daily exercises make a real "
                "difference. Is anything getting in the way? Let us know and we can adjust "
                "the plan.",
                ("adherence",)),
    MessageSpec("msg_appointment_sooner", "Bring the appointment forward",
                "Hi {first} — Dr. {surgeon}'s team here. We'd like to see you a little sooner "
                "than planned. Could you call the office today to move your appointment up?",
                ("follow-up",), "direct"),
    MessageSpec("msg_wound_photo", "Ask for a wound photo",
                "Hi {first} — Dr. {surgeon}'s team. Could you send a photo of the incision in "
                "the app today? It lets us check on healing without a visit.",
                ("wound",)),
    MessageSpec("msg_great_progress", "Great progress",
                "Hi {first} — Dr. {surgeon}'s team here. You're doing really well. Keep up the "
                "daily check-ins and walks, and tell us right away if anything changes.",
                ("encouragement",), "encouraging"),
    MessageSpec("msg_weight_reminder", "Daily weight reminder",
                "Hi {first} — Dr. {surgeon}'s team. A quick reminder to weigh yourself first "
                "thing each morning, before breakfast, and log it in the app. It's the earliest "
                "sign of fluid building up.",
                ("chronic", "weight")),
    MessageSpec("msg_bp_reminder", "Blood-pressure log reminder",
                "Hi {first} — Dr. {surgeon}'s team. Could you take your blood pressure this "
                "morning and this evening, seated and rested, and log both readings? It shows "
                "us whether the plan is working.",
                ("chronic", "bp")),
    MessageSpec("msg_breathing_check", "Breathing check",
                "Hi {first} — Dr. {surgeon}'s team here. How is your breathing today compared "
                "with a normal day for you? Let us know in the app, and tell us right away if it "
                "feels harder than usual.",
                ("chronic", "breathing")),
]

MESSAGE_BY_KEY: dict[str, MessageSpec] = {m.key: m for m in MESSAGE_LIBRARY}


def ensure_message_library(db: Session) -> int:
    existing = {
        t.key: t for t in db.scalars(
            select(MessageTemplate).where(MessageTemplate.key.is_not(None))
        )
    }
    created = 0
    for spec in MESSAGE_LIBRARY:
        row = existing.get(spec.key)
        fields = dict(title=spec.title, body=spec.body, tone=spec.tone, tags=list(spec.tags),
                      source="library", created_by="library")
        if row is None:
            db.add(MessageTemplate(key=spec.key, pinned=spec.pinned, **fields))
            created += 1
        else:
            for name, value in fields.items():
                if getattr(row, name) != value:
                    setattr(row, name, value)
    db.commit()
    return created


def message_payload(t: MessageTemplate) -> dict[str, Any]:
    return {
        "id": t.id, "key": t.key, "title": t.title, "body": t.body, "tone": t.tone,
        "tags": list(t.tags or []), "source": t.source, "pinned": bool(t.pinned),
        "archived": bool(t.archived), "usage_count": int(t.usage_count or 0),
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _names(patient: Patient) -> tuple[str, str]:
    first = (patient.name or "there").split()[0]
    surgeon = getattr(getattr(patient, "surgeon", None), "name", "") or "your surgeon"
    return first, surgeon.replace("Dr. ", "")


def fill_template(body: str, patient: Patient) -> str:
    first, surgeon = _names(patient)
    return body.replace("{first}", first).replace("{surgeon}", surgeon)


_PRONOUNS = [
    (re.compile(r"\b(her|his|their)\b", re.IGNORECASE), "your"),
    (re.compile(r"\b(she|he|they)\b", re.IGNORECASE), "you"),
    (re.compile(r"\b(herself|himself|themselves)\b", re.IGNORECASE), "yourself"),
    (re.compile(r"\bthe patient\b", re.IGNORECASE), "you"),
]
_LEADS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(?:please\s+)?remind(?:er)?\s+(?:her|him|them|the patient)?\s*(?:to\s+)?",
                re.IGNORECASE), "a quick reminder to "),
    (re.compile(r"^(?:please\s+)?ask\s+(?:her|him|them|the patient)?\s*(?:to\s+)?(?:about\s+)?",
                re.IGNORECASE), "could you "),
    (re.compile(r"^(?:please\s+)?tell\s+(?:her|him|them|the patient)?\s*(?:to\s+)?",
                re.IGNORECASE), "please "),
    (re.compile(r"^(?:please\s+)?(?:encourage|congratulate)\s+(?:her|him|them|the patient)?\s*"
                r"(?:to\s+|on\s+)?", re.IGNORECASE), "keep going with "),
    (re.compile(r"^(?:please\s+)?check\s+(?:on\s+|whether\s+|if\s+)?", re.IGNORECASE),
     "could you let us know "),
]


def intent_fallback(patient: Patient, intent: str, tone: str = "warm") -> str:
    """A deterministic message from the clinician's intent: the lead verb
    becomes the patient-facing frame, pronouns turn second person, and the
    tone picks the greeting and the sign-off."""
    first, surgeon = _names(patient)
    body = " ".join((intent or "").split()).rstrip(".!")
    asked = False
    for pattern, lead in _LEADS:
        if pattern.match(body):
            body = lead + pattern.sub("", body, count=1)
            asked = lead.startswith("could you")
            break
    for pattern, replacement in _PRONOUNS:
        body = pattern.sub(replacement, body)
    body = body[:1].upper() + body[1:]
    body = body + ("?" if asked else ".")
    if tone == "direct":
        text = f"{first}, Dr. {surgeon}'s team: {body} Reply here with any questions."
    elif tone == "encouraging":
        text = f"Hi {first} — you're doing great. Dr. {surgeon}'s team here: {body} Keep it up!"
    else:
        text = f"Hi {first} — Dr. {surgeon}'s team here. {body} Reply here if anything feels off."
    return text[:MESSAGE_MAX]


def _valid(message: str) -> bool:
    return MESSAGE_MIN <= len(message) <= MESSAGE_MAX and not BANNED.search(message)


def draft_patient_message(
    db: Session, patient: Patient, *, intent: str | None = None, tone: str = "warm",
    template_id: int | None = None,
) -> dict[str, Any]:
    from app.engine.pipeline import latest_assessment

    tone = tone if tone in TONES else "warm"
    template = db.get(MessageTemplate, template_id) if template_id is not None else None
    if template_id is not None and template is None:
        raise ValueError(f"Unknown message template {template_id}")
    assessment = latest_assessment(db, patient.id)
    reasons = list(assessment.reasons) if assessment is not None else []
    template_body = fill_template(template.body, patient) if template else None
    intent = " ".join((intent or "").split())[:400] or None

    provider = provider_name()
    if provider != "fallback":
        analytics = assessment.analytics if assessment is not None else {}
        context = {
            "patient_first_name": _names(patient)[0],
            "pathway": patient.procedure_display,
            "day_in_program": analytics.get("postop_day"),
            "priority": str(assessment.risk_level) if assessment else None,
            "reasons": [r.get("text") for r in reasons],
            "patient_said_recently": [
                m["text"] for m in _transcript(db, patient.id, 2) if m["who"] == "patient"
            ][-5:],
            "care_team": f"Dr. {_names(patient)[1]}",
            "clinician_intent": intent,
            "tone": tone,
            "template_body": template_body,
        }
        system = DRAFT_SYSTEM + (
            "\nWhen 'clinician_intent' is given, the message must say that, in the patient's "
            "words. Match 'tone' (warm | direct | encouraging). When 'template_body' is given, "
            "personalize it: keep its meaning, keep it under 320 characters."
        )
        try:
            raw = complete_json(system, f"Context:\n{json.dumps(context, default=str)}",
                                num_predict=220)
            message = str(raw.get("message", "")).strip()
            if _valid(message):
                note_valid_output(provider)
                return {"message": message, "provider": provider,
                        "template_id": template.id if template else None, "tone": tone}
            logger.warning("Message draft failed validation; using fallback")
            note_invalid_output(provider)
        except LLMError as e:
            logger.warning("Message draft LLM call failed: %s", e)

    if template_body:
        message = template_body
    elif intent:
        message = intent_fallback(patient, intent, tone)
    else:
        message = _fallback_draft(patient, reasons)
    return {"message": message[:MESSAGE_MAX], "provider": "fallback",
            "template_id": template.id if template else None, "tone": tone}


__all__ = [
    "MESSAGE_LIBRARY", "MESSAGE_BY_KEY", "TONES", "ensure_message_library", "message_payload",
    "fill_template", "intent_fallback", "draft_patient_message",
]
