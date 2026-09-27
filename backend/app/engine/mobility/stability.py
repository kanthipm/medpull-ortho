"""Walking-steadiness index (0-100) from gait-variability features.

Apple's Walking Steadiness is a closed classifier trained on the Apple Heart
& Movement Study. MedPull's index is instead an explicit, fixed combination
of four features the prospective fall-risk literature has repeatedly found
informative on trunk / pocket accelerometry (Weiss 2013, Rispens 2015,
van Schooten 2016, Hausdorff 2001):

  step-time CV        variability of step timing (higher = less steady)
  stride regularity   autocorrelation of the vertical acceleration at the
                      stride lag (higher = more regular)
  harmonic ratio      even/odd harmonic power of the vertical acceleration
                      at the stride frequency (higher = smoother, symmetric)
  walking speed       (higher = steadier; the strongest single predictor)

Each feature is mapped to 0-1 through a logistic centred on the value that
separates "typical" from "impaired" community-dwelling older adults in those
studies (the anchors below), and the index is their weighted mean x 100.
Bands mirror Apple's three levels so clinicians read one scale:
  >= 60 OK, 40-60 Low, < 40 Very low.

What the index is NOT: a validated fall-risk classifier. The features are
reimplemented from the literature; the weights and anchors are defensible
starting points, and the validation plan in the methodology document is the
work that turns them into a claim. Until then the card is labelled guarded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.engine.mobility.dsp import autocorr, harmonic_ratio, lowpass

# (anchor at which the feature scores 0.5, scale, direction: +1 higher is better)
ANCHORS = {
    "step_time_cv": (0.045, 0.015, -1),     # 4.5 % CV: healthy ~2-3 %, fallers ~5-8 %
    "stride_regularity": (0.65, 0.12, +1),  # autocorrelation at stride lag
    "harmonic_ratio": (1.7, 0.4, +1),       # vertical HR: healthy 2-3, impaired < 1.5
    "speed_mps": (0.85, 0.15, +1),          # ~0.8 m/s: the community-ambulation threshold
}
WEIGHTS = {"step_time_cv": 0.30, "stride_regularity": 0.20, "harmonic_ratio": 0.20,
           "speed_mps": 0.30}
LOW = 60.0
VERY_LOW = 40.0


@dataclass
class Stability:
    index: float
    level: str                  # "ok" | "low" | "very_low"
    features: dict[str, float]


def _logistic(value: float, anchor: float, scale: float, direction: int) -> float:
    z = direction * (value - anchor) / scale
    return 1.0 / (1.0 + math.exp(-z))


def stability(
    a_vert: np.ndarray, fs: float, step_time_cv: float, stride_time_s: float,
    speed_mps: float | None,
) -> Stability:
    x = lowpass(a_vert, 10.0, fs)
    lag = int(round(stride_time_s * fs)) if stride_time_s > 0 else 0
    ac = autocorr(x, min(lag + 2, len(x) - 1)) if lag > 0 else np.array([0.0])
    stride_reg = float(ac[lag]) if lag < len(ac) else 0.0
    hr = harmonic_ratio(x, fs, 1.0 / stride_time_s) if stride_time_s > 0 else 0.0
    features = {
        "step_time_cv": float(step_time_cv),
        "stride_regularity": float(np.clip(stride_reg, -1.0, 1.0)),
        "harmonic_ratio": float(hr),
    }
    if speed_mps is not None and speed_mps > 0:
        features["speed_mps"] = float(speed_mps)
    total_w = 0.0
    score = 0.0
    for key, value in features.items():
        anchor, scale, direction = ANCHORS[key]
        score += WEIGHTS[key] * _logistic(value, anchor, scale, direction)
        total_w += WEIGHTS[key]
    index = 100.0 * score / total_w if total_w > 0 else 0.0
    level = "ok" if index >= LOW else "low" if index >= VERY_LOW else "very_low"
    return Stability(index=round(index, 1), level=level, features=features)
