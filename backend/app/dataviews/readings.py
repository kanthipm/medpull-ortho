"""One chart's stored readings: where they come from (``summary``) and the
readings themselves, newest first, a page at a time (``browse``).

A reading is an ``Observation`` row. Tombstoned rows are never returned, and
neither is ``raw_payload``: the provider's own body can carry identifiers
the console has no use for, and ``value_json`` already holds the detail a
reader needs (stage hours, the method a MedPull measurement used).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.config import settings
from app.dataviews import iso, window_start
from app.dataviews.roster import confidence_level
from app.engine.data_catalog import (
    EXERCISE_SESSIONS,
    FAMILY_KEYS,
    FAMILY_NAMES,
    catalog,
    family_metrics,
    family_of,
    source_name,
)
from app.engine.dataload import ADDITIVE, source_rank
from app.engine.pipeline import compute_input_hash, latest_assessment
from app.engine.sources import has_app, source_profile
from app.hep.schedule import pathway_of
from app.models.connection import WearableConnection
from app.models.enums import Granularity
from app.models.hospital import Hospital
from app.models.mobile import PatientSession, live_session_clause
from app.models.observation import Observation
from app.models.patient import Patient

CALENDAR_DAYS = 60
DEFAULT_PAGE = 50
MAX_PAGE = 200

_SUMMARY = str(Granularity.DAILY_SUMMARY)


def patient_header(db: Session, patient: Patient, today: date) -> dict[str, Any]:
    """Who the chart is, in the few fields every chart view repeats."""
    hospital = db.get(Hospital, patient.hospital_id) if patient.hospital_id else None
    return {
        "id": patient.id,
        "name": patient.name,
        "initials": patient.initials,
        "pathway": pathway_of(patient),
        "hospital": {"id": hospital.id, "name": hospital.name} if hospital else None,
        # "recovery": days count from an operation; "general": from the day
        # the person joined, with no recovery curve.
        "mode": "general" if str(patient.procedure_type) == "NONE" else "recovery",
        "day_zero": patient.surgery_date.isoformat(),
        "postop_day": (today - patient.surgery_date).days,
    }


# --- summary -------------------------------------------------------------------------


def _devices(patient: Patient) -> list[dict[str, Any]]:
    return [
        {
            "id": d.id,
            "provider": str(d.source_provider),
            "provider_name": source_name(str(d.source_provider)),
            "model": d.device_model,
            "status": d.status,
            "connected_at": iso(d.connected_at),
            "last_sync_at": iso(d.last_sync_at),
            "via_junction": d.id.startswith("junction:"),
        }
        for d in patient.devices
    ]


def _connections(db: Session, patient: Patient) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(WearableConnection)
        .where(WearableConnection.patient_id == patient.id)
        .order_by(WearableConnection.id)
    ).all()
    return [
        {
            "aggregator": str(c.aggregator),
            "status": str(c.status),
            "environment": c.environment,
            "providers": c.providers or [],
            "last_event_at": iso(c.last_event_at),
            "last_data_at": iso(c.last_data_at),
            "last_backfill_at": iso(c.last_backfill_at),
            "last_error": c.last_error,
        }
        for c in rows
    ]


def _app(db: Session, patient: Patient) -> dict[str, Any]:
    last_seen = db.scalar(
        select(func.max(PatientSession.last_seen_at))
        .where(PatientSession.patient_id == patient.id, live_session_clause())
    )
    return {"signed_in": has_app(db, patient), "last_seen_at": iso(last_seen),
            "texts": bool(patient.phone)}


def _metric_rows(db: Session, patient: Patient) -> list[dict[str, Any]]:
    """Every metric type this chart has a reading of, or a signal card for:
    how many readings, over which days, from which sources, and whether this
    person's setup can produce it at all (engine/sources.py)."""
    by_source = db.execute(
        select(
            Observation.metric_type, Observation.source_provider, func.count(Observation.id),
            func.min(Observation.local_date), func.max(Observation.local_date),
            func.max(Observation.ingested_at),
        )
        .where(Observation.patient_id == patient.id, Observation.deleted_at.is_(None))
        .group_by(Observation.metric_type, Observation.source_provider)
    ).all()
    day_counts = dict(
        db.execute(
            select(Observation.metric_type, func.count(func.distinct(Observation.local_date)))
            .where(Observation.patient_id == patient.id, Observation.deleted_at.is_(None))
            .group_by(Observation.metric_type)
        ).all()
    )
    stored: dict[str, dict[str, Any]] = {}
    for metric_type, provider, count, first, last, ingested in by_source:
        row = stored.setdefault(str(metric_type), {
            "count": 0, "first": None, "last": None, "last_ingested_at": None, "sources": [],
        })
        row["count"] += int(count)
        row["first"] = first if row["first"] is None or first < row["first"] else row["first"]
        row["last"] = last if row["last"] is None or last > row["last"] else row["last"]
        if row["last_ingested_at"] is None or ingested > row["last_ingested_at"]:
            row["last_ingested_at"] = ingested
        row["sources"].append({
            "key": str(provider), "name": source_name(str(provider)),
            "rank": source_rank(str(provider)), "count": int(count),
            "first": iso(first), "last": iso(last),
        })

    profile = source_profile(db, patient)
    out = []
    for entry in catalog()["metrics"]:
        key = entry["key"]
        have = stored.get(key)
        available = profile.get(key)
        if have is None and available is None:
            continue
        out.append({
            "metric_type": key,
            "label": entry["label"],
            "family": entry["family"],
            "unit": entry["unit"],
            "tier": entry["tier"],
            "in_house": entry["in_house"],
            "computed": entry["computed"],
            "count": have["count"] if have else 0,
            "days": int(day_counts.get(key, 0)),
            "first": iso(have["first"]) if have else None,
            "last": iso(have["last"]) if have else None,
            "last_ingested_at": iso(have["last_ingested_at"]) if have else None,
            "sources": sorted(have["sources"], key=lambda s: (s["rank"], s["key"])) if have else [],
            "availability": available["availability"] if available else None,
            "availability_note": available["note"] if available else None,
        })
    return out


