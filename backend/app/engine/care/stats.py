"""Shared numerics for the care-metrics engine — numpy only, all pure.

No scientific-computing library beyond numpy is used on purpose:
``infra/build-lambda.sh`` fails the build when the heavier one is imported
anywhere under ``app/``, so the handful of special functions the metrics need
— the regularized incomplete gamma behind a chi-square tail, a CUSUM
change-point search, saturating-exponential and exponential-decay fits, a
shrinkage Mahalanobis distance, a 24 h cosinor — are written out here.
Every function takes plain sequences and returns plain Python numbers, so
results serialize straight into the analytics bundle.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _finite_pairs(x, y) -> tuple[np.ndarray, np.ndarray]:
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    mask = np.isfinite(xa) & np.isfinite(ya)
    return xa[mask], ya[mask]


def ols(x, y) -> tuple[float, float, float, float, int]:
    """Ordinary least squares of y on x.

    Returns (slope, intercept, se_slope, r2, n). With fewer than two distinct x
    values the slope is 0 and its standard error infinite, so a caller that
    forms a t-statistic reads "no evidence" rather than a division error.
    """
    xa, ya = _finite_pairs(x, y)
    n = int(len(xa))
    if n == 0:
        return 0.0, 0.0, math.inf, 0.0, 0
    xm, ym = float(xa.mean()), float(ya.mean())
    sxx = float(((xa - xm) ** 2).sum())
    if n < 2 or sxx <= 0:
        return 0.0, ym, math.inf, 0.0, n
    sxy = float(((xa - xm) * (ya - ym)).sum())
    slope = sxy / sxx
    intercept = ym - slope * xm
    resid = ya - (intercept + slope * xa)
    sse = float((resid**2).sum())
    sst = float(((ya - ym) ** 2).sum())
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    se_slope = math.sqrt(sse / (n - 2) / sxx) if n > 2 else math.inf
    return slope, intercept, se_slope, r2, n


def ols_partial(x, t, y) -> tuple[float, float, float, int]:
    """Slope of y on x holding t fixed — y = a + b·x + c·t — with the slope's
    standard error and r². Used where x and y share a slow trend in t (a
    recovering patient walks more AND hurts less every day), so the plain
    slope of y on x would read the recovery itself as a dose-response.
    Returns (slope, se_slope, r2, n)."""
    xa = np.asarray(x, dtype=float)
    ta = np.asarray(t, dtype=float)
    ya = np.asarray(y, dtype=float)
    mask = np.isfinite(xa) & np.isfinite(ta) & np.isfinite(ya)
    xa, ta, ya = xa[mask], ta[mask], ya[mask]
    n = int(len(xa))
    if n < 4:
        return 0.0, math.inf, 0.0, n
    x_mat = np.column_stack([np.ones(n), xa, ta])
    coef, *_ = np.linalg.lstsq(x_mat, ya, rcond=None)
    resid = ya - x_mat @ coef
    sse = float((resid**2).sum())
    sst = float(((ya - ya.mean()) ** 2).sum())
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    try:
        cov = np.linalg.inv(x_mat.T @ x_mat) * (sse / max(n - 3, 1))
        se = math.sqrt(max(float(cov[1, 1]), 0.0))
    except np.linalg.LinAlgError:
        se = math.inf
    return float(coef[1]), se, r2, n


def ols_slope_t(x, y) -> tuple[float, float]:
    """(slope, t) where t = slope / se; t is 0 when the slope has no standard
    error (too few points) and capped at 99 when the fit is exact."""
    slope, _, se, _, n = ols(x, y)
    if n < 3 or not math.isfinite(se):
        return slope, 0.0
    if se <= 1e-12:
        return slope, 99.0 if slope != 0 else 0.0
    return slope, min(99.0, abs(slope) / se) * (1.0 if slope >= 0 else -1.0)


def pearson(x, y) -> float | None:
    """Correlation over the finite pairs, None with fewer than 4 of them or a
    constant input."""
    xa, ya = _finite_pairs(x, y)
    if len(xa) < 4:
        return None
    sx, sy = float(xa.std()), float(ya.std())
    if sx <= 1e-12 or sy <= 1e-12:
        return None
    return float(np.corrcoef(xa, ya)[0, 1])


def xcorr_lag(a, b, max_lag: int = 2) -> tuple[int, float]:
    """The lag (in samples, -max_lag..max_lag) at which b best follows a,
    and the correlation there. Positive lag: b moves after a."""
    aa = np.asarray(a, dtype=float)
    ba = np.asarray(b, dtype=float)
    best_lag, best_r = 0, 0.0
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            xa, ya = aa[: len(aa) - lag] if lag else aa, ba[lag:]
        else:
            xa, ya = aa[-lag:], ba[: len(ba) + lag]
        m = min(len(xa), len(ya))
        r = pearson(xa[:m], ya[:m]) if m >= 4 else None
        if r is not None and (r > best_r or (lag == 0 and best_r == 0.0)):
            best_lag, best_r = lag, r
    return best_lag, float(best_r)


def rolling_mean(series: pd.Series, window: int, min_periods: int = 1) -> pd.Series:
    """Rolling mean on a complete daily grid — the series is reindexed to
    every day between its first and last index so a gap counts as missing
    rather than silently shrinking the window."""
    if len(series) == 0:
        return pd.Series(dtype=float)
    grid = range(int(series.index.min()), int(series.index.max()) + 1)
    full = series.reindex(grid).astype(float)
    return full.rolling(window, min_periods=min_periods).mean()


def _cusum_split(values: np.ndarray, min_seg: int, min_shift_sd: float) -> int | None:
    n = len(values)
    if n < 2 * min_seg:
        return None
    centered = values - values.mean()
    cusum = np.cumsum(centered)
    # the split goes AFTER index k; both segments must keep min_seg points
    candidates = range(min_seg - 1, n - min_seg)
    k = max(candidates, key=lambda i: abs(cusum[i]))
    left, right = values[: k + 1], values[k + 1 :]
    pooled = math.sqrt(
        ((left.var(ddof=1) * (len(left) - 1)) + (right.var(ddof=1) * (len(right) - 1)))
        / max(n - 2, 1)
    )
    scale = max(pooled, 1e-9 * max(abs(values).max(), 1.0), 1e-12)
    shift = abs(right.mean() - left.mean()) / scale
    # Two guards: the shift must be material (min_shift_sd) AND unlikely to be
    # noise given the segment sizes — a Welch-style t of the two means. Without
    # the second, recursing into a segment of pure noise reliably "finds" a
    # one-SD split somewhere in it.
    t_stat = shift / math.sqrt(1.0 / len(left) + 1.0 / len(right))
    if shift < min_shift_sd or t_stat < 2.5:
        return None
    return k + 1


def binary_segmentation(values, min_seg: int = 4, min_shift_sd: float = 1.0) -> list[int]:
    """Indices where the mean shifts: the single most significant CUSUM split,
    then the same search inside each half (depth 2). A split counts when the
    two segment means differ by at least ``min_shift_sd`` pooled within-segment
    standard deviations. Returned indices are the first index of the new
    segment, ascending."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    found: list[int] = []

    def _search(lo: int, hi: int, depth: int) -> None:
        if depth > 2:
            return
        k = _cusum_split(v[lo:hi], min_seg, min_shift_sd)
        if k is None:
            return
        found.append(lo + k)
        _search(lo, lo + k, depth + 1)
        _search(lo + k, hi, depth + 1)

    _search(0, len(v), 1)
    return sorted(found)


