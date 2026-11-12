"""The roster by data family: for every chart a console may list, how many
days in the window carry each kind of data, from which sources, and how
recently, beside the stored risk read.

Seven queries however long the roster is: hospitals, devices, the latest
assessment's columns (never its analytics blob), one grouped pass over the
observation table, check-ins, and the exercise calendar.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.dataviews import iso, window_start
from app.engine.confidence import GATE, HIGH_GATE
from app.engine.data_catalog import (
    EXERCISE_SESSIONS,
    FAMILY_KEYS,
    FAMILY_NAMES,
    family_of,
)
from app.engine.dataload import source_rank
from app.hep.schedule import pathway_of
from app.models.checkin import Checkin
from app.models.enums import ConfidenceLevel
from app.models.hospital import Hospital
from app.models.insight import RiskAssessment
from app.models.observation import Observation
from app.models.patient import Device, Patient


def confidence_level(score: float) -> str:
    """The level the engine gives a coverage score (engine/confidence.py)."""
    if score >= HIGH_GATE:
        return str(ConfidenceLevel.HIGH)
    if score >= GATE:
        return str(ConfidenceLevel.MEDIUM)
    return str(ConfidenceLevel.LOW)


def _empty_cell() -> dict[str, Any]:
    return {"days": 0, "rows": 0, "last": None, "sources": []}


class _Cell:
    """One chart's one family while the grouped rows are folded in."""

    def __init__(self) -> None:
        self.days: set[date] = set()
        self.rows = 0
        self.sources: set[str] = set()

    def add(self, day: date, rows: int, source: str | None) -> None:
        self.days.add(day)
        self.rows += rows
        if source:
            self.sources.add(source)

    def view(self) -> dict[str, Any]:
        return {
            "days": len(self.days),
            "rows": self.rows,
            "last": iso(max(self.days)) if self.days else None,
            "sources": sorted(self.sources, key=lambda s: (source_rank(s), s)),
        }


def _latest_assessments(db: Session, ids: list[str]) -> dict[str, Any]:
    """The newest assessment's scalar columns per chart. The analytics blob
    is the largest value in the database and is never selected here."""
    rows = db.execute(
        select(
            RiskAssessment.patient_id, RiskAssessment.risk_level, RiskAssessment.risk_score,
            RiskAssessment.data_confidence, RiskAssessment.computed_at,
        )
        .where(RiskAssessment.patient_id.in_(ids))
        .order_by(RiskAssessment.patient_id, RiskAssessment.computed_at.desc(),
                  RiskAssessment.id.desc())
    ).all()
    latest: dict[str, Any] = {}
    for row in rows:
        latest.setdefault(row.patient_id, row)
    return latest


def _devices(db: Session, ids: list[str]) -> dict[str, Device]:
    """Each chart's newest connected device (the order Patient.devices uses)."""
    rows = db.scalars(
        select(Device)
        .where(Device.patient_id.in_(ids), Device.status != "revoked")
        .order_by(Device.connected_at.desc(), Device.id)
    ).all()
    newest: dict[str, Device] = {}
    for device in rows:
        newest.setdefault(device.patient_id, device)
    return newest


def _observation_cells(db: Session, ids: list[str], since: date, today: date) -> dict[tuple[str, str], _Cell]:
    rows = db.execute(
        select(
            Observation.patient_id, Observation.metric_type, Observation.source_provider,
            Observation.local_date, func.count(Observation.id),
        )
        .where(
            Observation.patient_id.in_(ids),
            Observation.deleted_at.is_(None),
            Observation.local_date >= since,
            Observation.local_date <= today,
        )
        .group_by(Observation.patient_id, Observation.metric_type,
                  Observation.source_provider, Observation.local_date)
    ).all()
    cells: dict[tuple[str, str], _Cell] = {}
    for patient_id, metric_type, provider, day, count in rows:
        family = family_of(metric_type)
        if family is None:
            continue
        cells.setdefault((patient_id, family), _Cell()).add(day, int(count), str(provider))
    return cells


def _checkins(db: Session, ids: list[str], since: date) -> dict[str, dict[str, Any]]:
    in_window = case((Checkin.occurred_at >= datetime.combine(since, time.min), 1), else_=0)
    rows = db.execute(
        select(Checkin.patient_id, func.sum(in_window), func.max(Checkin.occurred_at))
        .where(Checkin.patient_id.in_(ids))
        .group_by(Checkin.patient_id)
    ).all()
    return {pid: {"count": int(count or 0), "last_at": iso(last)} for pid, count, last in rows}


