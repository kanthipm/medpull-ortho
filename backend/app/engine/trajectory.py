"""Functional recovery trajectory vs the procedure's expected curve.

The functional index is activity recovered relative to the patient's own
pre-op norm: steps ratio (weight 0.7) and walking-speed ratio (0.3, Apple
patients only — weights renormalize when a component is missing). An on-track
patient's index sits on the expected curve by construction.

A component whose baseline was anchored on post-op days is NOT in pre-op
units, and dividing it straight into the curve reads a large positive
percentage however badly the recovery is going. It is converted first:
multiplying by the curve's own level on the anchor days restores the unit,
because the curve says what fraction of pre-op capacity a patient at that
point in recovery typically holds. What survives that conversion is a claim
about pace rather than capacity, so an anchored index may report BEHIND but
never AHEAD — a reassuring verdict resting on an acute-phase anchor is exactly
the reading this module is here to prevent.
"""

import numpy as np
import pandas as pd

from app.engine.curves import curve_mid, expected_curve
from app.engine.deviation import curve_anchor
from app.engine.types import Baseline, TrajectoryResult
from app.models.enums import MetricType as M
from app.models.enums import ProcedureType, TrajectoryState

WEIGHTS = {M.STEPS: 0.7, M.WALKING_SPEED: 0.3}
BEHIND_PCT = -12.0
AHEAD_PCT = 10.0
MIN_DAYS = 4


def functional_index(
    series: dict[str, pd.Series],
    baselines: dict[str, Baseline],
    procedure: ProcedureType,
) -> pd.Series:
    components: list[tuple[float, pd.Series]] = []
    for metric, weight in WEIGHTS.items():
        s = series.get(str(metric))
        b = baselines.get(str(metric))
        if s is None or b is None or b.mean <= 0:
            continue
        anchor = curve_anchor(b, procedure)
        if anchor is None:
            continue
        post = s[s.index >= 0]
        if len(post) == 0:
            continue
        # anchor is 1.0 for a pre-op baseline and the curve's level on the
        # anchor days otherwise, which is what puts both on the one scale the
        # expected curve is drawn in.
        components.append((weight, ((post / b.mean) * anchor).clip(upper=1.2)))
    if not components:
        return pd.Series(dtype=float)

    total_w = sum(w for w, _ in components)
    combined = sum((w / total_w) * s for w, s in components)
    return combined.dropna().sort_index()


def is_anchored(baselines: dict[str, Baseline]) -> bool:
    """True when every component of the index came from a post-op anchor —
    the case where AHEAD is withheld."""
    used = [baselines[str(m)] for m in WEIGHTS if str(m) in baselines]
    return bool(used) and not any(b.is_preop for b in used)


def change_point(residual: pd.Series) -> int | None:
    """Post-op day of the largest sustained mean shift in the RESIDUAL
    (index minus expected curve). Detecting on the raw index would flag every
    normal recovery — the whole curve is one long upward 'shift'."""
    if len(residual) < 6:
        return None
    values = residual.to_numpy(dtype=float)
    days = residual.index.to_numpy()
    centered = values - values.mean()
    cusum = np.cumsum(centered)
    k = int(np.argmax(np.abs(cusum)))
    left, right = values[: k + 1], values[k + 1 :]
    if len(left) < 2 or len(right) < 2:
        return None
    if abs(right.mean() - left.mean()) < 0.05:
        return None
    return int(days[k + 1])


def compare(
    index: pd.Series,
    procedure: ProcedureType,
    postop_day: int,
    anchored: bool = False,
) -> TrajectoryResult:
    """Compare the functional index to the procedure's expected curve.

    `anchored` marks an index built entirely from post-op anchors: the
    comparison still detects a patient falling behind their own expected pace,
    but it rests on the assumption that their early post-op level was itself
    normal, which is too thin to hang a reassuring AHEAD on. Such an index
    reports ON_TRACK at worst-case best.
    """
    all_days = np.arange(0, max(postop_day, 1) + 1)
    expected = expected_curve(procedure, all_days)

    if len(index) < MIN_DAYS:
        return TrajectoryResult(
            state=TrajectoryState.UNKNOWN,
            pct=None,
            change_point_day=None,
            actual=[{"day": int(d), "v": round(float(v), 3)} for d, v in index.items()],
            expected=expected,
            anchored=anchored,
        )

    all_mids = pd.Series(
        [float(curve_mid(procedure, int(d))) for d in index.index], index=index.index
    )
    residual = index - all_mids

    recent = index.iloc[-5:]
    mids = np.array([float(curve_mid(procedure, int(d))) for d in recent.index])
    pct = float(np.mean((recent.to_numpy() - mids) / mids) * 100.0)

    if pct <= BEHIND_PCT:
        state = TrajectoryState.BEHIND
    elif pct >= AHEAD_PCT and not anchored:
        state = TrajectoryState.AHEAD
    else:
        state = TrajectoryState.ON_TRACK

    return TrajectoryResult(
        state=state,
        pct=round(pct, 1),
        change_point_day=change_point(residual),
        actual=[{"day": int(d), "v": round(float(v), 3)} for d, v in index.items()],
        expected=expected,
        anchored=anchored,
    )
