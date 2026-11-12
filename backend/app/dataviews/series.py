"""One chart's daily series, read the way the engine reads them, and the
nights behind its sleep numbers.

``chart_series`` rebuilds in memory exactly what ``run_patient`` builds on
its way to a tier: the daily value per metric (one source per day under the
precedence rule, means or totals as ``engine/dataload`` decides), the
person's own baseline (the established pre-op norm when one is held, else
the one this series gives), each day's standardized deviation against that
baseline or the expected recovery curve, and the control-chart verdict. The
stress index is derived from the same series on the spot, as the engine
derives it; it is never a stored reading. Nothing is written: no
assessment, no established baseline.

``sleep`` lists the nights: duration, stage hours, bed and wake times where
the source sent them, and what the stored assessment makes of them.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from math import sqrt
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dataviews import iso, window_start
from app.dataviews.readings import patient_header
from app.engine import baseline_store
from app.engine.data_catalog import catalog
from app.engine.dataload import load_daily_series, source_rank
from app.engine.deviation import (
    CURVE_SCALED,
    EWMA_L,
    EWMA_LAMBDA,
    RECENCY_WINDOW_DAYS,
    analyze_metric,
    expected_functional,
    standardized_deviations,
)
from app.engine.metrics_cards import SLOW_RECENCY_DAYS
from app.engine.mobility import stress_index_series
from app.engine.pipeline import ANALYZED_METRICS, DISPLAY_METRICS, latest_assessment
from app.engine.types import Baseline, DeviationResult
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider
from app.models.observation import Observation
from app.models.patient import Patient
from app.personal.metrics import _circular_sd_minutes, _mean_clock

# The EWMA control limit in sigmas of the standardized series: a day's
# smoothed z outside it, twice running in the adverse direction, is a flag
# (engine/deviation.ewma_cusum).
CONTROL_LIMIT = EWMA_L * sqrt(EWMA_LAMBDA / (2 - EWMA_LAMBDA))
MAX_METRICS = 12
STAGES = ("deep", "rem", "light", "awake")


def _winning_sources(
    db: Session, patient_id: str, metrics: list[str]
) -> dict[tuple[str, date], str]:
    """The source whose readings are a metric's value on each day: the
    best-ranked one that reported it (two of equal rank share the day and
    are joined with a plus)."""
    rows = db.execute(
        select(Observation.metric_type, Observation.local_date, Observation.source_provider)
        .where(
            Observation.patient_id == patient_id,
            Observation.deleted_at.is_(None),
            Observation.value_num.is_not(None),
            Observation.metric_type.in_(metrics),
        )
        .distinct()
    ).all()
    present: dict[tuple[str, date], set[str]] = {}
    for metric_type, day, provider in rows:
        present.setdefault((str(metric_type), day), set()).add(str(provider))
    winners: dict[tuple[str, date], str] = {}
    for key, providers in present.items():
        best = min(source_rank(p) for p in providers)
        winners[key] = "+".join(sorted(p for p in providers if source_rank(p) == best))
    return winners


class ChartSeries:
    """Everything the series views share for one chart: the daily series,
    the held baselines and today's place on the day axis."""

    def __init__(self, db: Session, patient: Patient, today: date):
        self.db = db
        self.patient = patient
        self.today = today
        self.postop_day = (today - patient.surgery_date).days
        self.series = load_daily_series(db, patient.id, patient.surgery_date)
        stress = stress_index_series(self.series)
        if stress is not None:
            self.series[str(M.STRESS_INDEX)] = stress
        self.established = baseline_store.load_established(db, patient.id)

    def judge(self, metric: M) -> tuple[Baseline, DeviationResult, bool] | None:
        """(baseline, deviation, the baseline is the established pre-op one)
        for a metric the engine judges, or None: a metric it only stores, or
        one with too few days to anchor a reference."""
        s = self.series.get(str(metric))
        if s is None or (metric not in ANALYZED_METRICS and metric not in DISPLAY_METRICS):
            return None
        held = self.established.get(str(metric)) if metric in ANALYZED_METRICS else None
        if held is not None and not (s.index < 0).any():
            # The pre-op history behind it is gone; the engine drops such a
            # reference on its next run and so does this read.
            held = None
        result = analyze_metric(metric, s, self.patient.procedure_type, baseline=held)
        if result is None:
            return None
        baseline, deviation = result
        return baseline, deviation, held is not None

    def day_of(self, day: int) -> date:
        return self.patient.surgery_date + timedelta(days=int(day))


def _baseline_view(baseline: Baseline, established: bool) -> dict[str, Any]:
    return {
        "mean": baseline.mean,
        "sd": baseline.sd,
        "n_days": baseline.n_days,
        "window": baseline.window,
        "is_preop": baseline.is_preop,
        "provisional": baseline.provisional,
        # Held since it was first established, so later data cannot move it.
        "established": established,
    }