def _calendar(db: Session, patient: Patient, today: date) -> dict[str, Any]:
    """Which families have anything on each of the last sixty days."""
    since = window_start(today, CALENDAR_DAYS)
    by_day: dict[date, set[str]] = {}
    rows = db.execute(
        select(Observation.local_date, Observation.metric_type)
        .where(
            Observation.patient_id == patient.id,
            Observation.deleted_at.is_(None),
            Observation.local_date >= since,
            Observation.local_date <= today,
        )
        .distinct()
    ).all()
    for day, metric_type in rows:
        family = family_of(metric_type)
        if family is not None:
            by_day.setdefault(day, set()).add(family)
    if settings.hep_enabled:
        from app.hep.models import ExerciseAssignment

        done_days = db.scalars(
            select(ExerciseAssignment.scheduled_for)
            .where(
                ExerciseAssignment.patient_id == patient.id,
                ExerciseAssignment.status == "done",
                ExerciseAssignment.scheduled_for >= since,
                ExerciseAssignment.scheduled_for <= today,
            )
            .distinct()
        ).all()
        for day in done_days:
            by_day.setdefault(day, set()).add(EXERCISE_SESSIONS)
    days = []
    for offset in range(CALENDAR_DAYS):
        day = since + timedelta(days=offset)
        families = [key for key in FAMILY_KEYS if key in by_day.get(day, ())]
        days.append({"date": day.isoformat(), "count": len(families), "families": families})
    return {
        "days": CALENDAR_DAYS,
        "since": since.isoformat(),
        "until": today.isoformat(),
        "families": [{"key": key, "name": FAMILY_NAMES[key]} for key in FAMILY_KEYS],
        "by_day": days,
    }


