"""The performance board: every test the athlete has logged, each against
their own best and trend first and the level second, with left-right
asymmetry wherever a test is sided and a neuromuscular-fatigue read off
the countermovement jump.

Nothing here is a verdict about the athlete; it is a reading of numbers
they or their staff entered, with the comparison stated.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import numpy as np

from app.models.sports import SportsTest
from app.sports.catalog.tests import CATEGORIES, TESTS, TestSpec, band_for, tests_for
from app.sports.data import SportsData

# A countermovement jump more than this far below the athlete's 28-day
# baseline reads as neuromuscular fatigue; strategy metrics (time to
# takeoff) move first, so they are read too.
CMJ_DROP_WATCH = 5.0
CMJ_DROP_FLAG = 10.0
TTO_RISE_FLAG = 8.0


def _fmt(value: float, decimals: int) -> str:
    if decimals == 0:
        return f"{value:,.0f}"
    return f"{value:,.{decimals}f}"


def _asymmetry(left: float | None, right: float | None, higher_is_better: bool) -> dict[str, Any] | None:
    if left is None or right is None or left <= 0 or right <= 0:
        return None
    if higher_is_better:
        weaker, stronger = min(left, right), max(left, right)
    else:
        # Lower is better (a timed test): the slower side is the weaker one.
        weaker, stronger = max(left, right), min(left, right)
    pct = abs(left - right) / max(stronger, 1e-9) * 100.0
    weaker_side = "left" if (left == weaker) else "right"
    return {"pct": round(pct, 1), "weaker": weaker_side,
            "lsi": round((weaker / stronger) * 100.0, 1) if higher_is_better
            else round((stronger / weaker) * 100.0, 1)}


def _series(rows: list[SportsTest], side: str | None) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if side is not None and r.side != side:
            continue
        if side is None and r.side is not None:
            continue
        out.append({"date": r.date.isoformat(), "value": round(float(r.value), 3),
                    "source": r.source, "device": r.device})
    return out


def _best(values: list[float], higher: bool) -> float | None:
    if not values:
        return None
    return max(values) if higher else min(values)


def _trend(points: list[dict[str, Any]], higher: bool) -> dict[str, Any] | None:
    """Change over the last ~8 weeks against the earlier readings, as a
    percentage, with the direction read in the test's own terms."""
    if len(points) < 3:
        return None
    recent = [p["value"] for p in points[-3:]]
    earlier = [p["value"] for p in points[:-3]] or [points[0]["value"]]
    a, b = float(np.mean(earlier)), float(np.mean(recent))
    if a == 0:
        return None
    pct = (b - a) / abs(a) * 100.0
    better = pct > 0 if higher else pct < 0
    return {"pct": round(pct, 1), "better": better if abs(pct) >= 1.0 else None}