def _one(chart: ChartSeries, metric: M, since: date, winners: dict[tuple[str, date], str],
         entry: dict[str, Any]) -> dict[str, Any]:
    key = str(metric)
    s = chart.series.get(key)
    judged = chart.judge(metric)
    out: dict[str, Any] = {
        "metric": key,
        "label": entry["label"],
        "unit": entry["unit"],
        "family": entry["family"],
        "tier": entry["tier"],
        "aggregation": entry["aggregation"],
        "adverse": entry["adverse"],
        "computed": entry["computed"],
        "judged": judged is not None,
        "reference": None,
        "baseline": None,
        "control_limit": None,
        "flagged": None,
        "drifting": None,
        "stale": None,
        "direction": None,
        "latest_z": None,
        "last_day": None,
        "points": [],
    }
    if s is None:
        return out

    z: pd.Series = pd.Series(dtype=float)
    ewma: dict[int, float] = {}
    baseline: Baseline | None = None
    if judged is not None:
        baseline, deviation, established = judged
        z = standardized_deviations(metric, s, baseline, chart.patient.procedure_type)
        smoothed = 0.0
        for day, value in z.items():
            smoothed = EWMA_LAMBDA * float(value) + (1 - EWMA_LAMBDA) * smoothed
            ewma[int(day)] = smoothed
        recency = SLOW_RECENCY_DAYS.get(metric, RECENCY_WINDOW_DAYS)
        out.update({
            "reference": deviation.reference,
            "baseline": _baseline_view(baseline, established),
            "control_limit": round(CONTROL_LIMIT, 3),
            "flagged": deviation.flagged,
            "drifting": deviation.drifting,
            "stale": (deviation.last_day is None
                      or chart.postop_day - deviation.last_day > recency),
            "direction": deviation.direction,
            "latest_z": deviation.latest_z,
            "last_day": deviation.last_day,
        })

    curve = baseline is not None and metric in CURVE_SCALED
    for day, value in s.sort_index().items():
        day = int(day)
        on = chart.day_of(day)
        if on < since or on > chart.today or pd.isna(value):
            continue
        expected = (expected_functional(baseline, chart.patient.procedure_type, day)
                    if curve and day >= 0 else None)
        out["points"].append({
            "date": on.isoformat(),
            "day": day,
            "value": round(float(value), 3),
            "z": round(float(z.loc[day]), 2) if day in z.index else None,
            "ewma_z": round(ewma[day], 2) if day in ewma else None,
            "expected": round(expected, 3) if expected is not None else None,
            "source": (str(SourceProvider.MEDPULL) if entry["computed"]
                       else winners.get((key, on))),
        })
    return out


def chart_series(
    db: Session, patient: Patient, metrics: list[M], days: int, today: date
) -> dict[str, Any]:
    chart = ChartSeries(db, patient, today)
    since = window_start(today, days)
    winners = _winning_sources(db, patient.id, [str(m) for m in metrics])
    entries = {entry["key"]: entry for entry in catalog()["metrics"]}
    return {
        "patient": patient_header(db, patient, today),
        "as_of": today.isoformat(),
        "days": days,
        "since": since.isoformat(),
        "series": [_one(chart, m, since, winners, entries[str(m)]) for m in metrics],
    }


# --- sleep ---------------------------------------------------------------------------


def _stamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hours(stages: dict[str, Any], name: str) -> float | None:
    value = stages.get(name)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _nights(db: Session, patient: Patient, since: date, today: date) -> list[dict[str, Any]]:
    """One row per night that has a duration or stages, from the source the
    precedence rule picks for that night. The date is the day the source
    filed the night under, which is the morning it ended."""
    rows = db.execute(
        select(Observation.metric_type, Observation.local_date, Observation.value_num,
               Observation.value_json, Observation.start_time, Observation.end_time,
               Observation.source_provider)
        .where(
            Observation.patient_id == patient.id,
            Observation.metric_type.in_([str(M.SLEEP_DURATION), str(M.SLEEP_STAGES)]),
            Observation.deleted_at.is_(None),
            Observation.local_date >= since,
            Observation.local_date <= today,
        )
        .order_by(Observation.local_date, Observation.start_time, Observation.id)
    ).all()
    by_night: dict[date, dict[str, list[Any]]] = {}
    for row in rows:
        by_night.setdefault(row.local_date, {}).setdefault(str(row.metric_type), []).append(row)

    def winning(found: list[Any]) -> list[Any]:
        if not found:
            return []
        best = min(source_rank(str(r.source_provider)) for r in found)
        return [r for r in found if source_rank(str(r.source_provider)) == best]

    nights = []
    for night in sorted(by_night, reverse=True):
        found = by_night[night]
        durations = winning([r for r in found.get(str(M.SLEEP_DURATION), [])
                             if r.value_num is not None])
        staged = winning(found.get(str(M.SLEEP_STAGES), []))
        # The newest stage row of the night: a restated summary replaces the
        # one before it.
        stage_row = staged[-1] if staged else None
        detail = stage_row.value_json if stage_row is not None and isinstance(stage_row.value_json, dict) else {}
        duration = (_mean([float(r.value_num) for r in durations]) if durations
                    else round(float(stage_row.value_num), 2)
                    if stage_row is not None and stage_row.value_num is not None else None)
        stages = {name: _hours(detail, name) for name in STAGES}

        bedtime, wake = _stamp(detail.get("bedtime_start")), _stamp(detail.get("bedtime_stop"))
        if bedtime is None and stage_row is not None \
                and stage_row.end_time - stage_row.start_time < timedelta(hours=20):
            # A session row is timed on the night itself; a daily summary
            # spans the calendar day and says nothing about bedtime.
            bedtime, wake = stage_row.start_time, stage_row.end_time
        efficiency = detail.get("efficiency")
        if isinstance(efficiency, (int, float)) and not isinstance(efficiency, bool):
            efficiency = float(efficiency) / 100.0 if efficiency > 1 else float(efficiency)
        elif duration and stages["awake"] is not None:
            # No figure from the source: time asleep over the time recorded.
            efficiency = (duration - stages["awake"]) / duration
        else:
            efficiency = None
        source_row = stage_row if stage_row is not None else (durations[0] if durations else None)
        nights.append({
            "date": night.isoformat(),
            "day": (night - patient.surgery_date).days,
            "duration_h": duration,
            "stages": stages if any(v is not None for v in stages.values()) else None,
            "bedtime": iso(bedtime),
            "wake": iso(wake),
            "efficiency": round(efficiency, 3) if efficiency is not None else None,
            "source": str(source_row.source_provider) if source_row is not None else None,
        })
    return nights