def fit_saturating(
    days, y, k_grid: np.ndarray | None = None, seed: int = 0
) -> dict[str, float | tuple[float, float]]:
    """Fit y = y0 + A(1 - exp(-k d)) by a grid over k with linear least
    squares for (y0, A) at each k. The 90 % CI on k comes from a residual
    bootstrap (40 resamples) — cheap at these sizes."""
    d, yy = _finite_pairs(days, y)
    grid = np.linspace(0.02, 0.4, 39) if k_grid is None else np.asarray(k_grid, dtype=float)
    if len(d) < 3:
        return {"k": 0.0, "A": 0.0, "y0": float(yy.mean()) if len(yy) else 0.0,
                "asymptote": float(yy.mean()) if len(yy) else 0.0, "r2": 0.0,
                "k_ci": (0.0, 0.0)}

    def _fit(target: np.ndarray) -> tuple[float, float, float, float]:
        best = None
        for k in grid:
            basis = 1.0 - np.exp(-k * d)
            x_mat = np.column_stack([np.ones_like(d), basis])
            coef, *_ = np.linalg.lstsq(x_mat, target, rcond=None)
            sse = float(((x_mat @ coef - target) ** 2).sum())
            if best is None or sse < best[0]:
                best = (sse, float(k), float(coef[0]), float(coef[1]))
        return best  # type: ignore[return-value]

    sse, k, y0, amp = _fit(yy)
    sst = float(((yy - yy.mean()) ** 2).sum())
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    fitted = y0 + amp * (1.0 - np.exp(-k * d))
    resid = yy - fitted
    rng = np.random.default_rng(seed)
    ks: list[float] = []
    for _ in range(40):
        sample = fitted + rng.choice(resid, size=len(resid), replace=True)
        ks.append(_fit(sample)[1])
    lo, hi = float(np.percentile(ks, 5)), float(np.percentile(ks, 95))
    return {"k": k, "A": amp, "y0": y0, "asymptote": y0 + amp, "r2": float(r2), "k_ci": (lo, hi)}


