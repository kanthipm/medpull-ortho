"""Data verification of assigned tasks.

For every active task that carries ``payload["care"]["verify"]`` and every
day of the recent window, the task's verify kind is evaluated against the
data the engine already loaded (daily series) plus the finer inputs the
care loaders read (walk sessions, hourly steps, symptom logs, check-ins,
cuff/scale rows), and an ``AdherenceRecord`` is written or upgraded:

- a record never moves down: ``verified`` stays verified whatever a later
  day's data says, a self-report the data cannot confirm stays
  ``self_attested`` (the M14 split shows it), and data only ever upgrades;
- today is never marked missed — the day is not over;
- tasks the seed wrote (no care payload) are never touched, so the seeded
  adherence rates and the golden risk tiers hold;
- self-report-only kinds (medication, questionnaire, photo, precautions)
  are never written here — the check-in and the app write those rows.

Runs inside ``run_patient`` ahead of the adherence scorer, so the records it
writes are what M14/M15 and the ADHERENCE_LOW rule read on the same pass.
Idempotent: a second run with the same data writes nothing.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engine import baseline_store
from app.engine.baseline import compute_baseline
from app.engine.care.loaders import (
    load_checkins,
    load_intraday,
    load_sessions,
    load_symptom,
)
from app.engine.care.pathways import pathway_for
from app.engine.dataload import load_daily_series
from app.engine.deviation import expected_functional
from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.enums import AdherenceStatus
from app.models.enums import MetricType as M
from app.models.enums import ProcedureType
from app.models.library import TaskVerification
from app.models.observation import Observation
from app.models.patient import Patient
from app.plan.service import RECORD_RANK, care_of
from app.plan.verify_kinds import VerifyKind, as_kind, params_for

logger = logging.getLogger(__name__)

WINDOW_DAYS = 14
BAND_LOW, BAND_HIGH = 0.75, 1.15
STEP_LENGTH_M = 0.7
MILE_M = 1609.0
BOUT_STEPS = 200          # an hour with this many steps counts as a walk bout
ACTIVE_HOUR_STEPS = 50    # an hour with this many steps counts as "moved"
WAKING_HOURS = range(7, 23)
INTRADAY_MIN_HOURS = 18

V = VerifyKind
VERIFIED, SELF, MISSED = (
    AdherenceStatus.VERIFIED, AdherenceStatus.SELF_ATTESTED, AdherenceStatus.MISSED,
)


@dataclass(frozen=True)
class Outcome:
    status: AdherenceStatus | None   # None = the data says nothing about this day
    source: str = ""
    count: float | None = None


NOTHING = Outcome(None)


class _Inputs:
    """Lazily loaded inputs shared by every task of one patient. Each loader
    runs at most once per verification pass, and only when a task needs it."""

    def __init__(self, db: Session, patient: Patient, today: date,
                 series: dict[str, pd.Series]) -> None:
        self.db, self.patient, self.today, self.series = db, patient, today, series
        self.surgery = patient.surgery_date
        self.pathway = pathway_for(patient)
        try:
            self.procedure = ProcedureType(patient.procedure_type)
        except ValueError:
            self.procedure = ProcedureType.TKA
        self._cache: dict[str, Any] = {}

    def day_index(self, on: date) -> int:
        return (on - self.surgery).days

    def daily(self, metric: M, on: date) -> float | None:
        s = self.series.get(str(metric))
        if s is None:
            return None
        idx = self.day_index(on)
        if idx not in s.index:
            return None
        value = s.loc[idx]
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if value == value else None

    def _memo(self, key: str, load: Callable[[], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = load()
        return self._cache[key]

    def sessions(self) -> dict[int, list[dict[str, Any]]]:
        def load() -> dict[int, list[dict[str, Any]]]:
            out: dict[int, list[dict[str, Any]]] = {}
            for s in load_sessions(self.db, self.patient.id, self.surgery, self.today):
                out.setdefault(int(s["day"]), []).append(s)
            return out
        return self._memo("sessions", load)

    def hourly_steps(self) -> dict[int, dict[int, float]]:
        def load() -> dict[int, dict[int, float]]:
            frame = load_intraday(self.db, self.patient.id, self.surgery, self.today, M.STEPS,
                                  days=WINDOW_DAYS + 1)
            out: dict[int, dict[int, float]] = {}
            for day, hour, value in frame.itertuples(index=False):
                out.setdefault(int(day), {})[int(hour)] = float(value)
            return out
        return self._memo("hourly", load)

    def symptom_slots(self, key: str) -> dict[int, int]:
        def load() -> dict[int, int]:
            frame = load_symptom(self.db, self.patient.id, self.surgery, key)
            out: dict[int, int] = {}
            for row in frame.itertuples(index=False):
                out[int(row.day)] = int(row.am == row.am) + int(row.pm == row.pm)
            return out
        return self._memo(f"symptom:{key}", load)

    def checkin_days(self) -> dict[date, bool]:
        """day -> whether a check-in that day carried a breathing answer."""
        def load() -> dict[date, bool]:
            out: dict[date, bool] = {}
            for c in load_checkins(self.db, self.patient.id):
                day = c["occurred_at"].date()
                out[day] = out.get(day, False)
            breathing = self.db.execute(
                select(func.date(Observation.start_time)).where(
                    Observation.patient_id == self.patient.id,
                    Observation.metric_type == M.BREATHLESSNESS,
                    Observation.deleted_at.is_(None),
                )
            ).all()
            for (day_text,) in breathing:
                try:
                    out[date.fromisoformat(str(day_text))] = True
                except ValueError:
                    continue
            return out
        return self._memo("checkins", load)

    def row_counts(self, metric: M) -> dict[date, int]:
        def load() -> dict[date, int]:
            rows = self.db.execute(
                select(Observation.local_date, func.count(Observation.id))
                .where(
                    Observation.patient_id == self.patient.id,
                    Observation.metric_type == metric,
                    Observation.deleted_at.is_(None),
                    Observation.local_date >= self.today - timedelta(days=WINDOW_DAYS),
                )
                .group_by(Observation.local_date)
            ).all()
            return {d: int(n) for d, n in rows}
        return self._memo(f"rows:{metric}", load)

    def sit_to_stand(self) -> dict[date, tuple[float, bool]]:
        """day -> (total count, any row from an IMU rather than self-report)."""
        def load() -> dict[date, tuple[float, bool]]:
            rows = self.db.execute(
                select(Observation.local_date, Observation.value_num, Observation.value_json,
                       Observation.is_patient_reported)
                .where(
                    Observation.patient_id == self.patient.id,
                    Observation.metric_type == M.SIT_TO_STAND,
                    Observation.deleted_at.is_(None),
                    Observation.local_date >= self.today - timedelta(days=WINDOW_DAYS),
                )
            ).all()
            out: dict[date, tuple[float, bool]] = {}
            for day, value, value_json, reported in rows:
                total, imu = out.get(day, (0.0, False))
                source = (value_json or {}).get("source") if isinstance(value_json, dict) else None
                imu = imu or (source == "imu") or (source is None and not reported)
                out[day] = (total + float(value or 0.0), imu)
            return out
        return self._memo("sts", load)

    def expected_steps(self, on: date) -> float | None:
        """The centre of the auto step band: the expected-curve value for
        ortho pathways (personal pre-op baseline scaled along the curve),
        else the patient's own trailing mean."""
        steps = self.series.get(str(M.STEPS))
        if steps is None:
            return None
        idx = self.day_index(on)
        if self.pathway.uses_expected_curve:
            baseline = self._memo("baseline", lambda: (
                baseline_store.load_established(self.db, self.patient.id).get(str(M.STEPS))
                or compute_baseline(str(M.STEPS), steps)
            ))
            if baseline is not None:
                expected = expected_functional(baseline, self.procedure, idx)
                if expected is not None and expected > 0:
                    return float(expected)
        window = 7 if self.pathway.uses_expected_curve else 14
        prior = steps[(steps.index < idx) & (steps.index >= idx - window)].dropna()
        if len(prior) < 3:
            return None
        return float(prior.mean())


