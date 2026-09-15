"""Recovery quality & systemic state: M9 nocturnal disruption, M10
autonomic recovery, M11 circadian rest–activity amplitude.

The signals patients under-report by day. None of them is a verdict: M9
reads as "fragmentation rising with evening symptoms — a signal for
review", M10 as monitoring context.
"""

from __future__ import annotations

import numpy as np

from app.engine.care._common import (
    NO_RECENT_TEXT,
    build,
    confidence_for,
    last_n_days,
    nodata,
    points,
    stale,
)
from app.engine.care.stats import cosinor, interdaily_stability, pearson
from app.engine.care.types import CareContext, CareMetric, ChartSpec, tail
from app.engine.types import DeviationResult
from app.models.enums import MetricStatus
from app.models.enums import MetricType as M


def deviation_with_fallback(
    ctx: CareContext, canonical: M, variant: M | None
) -> tuple[DeviationResult | None, str]:
    """The engine's deviation for the canonical metric, else the locally
    scored variant a real device ships (hrv_sdnn for hrv_rmssd, skin_temp_delta
    for skin_temp — §9.4), with the key that was actually used."""
    dev = ctx.deviations.get(str(canonical))
    if dev is not None:
        return dev, str(canonical)
    if variant is not None:
        local = ctx.local_deviations.get(str(variant))
        if local is not None:
            return local, str(variant)
    return None, str(canonical)


