"""Trajectory & benchmarking: M17 recovery-trajectory fit, M18 plateau /
regression change-point. Neither may contradict the engine's own
trajectory verdict — M17 reads its state straight from
``TrajectoryResult`` and only adds the fitted pace; M18 exposes the
engine's change-point day as its first driver so the timeline and the card
agree.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from app.engine.care._common import build, confidence_for, nodata, points, signed_pct, stale
from app.engine.care.stats import binary_segmentation, fit_saturating, ols
from app.engine.care.types import CareContext, CareMetric, ChartSpec, tail
from app.engine.curves import curve_mid
from app.models.enums import MetricStatus
from app.models.enums import MetricType as M
from app.models.enums import ProcedureType, TrajectoryState

FUNCTIONAL_LABELS = {str(M.STEPS): "Steps", str(M.WALKING_SPEED): "Walking speed",
                     "index": "Functional index"}
VITAL_ADVERSE = {str(M.RESTING_HR): ("up", "Resting HR"), str(M.SLEEP_DURATION): ("down", "Sleep")}


@lru_cache(maxsize=None)
def expected_rate(procedure: ProcedureType, first_day: int = 0, last_day: int = 60) -> float:
    """The saturating-exponential rate of the procedure's own expected curve
    over the same day span the patient's index covers — the yardstick a
    patient's fitted k is read against. Fitting the whole 60-day sigmoid
    while the patient shows only its first two weeks would compare two
    different shapes."""
    days = np.arange(first_day, last_day + 1, dtype=float)
    return float(fit_saturating(days, np.asarray(curve_mid(procedure, days), dtype=float))["k"])


def m17(ctx: CareContext) -> CareMetric:
    if not ctx.uses_expected_curve:
        return _own_baseline_trend(ctx)
    traj = ctx.trajectory
    actual = [(int(p["day"]), float(p["v"])) for p in traj.actual]
    coverage = f"{len(actual)} days of functional index"
    if len(actual) < 6:
        return nodata("M17", ctx, "Building baseline" if actual else "No data yet",
                      coverage_text=coverage)
    days = np.asarray([d for d, _ in actual], dtype=float)
    values = np.asarray([v for _, v in actual], dtype=float)
    fit = fit_saturating(days, values, seed=ctx.seed)
    k_exp = expected_rate(ctx.procedure, int(days.min()), int(days.max()))
    pace = fit["k"] / k_exp if k_exp > 0 else 0.0
    state = TrajectoryState(traj.state)
    if state == TrajectoryState.UNKNOWN or traj.pct is None:
        return nodata("M17", ctx, "Not yet comparable", coverage_text=coverage,
                      finding="The functional index cannot be compared to the curve yet.")
    if stale(int(days.max()), ctx.postop_day):
        return nodata("M17", ctx, "No recent data", coverage_text=coverage)
    if state == TrajectoryState.BEHIND:
        status, text = MetricStatus.FLAG, "Behind expected curve"
    elif state == TrajectoryState.AHEAD:
        status, text = MetricStatus.OK, "Ahead of expected curve"
    else:
        status, text = MetricStatus.OK, "On expected curve"
    lo, hi = fit["k_ci"]
    resolved = (hi - lo) <= max(fit["k"], 0.02)
    if fit["A"] <= 0:
        plateau_text = "index falling — no plateau projected"
    elif fit["asymptote"] > 1.2:
        plateau_text = "projected plateau above 120%"
    else:
        plateau_text = f"projected plateau {fit['asymptote'] * 100:.0f}%"
    pace_text = f"pace {pace:.2f}×" if resolved else "pace not yet resolved"
    delta = f"{pace_text} · {plateau_text}"
    if traj.anchored:
        delta += " · pace only, no pre-op norm"
    finding = f"Functional index {traj.pct:+.0f}% vs the expected curve at {ctx.day_phrase()}"
    if resolved:
        finding += (f"; the fitted recovery rate is {pace:.2f}× the curve's over the same days "
                    f"(k={fit['k']:.3f}/day, 90% CI {lo:.2f}–{hi:.2f})")
    else:
        finding += (f"; the fitted recovery rate (k={fit['k']:.3f}/day, 90% CI {lo:.2f}–{hi:.2f}) "
                    "is not resolved yet")
    finding += f", {plateau_text}" + (" of baseline capacity." if fit["A"] > 0 else ".")
    if traj.anchored:
        finding += " No pre-op norm, so this tracks pace, not capacity."
    if status is MetricStatus.FLAG:
        finding += " Recovery is running behind the curve for this procedure."
    fitted = [{"x": int(d), "y": round(fit["y0"] + fit["A"] * (1 - float(np.exp(-fit["k"] * d))), 3)}
              for d in days]
    band = [{"x": int(p["day"]), "lo": p["lo"], "hi": p["hi"]} for p in traj.expected
            if int(p["day"]) >= int(days.min())]
    chart = ChartSpec(
        kind="band", series=tail([{"x": d, "y": round(v, 3)} for d, v in actual]),
        band=tail(band), fit=tail(fitted), marker_x=traj.change_point_day,
        y_label="fraction of baseline capacity",
    )
    return build(
        "M17", ctx, status=status, status_text=text, finding=finding,
        value=signed_pct(traj.pct), value_num=traj.pct, unit="vs expected",
        value_label="functional index vs curve", delta_text=delta, chart=chart,
        confidence=confidence_for(ctx, len(actual), 10), coverage_text=coverage,
        drivers=[{"label": "Fitted rate k", "value": round(fit["k"], 4)},
                 {"label": "Expected rate k", "value": round(k_exp, 4)},
                 {"label": "Fit r²", "value": round(fit["r2"], 3)}],
        next_step="Review what is limiting progression with PT; check pain, sleep and adherence."
        if status is MetricStatus.FLAG else None,
    )


def _own_baseline_trend(ctx: CareContext) -> CareMetric:
    """Chronic pathways: no expected curve, so the verdict is the 28-day
    trend of activity against the patient's own median, with its CI."""
    steps = ctx.series.get(str(M.STEPS))
    if steps is None:
        return nodata("M17", ctx, name="Trend vs own baseline",
                      unlock="Needs daily activity (steps) to trend against the patient's own baseline.")
    window = steps[steps.index > ctx.postop_day - 28].astype(float)
    if len(window) < 8:
        return nodata("M17", ctx, "Building baseline", name="Trend vs own baseline",
                      coverage_text=f"{len(window)} of 28 days of steps")
    if stale(int(window.index.max()), ctx.postop_day):
        return nodata("M17", ctx, "No recent data", name="Trend vs own baseline")
    median = float(window.median())
    slope, _, se, _, n = ols(window.index.to_numpy(dtype=float), window.to_numpy(dtype=float))
    per_week = slope * 7 / median * 100 if median > 0 else 0.0
    ci = 1.645 * se * 7 / median * 100 if median > 0 and np.isfinite(se) else float("inf")
    if per_week + ci < 0:
        status, text = MetricStatus.WATCH, "Trending below own baseline"
    elif per_week - ci > 0:
        status, text = MetricStatus.OK, "Trending up"
    else:
        status, text = MetricStatus.OK, "Holding own baseline"
    finding = (f"Activity is changing {per_week:+.0f}% per week relative to the patient's own "
               f"28-day median ({median:,.0f} steps; 90% CI ±{ci:.0f} points) at {ctx.day_phrase()}.")
    chart = ChartSpec(kind="line", series=tail(points(window)), reference=round(median, 0),
                      x_label="Day in program", y_label="steps")
    return build(
        "M17", ctx, name="Trend vs own baseline", status=status, status_text=text,
        finding=finding, value=signed_pct(per_week), value_num=per_week, unit="per week",
        value_label="trend vs own baseline", delta_text=f"median {median:,.0f} steps",
        chart=chart, confidence=confidence_for(ctx, n, 14),
        coverage_text=f"{n} of 28 days of steps",
        method="OLS slope of daily steps over the last 28 days, as % of the 28-day median per "
               "week, with a 90% CI.",
    )


