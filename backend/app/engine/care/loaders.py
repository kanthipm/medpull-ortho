"""Database loaders for the inputs ``load_daily_series`` does not carry:
json-bearing rows (sleep stages, exercise sessions), intraday buckets,
patient-reported symptoms (observations AND check-in transcripts), check-in
engagement and task records.

Every loader is a plain query plus a pandas reshape; none of them stores
anything. The check-in transcript parsers are here because the patient app
writes a pain score into a ``Checkin`` transcript sentence rather than a
PAIN_NRS observation, and a metric that only read observations would miss
every score the SMS conversation collected.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.care.types import (
    empty_glucose_frame,
    empty_sleep_frame,
    empty_symptom_frame,
)
from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.checkin import Checkin, CheckinMessage
from app.models.enums import Granularity
from app.models.enums import MetricType as M
from app.models.observation import Observation

# Patient sentences the SMS/app conversation writes for a pain score
# (tasks/service.answer_to_text) and the free-text form a walk/exercise task
# may use. Only patient lines are parsed — the copilot's own prompt
# ("Pain during the exercises, 0 to 10?") carries digits that are not a score.
PAIN_PATTERNS = [
    re.compile(r"My pain is about (\d+) out of 10", re.IGNORECASE),
    re.compile(r"Pain (?:during|while) [^.\d]*?(\d+)(?!\s*to\s*10)", re.IGNORECASE),
]
BREATHLESSNESS_PATTERNS = [
    re.compile(r"My breathlessness is about (\d+) out of 4", re.IGNORECASE),
    re.compile(r"breath(?:ing|lessness)[^.\d]*?(\d+) out of 4", re.IGNORECASE),
]
FATIGUE_PATTERNS = [
    re.compile(r"My fatigue is about (\d+) out of 10", re.IGNORECASE),
    re.compile(r"fatigue[^.\d]*?(\d+) out of 10", re.IGNORECASE),
]
SYMPTOM_SCALE = {"pain": 10, "breathlessness": 4, "fatigue": 10}
SYMPTOM_METRIC = {"pain": M.PAIN_NRS, "breathlessness": M.BREATHLESSNESS, "fatigue": M.FATIGUE}
SYMPTOM_PATTERNS = {
    "pain": PAIN_PATTERNS,
    "breathlessness": BREATHLESSNESS_PATTERNS,
    "fatigue": FATIGUE_PATTERNS,
}
# Check-in answers (tasks/service.PHRASES) that count as a "yes" to a
# symptom question, for the daily symptom-burden score.
SYMPTOM_FLAG_PATTERNS = [
    re.compile(r"more swollen", re.IGNORECASE),
    re.compile(r"feverish|fever or chills.*yes|chills", re.IGNORECASE),
    re.compile(r"redness spreading|spreading redness", re.IGNORECASE),
    re.compile(r"some drainage", re.IGNORECASE),
]
_NEGATIONS = re.compile(r"\b(no|nothing|none|without)\b", re.IGNORECASE)


def _slot(hour: int) -> str:
    return "am" if hour < 12 else "pm"


def load_symptom(
    db: Session, patient_id: str, surgery_date: date, key: str = "pain"
) -> pd.DataFrame:
    """Daily symptom scores — columns day, am, pm, mean (NaN where absent).

    Observations of the symptom's metric type win over transcript-derived
    values on the same day and slot; the slot comes from
    ``value_json["time_of_day"]`` when the writer said, else from the hour.
    """
    metric = SYMPTOM_METRIC[key]
    scale = SYMPTOM_SCALE[key]
    patterns = SYMPTOM_PATTERNS[key]
    from_obs: dict[tuple[int, str], list[float]] = {}
    from_text: dict[tuple[int, str], list[float]] = {}

    rows = db.execute(
        select(Observation.local_date, Observation.start_time, Observation.value_num,
               Observation.value_json)
        .where(
            Observation.patient_id == patient_id,
            Observation.metric_type == metric,
            Observation.deleted_at.is_(None),
            Observation.value_num.is_not(None),
        )
    ).all()
    for local_date, start_time, value, value_json in rows:
        slot = (value_json or {}).get("time_of_day") if isinstance(value_json, dict) else None
        if slot not in ("am", "pm"):
            slot = _slot(start_time.hour)
        day = (local_date - surgery_date).days
        from_obs.setdefault((day, slot), []).append(float(value))

    transcript = db.execute(
        select(Checkin.occurred_at, CheckinMessage.text)
        .join(CheckinMessage, CheckinMessage.checkin_id == Checkin.id)
        .where(Checkin.patient_id == patient_id, CheckinMessage.who == "patient")
    ).all()
    for occurred_at, text in transcript:
        for pattern in patterns:
            match = pattern.search(text or "")
            if match:
                value = int(match.group(1))
                if 0 <= value <= scale:
                    day = (occurred_at.date() - surgery_date).days
                    from_text.setdefault((day, _slot(occurred_at.hour)), []).append(float(value))
                break

    keys = set(from_obs) | set(from_text)
    if not keys:
        return empty_symptom_frame()
    by_day: dict[int, dict[str, float]] = {}
    for day, slot in keys:
        values = from_obs.get((day, slot)) or from_text.get((day, slot)) or []
        if values:
            by_day.setdefault(day, {})[slot] = sum(values) / len(values)
    records = []
    for day in sorted(by_day):
        am = by_day[day].get("am", float("nan"))
        pm = by_day[day].get("pm", float("nan"))
        present = [v for v in (am, pm) if v == v]
        records.append({"day": day, "am": am, "pm": pm, "mean": sum(present) / len(present)})
    return pd.DataFrame(records, columns=["day", "am", "pm", "mean"])


def load_pain(db: Session, patient_id: str, surgery_date: date) -> pd.DataFrame:
    return load_symptom(db, patient_id, surgery_date, "pain")


def load_sleep_stages(db: Session, patient_id: str, surgery_date: date) -> pd.DataFrame:
    """Nightly stage hours from SLEEP_STAGES rows: day, total_h, awake_h,
    deep_h, rem_h, light_h. A missing stage is NaN, never zero — an awake
    fraction of exactly 0 % is a claim, not an absence."""
    rows = db.execute(
        select(Observation.local_date, Observation.value_num, Observation.value_json)
        .where(
            Observation.patient_id == patient_id,
            Observation.metric_type == M.SLEEP_STAGES,
            Observation.deleted_at.is_(None),
        )
        .order_by(Observation.local_date)
    ).all()
    if not rows:
        return empty_sleep_frame()
    records = []
    for local_date, total, value_json in rows:
        stages = value_json if isinstance(value_json, dict) else {}

        def hours(name: str) -> float:
            value = stages.get(name)
            return float(value) if isinstance(value, (int, float)) else float("nan")

        records.append({
            "day": (local_date - surgery_date).days,
            "total_h": float(total) if total is not None else float("nan"),
            "awake_h": hours("awake"), "deep_h": hours("deep"),
            "rem_h": hours("rem"), "light_h": hours("light"),
        })
    frame = pd.DataFrame(records)
    return frame.groupby("day", as_index=False).mean().sort_values("day").reset_index(drop=True)


def load_sessions(
    db: Session, patient_id: str, surgery_date: date, today: date, days: int = 42
) -> list[dict[str, Any]]:
    """Exercise sessions with whatever per-minute detail the source carried:
    {day, kind, minutes, cadence_spm, hr_bpm, speed_mps, steps}."""
    rows = db.execute(
        select(Observation.local_date, Observation.start_time, Observation.value_num,
               Observation.value_json)
        .where(
            Observation.patient_id == patient_id,
            Observation.metric_type == M.EXERCISE_SESSION,
            Observation.deleted_at.is_(None),
            Observation.local_date >= today - timedelta(days=days),
        )
        .order_by(Observation.start_time)
    ).all()
    out: list[dict[str, Any]] = []
    for local_date, start_time, minutes, value_json in rows:
        detail = value_json if isinstance(value_json, dict) else {}
        kind = detail.get("kind") or detail.get("sport") or detail.get("title") or "session"
        kind = str(kind).lower()
        if "walk" in kind and kind != "guided_walk":
            kind = "walk"
        out.append({
            "day": (local_date - surgery_date).days,
            "start_time": start_time,
            "kind": kind,
            "minutes": float(minutes) if minutes is not None else float(detail.get("minutes") or 0),
            "cadence_spm": _floats(detail.get("cadence_spm")),
            "hr_bpm": _floats(detail.get("hr_bpm")),
            "speed_mps": _floats(detail.get("speed_mps")),
            "steps": detail.get("steps"),
            "average_hr": detail.get("average_hr"),
        })
    return out


def _floats(values: Any) -> list[float] | None:
    if not isinstance(values, list) or not values:
        return None
    try:
        return [float(v) for v in values]
    except (TypeError, ValueError):
        return None


def load_intraday(
    db: Session, patient_id: str, surgery_date: date, today: date, metric: M, days: int = 14
) -> pd.DataFrame:
    """Hourly bins of a metric's INTERVAL/INSTANT rows: day, hour, value
    (sum for additive metrics such as steps, mean otherwise)."""
    rows = db.execute(
        select(Observation.local_date, Observation.start_time, Observation.value_num)
        .where(
            Observation.patient_id == patient_id,
            Observation.metric_type == metric,
            Observation.deleted_at.is_(None),
            Observation.value_num.is_not(None),
            Observation.granularity.in_([str(Granularity.INTERVAL), str(Granularity.INSTANT)]),
            Observation.local_date >= today - timedelta(days=days),
        )
    ).all()
    if not rows:
        return pd.DataFrame({"day": pd.Series(dtype=int), "hour": pd.Series(dtype=int),
                             "value": pd.Series(dtype=float)})
    frame = pd.DataFrame(
        [((d - surgery_date).days, t.hour, float(v)) for d, t, v in rows],
        columns=["day", "hour", "value"],
    )
    from app.engine.dataload import ADDITIVE

    agg = "sum" if str(metric) in ADDITIVE else "mean"
    return (
        frame.groupby(["day", "hour"], as_index=False)["value"].agg(agg)
        .sort_values(["day", "hour"]).reset_index(drop=True)
    )


def load_glucose(
    db: Session, patient_id: str, surgery_date: date, today: date, days: int = 14
) -> pd.DataFrame:
    rows = db.execute(
        select(Observation.local_date, Observation.value_num, Observation.granularity,
               Observation.value_json)
        .where(
            Observation.patient_id == patient_id,
            Observation.metric_type == M.BLOOD_GLUCOSE,
            Observation.deleted_at.is_(None),
            Observation.local_date >= today - timedelta(days=days),
        )
    ).all()
    if not rows:
        return empty_glucose_frame()
    return pd.DataFrame(
        [((d - surgery_date).days, float(v) if v is not None else float("nan"), str(g),
          j if isinstance(j, dict) else None) for d, v, g, j in rows],
        columns=["day", "value", "granularity", "json"],
    )


def load_checkins(db: Session, patient_id: str) -> list[dict[str, Any]]:
    """Every check-in, oldest first: when, channel, how much the patient wrote,
    and how many symptom questions they answered yes to."""
    rows = db.execute(
        select(Checkin.id, Checkin.occurred_at, Checkin.channel, CheckinMessage.who,
               CheckinMessage.text)
        .join(CheckinMessage, CheckinMessage.checkin_id == Checkin.id, isouter=True)
        .where(Checkin.patient_id == patient_id)
        .order_by(Checkin.occurred_at, Checkin.id, CheckinMessage.seq)
    ).all()
    by_id: dict[int, dict[str, Any]] = {}
    for checkin_id, occurred_at, channel, who, text in rows:
        entry = by_id.setdefault(checkin_id, {
            "id": checkin_id, "occurred_at": occurred_at, "channel": channel,
            "patient_chars": 0, "n_patient_msgs": 0, "flags": 0,
        })
        if who == "patient" and text:
            entry["patient_chars"] += len(text)
            entry["n_patient_msgs"] += 1
            entry["flags"] += symptom_flags(text)
    return sorted(by_id.values(), key=lambda c: (c["occurred_at"], c["id"]))


def symptom_flags(text: str) -> int:
    """How many yes-answers to swelling/fever/redness/drainage one patient
    line carries (the phrases tasks/service writes for a yes)."""
    if _NEGATIONS.search(text):
        return 0
    return sum(1 for pattern in SYMPTOM_FLAG_PATTERNS if pattern.search(text))


def load_tasks_with_records(
    db: Session, patient_id: str, today: date, days: int = 14
) -> list[dict[str, Any]]:
    """Active tasks (any lifecycle status) with their last-14-day records:
    {id, title, kind, records: {date: (status, source)}}."""
    tasks = db.scalars(
        select(AdherenceTask)
        .where(AdherenceTask.patient_id == patient_id, AdherenceTask.active.is_(True))
        .order_by(AdherenceTask.id)
    ).all()
    if not tasks:
        return []
    start = today - timedelta(days=days - 1)
    records = db.scalars(
        select(AdherenceRecord).where(
            AdherenceRecord.patient_id == patient_id, AdherenceRecord.date >= start
        )
    ).all()
    by_task: dict[int, dict[date, tuple[str, str]]] = {}
    for record in records:
        source = getattr(record, "source", None) or "record"
        by_task.setdefault(record.task_id, {})[record.date] = (str(record.status), str(source))
    return [
        {
            "id": task.id,
            "title": task.title,
            "kind": task.kind or "custom",
            "status": task.status or "pending",
            "records": by_task.get(task.id, {}),
        }
        for task in tasks
    ]


def device_last_sync(patient) -> datetime | None:
    devices = getattr(patient, "devices", None) or []
    return devices[0].last_sync_at if devices else None
