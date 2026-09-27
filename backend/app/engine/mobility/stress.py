"""Daily stress index from the patient's own autonomic baselines.

No wearable vendor exposes a comparable stress number (Garmin and Oura ship
proprietary scores through their APIs; Apple, Fitbit, WHOOP and Samsung ship
none), so MedPull computes one the same way for every device: each overnight
autonomic signal is standardised against the patient's own recent history
from the SAME series, and the standardised deviations are combined in the
direction that means strain.

  inputs (daily)     ln(HRV)  [RMSSD, or SDNN when that is what the device
                     ships — never mixed, the series is whichever exists]
                     resting heart rate
                     respiratory rate (sleep)
  baseline           trailing window of BASELINE_DAYS days ending the day
                     before, at least MIN_BASELINE_DAYS values; mean and SD
                     with the same physiological SD floors the risk engine
                     uses, so one quiet week cannot make a normal night look
                     extreme
  strain z           -z(ln HRV), +z(RHR), +z(RR): a suppressed HRV, a raised
                     resting rate and faster breathing each push the same way
  composite          weighted mean of the strain z-scores present that day
                     (HRV 0.4, RHR 0.4, RR 0.2, renormalised over what exists)
  index              50 + 25 x composite, clipped to 0-100

So 50 is "at your own baseline", 75 is one SD of strain, 100 two SD. The
construction follows the HRV-stress literature (RMSSD and HF power fall,
heart rate rises under sympathetic load: Kim et al. 2018 meta-analysis) and
Firstbeat's stress/recovery framing without its proprietary model. Baevsky's
stress index needs beat-to-beat intervals, which daily summaries do not
carry; it is the natural extension once the app uploads HKHeartbeatSeries.
"""

from __future__ import annotations

import math

import pandas as pd

from app.models.enums import MetricType as M

BASELINE_DAYS = 28
MIN_BASELINE_DAYS = 5
WEIGHTS = {"hrv": 0.4, "rhr": 0.4, "rr": 0.2}
SD_FLOORS = {"hrv": 0.06, "rhr": 1.5, "rr": 0.6}   # ln-units, bpm, breaths/min
Z_CLIP = 3.0


def _pick_hrv(series: dict[str, pd.Series]) -> pd.Series | None:
    for key in (str(M.HRV_RMSSD), str(M.HRV_SDNN)):
        s = series.get(key)
        if s is not None and len(s) > 0:
            return s
    return None


def _strain_z(s: pd.Series, day: int, floor: float, log: bool) -> float | None:
    hist = s[(s.index < day) & (s.index >= day - BASELINE_DAYS)].dropna()
    if log:
        hist = hist[hist > 0].map(math.log)
    if len(hist) < MIN_BASELINE_DAYS:
        return None
    value = float(s.loc[day])
    if log:
        if value <= 0:
            return None
        value = math.log(value)
    sd = max(float(hist.std(ddof=1)), floor)
    z = (value - float(hist.mean())) / sd
    return max(-Z_CLIP, min(Z_CLIP, z))


def stress_index_series(series: dict[str, pd.Series]) -> pd.Series | None:
    """Daily 0-100 index indexed by post-op day, or None when no autonomic
    series exists."""
    hrv = _pick_hrv(series)
    rhr = series.get(str(M.RESTING_HR))
    rr = series.get(str(M.RESPIRATORY_RATE))
    sources = [(k, s) for k, s in (("hrv", hrv), ("rhr", rhr), ("rr", rr)) if s is not None]
    if not sources:
        return None
    days = sorted(set().union(*[set(s.index) for _, s in sources]))
    out: dict[int, float] = {}
    for day in days:
        total_w = 0.0
        acc = 0.0
        for key, s in sources:
            if day not in s.index or pd.isna(s.loc[day]):
                continue
            z = _strain_z(s, day, SD_FLOORS[key], log=(key == "hrv"))
            if z is None:
                continue
            if key == "hrv":
                z = -z
            acc += WEIGHTS[key] * z
            total_w += WEIGHTS[key]
        if total_w > 0:
            out[int(day)] = round(max(0.0, min(100.0, 50.0 + 25.0 * acc / total_w)), 1)
    if not out:
        return None
    return pd.Series(out, dtype=float).sort_index()
