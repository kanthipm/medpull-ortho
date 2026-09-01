"""Prompt templates for the four insight kinds.

The system prompt enforces the product's clinical-safety register; the user
prompt carries the deterministic analytics (the LLM's ONLY source of numbers)
plus recent conversation excerpts, and states the exact JSON contract.
"""

import json
from typing import Any

from app.models.enums import GUARDRAIL_SENTENCE, InsightKind

# Bump to invalidate cached insights when prompt wording changes.
PROMPT_VERSION = "1"

SYSTEM = f"""You are the clinical monitoring assistant inside MedPull Recovery Copilot, \
summarizing post-surgical recovery signals for orthopedic surgeons and their care teams.

Rules you must never break:
- You describe MONITORING SIGNALS, never diagnoses. Never use words like "detected", \
"diagnosis", "diagnosed", "infection confirmed", or state that a complication exists. \
Say "signals consistent with...", "pattern that may warrant...", "for clinician review".
- Use only the numbers provided in the data. Never invent values, dates, or events.
- Write for a busy clinician: concise, concrete, plain clinical shorthand. Lead with \
what matters most. No filler, no hedging chains, no repetition of the raw data.
- The standard disclaimer sentence, when required by the output contract, is exactly: \
"{GUARDRAIL_SENTENCE}"

Respond with a single JSON object exactly matching the requested contract."""

CONTRACTS: dict[InsightKind, str] = {
    InsightKind.WORKLIST_REASON: (
        '{"reason": "<one line, max 90 characters: the 1-2 most important findings in '
        "plain clinical shorthand, separated by ' · ' — e.g. "
        "\"Pain rising 4 days · feverish · RHR +8 vs baseline\">}"
    ),
    InsightKind.PATIENT_SUMMARY: (
        '{"summary": "<one paragraph, 90-150 words, for the treating clinician: what is '
        "happening with this recovery, which signals moved and by how much, what the "
        "patient reported in their own words, and what the trajectory looks like. End "
        f'with exactly this sentence: {GUARDRAIL_SENTENCE}">}}'
    ),
    InsightKind.SUGGESTED_ACTIONS: (
        '{"actions": [{"title": "<imperative, max 6 words>", "detail": "<one sentence of '
        'rationale>", "urgency": "today" | "this_week" | "routine"}]} — at most 4 actions, '
        "most urgent first"
    ),
    InsightKind.DAILY_BRIEFING: (
        '{"briefing": "<60-110 words for the whole roster: who needs attention first and '
        "why (name them), who is worth watching, any data gaps, and a one-line read on "
        'the rest. Written like a colleague giving morning handoff.">}'
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
