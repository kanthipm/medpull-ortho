"""The care engine's numerics, checked against known values — numpy only, so
each helper stands in for the scipy routine the Lambda build forbids."""

import numpy as np

from app.engine.care.stats import (
    binary_segmentation,
    chi2_sf,
    cosinor,
    fit_exp_decay,
    fit_saturating,
    interdaily_stability,
    mahalanobis,
    ols,
    ols_partial,
    ols_slope_t,
    pearson,
    rolling_mean,
    xcorr_lag,
)


def test_chi2_sf_matches_known_tails():
    assert abs(chi2_sf(3.84, 1) - 0.05) < 1e-3
    assert abs(chi2_sf(9.21, 2) - 0.01) < 1e-3
    assert abs(chi2_sf(11.07, 5) - 0.05) < 1e-3
    assert chi2_sf(0.0, 3) == 1.0
    assert 0.0 <= chi2_sf(200.0, 3) < 1e-12


def test_fit_saturating_recovers_the_rate_on_a_clean_curve():
    days = np.arange(0, 40, dtype=float)
    y = 0.3 + 0.6 * (1 - np.exp(-0.1 * days))
    fit = fit_saturating(days, y)
    assert abs(fit["k"] - 0.1) < 1e-6
    assert abs(fit["asymptote"] - 0.9) < 1e-6
    assert fit["r2"] > 0.999
    lo, hi = fit["k_ci"]
    assert lo <= 0.1 <= hi


def test_binary_segmentation_finds_an_injected_shift():
    rng = np.random.default_rng(3)
    values = np.concatenate([rng.normal(0, 1, 14), rng.normal(4, 1, 12)])
    splits = binary_segmentation(values)
    assert 14 in splits
    # pure noise: no split survives the significance guard
    assert binary_segmentation(rng.normal(0, 1, 30)) == []


def test_mahalanobis_with_identity_covariance_is_euclidean():
    d, contributions = mahalanobis([3.0, 4.0], np.zeros((2, 2)))  # <5 rows -> identity
    assert abs(d - 5.0) < 1e-9
    assert abs(sum(contributions) - 1.0) < 1e-9
    assert contributions[1] > contributions[0]


def test_mahalanobis_discounts_a_direction_the_history_already_varies_in():
    rng = np.random.default_rng(7)
    hist = np.column_stack([rng.normal(0, 3, 30), rng.normal(0, 0.2, 30)])
    d_wide, _ = mahalanobis([3.0, 0.0], hist)
    d_narrow, _ = mahalanobis([0.0, 3.0], hist)
    assert d_wide < d_narrow


def test_cosinor_recovers_amplitude_and_acrophase():
    hours = np.arange(24, dtype=float)
    values = 5 + 3 * np.cos(2 * np.pi * (hours - 14) / 24)
    fit = cosinor(hours, values)
    assert abs(fit["mesor"] - 5) < 1e-9
    assert abs(fit["amplitude"] - 3) < 1e-9
    assert abs(fit["acrophase_h"] - 14) < 1e-6
    assert fit["r2"] > 0.999


def test_interdaily_stability_is_one_for_a_repeated_day_and_low_for_noise():
    hours = np.arange(24, dtype=float)
    profile = 5 + 3 * np.cos(2 * np.pi * (hours - 14) / 24)
    assert abs(interdaily_stability(np.tile(profile, (5, 1))) - 1.0) < 1e-9
    noise = np.random.default_rng(1).normal(0, 1, (14, 24))
    assert interdaily_stability(noise) < 0.3


def test_ols_and_partial_slopes():
    x = np.arange(10, dtype=float)
    slope, intercept, se, r2, n = ols(x, 2 * x + 1)
    assert abs(slope - 2) < 1e-9 and abs(intercept - 1) < 1e-9 and n == 10
    assert se < 1e-6 and r2 > 0.999
    # y depends on t, not on x: holding t fixed removes the spurious slope
    t = np.arange(20, dtype=float)
    x2 = t * 100 + np.array([(-1) ** i * 20 for i in range(20)])
    y = 8 - 0.3 * t
    assert abs(ols(x2, y)[0]) > 0.001  # raw slope reads the trend
    assert abs(ols_partial(x2, t, y)[0]) < 1e-9
    _, t_stat = ols_slope_t(x, 2 * x + 1)
    assert t_stat == 99.0


def test_pearson_and_lagged_correlation():
    a = [0, 1, 2, 3, 4, 5, 4, 3, 2, 1]
    b = [0, 0, 1, 2, 3, 4, 5, 4, 3, 2]
    assert abs(pearson(a, a) - 1.0) < 1e-9
    assert pearson([1, 1, 1, 1], [1, 2, 3, 4]) is None
    assert pearson([1, 2], [3, 4]) is None
    lag, r = xcorr_lag(a, b)
    assert lag == 1 and r > 0.99


def test_fit_exp_decay_and_rolling_mean():
    days = np.arange(2, 30, dtype=float)
    fit = fit_exp_decay(days, 8 + 10 * np.exp(-0.15 * days))
    assert abs(fit["k"] - 0.15) < 0.02
    assert abs(fit["c"] - 8) < 0.5
    import pandas as pd

    series = pd.Series([1.0, 2.0, 4.0], index=[0, 1, 3])  # day 2 missing
    smoothed = rolling_mean(series, 2, min_periods=1)
    assert list(smoothed.index) == [0, 1, 2, 3]
    assert smoothed.loc[2] == 2.0  # only day 1 in the window
    assert smoothed.loc[3] == 4.0
