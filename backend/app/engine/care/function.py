"""Functional capacity: M4 walking economy, M5 endurance fade, M6
sit-to-stand, M7 cadence/pace recovery, M8 stairs.

Can the patient do more, and does it cost them less? M4/M5 need per-minute
walk detail (an in-app guided walk or Junction samples), so for most devices
they honestly report what would unlock them rather than a guess.
"""

from __future__ import annotations

from typing import Any

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
from app.engine.care.pathways import LOWER_LIMB
from app.engine.care.stats import ols
from app.engine.care.types import CareContext, CareMetric, ChartSpec, tail
from app.engine.deviation import expected_functional
from app.models.enums import MetricStatus
from app.models.enums import MetricType as M

WALK_KINDS = {"walk", "guided_walk", "walking", "outdoor_walk", "indoor_walk", "hiking"}


def _walks(ctx: CareContext, days: int = 28) -> list[dict[str, Any]]:
    return [
        s for s in ctx.sessions
        if (s["kind"] in WALK_KINDS or "walk" in s["kind"])
        and s["day"] > ctx.postop_day - days
    ]


def m4(ctx: CareContext) -> CareMetric:
    walks = [s for s in _walks(ctx) if s.get("hr_bpm") and (s.get("cadence_spm") or s.get("speed_mps"))]
    coverage = f"{len(walks)} walks with heart rate in 28 days"
    if len(walks) < 3:
        return nodata("M4", ctx, "Needs 3 walks" if walks else "No data yet",
                      coverage_text=coverage)
    base = ctx.baselines.get(str(M.RESTING_HR))
    unit = "bpm / spm"
    costs: list[tuple[int, float]] = []
    for s in walks:
        hr = np.asarray(s["hr_bpm"], dtype=float)
        rhr = base.mean if base is not None else float(hr.min()) - 5.0
        reserve = float(np.mean(hr - rhr))
        if s.get("cadence_spm"):
            output = float(np.mean(s["cadence_spm"]))
        else:
            output = float(np.mean(s["speed_mps"])) * 10.0  # per 0.1 m/s
            unit = "bpm / 0.1 m/s"
        if output > 0:
            costs.append((int(s["day"]), reserve / output))
    if len(costs) < 3:
        return nodata("M4", ctx, "Needs 3 walks", coverage_text=coverage)
    values = [c for _, c in costs]
    latest = values[-1]
    first3 = float(np.mean(values[:3]))
    last3 = float(np.mean(values[-3:]))
    ratio = last3 / first3 if first3 > 0 else 1.0
    slope = ols([d for d, _ in costs], values)[0]
    if ratio >= 1.3:
        status, text = MetricStatus.FLAG, "Effort cost rising"
    elif ratio >= 1.15:
        status, text = MetricStatus.WATCH, "Effort cost up"
    elif ratio <= 0.9:
        status, text = MetricStatus.OK, "Effort cost falling"
    else:
        status, text = MetricStatus.OK, "Effort cost stable"
    finding = (
        f"Heart-rate reserve per unit of walking output is {latest:.2f} {unit} on the latest "
        f"walk; the last three walks average {last3:.2f} against {first3:.2f} for the first "
        f"three ({(ratio - 1) * 100:+.0f}%, trend {slope:+.3f}/day)."
    )
    if status is MetricStatus.FLAG:
        finding += " A rising effort cost is an early sign of deconditioning or guarding."
    elif ratio <= 0.9:
        finding += " Walking is getting cheaper — deconditioning reversing, less guarding."
    chart = ChartSpec(kind="line", series=tail([{"x": d, "y": round(c, 3)} for d, c in costs]),
                      y_label=unit)
    return build(
        "M4", ctx, status=status, status_text=text, finding=finding,
        value=f"{latest:.2f}", value_num=latest, unit=unit, value_label="effort cost",
        delta_text=f"{(ratio - 1) * 100:+.0f}% vs first walks", chart=chart,
        next_step="Ask about breathlessness, pain guarding and sleep; review with PT."
        if status is MetricStatus.FLAG else None,
        confidence=confidence_for(ctx, len(costs), 6), coverage_text=coverage,
        method="Mean (heart rate − resting heart rate) divided by mean cadence per walk"
               + (" (resting HR from the pre-op baseline)" if base is not None
                  else " (resting HR estimated from the walk's minimum)")
               + "; last three walks vs the first three.",
    )


