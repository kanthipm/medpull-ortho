"""The console's Data tab: every stored reading, what was computed from it,
and where it came from, across a roster and for one chart.

Read-only. Roster reads go through ``scoped_clinic_patients`` (so a hospital
credential, or staff acting for one clinic, see that clinic's charts); a
chart's reads through ``require_patient``, which answers 404 for anything
that is not a clinic chart in the caller's scope. No route here recomputes
and stores, and none commits: a GET that commits re-uploads the database on
AWS. The builders are in ``app/dataviews``; the dictionary in
``app/engine/data_catalog.py``.

    GET /api/data/catalog                         the metric dictionary
    GET /api/data/coverage                        the roster by data family
    GET /api/patients/{id}/data/summary           sources, coverage, the stored risk read
    GET /api/patients/{id}/observations/browse    raw readings, paged
    GET /api/patients/{id}/series                 daily series against the baseline
    GET /api/patients/{id}/sleep                  the nights
    GET /api/patients/{id}/reported               check-ins and exercise days, by day
    GET /api/patients/{id}/data/export            any of the three as CSV
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.auth import ConsoleScope, console_scope
from app.api.scope import require_patient, scoped_clinic_patients
from app.database import get_db
from app.dataviews import readings, reported, roster, series
from app.engine.data_catalog import FAMILY_KEYS, catalog
from app.models.enums import Granularity
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider
from app.models.patient import Patient

router = APIRouter(tags=["data"])

MAX_DAYS = 365
# An export is one request held in memory; a year of one chart's readings is
# a few thousand rows, and anything past this is asked for by metric.
EXPORT_ROWS = 20_000

_METRICS = {str(m): m for m in M}
_SOURCES = {str(p) for p in SourceProvider}
_GRANULARITIES = {str(g) for g in Granularity}


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


@router.get("/data/catalog")
def data_catalog() -> JSONResponse:
    """Every metric MedPull stores or computes, with its unit, tier, sources
    and method; the care metrics; the sources in precedence order. Built from
    the code, so it cannot drift from what the engine does. Static for a
    release, hence cacheable like the glossary."""
    return JSONResponse(catalog(), headers={"Cache-Control": "public, max-age=3600"})


@router.get("/data/coverage")
def data_coverage(
    days: int = Query(default=30, ge=1, le=MAX_DAYS),
    scope: ConsoleScope = Depends(console_scope),
    db: Session = Depends(get_db),
) -> dict:
    """The roster by data family over the last ``days`` days: who has what,
    from which sources, how recently."""
    patients = scoped_clinic_patients(db, scope, order_by=Patient.name)
    return roster.coverage(db, patients, days, date.today())


@router.get("/patients/{patient_id}/data/summary")
def data_summary(
    patient_id: str,
    scope: ConsoleScope = Depends(console_scope),
    db: Session = Depends(get_db),
) -> dict:
    """One chart's sources and coverage, and what the latest stored
    assessment says (tier, reasons, composite, confidence, trajectory). The
    assessment is read as stored, never recomputed here."""
    patient = require_patient(db, scope, patient_id)
    return readings.summary(db, patient, date.today())


def _reading_filter(
    metric_type: str | None, family: str | None, source: str | None, granularity: str | None,
    start: date | None, end: date | None,
) -> readings.ReadingFilter:
    if metric_type is not None and metric_type not in _METRICS:
        raise _bad(f"Unknown metric_type: {metric_type}")
    if family is not None and family not in FAMILY_KEYS:
        raise _bad(f"Unknown family: {family}")
    if source is not None and source not in _SOURCES:
        raise _bad(f"Unknown source: {source}")
    if granularity is not None and granularity not in _GRANULARITIES:
        raise _bad(f"Unknown granularity: {granularity}")
    if start is not None and end is not None and end < start:
        raise _bad("'to' is before 'from'")
    return readings.ReadingFilter(
        metric_type=metric_type, family=family, source=source, granularity=granularity,
        start=start, end=end,
    )


@router.get("/patients/{patient_id}/observations/browse")
def browse_observations(
    patient_id: str,
    metric_type: str | None = None,
    family: str | None = None,
    source: str | None = None,
    granularity: str | None = None,
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=readings.DEFAULT_PAGE, ge=1, le=readings.MAX_PAGE),
    cursor: str | None = None,
    scope: ConsoleScope = Depends(console_scope),
    db: Session = Depends(get_db),
) -> dict:
    """The chart's stored readings newest first, a page at a time, each with
    its provenance and whether it is the one the daily series uses."""
    patient = require_patient(db, scope, patient_id)
    f = _reading_filter(metric_type, family, source, granularity, start, end)
    after = None
    if cursor:
        try:
            after = readings.decode_cursor(cursor)
        except ValueError as e:
            raise _bad(str(e)) from e
    return readings.browse(db, patient, f, limit, after)


def _metric_list(metric: str) -> list[M]:
    keys = [k.strip() for k in metric.split(",") if k.strip()]
    if not keys:
        raise _bad("Name at least one metric")
    if len(keys) > series.MAX_METRICS:
        raise _bad(f"At most {series.MAX_METRICS} metrics in one request")
    unknown = [k for k in keys if k not in _METRICS]
    if unknown:
        raise _bad(f"Unknown metric: {', '.join(unknown)}")
    return [_METRICS[k] for k in dict.fromkeys(keys)]


@router.get("/patients/{patient_id}/series")
def daily_series(
    patient_id: str,
    metric: str = Query(..., description="One metric key, or several separated by commas"),
    days: int = Query(default=90, ge=1, le=MAX_DAYS),
    scope: ConsoleScope = Depends(console_scope),
    db: Session = Depends(get_db),
) -> dict:
    """Each metric's daily series as the engine builds it, with the person's
    baseline, each day's deviation and the source that supplied the day."""
    patient = require_patient(db, scope, patient_id)
    return series.chart_series(db, patient, _metric_list(metric), days, date.today())


