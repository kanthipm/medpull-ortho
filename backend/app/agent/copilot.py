"""The patient-facing copilot: the voice in the app's Talk screen, the chat
box, and whatever a patient texts that is not an answer to a task question.

It is deliberately narrow. It can log pain, complete a task from what the
patient said, pass a message to the care team, and answer "what do I have to
do today". It never interprets symptoms: a deterministic red-flag pass runs
before any model call, and its text — call the clinic, or 911 — is what the
patient reads, with the care team alerted in the same transaction. Model
output is validated against the same banned-language rule as the console's
narratives (``detect…`` / ``diagnos…``) and replaced by the deterministic
reply when it fails.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.prompts import PATIENT_STYLE
from app.llm.provider import (
    LLMError,
    complete_json,
    note_invalid_output,
    note_valid_output,
    provider_name,
)
from app.models.adherence import AdherenceTask
from app.models.checkin import Checkin, CheckinMessage
from app.models.mobile import Message
from app.models.patient import Patient
from app.tasks import service as tasks

logger = logging.getLogger(__name__)

MAX_REPLY_CHARS = 420

# (pattern, what the patient reads, what the care team is told)
RED_FLAGS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"chest pain|can'?t breathe|cannot breathe|short(ness)? of breath|trouble breathing|hard to breathe", re.I),
        "Chest pain or trouble breathing can be an emergency. Please call 911 now. I've alerted your care team.",
        "Reported chest pain or trouble breathing",
    ),
    (
        re.compile(r"calf (pain|swelling|cramp|tight)|(leg|calf) (is |feels )?(hot|red|warm)", re.I),
        "New calf pain or swelling after surgery needs same-day attention. Please call your care team now — and 911 if you also have trouble breathing. I've alerted them.",
        "Reported calf pain or swelling",
    ),
    (
        re.compile(r"(pus|drainage|oozing|leaking|bleeding|opened up|coming apart).{0,40}(incision|wound|stitches|staples)|(incision|wound|stitches|staples).{0,40}(pus|drainage|oozing|leaking|bleeding|open)", re.I),
        "Drainage or bleeding from the incision is something your care team wants to see today. I've alerted them — please call the clinic if it's more than a small spot.",
        "Reported incision drainage or bleeding",
    ),
    (
        re.compile(r"\bfever\b|\bchills\b|temperature (of |is |was )?(10[1-9]|11\d)", re.I),
        "A fever after surgery is worth a same-day call. I've flagged it for your care team — if it's over 101°F, please call the clinic now.",
        "Reported fever or chills",
    ),
    (
        re.compile(r"\b(fell|fall|fallen|passed out|fainted|blacked out)\b", re.I),
        "I'm sorry — a fall after surgery needs to be checked. I've alerted your care team; if you hit your head or can't bear weight, please call 911.",
        "Reported a fall or fainting",
    ),
]

BANNED = re.compile(r"\b(diagnos\w*|detect\w*)\b|you (probably |likely |might )?have (an? )?(infection|blood clot|clot|dvt|pneumonia)", re.I)

SYSTEM_PROMPT = f"""You are MedPull, the recovery companion inside a patient's app after orthopedic surgery.
You are not a clinician. You never diagnose, never name a condition the patient might have, and never change their plan.
Keep every reply under 60 words. Answer what they asked first, in one or two sentences, then one next step at most. Send questions about symptoms, medication changes or appointments to their care team, and say you have passed it on when you do.

{PATIENT_STYLE}