def _exercises(
    db: Session, ids: list[str], since: date, today: date
) -> tuple[dict[str, dict[str, Any]], dict[str, _Cell]]:
    """What was on each chart's exercise calendar in the window and what was
    done of it, plus the family cell: the days with a done session."""
    from app.hep.models import ExerciseAssignment

    rows = db.execute(
        select(
            ExerciseAssignment.patient_id, ExerciseAssignment.scheduled_for,
            ExerciseAssignment.status, ExerciseAssignment.completion_source,
            func.count(ExerciseAssignment.id), func.max(ExerciseAssignment.completed_at),
        )
        .where(
            ExerciseAssignment.patient_id.in_(ids),
            ExerciseAssignment.scheduled_for >= since,
            ExerciseAssignment.scheduled_for <= today,
        )
        .group_by(ExerciseAssignment.patient_id, ExerciseAssignment.scheduled_for,
                  ExerciseAssignment.status, ExerciseAssignment.completion_source)
    ).all()
    totals: dict[str, dict[str, Any]] = {}
    cells: dict[str, _Cell] = {}
    for patient_id, day, status, source, count, completed_at in rows:
        total = totals.setdefault(patient_id, {"assigned": 0, "done": 0, "last_at": None})
        total["assigned"] += int(count)
        if status != "done":
            continue
        total["done"] += int(count)
        if completed_at is not None and (total["last_at"] is None or completed_at > total["last_at"]):
            total["last_at"] = completed_at
        cells.setdefault(patient_id, _Cell()).add(day, int(count), source)
    for total in totals.values():
        total["last_at"] = iso(total["last_at"])
    return totals, cells


def coverage(db: Session, patients: list[Patient], days: int, today: date) -> dict[str, Any]:
    """The roster view for ``patients`` (already narrowed to what the console
    may list) over the ``days`` calendar days ending ``today``."""
    since = window_start(today, days)
    ids = [p.id for p in patients]
    hospitals = dict(db.execute(select(Hospital.id, Hospital.name)).all()) if ids else {}
    assessments = _latest_assessments(db, ids) if ids else {}
    devices = _devices(db, ids) if ids else {}
    cells = _observation_cells(db, ids, since, today) if ids else {}
    checkins = _checkins(db, ids, since) if ids else {}
    exercises: dict[str, dict[str, Any]] = {}
    sessions: dict[str, _Cell] = {}
    if ids and settings.hep_enabled:
        exercises, sessions = _exercises(db, ids, since, today)

    rows = []
    with_data = dict.fromkeys(FAMILY_KEYS, 0)
    for patient in patients:
        row_cells = {}
        for family in FAMILY_KEYS:
            cell = (sessions.get(patient.id) if family == EXERCISE_SESSIONS
                    else cells.get((patient.id, family)))
            row_cells[family] = cell.view() if cell is not None else _empty_cell()
            if row_cells[family]["days"]:
                with_data[family] += 1
        assessment = assessments.get(patient.id)
        device = devices.get(patient.id)
        rows.append({
            "id": patient.id,
            "name": patient.name,
            "initials": patient.initials,
            "pathway": pathway_of(patient),
            "hospital": ({"id": patient.hospital_id, "name": hospitals.get(patient.hospital_id)}
                         if patient.hospital_id else None),
            "device": ({"provider": str(device.source_provider), "model": device.device_model,
                        "status": device.status, "last_sync_at": iso(device.last_sync_at)}
                       if device is not None else None),
            "risk_level": str(assessment.risk_level) if assessment is not None else None,
            "confidence": ({"score": assessment.data_confidence,
                            "level": confidence_level(assessment.data_confidence)}
                           if assessment is not None else None),
            "assessed_at": iso(assessment.computed_at) if assessment is not None else None,
            "cells": row_cells,
            "checkins": checkins.get(patient.id, {"count": 0, "last_at": None}),
            "exercises": exercises.get(patient.id, {"assigned": 0, "done": 0, "last_at": None}),
        })
    return {
        "as_of": today.isoformat(),
        "days": days,
        "since": since.isoformat(),
        "families": [{"key": key, "name": FAMILY_NAMES[key], "patients": with_data[key]}
                     for key in FAMILY_KEYS],
        "patients": rows,
    }
