"""The athlete's readouts: readiness, HRV, resting heart rate, sleep,
training load, fitness, body signals, rhythm, activity and a verdict for
the day — computed from the same wearable stream the clinic engine scores,
in the vocabulary a serious runner, lifter or coach already uses.

Design rules, in order of importance:

* **Personal, never population.** Every score is a comparison with the
  person's own trailing baseline (28 days, ending yesterday). The only
  population table is the coarse VO2 max band, and it says so.
* **Say the method.** Each panel carries a one-line ``method`` so a reader
  who knows the literature can see exactly what was computed: ln-RMSSD
  seven-day means, the smallest worthwhile change, EWMA acute:chronic
  ratios, Banister fitness/fatigue, Foster monotony and strain.
* **Confidence travels with the number.** Fewer than five baseline days,
  a missing signal, a stale reading: the panel says so rather than
  inventing a verdict.
* **No medicine.** Nothing here names a condition. A body under stress is
  "signals consistent with strain"; the verdict is about training and
  sleep, and the guardrail sentence is added by the caller.

Everything is a pure function of ``PersonalData`` and a profile, so the
dashboard can be recomputed for any day and unit-tested by hand.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.engine.care.stats import interdaily_stability, ols_slope_t
from app.models.enums import MetricType as M
from app.personal.data import PersonalData

BASELINE_DAYS = 28
BASELINE_MIN = 5
RECENT_DAYS = 7
SERIES_DAYS = 28
STALE_AFTER_DAYS = 3

# Physiological floors for a baseline SD (a quiet fortnight understates
# real day-to-day variability). ln(HRV) floor of 0.08 is ~8 % of the mean.
SD_FLOORS = {
    "ln_hrv": 0.08, str(M.RESTING_HR): 1.5, str(M.RESPIRATORY_RATE): 0.6,
    str(M.SKIN_TEMP): 0.12, str(M.SKIN_TEMP_DELTA): 0.12, str(M.SPO2): 0.5,
    str(M.SLEEP_DURATION): 0.4,
}

READINESS_WEIGHTS = {"hrv": 0.40, "resting_hr": 0.25, "sleep": 0.25,
                     "respiratory_rate": 0.05, "temperature": 0.05}
READINESS_GREEN = 67.0
READINESS_AMBER = 34.0

ACWR_SPIKE = 1.5
ACWR_HIGH = 1.3
ACWR_LOW = 0.8
MONOTONY_HIGH = 2.0

SLEEP_NEED_DEFAULT = 7.5
SLEEP_DEBT_WATCH = 2.0
SLEEP_DEBT_FLAG = 4.0

# Coarse VO2 max bands (mL/kg/min) by sex and decade, the ACSM-style
# "fair / good / excellent" cut points. Deliberately coarse and labelled as
# such: the number that matters is the person's own trend.
VO2_BANDS = {
    "M": {20: (38, 44, 51), 30: (36, 42, 48), 40: (34, 39, 45), 50: (31, 36, 41),
          60: (28, 33, 38), 70: (26, 30, 35)},
    "F": {20: (32, 37, 44), 30: (30, 35, 41), 40: (28, 33, 38), 50: (26, 30, 35),
          60: (24, 28, 32), 70: (22, 26, 30)},
}


@dataclass
class Panel:
    key: str
    title: str
    status: str            # ok | watch | flag | nodata
    status_text: str
    headline: str          # the big figure, as text
    unit: str
    sub: str               # the line under it
    finding: str           # one or two sentences, what it means
    method: str            # how it was computed
    confidence: str        # high | med | low
    coverage: str
    series: list[dict[str, Any]]
    stats: list[dict[str, Any]]
    extra: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "title": self.title, "status": self.status,
            "status_text": self.status_text, "headline": self.headline, "unit": self.unit,
            "sub": self.sub, "finding": self.finding, "method": self.method,
            "confidence": self.confidence, "coverage": self.coverage,
            "series": self.series, "stats": self.stats, "extra": _clean(self.extra),
        }


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            return None
        return int(number) if isinstance(value, (int, np.integer)) else round(number, 3)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


# --- numerics ---------------------------------------------------------------------


def _grid(series: pd.Series, start: date, end: date) -> pd.Series:
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    return series.reindex(days).astype(float)


def _finite(values: pd.Series) -> pd.Series:
    return values[np.isfinite(values.values.astype(float))]


def _baseline(series: pd.Series, day: date, floor: float = 0.0,
              days: int = BASELINE_DAYS) -> tuple[float, float, int] | None:
    """(mean, sd, n) over the window ending the day before ``day``."""
    start = day - timedelta(days=days)
    window = series[[start <= d < day for d in series.index]]
    window = _finite(window)
    if len(window) < BASELINE_MIN:
        return None
    mean = float(window.mean())
    sd = float(window.std(ddof=1)) if len(window) > 1 else 0.0
    return mean, max(sd, floor, 1e-6), int(len(window))


def _recent_mean(series: pd.Series, day: date, days: int = RECENT_DAYS) -> float | None:
    start = day - timedelta(days=days - 1)
    window = _finite(series[[start <= d <= day for d in series.index]])
    return float(window.mean()) if len(window) else None


def _latest(series: pd.Series, day: date) -> tuple[date, float] | None:
    s = _finite(series[[d <= day for d in series.index]])
    if len(s) == 0:
        return None
    return s.index[-1], float(s.iloc[-1])


def _stale(latest_day: date | None, today: date) -> bool:
    return latest_day is None or (today - latest_day).days > STALE_AFTER_DAYS


def _ewma(values: np.ndarray, span_days: float) -> np.ndarray:
    lam = 2.0 / (span_days + 1.0)
    out = np.zeros_like(values, dtype=float)
    e = 0.0
    for i, v in enumerate(values):
        e = lam * float(v) + (1.0 - lam) * e
        out[i] = e
    return out


def _points(series: pd.Series, digits: int = 2) -> list[dict[str, Any]]:
    return [{"date": d.isoformat(), "value": round(float(v), digits)}
            for d, v in series.items() if v == v]


def _tail(series: pd.Series, today: date, days: int = SERIES_DAYS) -> pd.Series:
    start = today - timedelta(days=days - 1)
    return series[[start <= d <= today for d in series.index]]


def _confidence(n_baseline: int, recent_days: int) -> str:
    if n_baseline >= 14 and recent_days >= 5:
        return "high"
    if n_baseline >= BASELINE_MIN and recent_days >= 3:
        return "med"
    return "low"


def _fmt(value: float | None, digits: int = 0) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{value:,.{digits}f}"


def _signed(value: float, digits: int = 0, unit: str = "") -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}{abs(value):,.{digits}f}{unit}"


def _hours(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    minutes = int(round(value * 60))
    return f"{minutes // 60} h {minutes % 60:02d} min"


def _nodata(key: str, title: str, unit: str, why: str, method: str) -> Panel:
    return Panel(key, title, "nodata", "No data yet", "—", unit, "", why, method, "low",
                 "0 days", [], [], {})


# --- the readiness score -----------------------------------------------------------


def _hrv_key(data: PersonalData) -> str | None:
    for key in (str(M.HRV_RMSSD), str(M.HRV_SDNN)):
        if key in data.series and len(_finite(data.series[key])) >= 3:
            return key
    return None


def _temp_key(data: PersonalData) -> str | None:
    for key in (str(M.SKIN_TEMP_DELTA), str(M.SKIN_TEMP)):
        if key in data.series and len(_finite(data.series[key])) >= 3:
            return key
    return None


def _sleep_need_for(data: PersonalData, day: date, target: float | None,
                    load_z: float | None) -> float:
    """Personal sleep need: the person's own 28-night median (or their
    target), plus up to an hour after a heavy day, plus a slice of the debt."""
    nights = data.get(str(M.SLEEP_DURATION))
    base = _baseline(nights[nights >= 3.0] if len(nights) else nights, day,
                     floor=SD_FLOORS[str(M.SLEEP_DURATION)])
    need = target if target else (
        float(np.median(_finite(nights[[day - timedelta(days=28) <= d < day
                                         for d in nights.index]])))
        if base is not None else SLEEP_NEED_DEFAULT
    )
    need = float(min(10.0, max(6.0, need)))
    if load_z is not None and load_z > 0:
        need += min(1.0, 0.5 * load_z)
    return need


def _readiness_day(data: PersonalData, day: date, hrv_key: str | None, temp_key: str | None,
                   need: float) -> tuple[float | None, list[dict[str, Any]]]:
    """The score for one day and the component rows behind it."""
    components: list[dict[str, Any]] = []
    weighted = 0.0
    weight_sum = 0.0

    def add(key: str, label: str, z: float | None, text: str, value: str) -> None:
        nonlocal weighted, weight_sum
        if z is None:
            components.append({"key": key, "label": label, "z": None, "weight": 0.0,
                               "value": value, "text": text})
            return
        z = float(max(-3.0, min(3.0, z)))
        w = READINESS_WEIGHTS[key]
        weighted += w * z
        weight_sum += w
        components.append({"key": key, "label": label, "z": round(z, 2), "weight": w,
                           "value": value, "text": text})

    # HRV: ln-transformed, above baseline is good.
    if hrv_key:
        s = data.get(hrv_key)
        latest = _latest(s, day)
        base = _baseline(np.log(s[s > 0]), day, floor=SD_FLOORS["ln_hrv"])
        if latest and base and latest[0] == day and latest[1] > 0:
            z = (math.log(latest[1]) - base[0]) / base[1]
            add("hrv", "HRV", z, "vs your 28-day ln-HRV baseline", f"{latest[1]:.0f} ms")
        else:
            add("hrv", "HRV", None, "no reading today", "—")
    else:
        add("hrv", "HRV", None, "no HRV from your device", "—")

    # Resting HR: below baseline is good.
    s = data.get(str(M.RESTING_HR))
    latest = _latest(s, day)
    base = _baseline(s, day, floor=SD_FLOORS[str(M.RESTING_HR)])
    if latest and base and latest[0] == day:
        z = -(latest[1] - base[0]) / base[1]
        add("resting_hr", "Resting HR", z, "vs your 28-day baseline", f"{latest[1]:.0f} bpm")
    else:
        add("resting_hr", "Resting HR", None, "no reading today", "—")

    # Sleep: performance against need. 85 % of need reads as one SD short.
    nights = data.get(str(M.SLEEP_DURATION))
    got = nights.get(day)
    if got is not None and got == got and need > 0:
        perf = min(1.2, float(got) / need)
        add("sleep", "Sleep", (perf - 1.0) / 0.15, f"{perf * 100:.0f}% of your {need:.1f} h need",
            _hours(float(got)))
    else:
        add("sleep", "Sleep", None, "no sleep recorded last night", "—")

    # Respiratory rate and temperature only ever subtract: a deviation past
    # one SD in the adverse direction costs, a normal reading is neutral.
    s = data.get(str(M.RESPIRATORY_RATE))
    latest = _latest(s, day)
    base = _baseline(s, day, floor=SD_FLOORS[str(M.RESPIRATORY_RATE)])
    if latest and base and latest[0] == day:
        z = (latest[1] - base[0]) / base[1]
        add("respiratory_rate", "Breathing rate", -max(0.0, z - 1.0),
            "penalised only above baseline", f"{latest[1]:.1f} br/min")
    if temp_key:
        s = data.get(temp_key)
        latest = _latest(s, day)
        base = _baseline(s, day, floor=SD_FLOORS[temp_key])
        if latest and base and latest[0] == day:
            z = (latest[1] - base[0]) / base[1]
            add("temperature", "Skin temperature", -max(0.0, z - 1.0),
                "penalised only above baseline", f"{_signed(latest[1], 1)} °C"
                if temp_key == str(M.SKIN_TEMP_DELTA) else f"{latest[1]:.1f} °C")

    core = {c["key"] for c in components if c["z"] is not None} & {"hrv", "resting_hr", "sleep"}
    if not core or weight_sum <= 0:
        return None, components
    zc = weighted / weight_sum
    # ln(67/33) ≈ 0.71: one SD off your normal, taken together, is exactly the
    # edge of the green or red band; two SD is a 19 or an 81.
    score = 100.0 / (1.0 + math.exp(-0.71 * zc))
    for c in components:
        if c["z"] is not None:
            c["contribution"] = round(c["weight"] * c["z"] / weight_sum, 3)
    return round(score, 1), components


def readiness_panel(data: PersonalData, profile: Any, load_z_yesterday: float | None) -> Panel:
    today = data.today
    hrv_key, temp_key = _hrv_key(data), _temp_key(data)
    target = getattr(profile, "sleep_target_hours", None)
    need = _sleep_need_for(data, today, target, load_z_yesterday)
    score, components = _readiness_day(data, today, hrv_key, temp_key, need)
    # The history: each day judged against its own trailing baseline.
    series = []
    for i in range(SERIES_DAYS - 1, -1, -1):
        day = today - timedelta(days=i)
        s, _ = _readiness_day(data, day, hrv_key, temp_key,
                              _sleep_need_for(data, day, target, None))
        if s is not None:
            series.append({"date": day.isoformat(), "value": s})
    method = ("Weighted z-scores against your own 28-day baselines (ln-HRV 40 %, resting HR 25 %, "
              "sleep vs need 25 %, breathing rate and skin temperature 5 % each), mapped to "
              "0–100 with a logistic curve. 50 is your normal; one SD off, taken together, is "
              "the edge of the green or red band.")
    if score is None:
        yesterday = series[-1] if series else None
        why = ("Readiness needs today's HRV or resting heart rate and last night's sleep. "
               "Wear your watch overnight and sync in the morning.")
        panel = _nodata("readiness", "Readiness", "", why, method)
        panel.series = series
        panel.extra = {"components": components, "yesterday": yesterday}
        panel.coverage = f"{len(series)} of {SERIES_DAYS} days scored"
        return panel
    band = "green" if score >= READINESS_GREEN else "amber" if score >= READINESS_AMBER else "red"
    label = {"green": "Primed", "amber": "Steady", "red": "Run down"}[band]
    week = [p["value"] for p in series[-7:]]
    week_mean = float(np.mean(week)) if week else None
    top = sorted((c for c in components if c.get("contribution") is not None),
                 key=lambda c: c["contribution"])
    dragging = [c for c in top if c["contribution"] < -0.1]
    lifting = [c for c in reversed(top) if c["contribution"] > 0.1]
    spoken = {"HRV": "HRV", "Resting HR": "resting heart rate", "Sleep": "sleep",
              "Breathing rate": "breathing rate", "Skin temperature": "skin temperature"}
    parts = []
    if dragging:
        parts.append("Pulled down by "
                     + " and ".join(spoken.get(c["label"], c["label"]) for c in dragging[:2]))
    if lifting:
        parts.append(("lifted" if parts else "Lifted") + " by "
                     + " and ".join(spoken.get(c["label"], c["label"]) for c in lifting[:2]))
    finding = (", ".join(parts) + "." if parts else "Every signal is close to your normal.")
    if week_mean is not None:
        finding += f" Seven-day average {week_mean:.0f}."
    status = "ok" if band == "green" else "watch" if band == "amber" else "flag"
    return Panel(
        "readiness", "Readiness", status, label, f"{score:.0f}", "", finding.split(".")[0] + ".",
        finding, method, _confidence(len(series), min(7, len(week))),
        f"{len(series)} of {SERIES_DAYS} days scored",
        series,
        [{"label": "7-day avg", "value": _fmt(week_mean), "unit": ""},
         {"label": "Sleep need", "value": f"{need:.1f}", "unit": "h"}],
        {"band": band, "components": components, "score": score, "need_hours": need},
    )


# --- HRV ---------------------------------------------------------------------------


def hrv_panel(data: PersonalData) -> Panel:
    today = data.today
    key = _hrv_key(data)
    method = ("Nightly HRV, ln-transformed for the seven-day mean and the 28-day baseline; the "
              "smallest worthwhile change is half the baseline SD; balance is the 7-day mean "
              "over the 28-day mean; trend is the OLS slope over 14 days.")
    if key is None:
        return _nodata("hrv", "HRV", "ms",
                       "HRV needs a device worn overnight (Apple Watch, Oura, WHOOP, Garmin).",
                       method)
    s = _finite(data.get(key))
    label = "RMSSD" if key == str(M.HRV_RMSSD) else "SDNN"
    latest = _latest(s, today)
    ln = np.log(s[s > 0])
    base = _baseline(ln, today, floor=SD_FLOORS["ln_hrv"])
    raw_base = _baseline(s, today)
    recent_ln = _recent_mean(ln, today)
    recent = _recent_mean(s, today)
    stats: list[dict[str, Any]] = []
    extra: dict[str, Any] = {"statistic": label}
    if latest is None:
        return _nodata("hrv", "HRV", "ms", "No HRV in the last 90 days.", method)
    stale = _stale(latest[0], today)
    sub = f"Latest {latest[1]:.0f} ms ({latest[0].strftime('%b %-d')})"
    status, status_text = "ok", "In your range"
    finding = ""
    if base is not None and recent_ln is not None and raw_base is not None:
        swc = 0.5 * base[1]
        lo, hi = math.exp(base[0] - swc), math.exp(base[0] + swc)
        balance = math.exp(recent_ln) / math.exp(base[0])
        cv = None
        recent_raw = s[[today - timedelta(days=6) <= d <= today for d in s.index]]
        if len(recent_raw) >= 3 and recent_raw.mean() > 0:
            cv = float(recent_raw.std(ddof=1) / recent_raw.mean() * 100)
        z_latest = (math.log(latest[1]) - base[0]) / base[1] if latest[1] > 0 else 0.0
        window = _tail(s, today, 14)
        slope, t = ols_slope_t([(d - today).days for d in window.index], window.values) \
            if len(window) >= 5 else (0.0, 0.0)
        extra.update({"swc_low": lo, "swc_high": hi, "balance": balance, "cv_pct": cv,
                      "z_latest": z_latest, "slope_ms_per_day": slope, "slope_t": t,
                      "baseline_mean": raw_base[0], "baseline_sd": raw_base[1],
                      "ln_mean_7d": recent_ln, "latest": latest[1]})
        stats = [
            {"label": "7-day", "value": _fmt(recent), "unit": "ms"},
            {"label": "Baseline", "value": f"{raw_base[0]:.0f} ± {raw_base[1]:.0f}", "unit": "ms"},
            {"label": "Balance", "value": f"{balance:.2f}", "unit": ""},
        ]
        if cv is not None:
            stats.append({"label": "CV (7d)", "value": f"{cv:.0f}", "unit": "%"})
        below = recent_ln < base[0] - swc
        above = recent_ln > base[0] + swc
        if below and z_latest < -1.0:
            status, status_text = "flag", "Suppressed"
            finding = (f"Your seven-day HRV sits below your normal range ({lo:.0f}–{hi:.0f} ms) "
                       f"and last night was {abs(z_latest):.1f} SD under baseline. That pattern "
                       "usually follows a hard block, short sleep, alcohol or an oncoming bug.")
        elif below:
            status, status_text = "watch", "Below range"
            finding = (f"Seven-day HRV is under your smallest worthwhile change band "
                       f"({lo:.0f}–{hi:.0f} ms). One night is noise; a week is a signal to "
                       "watch load and sleep.")
        elif above:
            status, status_text = "ok", "Above range"
            finding = (f"Seven-day HRV is above your usual band ({lo:.0f}–{hi:.0f} ms), which "
                       "is what a good adaptation week looks like.")
        else:
            finding = (f"Seven-day HRV is inside your usual band ({lo:.0f}–{hi:.0f} ms). "
                       f"Balance {balance:.2f}: right on your baseline.")
        if latest[0] == today and z_latest <= -1.5 and not below:
            # One bad night inside a fine week is worth a sentence, not a
            # status: the weekly mean is the signal, the night is the news.
            status, status_text = ("watch", "Low last night") if status == "ok" else (status, status_text)
            finding += (f" Last night was low on its own: {latest[1]:.0f} ms, "
                        f"{abs(z_latest):.1f} SD under your baseline.")
        if cv is not None and cv > 15:
            finding += f" Day-to-day variation is high (CV {cv:.0f} %), so read the weekly mean, not one night."
        if abs(t) >= 2.5:
            finding += (f" Trend over 14 days: {_signed(slope * 7, 1)} ms per week"
                        f" ({'rising' if slope > 0 else 'falling'}).")
    else:
        finding = (f"{base[2] if base else len(s)} nights so far. A personal baseline needs "
                   f"{BASELINE_MIN} nights; the range and balance appear after that.")
        status, status_text = "nodata" if len(s) < BASELINE_MIN else "ok", "Learning your baseline"
        stats = [{"label": "7-day", "value": _fmt(recent), "unit": "ms"}]
    if stale:
        status, status_text = "nodata", "No recent reading"
        finding = f"Last HRV reading was {(today - latest[0]).days} days ago. " + finding
    series = _points(_tail(s, today), 0)
    return Panel("hrv", f"HRV ({label})", status, status_text, f"{recent:.0f}" if recent else
                 f"{latest[1]:.0f}", "ms", sub, finding, method,
                 _confidence(base[2] if base else 0, len(_tail(s, today, 7))),
                 f"{len(_tail(s, today, 7))} of 7 nights", series, stats, extra)


# --- resting heart rate --------------------------------------------------------------


def resting_hr_panel(data: PersonalData) -> Panel:
    today = data.today
    method = ("Nightly resting heart rate against your own 28-day baseline; the seven-day mean "
              "is compared to the baseline mean and SD.")
    s = _finite(data.get(str(M.RESTING_HR)))
    latest = _latest(s, today)
    if latest is None:
        return _nodata("resting_hr", "Resting heart rate", "bpm",
                       "Resting heart rate arrives from a watch or ring worn overnight.", method)
    base = _baseline(s, today, floor=SD_FLOORS[str(M.RESTING_HR)])
    recent = _recent_mean(s, today)
    status, status_text, finding = "ok", "Normal for you", ""
    stats: list[dict[str, Any]] = [{"label": "Latest", "value": f"{latest[1]:.0f}", "unit": "bpm"}]
    extra: dict[str, Any] = {}
    if base is not None and recent is not None:
        delta = recent - base[0]
        z_latest = (latest[1] - base[0]) / base[1]
        window = _tail(s, today, 14)
        slope, t = ols_slope_t([(d - today).days for d in window.index], window.values) \
            if len(window) >= 5 else (0.0, 0.0)
        stats += [{"label": "7-day", "value": f"{recent:.0f}", "unit": "bpm"},
                  {"label": "Baseline", "value": f"{base[0]:.0f} ± {base[1]:.0f}", "unit": "bpm"},
                  {"label": "Δ 7d", "value": _signed(delta, 1), "unit": "bpm"}]
        extra.update({"baseline_mean": base[0], "baseline_sd": base[1], "delta_7d": delta,
                      "z_latest": z_latest, "slope_bpm_per_day": slope, "slope_t": t,
                      "latest": latest[1], "latest_is_last_night": latest[0] == today})
        if delta >= max(4.0, 1.5 * base[1]):
            status, status_text = "flag", "Elevated all week"
            finding = (f"Resting heart rate is running {_signed(delta, 1)} bpm over your baseline "
                       f"({base[0]:.0f}) across the week. A sustained rise like this is the "
                       "clearest sign of accumulated fatigue, dehydration or an oncoming illness.")
        elif latest[0] == today and z_latest >= 2.0:
            status, status_text = "flag", "Elevated last night"
            finding = (f"Last night's resting heart rate was {latest[1]:.0f} bpm, "
                       f"{_signed(latest[1] - base[0], 0)} over your baseline of {base[0]:.0f}: the "
                       "clearest overnight sign of fatigue, dehydration or an oncoming illness. "
                       f"The seven-day mean is {recent:.0f}.")
        elif delta >= max(2.0, base[1]) or (latest[0] == today and z_latest >= 1.5):
            status, status_text = "watch", "A little high"
            finding = (f"Seven-day resting heart rate is {_signed(delta, 1)} bpm above baseline"
                       + (f"; last night {latest[1]:.0f}." if latest[0] == today else ".")
                       + " Worth an easier day if it holds.")
        elif delta <= -max(2.0, base[1]):
            finding = (f"Resting heart rate is {_signed(delta, 1)} bpm under your baseline, "
                       "the direction fitness moves it.")
        else:
            finding = f"Steady at your baseline of {base[0]:.0f} bpm."
        if abs(t) >= 2.5:
            finding += f" Fourteen-day trend {_signed(slope * 7, 1)} bpm per week."
    else:
        finding = f"{len(s)} nights so far; a baseline needs {BASELINE_MIN}."
        status, status_text = ("nodata" if len(s) < BASELINE_MIN else "ok"), "Learning your baseline"
    if _stale(latest[0], today):
        status, status_text = "nodata", "No recent reading"
    # Last night is the headline when it is the story; otherwise the week.
    headline = latest[1] if (latest[0] == today and status_text == "Elevated last night") or not recent \
        else recent
    return Panel("resting_hr", "Resting heart rate", status, status_text,
                 f"{headline:.0f}", "bpm",
                 f"Latest {latest[1]:.0f} bpm ({latest[0].strftime('%b %-d')})", finding, method,
                 _confidence(base[2] if base else 0, len(_tail(s, today, 7))),
                 f"{len(_tail(s, today, 7))} of 7 nights", _points(_tail(s, today), 0), stats, extra)


# --- sleep ---------------------------------------------------------------------------


def _circular_sd_minutes(stamps: list[datetime]) -> float | None:
    """SD of clock times in minutes, computed on the circle so 23:30 and
    00:30 are an hour apart, not 23."""
    if len(stamps) < 3:
        return None
    angles = np.array([(t.hour * 60 + t.minute) / 1440.0 * 2 * math.pi for t in stamps])
    c, s = np.cos(angles).mean(), np.sin(angles).mean()
    r = min(1.0, math.hypot(c, s))
    if r <= 1e-9:
        return 720.0
    # Identical stamps give r a hair over 1 in floating point; clamp before the log.
    return float(math.sqrt(max(0.0, -2 * math.log(r))) / (2 * math.pi) * 1440)


def _mean_clock(stamps: list[datetime]) -> str | None:
    if not stamps:
        return None
    angles = np.array([(t.hour * 60 + t.minute) / 1440.0 * 2 * math.pi for t in stamps])
    mean = math.atan2(np.sin(angles).mean(), np.cos(angles).mean()) % (2 * math.pi)
    minutes = int(round(mean / (2 * math.pi) * 1440)) % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def sleep_panel(data: PersonalData, profile: Any, load_z_yesterday: float | None) -> Panel:
    today = data.today
    method = ("Sleep need is your 28-night median (or your target) plus up to an hour after a "
              "heavy day. Debt is the last seven nights' shortfall against need, older nights "
              "discounted 15 % a night. Consistency is the circular SD of bedtime and wake "
              "time over 14 nights; efficiency is time asleep over time in bed.")
    nights = _finite(data.get(str(M.SLEEP_DURATION)))
    if len(nights) == 0:
        return _nodata("sleep", "Sleep", "h",
                       "Sleep arrives from a watch or ring worn overnight, or from Health.",
                       method)
    target = getattr(profile, "sleep_target_hours", None)
    need = _sleep_need_for(data, today, target, load_z_yesterday)
    last = _latest(nights, today)
    got_last = last[1] if last and last[0] == today else None
    debt = 0.0
    for i in range(1, 8):
        day = today - timedelta(days=i - 1)
        got = nights.get(day)
        if got is None or got != got:
            continue
        shortfall = max(0.0, _sleep_need_for(data, day, target, None) - float(got))
        debt += shortfall * (0.85 ** (i - 1))
    debt = min(8.0, debt)
    recent = _recent_mean(nights, today)
    base = _baseline(nights, today, floor=SD_FLOORS[str(M.SLEEP_DURATION)])
    detail = data.sleep
    bedtimes = [b for b in detail["bedtime"].tolist() if isinstance(b, datetime)] \
        if len(detail) else []
    waketimes = [w for w in detail["waketime"].tolist() if isinstance(w, datetime)] \
        if len(detail) else []
    recent_detail = detail[detail["date"] >= today - timedelta(days=13)] if len(detail) else detail
    bed_sd = _circular_sd_minutes([b for b in recent_detail["bedtime"].tolist()
                                   if isinstance(b, datetime)]) if len(recent_detail) else None
    wake_sd = _circular_sd_minutes([w for w in recent_detail["waketime"].tolist()
                                    if isinstance(w, datetime)]) if len(recent_detail) else None
    efficiency = None
    deep_pct = rem_pct = None
    if len(recent_detail):
        eff = recent_detail["efficiency"].dropna()
        efficiency = float(eff.mean()) if len(eff) else None
        tot = recent_detail["total_h"]
        deep = (recent_detail["deep_h"] / tot).dropna()
        rem = (recent_detail["rem_h"] / tot).dropna()
        deep_pct = float(deep.mean() * 100) if len(deep) else None
        rem_pct = float(rem.mean() * 100) if len(rem) else None
    perf = (got_last / need) if got_last else None
    status, status_text = "ok", "Rested"
    if debt >= SLEEP_DEBT_FLAG:
        status, status_text = "flag", f"{debt:.1f} h in debt"
    elif debt >= SLEEP_DEBT_WATCH or (perf is not None and perf < 0.75):
        status, status_text = "watch", f"{debt:.1f} h in debt" if debt >= SLEEP_DEBT_WATCH \
            else "Short night"
    parts = []
    if got_last is not None:
        parts.append(f"Last night {_hours(got_last)} against a need of {need:.1f} h "
                     f"({perf * 100:.0f}%).")
    else:
        parts.append(f"No sleep recorded for last night; your need today is about {need:.1f} h.")
    if debt >= SLEEP_DEBT_WATCH:
        parts.append(f"You are carrying {debt:.1f} h of debt over the week; an early night "
                     "clears most of it.")
    elif recent is not None:
        parts.append(f"Seven-night average {_hours(recent)}.")
    if bed_sd is not None:
        word = "regular" if bed_sd < 30 else "variable" if bed_sd < 60 else "irregular"
        parts.append(f"Bedtime is {word} (±{bed_sd:.0f} min).")
    if efficiency is not None and efficiency < 0.85:
        parts.append(f"Efficiency {efficiency * 100:.0f}%: a fair amount of the night awake.")
    stats = [
        {"label": "Need", "value": f"{need:.1f}", "unit": "h"},
        {"label": "Debt", "value": f"{debt:.1f}", "unit": "h"},
        {"label": "7-night", "value": _hours(recent), "unit": ""},
    ]
    if efficiency is not None:
        stats.append({"label": "Efficiency", "value": f"{efficiency * 100:.0f}", "unit": "%"})
    extra = {
        "need_hours": need, "debt_hours": debt, "performance": perf, "last_night_hours": got_last,
        "baseline_mean": base[0] if base else None, "bedtime_sd_min": bed_sd,
        "waketime_sd_min": wake_sd, "mean_bedtime": _mean_clock(bedtimes[-14:]),
        "mean_waketime": _mean_clock(waketimes[-14:]), "efficiency": efficiency,
        "deep_pct": deep_pct, "rem_pct": rem_pct,
        "target_hours": target,
    }
    series = _points(_tail(nights, today), 2)
    return Panel("sleep", "Sleep", status, status_text,
                 _hours(got_last) if got_last is not None else _hours(recent), "",
                 f"Need {need:.1f} h{' · debt ' + f'{debt:.1f} h' if debt >= 0.5 else ''}",
                 " ".join(parts), method,
                 _confidence(base[2] if base else 0, len(_tail(nights, today, 7))),
                 f"{len(_tail(nights, today, 7))} of 7 nights", series, stats, extra)


# --- training load ----------------------------------------------------------------


SRPE_MIN_SESSIONS = 5


def _srpe_series(data: PersonalData) -> pd.Series:
    """Session RPE load (Foster): minutes × RPE, from the sessions the person
    logs. Zero on a day with no logged session inside the logging window,
    which is what makes it a training load rather than a wear-time proxy."""
    rpe = data.logs.get("rpe")
    minutes = data.logs.get("session_minutes")
    if rpe is None or minutes is None or len(rpe) == 0 or len(minutes) == 0:
        return pd.Series(dtype=float)
    days = sorted(set(rpe.index) & set(minutes.index))
    if not days:
        return pd.Series(dtype=float)
    values = pd.Series([float(rpe[d]) * float(minutes[d]) for d in days], index=days)
    # A logged day is a real day; the days between two logs are rest days.
    return _grid(values, days[0], data.today).fillna(0.0)


def _load_source(data: PersonalData) -> tuple[pd.Series | None, str, str]:
    """Session RPE first when the person logs sessions (the standard for
    athletes without a chest strap), else the device's own measures."""
    srpe = _srpe_series(data)
    logged = int((srpe > 0).sum()) if len(srpe) else 0
    if logged >= SRPE_MIN_SESSIONS and len(_tail(srpe, data.today, 28)) >= 14:
        return srpe, "AU", "session RPE"
    candidates = [
        (str(M.ACTIVE_ENERGY), "kcal", "active energy"),
        (str(M.EXERCISE_SESSION), "min", "exercise minutes"),
        (str(M.STEPS), "steps", "steps"),
    ]
    best: tuple[pd.Series | None, str, str] = (None, "", "")
    best_n = 0
    for key, unit, label in candidates:
        s = _finite(data.get(key))
        recent = _tail(s, data.today, 28)
        if len(recent) > best_n and len(recent) >= 3:
            best, best_n = (s, unit, label), len(recent)
    return best


