"""The lifter check-in's numbers, written as Observations.

A clinic that follows people who train in a gym between visits (the HIRT
roster, app/seed/hirt.py) has no wearable to read load from. The patient
texts it: how hard today's session was and how long, and whether today's
program got done. Those two answers become rows in the observation table so
the same engine that reads step counts off a watch can read training load
off a text:

* ``SESSION_LOAD``  effort (RPE 0-10) x minutes, Foster's session-RPE, one
                    SESSION row per check-in so two sessions in a day add up
                    (engine/dataload.py lists it as additive). A rest day with
                    zero minutes is a real zero, not a gap: a week's load is
                    its training days and its rest days together.
* ``PROGRAM_DONE``  the day's answer to "did you get today's program in?",
                    1 for all, 0.5 for some, 0 for none, one DAILY_SUMMARY per
                    day (the last answer of the day stands).

Pain and the new-pain question stay in the transcript, where the care
loaders already parse them (engine/care/loaders.py); nothing here duplicates
them. One function builds the rows for the live completion path
(tasks/service.complete_task), the tokenized web form (api/checkin.py) and
the seed, so the three cannot drift.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from app.connectors.base import CanonicalObservation
from app.models.enums import Granularity
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider

LIFTER_QSET = "checkin_lifter"

PROGRAM_VALUE: dict[str, float] = {"all": 1.0, "some": 0.5, "none": 0.0}


def _int(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        return int(raw.strip())
    return None


def session_load(answers: dict[str, Any]) -> float | None:
    """RPE x minutes for the day's training, or None when the check-in did
    not say. Zero minutes is a rest day and returns 0.0."""
    minutes = _int(answers.get("minutes"))
    if minutes is None:
        return None
    if minutes <= 0:
        return 0.0
    rpe = _int(answers.get("rpe"))
    if rpe is None:
        return None
    return float(max(0, min(10, rpe)) * minutes)


def program_done(answers: dict[str, Any]) -> float | None:
    value = str(answers.get("program", "")).strip().lower()
    return PROGRAM_VALUE.get(value)


def reported_observations(
    patient_id: str, answers: dict[str, Any], at: datetime, tz_id: str = "America/Chicago",
) -> list[CanonicalObservation]:
    """The observation rows one lifter check-in produces. ``at`` is the
    patient-local wall time the answers were given, which is the day they
    are about."""
    day = at.date()
    out: list[CanonicalObservation] = []
    load = session_load(answers)
    if load is not None:
        minutes = _int(answers.get("minutes")) or 0
        rpe = _int(answers.get("rpe"))
        out.append(CanonicalObservation(
            patient_id=patient_id,
            source_provider=SourceProvider.PATIENT_REPORTED,
            metric_type=M.SESSION_LOAD,
            unit="au",
            value_num=round(load, 1),
            value_json={"rpe": rpe, "minutes": minutes, "source": "checkin"},
            start_time=at - timedelta(minutes=max(1, minutes)),
            end_time=at,
            granularity=Granularity.SESSION,
            timezone=tz_id,
            is_patient_reported=True,
        ))
    done = program_done(answers)
    if done is not None:
        out.append(CanonicalObservation(
            patient_id=patient_id,
            source_provider=SourceProvider.PATIENT_REPORTED,
            metric_type=M.PROGRAM_DONE,
            unit="fraction",
            value_num=done,
            value_json={"answer": str(answers.get("program")).lower(), "source": "checkin"},
            start_time=datetime.combine(day, time.min),
            end_time=datetime.combine(day, time(23, 59, 59)),
            granularity=Granularity.DAILY_SUMMARY,
            timezone=tz_id,
            is_patient_reported=True,
        ))
    return out


def record_reported(db, patient, answers: dict[str, Any], at: datetime) -> int:
    """Write the check-in's observations for ``patient``; returns how many
    rows were written or restated. Never raises past its caller's transcript:
    a check-in whose numbers cannot be stored is still a check-in."""
    from app.connectors.ingest import ingest_observations

    rows = reported_observations(
        patient.id, answers, at, tz_id=getattr(patient, "timezone", None) or "America/Chicago",
    )
    if not rows:
        return 0
    ingested, updated, _ = ingest_observations(db, rows)
    return ingested + updated


__all__ = [
    "LIFTER_QSET", "PROGRAM_VALUE", "session_load", "program_done", "reported_observations",
    "record_reported",
]
