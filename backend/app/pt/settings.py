"""A clinic's own settings, and one person's where they differ.

Every value has a product default. A clinic that has changed nothing has no
row, and reads the defaults; a row holds only what was changed, so a later
change of a default reaches everyone who never touched it.

The flag thresholds here are the ones ``engine/risk.py`` ``score_reported``
fires on for a chart followed by check-ins (the clinic's lifters). The
engine reads them through ``flag_thresholds``; the rules page
(``flag_rules``) shows each rule beside its number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engine import risk
from app.pt.instruments import INSTRUMENTS
from app.pt.models import ClinicSetting, FlagEvent, PatientSetting

# --- the flags ---------------------------------------------------------------------

# key: (default, low, high, whole number)
FLAG_BOUNDS: dict[str, tuple[float, float, float, bool]] = {
    "load_spike_ratio": (risk.LOAD_SPIKE_RATIO, 1.1, 3.0, False),
    "load_watch_ratio": (risk.LOAD_WATCH_RATIO, 1.05, 2.5, False),
    "pain_rise_points": (risk.PAIN_RISE_POINTS, 1.0, 6.0, False),
    "program_low": (risk.PROGRAM_LOW, 0.1, 0.9, False),
    "quiet_days": (float(risk.QUIET_DAYS), 1, 10, True),
    "quiet_days_high": (float(risk.QUIET_DAYS_HIGH), 2, 21, True),
}

# What the rules page says about each flag. ``thresholds`` name the settings
# it fires on; the sentence is the rule as it is coded in risk.score_reported.
FLAG_RULES: tuple[dict[str, Any], ...] = (
    {
        "code": "LOAD_SPIKE", "name": "Training load, too much too soon",
        "inputs": "The training the person reports each evening (effort 0 to 10 times "
                  "minutes), as the last 7 days against their own recent weeks.",
        "rule": "Raised when the 7-day load is {load_watch_ratio}× the recent average or "
                "more. At {load_spike_ratio}× or more, once there are ten days of history, "
                "the chart is High.",
        "thresholds": ["load_watch_ratio", "load_spike_ratio"],
    },
    {
        "code": "PAIN_RISING", "name": "Pain rising",
        "inputs": "The pain score from each check-in.",
        "rule": "Raised when the latest score is {pain_rise_points} points or more above "
                "the average of the week before it (which needs three scores).",
        "thresholds": ["pain_rise_points"],
    },
    {
        "code": "NEW_PAIN", "name": "New pain since the last visit",
        "inputs": "The check-in's \"any new pain that wasn't there at your last visit?\" and "
                  "the area the person names.",
        "rule": "Raised for three days after a yes, or until a later check-in says no. An "
                "area that was not among those recorded at the evaluation is named.",
        "thresholds": [],
    },
    {
        "code": "PROGRAM_SLIPPING", "name": "Program slipping",
        "inputs": "The check-in's \"did you get today's program in?\" (all, some, none).",
        "rule": "Raised when the last three days average under {program_low_pct}% done "
                "(which needs two answers).",
        "thresholds": ["program_low"],
    },
    {
        "code": "WENT_QUIET", "name": "Went quiet",
        "inputs": "The dates of the person's check-ins.",
        "rule": "Raised after {quiet_days} days with no check-in. At {quiet_days_high} "
                "days the chart is High.",
        "thresholds": ["quiet_days", "quiet_days_high"],
    },
)

# --- everything else -----------------------------------------------------------------

# Words that make a person's question one for today rather than the weekly
# block. A clinic edits the list; these are where it starts.
TRIAGE_WORDS = (
    "pain", "hurts", "hurting", "sharp", "swollen", "swell", "numb", "numbness",
    "tingling", "pins and needles", "gave out", "gave way", "popped", "pop", "locked",
    "can't", "cannot", "worse", "worried", "today", "tonight", "tomorrow", "right now",
    "urgent", "before my session",
)
EXERCISE_GUARD_DEFAULT = 6
EXERCISE_GUARD_MAX = 20
MORNING_CEILING_DEFAULT = 3

DEFAULTS: dict[str, Any] = {
    "flags": {key: bounds[0] for key, bounds in FLAG_BOUNDS.items()},
    # Exercises on one person's day before the calendar asks "are you sure?".
    "exercise_guard": EXERCISE_GUARD_DEFAULT,
    "triage_words": list(TRIAGE_WORDS),
    # The morning after a loaded session: ask or not, and the pain at or
    # under which the morning counts as settled.
    "morning_check": {"on": False, "ceiling": MORNING_CEILING_DEFAULT},
    # The Friday word on the week.
    "week_checkin": {"on": False},
    # The clinic's own change thresholds for outcome measures, by instrument.
    "outcome_thresholds": {},
}


class SettingError(ValueError):
    """A value a setting does not take; the message is for the person typing."""


@dataclass(frozen=True)
class FlagThresholds:
    load_spike_ratio: float = risk.LOAD_SPIKE_RATIO
    load_watch_ratio: float = risk.LOAD_WATCH_RATIO
    pain_rise_points: float = risk.PAIN_RISE_POINTS
    program_low: float = risk.PROGRAM_LOW
    quiet_days: int = risk.QUIET_DAYS
    quiet_days_high: int = risk.QUIET_DAYS_HIGH

    def changed(self) -> dict[str, float]:
        """What differs from the product's defaults (empty for a clinic that
        changed nothing)."""
        return {key: getattr(self, key) for key, bounds in FLAG_BOUNDS.items()
                if float(getattr(self, key)) != float(bounds[0])}


def _row(db: Session, hospital_id: str | None) -> ClinicSetting | None:
    return db.get(ClinicSetting, hospital_id) if hospital_id else None


def _merged(stored: dict[str, Any] | None) -> dict[str, Any]:
    stored = stored if isinstance(stored, dict) else {}
    out: dict[str, Any] = {}
    for key, default in DEFAULTS.items():
        value = stored.get(key)
        if isinstance(default, dict):
            out[key] = {**default, **(value if isinstance(value, dict) else {})}
        elif isinstance(default, list):
            out[key] = list(value) if isinstance(value, list) else list(default)
        else:
            out[key] = default if value is None else value
    return out


def read(db: Session, hospital_id: str | None) -> dict[str, Any]:
    """The clinic's settings with every default filled in."""
    row = _row(db, hospital_id)
    return _merged(row.data if row is not None else None)