def load_panel(data: PersonalData, profile: Any) -> Panel:
    today = data.today
    method = ("Daily load from active energy (else exercise minutes, else steps). Acute and "
              "chronic are exponentially weighted averages with 7- and 28-day spans; ACWR is "
              "their ratio. Fitness and fatigue follow Banister (42- and 7-day constants), "
              "form is fitness minus fatigue. Monotony is the 7-day mean over its SD of the "
              "load above your everyday floor (the 28-day 20th percentile); strain is that "
              "weekly load times monotony (Foster).")
    source, unit, label = _load_source(data)
    if source is None:
        return _nodata("load", "Training load", "", "Load needs active energy, workouts or "
                       "steps from your device.", method)
    start = today - timedelta(days=89)
    g = _grid(source, start, today).fillna(0.0)
    values = g.values.astype(float)
    acute = _ewma(values, 7)
    chronic = _ewma(values, 28)
    ctl = _ewma(values, 42)
    atl = _ewma(values, 7)
    tsb = ctl - atl
    # Yesterday's fitness/fatigue is what today's form is built on.
    form = float(ctl[-2] - atl[-2]) if len(values) > 1 else 0.0
    acwr = float(acute[-1] / chronic[-1]) if chronic[-1] > 0 else None
    week = values[-7:]
    # Monotony and strain on the TRAINING part of the load. Active energy
    # and steps carry a floor of ordinary living that never varies, which
    # made every week read as monotonous; the 28-day 20th percentile is
    # taken as that floor and subtracted first.
    floor = float(np.percentile(values[-28:], 20)) if len(values) >= 7 else 0.0
    training_week = np.clip(week - floor, 0.0, None)
    monotony = float(training_week.mean() / training_week.std(ddof=1)) \
        if len(training_week) > 2 and training_week.std(ddof=1) > 0 and training_week.mean() > 0 \
        else None
    strain = float(training_week.sum() * monotony) if monotony is not None else None
    today_load = float(values[-1])
    yesterday_load = float(values[-2]) if len(values) > 1 else 0.0
    ref = max(float(chronic[-1]), 1e-6)
    day_strain = 21.0 * (1.0 - math.exp(-today_load / (1.5 * ref))) if ref > 1e-6 else 0.0
    covered = len(_tail(source, today, 28))
    days_history = int((today - source.index[0]).days) + 1 if len(source) else 0
    # z of yesterday's load against the chronic mean, for the sleep need.
    hist = values[-29:-1]
    load_z_yesterday = None
    if len(hist) >= 5 and hist.std(ddof=1) > 0:
        load_z_yesterday = float((yesterday_load - hist.mean()) / hist.std(ddof=1))
    status, status_text = "ok", "Balanced"
    parts = []
    if acwr is not None and days_history >= 14:
        if acwr >= ACWR_SPIKE:
            status, status_text = "flag", "Load spike"
            parts.append(f"Acute load is {acwr:.2f}× your chronic level: a spike, and the range "
                         "where overuse trouble is most likely. Ease the next few days.")
        elif acwr >= ACWR_HIGH:
            status, status_text = "watch", "Building fast"
            parts.append(f"Acute:chronic {acwr:.2f}. You are ramping; keep the next step small.")
        elif acwr <= ACWR_LOW:
            status, status_text = "watch", "Under-loading"
            parts.append(f"Acute:chronic {acwr:.2f}: a lighter week than your norm, which is "
                         "fine as a deload and a loss if it continues.")
        else:
            parts.append(f"Acute:chronic {acwr:.2f}, inside the 0.8–1.3 sweet spot.")
    elif acwr is not None:
        parts.append(f"{days_history} days of load so far; the acute:chronic ratio settles "
                     "after about four weeks.")
    if monotony is not None and monotony >= MONOTONY_HIGH:
        if status == "ok":
            status, status_text = "watch", "Monotonous"
        parts.append(f"Monotony {monotony:.1f}: every day looks the same. Vary hard and easy.")
    if days_history >= 14:
        if form < -0.25 * max(ctl[-2], 1e-6):
            parts.append("Form is well negative: fatigue is ahead of fitness, which is how a "
                         "productive block feels and how an overreach starts.")
        elif form > 0.1 * max(ctl[-2], 1e-6):
            parts.append("Form is positive: fresh, the state you race in.")
    finding = " ".join(parts) or f"Today's load {_fmt(today_load)} {unit}."
    stats = [
        {"label": "Today", "value": _fmt(today_load), "unit": unit},
        {"label": "ACWR", "value": f"{acwr:.2f}" if acwr is not None else "—", "unit": ""},
        {"label": "Fitness", "value": _fmt(float(ctl[-1])), "unit": unit},
        {"label": "Fatigue", "value": _fmt(float(atl[-1])), "unit": unit},
        {"label": "Form", "value": _signed(form), "unit": unit},
    ]
    if monotony is not None:
        stats.append({"label": "Monotony", "value": f"{monotony:.1f}", "unit": ""})
    weekly_minutes = None
    target = getattr(profile, "weekly_target_minutes", None)
    sessions_week = [x for x in data.sessions if x["date"] > today - timedelta(days=7)]
    if sessions_week:
        weekly_minutes = float(sum(x["minutes"] for x in sessions_week))
    extra = {
        "source": label, "unit": unit, "acwr": acwr, "acute": float(acute[-1]),
        "chronic": float(chronic[-1]), "fitness": float(ctl[-1]), "fatigue": float(atl[-1]),
        "form": form, "monotony": monotony, "strain_week": strain, "day_strain": day_strain,
        "load_z_yesterday": load_z_yesterday, "days_history": days_history,
        "weekly_minutes": weekly_minutes, "weekly_target_minutes": target,
        "sessions_week": len(sessions_week),
        "form_series": [{"date": (start + timedelta(days=i)).isoformat(),
                         "fitness": round(float(ctl[i]), 1), "fatigue": round(float(atl[i]), 1),
                         "form": round(float(tsb[i]), 1)}
                        for i in range(max(0, len(values) - SERIES_DAYS), len(values))],
    }
    series = [{"date": (start + timedelta(days=i)).isoformat(), "value": round(float(values[i]), 1)}
              for i in range(max(0, len(values) - SERIES_DAYS), len(values))]
    return Panel("load", "Training load", status, status_text,
                 f"{day_strain:.1f}", "strain", f"{_fmt(today_load)} {unit} today · ACWR "
                 f"{acwr:.2f}" if acwr is not None else f"{_fmt(today_load)} {unit} today",
                 finding, method, _confidence(min(days_history, 28), covered if covered < 7 else 7),
                 f"{covered} of 28 days", series, stats, extra)


