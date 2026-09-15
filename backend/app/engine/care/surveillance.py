"""Deterioration surveillance: M12 multi-signal deterioration index, M13
thermal–cardiac coupling. Both are GUARDED: every string they emit reads as
"signals deviating from baseline — recommend review", never as a named
complication, and the M12 status can never disagree with the weighted
composite the risk tier already uses.
"""

from __future__ import annotations

import math

from app.engine.care._common import build, confidence_for, nodata, stale
from app.engine.care.recovery_quality import deviation_with_fallback
from app.engine.care.stats import chi2_sf, mahalanobis, pearson, xcorr_lag
from app.engine.care.types import CareContext, CareMetric, ChartSpec
from app.engine.deviation import EWMA_LAMBDA
from app.models.enums import MetricStatus
from app.models.enums import MetricType as M

# The history behind the Mahalanobis distance is the EWMA-smoothed z series
# (DeviationResult.series_z) while today's vector is the raw z. An EWMA with
# smoothing λ carries λ/(2-λ) of the raw variance, so the history is scaled
# back up before its covariance is taken — otherwise every raw day sits
# "far" from a history that was smoothed to a third of its spread, and five
# healthy signals read as a deviation on most days.
_EWMA_SCALE = 1.0 / math.sqrt(EWMA_LAMBDA / (2.0 - EWMA_LAMBDA))
# Chi-square tails, not raw σ cut-offs: with k signals, d² ~ χ²(k) under the
# null, so the same "2σ" means p=0.05 for one signal and p=0.55 for five.
FLAG_P = 0.01
WATCH_P = 0.10

# (canonical, variant, adverse sign, label): sign +1 = rising is adverse
SIGNALS: list[tuple[M, M | None, float, str]] = [
    (M.RESTING_HR, None, 1.0, "Resting heart rate"),
    (M.RESPIRATORY_RATE, None, 1.0, "Respiratory rate"),
    (M.SKIN_TEMP, M.SKIN_TEMP_DELTA, 1.0, "Skin temperature"),
    (M.HRV_RMSSD, M.HRV_SDNN, -1.0, "HRV"),
    (M.SPO2, None, -1.0, "SpO₂"),
]


def m12(ctx: CareContext) -> CareMetric:
    rows = []
    for canonical, variant, sign, label in SIGNALS:
        dev, key = deviation_with_fallback(ctx, canonical, variant)
        if dev is None or stale(dev.last_day, ctx.postop_day):
            continue
        rows.append((key, label, sign, dev))
    k = len(rows)
    coverage = f"{k} of {len(SIGNALS)} signals reporting"
    if k < 3:
        return nodata("M12", ctx, "Needs 3 signals" if k else "No data yet", coverage_text=coverage)
    z_today = [sign * float(dev.raw_z) for _, _, sign, dev in rows]
    n = min(len(dev.series_z) for *_, dev in rows)
    hist = [[rows[j][2] * float(rows[j][3].series_z[-n:][i]) * _EWMA_SCALE for j in range(k)]
            for i in range(n)]
    d, contributions = mahalanobis(z_today, hist)
    p = chi2_sf(d * d, k)
    comp = ctx.composite
    if comp.level == "high" or p < FLAG_P:
        status, text = MetricStatus.FLAG, "Deviating from baseline — review"
    elif comp.level == "elevated" or p < WATCH_P:
        status, text = MetricStatus.WATCH, "Drifting from baseline"
    else:
        status, text = MetricStatus.OK, "Within personal baseline"
    drivers = sorted(
        [{"metric_type": key, "label": label, "contribution": round(c, 3),
          "direction": "up" if z > 0 else "down", "z": round(z, 2)}
         for (key, label, _, _), c, z in zip(rows, contributions, z_today)],
        key=lambda item: -item["contribution"],
    )
    top = " and ".join(item["label"].lower() for item in drivers[:2])
    first = ctx.first_name
    early = ctx.uses_expected_curve and ctx.postop_day < 14
    if status is MetricStatus.FLAG:
        finding = (f"Today's physiologic state sits {d:.1f}σ from {first}'s own stable baseline "
                   f"across {k} signals, led by {top}. Signals deviating from baseline — "
                   "recommend clinician review.")
    elif status is MetricStatus.WATCH:
        finding = (f"Today's physiologic state sits {d:.1f}σ from {first}'s own baseline across "
                   f"{k} signals (led by {top}); the weighted composite reads {comp.index:.1f} "
                   f"({comp.level}). Drifting from baseline — worth a look.")
    else:
        finding = (f"Today's {k} signals sit within {first}'s own baseline ({d:.1f}σ; composite "
                   f"{comp.index:.1f}, {comp.level}).")
    if early:
        finding += " Early post-op — physiologic settling can move these signals."
    chart = ChartSpec(
        kind="bars",
        series=[{"x": item["label"], "y": round(item["contribution"] * 100, 1)} for item in drivers],
        x_label="Signal", y_label="% of distance",
    )
    return build(
        "M12", ctx, status=status, status_text=text, finding=finding,
        value=f"{d:.1f}", value_num=d, unit="σ", value_label="distance from own baseline",
        delta_text=f"{k} signals · p={p:.2f} · composite {comp.index:.1f} ({comp.level}) · "
                   f"{ctx.day_phrase()}",
        chart=chart, drivers=drivers, inputs=[key for key, *_ in rows],
        next_step="Contact the patient today; ask about fever, chills, breathing, and the incision."
        if status is MetricStatus.FLAG else None,
        confidence=confidence_for(ctx, n, 7),
        coverage_text=f"{coverage} · {n} baseline days",
        method="Mahalanobis distance of today's z-scores from the patient's own 14-day "
               "multivariate baseline (shrinkage covariance), read as a chi-square tail with one "
               "degree of freedom per signal, alongside the weighted composite used for the risk "
               "tier.",
    )