def _events(ctx: CareContext) -> list[dict]:
    candidates: list[tuple[str, pd.Series, str]] = []
    for metric in (M.STEPS, M.WALKING_SPEED):
        s = ctx.series.get(str(metric))
        if s is not None:
            candidates.append((str(metric), s, "functional"))
    if ctx.uses_expected_curve and ctx.trajectory.actual:
        index = pd.Series({int(p["day"]): float(p["v"]) for p in ctx.trajectory.actual})
        candidates.append(("index", index, "index"))
    for metric in VITAL_ADVERSE:
        s = ctx.series.get(str(metric))
        if s is not None:
            candidates.append((str(metric), s, "vital"))

    events = []
    for key, series, kind in candidates:
        window = series[(series.index >= 2) & (series.index > ctx.postop_day - 28)].astype(float)
        window = window.dropna()
        if len(window) < 8:
            continue
        values = window.to_numpy(dtype=float)
        splits = binary_segmentation(values, min_seg=4, min_shift_sd=1.0)
        if not splits:
            continue
        k = splits[-1]
        day = int(window.index[k])
        if ctx.postop_day - day > 14:
            continue
        left, right = values[:k], values[k:]
        shift = float(right.mean() - left.mean())
        level = float(abs(right.mean())) or 1.0
        post_days = window.index[k:].to_numpy(dtype=float)
        post_slope, _, post_se, _, _ = ols(post_days, right)
        post_se = post_se if np.isfinite(post_se) else abs(post_slope)
        # growth per day as a fraction of the level, with its 90% upper bound:
        # a plateau is growth we are confident is small, never a noisy week
        growth = post_slope / level
        growth_hi = (post_slope + 1.645 * post_se) / level
        growth_lo = (post_slope - 1.645 * post_se) / level
        if kind == "vital":
            adverse, label = VITAL_ADVERSE[key]
            if (adverse == "up" and shift > 0) or (adverse == "down" and shift < 0):
                events.append({"metric": key, "label": label, "day": day, "kind": "regression",
                               "direction": "up" if shift > 0 else "down", "series": window})
            continue
        label = FUNCTIONAL_LABELS[key]
        falling = shift < 0 or growth_hi < 0
        if falling:
            events.append({"metric": key, "label": label, "day": day, "kind": "regression",
                           "direction": "down", "series": window})
            continue
        if not ctx.uses_expected_curve:
            continue  # without an expected rise, flat is not a finding
        # a plateau is growth confidently below half of what the curve still
        # expects at these days — late in a recovery the curve itself flattens
        mid_now = float(curve_mid(ctx.procedure, post_days[-1]))
        mid_then = float(curve_mid(ctx.procedure, post_days[0]))
        span = max(post_days[-1] - post_days[0], 1.0)
        expected_growth = (mid_now - mid_then) / span / max(mid_now, 1e-6)
        if expected_growth >= 0.01 and growth_hi < 0.5 * expected_growth and growth_lo <= 0.0:
            events.append({"metric": key, "label": label, "day": day, "kind": "plateau",
                           "direction": "flat", "series": window, "growth": growth})
    return events


