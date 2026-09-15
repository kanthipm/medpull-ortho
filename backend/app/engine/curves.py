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
    # No operation: expected function is the patient's own baseline from day
    # one, so the curve sits at ~0.99 from day 0 and creeps to 1.0 (kept
    # strictly increasing for the monotonicity invariant, but with no
    # recovery shape): every deviation the engine sees is a change from
    # normal, not slow recovery.
    ProcedureType.NONE: CurveParams(0.95, 0.15, -10),
}


def curve_params(procedure: ProcedureType | str | None) -> CurveParams | None:
    """The procedure's curve, or None when there is no surgical recovery to
    expect — a general-care or chronic patient (``ProcedureType.NONE``, or a
    value this table has never heard of).

    Callers get a flat curve for those patients rather than a KeyError, which
    is the difference between "compare activity to the patient's own baseline"
    and a 500 on every read of that patient's chart."""
    try:
        return EXPECTED_CURVES.get(ProcedureType(procedure)) if procedure else None
    except ValueError:
        return None


def has_curve(procedure: ProcedureType | str | None) -> bool:
    return curve_params(procedure) is not None


def curve_mid(procedure: ProcedureType, day: float | np.ndarray) -> float | np.ndarray:
    p = curve_params(procedure)
    days = np.asarray(day, dtype=float)
    if p is None:
        # No surgical recovery to expect: capacity is the patient's own
        # baseline from day one, so the "expected" fraction is 1.0 throughout.
        flat = np.ones_like(days)
        return float(flat) if flat.ndim == 0 else flat
    return p.floor + (1 - p.floor) / (1 + np.exp(-p.r * (days - p.d50)))


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
    """0..1 — how far along the recoverable range a typical patient is at day d.
    A patient with no surgical curve has nothing to recover along: 1.0."""
    p = curve_params(procedure)
    if p is None:
        return 1.0
    mid = float(curve_mid(procedure, day))
    return (mid - p.floor) / (1 - p.floor)
