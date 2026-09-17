"""Deterministic insight renderer — the zero-key, zero-failure path.

Everything here is templated from the engine's typed reason codes and
analytics values, so the app is fully functional (and safe) with no LLM at
all. It is also the replacement of last resort when LLM output fails
validation.
"""

from typing import Any

from app.models.enums import GUARDRAIL_SENTENCE, RiskLevel

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


# Assessments stored before the coverage line was reworded still carry it.
_LEGACY_ZERO_COVERAGE = "Only 0% of recent days reporting data"


def _reason_text(reason: dict[str, Any]) -> str:
    text = reason["text"]
    if text == _LEGACY_ZERO_COVERAGE:
        return "No device data yet"
    if reason.get("code") == "LOW_COVERAGE" and text.endswith("% of recent days reporting data"):
        return "Device data on only " + text.removeprefix("Only ").removesuffix(" reporting data")
    return text


def _reason_texts(reasons: list[dict[str, Any]], limit: int) -> list[str]:
    return [_reason_text(r) for r in reasons[:limit]]


def worklist_reason(analytics: dict[str, Any]) -> dict[str, str]:
    reasons = analytics.get("risk", {}).get("reasons", [])
    text = " · ".join(_reason_texts(reasons, 2)) or "Recovery tracking as expected"
    return {"reason": text[:90]}


def patient_summary(patient_header: dict[str, Any], analytics: dict[str, Any]) -> dict[str, str]:
    name = patient_header.get("name", "The patient").split()[0]
    day = analytics.get("postop_day")
    # "N days post-op" is false about a patient who did not have surgery; for
    # them the same number counts days on the programme.
    surgical = patient_header.get("surgical", True)
    since = f"{day} days post-op" if surgical else f"{day} days into monitoring"
    level = analytics.get("risk", {}).get("level")
    reasons = analytics.get("risk", {}).get("reasons", [])
    trajectory = analytics.get("trajectory", {})
    confidence = analytics.get("confidence", {})
    adherence = analytics.get("adherence", {})

    parts: list[str] = []
    if level == RiskLevel.MISSING_DATA:
        pct = int(round((confidence.get("score") or 0) * 100))
        seen = ("there is no recent device data" if pct <= 0
                else f"only {pct}% of recent days have device data")
        parts.append(
            f"{name} is {since}, but {seen}, "
            f"so {'recovery' if surgical else 'their baseline'} cannot be assessed reliably."
        )
        parts.append("Confirm the wearable is charged, worn, and syncing before reading trends.")
    else:
        opener = {
            RiskLevel.HIGH: f"{name} is {since} and several monitoring signals have moved away from baseline together.",
            RiskLevel.MEDIUM: f"{name} is {since} with findings worth a look this week.",
            RiskLevel.LOW: (f"{name} is {since} and recovering as expected." if surgical
                            else f"{name} is {since} and tracking at their usual baseline."),
        }[RiskLevel(level)]
        parts.append(opener)
        texts = _reason_texts([r for r in reasons if r["code"] != "ON_TRACK"], 4)
        if texts:
            parts.append("; ".join(texts) + ".")
        pct = trajectory.get("pct")
        state = trajectory.get("state")
        # The expected curve is a post-surgical construct; a general patient
        # has no procedure to be behind or ahead of.
        if surgical and state == "behind" and pct is not None:
            parts.append(f"Functional recovery is tracking {abs(round(pct))}% behind the expected curve for this procedure.")
        elif surgical and state == "ahead" and pct is not None:
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


def _stable_sentence(n: int, everyone: bool) -> str:
    if everyone:
        return ("The one patient on the roster is recovering as expected." if n == 1
                else f"All {n} patients are recovering as expected.")
    return ("The other patient is recovering as expected." if n == 1
            else f"The other {n} patients are recovering as expected.")


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
        parts.append(_stable_sentence(len(stable), everyone=len(stable) == len(roster)))
    if not parts:
        parts.append("No patients on the roster yet.")
    return {"briefing": " ".join(parts)}