@router.get("/patients/{patient_id}/sleep")
def sleep_nights(
    patient_id: str,
    days: int = Query(default=30, ge=1, le=MAX_DAYS),
    scope: ConsoleScope = Depends(console_scope),
    db: Session = Depends(get_db),
) -> dict:
    """The nights: duration, stage hours, bed and wake times where the source
    sent them, averages and consistency, and what the stored assessment
    derives from them."""
    patient = require_patient(db, scope, patient_id)
    return series.sleep(db, patient, days, date.today())


@router.get("/patients/{patient_id}/reported")
def reported_grid(
    patient_id: str,
    days: int = Query(default=30, ge=1, le=120),
    scope: ConsoleScope = Depends(console_scope),
    db: Session = Depends(get_db),
) -> dict:
    """One row per day, newest first: the check-in's answers, the training
    load they give, and that day on the exercise calendar (prescribed
    against done)."""
    patient = require_patient(db, scope, patient_id)
    return reported.reported(db, patient, days, date.today())


# --- export ---------------------------------------------------------------------------


def _csv(filename: str, header: list[str], rows: list[list[Any]]) -> Response:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _observations_csv(db: Session, patient: Patient, f: readings.ReadingFilter) -> Response:
    found, _ = readings.page(db, patient, f, EXPORT_ROWS)
    used = readings.series_use(db, patient.id, found)
    header = ["date", "start_time", "end_time", "metric_type", "value", "unit", "granularity",
              "source", "device", "body_site", "side", "patient_reported", "used_in_series",
              "day", "revision", "ingested_at"]
    rows = []
    for row in found:
        r = readings.reading_row(row, patient, used[row.id])
        rows.append([r["local_date"], r["start_time"], r["end_time"], r["metric_type"], r["value"],
                     r["unit"], r["granularity"], r["source"], r["device"], r["body_site"],
                     r["side"], r["patient_reported"], r["used_in_series"], r["postop_day"],
                     r["revision"], r["ingested_at"]])
    return _csv(f"{patient.id}-readings.csv", header, rows)


def _reported_csv(db: Session, patient: Patient, days: int) -> Response:
    grid = reported.reported(db, patient, days, date.today())
    questions = [q["id"] for q in grid["questions"]]
    unit = grid["load_unit"]
    header = (["date", "checked_in"] + questions
              + ["training_load_au", "program_done", "exercises_assigned", "exercises_done",
                 "exercises_skipped", "exercises_missed", "pain_before_avg", "pain_after_max",
                 "effort_max", "effort_target", "minutes", "load_moved_kg",
                 "more_than_prescribed", "clips", "done_against_prescribed"])
    rows = []
    for row in grid["rows"]:
        ex = row["exercises"] or {}
        lines = "; ".join(
            f"{item['title']}: {item['line']}"
            for item in ex.get("items", []) if item["line"] and (item["over"] or item["under"])
        )
        rows.append(
            [row["date"], bool(row["checkins"])]
            + [row["answers"].get(q) for q in questions]
            + [row["load"], row["program"], ex.get("assigned"), ex.get("done"), ex.get("skipped"),
               ex.get("missed"), ex.get("pain_before"), ex.get("pain_after"), ex.get("effort"),
               ex.get("effort_target"), ex.get("minutes"), ex.get("load_done"), ex.get("over"),
               ex.get("clips"), lines]
        )
    # the unit loads are prescribed in is part of the file's name, not a column
    return _csv(f"{patient.id}-reported-{unit}.csv", header, rows)


def _series_csv(db: Session, patient: Patient, metrics: list[M], days: int) -> Response:
    built = series.chart_series(db, patient, metrics, days, date.today())
    header = ["date", "day", "metric", "value", "unit", "z", "ewma_z", "expected", "source",
              "baseline_mean", "baseline_sd"]
    rows = []
    for entry in built["series"]:
        baseline = entry["baseline"] or {}
        for point in entry["points"]:
            rows.append([point["date"], point["day"], entry["metric"], point["value"],
                         entry["unit"], point["z"], point["ewma_z"], point["expected"],
                         point["source"], baseline.get("mean"), baseline.get("sd")])
    return _csv(f"{patient.id}-daily-series.csv", header, rows)


@router.get("/patients/{patient_id}/data/export")
def export_data(
    patient_id: str,
    kind: str = Query(default="observations", pattern="^(observations|reported|series)$"),
    metric_type: str | None = None,
    family: str | None = None,
    source: str | None = None,
    granularity: str | None = None,
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    metric: str | None = None,
    days: int = Query(default=90, ge=1, le=MAX_DAYS),
    scope: ConsoleScope = Depends(console_scope),
    db: Session = Depends(get_db),
) -> Response:
    """One chart's data as a CSV file: its raw readings (the browse filters
    apply), its reported grid, or the daily series of the metrics named."""
    patient = require_patient(db, scope, patient_id)
    if kind == "observations":
        f = _reading_filter(metric_type, family, source, granularity, start, end)
        return _observations_csv(db, patient, f)
    if kind == "reported":
        return _reported_csv(db, patient, min(days, 120))
    if not metric:
        raise _bad("Name the metrics to export: metric=a,b")
    return _series_csv(db, patient, _metric_list(metric), days)