def fit_exp_decay(days, y) -> dict[str, float]:
    """Fit y = c + a·exp(-k d): a grid over the floor c in [0, min(y)) with a
    linear fit of log(y - c) at each. Chosen by SSE in the original units."""
    d, yy = _finite_pairs(days, y)
    if len(d) < 3:
        return {"a": 0.0, "k": 0.0, "c": float(yy.mean()) if len(yy) else 0.0, "r2": 0.0}
    floor = float(yy.min())
    best: tuple[float, float, float, float] | None = None
    # The floor grid clusters just under min(y): a series that has settled
    # sits right on its floor, and a coarse grid that stops well short of it
    # reads that as a slow, still-ongoing decay.
    for c in floor * (1.0 - np.geomspace(1e-3, 1.0, 25)) if floor > 0 else [0.0]:
        shifted = yy - c
        if (shifted <= 0).any():
            continue
        slope, intercept, _, _, _ = ols(d, np.log(shifted))
        a, k = math.exp(intercept), -slope
        sse = float(((c + a * np.exp(-k * d) - yy) ** 2).sum())
        if best is None or sse < best[0]:
            best = (sse, a, k, float(c))
    if best is None:
        return {"a": 0.0, "k": 0.0, "c": floor, "r2": 0.0}
    sse, a, k, c = best
    sst = float(((yy - yy.mean()) ** 2).sum())
    return {"a": a, "k": k, "c": c, "r2": (1.0 - sse / sst) if sst > 0 else 0.0}


def mahalanobis(z_today, z_hist) -> tuple[float, list[float]]:
    """Distance of today's k-vector from a history of n×k vectors, using a
    shrinkage covariance S = (1-λ)·cov + λ·I with λ = 0.5 (λ = 1 when fewer
    than five history rows, i.e. plain Euclidean). Contributions are each
    signal's share of zᵀS⁻¹z, clipped at zero and normalized."""
    z = np.asarray(z_today, dtype=float)
    hist = np.asarray(z_hist, dtype=float)
    k = len(z)
    if hist.ndim != 2 or hist.shape[0] < 5 or hist.shape[1] != k:
        s_mat = np.eye(k)
    else:
        cov = np.cov(hist, rowvar=False, ddof=1)
        cov = np.atleast_2d(cov)
        s_mat = 0.5 * cov + 0.5 * np.eye(k)
    try:
        s_inv_z = np.linalg.solve(s_mat, z)
    except np.linalg.LinAlgError:
        s_inv_z = z
    quad = float(z @ s_inv_z)
    d = math.sqrt(max(quad, 0.0))
    parts = np.clip(z * s_inv_z, 0.0, None)
    total = float(parts.sum())
    contributions = [float(p / total) if total > 0 else 0.0 for p in parts]
    return d, contributions


