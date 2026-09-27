"""Stair ascent and descent speed from the barometer.

The phone's pressure altimeter resolves height changes of a few tens of
centimetres once smoothed. A flight of stairs is a monotonic change of at
least FLIGHT_MIN_M (Apple's own convention is ~3 m per flight; 2.5 m is one
domestic flight of 14 x 18 cm risers) sustained at a plausible vertical
speed, DURING which steps are being taken. The last condition is what
separates stairs from an elevator or an escalator.

  vertical speed = 0.8 x |altitude change| / (t90 - t10)   [m/s]

where t10 and t90 are the times the smoothed trace crosses 10 % and 90 %
of the flight's height change (the smoothing stretches the flight's
edges; the mid-crossings keep its true duration),

reported separately for ascent and descent, one row per flight. The
altitude trace is resampled to ALT_FS Hz, median-filtered (3 samples) and
low-passed at 0.3 Hz before differencing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.engine.mobility.dsp import lowpass, resample_uniform

ALT_FS = 2.0
FLIGHT_MIN_M = 2.5
MIN_V = 0.08                  # m/s: below this the trace is drifting, not climbing
V_RANGE = (0.10, 1.50)        # plausible vertical speed on stairs
MIN_STEPS = 6
MERGE_GAP_S = 2.0


@dataclass
class StairEvent:
    start_s: float
    end_s: float
    direction: str            # "up" | "down"
    height_m: float
    speed_mps: float
    n_steps: int


def _median3(x: np.ndarray) -> np.ndarray:
    if len(x) < 3:
        return x
    stacked = np.stack([np.r_[x[0], x[:-1]], x, np.r_[x[1:], x[-1]]], axis=0)
    return np.median(stacked, axis=0)


def _rise_time(h: np.ndarray, t: np.ndarray) -> float:
    """Time between the 10 % and 90 % crossings of the segment's height
    change. Low-pass smoothing stretches a flight's edges symmetrically, so
    the mid-crossings keep the true duration where the end points do not."""
    dh = float(h[-1] - h[0])
    if dh == 0 or len(h) < 2:
        return 0.0
    frac = (h - h[0]) / dh
    above10 = np.where(frac >= 0.1)[0]
    above90 = np.where(frac >= 0.9)[0]
    if len(above10) == 0 or len(above90) == 0:
        return 0.0
    return float(t[above90[0]] - t[above10[0]])


def stair_events(
    altitude: np.ndarray | None, step_times_s: np.ndarray
) -> list[StairEvent]:
    """altitude: (M,2) [t_s, relative_m]; step_times_s: absolute step instants
    in the window (s)."""
    if altitude is None or len(altitude) < 6:
        return []
    alt = np.asarray(altitude, dtype=float).reshape(-1, 2)
    t, h = resample_uniform(alt[:, 0], alt[:, 1], ALT_FS)
    if len(t) < 6:
        return []
    h = lowpass(_median3(h), 0.3, ALT_FS)
    v = np.gradient(h, 1.0 / ALT_FS)
    moving = np.abs(v) > MIN_V
    events: list[StairEvent] = []
    i = 0
    gap = int(MERGE_GAP_S * ALT_FS)
    steps = np.asarray(step_times_s, dtype=float)
    while i < len(t):
        if not moving[i]:
            i += 1
            continue
        sign = np.sign(v[i])
        j = i
        last_moving = i
        while j < len(t) and (j - last_moving) <= gap:
            if moving[j] and np.sign(v[j]) == sign:
                last_moving = j
            elif moving[j] and np.sign(v[j]) != sign:
                break
            j += 1
        s, e = i, last_moving
        dh = float(h[e] - h[s])
        dt = _rise_time(h[s:e + 1], t[s:e + 1])
        n_steps = int(((steps >= t[s]) & (steps <= t[e])).sum())
        if abs(dh) >= FLIGHT_MIN_M and dt > 0:
            speed = 0.8 * abs(dh) / dt
            if V_RANGE[0] <= speed <= V_RANGE[1] and n_steps >= MIN_STEPS:
                events.append(StairEvent(
                    start_s=float(t[s]), end_s=float(t[e]),
                    direction="up" if dh > 0 else "down",
                    height_m=round(abs(dh), 2), speed_mps=round(speed, 3), n_steps=n_steps,
                ))
        i = max(e + 1, i + 1)
    return events
