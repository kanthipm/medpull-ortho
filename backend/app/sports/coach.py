"""The agent: the copilot speaking to an athlete.

Same machinery as ``app/agent/copilot.py`` (red-flag pass first, model,
validation, deterministic fallback), with the athlete's readouts,
performance tests, load, schedule and injury plan in context. It can log
wellness and a session, and it can pass a note to the staff when the
athlete is on a team; otherwise the note goes to their own journal.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.agent import copilot
from app.llm.prompts import PATIENT_STYLE
from app.models.mobile import Message
from app.models.patient import Patient
from app.models.sports import SPORT_LABELS
from app.sports import fallback

SYSTEM_PROMPT = f"""You are MedPull, the performance coach inside an athlete's app. They play {{sport}} \
{{context}}. You are not a clinician and not their coach of record. You never diagnose, never name a condition, \
never give medication advice, and never say whether they are cleared to play: the medical staff decide that. \
If they describe something that sounds like an emergency, tell them to get help now.
You know today's readouts (given below): readiness and its drivers, HRV, resting heart rate, sleep, training \
load, their wellness answers, their performance tests against their own baseline and their level, the team \
schedule, and the injury plan with its phase and criteria when there is one. When they ask about a number, \
answer with the actual values and what they mean for practice, recovery or sleep, in the language of a coach \
who reads the literature. Keep every reply under 70 words: the answer first, then at most one next step.

{PATIENT_STYLE}

You can take these actions, and only these:
- log_pain: when they state soreness or pain 0-10.
- log_metric: when they state how they feel as a number: key is one of energy, mood, sleep_quality, rpe \
(0-10 each) or session_minutes.
- complete_task: when they say they did (or did not do) one of their open tasks. Fill the task's answers from \
what they said (ids and allowed values are given). Only for tasks listed.
- message_care_team: to pass a note to their athletic trainer or coach (or to their journal when they are on \
their own).
Return ONLY JSON: {{{{"reply": "<text>", "actions": [{{{{"type": "log_pain", "value": 4}}}} | \
{{{{"type": "log_metric", "key": "energy", "value": 7}}}} | {{{{"type": "complete_task", "task_id": 12, \
"answers": {{{{"minutes": 90, "rpe": 7}}}}}}}} | {{{{"type": "message_care_team", "text": "..."}}}}]}}}}
Use an empty actions list when nothing applies."""


def _context_lines(home: dict[str, Any] | None, profile: Any) -> str:
    if home is None:
        return "Readouts: not available yet"
    rec = home.get("recovery") or {}
    perf = home.get("performance") or {}
    rehab = home.get("rehab") or {}
    v = rec.get("verdict") or {}
    d = rec.get("digest") or {}
    lines = [f"Today's verdict: {v.get('title')} — {v.get('reason')} {v.get('detail')}"]
    for key in ("readiness", "hrv", "resting_hr", "sleep", "load", "body", "fitness"):
        p = d.get(key) or {}
        if not p or p.get("status") == "nodata":
            continue
        numbers = {k: val for k, val in p.items() if k not in ("status", "status_text", "headline", "finding") and val is not None}
        lines.append(f"{key}: {p.get('headline')} ({p.get('status_text')}). {p.get('finding')} {json.dumps(numbers, default=str) if numbers else ''}".strip())
    w = rec.get("wellness") or {}
    if w.get("items"):
        lines.append("Wellness today: " + "; ".join(f"{i['label']} {i['value']:.0f}/10 (z {i['z']})" for i in w["items"]))
    load = rec.get("load") or {}
    lines.append(f"Load: week {load.get('week_load')} AU ({load.get('change_pct')}% vs last), monotony {load.get('monotony')}, "
                 f"ACWR {load.get('acwr')} (context only). {load.get('finding')}")
    s = rec.get("schedule") or {}
    lines.append(f"Schedule: {s.get('finding')}")
    n = rec.get("neuromuscular") or {}
    if n.get("status") not in (None, "nodata"):
        lines.append(f"Jump test: {n.get('status_text')}. {n.get('finding')}")
    for h in (perf.get("headline") or []):
        if h.get("logged"):
            band = h.get("band") or {}
            lines.append(f"Test {h['label']}: {h['latest_text']} {h['unit']} ({band.get('word')}, p{band.get('percentile')} for the level; "
                         f"{h.get('days_ago')} days ago)")
    for a in perf.get("asymmetries") or []:
        lines.append(f"Asymmetry {a['label']}: {a['asymmetry']['pct']}% weaker {a['asymmetry']['weaker']}")
    for b in (rehab.get("active") or [])[:1]:
        ph = b.get("phase") or {}
        rts = b.get("rts") or {}
        unmet = [c["label"] for c in ph.get("criteria") or [] if c.get("met") is not True]
        lines.append(f"Injury: {b.get('label')} ({b.get('side')}), {b.get('weeks')} wk since {b.get('anchor')}, phase {ph.get('number')}/{ph.get('of')} "
                     f"{ph.get('name')}; unmet gates: {', '.join(unmet) or 'none'}; RTS {rts.get('met')}/{rts.get('total')}; projected {rts.get('projected')}")
    tips = rec.get("suggestions") or []
    if tips:
        lines.append("Today's suggestions: " + " | ".join(f"{t['title']} ({t['evidence']}): {t['why']}" for t in tips[:3]))
    return "\n".join(lines)


def respond(db: Session, patient: Patient, profile: Any, home: dict[str, Any] | None, text: str, *,
            channel: str = "app", deadline_s: float | None = None) -> dict[str, Any]:
    sport = SPORT_LABELS.get(getattr(profile, "sport", ""), "their sport").lower()
    linked = bool(getattr(profile, "coach_linked", False))
    context = ("on a team whose athletic trainer and coaches can see what they share"
               if linked else "on their own, with no staff behind this conversation")
    system = SYSTEM_PROMPT.replace("{sport}", sport).replace("{context}", context)
    result = copilot.respond(
        db, patient, text, channel=channel, default_to_care_team=False, deadline_s=deadline_s,
        system_prompt=system, extra_context=_context_lines(home, profile), care_team=linked,
        allow_log_metric=True, record_reply=False,
    )
    reply = result["reply"]
    # Without a model the copilot can only log and list; an athlete asking
    # about a number gets the board's own words instead.
    if result.get("provider") == "fallback" and not result.get("flagged") and not result.get("actions"):
        answered = fallback.answer(text, home, profile)
        if answered:
            reply = answered
    db.add(Message(patient_id=patient.id, sender="copilot", channel=channel, text=reply, authored_by="ai"))
    db.commit()
    return {**result, "reply": reply}