def _assessment(db: Session, patient: Patient) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """The latest stored assessment, as stored: the risk read with its
    reasons, the composite, confidence and the trajectory; and the reported
    signals when there are any. Nothing is recomputed. ``current`` says
    whether the stored read still matches what is on file (the engine's own
    staleness check, which reads counts and writes nothing)."""
    row = latest_assessment(db, patient.id)
    if row is None:
        return None, None
    analytics = row.analytics or {}
    confidence = analytics.get("confidence") or {}
    composite = analytics.get("composite") or {}
    reported = analytics.get("reported")
    followed_by_text = bool(reported and reported.get("followed") and not confidence.get("panel"))
    assessment = {
        "computed_at": iso(row.computed_at),
        "engine_version": row.engine_version,
        "current": row.input_hash == compute_input_hash(db, patient.id),
        # What the tier was read from: the wearable's signals, what the
        # person reported by check-in (no wearable on file), or nothing yet.
        "basis": ("reported" if followed_by_text
                  else "device" if confidence.get("panel") else "none"),
        "risk": {
            "level": str(row.risk_level),
            "score": row.risk_score,
            "reasons": row.reasons or [],
        },
        "composite": {
            "index": composite.get("index"),
            "level": composite.get("level"),
            "drivers": composite.get("drivers") or [],
        },
        "confidence": {
            "score": row.data_confidence,
            "level": confidence.get("level") or confidence_level(row.data_confidence),
            "days_with_data": confidence.get("days_with_data"),
            "window_days": confidence.get("window_days"),
            "dark_metrics": confidence.get("dark_metrics") or [],
            "panel": confidence.get("panel") or [],
        },
        "trajectory": analytics.get("trajectory"),
    }
    has_reports = bool(reported) and bool(
        reported.get("checkins_14d") or reported.get("load_days") or reported.get("program_days")
    )
    return assessment, (reported if has_reports else None)


def summary(db: Session, patient: Patient, today: date) -> dict[str, Any]:
    assessment, reported = _assessment(db, patient)
    return {
        "patient": patient_header(db, patient, today),
        "as_of": today.isoformat(),
        "devices": _devices(patient),
        "connections": _connections(db, patient),
        "app": _app(db, patient),
        "metrics": _metric_rows(db, patient),
        "calendar": _calendar(db, patient, today),
        "assessment": assessment,
        "reported": reported,
    }


# --- browse --------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadingFilter:
    """What a page of readings is narrowed by. ``metric_type`` and ``family``
    are both allowed; a type outside the family simply matches nothing."""

    metric_type: str | None = None
    family: str | None = None
    source: str | None = None
    granularity: str | None = None
    start: date | None = None
    end: date | None = None

    def view(self) -> dict[str, Any]:
        return {
            "metric_type": self.metric_type, "family": self.family, "source": self.source,
            "granularity": self.granularity, "from": iso(self.start), "to": iso(self.end),
        }


def _conditions(patient_id: str, f: ReadingFilter, *, skip: str | None = None) -> list[ColumnElement]:
    """The WHERE clauses for a filter. ``skip`` leaves one dimension out, so
    a facet counts what choosing another value of it would show."""
    where: list[ColumnElement] = [
        Observation.patient_id == patient_id,
        Observation.deleted_at.is_(None),
    ]
    if skip != "metric":
        if f.metric_type is not None:
            where.append(Observation.metric_type == f.metric_type)
        if f.family is not None:
            where.append(Observation.metric_type.in_(family_metrics(f.family)))
    if skip != "source" and f.source is not None:
        where.append(Observation.source_provider == f.source)
    if f.granularity is not None:
        where.append(Observation.granularity == f.granularity)
    if f.start is not None:
        where.append(Observation.local_date >= f.start)
    if f.end is not None:
        where.append(Observation.local_date <= f.end)
    return where


def encode_cursor(row: Observation) -> str:
    raw = f"{row.start_time.isoformat()}|{row.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """(start_time, id) of the last row of the page before. ValueError when
    the string is not a cursor this module wrote."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        stamp, _, row_id = raw.rpartition("|")
        return datetime.fromisoformat(stamp), int(row_id)
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError("Not a cursor from this list") from e


def series_use(db: Session, patient_id: str, rows: list[Observation]) -> dict[int, bool]:
    """Whether each row enters the daily series the engine builds
    (engine/dataload.py): its source must be the best-ranked one that
    reported that metric that day, it must carry a number, and for an
    additive metric on a day the winning source sent a daily summary, it must
    be that summary (the parts are the same total counted again)."""
    pairs = {(str(r.metric_type), r.local_date) for r in rows}
    if not pairs:
        return {}
    present = db.execute(
        select(Observation.metric_type, Observation.local_date, Observation.source_provider,
               Observation.granularity)
        .where(
            Observation.patient_id == patient_id,
            Observation.deleted_at.is_(None),
            Observation.value_num.is_not(None),
            Observation.metric_type.in_({metric for metric, _ in pairs}),
            Observation.local_date.in_({day for _, day in pairs}),
        )
        .distinct()
    ).all()
    best: dict[tuple[str, date], int] = {}
    for metric_type, day, provider, _ in present:
        key = (str(metric_type), day)
        rank = source_rank(str(provider))
        best[key] = min(best.get(key, rank), rank)
    summarised = {
        (str(metric_type), day)
        for metric_type, day, provider, granularity in present
        if str(granularity) == _SUMMARY and source_rank(str(provider)) == best[(str(metric_type), day)]
    }
    used: dict[int, bool] = {}
    for r in rows:
        key = (str(r.metric_type), r.local_date)
        wins = r.value_num is not None and source_rank(str(r.source_provider)) == best.get(key)
        if wins and key[0] in ADDITIVE and key in summarised:
            wins = str(r.granularity) == _SUMMARY
        used[r.id] = bool(wins)
    return used