def _fade(cadence: list[float]) -> tuple[float, int | None]:
    cad = np.asarray(cadence, dtype=float)
    minutes = np.arange(len(cad), dtype=float)
    slope = ols(minutes, cad)[0]
    c0 = float(np.mean(cad[:2]))
    fade = (-slope / c0 * 100.0) if c0 > 0 else 0.0
    below = np.nonzero(cad < 0.9 * c0)[0]
    ttf = int(below[0]) if len(below) else None
    return fade, ttf


def m5(ctx: CareContext) -> CareMetric:
    walks = [s for s in _walks(ctx)
             if s.get("cadence_spm") and len(s["cadence_spm"]) >= 6 and s["minutes"] >= 6]
    coverage = f"{len(walks)} walks of 6+ minutes with cadence in 28 days"
    if not walks:
        return nodata("M5", ctx, coverage_text=coverage)
    recent = walks[-3:]
    fades = [_fade(s["cadence_spm"]) for s in recent]
    index = float(np.mean([f for f, _ in fades]))
    ttf = fades[-1][1]
    if index > 3:
        status, text = MetricStatus.FLAG, "Steep intra-walk fade"
    elif index > 1.5:
        status, text = MetricStatus.WATCH, "Fading within walks"
    else:
        status, text = MetricStatus.OK, "Sustaining cadence"
    latest = recent[-1]
    finding = (
        f"Cadence fades {index:.1f}% per minute within a walk (mean of the last "
        f"{len(recent)} walks); on the latest {latest['minutes']:.0f}-minute walk it "
        + (f"dropped below 90% of its opening cadence at minute {ttf}."
           if ttf is not None else "held above 90% of its opening cadence throughout.")
    )
    if status is MetricStatus.FLAG:
        finding += " The patient cannot yet sustain a bout — keep walks short and frequent."
    delta = f"time to fatigue ≈ {ttf} min" if ttf is not None else "cadence held through the walk"
    chart = ChartSpec(
        kind="line",
        series=[{"x": m, "y": round(float(c), 1)} for m, c in enumerate(latest["cadence_spm"])][:60],
        x_label="Minute", y_label="spm",
    )
    return build(
        "M5", ctx, status=status, status_text=text, finding=finding,
        value=f"{index:.1f}", value_num=index, unit="%/min", value_label="cadence fade",
        delta_text=delta, chart=chart,
        next_step="Shorten walks and add a second bout rather than pushing one longer one."
        if status is MetricStatus.FLAG else None,
        confidence=confidence_for(ctx, len(walks), 3), coverage_text=coverage,
    )


def m6(ctx: CareContext) -> CareMetric:
    series = ctx.series.get(str(M.SIT_TO_STAND))
    if series is None:
        return nodata("M6", ctx)
    post = series[series.index >= 0].astype(float)
    latest_day = int(post.index.max()) if len(post) else None
    if stale(latest_day, ctx.postop_day):
        return nodata("M6", ctx, NO_RECENT_TEXT,
                      finding=f"The latest sit-to-stand count is from {ctx.day_phrase(latest_day)}.")
    last14 = last_n_days(post, ctx.postop_day, 14)
    coverage = f"{len(last14)} of 14 days of chair-rise counts"
    if len(last14) < 3:
        return nodata("M6", ctx, "Building baseline", coverage_text=coverage)
    last7 = last14[last14.index > ctx.postop_day - 7]
    prev7 = last14[last14.index <= ctx.postop_day - 7]
    l7 = float(last7.mean()) if len(last7) else float(last14.iloc[-1])
    p7 = float(prev7.mean()) if len(prev7) >= 2 else None
    if p7 is None:
        status, text = MetricStatus.OK, "Steady"
        delta = "first week of counts"
    elif l7 >= 1.2 * p7:
        status, text, delta = MetricStatus.OK, "Chair rises up", f"prior week {p7:.0f}/day"
    elif l7 <= 0.75 * p7:
        status, text, delta = MetricStatus.WATCH, "Chair rises down", f"prior week {p7:.0f}/day"
    else:
        status, text, delta = MetricStatus.OK, "Steady", f"prior week {p7:.0f}/day"
    finding = f"About {l7:.0f} chair rises a day this week"
    if p7 is not None:
        finding += f" against {p7:.0f} the week before ({(l7 / p7 - 1) * 100:+.0f}%)"
    finding += "."
    if status is MetricStatus.WATCH:
        finding += " Fewer rises usually means more sitting — ask what changed."
    chart = ChartSpec(kind="bars", series=tail(points(last_n_days(post, ctx.postop_day, 28), digits=0)),
                      y_label="rises/day")
    return build(
        "M6", ctx, status=status, status_text=text, finding=finding,
        value=f"{l7:.0f}", value_num=l7, unit="rises/day", value_label="chair rises",
        delta_text=delta, chart=chart, confidence=confidence_for(ctx, len(last7), 7),
        coverage_text=coverage,
    )


