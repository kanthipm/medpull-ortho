"""Raw sensor windows and their gravity-aligned, uniformly sampled form.

A ``MotionWindow`` is what the patient app uploads: a few minutes of
accelerometer (and, when the phone has it, gyroscope) samples in the device
frame, the phone's own gravity estimate, barometric altitude, and whatever
the phone's pedometer / GPS said about the same minutes. ``align`` turns it
into the three signals every algorithm downstream reads:

- ``a_mag``  the dynamic acceleration magnitude, |a| minus its mean. It does
             not depend on how the phone sits in the pocket, which is why
             step detection and bout detection run on it.
- ``a_vert`` the dynamic component along gravity. Its SIGN depends on the
             platform's convention (iOS reports the gravity vector pointing
             into the ground, Android out of it); everything that consumes it
             (integration range, autocorrelation, harmonic ratio) is
             sign-invariant, so the convention is recorded but never relied on.
- ``gyro``   angular velocity resampled onto the same grid, for the thigh
             phase model.

Sampling: phones deliver motion at a nominal rate with jitter; when the app
sends per-sample timestamps the window is linearly resampled onto a uniform
grid at ``FS`` Hz, otherwise the nominal rate is trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from app.engine.mobility.dsp import lowpass, resample_uniform

FS = 50.0          # working sample rate (Hz)
G = 9.80665        # standard gravity (m/s^2)
GRAVITY_LP_HZ = 0.25


@dataclass
class MotionWindow:
    started_at: datetime
    fs: float
    accel: np.ndarray                     # (N,3) total acceleration, m/s^2, device frame
    gyro: np.ndarray | None = None        # (N,3) rad/s, device frame
    gravity: np.ndarray | None = None     # (N,3) unit gravity direction, device frame
    timestamps: np.ndarray | None = None  # (N,) seconds since started_at
    altitude: np.ndarray | None = None    # (M,2) [seconds since started_at, relative metres]
    gps_distance_m: float | None = None
    gps_accuracy_m: float | None = None   # horizontal accuracy the phone reported (m)
    pedometer_steps: int | None = None
    pedometer_distance_m: float | None = None
    height_cm: float | None = None
    pocket_side: str | None = None        # "left" | "right": the leg the phone rides on
    context: str = "free_living"          # guided_walk | six_minute_walk | free_living
    device_model: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return int(len(self.accel))

    @property
    def duration_s(self) -> float:
        if self.timestamps is not None and len(self.timestamps) > 1:
            return float(self.timestamps[-1] - self.timestamps[0])
        return self.n / self.fs if self.fs > 0 else 0.0


@dataclass
class Aligned:
    fs: float
    t: np.ndarray          # (N,) seconds since window start
    a_mag: np.ndarray      # (N,) m/s^2, mean removed
    a_vert: np.ndarray     # (N,) m/s^2 along gravity, mean removed
    g_hat: np.ndarray      # (N,3) unit gravity direction used
    gyro: np.ndarray | None
    gravity_source: str    # "phone" | "lowpass"

    @property
    def n(self) -> int:
        return int(len(self.t))


def align(window: MotionWindow, fs: float = FS) -> Aligned:
    accel = np.asarray(window.accel, dtype=float).reshape(-1, 3)
    n = len(accel)
    if window.timestamps is not None and len(window.timestamps) == n and n > 1:
        t_in = np.asarray(window.timestamps, dtype=float)
        t_in = t_in - t_in[0]
    else:
        t_in = np.arange(n) / float(window.fs)

    def onto_grid(x: np.ndarray | None) -> np.ndarray | None:
        if x is None:
            return None
        x = np.asarray(x, dtype=float).reshape(-1, 3)
        if len(x) != n:
            return None
        return resample_uniform(t_in, x, fs)[1]

    t, acc = resample_uniform(t_in, accel, fs)
    gyro = onto_grid(window.gyro)
    grav = onto_grid(window.gravity)
    if grav is not None and np.all(np.isfinite(grav)):
        norms = np.linalg.norm(grav, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        g_hat = grav / norms
        source = "phone"
    else:
        low = np.stack([lowpass(acc[:, j], GRAVITY_LP_HZ, fs) for j in range(3)], axis=1)
        norms = np.linalg.norm(low, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        g_hat = low / norms
        source = "lowpass"
    along = np.sum(acc * g_hat, axis=1)
    mag = np.linalg.norm(acc, axis=1)
    return Aligned(
        fs=fs, t=t, a_mag=mag - mag.mean(), a_vert=along - along.mean(),
        g_hat=g_hat, gyro=gyro, gravity_source=source,
    )
