"""The patient's view of their own metrics.

The console shows a clinician the care metrics as findings: sigma distances,
control-chart flags, "deterioration index". None of that belongs on a
patient's phone. This module reads the same stored analytics bundle and
renders each metric the way a kind nurse would say it: what it is, whether
it looks steady or the care team is keeping an eye on it, how many more days
of wearing the watch before it shows, and why it matters. It never names a
condition, never says anything was detected, and never prints a verdict
the care team has not made.

Everything here is a pure function of the analytics dict and the glossary,
so the mobile API can serve it from the stored assessment with no recompute.
"""

from __future__ import annotations

from typing import Any

from app.engine.explain import METRICS, SECTIONS, SIGNALS, patient_explanation
from app.engine.readiness import days_left_text

# The clinician's four statuses, in the register a patient reads. The words
# never carry alarm: "reviewing" means the care team can see it and will say
# something if there is something to say.
STATE = {
    "ok": ("good", "Looking steady"),
    "watch": ("watch", "Worth keeping an eye on"),
    "flag": ("reviewing", "Your care team is taking a look"),
    "nodata": ("waiting", "Not showing yet"),
}

# The patient's name for each care metric: the clinician's title is a term
# of art ("acute:chronic load ratio"); these are what the thing is.
PATIENT_TITLE: dict[str, str] = {
    "M1": "Activity this week",
    "M2": "How activity affects your pain",
    "M3": "How evenly you walk",
    "M4": "Walking effort",
    "M5": "Keeping pace on a walk",
    "M6": "Standing up from a chair",
    "M7": "Walking pace",
    "M8": "Stairs",
    "M9": "Sleep and night pain",
    "M10": "Overnight recovery",
    "M11": "Day–night rhythm",
    "M12": "Overnight readings together",
    "M13": "Temperature and heart rate overnight",
    "M14": "Your plan",
    "M15": "Staying in touch",
    "M16": "Data reaching your team",
    "M17": "Your recovery curve",
    "M18": "Recent changes",
    "C1": "Weight",
    "C2": "Oxygen overnight",
    "C3": "Blood sugar in range",
    "C4": "Blood pressure",
    "C5": "Symptoms this week",
    "C6": "Time spent still",
}

# Signal cards whose number a patient already sees on their portfolio.
SIGNAL_TITLE: dict[str, str] = {
    "steps": "Steps", "resting_hr": "Resting heart rate", "hrv_rmssd": "Heart rate variability",
    "hrv_sdnn": "Heart rate variability", "sleep_duration": "Sleep", "skin_temp": "Skin temperature",
    "skin_temp_delta": "Skin temperature", "spo2": "Blood oxygen", "respiratory_rate": "Breathing rate",
    "walking_speed": "Walking speed", "walking_asymmetry_pct": "Walking evenness",
    "step_length": "Step length", "cadence": "Steps per minute", "double_support_pct": "Both feet down",
    "walking_steadiness": "Walking steadiness", "stair_speed_up": "Stairs up", "stair_speed_down": "Stairs down",
    "six_min_walk": "Six-minute walk", "rom_flexion": "Bend", "rom_extension": "Straightening",
    "rom_abduction": "Arm lift", "exercise_session": "Exercise", "active_energy": "Active energy",
    "calories": "Calories", "stress_index": "Strain overnight",
}

# Metrics that are the clinician's business and read oddly on a phone.
HIDDEN_FROM_PATIENT = {"M15", "M16"}


def _headline(
    state: str, title: str, readiness: dict | None, latest_text: str | None,
    help_text: str | None = None,
) -> str:
    """One sentence a patient reads under the title."""
    lower = title[:1].lower() + title[1:]
    if state == "waiting":
        left = days_left_text(readiness)
        if readiness is not None and not readiness.get("left") and readiness.get("have", 0) > 0:
            return "Waiting on new data from your watch or phone."
        if left and not left.startswith("waiting"):
            return f"Shows after {left} of data."
        return help_text or "Shows once your data is coming through."
    early = readiness is not None and readiness.get("stage") == "provisional"
    if state == "good":
        text = f"{title} looks steady." if latest_text is None else f"{title}: {latest_text}. Looking steady."
    elif state == "watch":
        text = (f"{title} has shifted a little this week. Your care team can see it."
                if latest_text is None
                else f"{title}: {latest_text}. Shifted a little this week; your care team can see it.")
    else:
        text = f"Your care team is taking a look at {lower}. They will be in touch if anything is needed."
    if early and state != "reviewing":
        text += " This is an early read and will settle over the next few days."
    return text


def _chart(spec: dict | None, limit: int = 30) -> dict | None:
    """A small, numbers-only series for the phone: line kinds only; the
    patient's chart never carries the clinician's bands, fits or markers."""
    if not spec or spec.get("kind") not in ("line", "band", "bars", "dual"):
        return None
    pts = [{"x": p.get("x"), "y": p.get("y")} for p in spec.get("series", [])
           if p.get("y") is not None and isinstance(p.get("x"), (int, float))]
    if not pts:
        return None
    return {"kind": "bars" if spec["kind"] == "bars" else "line", "points": pts[-limit:],
            "x_label": spec.get("x_label", "Post-op day")}


