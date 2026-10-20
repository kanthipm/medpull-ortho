"""What the sports boards read, loaded once per request.

``SportsData`` wraps the personal tier's ``PersonalData`` (the wearable
stream, nightly sleep detail, exercise sessions, hourly steps) and adds
what an athlete has that a subscriber does not: logged sessions with their
load, the morning wellness answers, performance tests, injuries with their
rehab measures, and the team calendar.

Two bridges keep the personal readiness engine working unchanged:

* Sessions become ``logs["rpe"]`` and ``logs["session_minutes"]`` per day
  (load-weighted RPE over the day's sessions), so ``load_panel`` runs on
  session-RPE load the moment five sessions exist.
* Wellness answers become the subjective log keys the personal panel reads
  (energy, soreness, mood, sleep_quality), while the full set stays in
  ``wellness`` for the Hooper index and the recovery rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.sports import (
    SportsEvent,
    SportsInjury,
    SportsProfile,
    SportsRehabMeasure,
    SportsSession,
    SportsTest,
    SportsWellness,
)
from app.personal.data import PersonalData, load_personal_data
from app.sports.catalog.wellness import WELLNESS

WINDOW_DAYS = 120


@dataclass
class SportsData:
    today: date
    since: date
    personal: PersonalData
    profile: SportsProfile
    sessions: list[SportsSession] = field(default_factory=list)
    wellness: dict[str, pd.Series] = field(default_factory=dict)
    wellness_text: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    tests: list[SportsTest] = field(default_factory=list)
    injuries: list[SportsInjury] = field(default_factory=list)
    measures: dict[int, list[SportsRehabMeasure]] = field(default_factory=dict)
    events: list[SportsEvent] = field(default_factory=list)

    @property
    def active_injuries(self) -> list[SportsInjury]:
        return [i for i in self.injuries if i.status == "active"]

    def session_load_series(self) -> pd.Series:
        """Daily session load (AU), zero on days with no session, from the
        first logged session to today."""
        if not self.sessions:
            return pd.Series(dtype=float)
        by_day: dict[date, float] = {}
        for s in self.sessions:
            by_day[s.date] = by_day.get(s.date, 0.0) + (s.load_au or 0.0)
        start = min(by_day)
        days = [start + timedelta(days=i) for i in range((self.today - start).days + 1)]
        return pd.Series([by_day.get(d, 0.0) for d in days], index=days)

    def jumps_series(self) -> pd.Series:
        if not self.sessions:
            return pd.Series(dtype=float)
        by_day: dict[date, float] = {}
        for s in self.sessions:
            if s.jumps is not None:
                by_day[s.date] = by_day.get(s.date, 0.0) + float(s.jumps)
        if not by_day:
            return pd.Series(dtype=float)
        start = min(by_day)
        days = [start + timedelta(days=i) for i in range((self.today - start).days + 1)]
        return pd.Series([by_day.get(d, 0.0) for d in days], index=days)

    def wellness_latest(self, key: str) -> tuple[date, float] | None:
        s = self.wellness.get(key)
        if s is None or len(s) == 0:
            return None
        d = s.index[-1]
        return d, float(s.iloc[-1])


def _sessions_to_logs(sessions: list[SportsSession]) -> tuple[pd.Series, pd.Series]:
    minutes: dict[date, float] = {}
    load: dict[date, float] = {}
    for s in sessions:
        if s.rpe is None:
            continue
        minutes[s.date] = minutes.get(s.date, 0.0) + float(s.minutes)
        load[s.date] = load.get(s.date, 0.0) + float(s.load_au or s.minutes * s.rpe)
    if not minutes:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    days = sorted(minutes)
    rpe = pd.Series([load[d] / minutes[d] if minutes[d] > 0 else 0.0 for d in days], index=days)
    mins = pd.Series([minutes[d] for d in days], index=days)
    return rpe, mins


def load_sports_data(db: Session, patient: Patient, profile: SportsProfile,
                     today: date | None = None, days: int = WINDOW_DAYS) -> SportsData:
    today = today or date.today()
    since = today - timedelta(days=days - 1)
    personal = load_personal_data(db, patient, today, days=min(days, 90))
    data = SportsData(today=today, since=since, personal=personal, profile=profile)

    data.sessions = list(db.scalars(
        select(SportsSession).where(SportsSession.patient_id == patient.id, SportsSession.date >= since,
                                    SportsSession.date <= today)
        .order_by(SportsSession.date, SportsSession.id)
    ).all())
    for s in data.sessions:
        if s.load_au is None and s.rpe is not None:
            s.load_au = float(s.minutes) * float(s.rpe)

    rows = db.scalars(
        select(SportsWellness).where(SportsWellness.patient_id == patient.id, SportsWellness.date >= since)
        .order_by(SportsWellness.date, SportsWellness.id)
    ).all()
    by_key: dict[str, dict[date, float]] = {}
    for row in rows:
        if row.key == "note" or WELLNESS.get(row.key, None) and WELLNESS[row.key].kind == "text":
            if row.text:
                data.wellness_text.setdefault(row.key, []).append({"date": row.date.isoformat(), "text": row.text[:400]})
            continue
        if row.value is None:
            continue
        by_key.setdefault(row.key, {})[row.date] = float(row.value)
    data.wellness = {k: pd.Series(list(v.values()), index=list(v.keys())).sort_index() for k, v in by_key.items()}

    # Bridge into the personal engine's log keys.
    rpe, mins = _sessions_to_logs(data.sessions)
    if len(rpe):
        personal.logs["rpe"] = rpe
        personal.logs["session_minutes"] = mins
    for key, spec in WELLNESS.items():
        if spec.personal_key and key in data.wellness:
            personal.logs[spec.personal_key] = data.wellness[key]
    # The personal panel reads soreness 0–10; it also reads "energy". Fatigue
    # inverted is a fair stand-in for energy when energy itself was not asked.
    if "energy" not in personal.logs and "fatigue" in data.wellness:
        personal.logs["energy"] = (10.0 - data.wellness["fatigue"]).clip(0, 10)
    # Sessions for the weekly-minutes figure the load panel reports.
    if data.sessions and not personal.sessions:
        personal.sessions = [
            {"date": s.date, "start_time": None, "kind": s.kind, "minutes": float(s.minutes),
             "average_hr": s.average_hr, "max_hr": None, "calories": None, "distance_m": s.distance_m}
            for s in data.sessions
        ]

    data.tests = list(db.scalars(
        select(SportsTest).where(SportsTest.patient_id == patient.id).order_by(SportsTest.date, SportsTest.id)
    ).all())
    data.injuries = list(db.scalars(
        select(SportsInjury).where(SportsInjury.patient_id == patient.id).order_by(SportsInjury.date_of_injury.desc())
    ).all())
    if data.injuries:
        measures = db.scalars(
            select(SportsRehabMeasure).where(SportsRehabMeasure.patient_id == patient.id)
            .order_by(SportsRehabMeasure.date, SportsRehabMeasure.id)
        ).all()
        for m in measures:
            data.measures.setdefault(m.injury_id, []).append(m)
    if profile.team_id:
        data.events = list(db.scalars(
            select(SportsEvent).where(SportsEvent.team_id == profile.team_id,
                                      SportsEvent.date >= today - timedelta(days=14),
                                      SportsEvent.date <= today + timedelta(days=21))
            .order_by(SportsEvent.date, SportsEvent.start_time)
        ).all())
    return data