def m18(ctx: CareContext) -> CareMetric:
    have_series = any(str(m) in ctx.series for m in (M.STEPS, M.WALKING_SPEED))
    if not have_series:
        return nodata("M18", ctx)
    steps = ctx.series.get(str(M.STEPS))
    if steps is not None and stale(int(steps[steps.index >= 0].index.max())
                                  if len(steps[steps.index >= 0]) else None, ctx.postop_day):
        return nodata("M18", ctx, "No recent data")
    events = _events(ctx)
    functional = [e for e in events if e["metric"] in FUNCTIONAL_LABELS]
    pick = max(functional or events, key=lambda e: e["day"]) if events else None
    drivers = [{"metric_type": "trajectory", "label": "Trajectory change point",
                "day": ctx.trajectory.change_point_day}]
    drivers += [{"metric_type": e["metric"], "label": e["label"], "day": e["day"],
                 "kind": e["kind"], "direction": e["direction"]} for e in events]
    if pick is None:
        status, text = MetricStatus.OK, "No plateau"
        finding = "No sustained mean shift in steps, walking speed, sleep or resting HR over the last 28 days."
        value, delta = "None", None
        series = steps[(steps.index >= 2) & (steps.index > ctx.postop_day - 28)] if steps is not None else None
        chart = ChartSpec(kind="line", series=tail(points(series)) if series is not None else [],
                          y_label="steps")
    else:
        day = pick["day"]
        if pick["kind"] == "regression":
            status, text = MetricStatus.FLAG, f"Regression since day {day}"
        else:
            status, text = MetricStatus.WATCH, f"Plateau since day {day}"
        direction = {"flat": "flat", "down": "falling", "up": "rising"}[pick["direction"]]
        finding = (f"{pick['label']} has been {direction} since {ctx.day_phrase(day)} — the most "
                   f"recent sustained shift in the last 14 days.")
        others = [e for e in events if e is not pick]
        if others:
            finding += " Also: " + ", ".join(f"{e['label'].lower()} {e['kind']} since day {e['day']}"
                                             for e in others) + "."
        value = f"Day {day}"
        delta = f"{pick['label']} {direction}"
        chart = ChartSpec(kind="line", series=tail(points(pick["series"], digits=3)), marker_x=day,
                          y_label=pick["label"].lower())
    return build(
        "M18", ctx, status=status, status_text=text, finding=finding,
        value=value, value_num=float(pick["day"]) if pick else None, unit="",
        value_label="most recent change point", delta_text=delta, chart=chart, drivers=drivers,
        next_step="Ask what changed that day — pain, a setback, a new activity — and adjust the plan."
        if status is not MetricStatus.OK else None,
        confidence=ctx.confidence.level,
        coverage_text=f"{len(events)} shift{'s' if len(events) != 1 else ''} found in 28 days",
    )
