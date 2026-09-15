"""Prompt templates for the four insight kinds.

The system prompt enforces the product's clinical-safety register; the user
prompt carries the deterministic analytics (the LLM's ONLY source of numbers)
plus recent conversation excerpts, and states the exact JSON contract.
"""

import json
from typing import Any

from app.models.enums import GUARDRAIL_SENTENCE, InsightKind

# Bump to invalidate cached insights when prompt wording changes.
PROMPT_VERSION = "2"

# Shared writing rules. Every prompt that produces prose a person will read
# includes one of these two blocks, so the product speaks with one voice.
CLINICIAN_STYLE = """How to write:
- Write the way a good colleague talks at handoff. Short sentences. One idea per sentence.
- Say the specific thing: which signal, which direction, how much, since when. Do not \
call something important, notable, concerning or significant. Give the number and let \
the reader judge.
- Use everyday words. Never use: leverage, utilize, robust, holistic, comprehensive, \
multifaceted, notably, importantly, crucially, it's worth noting, in terms of, going \
forward, overall, ultimately, in conclusion, delve, underscore, highlight, showcase, \
foster, optimal, trajectory analysis, warrant, indicative.
- Hedge once where the data is thin ("may", "looks like"). Never stack hedges.
- No openers ("Here's the thing", "It's important to"), no closing recap, no rhetorical \
questions, no exclamation marks, no bullet lists inside a sentence.
- No dashes. Use commas or full stops. The only exception is the disclaimer sentence, \
which you copy exactly when the contract asks for it.
- Do not read the data back one metric per sentence. Put signals that belong together in \
one sentence ("chills, a warm knee, and temperature and heart rate both up since day 6"). \
Say what the picture means for this patient.
- Turn rates and codes into plain counts and words: "did 4 of 8 exercises", not "adherence \
0.5"; "about two thirds of the expected pace", not "68% of projected progress". Never \
write status labels like "flag", "watch", "risk: high" or "composite index" in prose.
- Say only what the data says. Never add a fact, an event or a reassurance the data does \
not contain."""

PATIENT_STYLE = """How to write to a patient:
- Talk like a kind nurse who knows them, not a form letter. Short sentences. Words a \
12-year-old knows.
- Say one thing clearly. No stacked reminders, no cheerleading ("You've got this!"), no \
exclamation marks, no emoji.
- Name what they told you or what their watch showed, in plain words ("your temperature \
was a bit up yesterday").
- Never name a condition. Never say anything was detected, diagnosed or confirmed. Never \
sound alarmed.
- No dashes. No "just", "simply", "please note", "as a reminder". Never open with "I \
hope this finds you well".
- Use only what the context says. Never thank them for, or mention, something they did \
unless the context says they did it. Never add a reassurance the context does not \
support."""

SYSTEM = f"""You are the monitoring assistant inside MedPull Recovery Copilot. You \
summarize recovery signals after orthopedic surgery for the surgeon and care team.

Rules you must never break:
- You describe monitoring signals, never diagnoses. Never write "detected", "diagnosis", \
"diagnosed", "infection confirmed", or say a complication exists. Say "signals consistent \
with", "pattern that may need a look", "for clinician review".
- Use only the numbers in the data. Never invent values, dates or events.
- Lead with what matters most to the clinician today.
- The disclaimer sentence, where the contract asks for it, is exactly: \
"{GUARDRAIL_SENTENCE}"

{CLINICIAN_STYLE}

Respond with a single JSON object exactly matching the requested contract."""

CONTRACTS: dict[InsightKind, str] = {
    InsightKind.WORKLIST_REASON: (
        '{"reason": "<one line, max 90 characters: the 1 or 2 findings that matter most, '
        "in plain shorthand a clinician scans in a second, separated by ' · '. Example: "
        "\"Pain rising 4 days · feverish · RHR +8 vs baseline\">}"
    ),
    InsightKind.PATIENT_SUMMARY: (
        '{"summary": "<one paragraph, 80-140 words, said the way you would tell the surgeon '
        "in the hallway. First sentence: the one thing they need to know today, with the "
        "patient's own words if they said it. Then the signals that go with it, by how "
        "much and since when, grouped where they point the same way. Then activity and "
        "exercises in plain counts, and whether the recovery is ahead, on track or behind. "
        "No headings, no one-sentence-per-metric. End with exactly this sentence: "
        f'{GUARDRAIL_SENTENCE}">}}'
    ),
    InsightKind.SUGGESTED_ACTIONS: (
        '{"actions": [{"title": "<one thing the clinician does, max 6 words, naming the '
        'patient where it fits, e.g. \"Call Maria about the chills\">", "detail": "<one '
        "plain sentence saying which data made you suggest this, in everyday words, with "
        'no status labels like flag or watch>", "urgency": "today" | "this_week" | '
        '"routine"}]}. At most 4 actions, most urgent first. Skip anything the data does '
        "not support. Do not suggest generic advice like \"encourage adherence\"; say the "
        "concrete step, e.g. \"Ask what is stopping the exercises\"."
    ),
    InsightKind.DAILY_BRIEFING: (
        '{"briefing": "<60-110 words for the whole roster, spoken the way a colleague '
        "gives a morning handoff. Who to see first and why, by name. Who is worth a look "
        "later. Any patient with missing data. One sentence on everyone else. No "
        'greeting, no sign-off.">}'
    ),
}


def _compact_analytics(analytics: dict[str, Any]) -> dict[str, Any]:
    """Strip chart series — the LLM needs findings, not plot points."""
    metrics = [
        {
            "name": m["name"],
            "status": m["status"],
            "finding": m["finding"],
        }
        for m in analytics.get("metrics", [])
        if m["status"] in ("flag", "watch")
    ]
    return {
        "postop_day": analytics.get("postop_day"),
        "risk": analytics.get("risk"),
        "trajectory": {
            "state": analytics.get("trajectory", {}).get("state"),
            "pct_vs_expected": analytics.get("trajectory", {}).get("pct"),
            "change_point_day": analytics.get("trajectory", {}).get("change_point_day"),
        },
        "composite_deviation": {
            "index": analytics.get("composite", {}).get("index"),
            "level": analytics.get("composite", {}).get("level"),
            "drivers": analytics.get("composite", {}).get("drivers"),
        },
        "data_confidence": analytics.get("confidence"),
        "adherence": {
            "rate": analytics.get("adherence", {}).get("rate"),
            "verified": analytics.get("adherence", {}).get("verified"),
            "assigned": analytics.get("adherence", {}).get("assigned"),
        },
        "notable_metrics": metrics,
    }


def patient_prompt(
    kind: InsightKind,
    patient_header: dict[str, Any],
    analytics: dict[str, Any],
    transcript: list[dict[str, str]],
) -> str:
    payload = {
        "patient": patient_header,
        "analytics": _compact_analytics(analytics),
        "recent_checkin_messages": transcript[-24:],
    }
    return (
        f"Data:\n{json.dumps(payload, default=str)}\n\n"
        f"Produce JSON matching exactly this contract:\n{CONTRACTS[kind]}"
    )


def briefing_prompt(roster: list[dict[str, Any]]) -> str:
    payload = {"as_of": "this morning", "patients": roster}
    return (
        f"Data:\n{json.dumps(payload, default=str)}\n\n"
        f"Produce JSON matching exactly this contract:\n{CONTRACTS[InsightKind.DAILY_BRIEFING]}"
    )
