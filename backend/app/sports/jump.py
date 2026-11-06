"""The phone as a jump mat: jump height from flight time.

The app records device motion during a jump with the phone held against
the chest or in a front pocket. During flight the total acceleration the
sensor reads (gravity included) falls to near zero, because a free-falling
body is weightless. The longest near-zero stretch between a takeoff spike
and a landing spike is the flight, and height follows from
``h = g · t² / 8``.

Flight-time jump heights from a worn sensor run a few centimetres high
against a force plate's impulse method and are sensitive to landing posture
(land with the same knee bend you took off with), so the result is labelled
an estimate and compared only with the athlete's own phone readings.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

G = 9.80665
FLIGHT_THRESHOLD = 3.0        # m/s²: below this the body is in free fall
MIN_FLIGHT_S = 0.18           # ~4 cm; anything shorter is a stumble
MAX_FLIGHT_S = 0.95           # ~1.1 m; anything longer is a sensor drop
SPIKE_THRESHOLD = 14.0        # m/s²: a takeoff or landing shows as a spike above 1.4 g


def estimate_jump(accel: list[list[float]], sample_rate_hz: float) -> dict[str, Any]:
    if not accel or sample_rate_hz <= 0:
        raise ValueError("No motion samples")
    a = np.asarray(accel, dtype=float)
    if a.ndim != 2 or a.shape[1] != 3 or len(a) < sample_rate_hz * 0.5:
        raise ValueError("The recording is too short to read a jump")
    mag = np.linalg.norm(a, axis=1)
    n = len(mag)
    dt = 1.0 / sample_rate_hz
    low = mag < FLIGHT_THRESHOLD
    # Longest run of near-zero acceleration.
    best_start, best_len = -1, 0
    i = 0
    while i < n:
        if low[i]:
            j = i
            while j < n and low[j]:
                j += 1
            if j - i > best_len:
                best_start, best_len = i, j - i
            i = j
        else:
            i += 1
    if best_len == 0:
        raise ValueError("No flight phase found. Jump higher, and keep the phone against your chest.")
    flight_s = best_len * dt
    if flight_s < MIN_FLIGHT_S:
        raise ValueError("The flight was too short to read. Jump for height, land softly, try again.")
    if flight_s > MAX_FLIGHT_S:
        raise ValueError("That looks like the phone falling rather than a jump. Hold it tight and try again.")
    takeoff = float(mag[max(0, best_start - int(0.25 * sample_rate_hz)):best_start].max()) if best_start > 0 else 0.0
    end = best_start + best_len
    landing = float(mag[end:min(n, end + int(0.25 * sample_rate_hz))].max()) if end < n else 0.0
    height_m = G * flight_s * flight_s / 8.0
    confidence = "high" if takeoff >= SPIKE_THRESHOLD and landing >= SPIKE_THRESHOLD else \
        "med" if (takeoff >= SPIKE_THRESHOLD or landing >= SPIKE_THRESHOLD) else "low"
    return {
        "height_cm": round(height_m * 100.0, 1),
        "flight_time_ms": round(flight_s * 1000.0),
        "takeoff_peak_ms2": round(takeoff, 1),
        "landing_peak_ms2": round(landing, 1),
        "confidence": confidence,
        "method": "flight time, h = g·t²/8",
    }


def estimate_balance(gravity: list[list[float]], sample_rate_hz: float) -> dict[str, Any]:
    """Postural sway from the gravity vector while the phone is held at the
    chest: the mean angular deviation and its path length. Decorative
    precision, honest use: the number compares a side with the other side."""
    g = np.asarray(gravity, dtype=float)
    if g.ndim != 2 or len(g) < sample_rate_hz:
        raise ValueError("The recording is too short")
    g = g / np.clip(np.linalg.norm(g, axis=1, keepdims=True), 1e-6, None)
    mean = g.mean(axis=0)
    mean /= max(np.linalg.norm(mean), 1e-6)
    dots = np.clip(g @ mean, -1.0, 1.0)
    angles = np.degrees(np.arccos(dots))
    path = float(np.sum(np.abs(np.diff(angles))))
    return {"sway_deg_mean": round(float(angles.mean()), 2), "sway_deg_max": round(float(angles.max()), 2),
            "path_deg": round(path, 1), "seconds": round(len(g) / sample_rate_hz, 1),
            "steadiness": round(max(0.0, 100.0 - min(100.0, path / max(len(g) / sample_rate_hz, 1) * 4.0)), 0)}


def rsi_from_flight_contact(flight_ms: float, contact_ms: float) -> float | None:
    if contact_ms <= 0:
        return None
    return round(flight_ms / contact_ms, 2)


def height_in(cm: float) -> float:
    return round(cm / 2.54, 1)


def is_plausible_jump(height_cm: float) -> bool:
    return 3.0 <= height_cm <= 120.0 and math.isfinite(height_cm)
