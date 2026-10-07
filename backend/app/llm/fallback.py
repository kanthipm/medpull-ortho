"""Deterministic insight renderer — the zero-key, zero-failure path.

Everything here is templated from the engine's typed reason codes and
analytics values, so the app is fully functional (and safe) with no LLM at
all. It is also the replacement of last resort when LLM output fails
validation.

The register is a colleague at handoff, not a read-out: the facts are woven
into sentences ("James needs a call today: his heart rate and temperature
have both climbed above his baseline, and he has moved less with it"), the
signals that belong together share a sentence, and nothing is stated one
metric per line. A reader should not be able to tell from the prose alone
whether a model or this file wrote it.
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
    """The one-line scan text. Shorthand on purpose — it is read in a second
    on a list — so it keeps the engine's fragments joined by dots."""
    reasons = analytics.get("risk", {}).get("reasons", [])
    text = " · ".join(_reason_texts(reasons, 2)) or "Recovery tracking as expected"
    return {"reason": text[:90]}


# --- the hallway summary ----------------------------------------------------------

_PRONOUNS = {
    "M": ("he", "his", "him", "is", "has"),
    "F": ("she", "her", "her", "is", "has"),
}
_THEY = ("they", "their", "them", "are", "have")

# Which flagged signal is which, and the direction that is the finding.
_RISING = {
    "RHR_RISING": "resting heart rate",
    "TEMP_RISING": "skin temperature",
    "RR_RISING": "breathing rate",
}
_FALLING = {
    "HRV_FALLING": "heart rate variability",
    "SPO2_LOW": "blood oxygen",
}


