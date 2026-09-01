"""Expected recovery curves per procedure.

A parametric logistic models the fraction of pre-op functional capacity a
typical patient regains by post-op day d:

    f(d) = floor + (1 - floor) / (1 + exp(-r * (d - d50)))

floor  — immediate post-op functional level (day-0 capacity)
r      — recovery rate
d50    — day at which half the recoverable capacity is regained

Parameters are demo-calibrated from published rehab timelines (TKA slowest
early, ACL a long tail, meniscus fastest). The seed generator shapes on-track
patients along these same curves, so "on track" is on track by construction.
"""

from dataclasses import dataclass

import numpy as np

from app.models.enums import ProcedureType

CI_WIDTH = 0.08


@dataclass(frozen=True)
class CurveParams:
    floor: float
    r: float
    d50: float


EXPECTED_CURVES: dict[ProcedureType, CurveParams] = {
    ProcedureType.TKA: CurveParams(0.25, 0.10, 21),
    ProcedureType.THA: CurveParams(0.30, 0.12, 17),
    ProcedureType.ACL: CurveParams(0.35, 0.07, 28),
    ProcedureType.ROTATOR_CUFF: CurveParams(0.30, 0.06, 35),
    ProcedureType.LUMBAR: CurveParams(0.25, 0.08, 25),
    ProcedureType.ANKLE: CurveParams(0.25, 0.09, 24),
    ProcedureType.MENISCUS: CurveParams(0.40, 0.15, 10),
}


def curve_mid(procedure: ProcedureType, day: float | np.ndarray) -> float | np.ndarray:
    p = EXPECTED_CURVES[procedure]
    return p.floor + (1 - p.floor) / (1 + np.exp(-p.r * (np.asarray(day, dtype=float) - p.d50)))


def expected_curve(
    procedure: ProcedureType, days: np.ndarray
) -> list[dict[str, float]]:
    """[{day, lo, mid, hi}] for the trajectory chart and comparison."""
    mid = np.asarray(curve_mid(procedure, days), dtype=float)
    lo = np.clip(mid - CI_WIDTH, 0.0, 1.0)
    hi = np.clip(mid + CI_WIDTH, 0.0, 1.1)
    return [
        {
            "day": int(day),
            "lo": round(float(low), 3),
            "mid": round(float(centre), 3),
            "hi": round(float(high), 3),
        }
        for day, low, centre, high in zip(days, lo, mid, hi)
    ]


def recovery_progress(procedure: ProcedureType, day: float) -> float:
    """0..1 — how far along the recoverable range a typical patient is at day d."""
    p = EXPECTED_CURVES[procedure]
    mid = float(curve_mid(procedure, day))
    return (mid - p.floor) / (1 - p.floor)