def _gammln(a: float) -> float:
    return math.lgamma(a)


def _gser(a: float, x: float) -> float:
    """Series for the regularized lower incomplete gamma P(a, x), x < a + 1."""
    ap = a
    total = term = 1.0 / a
    for _ in range(500):
        ap += 1.0
        term *= x / ap
        total += term
        if abs(term) < abs(total) * 1e-14:
            break
    return total * math.exp(-x + a * math.log(x) - _gammln(a))


def _gcf(a: float, x: float) -> float:
    """Continued fraction for the regularized upper incomplete gamma Q(a, x),
    x >= a + 1 (Numerical Recipes gcf, modified Lentz)."""
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return math.exp(-x + a * math.log(x) - _gammln(a)) * h


def gammq(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x)."""
    if x <= 0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gser(a, x)
    return _gcf(a, x)


def chi2_sf(x: float, k: int) -> float:
    """Survival function of the chi-square distribution with k degrees of
    freedom: P(X > x) = Q(k/2, x/2)."""
    if k <= 0:
        return 1.0
    return float(min(1.0, max(0.0, gammq(k / 2.0, x / 2.0))))


def cosinor(hours, values) -> dict[str, float]:
    """24 h cosinor by linear least squares on cos/sin: mesor, amplitude,
    acrophase (hour of the fitted peak, 0-24) and r2."""
    h, v = _finite_pairs(hours, values)
    if len(h) < 4:
        return {"mesor": float(v.mean()) if len(v) else 0.0, "amplitude": 0.0,
                "acrophase_h": 0.0, "r2": 0.0}
    omega = 2.0 * math.pi / 24.0
    x_mat = np.column_stack([np.ones_like(h), np.cos(omega * h), np.sin(omega * h)])
    coef, *_ = np.linalg.lstsq(x_mat, v, rcond=None)
    mesor, beta, gamma = (float(c) for c in coef)
    amplitude = math.hypot(beta, gamma)
    phase = math.atan2(gamma, beta)  # cos(ωh - φ) peaks at h = φ/ω
    acrophase = (phase / omega) % 24.0
    fitted = x_mat @ coef
    sse = float(((v - fitted) ** 2).sum())
    sst = float(((v - v.mean()) ** 2).sum())
    return {"mesor": mesor, "amplitude": amplitude, "acrophase_h": float(acrophase),
            "r2": (1.0 - sse / sst) if sst > 0 else 0.0}


def interdaily_stability(hourly) -> float:
    """Van Someren interdaily stability over a days×24 matrix (NaN = missing):
    the variance of the mean 24 h profile relative to the total variance.
    1.0 is a perfectly repeated day, 0 is noise."""
    m = np.asarray(hourly, dtype=float)
    if m.ndim != 2 or m.shape[1] == 0:
        return 0.0
    finite = np.isfinite(m)
    n = int(finite.sum())
    if n < 2:
        return 0.0
    grand = float(np.nanmean(m))
    hourly_means = np.nanmean(m, axis=0)
    hourly_means = hourly_means[np.isfinite(hourly_means)]
    p = len(hourly_means)
    denom = float(np.nansum((m - grand) ** 2)) * p
    if denom <= 0:
        return 0.0
    return float(min(1.0, max(0.0, n * float(((hourly_means - grand) ** 2).sum()) / denom)))