def _pronouns(header: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return _PRONOUNS.get(str(header.get("sex") or "").upper(), _THEY)


def _procedure_phrase(header: dict[str, Any]) -> str | None:
    """"a total knee replacement" from "Total Knee Replacement (TKA)"."""
    raw = str(header.get("procedure") or "").split("(")[0].strip()
    if not raw or raw.lower() in ("general care", "none"):
        return None
    words = raw.lower()
    article = "an" if words[0] in "aeiou" else "a"
    return f"{article} {words}"


def _join(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


_DRIFT_LABELS = {
    "resting hr": "resting heart rate", "hrv": "heart rate variability", "activity": "activity",
    "sleep": "sleep", "skin temperature": "skin temperature", "walking speed": "walking speed",
    "blood oxygen": "blood oxygen", "respiratory rate": "breathing rate",
}


def _signal_sentences(
    reasons: list[dict[str, Any]], subj: str, pos: str, verb_is: str, verb_has: str, day: Any
) -> list[str]:
    """The flagged signals, grouped the way a clinician would say them."""
    codes = {r["code"]: r for r in reasons}
    out: list[str] = []

    rising = [label for code, label in _RISING.items() if code in codes]
    falling = [label for code, label in _FALLING.items() if code in codes]
    vitals = ""
    if rising:
        both = " both" if len(rising) == 2 else ""
        vitals = (f"{_cap(pos)} {_join(rising)} {verb_has if len(rising) == 1 else 'have'}"
                  f"{both} climbed above {pos} baseline")
    if falling:
        drop = f"{pos} {_join(falling)} {verb_has if len(falling) == 1 else 'have'} dropped"
        vitals = f"{vitals}, and {drop}" if vitals else _cap(drop) + f" below {pos} baseline"
    if "COMPOSITE_HIGH" in codes:
        vitals = (f"{vitals} — several signals moving together" if vitals
                  else "Several signals have moved away from " + pos + " baseline together")
    if vitals:
        out.append(vitals + ".")

    activity: list[str] = []
    anchored = any("post-op start" in r["text"] for r in reasons
                   if r["code"] in ("STEPS_FALLING", "WALKING_SLOWING"))
    when = f" for day {day}" if day is not None and not anchored else ""
    if "STEPS_FALLING" in codes:
        activity.append(f"moved less than expected{when}" if not anchored
                        else "not picked up activity since the first days")
    if "WALKING_SLOWING" in codes:
        activity.append("walked more slowly than expected" if not anchored
                        else "not picked up walking speed since the first days")
    if "GAIT_ASYMMETRY_HIGH" in codes:
        activity.append("kept favouring one side when walking")
    if activity:
        lead = f"{_cap(subj)} {verb_has} also" if out else f"{_cap(subj)} {verb_has}"
        out.append(f"{lead} {_join(activity)}.")

    if "SLEEP_DISRUPTED" in codes:
        out.append(f"Sleep is well under {pos} usual{' too' if out else ''}.")
    drifts = [r["text"] for r in reasons if r["code"] == "DRIFT_DETECTED"]
    if drifts:
        # "Resting HR sliding gradually day over day" -> "resting heart rate"
        raw = [t.split(" sliding")[0].strip().lower() for t in drifts]
        names = _join([_DRIFT_LABELS.get(n, n) for n in raw])
        out.append(f"{_cap(names)} {'is' if len(drifts) == 1 else 'are'} sliding a little each day, "
                   "not enough to flag yet.")
    dark = [r for r in reasons if r["code"] == "LOW_COVERAGE" and "no longer reporting" in r["text"]]
    if dark:
        out.append(f"{_cap(dark[0]['text'].replace(' no longer reporting', ''))} "
                   f"{'has' if ',' not in dark[0]['text'] else 'have'} stopped reporting, so "
                   "part of the picture is missing.")
    return out


def patient_summary(patient_header: dict[str, Any], analytics: dict[str, Any]) -> dict[str, str]:
    name = patient_header.get("name", "The patient").split()[0]
    subj, pos, _obj, verb_is, verb_has = _pronouns(patient_header)
    day = analytics.get("postop_day")
    surgical = patient_header.get("surgical", True)
    procedure = _procedure_phrase(patient_header) if surgical else None
    level = analytics.get("risk", {}).get("level")
    reasons = [r for r in analytics.get("risk", {}).get("reasons", []) if r["code"] != "ON_TRACK"]
    trajectory = analytics.get("trajectory", {})
    confidence = analytics.get("confidence", {})
    adherence = analytics.get("adherence", {})

    if procedure and day is not None:
        since = f"on post-op day {day} after {procedure}"
    elif surgical and day is not None:
        since = f"{day} days post-op"
    else:
        since = f"{day} days into monitoring" if day is not None else "being monitored"

    parts: list[str] = []
    if level == RiskLevel.MISSING_DATA:
        pct = int(round((confidence.get("score") or 0) * 100))
        seen = ("there is no recent device data" if pct <= 0
                else f"only about {pct}% of recent days have device data")
        parts.append(f"{name} can't be assessed yet: {seen}. {_cap(subj)} {verb_is} {since}, "
                     f"so the picture should fill in quickly once the watch is charged, worn "
                     f"and syncing.")
    else:
        signals = _signal_sentences(reasons, subj, pos, verb_is, verb_has, day)
        pct = trajectory.get("pct")
        state = trajectory.get("state")
        if level == RiskLevel.HIGH:
            parts.append(f"{name} needs a call today.")
            parts.extend(signals)
        elif level == RiskLevel.MEDIUM:
            parts.append(f"{name} is worth a look this week.")
            parts.extend(signals)
        else:
            if surgical:
                parts.append(f"{name} is {since} and recovering as expected.")
            else:
                parts.append(f"{name} is {since} and tracking at {pos} usual baseline.")
            parts.extend(signals)
        if surgical and state == "behind" and pct is not None:
            parts.append(f"Overall {subj} {verb_is} running about {abs(round(pct))}% behind the "
                         f"expected curve for {procedure or 'this procedure'}.")
        elif surgical and state == "ahead" and pct is not None:
            parts.append(f"Overall {subj} {verb_is} about {abs(round(pct))}% ahead of the expected "
                         f"curve.")
        if adherence.get("assigned") and adherence.get("rate", 1) < 0.7:
            done = int(round(adherence["rate"] * 100))
            parts.append(f"{_cap(subj)} {verb_has} finished about {done}% of {pos} tasks over the "
                         "last two weeks.")
        if level in (RiskLevel.HIGH, RiskLevel.MEDIUM):
            parts.append(f"{_cap(subj)} {verb_is} {since}.")
        if level == RiskLevel.HIGH:
            parts.append("A short call would settle whether to bring the follow-up forward.")

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


def _lower_reason(reason: str) -> str:
    """"Resting HR rising vs baseline · Activity below expected range" -> a
    clause: "resting HR rising vs baseline and activity below expected range"."""
    bits = [b.strip() for b in reason.split("·") if b.strip()]
    bits = [b[:1].lower() + b[1:] for b in bits]
    return _join(bits)


def daily_briefing(roster: list[dict[str, Any]]) -> dict[str, str]:
    high = [p for p in roster if p["priority"] == RiskLevel.HIGH]
    medium = [p for p in roster if p["priority"] == RiskLevel.MEDIUM]
    missing = [p for p in roster if p["priority"] == RiskLevel.MISSING_DATA]
    stable = [p for p in roster if p["priority"] == RiskLevel.LOW]

    parts: list[str] = []
    if high:
        first = high[0]
        lead = f"Start with {first['name']}"
        if first.get("reason"):
            lead += f": {_lower_reason(first['reason'])}"
        parts.append(lead + ".")
        for p in high[1:]:
            line = f"{p['name']} needs a call today too"
            if p.get("reason"):
                line += f", with {_lower_reason(p['reason'])}"
            parts.append(line + ".")
    if medium:
        names = _join([p["name"] for p in medium])
        verb = "is" if len(medium) == 1 else "are"
        parts.append(f"{names} {verb} worth a look when you have a moment.")
    if missing:
        names = _join([p["name"] for p in missing])
        has = "has" if len(missing) == 1 else "have"
        parts.append(f"{names} {has} too little device data to assess; worth a nudge about "
                     "wearing and syncing.")
    if stable:
        parts.append(_stable_sentence(len(stable), everyone=len(stable) == len(roster)))
    if not parts:
        parts.append("No patients on the roster yet.")
    return {"briefing": " ".join(parts)}