def m7(ctx: CareContext) -> CareMetric:
    speed = ctx.series.get(str(M.WALKING_SPEED))
    step_len = ctx.series.get(str(M.STEP_LENGTH))
    if speed is None:
        return nodata("M7", ctx)
    name, unit, label, inputs = "Walking pace recovery", "m/s", "walking pace", [str(M.WALKING_SPEED)]
    series = speed.astype(float)
    cadence_mode = False
    if step_len is not None:
        aligned = pd.concat([speed, step_len], axis=1, join="inner").dropna()
        if len(aligned) >= 3:
            series = (aligned.iloc[:, 0] / aligned.iloc[:, 1] * 60.0).astype(float)
            name, unit, label, cadence_mode = "Cadence recovery curve", "spm", "cadence", True
            inputs = [str(M.WALKING_SPEED), str(M.STEP_LENGTH)]
    post = series[series.index >= 2]
    latest_day = int(post.index.max()) if len(post) else None
    if stale(latest_day, ctx.postop_day):
        return nodata("M7", ctx, NO_RECENT_TEXT, name=name,
                      finding=f"The latest {label} reading is from {ctx.day_phrase(latest_day)}.")
    if len(post) < 3:
        return nodata("M7", ctx, "Building baseline", name=name,
                      coverage_text=f"{len(post)} days of {label}")
    latest = float(post.iloc[-1])
    last3 = float(post.iloc[-3:].mean())
    prev7 = post.iloc[-10:-3]
    dev = ctx.deviations.get(str(M.WALKING_SPEED)) if not cadence_mode else None
    reference = None
    base = ctx.baselines.get(str(M.WALKING_SPEED))

    if ctx.uses_expected_curve:
        if dev is not None and not stale(dev.last_day, ctx.postop_day) and dev.flagged:
            status, text = MetricStatus.FLAG, "Below expected pace"
        elif dev is not None and not stale(dev.last_day, ctx.postop_day) and dev.drifting:
            status, text = MetricStatus.WATCH, "Drifting below expected pace"
        elif len(prev7) >= 3 and last3 < 0.92 * float(prev7.mean()):
            status, text = MetricStatus.WATCH, "Dip vs own trend"
        else:
            status, text = MetricStatus.OK, "Climbing with recovery"
        if base is not None and not cadence_mode:
            expected = expected_functional(base, ctx.procedure, ctx.postop_day)
            reference = round(expected, 2) if expected is not None else None
    else:
        window = series[series.index > ctx.postop_day - 28]
        median = float(window.median())
        reference = round(median, 2)
        if median > 0 and last3 < 0.92 * median:
            status, text = MetricStatus.WATCH, "Dip vs own baseline"
        else:
            status, text = MetricStatus.OK, "Holding own baseline"

    # `value` is the number alone; the unit travels separately so no surface
    # prints it twice. Prose (finding, delta) keeps the unit inline.
    num = (lambda v: f"{v:.0f}") if cadence_mode else (lambda v: f"{v:.2f}")
    fmt = (lambda v: f"{num(v)} spm") if cadence_mode else (lambda v: f"{num(v)} m/s")
    finding = f"Latest {label} {fmt(latest)}; 3-day mean {fmt(last3)}"
    if reference is not None:
        finding += (f" vs {'expected' if ctx.uses_expected_curve else 'own 28-day median'} "
                    f"{fmt(reference)}")
    finding += "."
    if status is MetricStatus.FLAG:
        finding += " Pace sits below what the recovery curve expects at this point."
    elif status is MetricStatus.WATCH and "Dip" in text:
        finding += " A dip against the patient's own trend, the day it starts."
    chart = ChartSpec(kind="line", series=tail(points(last_n_days(post, ctx.postop_day, 28))),
                      reference=reference, y_label=unit)
    return build(
        "M7", ctx, name=name, status=status, status_text=text, finding=finding,
        value=num(latest), value_num=latest, unit=unit, value_label=label,
        delta_text=f"3-day mean {fmt(last3)}", chart=chart, inputs=inputs,
        next_step="Review activity progression with PT." if status is not MetricStatus.OK else None,
        confidence=confidence_for(ctx, len(post.iloc[-7:]), 7),
        coverage_text=f"{len(last_n_days(post, ctx.postop_day, 7))} of 7 days of {label}",
    )


