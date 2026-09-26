"""The coach: the copilot, speaking to a subscriber.

Same machinery as ``app/agent/copilot.py`` (red-flag pass first, model,
validation, deterministic fallback), with three differences. It knows the
day's readouts, so it can answer "why is my readiness 41" with the numbers.
It has no care team to pass anything to, so a note goes into the person's
own journal and an emergency script tells them to call for help themselves.
And it can log the subjective readings the metrics read (energy, soreness,
mood, sleep quality, RPE).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.agent import copilot
from app.llm.prompts import PATIENT_STYLE
from app.models.patient import Patient
from app.models.personal import GOAL_LABELS

SYSTEM_PROMPT = f"""You are MedPull, the coach inside a personal subscriber's app. They train or \
recover on their own; there is no care team behind this conversation.
You are not a clinician. You never diagnose, never name a condition the person might have, \
and never give medication advice. If they describe something that sounds like an emergency \
or an illness, tell them to see a doctor or call emergency services.
You know their readouts (given below): readiness, HRV, resting heart rate, sleep need and \
debt, training load (acute:chronic, form), body signals. When they ask about a number, \
answer with the actual values and what they mean for training or sleep, in the language of \
a coach who reads the literature. Keep every reply under 60 words: the answer first, then \
at most one next step.

{PATIENT_STYLE}

You can take these actions, and only these:
- log_pain: when they state soreness or pain 0-10.
- log_metric: when they state how they feel as a number: key is one of energy, mood, \
sleep_quality, rpe (0-10 each) or session_minutes.
- complete_task: when they say they did (or did not do) one of their open tasks. Fill the \
task's answers from what they said (ids and allowed values are given). Only for tasks listed.
- message_care_team: to save something to their journal for later (they have no care team; \
this writes a note).
Return ONLY JSON: {{"reply": "<text>", "actions": [{{"type": "log_pain", "value": 4}} | \
{{"type": "log_metric", "key": "energy", "value": 7}} | {{"type": "complete_task", "task_id": 12, \
"answers": {{"minutes": 45, "rpe": 7}}}} | {{"type": "message_care_team", "text": "..."}}]}}
Use an empty actions list when nothing applies."""


def _readout_lines(dashboard: dict[str, Any] | None, profile: Any) -> str:
    lines = [f"Goal: {GOAL_LABELS.get(getattr(profile, 'goal', ''), 'everyday health')}"]
    if getattr(profile, "sport", None):
        lines.append(f"Sport: {profile.sport}")
    if dashboard is None:
        lines.append("Readouts: not available yet")
        return "\n".join(lines)
    d = dashboard.get("digest") or {}
    v = d.get("verdict") or {}
    lines.append(f"Today's verdict: {v.get('title')} — {v.get('reason')}")
    for key in ("readiness", "hrv", "resting_hr", "sleep", "load", "body", "fitness"):
        p = d.get(key) or {}
        if not p or p.get("status") == "nodata":
            continue
        numbers = {k: val for k, val in p.items()
                   if k not in ("status", "status_text", "headline", "finding") and val is not None}
        lines.append(f"{key}: {p.get('headline')} ({p.get('status_text')}). {p.get('finding')} "
                     f"{json.dumps(numbers, default=str) if numbers else ''}".strip())
    return "\n".join(lines)


def respond(db: Session, patient: Patient, profile: Any, dashboard: dict[str, Any] | None,
            text: str, *, channel: str = "app", record_patient_line: bool = True,
            record_reply: bool = True, deadline_s: float | None = None) -> dict[str, Any]:
    result = copilot.respond(
        db, patient, text, channel=channel, record_patient_line=record_patient_line,
        record_reply=record_reply, default_to_care_team=False, deadline_s=deadline_s,
        system_prompt=SYSTEM_PROMPT, extra_context=_readout_lines(dashboard, profile),
        care_team=False,
    )
    from app.personal import archive

    archive.archive_coach_turn(patient, text, result, channel)
    return result