# --- per-kind evaluation ----------------------------------------------------------------


def _walks(inputs: _Inputs, on: date) -> list[dict[str, Any]]:
    return [s for s in inputs.sessions().get(inputs.day_index(on), [])
            if s["kind"] in ("walk", "guided_walk")]


def _hours(inputs: _Inputs, on: date) -> dict[int, float]:
    return inputs.hourly_steps().get(inputs.day_index(on), {})


def _logged(n: int, times: int, source: str) -> Outcome:
    if n >= max(1, times):
        return Outcome(VERIFIED, source, float(n))
    if n >= 1:
        return Outcome(SELF, source, float(n))
    return Outcome(MISSED, source, 0.0)


def evaluate(kind: VerifyKind, params: dict[str, Any], inputs: _Inputs, on: date) -> Outcome:
    if kind is V.STEPS_MIN:
        steps = inputs.daily(M.STEPS, on)
        if steps is None:
            return NOTHING
        target = float(params.get("min_steps") or 0)
        return Outcome(VERIFIED if steps >= target else MISSED, "data:steps", steps)

    if kind is V.STEPS_BAND:
        steps = inputs.daily(M.STEPS, on)
        if steps is None:
            return NOTHING
        low, high = params.get("band_low"), params.get("band_high")
        if params.get("auto", True) or not (low and high):
            expected = inputs.expected_steps(on)
            if expected is None:
                return NOTHING
            low, high = BAND_LOW * expected, BAND_HIGH * expected
        # Over the band is still "verified": the task is to stay within, and an
        # overshoot is surfaced by M1 rather than scored as a missed day.
        return Outcome(MISSED if steps < float(low) else VERIFIED, "data:steps", steps)

    if kind is V.WALK_BOUTS:
        bouts = int(params.get("bouts") or 1)
        walks = _walks(inputs, on)
        if len(walks) >= bouts:
            return Outcome(VERIFIED, "data:sessions", float(len(walks)))
        hours = _hours(inputs, on)
        if hours:
            n = sum(1 for v in hours.values() if v >= BOUT_STEPS)
            if n >= bouts:
                return Outcome(VERIFIED, "data:steps_hourly", float(n))
        return NOTHING

    if kind is V.GUIDED_WALK:
        guided = [s for s in _walks(inputs, on) if s["kind"] == "guided_walk"]
        if guided:
            return Outcome(VERIFIED, "data:sessions", float(max(s["minutes"] for s in guided)))
        return NOTHING

    if kind is V.CONTINUOUS_WALK:
        minutes = float(params.get("minutes") or 0)
        walks = _walks(inputs, on)
        if walks:
            longest = max(float(s["minutes"]) for s in walks)
            if longest >= minutes:
                return Outcome(VERIFIED, "data:sessions", longest)
        return NOTHING

    if kind is V.DISTANCE_TARGET:
        steps = inputs.daily(M.STEPS, on)
        if steps is None:
            return NOTHING
        miles = steps * STEP_LENGTH_M / MILE_M
        target = float(params.get("miles") or 0)
        return Outcome(VERIFIED if miles >= target else MISSED, "data:steps", round(miles, 2))

    if kind is V.STAIRS:
        flights = inputs.daily(M.FLIGHTS_CLIMBED, on)
        if flights is None:
            return NOTHING
        target = float(params.get("flights") or 1)
        return Outcome(VERIFIED if flights >= target else MISSED, "data:flights_climbed", flights)

    if kind is V.SIT_TO_STAND:
        entry = inputs.sit_to_stand().get(on)
        if entry is None:
            return NOTHING
        total, imu = entry
        target = float(params.get("reps") or 1) * float(params.get("times") or 1)
        if imu:
            return Outcome(VERIFIED if total >= target else MISSED, "data:sit_to_stand", total)
        if total >= target:
            return Outcome(SELF, "self_report:sit_to_stand", total)
        return NOTHING

    if kind in (V.MOVE_HOURLY, V.SEDENTARY_LIMIT):
        hours = _hours(inputs, on)
        if len(hours) < INTRADAY_MIN_HOURS:
            return NOTHING
        if kind is V.MOVE_HOURLY:
            active = sum(1 for v in hours.values() if v >= ACTIVE_HOUR_STEPS)
            target = int(params.get("hours") or 1)
            return Outcome(VERIFIED if active >= target else MISSED, "data:steps_hourly",
                           float(active))
        longest = run = 0
        for hour in WAKING_HOURS:
            run = run + 1 if hours.get(hour, 0.0) <= 0.0 else 0
            longest = max(longest, run)
        gap_minutes = longest * 60.0
        limit = float(params.get("max_minutes") or 60)
        return Outcome(VERIFIED if gap_minutes <= limit else MISSED, "data:steps_hourly",
                       gap_minutes)

    if kind is V.PAIN_LOG:
        n = inputs.symptom_slots("pain").get(inputs.day_index(on), 0)
        return _logged(n, int(params.get("times") or 1), "data:pain_nrs")

    if kind is V.SYMPTOM_LOG:
        if on in inputs.checkin_days():
            return Outcome(VERIFIED, "data:checkin", 1.0)
        return Outcome(MISSED, "data:checkin", 0.0)

    if kind is V.OVERNIGHT_WEAR:
        slept = inputs.daily(M.SLEEP_DURATION, on)
        if slept is None:
            slept = inputs.daily(M.SLEEP_STAGES, on)
        if slept is not None:
            return Outcome(VERIFIED, "data:sleep", slept)
        return Outcome(MISSED, "data:sleep", None)

    if kind is V.THERAPY_SESSION:
        sessions = inputs.sessions().get(inputs.day_index(on), [])
        pt = [s for s in sessions if "pt" in s["kind"] or "therapy" in s["kind"]]
        if pt:
            return Outcome(VERIFIED, "data:sessions", float(max(s["minutes"] for s in pt)))
        return NOTHING

    if kind is V.WEIGHT_LOG:
        kg = inputs.daily(M.BODY_WEIGHT, on)
        if kg is not None:
            return Outcome(VERIFIED, "data:body_weight", round(kg, 1))
        return Outcome(MISSED, "data:body_weight", None)

    if kind is V.BP_LOG:
        n = inputs.row_counts(M.BLOOD_PRESSURE_SYSTOLIC).get(on, 0)
        return _logged(n, int(params.get("times") or 1), "data:bp")

    if kind is V.GLUCOSE_LOG:
        n = inputs.row_counts(M.BLOOD_GLUCOSE).get(on, 0)
        return _logged(n, int(params.get("times") or 1), "data:blood_glucose")

    if kind is V.SPO2_CHECK:
        spo2 = inputs.daily(M.SPO2, on)
        if spo2 is not None:
            return Outcome(VERIFIED, "data:spo2", spo2)
        return Outcome(MISSED, "data:spo2", None)

    if kind is V.BREATHLESSNESS_LOG:
        n = inputs.symptom_slots("breathlessness").get(inputs.day_index(on), 0)
        times = int(params.get("times") or 1)
        if n >= 1:
            return _logged(n, times, "data:breathlessness")
        if inputs.checkin_days().get(on):
            return Outcome(VERIFIED, "data:checkin", 1.0)
        return Outcome(MISSED, "data:breathlessness", 0.0)

    # medication, PROM, photo, ROM milestones, precautions, custom, fluid /
    # foot / inhaler notes: self-report only — the check-in writes those rows.
    return NOTHING


