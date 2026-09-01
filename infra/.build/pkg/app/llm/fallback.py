"""Deterministic insight renderer — the zero-key, zero-failure path.

Everything here is templated from the engine's typed reason codes and
analytics values, so the app is fully functional (and safe) with no LLM at
all. It is also the replacement of last resort when LLM output fails
validation.
"""

from typing import Any

from app.models.enums import GUARDRAIL_SENTENCE, InsightKind, RiskLevel

_ACTION_LIBRARY: list[tuple[tuple[str, ...], dict[str, str]]] = [
    (("COMPOSITE_HIGH", "RHR_RISING", "TEMP_RISING", "SPO2_LOW", "RR_RISING"), {
        "title": "Call the patient today",
        "detail": "Several signals moved together; a short call can establish whether earlier clinical follow-up is appropriate.",
        "urgency": "today",
    }),
    (("TEMP_RISING",), {
        "title": "Ask about fever and the incision",
        "detail": "Skin temperature is elevated vs baseline — ask about chills, warmth, redness, or drainage.",
        "urgency": "today",
    }),
    (("TRAJECTORY_BEHIND", "STEPS_FALLING", "WALKING_SLOWING"), {
        "title": "Review activity progression",
        "detail": "Activity is under the expected range — ask what is limiting movement and adjust the plan with PT.",
        "urgency": "this_week",
    }),
    (("GAIT_ASYMMETRY_HIGH",), {
        "title": "Consider a gait review with PT",
        "detail": "Walking asymmetry remains elevated for this stage of recovery.",
        "urgency": "this_week",
    }),
    (("SLEEP_DISRUPTED",), {
        "title": "Ask about pain at night",
        "detail": "Sleep is well below baseline — review night-time pain control and positioning.",
        "urgency": "this_week",
    }),
    (("LOW_COVERAGE",), {
        "title": "Check the device connection",
        "detail": "Too few days are reporting data to assess recovery — confirm the wearable is charged, worn, and synced.",
        "urgency": "this_week",
    }),
    (("ADHERENCE_LOW",), {
        "title": "Reinforce the exercise plan",
        "detail": "Task completion is low over the last two weeks — a quick nudge often restores momentum.",
        "urgency": "this_week",
    }),
    (("DRIFT_DETECTED",), {
        "title": "Recheck at the next check-in",
        "detail": "A signal is sliding gradually — worth confirming the trend before acting.",
        "urgency": "routine",
    }),
]

_DEFAULT_ACTION = {
    "title": "Continue routine monitoring",
    "detail": "No findings require action; daily check-ins and passive monitoring continue.",
    "urgency": "routine",
}


def _reason_texts(reasons: list[dict[str, Any]], limit: int) -> list[str]:
    return [r["text"] for r in reasons[:limit]]


def worklist_reason(analytics: dict[str, Any]) -> dict[str, str]:
    reasons = analytics.get("risk", {}).get("reasons", [])
    text = " · ".join(_reason_texts(reasons, 2)) or "Recovery tracking as expected"
    return {"reason": text[:90]}


def patient_summary(patient_header: dict[str, Any], analytics: dict[str, Any]) -> dict[str, str]:
    name = patient_header.get("name", "The patient").split()[0]
    day = analytics.get("postop_day")
    level = analytics.get("risk", {}).get("level")
    reasons = analytics.get("risk", {}).get("reasons", [])
    trajectory = analytics.get("trajectory", {})
    confidence = analytics.get("confidence", {})
    adherence = analytics.get("adherence", {})

    parts: list[str] = []
    if level == RiskLevel.MISSING_DATA:
        pct = int(round((confidence.get("score") or 0) * 100))
        parts.append(
            f"{name} is {day} days post-op, but only {pct}% of recent days have device data, "
            "so recovery cannot be assessed reliably."
        )
        parts.append("Confirm the wearable is charged, worn, and syncing before reading trends.")
    else:
        opener = {
            RiskLevel.HIGH: f"{name} is {day} days post-op and several monitoring signals have moved away from baseline together.",
            RiskLevel.MEDIUM: f"{name} is {day} days post-op with findings worth a look this week.",
            RiskLevel.LOW: f"{name} is {day} days post-op and recovering as expected.",
        }[RiskLevel(level)]
        parts.append(opener)
        texts = _reason_texts([r for r in reasons if r["code"] != "ON_TRACK"], 4)
        if texts:
            parts.append("; ".join(texts) + ".")
        pct = trajectory.get("pct")
        state = trajectory.get("state")
        if state == "behind" and pct is not None:
            parts.append(f"Functional recovery is tracking {abs(round(pct))}% behind the expected curve for this procedure.")
        elif state == "ahead" and pct is not None:
            parts.append(f"Functional recovery is tracking {abs(round(pct))}% ahead of the expected curve.")
        if adherence.get("assigned") and adherence.get("rate", 1) < 0.7:
            parts.append(f"Task adherence is {int(round(adherence['rate'] * 100))}% over the last two weeks.")
        if level == RiskLevel.HIGH:
            parts.append("Consider contacting the patient to determine whether earlier clinical follow-up is appropriate.")

    parts.append(GUARDRAIL_SENTENCE)
    return {"summary": " ".join(parts)}


def suggested_actions(analytics: dict[str, Any]) -> dict[str, Any]:
    codes = {r["code"] for r in analytics.get("risk", {}).get("reasons", [])}
    actions: list[dict[str, str]] = []
    for trigger_codes, action in _ACTION_LIBRARY:
        if codes.intersection(trigger_codes) and action not in actions:
            actions.append(action)
        if len(actions) == 4:
            break
    if not actions:
        actions = [_DEFAULT_ACTION]
    return {"actions": actions}


def daily_briefing(roster: list[dict[str, Any]]) -> dict[str, str]:
    high = [p for p in roster if p["priority"] == RiskLevel.HIGH]
    medium = [p for p in roster if p["priority"] == RiskLevel.MEDIUM]
    missing = [p for p in roster if p["priority"] == RiskLevel.MISSING_DATA]
    stable = [p for p in roster if p["priority"] == RiskLevel.LOW]

    def names(patients: list[dict[str, Any]], with_reason: bool = False) -> str:
        if with_reason:
            return "; ".join(f"{p['name']} ({p['reason']})" for p in patients)
        return ", ".join(p["name"] for p in patients)

    parts: list[str] = []
    if high:
        parts.append(f"{names(high, with_reason=True)} — review first.")
    if medium:
        parts.append(f"Worth a look: {names(medium)}.")
    if missing:
        parts.append(f"{names(missing)} " + ("has" if len(missing) == 1 else "have") + " too little device data to assess — check the connection.")
    if stable:
        parts.append(f"The remaining {len(stable)} are recovering as expected.")
    if not parts:
        parts.append("No patients on the roster yet.")
    return {"briefing": " ".join(parts)}
