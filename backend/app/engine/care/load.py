"""Activity & load tolerance: M1 acute:chronic load ratio, M2 symptom–load
sensitivity, M3 loading-asymmetry decay.

These answer the progression-vs-overload question every follow-up turns on:
is the patient loading more than their tissue tolerance, does each extra
unit of load cost them symptoms the next morning, and is the limp settling.
"""

from __future__ import annotations

import numpy as np

from app.engine.care._common import (
    NO_RECENT_TEXT,
    build,
    confidence_for,
    grid,
    load_source,
    nodata,
    points,
    stale,
)
from app.engine.care.stats import (
    binary_segmentation,
    fit_exp_decay,
    ols_partial,
    ols_slope_t,
    rolling_mean,
)
from app.engine.care.types import CareContext, CareMetric, ChartSpec, tail
from app.engine.curves import curve_mid
from app.models.enums import MetricStatus
from app.models.enums import MetricType as M

GAIT_OK_PCT = 8.0
GAIT_FLAG_PCT = 10.0
GAIT_FLAG_AFTER_DAY = 10

SYMPTOM_NAMES = {
    "pain": ("Pain–load sensitivity", "pain", "0–10"),
    "breathlessness": ("Breathlessness–load sensitivity", "breathlessness", "0–4"),
    "fatigue": ("Fatigue–load sensitivity", "fatigue", "0–10"),
}
LOAD_SCALE = {str(M.STEPS): (1000.0, "1,000 steps", "pts / 1k steps"),
              str(M.ACTIVE_ENERGY): (100.0, "100 kcal", "pts / 100 kcal"),
              str(M.EXERCISE_SESSION): (10.0, "10 minutes", "pts / 10 min")}


def m1(ctx: CareContext) -> CareMetric:
    series, key, label = load_source(ctx)
    if series is None:
        return nodata("M1", ctx)
    post = series[series.index >= 2]
    latest_day = int(post.index.max()) if len(post) else None
    if stale(latest_day, ctx.postop_day):
        return nodata(
            "M1", ctx, NO_RECENT_TEXT,
            finding=f"The latest {label} reading is from {ctx.day_phrase(latest_day)}.",
        )
    day = ctx.postop_day
    full = grid(post, 2, day)
    acute = full[full.index > day - 7]
    short = day < 30
    chronic = full if short else full[full.index > day - 28]
    n_acute, n_chronic = int(acute.notna().sum()), int(chronic.notna().sum())
    coverage = f"{n_acute} of 7 days of {label} · {n_chronic}-day chronic window"
    if n_acute < 4 or n_chronic < 8 or n_chronic <= n_acute:
        return nodata(
            "M1", ctx, "Building baseline",
            finding=f"Only {n_chronic} days of {label} so far — the 28-day chronic window needs "
                    "at least eight.",
            coverage_text=coverage,
        )
    acute_mean = float(acute.mean())
    chronic_mean = float(chronic.mean())
    if chronic_mean <= 0:
        return nodata("M1", ctx, "Building baseline", coverage_text=coverage)
    ratio = acute_mean / chronic_mean

    if ctx.uses_expected_curve:
        chronic_days = chronic.dropna().index.to_numpy(dtype=float)
        acute_days = acute.dropna().index.to_numpy(dtype=float)
        chronic_curve = float(np.mean(curve_mid(ctx.procedure, chronic_days)))
        ratio_exp = float(np.mean(curve_mid(ctx.procedure, acute_days))) / chronic_curve
    else:
        chronic_curve, ratio_exp = 1.0, 1.0
    adjusted = ratio / ratio_exp if ratio_exp > 0 else ratio

    if adjusted > 1.5:
        status, text = MetricStatus.FLAG, "Overreaching vs tolerance band"
    elif adjusted >= 1.3:
        status, text = MetricStatus.WATCH, "Above tolerance band"
    elif adjusted < 0.6:
        status, text = MetricStatus.FLAG, "Load collapsing"
    elif adjusted < 0.8:
        status, text = MetricStatus.WATCH, "Stalled progression"
    else:
        status, text = MetricStatus.OK, "Within tolerance band"

    expected_clause = (
        f"expected ≈{ratio_exp:.2f}× at {ctx.day_phrase()}"
        if ctx.uses_expected_curve else "band 0.8–1.3× of the patient's own 28-day mean"
    )
    finding = (
        f"The last 7 days averaged {acute_mean:,.0f} {label}/day against a "
        f"{n_chronic}-day mean of {chronic_mean:,.0f} — ratio {ratio:.2f}× ({expected_clause})."
    )
    if short and ctx.uses_expected_curve:
        finding += f" Short chronic window ({n_chronic} days)."
    if status is MetricStatus.FLAG and adjusted > 1.5:
        finding += " Load has run well past the tolerance band."
    elif status is MetricStatus.WATCH and adjusted >= 1.3:
        finding += " Load is above the tolerance band."
    elif adjusted < 0.8:
        finding += " Load is falling behind what the recent weeks supported."
    if adjusted > 1.3:
        spike_note = _spike_followed_by_symptom(ctx, acute)
        if spike_note:
            finding += " " + spike_note

    next_step = None
    if status is not MetricStatus.OK:
        next_step = (
            "Hold the step target for 2–3 days, then progress ~10%/week."
            if adjusted > 1.0
            else "Ask what is limiting activity — pain, fatigue, fear of movement."
        )

    window = full[full.index > day - 28]
    fit = rolling_mean(window, 7, min_periods=3)
    band = []
    for d in window.index:
        adj = (float(curve_mid(ctx.procedure, float(d))) / chronic_curve
               if ctx.uses_expected_curve else 1.0)
        band.append({"x": int(d), "lo": round(0.8 * chronic_mean * adj, 1),
                     "hi": round(1.3 * chronic_mean * adj, 1)})
    chart = ChartSpec(
        kind="band", series=tail(points(window)), reference=round(chronic_mean, 1),
        band=tail(band), y_label=label, fit=tail(points(fit)),
    )
    return build(
        "M1", ctx, status=status, status_text=text, finding=finding,
        value=f"{ratio:.2f}×", value_num=ratio, unit="ratio", value_label="7-day ÷ 28-day load",
        delta_text=expected_clause, next_step=next_step,
        confidence=confidence_for(ctx, n_acute, 7), coverage_text=coverage, chart=chart,
        inputs=[key],
        method=f"7-day mean {label} divided by the {n_chronic}-day mean"
               + (", with the same ratio taken along the expected recovery curve as the "
                  "reference." if ctx.uses_expected_curve else ", judged against a 0.8–1.3 band."),
    )