# --- the pass ------------------------------------------------------------------------------


def _window(task: AdherenceTask, care: dict[str, Any], today: date) -> tuple[date, date]:
    start = today - timedelta(days=WINDOW_DAYS - 1)
    assigned = care.get("assigned_on")
    try:
        assigned_day = date.fromisoformat(str(assigned)) if assigned else None
    except ValueError:
        assigned_day = None
    if assigned_day is None and task.created_at is not None:
        assigned_day = task.created_at.date()
    if assigned_day is not None:
        start = max(start, assigned_day)
    end = today
    if task.due_at is not None and care.get("schedule") == "once":
        end = min(end, task.due_at.date())
    return start, end


def verify_recent(
    db: Session,
    patient_id: str,
    today: date,
    series: dict[str, pd.Series] | None = None,
    days: int = WINDOW_DAYS,
) -> int:
    """Evaluate every active care task over the recent window and write or
    upgrade its records. Returns how many records were written or changed;
    rows are flushed (not committed) so the caller's transaction owns them."""
    tasks = [
        t for t in db.scalars(
            select(AdherenceTask).where(
                AdherenceTask.patient_id == patient_id, AdherenceTask.active.is_(True)
            ).order_by(AdherenceTask.id)
        ).all()
        if care_of(t) and isinstance(care_of(t).get("verify"), dict)
    ]
    if not tasks:
        return 0
    patient = db.get(Patient, patient_id)
    if patient is None:
        return 0
    if series is None:
        series = load_daily_series(db, patient_id, patient.surgery_date)
    inputs = _Inputs(db, patient, today, series)
    since = today - timedelta(days=days - 1)
    task_ids = [t.id for t in tasks]
    existing: dict[tuple[int, date], AdherenceRecord] = {
        (r.task_id, r.date): r
        for r in db.scalars(select(AdherenceRecord).where(
            AdherenceRecord.task_id.in_(task_ids), AdherenceRecord.date >= since
        )).all()
    }
    notes: dict[tuple[int, date], TaskVerification] = {
        (n.task_id, n.date): n
        for n in db.scalars(select(TaskVerification).where(
            TaskVerification.task_id.in_(task_ids), TaskVerification.date >= since
        )).all()
    }

    written = 0
    for task in tasks:
        care = care_of(task) or {}
        verify = care["verify"]
        kind = as_kind(verify.get("kind"))
        params = params_for(kind, verify.get("params") if isinstance(verify.get("params"), dict)
                            else {})
        start, end = _window(task, care, today)
        start = max(start, since)
        schedule = care.get("schedule", "daily")
        day = start
        while day <= end:
            outcome = evaluate(kind, params, inputs, day)
            day_status = outcome.status
            # Today is never missed (the day is not over), and a weekly or
            # one-off task is not missed on any single day.
            if day_status is MISSED and (day == today or schedule in ("weekly", "once")):
                day_status = None
            if day_status is None:
                day += timedelta(days=1)
                continue
            key = (task.id, day)
            record = existing.get(key)
            if record is None:
                record = AdherenceRecord(patient_id=patient_id, task_id=task.id, date=day,
                                         status=str(day_status))
                db.add(record)
                existing[key] = record
                changed = True
            elif RECORD_RANK.get(str(day_status), 0) > RECORD_RANK.get(str(record.status), 0):
                record.status = str(day_status)
                changed = True
            else:
                changed = False
            note = notes.get(key)
            if changed:
                written += 1
                if note is None:
                    note = TaskVerification(patient_id=patient_id, task_id=task.id, date=day,
                                            source=outcome.source, count=outcome.count)
                    db.add(note)
                    notes[key] = note
                else:
                    note.source, note.count = outcome.source, outcome.count
            day += timedelta(days=1)
    if written:
        db.flush()
        logger.info("Verification: %d record(s) written for %s", written, patient_id)
    return written