def care_metric_view(m: dict[str, Any]) -> dict[str, Any] | None:
    if m.get("id") in HIDDEN_FROM_PATIENT or m.get("applicable") is False:
        return None
    state, state_label = STATE.get(str(m.get("status")), STATE["nodata"])
    title = PATIENT_TITLE.get(m["id"], m.get("name", ""))
    readiness = m.get("readiness")
    explain = patient_explanation(METRICS.get(m["id"]))
    return {
        "id": m["id"],
        "key": m.get("key"),
        "title": title,
        "state": state,
        "state_label": state_label,
        "headline": _headline(state, title, readiness, None, explain and explain.get("help")),
        "value": m.get("value") if state != "waiting" else None,
        "unit": m.get("unit", "") if state != "waiting" else "",
        "readiness": readiness,
        "days_left_text": days_left_text(readiness),
        "explain": explain,
        "chart": _chart(m.get("chart")) if state != "waiting" else None,
    }


def signal_view(card: dict[str, Any]) -> dict[str, Any]:
    state, state_label = STATE.get(str(card.get("status")), STATE["nodata"])
    key = card.get("metric_key", "")
    title = SIGNAL_TITLE.get(key, card.get("name", key))
    series = card.get("series") or []
    latest = series[-1] if series else None
    latest_text = None
    if latest is not None and state != "waiting":
        v = latest.get("value")
        unit = card.get("unit", "")
        if isinstance(v, (int, float)):
            shown = f"{v:,.0f}" if abs(v) >= 100 else f"{round(v, 1):g}"
            latest_text = f"{shown} {unit}".strip()
    readiness = card.get("readiness")
    explain = patient_explanation(SIGNALS.get(key))
    return {
        "key": key,
        "title": title,
        "state": state,
        "state_label": state_label,
        "headline": _headline(state, title, readiness, latest_text, explain and explain.get("help")),
        "latest": latest,
        "unit": card.get("unit", ""),
        "readiness": readiness,
        "days_left_text": days_left_text(readiness),
        "explain": explain,
        "series": [{"date": p.get("date"), "value": p.get("value")} for p in series[-14:]],
    }


def _days_until_full_picture(views: list[dict[str, Any]]) -> int | None:
    """The longest countdown among the metrics the patient is waiting on —
    "your full picture shows in N days"."""
    lefts = [int(v["readiness"]["left"]) for v in views
             if v.get("readiness") and not v["readiness"].get("ready") and v["readiness"].get("left")]
    return max(lefts) if lefts else None


def overall_line(
    analytics: dict[str, Any], surgical: bool, *, signal_days: int = 0
) -> tuple[str | None, int | None]:
    """A data-driven sentence for the recovery card, and the days until the
    full picture is in. Returns (None, None) when there is nothing to say
    beyond the canned tier line."""
    care = (analytics.get("care_metrics") or {}).get("metrics") or []
    cards = analytics.get("metrics") or []
    views = [v for v in (care_metric_view(m) for m in care) if v]
    signal_views = [signal_view(c) for c in cards]
    showing = [v for v in views if v["state"] != "waiting"]
    waiting = [v for v in views if v["state"] == "waiting"]
    days = _days_until_full_picture(views + signal_views)

    steady = [v["title"] for v in showing if v["state"] == "good"]
    watching = [v["title"] for v in showing if v["state"] in ("watch", "reviewing")]
    level = (analytics.get("risk") or {}).get("level")

    parts: list[str] = []
    if not showing:
        if signal_days <= 0 and not any(c.get("series") for c in cards):
            return None, days
        if days:
            parts.append(f"Your first signals are in. Most readings appear after {days} more "
                         f"day{'s' if days != 1 else ''} of wearing your watch or carrying your phone.")
        else:
            parts.append("Your first signals are in; the readings fill in as the days go by.")
        return " ".join(parts), days

    if steady:
        names = _join([s.lower() for s in steady[:3]])
        parts.append(f"{_cap(names)} look{'s' if len(steady[:3]) == 1 else ''} steady.")
    if watching and level in ("high", "medium"):
        names = _join([w.lower() for w in watching[:2]])
        parts.append(f"Your care team is keeping an eye on {names}.")
    elif watching:
        names = _join([w.lower() for w in watching[:2]])
        parts.append(f"{_cap(names)} shifted a little this week, which happens.")
    counting = [v for v in waiting if v.get("readiness") and v["readiness"].get("left")]
    if counting and days:
        n = len(counting)
        parts.append(f"{n} more reading{'s' if n != 1 else ''} will show over the next "
                     f"{days} day{'s' if days != 1 else ''} of data.")
    return (" ".join(parts) if parts else None), days


def _join(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def metrics_view(analytics: dict[str, Any], surgical: bool, *, signal_days: int = 0) -> dict[str, Any]:
    care = analytics.get("care_metrics") or {}
    by_id = {m["id"]: m for m in care.get("metrics") or []}
    # Headline first, in the pathway's order; then everything else that applies.
    order = [i for i in care.get("headline") or [] if i in by_id]
    order += [i for i in by_id if i not in order]
    views = [v for v in (care_metric_view(by_id[i]) for i in order) if v]
    signals = [signal_view(c) for c in analytics.get("metrics") or []]
    blurb, days = overall_line(analytics, surgical, signal_days=signal_days)
    trajectory = analytics.get("trajectory") or {}
    return {
        "postop_day": analytics.get("postop_day"),
        "mode": "recovery" if surgical else "general",
        "overall": {
            "blurb": blurb,
            "days_until_full_picture": days,
            "showing": sum(1 for v in views if v["state"] != "waiting"),
            "waiting": sum(1 for v in views if v["state"] == "waiting"),
        },
        "trajectory": {
            "state": trajectory.get("state"),
            "pct": trajectory.get("pct"),
            "readiness": trajectory.get("readiness"),
            "days_left_text": days_left_text(trajectory.get("readiness")),
            "explain": patient_explanation(SECTIONS["trajectory"]),
        },
        "metrics": views,
        "signals": signals,
    }
