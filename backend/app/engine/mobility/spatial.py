"""Step length and walking speed: the inverted-pendulum model.

Zijlstra & Hof (2003) showed that during single support the body's centre
of mass follows an arc over the stance leg, so the vertical excursion h of
the trunk within one step and the leg length l give the step length
geometrically:

    SL = K * 2 * sqrt(2 * l * h - h^2)

with an empirical correction K (Zijlstra's 1.25) for the parts of the step
the pendulum does not describe (double support, knee flexion). h comes from
double integration of the vertical acceleration with a 0.1 Hz high-pass
after each integration to hold drift down; it is read as max - min of the
displacement between consecutive foot contacts. l is taken as
LEG_LENGTH_RATIO x stature (Winter's anthropometric table, greater
trochanter height ~ 0.53 H).

Placement caveat, stated up front: Zijlstra validated the model with a sensor
at the lower trunk; a pocketed phone rides on the thigh, whose vertical
excursion is close to but not identical to the trunk's. K therefore needs
its own calibration for pocket carriage. When the window carries a GPS
distance with good accuracy (GPS_MAX_ACCURACY_M) over a long enough bout,
the pipeline calibrates K for that bout (k_cal = gps distance / uncorrected
distance) and records it, which is the personalisation Soltani et al. (2020)
showed halves the wrist speed error. Until a per-patient K exists the
default applies and the row is flagged ``calibrated: false``.

Walking speed for a bout is total distance / bout duration — equivalently
mean step length x cadence / 60.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.engine.mobility.dsp import highpass, lowpass, trapezoid_cumulative

LEG_LENGTH_RATIO = 0.53
K_DEFAULT = 1.25
DRIFT_HP_HZ = 0.1
COM_LP_HZ = 5.0
H_RANGE = (0.005, 0.12)       # plausible vertical excursion per step (m)
SL_RANGE = (0.10, 1.60)       # plausible step length (m)
GPS_MAX_ACCURACY_M = 12.0
GPS_MIN_STEPS = 40
K_RANGE = (0.6, 2.0)
EDGE_TRIM = 2                 # strides dropped at each end of a bout


@dataclass
class Spatial:
    step_lengths: np.ndarray   # m, one per step interval (uncorrected edges included)
    distance_m: float
    speed_mps: float
    k_used: float
    calibrated: bool
    method: str                # "inverted_pendulum" | "inverted_pendulum+gps" | "gps"


def vertical_displacement(a_vert: np.ndarray, fs: float) -> np.ndarray:
    """Double integration of the vertical acceleration to displacement.

    The acceleration is low-passed at COM_LP_HZ first: the centre of mass
    moves at the step frequency and its first few harmonics (< 5 Hz), while
    the heel-strike transient the thigh feels is a brief high-frequency
    oscillation whose net impulse is ~0 but whose integration noise is not.
    A 0.1 Hz high-pass after each integration removes the drift that
    integrating a small bias produces.
    """
    dt = 1.0 / fs
    a = highpass(lowpass(a_vert, COM_LP_HZ, fs), DRIFT_HP_HZ, fs)
    v = highpass(trapezoid_cumulative(a, dt), DRIFT_HP_HZ, fs)
    return highpass(trapezoid_cumulative(v, dt), DRIFT_HP_HZ, fs)


def step_lengths(
    a_vert: np.ndarray, peaks: np.ndarray, fs: float, height_m: float, k: float = K_DEFAULT
) -> np.ndarray:
    z = vertical_displacement(a_vert, fs)
    leg = LEG_LENGTH_RATIO * height_m
    out = []
    for i, j in zip(peaks[:-1], peaks[1:]):
        seg = z[i:j + 1]
        h = float(seg.max() - seg.min()) if len(seg) > 1 else 0.0
        h = min(max(h, H_RANGE[0]), min(H_RANGE[1], leg - 1e-3))
        sl = k * 2.0 * np.sqrt(max(2.0 * leg * h - h * h, 0.0))
        out.append(min(max(sl, SL_RANGE[0]), SL_RANGE[1]))
    return np.asarray(out, dtype=float)


def spatial(
    a_vert: np.ndarray,
    peaks: np.ndarray,
    fs: float,
    duration_s: float,
    height_m: float | None,
    gps_distance_m: float | None = None,
    gps_accuracy_m: float | None = None,
    k: float = K_DEFAULT,
) -> Spatial | None:
    """Per-bout step lengths, distance and speed; None when neither stature
    nor a usable GPS distance is available."""
    gps_ok = (
        gps_distance_m is not None and gps_distance_m > 0
        and gps_accuracy_m is not None and gps_accuracy_m <= GPS_MAX_ACCURACY_M
        and len(peaks) >= GPS_MIN_STEPS
    )
    if height_m is None or height_m <= 0:
        if gps_ok and duration_s > 0:
            n = max(len(peaks) - 1, 1)
            return Spatial(np.full(n, gps_distance_m / n), float(gps_distance_m),
                           float(gps_distance_m) / duration_s, float("nan"), True, "gps")
        return None
    raw = step_lengths(a_vert, peaks, fs, height_m, k=1.0)
    if len(raw) == 0 or duration_s <= 0:
        return None
    n_intervals = len(raw)
    # The first and last strides sit in the integrators' edge transient;
    # they are dropped from the estimate when there are enough others, and
    # the bout's step length is the MEDIAN of the rest so one mis-detected
    # contact cannot drag it. Distance is that median over every interval.
    core = raw[EDGE_TRIM:-EDGE_TRIM] if n_intervals > 2 * EDGE_TRIM + 4 else raw
    typical = float(np.median(core))
    if gps_ok:
        k_cal = float(gps_distance_m / (typical * n_intervals))
        k_cal = min(max(k_cal, K_RANGE[0]), K_RANGE[1])
        lengths = raw * k_cal
        distance = typical * k_cal * n_intervals
        return Spatial(lengths, distance, distance / duration_s, k_cal, True,
                       "inverted_pendulum+gps")
    lengths = raw * k
    distance = typical * k * n_intervals
    return Spatial(lengths, distance, distance / duration_s, float(k), False, "inverted_pendulum")