# --- fitness -------------------------------------------------------------------------


def _vo2_band(value: float, age: int | None, sex: str | None) -> str | None:
    table = VO2_BANDS.get((sex or "").upper())
    if table is None or not age:
        return None
    decade = max(20, min(70, (age // 10) * 10))
    fair, good, excellent = table[decade]
    if value >= excellent:
        return "excellent"
    if value >= good:
        return "good"
    if value >= fair:
        return "fair"
    return "below average"


def fitness_panel(data: PersonalData, patient: Any) -> Panel:
    today = data.today
    method = ("VO2 max as Apple estimates it from outdoor walks and runs (90-day trend, first "
              "vs last month); one-minute heart-rate recovery after workouts; resting heart "
              "rate as the slow proxy. The band is a coarse population table by age and sex.")
    vo2 = _finite(data.get(str(M.VO2_MAX)))
    hrr = _finite(data.get(str(M.HR_RECOVERY_1MIN)))
    if len(vo2) == 0 and len(hrr) == 0:
        return _nodata("fitness", "Cardio fitness", "", "VO2 max and heart-rate recovery come "
                       "from Apple Watch workouts outdoors; the app sends them with your "
                       "walking data.", method)
    stats: list[dict[str, Any]] = []
    extra: dict[str, Any] = {}
    parts = []
    headline, unit = "—", ""
    if len(vo2):
        latest = _latest(vo2, today)
        headline, unit = f"{latest[1]:.1f}", "mL/kg/min"
        first_month = vo2[[d <= vo2.index[0] + timedelta(days=30) for d in vo2.index]]
        last_month = _tail(vo2, today, 30)
        change = float(last_month.mean() - first_month.mean()) \
            if len(first_month) and len(last_month) and \
            (vo2.index[-1] - vo2.index[0]).days >= 45 else None
        band = _vo2_band(latest[1], getattr(patient, "age", None), getattr(patient, "sex", None))
        stats.append({"label": "VO2 max", "value": f"{latest[1]:.1f}", "unit": "mL/kg/min"})
        if change is not None:
            stats.append({"label": "90-day", "value": _signed(change, 1), "unit": ""})
        extra.update({"vo2_max": latest[1], "vo2_change_90d": change, "vo2_band": band})
        parts.append(f"VO2 max {latest[1]:.1f} mL/kg/min"
                     + (f", {band} for your age (rough band)" if band else "") + ".")
        if change is not None and abs(change) >= 1.0:
            parts.append(f"{'Up' if change > 0 else 'Down'} {abs(change):.1f} over the last three months.")
    if len(hrr):
        latest = _latest(hrr, today)
        recent = _recent_mean(hrr, today, 28)
        stats.append({"label": "HR recovery", "value": f"{latest[1]:.0f}", "unit": "bpm/min"})
        extra.update({"hr_recovery": latest[1], "hr_recovery_28d": recent})
        parts.append(f"Heart rate drops {latest[1]:.0f} bpm in the first minute after exercise"
                     + (f" (28-day mean {recent:.0f})" if recent else "") + ".")
        if headline == "—":
            headline, unit = f"{latest[1]:.0f}", "bpm/min"
    series = _points(_tail(vo2, today, 90), 1) if len(vo2) else _points(_tail(hrr, today, 90), 0)
    return Panel("fitness", "Cardio fitness", "ok", "Tracking", headline, unit,
                 "Apple Watch estimates", " ".join(parts), method,
                 "med" if len(vo2) >= 3 or len(hrr) >= 3 else "low",
                 f"{len(vo2)} VO2 readings · {len(hrr)} recovery readings", series, stats, extra)


# --- body signals ------------------------------------------------------------------


def body_panel(data: PersonalData) -> Panel:
    today = data.today
    method = ("Overnight SpO₂, breathing rate and skin temperature against your own 28-day "
              "baselines; the strain flag counts how many of resting HR, HRV, breathing rate "
              "and temperature moved the adverse way past one SD last night.")
    rows: list[dict[str, Any]] = []
    adverse = 0
    scored = 0

    def check(key: str, label: str, unit: str, floor: float, up_is_bad: bool | None,
              abs_flag: float | None = None) -> None:
        nonlocal adverse, scored
        s = _finite(data.get(key))
        latest = _latest(s, today)
        if latest is None:
            return
        base = _baseline(s, today, floor=floor)
        z = None
        if base is not None:
            z = (latest[1] - base[0]) / base[1]
            if not _stale(latest[0], today) and up_is_bad is not None:
                scored += 1
                if (z > 1.0 and up_is_bad) or (z < -1.0 and not up_is_bad):
                    adverse += 1
        rows.append({
            "key": key, "label": label, "unit": unit, "latest": latest[1],
            "latest_date": latest[0].isoformat(), "baseline": base[0] if base else None,
            "sd": base[1] if base else None, "z": z, "stale": _stale(latest[0], today),
            "series": _points(_tail(s, today), 2),
            "abs_flag": abs_flag,
        })

    check(str(M.SPO2), "Blood oxygen", "%", SD_FLOORS[str(M.SPO2)], False, 90.0)
    check(str(M.RESPIRATORY_RATE), "Breathing rate", "br/min",
          SD_FLOORS[str(M.RESPIRATORY_RATE)], True)
    temp_key = _temp_key(data)
    if temp_key:
        check(temp_key, "Skin temperature", "°C", SD_FLOORS[temp_key], True)
    # RHR and HRV count toward the strain tally but live in their own panels.
    s = _finite(data.get(str(M.RESTING_HR)))
    latest = _latest(s, today)
    base = _baseline(s, today, floor=SD_FLOORS[str(M.RESTING_HR)])
    if latest and base and not _stale(latest[0], today):
        scored += 1
        if (latest[1] - base[0]) / base[1] > 1.0:
            adverse += 1
    hrv_key = _hrv_key(data)
    if hrv_key:
        s = _finite(data.get(hrv_key))
        latest = _latest(s, today)
        base = _baseline(np.log(s[s > 0]), today, floor=SD_FLOORS["ln_hrv"])
        if latest and base and latest[1] > 0 and not _stale(latest[0], today):
            scored += 1
            if (math.log(latest[1]) - base[0]) / base[1] < -1.0:
                adverse += 1
    if not rows and scored == 0:
        return _nodata("body", "Body signals", "", "Blood oxygen, breathing rate and skin "
                       "temperature come from a watch or ring worn overnight.", method)
    status, status_text = "ok", "Quiet"
    parts = []
    for r in rows:
        if r["stale"] or r["z"] is None:
            continue
        if r["key"] == str(M.SPO2):
            if r["latest"] < 90:
                status, status_text = "flag", "Low oxygen night"
                parts.append(f"Blood oxygen averaged {r['latest']:.0f}% last night.")
            elif r["z"] < -1.5:
                parts.append(f"Blood oxygen a little under your usual ({r['latest']:.1f}%).")
        elif r["key"] == str(M.RESPIRATORY_RATE):
            if r["z"] >= 2.0:
                status = "flag" if status != "flag" else status
                status_text = "Signals consistent with strain"
                parts.append(f"Breathing rate {_signed(r['latest'] - r['baseline'], 1)} br/min over baseline.")
            elif r["z"] >= 1.0 and status == "ok":
                status, status_text = "watch", "Breathing rate up"
        else:
            if r["z"] >= 2.0:
                status, status_text = "flag", "Signals consistent with strain"
                parts.append(f"Skin temperature {_signed(r['latest'] - r['baseline'], 2)} °C over your baseline.")
            elif r["z"] >= 1.0 and status == "ok":
                status, status_text = "watch", "Temperature up"
    if adverse >= 2:
        status, status_text = "flag", "Signals consistent with strain"
        parts.insert(0, f"{adverse} of {scored} overnight signals moved the wrong way together. "
                        "That is what a hard block, poor sleep, alcohol, travel or the start of "
                        "a bug looks like; if you feel unwell, ease off and see a clinician.")
    elif adverse == 1 and status == "ok":
        status, status_text = "watch", "One signal off"
    finding = " ".join(parts) or "Every overnight signal is close to your baseline."
    stats = [{"label": r["label"], "value": f"{r['latest']:.{2 if 'temp' in r['key'] else 1}f}",
              "unit": r["unit"]} for r in rows]
    stats.append({"label": "Strain tally", "value": f"{adverse}/{scored}", "unit": ""})
    return Panel("body", "Body signals", status, status_text, f"{adverse}/{scored}", "off",
                 "signals off baseline last night", finding, method,
                 "high" if scored >= 3 else "med" if scored >= 2 else "low",
                 f"{scored} signals scored", [], stats,
                 {"signals": rows, "adverse": adverse, "scored": scored})


# --- rhythm ----------------------------------------------------------------------------


def rhythm_panel(data: PersonalData, sleep: Panel) -> Panel:
    today = data.today
    method = ("Bedtime and wake regularity from the sleep panel; interdaily stability (van "
              "Someren) over hourly steps, 1.0 being a perfectly repeated day.")
    bed_sd = sleep.extra.get("bedtime_sd_min")
    wake_sd = sleep.extra.get("waketime_sd_min")
    stability = None
    if len(data.intraday_steps):
        frame = data.intraday_steps[data.intraday_steps["date"] > today - timedelta(days=14)]
        if len(frame):
            pivot = frame.pivot_table(index="date", columns="hour", values="value", aggfunc="sum")
            pivot = pivot.reindex(columns=range(24))
            if len(pivot) >= 5:
                stability = interdaily_stability(pivot.values)
    if bed_sd is None and stability is None:
        return _nodata("rhythm", "Rhythm", "", "Regularity needs bedtimes from your sleep "
                       "tracker or hourly steps from your phone.", method)
    stats = []
    parts = []
    status, status_text = "ok", "Regular"
    if bed_sd is not None:
        stats.append({"label": "Bedtime", "value": f"±{bed_sd:.0f}", "unit": "min"})
        stats.append({"label": "Usual bedtime", "value": sleep.extra.get("mean_bedtime") or "—",
                      "unit": ""})
        if bed_sd >= 60:
            status, status_text = "watch", "Irregular"
            parts.append(f"Bedtime moves by ±{bed_sd:.0f} min. A fixed wake time is the lever "
                         "that pulls bedtime into line.")
        elif bed_sd >= 30:
            parts.append(f"Bedtime varies ±{bed_sd:.0f} min; under 30 is where sleep quality "
                         "tends to settle.")
        else:
            parts.append(f"Bedtime is steady (±{bed_sd:.0f} min).")
    if wake_sd is not None:
        stats.append({"label": "Wake", "value": f"±{wake_sd:.0f}", "unit": "min"})
    if stability is not None:
        stats.append({"label": "Stability", "value": f"{stability:.2f}", "unit": ""})
        parts.append(f"Daily activity rhythm stability {stability:.2f}"
                     + (" (strong)." if stability >= 0.6 else " (loose)." if stability < 0.4 else "."))
    return Panel("rhythm", "Rhythm", status, status_text,
                 f"±{bed_sd:.0f}" if bed_sd is not None else f"{stability:.2f}",
                 "min" if bed_sd is not None else "", "bedtime regularity, 14 nights",
                 " ".join(parts), method, "med", "14 nights", [], stats,
                 {"bedtime_sd_min": bed_sd, "waketime_sd_min": wake_sd, "stability": stability})


# --- activity & subjective ----------------------------------------------------------------


def activity_panel(data: PersonalData) -> Panel:
    today = data.today
    method = "Daily steps, exercise minutes and active energy: today, 7-day and 28-day means."
    steps = _finite(data.get(str(M.STEPS)))
    minutes = _finite(data.get(str(M.EXERCISE_SESSION)))
    energy = _finite(data.get(str(M.ACTIVE_ENERGY)))
    if len(steps) == 0 and len(minutes) == 0 and len(energy) == 0:
        return _nodata("activity", "Activity", "", "Steps, workouts and active energy arrive "
                       "from Apple Health or your wearable.", method)
    stats = []
    extra: dict[str, Any] = {}
    parts = []
    for s, label, unit, key in ((steps, "Steps", "", "steps"), (minutes, "Exercise", "min",
                                "exercise_minutes"), (energy, "Active energy", "kcal",
                                "active_energy")):
        if len(s) == 0:
            continue
        latest = _latest(s, today)
        week = _recent_mean(s, today)
        month = _recent_mean(s, today, 28)
        stats.append({"label": label, "value": _fmt(week), "unit": f"{unit}/day".strip("/")})
        extra[key] = {"latest": latest[1] if latest else None, "week": week, "month": month}
        if week is not None and month is not None and month > 0:
            pct = (week / month - 1) * 100
            if abs(pct) >= 15:
                parts.append(f"{label} {'up' if pct > 0 else 'down'} {abs(pct):.0f}% on your monthly average.")
    week_minutes = float(_tail(minutes, today, 7).sum()) if len(minutes) else None
    extra["week_exercise_minutes"] = week_minutes
    headline = _fmt(_recent_mean(steps, today)) if len(steps) else _fmt(week_minutes)
    return Panel("activity", "Activity", "ok", "Tracking", headline,
                 "steps/day" if len(steps) else "min this week",
                 "7-day average", " ".join(parts) or "Holding your usual level.", method,
                 "high" if len(_tail(steps, today, 7)) >= 5 else "med",
                 f"{len(_tail(steps if len(steps) else minutes, today, 7))} of 7 days",
                 _points(_tail(steps if len(steps) else minutes, today), 0), stats, extra)


def subjective_panel(data: PersonalData) -> Panel:
    today = data.today
    method = "Your check-in answers over the last seven days: latest and average."
    labels = {"energy": ("Energy", "/10"), "soreness": ("Soreness", "/10"), "mood": ("Mood", "/10"),
              "sleep_quality": ("Sleep quality", "/10"), "rpe": ("Session RPE", "/10"),
              "session_minutes": ("Session", "min")}
    stats = []
    extra: dict[str, Any] = {}
    for key, (label, unit) in labels.items():
        s = data.logs.get(key)
        if s is None or len(s) == 0:
            continue
        latest = _latest(s, today)
        week = _recent_mean(s, today)
        stats.append({"label": label, "value": _fmt(week, 1), "unit": unit})
        extra[key] = {"latest": latest[1] if latest else None, "week": week,
                      "series": _points(_tail(s, today), 1)}
    if not stats:
        return _nodata("subjective", "How you feel", "", "Answer the daily check-in and your "
                       "energy, soreness and mood sit here beside the wearable numbers.", method)
    parts = []
    sore = extra.get("soreness", {}).get("week")
    energy = extra.get("energy", {}).get("week")
    if sore is not None and sore >= 6:
        parts.append(f"Soreness has averaged {sore:.1f}/10 this week.")
    if energy is not None and energy <= 4:
        parts.append(f"Energy has been low ({energy:.1f}/10).")
    return Panel("subjective", "How you feel", "watch" if parts else "ok",
                 "Worth noting" if parts else "Steady", stats[0]["value"], stats[0]["unit"],
                 stats[0]["label"] + ", 7-day", " ".join(parts) or "Nothing standing out this week.",
                 method, "med", f"{len(stats)} signals", [], stats, extra)


# --- overreach watch ------------------------------------------------------------------

OVERREACH_WATCH = 25
OVERREACH_FLAG = 50


def overreach_panel(readiness: Panel, load: Panel, hrv: Panel, rhr: Panel, sleep: Panel,
                    subjective: Panel) -> Panel:
    """A 0–100 tally of the signs that precede functional overreaching:
    a low readiness week, a load spike or a monotonous block, negative form,
    a resting heart rate climbing, HRV under its band, sleep debt, soreness."""
    method = ("Points for each sign present this week: seven-day readiness under 40 or 30, "
              "acute:chronic at 1.3 or 1.5, monotony over 2, form below −25 % of fitness, "
              "resting HR +2 or +4 bpm over baseline, seven-day HRV under its band, sleep "
              "debt over 2 or 4 h, soreness over 6/10. Capped at 100. Watch from 25, flag "
              "from 50.")
    scored = any(p.hasData if hasattr(p, "hasData") else p.status != "nodata"
                 for p in (readiness, load, hrv, rhr, sleep))
    if not scored:
        return _nodata("overreach", "Overreach watch", "", "Needs a week of readiness, load "
                       "and sleep to judge.", method)
    score = 0.0
    drivers: list[dict[str, Any]] = []

    def add(points: float, label: str, text: str) -> None:
        nonlocal score
        score += points
        drivers.append({"label": label, "points": points, "text": text})

    week = [p["value"] for p in readiness.series[-7:]]
    if len(week) >= 4:
        mean = float(np.mean(week))
        if mean < 30:
            add(35, "Readiness", f"Seven-day readiness {mean:.0f}")
        elif mean < 40:
            add(25, "Readiness", f"Seven-day readiness {mean:.0f}")
    acwr = load.extra.get("acwr")
    if acwr is not None and (load.extra.get("days_history") or 0) >= 14:
        if acwr >= ACWR_SPIKE:
            add(25, "Load spike", f"Acute:chronic {acwr:.2f}")
        elif acwr >= ACWR_HIGH:
            add(15, "Load rising", f"Acute:chronic {acwr:.2f}")
    monotony = load.extra.get("monotony")
    if monotony is not None and monotony >= MONOTONY_HIGH:
        add(10, "Monotony", f"Monotony {monotony:.1f}")
    form, fitness = load.extra.get("form"), load.extra.get("fitness")
    if form is not None and fitness and form < -0.25 * fitness:
        add(15, "Deep fatigue", f"Form {form:.0f} against fitness {fitness:.0f}")
    delta = rhr.extra.get("delta_7d")
    if delta is not None:
        if delta >= 4:
            add(25, "Resting HR", f"+{delta:.1f} bpm over baseline this week")
        elif delta >= 2:
            add(15, "Resting HR", f"+{delta:.1f} bpm over baseline this week")
    if hrv.status in ("watch", "flag") and hrv.extra.get("balance") is not None \
            and hrv.extra["balance"] < 1.0 and hrv.extra.get("ln_mean_7d") is not None:
        lo = hrv.extra.get("swc_low")
        add(15, "HRV", f"Seven-day HRV under your band ({lo:.0f} ms)" if lo else "Seven-day HRV under your band")
    debt = sleep.extra.get("debt_hours") or 0.0
    if debt >= SLEEP_DEBT_FLAG:
        add(15, "Sleep debt", f"{debt:.1f} h behind this week")
    elif debt >= SLEEP_DEBT_WATCH:
        add(10, "Sleep debt", f"{debt:.1f} h behind this week")
    sore = (subjective.extra.get("soreness") or {}).get("week")
    if sore is not None and sore >= 6:
        add(10, "Soreness", f"Soreness averaging {sore:.1f}/10")
    score = min(100.0, score)
    if score >= OVERREACH_FLAG:
        status, status_text = "flag", "Signs present"
        finding = ("Several signs that precede functional overreaching are present at once: "
                   + "; ".join(d["text"].lower() for d in drivers[:4]) + ". Two or three easy days "
                   "and full nights usually turn it round; if it does not, or you feel unwell, "
                   "ease off further and see a clinician.")
    elif score >= OVERREACH_WATCH:
        status, status_text = "watch", "Building"
        finding = ("Some strain is accumulating: " + "; ".join(d["text"].lower() for d in drivers[:3])
                   + ". Fine inside a hard block, as long as the next easy day is real.")
    else:
        status, status_text = "ok", "Clear"
        finding = ("No sign of overreaching this week." if not drivers
                   else "One mild sign only: " + drivers[0]["text"].lower() + ". Nothing to change.")
    return Panel("overreach", "Overreach watch", status, status_text, f"{score:.0f}", "/100",
                 f"{len(drivers)} sign{'s' if len(drivers) != 1 else ''} this week", finding, method,
                 "med" if len(week) >= 5 else "low", f"{len(week)} of 7 days scored", [],
                 [{"label": d["label"], "value": f"+{d['points']:.0f}", "unit": ""} for d in drivers],
                 {"score": score, "drivers": drivers})


# --- trends and the week -----------------------------------------------------------------

TREND_WEEKS = 13


def weekly_means(series: pd.Series, today: date, weeks: int = TREND_WEEKS) -> list[dict[str, Any]]:
    out = []
    for i in range(weeks - 1, -1, -1):
        end = today - timedelta(days=7 * i)
        start = end - timedelta(days=6)
        window = _finite(series[[start <= d <= end for d in series.index]])
        out.append({"week": start.isoformat(),
                    "value": round(float(window.mean()), 2) if len(window) else None,
                    "days": int(len(window))})
    return out


def trends(data: PersonalData, readiness_daily: pd.Series) -> dict[str, Any]:
    """Thirteen weekly means per key metric, and the change between the
    last four weeks and the four before."""
    today = data.today
    hrv_key = _hrv_key(data)
    load, unit, label = _load_source(data)
    keys: list[tuple[str, pd.Series, str, str]] = [
        ("readiness", readiness_daily, "Readiness", ""),
        ("hrv", _finite(data.get(hrv_key)) if hrv_key else pd.Series(dtype=float), "HRV", "ms"),
        ("resting_hr", _finite(data.get(str(M.RESTING_HR))), "Resting HR", "bpm"),
        ("sleep", _finite(data.get(str(M.SLEEP_DURATION))), "Sleep", "h"),
        ("load", load if load is not None else pd.Series(dtype=float), "Load", unit),
        ("steps", _finite(data.get(str(M.STEPS))), "Steps", ""),
    ]
    out: dict[str, Any] = {}
    for key, series, title, u in keys:
        if len(series) == 0:
            continue
        weeks = weekly_means(series, today)
        recent = [w["value"] for w in weeks[-4:] if w["value"] is not None]
        before = [w["value"] for w in weeks[-8:-4] if w["value"] is not None]
        change = None
        if len(recent) >= 2 and len(before) >= 2 and np.mean(before) != 0:
            change = float((np.mean(recent) / np.mean(before) - 1) * 100)
        out[key] = {"label": title, "unit": u, "weeks": weeks, "change_pct": change,
                    "weeks_with_data": sum(1 for w in weeks if w["value"] is not None)}
    return out


def week_review(data: PersonalData, panels: dict[str, Panel], readiness_daily: pd.Series) -> dict[str, Any]:
    """This week against last: the numbers a Sunday review needs."""
    today = data.today
    this_start, prev_start = today - timedelta(days=6), today - timedelta(days=13)

    def mean_between(series: pd.Series, start: date, end: date) -> float | None:
        w = _finite(series[[start <= d <= end for d in series.index]])
        return float(w.mean()) if len(w) else None

    def sum_between(series: pd.Series, start: date, end: date) -> float | None:
        w = _finite(series[[start <= d <= end for d in series.index]])
        return float(w.sum()) if len(w) else None

    hrv_key = _hrv_key(data)
    load, unit, _label = _load_source(data)
    rows: dict[str, dict[str, Any]] = {}
    for key, series, agg, u in (
        ("readiness", readiness_daily, "mean", ""),
        ("hrv", _finite(data.get(hrv_key)) if hrv_key else pd.Series(dtype=float), "mean", "ms"),
        ("resting_hr", _finite(data.get(str(M.RESTING_HR))), "mean", "bpm"),
        ("sleep", _finite(data.get(str(M.SLEEP_DURATION))), "mean", "h"),
        ("load", load if load is not None else pd.Series(dtype=float), "sum", unit),
        ("steps", _finite(data.get(str(M.STEPS))), "mean", ""),
    ):
        if len(series) == 0:
            continue
        f = mean_between if agg == "mean" else sum_between
        now, prev = f(series, this_start, today), f(series, prev_start, this_start - timedelta(days=1))
        rows[key] = {"unit": u, "this": now, "last": prev,
                     "delta_pct": float((now / prev - 1) * 100) if now is not None and prev else None}
    best_day = None
    week_ready = readiness_daily[[this_start <= d <= today for d in readiness_daily.index]]
    if len(week_ready):
        best = week_ready.idxmax()
        worst = week_ready.idxmin()
        best_day = {"best": {"date": best.isoformat(), "value": float(week_ready[best])},
                    "worst": {"date": worst.isoformat(), "value": float(week_ready[worst])}}
    sessions = [s for s in data.sessions if this_start <= s["date"] <= today]
    logged = _srpe_series(data)
    logged_days = int((logged[[this_start <= d <= today for d in logged.index]] > 0).sum()) if len(logged) else 0
    # Streaks: consecutive days ending today with a check-in answered, and
    # with sleep at or above need (the need the sleep panel computed).
    energy = data.logs.get("energy")
    checkin_streak = 0
    if energy is not None:
        d = today
        while d in energy.index:
            checkin_streak += 1
            d -= timedelta(days=1)
    need = (panels["sleep"].extra.get("need_hours") if "sleep" in panels else None) or SLEEP_NEED_DEFAULT
    nights = _finite(data.get(str(M.SLEEP_DURATION)))
    sleep_streak = 0
    d = today
    while d in nights.index and float(nights[d]) >= need - 0.25:
        sleep_streak += 1
        d -= timedelta(days=1)
    highlights: list[str] = []
    r = rows.get("readiness")
    if r and r["this"] is not None and r["last"] is not None:
        highlights.append(f"Readiness averaged {r['this']:.0f}, {_signed(r['this'] - r['last'])} on last week.")
    s = rows.get("sleep")
    if s and s["this"] is not None:
        highlights.append(f"Sleep averaged {_hours(s['this'])} a night"
                          + (f", {_signed((s['this'] - s['last']) * 60)} min on last week." if s["last"] else "."))
    ld = rows.get("load")
    if ld and ld["this"] is not None and ld["last"]:
        highlights.append(f"Training load {_signed(ld['delta_pct'])}% on last week ({len(sessions) or logged_days} sessions).")
    h = rows.get("hrv")
    if h and h["this"] is not None and h["last"] is not None:
        highlights.append(f"HRV averaged {h['this']:.0f} ms ({_signed(h['this'] - h['last'])} ms).")
    if checkin_streak >= 3:
        highlights.append(f"{checkin_streak}-day check-in streak.")
    return {
        "start": this_start.isoformat(), "end": today.isoformat(),
        "metrics": rows, "readiness_days": best_day,
        "sessions": len(sessions) or logged_days,
        "session_minutes": float(sum(x["minutes"] for x in sessions)) if sessions else None,
        "streaks": {"checkin_days": checkin_streak, "sleep_on_need_days": sleep_streak},
        "highlights": highlights[:4],
    }


# --- the verdict ---------------------------------------------------------------------


def verdict(goal: str, readiness: Panel, load: Panel, sleep: Panel, body: Panel,
            days_with_data: int) -> dict[str, Any]:
    score = readiness.extra.get("score")
    band = readiness.extra.get("band")
    acwr = load.extra.get("acwr")
    form = load.extra.get("form")
    debt = sleep.extra.get("debt_hours") or 0.0
    train = goal in ("performance", "everyday")
    rehab = goal == "recovery"
    if days_with_data < 3 or score is None:
        return {"kind": "unknown", "title": "Still learning you",
                "reason": "Readiness needs a few nights of HRV, resting heart rate and sleep.",
                "detail": "Wear your watch overnight and check back in a couple of days."}
    if body.status == "flag" or band == "red":
        return {"kind": "rest", "title": "Recover today",
                "reason": (body.finding.split(".")[0] + "." if body.status == "flag"
                           else readiness.finding.split(".")[0] + "."),
                "detail": ("Light movement, food, water and an early night. "
                           + ("Skip loaded rehab work today; range-of-motion only." if rehab
                              else "No intensity."))}
    if acwr is not None and acwr >= ACWR_SPIKE:
        return {"kind": "easy", "title": "Ease off",
                "reason": f"Training load spiked to {acwr:.2f}× your chronic level.",
                "detail": "Keep today easy and short; let the chronic base catch up."}
    if debt >= SLEEP_DEBT_FLAG:
        return {"kind": "easy", "title": "Prioritise sleep",
                "reason": f"You are {debt:.1f} h behind on sleep this week.",
                "detail": "An easy day and an early night pay that back faster than anything else."}
    if band == "green" and (form is None or form > -0.25 * max(load.extra.get("fitness") or 1, 1)) \
            and (acwr is None or acwr < ACWR_HIGH):
        title = "Progress your rehab" if rehab else "Green light" if train else "Good day to push"
        return {"kind": "push", "title": title,
                "reason": f"Readiness {score:.0f}: recovery signals are above your normal.",
                "detail": ("Add a small step to today's rehab load and watch tomorrow's soreness."
                           if rehab else "Quality session if one is planned; your body is ready for it.")}
    if band == "green":
        return {"kind": "steady", "title": "Steady",
                "reason": f"Readiness {score:.0f}, but load or form says hold the line.",
                "detail": "Train as planned; no need to add."}
    return {"kind": "steady", "title": "Steady",
            "reason": f"Readiness {score:.0f}: close to your normal.",
            "detail": ("Keep the rehab plan as written." if rehab
                       else "Train as planned, moderate intensity.")}


# --- assembly ------------------------------------------------------------------------------

SECTIONS_BY_GOAL = {
    "performance": ["readiness", "load", "overreach", "hrv", "sleep", "resting_hr", "fitness",
                    "body", "activity", "rhythm", "subjective"],
    "sleep": ["sleep", "readiness", "rhythm", "hrv", "resting_hr", "body", "activity", "load",
              "overreach", "subjective"],
    "recovery": ["readiness", "care", "load", "overreach", "sleep", "hrv", "resting_hr", "body",
                 "activity", "subjective"],
    "everyday": ["readiness", "sleep", "activity", "resting_hr", "hrv", "body", "load",
                 "overreach", "fitness", "rhythm", "subjective"],
}


def compute_dashboard(data: PersonalData, patient: Any, profile: Any) -> dict[str, Any]:
    goal = getattr(profile, "goal", None) or "everyday"
    load = load_panel(data, profile)
    load_z = load.extra.get("load_z_yesterday")
    readiness = readiness_panel(data, profile, load_z)
    sleep = sleep_panel(data, profile, load_z)
    panels = {
        "readiness": readiness,
        "hrv": hrv_panel(data),
        "resting_hr": resting_hr_panel(data),
        "sleep": sleep,
        "load": load,
        "fitness": fitness_panel(data, patient),
        "body": body_panel(data),
        "activity": activity_panel(data),
        "subjective": subjective_panel(data),
    }
    panels["rhythm"] = rhythm_panel(data, sleep)
    panels["overreach"] = overreach_panel(readiness, load, panels["hrv"], panels["resting_hr"],
                                          sleep, panels["subjective"])
    days = data.days_with_data
    today_verdict = verdict(goal, readiness, load, sleep, panels["body"], days)
    order = SECTIONS_BY_GOAL.get(goal, SECTIONS_BY_GOAL["everyday"])
    readiness_daily = pd.Series(
        [p["value"] for p in readiness.series],
        index=[date.fromisoformat(p["date"]) for p in readiness.series],
    ) if readiness.series else pd.Series(dtype=float)
    out = {
        "as_of": data.today.isoformat(),
        "goal": goal,
        "days_with_data": days,
        "verdict": today_verdict,
        "sections": order,
        "panels": {key: panel.to_dict() for key, panel in panels.items()},
        "trends": _clean(trends(data, readiness_daily)),
        "week": _clean(week_review(data, panels, readiness_daily)),
    }
    out["digest"] = digest(out)
    out["fingerprint"] = hashlib.sha256(
        json.dumps(out["digest"], sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return out


def digest(dashboard: dict[str, Any]) -> dict[str, Any]:
    """The compact numbers a prompt (or a cache key) needs — no series."""
    panels = dashboard["panels"]

    def brief(key: str, *fields: str) -> dict[str, Any]:
        p = panels.get(key) or {}
        d = {"status": p.get("status"), "status_text": p.get("status_text"),
             "headline": f"{p.get('headline', '')} {p.get('unit', '')}".strip(),
             "finding": p.get("finding")}
        for f in fields:
            v = (p.get("extra") or {}).get(f)
            if isinstance(v, float):
                # Load-scale figures (kcal) as whole numbers; ratios keep two
                # places. The model reads these back verbatim.
                v = round(v) if abs(v) >= 100 else round(v, 2)
            if v is not None and not isinstance(v, (list, dict)):
                d[f] = v
        return d

    return {
        "as_of": dashboard["as_of"],
        "goal": dashboard["goal"],
        "days_with_data": dashboard["days_with_data"],
        "verdict": dashboard["verdict"],
        "readiness": brief("readiness", "score", "band", "need_hours"),
        "hrv": brief("hrv", "statistic", "balance", "cv_pct", "z_latest", "swc_low", "swc_high",
                     "baseline_mean", "latest"),
        "resting_hr": brief("resting_hr", "delta_7d", "z_latest", "baseline_mean", "latest",
                            "latest_is_last_night"),
        "sleep": brief("sleep", "need_hours", "debt_hours", "performance", "last_night_hours",
                       "bedtime_sd_min", "efficiency", "deep_pct", "rem_pct", "mean_bedtime"),
        "load": brief("load", "source", "acwr", "form", "fitness", "fatigue", "monotony",
                      "day_strain", "weekly_minutes", "weekly_target_minutes", "days_history"),
        "fitness": brief("fitness", "vo2_max", "vo2_change_90d", "vo2_band", "hr_recovery"),
        "body": brief("body", "adverse", "scored"),
        "activity": brief("activity", "week_exercise_minutes"),
        "rhythm": brief("rhythm", "bedtime_sd_min", "stability"),
        "subjective": brief("subjective"),
        "overreach": brief("overreach", "score"),
        "week": {k: v for k, v in (dashboard.get("week") or {}).items()
                 if k in ("highlights", "streaks", "sessions")},
    }