def reading_row(row: Observation, patient: Patient, used: bool) -> dict[str, Any]:
    return {
        "id": row.id,
        "metric_type": str(row.metric_type),
        "value": row.value_num,
        "unit": row.unit,
        "json": row.value_json,
        "start_time": iso(row.start_time),
        "end_time": iso(row.end_time),
        "local_date": iso(row.local_date),
        "postop_day": (row.local_date - patient.surgery_date).days,
        "granularity": str(row.granularity),
        "source": str(row.source_provider),
        "device": row.source_device_id,
        "body_site": row.body_site,
        "side": row.side,
        "patient_reported": bool(row.is_patient_reported),
        "revision": row.revision,
        "ingested_at": iso(row.ingested_at),
        "used_in_series": used,
    }


def page(
    db: Session, patient: Patient, f: ReadingFilter, limit: int,
    after: tuple[datetime, int] | None = None,
) -> tuple[list[Observation], bool]:
    """Up to ``limit`` readings newest first, and whether more follow. Keyset
    on (start_time, id), which the (patient, metric, start_time) index and
    the primary key cover."""
    stmt = select(Observation).where(*_conditions(patient.id, f))
    if after is not None:
        stamp, row_id = after
        stmt = stmt.where(
            (Observation.start_time < stamp)
            | ((Observation.start_time == stamp) & (Observation.id < row_id))
        )
    rows = list(db.scalars(
        stmt.order_by(Observation.start_time.desc(), Observation.id.desc()).limit(limit + 1)
    ).all())
    return rows[:limit], len(rows) > limit


def _facet(db: Session, column, where: list[ColumnElement]) -> dict[str, int]:
    return {str(key): int(count) for key, count in db.execute(
        select(column, func.count(Observation.id)).where(*where).group_by(column)
    ).all()}


def facets(db: Session, patient: Patient, f: ReadingFilter) -> dict[str, Any]:
    """Counts for the filter's two pickers. Each counts with every other
    part of the filter applied and its own left out, so the list shows what
    choosing a different value would return."""
    by_metric = _facet(db, Observation.metric_type, _conditions(patient.id, f, skip="metric"))
    by_source = _facet(db, Observation.source_provider, _conditions(patient.id, f, skip="source"))
    by_family: dict[str, int] = {}
    for metric_type, count in by_metric.items():
        family = family_of(metric_type)
        if family is not None:
            by_family[family] = by_family.get(family, 0) + count
    labels = {entry["key"]: entry["label"] for entry in catalog()["metrics"]}
    return {
        "metric_type": [
            {"key": key, "label": labels.get(key, key), "family": family_of(key), "count": count}
            for key, count in sorted(by_metric.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "family": [
            {"key": key, "name": FAMILY_NAMES[key], "count": by_family[key]}
            for key in FAMILY_KEYS if key in by_family
        ],
        "source": [
            {"key": key, "name": source_name(key), "rank": source_rank(key), "count": count}
            for key, count in sorted(by_source.items(), key=lambda kv: (source_rank(kv[0]), kv[0]))
        ],
    }


def browse(
    db: Session, patient: Patient, f: ReadingFilter, limit: int,
    after: tuple[datetime, int] | None = None,
) -> dict[str, Any]:
    rows, more = page(db, patient, f, limit, after)
    used = series_use(db, patient.id, rows)
    total = db.scalar(select(func.count(Observation.id)).where(*_conditions(patient.id, f)))
    return {
        "patient_id": patient.id,
        "filters": f.view(),
        "limit": limit,
        "total": int(total or 0),
        "rows": [reading_row(r, patient, used[r.id]) for r in rows],
        "facets": facets(db, patient, f),
        "next_cursor": encode_cursor(rows[-1]) if more and rows else None,
    }
