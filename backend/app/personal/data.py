"""What the personal metrics read, loaded once per dashboard.

The clinic engine indexes everything by post-op day because a recovery is
measured from an operation. A subscriber's readouts are measured from
today, so everything here is indexed by calendar date: the daily series
the engine already builds (re-keyed), the nightly sleep detail, exercise
sessions, hourly steps, and the subjective log the check-in writes.

Observations are read for the row that owns the wearable stream
(``scope.data_patient_id``), never blindly for the profile: a personal
profile linked to a clinic chart has no rows of its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.dataload import load_daily_series
from app.models.enums import Granularity
from app.models.enums import MetricType as M
from app.models.observation import Observation
from app.models.patient import Patient
from app.models.personal import PersonalLog
from app.personal.scope import data_patient_id

WINDOW_DAYS = 90


@dataclass
class PersonalData:
    today: date
    since: date
    # metric key -> Series of daily values indexed by date
    series: dict[str, pd.Series] = field(default_factory=dict)
    # one row per night: date, total_h, awake_h, deep_h, rem_h, light_h,
    # bedtime (datetime|None), waketime (datetime|None), efficiency
    sleep: pd.DataFrame = field(default_factory=pd.DataFrame)
    # {date, kind, minutes, average_hr, steps}
    sessions: list[dict[str, Any]] = field(default_factory=list)
    # hourly steps: date, hour, value
    intraday_steps: pd.DataFrame = field(default_factory=pd.DataFrame)
    # key -> Series indexed by date (energy, soreness, mood, sleep_quality, rpe...)
    logs: dict[str, pd.Series] = field(default_factory=dict)
    notes: list[dict[str, Any]] = field(default_factory=list)

    def get(self, key: str) -> pd.Series:
        s = self.series.get(key)
        if s is None:
            return pd.Series(dtype=float)
        return s

    @property
    def days_with_data(self) -> int:
        days: set[date] = set()
        for s in self.series.values():
            days.update(d for d in s.index)
        return len(days)


def _parse_stamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _rekey(series: dict[str, pd.Series], anchor: date, since: date) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for key, s in series.items():
        if len(s) == 0:
            continue
        dated = pd.Series(
            s.values.astype(float),
            index=[anchor + timedelta(days=int(d)) for d in s.index],
        )
        dated = dated[[d >= since for d in dated.index]]
        if len(dated):
            out[key] = dated.sort_index()
    return out


def load_sleep_detail(
    db: Session, owner_id: str, since: date
) -> pd.DataFrame:
    """One row per night from SLEEP_STAGES rows (the sleep summaries carry
    stage hours and, from most providers, bedtime and wake stamps)."""
    rows = db.execute(
        select(Observation.local_date, Observation.value_num, Observation.value_json,
               Observation.start_time, Observation.end_time)
        .where(
            Observation.patient_id == owner_id,
            Observation.metric_type == M.SLEEP_STAGES,
            Observation.deleted_at.is_(None),
            Observation.local_date >= since,
        )
        .order_by(Observation.local_date)
    ).all()
    records = []
    for local_date, total, value_json, start_time, end_time in rows:
        stages = value_json if isinstance(value_json, dict) else {}

        def hours(name: str) -> float:
            value = stages.get(name)
            return float(value) if isinstance(value, (int, float)) else float("nan")

        bedtime = _parse_stamp(stages.get("bedtime_start"))
        waketime = _parse_stamp(stages.get("bedtime_stop"))
        if bedtime is None and start_time is not None and end_time is not None \
                and (end_time - start_time) < timedelta(hours=20):
            bedtime, waketime = start_time, end_time
        total_h = float(total) if total is not None else float("nan")
        awake = hours("awake")
        efficiency = stages.get("efficiency")
        if not isinstance(efficiency, (int, float)):
            efficiency = (
                (total_h - awake) / total_h
                if total_h == total_h and awake == awake and total_h > 0 else float("nan")
            )
            if efficiency == efficiency and efficiency > 1:
                efficiency = efficiency / 100.0
        elif efficiency > 1:
            efficiency = float(efficiency) / 100.0
        records.append({
            "date": local_date, "total_h": total_h, "awake_h": awake,
            "deep_h": hours("deep"), "rem_h": hours("rem"), "light_h": hours("light"),
            "bedtime": bedtime, "waketime": waketime, "efficiency": float(efficiency),
        })
    if not records:
        return pd.DataFrame(columns=["date", "total_h", "awake_h", "deep_h", "rem_h",
                                     "light_h", "bedtime", "waketime", "efficiency"])
    frame = pd.DataFrame(records)
    # One night per date: a restated summary lands on the same day.
    frame = frame.sort_values("date").drop_duplicates("date", keep="last")
    return frame.reset_index(drop=True)


def load_sessions(db: Session, owner_id: str, since: date) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Observation.local_date, Observation.start_time, Observation.value_num,
               Observation.value_json)
        .where(
            Observation.patient_id == owner_id,
            Observation.metric_type == M.EXERCISE_SESSION,
            Observation.deleted_at.is_(None),
            Observation.local_date >= since,
        )
        .order_by(Observation.start_time)
    ).all()
    out: list[dict[str, Any]] = []
    for local_date, start_time, minutes, value_json in rows:
        detail = value_json if isinstance(value_json, dict) else {}
        kind = str(detail.get("kind") or detail.get("sport") or detail.get("title") or "session")
        out.append({
            "date": local_date,
            "start_time": start_time,
            "kind": kind.lower(),
            "minutes": float(minutes) if minutes is not None else float(detail.get("minutes") or 0),
            "average_hr": detail.get("average_hr"),
            "max_hr": detail.get("max_hr"),
            "calories": detail.get("calories"),
            "distance_m": detail.get("distance") or detail.get("distance_m"),
        })
    return out


def load_intraday_steps(db: Session, owner_id: str, since: date) -> pd.DataFrame:
    rows = db.execute(
        select(Observation.local_date, Observation.start_time, Observation.value_num)
        .where(
            Observation.patient_id == owner_id,
            Observation.metric_type == M.STEPS,
            Observation.deleted_at.is_(None),
            Observation.value_num.is_not(None),
            Observation.granularity.in_([str(Granularity.INTERVAL), str(Granularity.INSTANT)]),
            Observation.local_date >= since,
        )
    ).all()
    if not rows:
        return pd.DataFrame(columns=["date", "hour", "value"])
    frame = pd.DataFrame([(d, t.hour, float(v)) for d, t, v in rows],
                         columns=["date", "hour", "value"])
    return (frame.groupby(["date", "hour"], as_index=False)["value"].sum()
            .sort_values(["date", "hour"]).reset_index(drop=True))


def load_logs(db: Session, patient_id: str, since: date) -> tuple[dict[str, pd.Series], list[dict]]:
    rows = db.scalars(
        select(PersonalLog)
        .where(PersonalLog.patient_id == patient_id, PersonalLog.date >= since)
        .order_by(PersonalLog.date, PersonalLog.id)
    ).all()
    by_key: dict[str, dict[date, float]] = {}
    notes: list[dict[str, Any]] = []
    for row in rows:
        if row.key == "note":
            if row.text:
                notes.append({"date": row.date.isoformat(), "text": row.text[:400]})
            continue
        if row.value_num is None:
            continue
        # The latest entry for a day wins (a re-answered check-in).
        by_key.setdefault(row.key, {})[row.date] = float(row.value_num)
    series = {
        key: pd.Series(list(values.values()), index=list(values.keys())).sort_index()
        for key, values in by_key.items()
    }
    return series, notes[-10:]


def load_personal_data(
    db: Session, patient: Patient, today: date | None = None, days: int = WINDOW_DAYS
) -> PersonalData:
    today = today or date.today()
    since = today - timedelta(days=days - 1)
    owner_id = data_patient_id(patient)
    owner = db.get(Patient, owner_id) or patient
    raw = load_daily_series(db, owner_id, owner.surgery_date)
    data = PersonalData(today=today, since=since)
    data.series = _rekey(raw, owner.surgery_date, since)
    data.sleep = load_sleep_detail(db, owner_id, since)
    data.sessions = load_sessions(db, owner_id, since)
    data.intraday_steps = load_intraday_steps(db, owner_id, since - timedelta(days=0))
    data.logs, data.notes = load_logs(db, patient.id, since)
    return data