def m9(ctx: CareContext) -> CareMetric:
    stages = ctx.sleep_stages
    sleep = ctx.series.get(str(M.SLEEP_DURATION))
    dev = ctx.deviations.get(str(M.SLEEP_DURATION))
    symptom_key = ctx.pathway.symptom_key
    have_stages = not stages.empty and stages["awake_h"].notna().any()
    if not have_stages:
        if sleep is None:
            return nodata("M9", ctx)
        post = sleep[sleep.index >= 0].astype(float)
        latest_day = int(post.index.max()) if len(post) else None
        if stale(latest_day, ctx.postop_day):
            return nodata("M9", ctx, NO_RECENT_TEXT,
                          finding=f"The latest night on record is {ctx.day_phrase(latest_day)}.")
        base = ctx.baselines.get(str(M.SLEEP_DURATION))
        latest = float(post.iloc[-1])
        flagged = dev is not None and dev.flagged and not stale(dev.last_day, ctx.postop_day)
        if flagged:
            status, text = MetricStatus.WATCH, "Sleep well below baseline"
        else:
            status, text = MetricStatus.OK, "Nights settling"
        finding = (f"Sleep stages are not reported, so only total sleep is tracked: latest "
                   f"{latest:.1f} h" + (f" vs baseline {base.mean:.1f} h" if base else "") + ".")
        if flagged:
            finding += " Total sleep has fallen well below the patient's own norm."
        chart = ChartSpec(kind="line", series=tail(points(last_n_days(post, ctx.postop_day, 28))),
                          reference=round(base.mean, 2) if base else None, y_label="h")
        return build(
            "M9", ctx, status=status, status_text=text, finding=finding,
            value=f"{latest:.1f} h", value_num=latest, unit="sleep duration only",
            value_label="total sleep", delta_text=f"baseline {base.mean:.1f} h" if base else None,
            chart=chart, inputs=[str(M.SLEEP_DURATION)],
            coverage_text=f"{len(last_n_days(post, ctx.postop_day, 7))} of 7 nights",
            next_step="Ask about pain at night and sleeping position." if flagged else None,
        )

    frame = stages[stages["total_h"] > 0].copy()
    frame["frag"] = frame["awake_h"] / frame["total_h"]
    frag = frame.dropna(subset=["frag"]).set_index("day")["frag"].astype(float)
    frag = frag.groupby(level=0).mean().sort_index()
    latest_day = int(frag[frag.index >= 0].index.max()) if len(frag[frag.index >= 0]) else None
    if stale(latest_day, ctx.postop_day):
        return nodata("M9", ctx, NO_RECENT_TEXT,
                      finding=f"The latest night with sleep stages is {ctx.day_phrase(latest_day)}.")
    pre = frag[frag.index < 0]
    if len(pre) >= 3:
        baseline, base_label = float(pre.mean()), "pre-op nights"
    else:
        early = frag[frag.index >= 2].iloc[:3]
        if early.empty:
            return nodata("M9", ctx, "Building baseline")
        baseline, base_label = float(early.mean()), "first post-op nights"
    recent_nights = last_n_days(frag, ctx.postop_day, 7)
    if len(recent_nights) < 2:
        return nodata("M9", ctx, "Building baseline",
                      coverage_text=f"{len(recent_nights)} of 7 nights with stages")
    recent = float(recent_nights.mean())

    symptom = ctx.symptom(symptom_key)
    evening = {}
    for row in symptom.itertuples():
        value = row.pm if row.pm == row.pm else row.mean
        if value == value:
            evening[int(row.day)] = float(value)
    window = last_n_days(frag, ctx.postop_day, 14)
    pairs = [(evening[int(d)], float(v)) for d, v in window.items() if int(d) in evening]
    r = pearson([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) >= 6 else None
    sleep_flagged = dev is not None and dev.flagged and not stale(dev.last_day, ctx.postop_day)

    if baseline > 0 and recent >= 1.5 * baseline and r is not None and r >= 0.4:
        status, text = MetricStatus.FLAG, f"Night disruption tracks {symptom_key}"
    elif baseline > 0 and recent >= 1.5 * baseline:
        status, text = MetricStatus.WATCH, "Nights fragmented"
    elif sleep_flagged:
        status, text = MetricStatus.WATCH, "Sleep well below baseline"
    else:
        status, text = MetricStatus.OK, "Nights settling"

    finding = (f"Awake {recent * 100:.0f}% of the night over the last {len(recent_nights)} nights "
               f"vs {baseline * 100:.0f}% on {base_label}")
    if r is not None:
        finding += f"; correlation with evening {symptom_key} r={r:.2f} over {len(pairs)} nights"
    finding += "."
    if status is MetricStatus.FLAG:
        finding += (f" Overnight fragmentation is rising with evening {symptom_key} — a "
                    f"{symptom_key}-not-controlled-overnight signal for review.")
    elif text == "Nights fragmented":
        finding += " Nights are more fragmented than the patient's own baseline."
    elif sleep_flagged:
        finding += " Fragmentation is near baseline but total sleep has fallen well below it."
    delta = f"baseline {baseline * 100:.0f}%" + (f" · r={r:.2f}" if r is not None else "")
    chart_series = [
        {"x": int(d), "y": round(float(v) * 100, 1), "y2": evening.get(int(d))}
        for d, v in last_n_days(frag, ctx.postop_day, 28).items()
    ]
    chart = ChartSpec(kind="dual", series=tail(chart_series), y_label="awake %",
                      y2_label=f"evening {symptom_key}", reference=round(baseline * 100, 1))
    return build(
        "M9", ctx, status=status, status_text=text, finding=finding,
        value=f"{recent * 100:.0f}%", value_num=recent * 100, unit="fragmented",
        value_label="awake fraction", delta_text=delta, chart=chart,
        confidence=confidence_for(ctx, len(recent_nights), 7),
        coverage_text=f"{len(recent_nights)} of 7 nights with stages · {len(pairs)} "
                      f"evening {symptom_key} logs",
        next_step="Ask about pain at night and sleeping position; review evening analgesia timing."
        if status is not MetricStatus.OK else None,
        inputs=[str(M.SLEEP_STAGES), symptom_key],
    )


def _aligned_z(a: DeviationResult, b: DeviationResult, n_max: int = 14) -> tuple[list, list, int]:
    n = min(len(a.series_z), len(b.series_z), n_max)
    return list(a.series_z[-n:]), list(b.series_z[-n:]), n


def m10(ctx: CareContext) -> CareMetric:
    hrv, hrv_key = deviation_with_fallback(ctx, M.HRV_RMSSD, M.HRV_SDNN)
    rhr = ctx.deviations.get(str(M.RESTING_HR))
    if hrv is None or rhr is None:
        return nodata("M10", ctx)
    if stale(hrv.last_day, ctx.postop_day) or stale(rhr.last_day, ctx.postop_day):
        return nodata("M10", ctx, NO_RECENT_TEXT,
                      finding="HRV or resting heart rate stopped reporting more than five days ago.")
    zh, zr, n = _aligned_z(hrv, rhr)
    if n < 3:
        return nodata("M10", ctx, "Building baseline", coverage_text=f"{n} scored nights")
    index_day = [(-a + b) / 2.0 for a, b in zip(zh, zr)]
    index = float(np.mean(index_day[-7:]))
    run = best = 0
    for a, b in zip(zh, zr):
        run = run + 1 if (-a > 1 and b > 1) else 0
        best = max(best, run)
    sustained = best >= 3
    if sustained and index > 1.5:
        status, text = MetricStatus.FLAG, "Sustained systemic stress signals"
    elif index > 0.8:
        status, text = MetricStatus.WATCH, "Autonomic recovery lagging"
    elif index < -0.3:
        status, text = MetricStatus.OK, "Autonomic recovery ahead"
    else:
        status, text = MetricStatus.OK, "Autonomic recovery on course"
    z_hrv, z_rhr = float(hrv.latest_z), float(rhr.latest_z)
    finding = (f"Adverse autonomic index {index:+.1f}σ over the last 7 nights (HRV "
               f"{z_hrv:+.1f}σ, resting HR {z_rhr:+.1f}σ vs the patient's own baseline)")
    if sustained:
        finding += f"; HRV suppressed with resting HR elevated on {best} consecutive nights"
    finding += "."
    if status is MetricStatus.FLAG:
        finding += (" Sustained HRV suppression with resting-HR elevation is a systemic stress "
                    "pattern (overloading, poorly controlled pain, or a brewing complication) — "
                    "monitoring context for clinician review.")
    elif status is MetricStatus.WATCH:
        finding += " Autonomic recovery is lagging the patient's own baseline."
    first_day = (hrv.last_day or ctx.postop_day) - (n - 1)
    chart = ChartSpec(
        kind="dual",
        series=[{"x": first_day + i, "y": round(-a, 2), "y2": round(b, 2)}
                for i, (a, b) in enumerate(zip(zh, zr))],
        y_label="−HRV z", y2_label="RHR z", reference=0.0,
    )
    return build(
        "M10", ctx, status=status, status_text=text, finding=finding,
        value=f"{index:+.1f}", value_num=index, unit="σ", value_label="adverse autonomic index",
        delta_text=f"HRV {z_hrv:+.1f}σ · RHR {z_rhr:+.1f}σ", chart=chart,
        inputs=[hrv_key, str(M.RESTING_HR)],
        next_step="Review alongside temperature, pain reports and the incision."
        if status is MetricStatus.FLAG else None,
        confidence=confidence_for(ctx, n, 7), coverage_text=f"{n} scored nights",
        method="Mean of the EWMA z-scores of HRV (sign flipped) and resting HR, last 7 nights; "
               "'sustained' is three consecutive nights with both beyond +1σ adverse.",
    )


def m11(ctx: CareContext) -> CareMetric:
    steps = ctx.intraday.get(str(M.STEPS))
    hr = ctx.intraday.get(str(M.HR_SAMPLE))
    if steps is not None and not steps.empty:
        frame, label, key = steps, "activity", str(M.STEPS)
    elif hr is not None and not hr.empty:
        frame, label, key = hr, "heart rate", str(M.HR_SAMPLE)
    else:
        return nodata("M11", ctx)
    recent = frame[frame["day"] > ctx.postop_day - 14]
    matrix = recent.pivot_table(index="day", columns="hour", values="value", aggfunc="mean")
    matrix = matrix.reindex(columns=range(24))
    complete = matrix[matrix.notna().sum(axis=1) >= 18]
    coverage = f"{len(complete)} of 14 days with hourly {label}"
    if len(complete) < 5:
        return nodata("M11", ctx, "Building baseline", coverage_text=coverage)
    latest_day = int(complete.index.max())
    if stale(latest_day, ctx.postop_day):
        return nodata("M11", ctx, NO_RECENT_TEXT, coverage_text=coverage)

    per_day: list[tuple[int, float, float]] = []
    for day, row in complete.iterrows():
        present = row.dropna()
        fit = cosinor(present.index.to_numpy(dtype=float), present.to_numpy(dtype=float))
        ra = fit["amplitude"] / fit["mesor"] if fit["mesor"] > 0 else 0.0
        per_day.append((int(day), float(ra), float(fit["acrophase_h"])))
    per_day.sort()
    stability = interdaily_stability(complete.to_numpy(dtype=float))
    ras = [ra for _, ra, _ in per_day]
    n = len(ras)
    if n >= 14:
        ref, last = ras[:7], ras[-7:]
    else:
        split = max(3, n // 2)
        ref, last = ras[:split], ras[split:]
    ra_last = float(np.mean(last)) if last else float(np.mean(ras))
    ra_ref = float(np.mean(ref))
    change = (ra_last / ra_ref - 1.0) if ra_ref > 0 else 0.0
    acro = float(np.mean([a for _, _, a in per_day[-7:]]))
    if len(last) < 2:
        status, text = MetricStatus.OK, "Rhythm forming"
    elif change <= -0.30:
        status, text = MetricStatus.WATCH, "Rhythm flattening"
    elif change >= 0.15:
        status, text = MetricStatus.OK, "Rhythm re-consolidating"
    else:
        status, text = MetricStatus.OK, "Rhythm stable"
    finding = (f"Relative rest–activity amplitude {ra_last:.2f} over the last {len(last)} days "
               f"({change:+.0f}% vs the first {len(ref)}), interdaily stability {stability:.2f}, "
               f"daily peak around {acro:.0f}:00.")
    if status is MetricStatus.WATCH:
        finding += " A flattening rhythm often precedes reduced daytime activity and poor nights."
    profile = complete.iloc[-7:].mean(axis=0)
    fit = cosinor(profile.dropna().index.to_numpy(dtype=float), profile.dropna().to_numpy(dtype=float))
    omega = 2 * np.pi / 24.0
    curve = [{"x": h, "y": round(fit["mesor"] + fit["amplitude"]
                                 * float(np.cos(omega * h - omega * fit["acrophase_h"])), 1)}
             for h in range(24)]
    chart = ChartSpec(
        kind="line", series=[{"x": int(h), "y": round(float(v), 1)} for h, v in profile.items()
                             if v == v],
        fit=curve, x_label="Hour", y_label=label,
    )
    return build(
        "M11", ctx, status=status, status_text=text, finding=finding,
        value=f"{ra_last:.2f}", value_num=ra_last, unit="rel. amplitude",
        value_label="rest–activity amplitude",
        delta_text=f"IS {stability:.2f} · peak {acro:.0f}:00", chart=chart, inputs=[key],
        confidence=confidence_for(ctx, n, 10), coverage_text=coverage,
    )