def m13(ctx: CareContext) -> CareMetric:
    temp, temp_key = deviation_with_fallback(ctx, M.SKIN_TEMP, M.SKIN_TEMP_DELTA)
    rhr = ctx.deviations.get(str(M.RESTING_HR))
    hrv, hrv_key = deviation_with_fallback(ctx, M.HRV_RMSSD, M.HRV_SDNN)
    if temp is None or rhr is None:
        return nodata("M13", ctx)
    if stale(temp.last_day, ctx.postop_day) or stale(rhr.last_day, ctx.postop_day):
        return nodata("M13", ctx, "No recent data",
                      finding="Skin temperature or resting heart rate stopped reporting more "
                              "than five days ago.")
    n = min(len(temp.series_z), len(rhr.series_z), 10)
    zt, zr = [float(z) for z in temp.series_z[-n:]], [float(z) for z in rhr.series_z[-n:]]
    zh = None
    if hrv is not None and not stale(hrv.last_day, ctx.postop_day) and len(hrv.series_z) >= n:
        zh = [float(z) for z in hrv.series_z[-n:]]
    zt7, zr7 = zt[-7:], zr[-7:]
    zh7 = zh[-7:] if zh is not None else None
    if len(zt7) < 5:
        return nodata("M13", ctx, "Building baseline", coverage_text=f"{len(zt7)} scored nights")
    r_tr = pearson(zt7, zr7)
    r_th = pearson(zt7, [-z for z in zh7]) if zh7 is not None else None
    lag, _ = xcorr_lag(zt, zr)
    # A coupled night needs the temperature side of the coupling: with temp
    # elevated, both cardiac signals adverse is a full night and one of them
    # a partial night. Two cardiac signals moving without temperature is M10's
    # story, not this one.
    full = partial = 0
    for i in range(len(zt7)):
        if zt7[i] <= 1:
            continue
        cardiac = [zr7[i] > 1] + ([-zh7[i] > 1] if zh7 is not None else [])
        hits = sum(cardiac)
        if hits == len(cardiac):
            full += 1
        elif hits >= 1:
            partial += 1
    shared = full + partial
    r_max = max(r_tr or 0.0, r_th or 0.0)
    if shared >= 2 and r_max >= 0.5:
        status, text = MetricStatus.FLAG, "Temp and HR rising together — review"
    elif (shared >= 1 and r_max >= 0.5) or shared >= 2:
        status, text = MetricStatus.WATCH, "Possible coupling"
    else:
        status, text = MetricStatus.OK, "No coupled movement"
    r_text = f"{r_tr:.2f}" if r_tr is not None else "n/a"
    if status is MetricStatus.FLAG:
        finding = (f"Skin temperature and resting heart rate rose together on {shared} of the last "
                   f"{len(zt7)} nights" + (" with HRV suppressed" if zh7 is not None else "")
                   + f" (r={r_max:.2f}). Signals deviating from baseline — recommend review.")
    elif status is MetricStatus.WATCH:
        finding = (f"Skin temperature and resting heart rate moved together on {shared} of the "
                   f"last {len(zt7)} nights (r={r_text}, lag {lag:+d} d) — a possible coupling to "
                   "keep an eye on.")
    else:
        finding = (f"No coupled movement: temperature and resting HR rose together on {shared} "
                   f"of the last {len(zt7)} nights (r={r_text}).")
    first_day = (temp.last_day or ctx.postop_day) - (n - 1)
    chart = ChartSpec(
        kind="dual",
        series=[{"x": first_day + i, "y": round(a, 2), "y2": round(b, 2)}
                for i, (a, b) in enumerate(zip(zt, zr))],
        y_label="temp z", y2_label="RHR z", reference=1.0,
        extra={"hrv_z": [round(-z, 2) for z in zh]} if zh is not None else {},
    )
    inputs = [temp_key, str(M.RESTING_HR)] + ([hrv_key] if zh is not None else [])
    return build(
        "M13", ctx, status=status, status_text=text, finding=finding,
        value=f"{shared}", value_num=shared, unit="coupled nights", value_label="of the last 7",
        delta_text=f"r(temp,HR)={r_text} · lag {lag:+d}d", chart=chart, inputs=inputs,
        drivers=[{"label": "Nights with all signals adverse", "count": full},
                 {"label": "Nights with two of three adverse", "count": partial}],
        next_step="Ask about fever, chills, warmth, redness or drainage at the incision; "
                  "consider bringing the follow-up forward." if status is MetricStatus.FLAG else None,
        confidence=confidence_for(ctx, len(zt7), 7), coverage_text=f"{len(zt7)} of 7 nights scored",
    )