def flag_thresholds(db: Session, hospital_id: str | None) -> FlagThresholds:
    flags = read(db, hospital_id)["flags"]
    return FlagThresholds(
        load_spike_ratio=float(flags["load_spike_ratio"]),
        load_watch_ratio=float(flags["load_watch_ratio"]),
        pain_rise_points=float(flags["pain_rise_points"]),
        program_low=float(flags["program_low"]),
        quiet_days=int(flags["quiet_days"]),
        quiet_days_high=int(flags["quiet_days_high"]),
    )


def flag_signature(db: Session, hospital_id: str | None) -> str:
    """What a stored assessment's key carries for this clinic's thresholds:
    nothing for a clinic on the defaults, so its charts keep the key they
    had, and the changed values otherwise, so an edit rescored every chart."""
    row = _row(db, hospital_id)
    if row is None or not isinstance(row.data, dict) or not row.data.get("flags"):
        return ""
    changed = flag_thresholds(db, hospital_id).changed()
    return ";".join(f"{k}={changed[k]}" for k in sorted(changed))


def _number(value: Any, name: str, low: float, high: float, whole: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SettingError(f"{name} must be a number")
    if not low <= float(value) <= high:
        raise SettingError(f"{name} must be between {low:g} and {high:g}")
    if whole and float(value) != int(value):
        raise SettingError(f"{name} must be a whole number")
    return int(value) if whole else round(float(value), 2)


def _clean_flags(patch: Any, current: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise SettingError("flags must be an object of thresholds")
    out = dict(current)
    for key, value in patch.items():
        if key not in FLAG_BOUNDS:
            raise SettingError(f"Unknown threshold: {key}")
        default, low, high, whole = FLAG_BOUNDS[key]
        out[key] = default if value is None else _number(value, key, low, high, whole)
    if out["load_spike_ratio"] < out["load_watch_ratio"]:
        raise SettingError("The High ratio cannot be under the ratio that raises the flag")
    if out["quiet_days_high"] < out["quiet_days"]:
        raise SettingError("The High number of quiet days cannot be under the first one")
    return out


def _clean_words(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SettingError("triage_words must be a list of words or phrases")
    words: list[str] = []
    for item in value:
        word = str(item).strip().lower()
        if not word:
            continue
        if len(word) > 40:
            raise SettingError("A triage word or phrase is at most 40 characters")
        if word not in words:
            words.append(word)
    if len(words) > 80:
        raise SettingError("At most 80 triage words")
    return words


def _clean_morning(value: Any, current: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SettingError("morning_check must be an object")
    out = dict(current)
    if "on" in value:
        out["on"] = bool(value["on"])
    if "ceiling" in value:
        out["ceiling"] = int(_number(value["ceiling"], "The pain ceiling", 0, 10, True))
    return out


def _clean_thresholds(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise SettingError("outcome_thresholds must be an object by instrument")
    out: dict[str, float] = {}
    for key, points in value.items():
        if key not in INSTRUMENTS:
            raise SettingError(f"Unknown outcome measure: {key}")
        if points is None:
            continue
        span = INSTRUMENTS[key].high - INSTRUMENTS[key].low
        out[key] = _number(points, f"The {INSTRUMENTS[key].short} threshold", 0.5, span, False)
    return out


def update(db: Session, hospital_id: str, patch: dict[str, Any], *, by: str | None) -> dict[str, Any]:
    """Change some of a clinic's settings. Only the keys named are touched;
    a threshold sent as null goes back to the product's default."""
    current = read(db, hospital_id)
    for key in patch:
        if key not in DEFAULTS:
            raise SettingError(f"Unknown setting: {key}")
    if "flags" in patch:
        current["flags"] = _clean_flags(patch["flags"], current["flags"])
    if "exercise_guard" in patch:
        current["exercise_guard"] = int(_number(
            patch["exercise_guard"], "The exercise count", 1, EXERCISE_GUARD_MAX, True))
    if "triage_words" in patch:
        current["triage_words"] = _clean_words(patch["triage_words"])
    if "morning_check" in patch:
        current["morning_check"] = _clean_morning(patch["morning_check"], current["morning_check"])
    if "week_checkin" in patch:
        if not isinstance(patch["week_checkin"], dict):
            raise SettingError("week_checkin must be an object")
        current["week_checkin"] = {"on": bool(patch["week_checkin"].get("on"))}
    if "outcome_thresholds" in patch:
        current["outcome_thresholds"] = _clean_thresholds(patch["outcome_thresholds"])
    # Stored: what differs from the defaults, and nothing else.
    stored: dict[str, Any] = {}
    flags = {k: v for k, v in current["flags"].items() if float(v) != float(FLAG_BOUNDS[k][0])}
    if flags:
        stored["flags"] = flags
    for key in ("exercise_guard", "triage_words", "morning_check", "week_checkin",
                "outcome_thresholds"):
        if current[key] != DEFAULTS[key]:
            stored[key] = current[key]
    row = _row(db, hospital_id)
    if row is None:
        row = ClinicSetting(hospital_id=hospital_id, data={})
        db.add(row)
    row.data = stored
    row.updated_at = datetime.now()
    row.updated_by = by
    db.commit()
    return read(db, hospital_id)


# --- one person's own ------------------------------------------------------------------


def patient_read(db: Session, patient_id: str, hospital_id: str | None) -> dict[str, Any]:
    """The next-morning check and the Friday check-in as they apply to this
    person: the clinic's setting, unless theirs says otherwise."""
    clinic = read(db, hospital_id)
    row = db.get(PatientSetting, patient_id)
    own = row.data if row is not None and isinstance(row.data, dict) else {}
    morning = {**clinic["morning_check"], **(own.get("morning_check") or {})}
    week = {**clinic["week_checkin"], **(own.get("week_checkin") or {})}
    return {
        "morning_check": {"on": bool(morning["on"]), "ceiling": int(morning["ceiling"]),
                          "own": bool(own.get("morning_check"))},
        "week_checkin": {"on": bool(week["on"]), "own": bool(own.get("week_checkin"))},
    }


def patient_update(db: Session, patient_id: str, hospital_id: str | None,
                   patch: dict[str, Any], *, by: str | None) -> dict[str, Any]:
    row = db.get(PatientSetting, patient_id)
    data = dict(row.data) if row is not None and isinstance(row.data, dict) else {}
    if "morning_check" in patch:
        value = patch["morning_check"]
        if value is None:
            data.pop("morning_check", None)
        else:
            current = patient_read(db, patient_id, hospital_id)["morning_check"]
            cleaned = _clean_morning(value, {"on": current["on"], "ceiling": current["ceiling"]})
            data["morning_check"] = cleaned
    if "week_checkin" in patch:
        value = patch["week_checkin"]
        if value is None:
            data.pop("week_checkin", None)
        elif not isinstance(value, dict):
            raise SettingError("week_checkin must be an object")
        else:
            data["week_checkin"] = {"on": bool(value.get("on"))}
    if row is None:
        row = PatientSetting(patient_id=patient_id, data={})
        db.add(row)
    row.data = data
    row.updated_at = datetime.now()
    row.updated_by = by
    db.commit()
    return patient_read(db, patient_id, hospital_id)


# --- the rules page ----------------------------------------------------------------------


def log_flags(db: Session, patient, codes: list[str], day: date) -> int:
    """Note the flags up on a chart today (once per chart, flag and day).
    Returns rows added; the caller commits."""
    if not codes:
        return 0
    seen = set(db.scalars(
        select(FlagEvent.code).where(FlagEvent.patient_id == patient.id, FlagEvent.day == day)
    ))
    added = 0
    for code in dict.fromkeys(codes):
        if code not in seen:
            db.add(FlagEvent(hospital_id=patient.hospital_id, patient_id=patient.id,
                             code=code, day=day))
            added += 1
    return added


def flag_rules(db: Session, hospital_id: str, *, today: date | None = None,
               window_days: int = 30) -> list[dict[str, Any]]:
    """Each flag as the rules page shows it: the rule in a sentence with this
    clinic's numbers in it, what it reads, its thresholds with their
    defaults and bounds, and how often it has been up: on how many charts
    today, and on how many chart-days in the window."""
    today = today or date.today()
    flags = read(db, hospital_id)["flags"]
    since = today - timedelta(days=window_days - 1)
    counts = dict(db.execute(
        select(FlagEvent.code, func.count(FlagEvent.id))
        .where(FlagEvent.hospital_id == hospital_id, FlagEvent.day >= since)
        .group_by(FlagEvent.code)
    ).all())
    people = dict(db.execute(
        select(FlagEvent.code, func.count(func.distinct(FlagEvent.patient_id)))
        .where(FlagEvent.hospital_id == hospital_id, FlagEvent.day >= since)
        .group_by(FlagEvent.code)
    ).all())
    now = dict(db.execute(
        select(FlagEvent.code, func.count(func.distinct(FlagEvent.patient_id)))
        .where(FlagEvent.hospital_id == hospital_id, FlagEvent.day == today)
        .group_by(FlagEvent.code)
    ).all())
    words = {**flags, "program_low_pct": int(round(float(flags["program_low"]) * 100))}
    out = []
    for rule in FLAG_RULES:
        out.append({
            "code": rule["code"],
            "name": rule["name"],
            "inputs": rule["inputs"],
            "rule": rule["rule"].format(**{
                k: (f"{v:g}" if isinstance(v, (int, float)) else v) for k, v in words.items()
            }),
            "thresholds": [
                {"key": key, "value": flags[key], "default": FLAG_BOUNDS[key][0],
                 "low": FLAG_BOUNDS[key][1], "high": FLAG_BOUNDS[key][2],
                 "whole": FLAG_BOUNDS[key][3],
                 "changed": float(flags[key]) != float(FLAG_BOUNDS[key][0])}
                for key in rule["thresholds"]
            ],
            "fired": {"today": int(now.get(rule["code"], 0)),
                      "chart_days": int(counts.get(rule["code"], 0)),
                      "charts": int(people.get(rule["code"], 0)),
                      "window_days": window_days},
        })
    return out