You can take these actions, and only these:
- log_pain: when the patient states a pain level 0-10.
- complete_task: when the patient says they did (or did not do) one of their open tasks. Fill the task's answers from what they said (ids and allowed values are given). Only for tasks listed.
- message_care_team: when the patient wants something passed to their nurse, surgeon, PT or care team, or shares something they should know.
Return ONLY JSON: {{"reply": "<text>", "actions": [{{"type": "log_pain", "value": 4}} | {{"type": "complete_task", "task_id": 12, "answers": {{"exercises": "all"}}}} | {{"type": "message_care_team", "text": "..."}}]}}
Use an empty actions list when nothing applies."""

# The same companion for a patient who did not have surgery: their hospital
# follows their signals (steps, sleep, heart, weight...) and sends tasks.
GENERAL_SYSTEM_PROMPT = SYSTEM_PROMPT.replace(
    "the recovery companion inside a patient's app after orthopedic surgery",
    "the health companion inside a patient's app; this patient has NOT had surgery — "
    "their hospital's care team follows their everyday health signals",
)

# Red-flag wording assumes an operation; for a general patient the same
# advice reads without it.
_GENERAL_REPLACEMENTS = (
    (" after surgery", ""),
    ("I'm sorry — a fall needs to be checked", "I'm sorry — a fall needs to be checked"),
)


def _for_patient(text: str, patient: Patient) -> str:
    if tasks.surgical(patient):
        return text
    for old, new in _GENERAL_REPLACEMENTS:
        text = text.replace(old, new)
    return text


def _context(db: Session, patient: Patient, open_tasks: list[AdherenceTask]) -> str:
    from app.engine.pipeline import latest_assessment

    assessment = latest_assessment(db, patient.id)
    postop = None
    if assessment is not None:
        postop = (assessment.analytics or {}).get("postop_day")
    lines = [f"Patient first name: {patient.name.split()[0]}"]
    if tasks.surgical(patient):
        lines += [
            f"Procedure: {patient.procedure_display}",
            f"Post-op day: {postop if postop is not None else 'unknown'}",
        ]
    else:
        lines.append("No surgery: a general patient followed by their hospital's care team")
    lines.append("Open tasks:" if open_tasks else "Open tasks: none")
    for t in open_tasks:
        qs = tasks.questions_for(t)
        fields = ", ".join(
            f"{q['id']}: {'/'.join(q.get('options') or ['yes', 'no']) if q['kind'] in ('yes_no', 'choice') else q['kind']}"
            for q in qs
        )
        lines.append(f"- id {t.id} ({t.kind}): {t.title}. Answers: {fields}")
    recent = db.scalars(
        select(Message)
        .where(Message.patient_id == patient.id)
        .order_by(Message.id.desc())
        .limit(6)
    ).all()
    if recent:
        lines.append("Recent thread (newest last):")
        for m in reversed(recent):
            lines.append(f"  {m.sender}: {m.text[:160]}")
    return "\n".join(lines)


def _red_flags(text: str) -> list[tuple[str, str]]:
    return [(patient_text, team_text) for pat, patient_text, team_text in RED_FLAGS if pat.search(text)]


def fallback_intent(text: str, open_tasks: list[AdherenceTask], *, default_to_care_team: bool) -> dict[str, Any]:
    """Keyword intents for when no model is available (or its output was
    rejected). Conservative: when unsure it either lists the tasks or passes
    the text to the care team, never invents an action."""
    body = text.strip()
    lowered = body.lower()
    actions: list[dict[str, Any]] = []

    m = re.search(r"pain[^0-9]{0,20}(\d{1,2})\b|\b(\d{1,2})\s*(?:/|out of)\s*10\b", lowered)
    if m:
        value = int(m.group(1) or m.group(2))
        if 0 <= value <= 10:
            actions.append({"type": "log_pain", "value": value})

    if re.search(r"\b(done|finished|completed|did (it|them|all|my)|got (it|them) done|took (it|them|my))\b", lowered):
        target = next((t for t in open_tasks if t.kind != "checkin"), None)
        if target is not None:
            negative = re.search(r"\b(didn'?t|did not|couldn'?t|could not|skipped|missed|haven'?t)\b", lowered)
            answers: dict[str, Any] = {}
            if target.kind == "exercise":
                answers["exercises"] = "none" if negative else ("some" if "some" in lowered else "all")
            elif target.kind == "medication":
                answers["taken"] = "no" if negative else "yes"
            elif target.kind == "walk":
                mins = re.search(r"(\d{1,3})\s*(min|minute)", lowered)
                answers["minutes"] = int(mins.group(1)) if mins else (0 if negative else 10)
            elif target.kind == "custom":
                answers["done"] = "no" if negative else "yes"
            if answers:
                actions.append({"type": "complete_task", "task_id": target.id, "answers": answers})

    if re.search(r"\b(tell|message|ask|let|inform|notify|remind)\b.{0,12}\b(doctor|nurse|surgeon|care team|team|pt|therapist|clinic|dr\b)", lowered):
        actions.append({"type": "message_care_team", "text": body})
    elif default_to_care_team and not actions and not re.search(r"\b(tasks?|to ?do|today|help|what|how)\b", lowered):
        actions.append({"type": "message_care_team", "text": body})

    return {"reply": "", "actions": actions}


def _validate_model_output(raw: Any, open_ids: set[int]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    reply = raw.get("reply")
    if not isinstance(reply, str) or not reply.strip() or BANNED.search(reply):
        return None
    actions_in = raw.get("actions", [])
    if not isinstance(actions_in, list):
        return None
    actions: list[dict[str, Any]] = []
    for a in actions_in[:4]:
        if not isinstance(a, dict):
            return None
        kind = a.get("type")
        if kind == "log_pain":
            value = tasks._int(a.get("value"))
            if value is None or not 0 <= value <= 10:
                return None
            actions.append({"type": "log_pain", "value": value})
        elif kind == "complete_task":
            tid = tasks._int(a.get("task_id"))
            answers = a.get("answers")
            if tid is None or tid not in open_ids or not isinstance(answers, dict):
                return None
            actions.append({"type": "complete_task", "task_id": tid, "answers": answers})
        elif kind == "message_care_team":
            text = a.get("text")
            if not isinstance(text, str) or not text.strip():
                return None
            actions.append({"type": "message_care_team", "text": text.strip()[:1000]})
        elif kind in (None, "none"):
            continue
        else:
            return None
    return {"reply": reply.strip()[:MAX_REPLY_CHARS], "actions": actions}


def _log_pain(db: Session, patient: Patient, value: int, channel: str) -> None:
    checkin = Checkin(patient_id=patient.id, occurred_at=__import__("datetime").datetime.now(),
                      channel=channel if channel in ("app", "sms", "voice") else "app")
    db.add(checkin)
    db.flush()
    db.add(CheckinMessage(checkin_id=checkin.id, seq=0, who="copilot",
                          text="How's your pain today, 0 to 10?"))
    db.add(CheckinMessage(checkin_id=checkin.id, seq=1, who="patient",
                          text=f"My pain is about {value} out of 10."))


def _apply(
    db: Session, patient: Patient, actions: list[dict[str, Any]], channel: str,
    open_tasks: list[AdherenceTask],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run the validated actions. Returns (applied, sentences for the reply)."""
    applied: list[dict[str, Any]] = []
    notes: list[str] = []
    by_id = {t.id: t for t in open_tasks}
    for a in actions:
        if a["type"] == "log_pain":
            _log_pain(db, patient, a["value"], channel)
            applied.append(a)
            notes.append(f"Logged pain {a['value']}/10 for today.")
            if a["value"] >= tasks._ALERT_PAIN:
                tasks.notify_care_team(db, patient, f"{patient.name} — Reported pain {a['value']}/10",
                                       f"Told the copilot by {channel}.", "patient_report")
                notes.append("That's high — I've let your care team know.")
        elif a["type"] == "complete_task":
            task = by_id.get(a["task_id"])
            if task is None:
                continue
            try:
                tasks.complete_task(db, task, a["answers"], via=channel if channel in tasks.COMPLETION_CHANNELS else "app")
            except ValueError as e:
                notes.append(f"I couldn't mark \"{task.title}\" done: {e}")
                continue
            applied.append({**a, "title": task.title})
            notes.append(f"Marked \"{task.title}\" as done.")
        elif a["type"] == "message_care_team":
            # The patient's own line is already on the thread (recorded by
            # respond() or by the SMS handler); a second copy of it here
            # showed every forwarded note twice. The action's work is the
            # care-team notification.
            tasks.notify_care_team(db, patient, f"{patient.name} sent a message", a["text"], "patient_message")
            applied.append(a)
            notes.append("Passed that along to your care team.")
    return applied, notes