def _averages(nights: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [n["duration_h"] for n in nights if n["duration_h"] is not None]
    staged = [n for n in nights if n["stages"] is not None]
    out: dict[str, Any] = {
        "nights": len(durations),
        "duration_h": _mean(durations),
        "efficiency": _mean([n["efficiency"] for n in nights if n["efficiency"] is not None]),
        "nights_with_stages": len(staged),
    }
    for name in STAGES:
        hours = [n["stages"][name] for n in staged if n["stages"][name] is not None]
        out[f"{name}_h"] = _mean(hours)
        shares = [n["stages"][name] / n["duration_h"] * 100 for n in staged
                  if n["stages"][name] is not None and n["duration_h"]]
        out[f"{name}_pct"] = round(sum(shares) / len(shares), 1) if shares else None
    return out


def _consistency(nights: list[dict[str, Any]]) -> dict[str, Any]:
    """How regular bed and wake times are: the circular standard deviation
    of each in minutes (23:30 and 00:30 are an hour apart), with the mean
    clock time. Needs three nights with stamps; the same definition the
    Personal sleep panel uses."""
    bedtimes = [datetime.fromisoformat(n["bedtime"]) for n in nights if n["bedtime"]]
    wakes = [datetime.fromisoformat(n["wake"]) for n in nights if n["wake"]]
    bed_sd, wake_sd = _circular_sd_minutes(bedtimes), _circular_sd_minutes(wakes)
    return {
        "nights": len(bedtimes),
        "bedtime_sd_min": round(bed_sd, 1) if bed_sd is not None else None,
        "wake_sd_min": round(wake_sd, 1) if wake_sd is not None else None,
        "mean_bedtime": _mean_clock(bedtimes),
        "mean_wake": _mean_clock(wakes),
    }


def _derived(db: Session, patient: Patient) -> dict[str, Any]:
    """What the stored assessment makes of the nights: the nocturnal
    disruption care metric (M9) and the sleep-duration signal card."""
    row = latest_assessment(db, patient.id)
    if row is None:
        return {"computed_at": None, "nocturnal_disruption": None, "sleep_duration": None}
    analytics = row.analytics or {}
    care = (analytics.get("care_metrics") or {}).get("metrics") or []
    cards = analytics.get("metrics") or []
    return {
        "computed_at": iso(row.computed_at),
        "nocturnal_disruption": next((m for m in care if m.get("id") == "M9"), None),
        "sleep_duration": next(
            (c for c in cards if c.get("metric_key") == str(M.SLEEP_DURATION)), None
        ),
    }


def sleep(db: Session, patient: Patient, days: int, today: date) -> dict[str, Any]:
    since = window_start(today, days)
    nights = _nights(db, patient, since, today)
    judged = ChartSeries(db, patient, today).judge(M.SLEEP_DURATION) if nights else None
    return {
        "patient": patient_header(db, patient, today),
        "as_of": today.isoformat(),
        "days": days,
        "since": since.isoformat(),
        "nights": nights,
        "averages": _averages(nights),
        "last_7": _averages([n for n in nights
                             if date.fromisoformat(n["date"]) > today - timedelta(days=7)]),
        "consistency": _consistency(nights),
        # The person's own sleep-duration norm, as the engine holds it.
        "baseline": _baseline_view(judged[0], judged[2]) if judged is not None else None,
        "derived": _derived(db, patient),
    }