def _baseline_z(points: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    """The latest value against the athlete's 28-day baseline (ending the
    day before the latest reading), for the neuromuscular read."""
    if len(points) < 4:
        return None
    latest = points[-1]
    latest_day = date.fromisoformat(latest["date"])
    window = [p["value"] for p in points[:-1]
              if latest_day - timedelta(days=42) <= date.fromisoformat(p["date"]) < latest_day]
    if len(window) < 3:
        return None
    mean = float(np.mean(window))
    sd = float(np.std(window, ddof=1)) if len(window) > 1 else 0.0
    if mean == 0:
        return None
    pct = (latest["value"] - mean) / abs(mean) * 100.0
    z = (latest["value"] - mean) / sd if sd > 0 else 0.0
    # Smallest worthwhile change: half an SD (Hopkins).
    swc = 0.5 * sd if sd > 0 else None
    return {"baseline_mean": round(mean, 2), "baseline_sd": round(sd, 2), "pct": round(pct, 1),
            "z": round(z, 2), "swc": round(swc, 2) if swc is not None else None, "n": len(window)}


def test_card(spec: TestSpec, rows: list[SportsTest], data: SportsData, level: str | None,
              sex: str | None) -> dict[str, Any] | None:
    if not rows:
        return None
    card: dict[str, Any] = {
        "key": spec.key, "label": spec.label, "category": spec.category, "unit": spec.unit,
        "higher_is_better": spec.higher_is_better, "sided": spec.sided, "decimals": spec.decimals,
        "core": spec.core, "phone": spec.phone,
    }
    if spec.sided:
        left = _series(rows, "left")
        right = _series(rows, "right")
        both = _series(rows, None)
        latest_l = left[-1]["value"] if left else None
        latest_r = right[-1]["value"] if right else None
        headline_value = None
        if latest_l is not None and latest_r is not None:
            headline_value = (max if spec.higher_is_better else min)(latest_l, latest_r)
        elif both:
            headline_value = both[-1]["value"]
        else:
            headline_value = latest_l if latest_l is not None else latest_r
        card["left"] = {"latest": latest_l, "series": left[-14:]}
        card["right"] = {"latest": latest_r, "series": right[-14:]}
        asym = _asymmetry(latest_l, latest_r, spec.higher_is_better)
        card["asymmetry"] = asym
        if asym and spec.asymmetry_flag_pct is not None:
            card["asymmetry_status"] = ("flag" if asym["pct"] >= spec.asymmetry_flag_pct * 1.5
                                        else "watch" if asym["pct"] >= spec.asymmetry_flag_pct else "ok")
        combined = sorted(left + right + both, key=lambda p: p["date"])
        series = both if both else combined
        latest_date = max((r.date for r in rows), default=None)
    else:
        series = _series(rows, None) or _series(rows, "left") + _series(rows, "right")
        series = sorted(series, key=lambda p: p["date"])
        headline_value = series[-1]["value"] if series else None
        latest_date = date.fromisoformat(series[-1]["date"]) if series else None
    if headline_value is None:
        return None
    values = [p["value"] for p in series]
    best = _best(values, spec.higher_is_better)
    card["latest"] = round(float(headline_value), 3)
    card["latest_text"] = _fmt(float(headline_value), spec.decimals)
    card["latest_date"] = latest_date.isoformat() if latest_date else None
    card["days_ago"] = (data.today - latest_date).days if latest_date else None
    card["best"] = round(float(best), 3) if best is not None else None
    card["best_text"] = _fmt(float(best), spec.decimals) if best is not None else None
    card["is_best"] = best is not None and math.isclose(float(headline_value), float(best), rel_tol=1e-6)
    card["series"] = series[-20:]
    card["count"] = len(series)
    card["trend"] = _trend(series, spec.higher_is_better)
    card["baseline"] = _baseline_z(series, data.today)
    card["band"] = band_for(spec, float(headline_value), level, sex)
    card["source"] = rows[-1].source
    card["device"] = rows[-1].device
    return card


def neuromuscular_read(cards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The countermovement jump against the athlete's own baseline: the
    weekly readiness test every force-plate program runs."""
    cmj = cards.get("cmj_height") or cards.get("phone_jump_height")
    rsi = cards.get("cmj_rsi_mod")
    tto = cards.get("cmj_time_to_takeoff")
    out: dict[str, Any] = {"status": "nodata", "status_text": "No jump on file", "finding":
                           "Log a countermovement jump (force plate, or the phone's jump test) and the "
                           "weekly neuromuscular read sits here.", "signals": [], "source": None}
    if cmj is None:
        return out
    out["source"] = "phone" if cmj["key"] == "phone_jump_height" else "force_plate"
    signals = []
    status = "ok"
    base = cmj.get("baseline")
    parts = []
    if base:
        drop = -base["pct"]
        signals.append({"label": "Jump height", "pct": base["pct"], "value": cmj["latest_text"] + " " + cmj["unit"],
                        "baseline": _fmt(base["baseline_mean"], cmj["decimals"])})
        if drop >= CMJ_DROP_FLAG:
            status = "flag"
            parts.append(f"Jump height is {drop:.0f}% under your 6-week baseline ({cmj['latest_text']} vs "
                         f"{_fmt(base['baseline_mean'], 1)} cm).")
        elif drop >= CMJ_DROP_WATCH:
            status = "watch"
            parts.append(f"Jump height is {drop:.0f}% under your baseline.")
        elif base["pct"] >= CMJ_DROP_WATCH:
            parts.append(f"Jump height is {base['pct']:.0f}% above your baseline: fresh.")
    else:
        parts.append(f"Latest jump {cmj['latest_text']} {cmj['unit']}; a baseline needs three more tests.")
    if rsi and rsi.get("baseline"):
        b = rsi["baseline"]
        signals.append({"label": "RSI-modified", "pct": b["pct"], "value": rsi["latest_text"],
                        "baseline": _fmt(b["baseline_mean"], 2)})
        if -b["pct"] >= CMJ_DROP_FLAG and status != "flag":
            status = "flag"
            parts.append(f"RSI-modified is {-b['pct']:.0f}% down, which is the most fatigue-sensitive jump variable.")
        elif -b["pct"] >= CMJ_DROP_WATCH and status == "ok":
            status = "watch"
            parts.append(f"RSI-modified is {-b['pct']:.0f}% down.")
    if tto and tto.get("baseline"):
        b = tto["baseline"]
        signals.append({"label": "Time to takeoff", "pct": b["pct"], "value": tto["latest_text"] + " ms",
                        "baseline": _fmt(b["baseline_mean"], 0)})
        if b["pct"] >= TTO_RISE_FLAG:
            if status == "ok":
                status = "watch"
            parts.append(f"Time to takeoff is {b['pct']:.0f}% longer: the same jump is costing more, "
                         "which is fatigue before height falls.")
    if cmj.get("days_ago") is not None and cmj["days_ago"] > 10:
        parts.append(f"Last jump {cmj['days_ago']} days ago; a weekly test keeps this read current.")
    out.update({
        "status": status,
        "status_text": {"ok": "Fresh", "watch": "Slightly down", "flag": "Fatigued"}[status],
        "finding": " ".join(parts), "signals": signals,
        "latest_date": cmj.get("latest_date"),
    })
    return out


def compute_performance(data: SportsData, sex: str | None) -> dict[str, Any]:
    profile = data.profile
    level = profile.level
    by_key: dict[str, list[SportsTest]] = {}
    for t in data.tests:
        by_key.setdefault(t.test_key, []).append(t)
    cards: dict[str, dict[str, Any]] = {}
    for key, rows in by_key.items():
        spec = TESTS.get(key)
        if spec is None:
            continue
        card = test_card(spec, rows, data, level, sex)
        if card:
            cards[key] = card
    categories = []
    for cat in CATEGORIES:
        items = [c for c in cards.values() if c["category"] == cat["key"]]
        items.sort(key=lambda c: (not c["core"], c["label"]))
        available = [t for t in tests_for(profile.sport) if t.category == cat["key"] and t.key not in cards]
        categories.append({
            **cat, "cards": items,
            "available": [{"key": t.key, "label": t.label, "unit": t.unit, "core": t.core,
                           "phone": t.phone, "sided": t.sided} for t in available],
        })
    # The headline strip: the core tests this sport leads with, logged or not.
    core = [t for t in tests_for(profile.sport, core_only=True)]
    headline = []
    for t in core:
        c = cards.get(t.key)
        headline.append({"key": t.key, "label": t.label, "unit": t.unit, "logged": c is not None,
                         "latest_text": c["latest_text"] if c else None,
                         "band": c["band"] if c else None, "trend": c["trend"] if c else None,
                         "days_ago": c["days_ago"] if c else None, "phone": t.phone, "sided": t.sided})
    asymmetries = [
        {"key": c["key"], "label": c["label"], "asymmetry": c["asymmetry"], "status": c.get("asymmetry_status", "ok")}
        for c in cards.values() if c.get("asymmetry") and c.get("asymmetry_status") in ("watch", "flag")
    ]
    bests = sorted([c for c in cards.values() if c["is_best"] and c["count"] >= 2],
                   key=lambda c: c["latest_date"] or "", reverse=True)[:5]
    percentiles = [c["band"]["percentile"] for c in cards.values() if c.get("band") and c["core"]]
    overall = round(float(np.mean(percentiles))) if percentiles else None
    return {
        "as_of": data.today.isoformat(),
        "sport": profile.sport, "level": level, "sex": sex,
        "logged": len(cards), "available": len(tests_for(profile.sport)),
        "overall_percentile": overall,
        "neuromuscular": neuromuscular_read(cards),
        "asymmetries": asymmetries,
        "recent_bests": [{"key": c["key"], "label": c["label"], "latest_text": c["latest_text"], "unit": c["unit"],
                          "date": c["latest_date"]} for c in bests],
        "headline": headline,
        "categories": categories,
        "cards": cards,
        "jumps": _jump_load(data),
    }


def _jump_load(data: SportsData) -> dict[str, Any] | None:
    series = data.jumps_series()
    if len(series) == 0:
        return None
    recent = series[series.index > data.today - timedelta(days=7)]
    chronic = series[series.index > data.today - timedelta(days=28)]
    week = float(recent.sum())
    prior = series[(series.index > data.today - timedelta(days=14)) & (series.index <= data.today - timedelta(days=7))]
    prior_week = float(prior.sum()) if len(prior) else None
    mean_session = float(chronic[chronic > 0].mean()) if (chronic > 0).any() else None
    sd_session = float(chronic[chronic > 0].std(ddof=1)) if (chronic > 0).sum() > 2 else None
    today_jumps = float(series.iloc[-1]) if series.index[-1] == data.today else 0.0
    status = "ok"
    text = "Within your usual week."
    change = None
    if prior_week and prior_week > 0:
        change = (week - prior_week) / prior_week * 100.0
        if change >= 15:
            status, text = "watch", f"Jumps up {change:.0f}% on last week: keep the next days flat."
    if mean_session and sd_session and today_jumps > mean_session + sd_session:
        status = "flag" if status == "watch" else "watch"
        text = f"Today's {today_jumps:.0f} jumps are above your usual session by more than one SD."
    return {"week": round(week), "prior_week": round(prior_week) if prior_week is not None else None,
            "change_pct": round(change, 1) if change is not None else None, "today": round(today_jumps),
            "mean_session": round(mean_session) if mean_session else None, "status": status, "text": text,
            "series": [{"date": d.isoformat(), "value": float(v)} for d, v in series.tail(28).items()]}