def m8(ctx: CareContext) -> CareMetric:
    flights = ctx.series.get(str(M.FLIGHTS_CLIMBED))
    if flights is None:
        return nodata("M8", ctx)
    post = flights[flights.index >= 0].astype(float)
    tempo = ctx.series.get(str(M.STAIR_SPEED_UP))
    latest_day = int(post.index.max()) if len(post) else None
    if stale(latest_day, ctx.postop_day):
        return nodata("M8", ctx, NO_RECENT_TEXT,
                      finding=f"The latest flights count is from {ctx.day_phrase(latest_day)}.")
    climbed = post[post >= 1]
    reintro = int(climbed.index.min()) if len(climbed) else None
    last7 = last_n_days(post, ctx.postop_day, 7)
    l7 = float(last7.mean()) if len(last7) else 0.0
    coverage = f"{len(last7)} of 7 days of flights"
    delta = None
    if reintro is None:
        if ctx.postop_day > 21 and ctx.procedure in LOWER_LIMB:
            status, text = MetricStatus.WATCH, "Stairs not yet resumed"
        else:
            status, text = MetricStatus.OK, "No stairs yet"
        finding = f"No flights climbed yet through {ctx.day_phrase()}."
        if status is MetricStatus.WATCH:
            finding += " Stairs usually re-enter the routine by week three — ask what is in the way."
    else:
        since = ctx.postop_day - reintro
        prior = post[(post.index > ctx.postop_day - 14) & (post.index <= ctx.postop_day - 7)
                     & (post.index >= reintro)]
        p7 = float(prior.mean()) if len(prior) >= 3 else None
        comparable = since >= 7 and p7 is not None
        plateau = comparable and l7 <= p7 * 1.10
        delta = f"since day {reintro}"
        if plateau and l7 >= 5:
            status, text = MetricStatus.OK, "Sustaining flight tolerance"
        elif plateau:
            status, text = MetricStatus.WATCH, "Flight tolerance plateaued"
        elif comparable:
            status, text = MetricStatus.OK, "Progressing"
        else:
            status, text = MetricStatus.OK, "Stairs resumed"
        finding = (f"Stairs re-entered the routine on {ctx.day_phrase(reintro)}; "
                   f"{l7:.1f} flights/day this week")
        if p7 is not None:
            finding += f" against {p7:.1f} the week before ({(l7 / p7 - 1) * 100:+.0f}%)"
        finding += "."
        if status is MetricStatus.WATCH:
            finding += " Flight count has stopped growing — an early plateau signal."
        elif text == "Sustaining flight tolerance":
            finding += " Volume is holding at a healthy level."
    tempo_latest = None
    if tempo is not None:
        tempo_post = tempo[tempo.index >= 0]
        if len(tempo_post) and not stale(int(tempo_post.index.max()), ctx.postop_day):
            tempo_latest = float(tempo_post.iloc[-1])
            delta = (delta + " · " if delta else "") + f"ascent {tempo_latest:.2f} m/s"
    window = last_n_days(post, ctx.postop_day, 28)
    if tempo is not None:
        tempo_by_day = {int(d): float(v) for d, v in tempo.items()}
        series = [{"x": int(d), "y": round(float(v), 0), "y2": round(tempo_by_day[int(d)], 2)}
                  if int(d) in tempo_by_day else {"x": int(d), "y": round(float(v), 0), "y2": None}
                  for d, v in window.items()]
        chart = ChartSpec(kind="dual", series=tail(series), y_label="flights/day", y2_label="m/s")
    else:
        chart = ChartSpec(kind="bars", series=tail(points(window, digits=0)), y_label="flights/day")
    return build(
        "M8", ctx, status=status, status_text=text, finding=finding,
        value=f"{l7:.1f}", value_num=l7, unit="flights/day", value_label="flights this week",
        delta_text=delta, chart=chart, confidence=confidence_for(ctx, len(last7), 7),
        coverage_text=coverage,
        next_step="Add one flight a day with rail support; progress when pain-free."
        if status is MetricStatus.WATCH else None,
        method="First post-op day with a flight climbed, then the last 7 days' mean flights "
               "against the 7 before (a plateau is growth of 10% or less once stairs have "
               "been back for a week; a plateau at 5+ flights/day is sustained volume).",
    )