def _spike_followed_by_symptom(ctx: CareContext, acute) -> str | None:
    frame = ctx.symptom()
    if frame.empty or acute.dropna().empty:
        return None
    spike_day = int(acute.idxmax())
    by_day = {int(r.day): float(r.mean) for r in frame.itertuples() if r.mean == r.mean}
    before, after = by_day.get(spike_day), by_day.get(spike_day + 1)
    if before is not None and after is not None and after > before:
        return (f"The last spike ({ctx.day_phrase(spike_day)}) was followed by a next-day "
                f"{ctx.pathway.symptom_key} rise ({before:.0f} → {after:.0f}).")
    return None


def m2(ctx: CareContext) -> CareMetric:
    symptom_key = ctx.pathway.symptom_key
    name, noun, scale_text = SYMPTOM_NAMES.get(symptom_key, SYMPTOM_NAMES["pain"])
    frame = ctx.symptom(symptom_key)
    series, key, label = load_source(ctx)
    unlock = (
        f"Needs daily {noun} logs — the check-in collects them; assign the "
        f"*Log {noun} AM & PM* task."
    )
    if series is None or frame.empty:
        return nodata("M2", ctx, unlock=unlock, name=name)
    divisor, per, unit = LOAD_SCALE.get(key, LOAD_SCALE[str(M.STEPS)])

    next_day = {}
    for row in frame.itertuples():
        value = row.am if row.am == row.am else row.mean
        if value == value:
            next_day[int(row.day)] = float(value)
    pairs: list[tuple[int, float, float]] = []
    for d in range(ctx.postop_day - 21, ctx.postop_day):
        x = series.get(d)
        y = next_day.get(d + 1)
        if x is not None and x == x and y is not None:
            pairs.append((d, float(x), y))
    n = len(pairs)
    coverage = (f"{n} paired {'day' if n == 1 else 'days'} of {label} and next-day {noun} "
                "in the last 21 days")
    if n < 6:
        if n == 0:
            have = f"No day yet pairs a {label} count with a next-day {noun} score"
        elif n == 1:
            have = f"Only one day pairs a {label} count with a next-day {noun} score"
        else:
            have = f"Only {n} days pair a {label} count with a next-day {noun} score"
        return nodata(
            "M2", ctx, "Needs more pairs", unlock=unlock, name=name, coverage_text=coverage,
            finding=f"{have}; six are needed.",
        )
    latest_pair_day = max(p[0] for p in pairs) + 1
    if stale(latest_pair_day, ctx.postop_day):
        return nodata("M2", ctx, NO_RECENT_TEXT, unlock=unlock, name=name, coverage_text=coverage,
                      finding=f"The last {noun} log is from {ctx.day_phrase(latest_pair_day)}.")

    xs = [p[1] / divisor for p in pairs]
    ys = [p[2] for p in pairs]
    ds = [float(p[0]) for p in pairs]
    # Day-adjusted: a recovering patient walks more AND hurts less every day,
    # so the raw slope of pain on steps is mostly the recovery itself. Holding
    # the day fixed leaves the dose-response — what an extra thousand steps
    # costs beyond where the recovery already had the patient.
    slope, se, _, _ = ols_partial(xs, ds, ys)
    finite_se = se == se and se != float("inf")
    if finite_se and se > 1e-9:
        t = slope / se
    elif finite_se and slope != 0:
        t = 99.0  # an exact fit has no standard error to divide by
    else:
        t = 0.0
    ci = 1.645 * se if finite_se else float("inf")
    # the drawn line carries the day-adjusted slope through the centroid
    intercept = float(np.mean(ys)) - slope * float(np.mean(xs))
    half = len(pairs) // 2
    early, late = pairs[:half], pairs[half:]
    slope_early = slope_late = None
    delta = delta_se = None
    if len(early) >= 5 and len(late) >= 5:
        slope_early, se_early, _, _ = ols_partial(
            [p[1] / divisor for p in early], [float(p[0]) for p in early], [p[2] for p in early])
        slope_late, se_late, _, _ = ols_partial(
            [p[1] / divisor for p in late], [float(p[0]) for p in late], [p[2] for p in late])
        if all(v == v and v != float("inf") for v in (se_early, se_late)):
            delta = slope_late - slope_early
            delta_se = (se_early**2 + se_late**2) ** 0.5
        else:
            slope_early = slope_late = None
    delta_resolved = delta is not None and delta_se is not None and abs(delta) >= 1.645 * delta_se

    # Every verdict carries its uncertainty: three weeks of near-constant
    # daily load cannot resolve a dose-response, and a slope with a ±3-point
    # interval is not a finding in either direction.
    cost_word = f"{noun} cost"
    unresolved = ci > 1.0
    if slope >= 0.5 and t >= 2:
        status, text = MetricStatus.FLAG, "Irritability rising"
    elif (slope >= 0.25 and t >= 1.0) or (delta_resolved and delta >= 0.2):
        status, text = MetricStatus.WATCH, f"{cost_word.capitalize()} climbing"
    elif unresolved:
        status, text = MetricStatus.OK, "Slope not yet resolved"
    elif delta_resolved and delta < -0.1:
        status, text = MetricStatus.OK, "Tolerance improving"
    else:
        status, text = MetricStatus.OK, "Tolerance stable"

    if text == "Slope not yet resolved":
        lead = (f"The day-to-day spread of {label} is too small to measure the {noun} cost of "
                f"activity yet (slope {slope:+.1f} ± {ci:.1f} points per {per}, {len(pairs)} "
                "paired days).")
    else:
        if slope >= 0:
            lead = f"Each extra {per} costs about {slope:.1f} {noun} points the next morning"
        else:
            lead = (f"Each extra {per} is followed by about {abs(slope):.1f} fewer {noun} points "
                    "the next morning")
        lead += f" (±{ci:.1f})"
        if slope_early is not None and delta_resolved:
            direction = "down" if slope < slope_early else "up"
            lead += f", {direction} from {slope_early:.1f} two weeks ago"
        if text == "Tolerance improving":
            lead += " — tolerance is improving."
        elif status is MetricStatus.WATCH:
            lead += f" — the {cost_word} of activity is climbing."
        elif status is MetricStatus.FLAG:
            lead += f" — irritability is rising (t={t:.1f})."
        else:
            lead += "."
    next_step = None
    if status is MetricStatus.FLAG:
        next_step = "Hold or reduce the load prescription and keep progression pain-limited."
    elif status is MetricStatus.WATCH:
        next_step = "Keep the load steady for a few days and re-check the slope."

    scatter = [{"x": round(p[1], 0), "y": round(p[2], 1), "label": f"D{p[0]}"} for p in pairs]
    x_lo, x_hi = min(xs), max(xs)
    fit = [{"x": round(x_lo * divisor, 0), "y": round(intercept + slope * x_lo, 2)},
           {"x": round(x_hi * divisor, 0), "y": round(intercept + slope * x_hi, 2)}]
    chart = ChartSpec(kind="scatter", series=tail(scatter), fit=fit, x_label=label,
                      y_label=f"next-day {noun}")
    return build(
        "M2", ctx, name=name, status=status, status_text=text, finding=lead,
        value=f"{slope:.2f}", value_num=slope, unit=unit, value_label=f"{cost_word} per {per}",
        delta_text=(f"was {slope_early:.2f} two weeks ago" if slope_early is not None and delta_resolved
                    else f"±{ci:.1f} (90% CI)" if ci != float("inf") else None),
        next_step=next_step, confidence=confidence_for(ctx, len(pairs), 14),
        coverage_text=coverage, chart=chart, inputs=[key, str(M.PAIN_NRS) if symptom_key == "pain"
                                                     else symptom_key, "checkins"],
        method=f"OLS regression of next-day {noun} ({scale_text}) on same-day {label} with the "
               "post-op day held fixed, last 21 days; the slope over the earlier half is compared "
               "with the later half.",
    )


