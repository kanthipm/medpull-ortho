"""Chronic-care metrics: C1 weight trend, C2 SpO₂ burden, C3 glucose
time-in-range, C4 blood-pressure control, C5 symptom burden, C6 sedentary
burden. C1, C2 and C4 are guarded — they read as "signal consistent with …
recommend review", never as a named decompensation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.engine.care._common import (
    NO_RECENT_TEXT,
    build,
    confidence_for,
    last_n_days,
    nodata,
    points,
    stale,
)
from app.engine.care.stats import ols
from app.engine.care.types import CareContext, CareMetric, ChartSpec, tail
from app.engine.curves import curve_mid
from app.models.enums import Granularity, MetricStatus
from app.models.enums import MetricType as M


def c1(ctx: CareContext) -> CareMetric:
    weight = ctx.series.get(str(M.BODY_WEIGHT))
    if weight is None:
        return nodata("C1", ctx)
    weight = weight.astype(float)
    latest_day = int(weight.index.max())
    if stale(latest_day, ctx.postop_day):
        return nodata("C1", ctx, NO_RECENT_TEXT,
                      finding=f"The latest weight is from {ctx.day_phrase(latest_day)}.")
    latest = float(weight.iloc[-1])
    history = weight[(weight.index >= latest_day - 14) & (weight.index < latest_day)]
    coverage = f"{len(history)} of 14 prior days weighed"
    if len(history) < 3:
        return nodata("C1", ctx, "Building baseline", coverage_text=coverage)
    baseline = float(history.median())
    gain7 = latest - baseline
    previous = weight.get(latest_day - 1)
    gain24 = (latest - float(previous)) if previous is not None else None
    if (gain24 is not None and gain24 >= 1.0) or gain7 >= 2.0:
        status, text = MetricStatus.FLAG, "Rapid weight gain — review"
    elif (gain24 is not None and gain24 >= 0.5) or gain7 >= 1.0:
        status, text = MetricStatus.WATCH, "Weight drifting up"
    else:
        status, text = MetricStatus.OK, "Weight stable"
    finding = f"Weight {latest:.1f} kg, {gain7:+.1f} kg vs the 14-day median of {baseline:.1f} kg"
    if gain24 is not None:
        finding += f" ({gain24:+.1f} kg in 24 h)"
    finding += "."
    if status is MetricStatus.FLAG:
        finding += " A signal consistent with fluid retention — recommend review."
    elif status is MetricStatus.WATCH:
        finding += " Drifting up against the patient's own baseline — worth a look."
    delta = f"{gain7:+.1f} kg / 7d" + (f" · {gain24:+.1f} kg / 24h" if gain24 is not None else "")
    chart = ChartSpec(kind="line", series=tail(points(last_n_days(weight, ctx.postop_day, 28))),
                      reference=round(baseline, 1), y_label="kg")
    return build(
        "C1", ctx, status=status, status_text=text, finding=finding,
        value=f"{latest:.1f}", value_num=latest, unit="kg", value_label="latest weight",
        delta_text=delta, chart=chart, confidence=confidence_for(ctx, len(history), 14),
        coverage_text=coverage,
        next_step="Ask about swelling, breathlessness lying flat and salt/fluid intake today."
        if status is MetricStatus.FLAG else None,
    )


def c2(ctx: CareContext) -> CareMetric:
    spo2 = ctx.series.get(str(M.SPO2))
    if spo2 is None:
        return nodata("C2", ctx)
    post = spo2[spo2.index >= 0].astype(float)
    latest_day = int(post.index.max()) if len(post) else None
    if stale(latest_day, ctx.postop_day):
        return nodata("C2", ctx, NO_RECENT_TEXT,
                      finding=f"The latest SpO₂ is from {ctx.day_phrase(latest_day)}.")
    last7 = last_n_days(post, ctx.postop_day, 7)
    coverage = f"{len(last7)} of 7 days of SpO₂"
    if len(last7) < 2:
        return nodata("C2", ctx, "Building baseline", coverage_text=coverage)
    n_low = int((last7 < 90).sum())
    n_92 = int((last7 < 92).sum())
    dev = ctx.deviations.get(str(M.SPO2))
    current = dev is not None and not stale(dev.last_day, ctx.postop_day)
    base = ctx.baselines.get(str(M.SPO2))
    if n_low >= 2 or (current and dev.flagged):
        status, text = MetricStatus.FLAG, "Desaturation burden — review"
    elif n_92 >= 1 or (current and dev.drifting):
        status, text = MetricStatus.WATCH, "SpO₂ drifting low"
    else:
        status, text = MetricStatus.OK, "Oxygenation within baseline"
    mean7 = float(last7.mean())
    finding = (f"Mean SpO₂ {mean7:.1f}% over the last {len(last7)} days; {n_low} day"
               f"{'s' if n_low != 1 else ''} under 90% and {n_92} under 92%")
    if base is not None:
        finding += f" (baseline {base.mean:.1f}%)"
    finding += "."
    if status is MetricStatus.FLAG:
        finding += " Signals deviating from baseline — recommend review."
    chart = ChartSpec(kind="line", series=tail(points(last_n_days(post, ctx.postop_day, 28), digits=1)),
                      reference=round(base.mean, 1) if base else 90.0, y_label="%")
    return build(
        "C2", ctx, status=status, status_text=text, finding=finding,
        value=f"{mean7:.1f}", value_num=mean7, unit="%", value_label="7-day mean SpO₂",
        delta_text=f"{n_low} of {len(last7)} days < 90%"
                   + (f" · baseline {base.mean:.1f}%" if base else ""),
        chart=chart, confidence=confidence_for(ctx, len(last7), 7), coverage_text=coverage,
        next_step="Ask about breathing comfort and cough; verify device fit; consider a same-day "
                  "call." if status is MetricStatus.FLAG else None,
    )


def c3(ctx: CareContext) -> CareMetric:
    frame = ctx.glucose
    if frame.empty:
        return nodata("C3", ctx)
    latest_day = int(frame["day"].max())
    if stale(latest_day, ctx.postop_day):
        return nodata("C3", ctx, NO_RECENT_TEXT,
                      finding=f"The latest glucose reading is from {ctx.day_phrase(latest_day)}.")
    readings = frame[(frame["granularity"] != str(Granularity.DAILY_SUMMARY)) & frame["value"].notna()]
    summaries = frame[frame["granularity"] == str(Granularity.DAILY_SUMMARY)]
    if len(readings) >= 10:
        values = readings["value"].to_numpy(dtype=float)
        tir = float(np.mean((values >= 70) & (values <= 180)) * 100)
        hypo = int((values < 70).sum())
        mean_g = float(values.mean())
        daily = readings.groupby("day")["value"].mean()
        coverage = f"{len(values)} readings over {readings['day'].nunique()} days"
    else:
        tirs, means, hypos = [], [], 0
        for row in summaries.itertuples():
            detail = row.json or {}
            if isinstance(detail.get("tir_pct"), (int, float)):
                tirs.append(float(detail["tir_pct"]))
            mean_value = detail.get("mean") if isinstance(detail.get("mean"), (int, float)) else row.value
            if mean_value == mean_value and mean_value is not None:
                means.append(float(mean_value))
            hypos += int(detail.get("hypo_count") or 0)
        if not tirs:
            return nodata("C3", ctx, "Building baseline",
                          coverage_text=f"{len(readings)} readings; 10 needed")
        tir, hypo = float(np.mean(tirs)), hypos
        mean_g = float(np.mean(means)) if means else float("nan")
        daily = summaries.groupby("day")["value"].mean()
        coverage = f"{len(tirs)} daily summaries"
    if tir < 50:
        status, text = MetricStatus.FLAG, "Time-in-range low — review"
    elif tir < 70:
        status, text = MetricStatus.WATCH, "Time-in-range below target"
    else:
        status, text = MetricStatus.OK, "Time-in-range on target"
    mean_text = f"{mean_g:.0f}" if mean_g == mean_g else "n/a"
    finding = (f"{tir:.0f}% of readings between 70 and 180 mg/dL over the last 14 days; mean "
               f"{mean_text} mg/dL; {hypo} reading{'s' if hypo != 1 else ''} under 70.")
    if status is MetricStatus.FLAG:
        finding += " Glycemic control is well below target — recommend review."
    chart = ChartSpec(kind="line", series=tail(points(daily, digits=0)), reference=180.0,
                      y_label="mg/dL", band=[{"x": int(d), "lo": 70, "hi": 180} for d in daily.index][-60:])
    return build(
        "C3", ctx, status=status, status_text=text, finding=finding,
        value=f"{tir:.0f}", value_num=tir, unit="%", value_label="time in range",
        delta_text=f"mean {mean_text} mg/dL · {hypo} readings < 70", chart=chart,
        drivers=[{"label": "Readings < 70 mg/dL", "count": hypo}],
        confidence=confidence_for(ctx, int(frame["day"].nunique()), 10), coverage_text=coverage,
        next_step="Review medication timing and meals; ask about symptoms of lows."
        if status is not MetricStatus.OK else None,
    )


def c4(ctx: CareContext) -> CareMetric:
    sys = ctx.series.get(str(M.BLOOD_PRESSURE_SYSTOLIC))
    dia = ctx.series.get(str(M.BLOOD_PRESSURE_DIASTOLIC))
    if sys is None:
        return nodata("C4", ctx)
    sys = sys.astype(float)
    latest_day = int(sys.index.max())
    if stale(latest_day, ctx.postop_day):
        return nodata("C4", ctx, NO_RECENT_TEXT,
                      finding=f"The latest blood pressure is from {ctx.day_phrase(latest_day)}.")
    window = last_n_days(sys, ctx.postop_day, 7)
    if len(window) < 2:
        window = last_n_days(sys, ctx.postop_day, 14)
    coverage = f"{len(window)} readings in {7 if len(last_n_days(sys, ctx.postop_day, 7)) >= 2 else 14} days"
    if len(window) < 2:
        return nodata("C4", ctx, "Building baseline", coverage_text=coverage)
    dia_by_day = {int(d): float(v) for d, v in dia.items()} if dia is not None else {}
    above = 0
    for day, value in window.items():
        d_value = dia_by_day.get(int(day))
        if value >= 140 or (d_value is not None and d_value >= 90):
            above += 1
    pct = above / len(window)
    mean_sys = float(window.mean())
    dia_values = [dia_by_day[int(d)] for d in window.index if int(d) in dia_by_day]
    mean_dia = float(np.mean(dia_values)) if dia_values else float("nan")
    if pct >= 0.5 or mean_sys >= 150:
        status, text = MetricStatus.FLAG, "Above target — for review"
    elif pct >= 0.25:
        status, text = MetricStatus.WATCH, "Readings drifting above target"
    else:
        status, text = MetricStatus.OK, "Within target"
    dia_text = f"{mean_dia:.0f}" if mean_dia == mean_dia else "–"
    finding = (f"Mean {mean_sys:.0f}/{dia_text} mmHg over {len(window)} readings; "
               f"{pct * 100:.0f}% at or above 140/90.")
    if status is MetricStatus.FLAG:
        finding += " Above target — for review."
    elif status is MetricStatus.WATCH:
        finding += " A quarter or more of readings sit above target."
    series = [{"x": int(d), "y": round(float(v), 0), "y2": dia_by_day.get(int(d))}
              for d, v in last_n_days(sys, ctx.postop_day, 28).items()]
    chart = ChartSpec(kind="dual", series=tail(series), reference=140.0, y_label="systolic",
                      y2_label="diastolic")
    return build(
        "C4", ctx, status=status, status_text=text, finding=finding,
        value=f"{mean_sys:.0f}/{dia_text}", value_num=mean_sys, unit="mmHg",
        value_label="mean blood pressure", delta_text=f"{pct * 100:.0f}% of readings ≥ 140/90",
        chart=chart, confidence=confidence_for(ctx, len(window), 4), coverage_text=coverage,
        next_step="Confirm cuff technique and medication adherence; review the log at the next "
                  "visit." if status is not MetricStatus.OK else None,
    )


def c5(ctx: CareContext) -> CareMetric:
    days = list(range(ctx.postop_day - 13, ctx.postop_day + 1))
    pain = {int(r.day): float(r.mean) for r in ctx.pain.itertuples() if r.mean == r.mean}
    breath = {int(r.day): float(r.mean) for r in ctx.symptom("breathlessness").itertuples()
              if r.mean == r.mean}
    fatigue = {int(r.day): float(r.mean) for r in ctx.symptom("fatigue").itertuples()
               if r.mean == r.mean}
    flags: dict[int, int] = {}
    for checkin in ctx.checkins:
        day = (checkin["occurred_at"].date() - ctx.surgery_date).days
        flags[day] = flags.get(day, 0) + int(checkin.get("flags", 0))
    scores = {}
    components = {"pain": [], "breathlessness": [], "fatigue": [], "symptom flags": []}
    for day in days:
        parts = []
        if day in pain:
            parts.append(pain[day])
            components["pain"].append(pain[day])
        if day in breath:
            parts.append(breath[day] * 2.5)
            components["breathlessness"].append(breath[day] * 2.5)
        if day in fatigue:
            parts.append(fatigue[day])
            components["fatigue"].append(fatigue[day])
        if day in flags and (parts or flags[day] > 0):
            parts.append(min(10.0, flags[day] * 2.0))
            components["symptom flags"].append(min(10.0, flags[day] * 2.0))
        if parts:
            scores[day] = float(np.mean(parts))
    series = pd.Series(scores, dtype=float).sort_index()
    coverage = f"{len(series)} of 14 days with a symptom log"
    if len(series) < 3:
        return nodata("C5", ctx, "Building baseline" if len(series) else "No data yet",
                      coverage_text=coverage)
    if stale(int(series.index.max()), ctx.postop_day):
        return nodata("C5", ctx, NO_RECENT_TEXT, coverage_text=coverage,
                      finding=f"The latest symptom log is from {ctx.day_phrase(int(series.index.max()))}.")
    level = float(last_n_days(series, ctx.postop_day, 7).mean())
    first_week = series[series.index <= ctx.postop_day - 7]
    first = float(first_week.mean()) if len(first_week) >= 2 else None
    slope_week = ols(series.index.to_numpy(dtype=float), series.to_numpy(dtype=float))[0] * 7
    if slope_week >= 2.0:
        status, text = MetricStatus.FLAG, "Symptom burden rising"
    elif level >= 7.0:
        status, text = MetricStatus.FLAG, "High symptom burden"
    elif slope_week >= 0.5:
        status, text = MetricStatus.WATCH, "Symptom burden rising"
    elif slope_week <= -0.5:
        status, text = MetricStatus.OK, "Symptom burden easing"
    else:
        status, text = MetricStatus.OK, "Symptom burden steady"
    finding = (f"Daily symptom score averages {level:.1f}/10 this week, changing "
               f"{slope_week:+.1f} points per week")
    if first is not None:
        finding += f" (first week of the window {first:.1f})"
    finding += "."
    if status is MetricStatus.FLAG:
        finding += (" Symptoms are climbing week on week." if slope_week >= 2.0
                    else " Symptom burden is high — check pain control and what is driving it.")
    drivers = [{"label": name, "mean": round(float(np.mean(values)), 1), "days": len(values)}
               for name, values in components.items() if values]
    fit_line = None
    if len(series) >= 3:
        slope, intercept, *_ = ols(series.index.to_numpy(dtype=float), series.to_numpy(dtype=float))
        fit_line = [{"x": int(d), "y": round(intercept + slope * d, 2)}
                    for d in (series.index.min(), series.index.max())]
    chart = ChartSpec(kind="line", series=tail(points(series, digits=1)), fit=fit_line, y_label="/10")
    return build(
        "C5", ctx, status=status, status_text=text, finding=finding,
        value=f"{level:.1f}", value_num=level, unit="/10", value_label="symptom score this week",
        delta_text=f"{slope_week:+.1f} pts/week" + (f" · first week {first:.1f}" if first is not None
                                                     else ""),
        chart=chart, drivers=drivers, confidence=confidence_for(ctx, len(series), 14),
        coverage_text=coverage,
        next_step="Review analgesia and what the patient says is driving the score; consider a "
                  "call." if status is MetricStatus.FLAG else None,
    )


def c6(ctx: CareContext) -> CareMetric:
    intraday = ctx.intraday.get(str(M.STEPS))
    steps = ctx.series.get(str(M.STEPS))
    if intraday is not None and not intraday.empty:
        recent = intraday[intraday["day"] > ctx.postop_day - 7]
        matrix = recent.pivot_table(index="day", columns="hour", values="value", aggfunc="sum")
        matrix = matrix.reindex(columns=range(24))
        complete = matrix[matrix.notna().sum(axis=1) >= 12]
        if len(complete) >= 3 and not stale(int(complete.index.max()), ctx.postop_day):
            per_day, gaps = [], []
            for _, row in complete.iterrows():
                waking = row.loc[7:21].fillna(0.0)
                sedentary = waking < 50
                per_day.append(int(sedentary.sum()))
                longest = run = 0
                for flag in sedentary:
                    run = run + 1 if flag else 0
                    longest = max(longest, run)
                gaps.append(longest)
            mean_sed = float(np.mean(per_day))
            gap = int(max(gaps))
            if mean_sed >= 12:
                status, text = MetricStatus.FLAG, "Sedentary most of the day"
            elif mean_sed >= 10:
                status, text = MetricStatus.WATCH, "Long sedentary hours"
            else:
                status, text = MetricStatus.OK, "Moving through the day"
            finding = (f"{mean_sed:.1f} of the 15 waking hours (07–22) carried under 50 steps on "
                       f"average over the last {len(complete)} days; longest sedentary stretch "
                       f"{gap} h.")
            if status is MetricStatus.FLAG:
                finding += " Most of the day is spent still."
            chart = ChartSpec(kind="bars",
                              series=[{"x": int(d), "y": v} for d, v in zip(complete.index, per_day)],
                              y_label="sedentary h")
            return build(
                "C6", ctx, status=status, status_text=text, finding=finding,
                value=f"{mean_sed:.1f}", value_num=mean_sed, unit="sedentary h/day",
                value_label="waking hours under 50 steps", delta_text=f"longest gap {gap} h",
                chart=chart, confidence=confidence_for(ctx, len(complete), 7),
                coverage_text=f"{len(complete)} of 7 days with hourly steps",
                next_step="Set an hourly move prompt; two-minute walks break up the long stretches."
                if status is not MetricStatus.OK else None,
                method="Waking hours (07–22) with under 50 steps per day from hourly buckets, "
                       "last 7 days.",
            )
    if steps is None:
        return nodata("C6", ctx)
    post = steps[steps.index >= 0].astype(float)
    latest_day = int(post.index.max()) if len(post) else None
    if stale(latest_day, ctx.postop_day):
        return nodata("C6", ctx, NO_RECENT_TEXT,
                      finding=f"The latest step count is from {ctx.day_phrase(latest_day)}.")
    last7 = last_n_days(post, ctx.postop_day, 7)
    coverage = f"{len(last7)} of 7 days of steps"
    if len(last7) < 3:
        return nodata("C6", ctx, "Building baseline", coverage_text=coverage)
    # On an ortho pathway the early post-op weeks are expected to be quiet, so
    # the 1,500-step floor is scaled to the recovery curve; a chronic program
    # holds the flat threshold.
    threshold = 1500.0
    if ctx.uses_expected_curve:
        threshold *= max(0.3, float(curve_mid(ctx.procedure, float(ctx.postop_day))))
    inactive = int((last7 < threshold).sum())
    if inactive >= 5:
        status, text = MetricStatus.FLAG, "Mostly inactive days"
    elif inactive >= 3:
        status, text = MetricStatus.WATCH, "Several inactive days"
    else:
        status, text = MetricStatus.OK, "Active most days"
    finding = (f"{inactive} of the last {len(last7)} days fell under {threshold:,.0f} steps"
               + (f" (1,500 scaled to {ctx.day_phrase()} on the recovery curve)"
                  if ctx.uses_expected_curve and threshold < 1500 else "") + ".")
    if status is MetricStatus.FLAG:
        finding += " Most days are inactive — ask what is keeping the patient sitting."
    chart = ChartSpec(kind="bars", series=tail(points(last_n_days(post, ctx.postop_day, 14), digits=0)),
                      reference=round(threshold, 0), y_label="steps")
    return build(
        "C6", ctx, status=status, status_text=text, finding=finding,
        value=f"{inactive}", value_num=inactive, unit="inactive days / 7",
        value_label="days under the activity floor", delta_text=f"floor {threshold:,.0f} steps",
        chart=chart, confidence=confidence_for(ctx, len(last7), 7), coverage_text=coverage,
        next_step="Ask what is limiting activity — pain, fatigue, fear of movement."
        if status is not MetricStatus.OK else None,
    )
