"""Synthetic phone-in-pocket walking signals with known ground truth, for the
mobility engine's tests. Nothing here is a model of a real patient; it is a
signal whose step instants, step lengths, thigh phases and stairs are known
exactly, so each algorithm can be checked against the number it should find.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from app.engine.mobility.frames import MotionWindow
from app.engine.mobility.spatial import K_DEFAULT, LEG_LENGTH_RATIO

G = 9.80665


def excursion_for(step_len: float, height_m: float, k: float = K_DEFAULT) -> float:
    """Vertical CoM excursion h that the inverted pendulum maps to step_len."""
    leg = LEG_LENGTH_RATIO * height_m
    half = step_len / (2.0 * k)
    return leg - np.sqrt(max(leg * leg - half * half, 0.0))


def synth_walk(
    duration_s: float = 60.0,
    fs: float = 50.0,
    cadence: float = 110.0,
    height_m: float = 1.75,
    step_len: float = 0.65,
    ipsi_ratio: float = 1.0,
    noise: float = 0.15,
    with_gyro: bool = True,
    with_gravity: bool = True,
    stairs: bool = False,
    lead_in_s: float = 0.0,
    seed: int = 0,
    pocket_side: str = "left",
    context: str = "guided_walk",
) -> tuple[MotionWindow, dict]:
    """A pocketed phone (long axis vertical, gravity along -y) during steady
    walking. ``ipsi_ratio`` is the instrumented leg's step time over the
    other leg's (1.0 symmetric). Returns (window, truth)."""
    rng = np.random.default_rng(seed)
    n = int(duration_s * fs)
    t = np.arange(n) / fs
    t_step = 60.0 / cadence
    ipsi = t_step * 2.0 * ipsi_ratio / (1.0 + ipsi_ratio)
    contra = t_step * 2.0 / (1.0 + ipsi_ratio)
    stride = ipsi + contra

    # Heel strikes: ipsilateral at HS_k, contralateral at HS_k + contra.
    hs_ipsi: list[float] = []
    hs_contra: list[float] = []
    tk = lead_in_s + 0.3
    while tk < duration_s - 0.3:
        hs_ipsi.append(tk)
        if tk + contra < duration_s - 0.3:
            hs_contra.append(tk + contra)
        tk += stride
    events = sorted([(x, "i") for x in hs_ipsi] + [(x, "c") for x in hs_contra])
    times = np.array([e[0] for e in events])

    # Vertical CoM displacement: one cosine arc per step, excursion h.
    h = excursion_for(step_len, height_m)
    z = np.zeros(n)
    walking = np.zeros(n, dtype=bool)
    for a, b in zip(times[:-1], times[1:]):
        m = (t >= a) & (t < b)
        u = (t[m] - a) / (b - a)
        z[m] = -(h / 2.0) * np.cos(2.0 * np.pi * u)
        walking[m] = True
    a_com = np.gradient(np.gradient(z, 1.0 / fs), 1.0 / fs)
    a_com[~walking] = 0.0
    # Heel-strike impacts, the near leg's felt harder.
    impacts = np.zeros(n)
    for x, who in events:
        amp = 3.0 if who == "i" else 1.9
        # A brief decelerate-then-rebound transient (net impulse ~ 0), like a
        # real heel strike, not a push that would leave the thigh moving.
        tau = (t - x) / 0.03
        impacts += amp * (1.0 - tau * tau) * np.exp(-tau * tau / 2.0) * 0.6
    a_vert = a_com + impacts
    a_ap = np.zeros(n)
    a_ap[walking] = 0.6 * np.sin(2.0 * np.pi * cadence / 60.0 * t[walking])
    a_ml = np.zeros(n)
    a_ml[walking] = 0.4 * np.sin(2.0 * np.pi * cadence / 120.0 * t[walking])

    accel = np.zeros((n, 3))
    accel[:, 0] = a_ml
    accel[:, 1] = -G + a_vert
    accel[:, 2] = a_ap
    accel += rng.normal(0.0, noise, accel.shape)

    gyro = None
    if with_gyro:
        w = np.zeros(n)
        for k, hs in enumerate(hs_ipsi[:-1]):
            c = hs + contra
            nxt = hs_ipsi[k + 1]
            m1 = (t >= hs) & (t < c)
            w[m1] = -1.6 * np.sin(np.pi * (t[m1] - hs) / contra)          # stance: extension
            m2 = (t >= c) & (t < nxt)
            u = (t[m2] - c) / ipsi
            # Flexion lobe: a slow start (the reversal), the steepest rise a
            # quarter in (toe-off), then a sharp deceleration into heel strike.
            w[m2] = np.where(u < 0.5, 3.2 * (1.0 - np.cos(2.0 * np.pi * u)) / 2.0,
                             3.2 * np.cos(np.pi * (u - 0.5)))
        gyro = np.zeros((n, 3))
        gyro[:, 0] = w                    # sagittal axis = device x
        gyro[:, 1] = 0.2 * rng.normal(size=n)
        gyro[:, 2] = 0.25 * w + 0.1 * rng.normal(size=n)
        gyro[:, 0] += 0.1 * rng.normal(size=n)

    gravity = None
    if with_gravity:
        gravity = np.tile(np.array([0.0, -1.0, 0.0]), (n, 1))

    altitude = None
    truth_stairs = []
    if stairs:
        ta = np.arange(0.0, duration_s, 1.0)
        alt = np.zeros_like(ta)
        up = (ta >= 15) & (ta < 23)
        alt[up] = (ta[up] - 15) * (3.0 / 8.0)
        alt[ta >= 23] = 3.0
        down = (ta >= 35) & (ta < 42)
        alt[down] = 3.0 - (ta[down] - 35) * (3.0 / 7.0)
        alt[ta >= 42] = 0.0
        alt += rng.normal(0.0, 0.05, alt.shape)
        altitude = np.stack([ta, alt], axis=1)
        truth_stairs = [("up", 3.0 / 8.0), ("down", 3.0 / 7.0)]

    window = MotionWindow(
        started_at=datetime(2026, 9, 20, 10, 0, 0), fs=fs, accel=accel, gyro=gyro,
        gravity=gravity, altitude=altitude, height_cm=height_m * 100.0,
        pocket_side=pocket_side, context=context, device_model="synthetic",
    )
    truth = {
        "n_steps": len(events), "cadence": cadence, "step_len": step_len,
        "speed": step_len * cadence / 60.0,
        "asymmetry_pct": (ipsi - contra) / ((ipsi + contra) / 2.0) * 100.0,
        # toe-off sits a quarter of the flexion lobe in, so swing = 3/4 ipsi
        "double_support_pct": 100.0 * (1.0 - 2.0 * (0.75 * ipsi) / stride),
        "stairs": truth_stairs, "h": h,
    }
    return window, truth