def _task_list_sentence(open_tasks: list[AdherenceTask]) -> str:
    if not open_tasks:
        return "You're all caught up — nothing is waiting today."
    titles = [t.title for t in open_tasks[:3]]
    more = len(open_tasks) - len(titles)
    joined = "; ".join(titles) + (f"; and {more} more" if more > 0 else "")
    return f"Today: {joined}. Tell me when you've done one and I'll log it."


def respond(
    db: Session,
    patient: Patient,
    text: str,
    *,
    channel: str = "app",
    record_patient_line: bool = True,
    record_reply: bool = True,
    default_to_care_team: bool = False,
) -> dict[str, Any]:
    """One turn. Records the patient's line and the reply on the thread
    (unless the caller does that itself) and returns what happened."""
    text = (text or "").strip()
    open_tasks = tasks.open_tasks(db, patient.id)
    if not text:
        reply = _task_list_sentence(open_tasks)
        return {"reply": reply, "actions": [], "flagged": False, "provider": "fallback"}

    if record_patient_line:
        db.add(Message(patient_id=patient.id, sender="patient", channel=channel, text=text[:2000]))
        db.flush()

    flags = _red_flags(text)
    for _patient_text, team_text in flags:
        tasks.notify_care_team(db, patient, f"{patient.name} — {team_text}",
                               f"Said by {channel}: \"{text[:240]}\"", "patient_report")

    provider = "fallback"
    intent: dict[str, Any] | None = None
    if not flags:  # a red flag gets the deterministic script, never a model's words
        try:
            raw = complete_json(
                SYSTEM_PROMPT if tasks.surgical(patient) else GENERAL_SYSTEM_PROMPT,
                f"{_context(db, patient, open_tasks)}\n\nPatient said: {json.dumps(text)}",
                num_predict=300,
                temperature=0.3,
            )
            active = provider_name()
            intent = _validate_model_output(raw, {t.id for t in open_tasks})
            if intent is None:
                note_invalid_output(active)
            else:
                note_valid_output(active)
                provider = active
        except LLMError:
            intent = None
    if intent is None:
        intent = fallback_intent(text, open_tasks, default_to_care_team=default_to_care_team)

    applied, notes = _apply(db, patient, intent["actions"], channel, open_tasks)

    if flags:
        reply = " ".join(dict.fromkeys(_for_patient(f, patient) for f, _ in flags))
        if notes:
            reply += " " + " ".join(notes)
    elif provider != "fallback" and intent["reply"]:
        reply = intent["reply"]
        # Only claim the actions that were actually applied.
        if applied and not any(n.split()[0].lower() in reply.lower() for n in notes):
            reply = (reply + " " + " ".join(notes)).strip()
    elif notes:
        reply = " ".join(notes)
    elif re.search(r"\b(tasks?|to ?do|today|what do i|help)\b", text.lower()):
        reply = _task_list_sentence(open_tasks)
    else:
        reply = ("Got it. " if not default_to_care_team else "") + (
            "I can log your pain, mark a task done, or pass a note to your care team — "
            "just say which. " + _task_list_sentence(open_tasks)
        )
    reply = reply[:MAX_REPLY_CHARS]

    if record_reply:
        db.add(Message(patient_id=patient.id, sender="copilot", channel=channel, text=reply))
    db.commit()
    return {"reply": reply, "actions": applied, "flagged": bool(flags), "provider": provider}