def m3(ctx: CareContext) -> CareMetric:
    series = ctx.series.get(str(M.WALKING_ASYMMETRY_PCT))
    key, name, label = str(M.WALKING_ASYMMETRY_PCT), None, "walking asymmetry"
    ok_level, flag_level = GAIT_OK_PCT, GAIT_FLAG_PCT
    if series is None:
        series = ctx.series.get(str(M.DOUBLE_SUPPORT_PCT))
        if series is None:
            return nodata("M3", ctx)
        key, name, label = str(M.DOUBLE_SUPPORT_PCT), "Loading asymmetry decay (double support)", \
            "double support"
        pre = series[series.index < 0]
        base = float(pre.mean()) if len(pre) >= 3 else float(series.min())
        ok_level, flag_level = base + 2.0, base + 4.0
    post = series[series.index >= 2].astype(float)
    latest_day = int(post.index.max()) if len(post) else None
    if stale(latest_day, ctx.postop_day):
        return nodata("M3", ctx, NO_RECENT_TEXT, name=name,
                      finding=f"The latest {label} reading is from {ctx.day_phrase(latest_day)}.")
    if len(post) < 4:
        return nodata("M3", ctx, "Building baseline", name=name,
                      coverage_text=f"{len(post)} days of {label}")
    days = post.index.to_numpy(dtype=float)
    values = post.to_numpy(dtype=float)
    fit = fit_exp_decay(days, values)
    latest = float(values[-1])

    last7 = post[post.index > ctx.postop_day - 7]
    # The trend is judged over ten days with a t-test: day-to-day gait noise
    # (~0.7 %) makes a seven-day slope alone a coin flip, and "improving" has
    # to mean the decline is real, not that the last week happened to tilt.
    last10 = post[post.index > ctx.postop_day - 10]
    slope7, t_slope = (ols_slope_t(last10.index, last10.values) if len(last10) >= 4
                       else (None, 0.0))
    improving = slope7 is not None and slope7 < -0.05 and t_slope <= -1.5
    plateau = slope7 is not None and not improving and latest > ok_level
    plateau_day = None
    if plateau:
        last21 = post[post.index > ctx.postop_day - 21]
        splits = binary_segmentation(last21.to_numpy(dtype=float), min_seg=3)
        plateau_day = int(last21.index[splits[-1]]) if splits else int(last10.index[0])

    if plateau and latest > flag_level and ctx.postop_day > GAIT_FLAG_AFTER_DAY:
        status, text = MetricStatus.FLAG, "Asymmetry plateaued elevated"
    elif latest <= ok_level:
        status, text = MetricStatus.OK, "Near symmetric"
    elif improving:
        status, text = MetricStatus.WATCH, "Still elevated, improving"
    else:
        status, text = MetricStatus.WATCH, "Elevated, not yet improving"

    delta_text = (f"plateau since day {plateau_day}" if plateau
                  else f"decay {fit['k']:.2f}/day")
    finding = f"Latest {label} {latest:.1f}%"
    if plateau:
        finding += (f" and flat since {ctx.day_phrase(plateau_day)} (slope {slope7:+.2f} %/day "
                    f"over the last {len(last10)} days)")
    elif improving:
        finding += f", still settling at {abs(slope7):.2f} %/day"
    finding += (f"; the decay fit projects a floor near {fit['c']:.1f}%."
                if fit["k"] > 0 else ".")
    if status is MetricStatus.FLAG:
        finding += " A plateau at an elevated level is a stalled weight-bearing trend worth a look."
    next_step = ("Consider a gait review with PT; weight-shift drills."
                 if status is MetricStatus.FLAG else None)

    window = post[post.index > ctx.postop_day - 28]
    curve = [{"x": int(d), "y": round(fit["c"] + fit["a"] * float(np.exp(-fit["k"] * d)), 2)}
             for d in window.index]
    chart = ChartSpec(kind="line", series=tail(points(window)), fit=tail(curve),
                      marker_x=plateau_day, y_label=f"{label} %", reference=round(ok_level, 1))
    return build(
        "M3", ctx, name=name, status=status, status_text=text, finding=finding,
        value=f"{latest:.1f}%", value_num=latest, unit="%", value_label=label,
        delta_text=delta_text, next_step=next_step,
        confidence=confidence_for(ctx, len(last7), 7),
        coverage_text=f"{len(last7)} of 7 days of {label}", chart=chart, inputs=[key],
    )
