"""Signal-processing primitives for the mobility engine, in numpy only.

scipy is excluded from the Lambda artifact (infra/build-lambda.sh), so the
filters, peak finder and spectral helpers every gait algorithm needs are
implemented here from first principles. Each one is small enough to be read
and checked line by line, which is the point: a reviewer can see exactly what
"band-pass 0.5-3.5 Hz" means without opening a library.

Conventions
- Signals are 1-D float arrays sampled uniformly at ``fs`` Hz.
- Filters are second-order Butterworth sections (RBJ audio-EQ cookbook
  coefficients, Q = 1/sqrt(2)) applied forward and backward (``filtfilt``),
  so the effective response is fourth-order and zero-phase: filtering never
  shifts a heel strike in time.
"""

from __future__ import annotations

import math

import numpy as np

SQRT_HALF = 1.0 / math.sqrt(2.0)


# --- filters -------------------------------------------------------------------


def biquad(kind: str, fc: float, fs: float, q: float = SQRT_HALF) -> tuple[np.ndarray, np.ndarray]:
    """Second-order low- or high-pass coefficients (b, a), normalized so a[0] = 1.

    Robert Bristow-Johnson's cookbook formulae. fc is the -3 dB corner in Hz;
    it is clamped below Nyquist so a caller can never request an unstable
    section.
    """
    fc = min(max(float(fc), 1e-3), 0.49 * fs)
    w0 = 2.0 * math.pi * fc / fs
    cos_w0, sin_w0 = math.cos(w0), math.sin(w0)
    alpha = sin_w0 / (2.0 * q)
    if kind == "low":
        b0 = (1.0 - cos_w0) / 2.0
        b1 = 1.0 - cos_w0
        b2 = (1.0 - cos_w0) / 2.0
    elif kind == "high":
        b0 = (1.0 + cos_w0) / 2.0
        b1 = -(1.0 + cos_w0)
        b2 = (1.0 + cos_w0) / 2.0
    else:
        raise ValueError(f"unknown filter kind {kind!r}")
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    b = np.array([b0, b1, b2], dtype=float) / a0
    a = np.array([1.0, a1 / a0, a2 / a0], dtype=float)
    return b, a


def lfilter(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Direct-form II transposed IIR filter (causal, one pass)."""
    x = np.asarray(x, dtype=float)
    y = np.empty_like(x)
    z1 = z2 = 0.0
    b0, b1, b2 = float(b[0]), float(b[1]), float(b[2])
    a1, a2 = float(a[1]), float(a[2])
    for i, xi in enumerate(x):
        yi = b0 * xi + z1
        z1 = b1 * xi - a1 * yi + z2
        z2 = b2 * xi - a2 * yi
        y[i] = yi
    return y


def filtfilt(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Zero-phase filtering: forward pass, backward pass, over a reflected
    edge pad so the transient never lands on the data."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 4:
        return x.copy()
    pad = min(3 * max(len(a), len(b)) * 4, n - 1)
    left = 2.0 * x[0] - x[pad:0:-1]
    right = 2.0 * x[-1] - x[-2:-pad - 2:-1]
    ext = np.concatenate([left, x, right])
    y = lfilter(b, a, ext)
    y = lfilter(b, a, y[::-1])[::-1]
    return y[pad:pad + n]


def lowpass(x: np.ndarray, fc: float, fs: float) -> np.ndarray:
    b, a = biquad("low", fc, fs)
    return filtfilt(b, a, x)


def highpass(x: np.ndarray, fc: float, fs: float) -> np.ndarray:
    b, a = biquad("high", fc, fs)
    return filtfilt(b, a, x)


def bandpass(x: np.ndarray, lo: float, hi: float, fs: float) -> np.ndarray:
    return lowpass(highpass(x, lo, fs), hi, fs)


# --- resampling ----------------------------------------------------------------


def resample_uniform(t: np.ndarray, x: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Linear interpolation of an irregularly timestamped signal onto a
    uniform grid at fs Hz. ``x`` may be (N,) or (N, k). Returns (t_uniform, x_uniform)."""
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    if len(t) < 2:
        return t, x
    order = np.argsort(t, kind="stable")
    t, x = t[order], x[order]
    keep = np.concatenate([[True], np.diff(t) > 0])  # drop duplicate stamps
    t, x = t[keep], x[keep]
    grid = np.arange(t[0], t[-1], 1.0 / fs)
    if x.ndim == 1:
        return grid, np.interp(grid, t, x)
    cols = [np.interp(grid, t, x[:, j]) for j in range(x.shape[1])]
    return grid, np.stack(cols, axis=1)


# --- peaks ---------------------------------------------------------------------


def find_peaks(x: np.ndarray, min_distance: int, min_height: float | None = None) -> np.ndarray:
    """Indices of local maxima at least ``min_distance`` samples apart.

    Candidates are strict local maxima (greater than both neighbours). When
    two candidates sit closer than min_distance, the taller one wins — the
    same greedy rule scipy uses — so a double bump at one heel strike counts
    once.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 3:
        return np.array([], dtype=int)
    cand = np.where((x[1:-1] > x[:-2]) & (x[1:-1] >= x[2:]))[0] + 1
    if min_height is not None:
        cand = cand[x[cand] >= min_height]
    if len(cand) == 0 or min_distance <= 1:
        return cand
    order = cand[np.argsort(-x[cand], kind="stable")]
    keep = np.ones(n, dtype=bool)
    chosen: list[int] = []
    for idx in order:
        if not keep[idx]:
            continue
        chosen.append(int(idx))
        lo, hi = max(0, idx - min_distance + 1), min(n, idx + min_distance)
        keep[lo:hi] = False
    return np.array(sorted(chosen), dtype=int)


# --- spectral + correlation ----------------------------------------------------


def autocorr(x: np.ndarray, max_lag: int) -> np.ndarray:
    """Unbiased, normalized autocorrelation for lags 0..max_lag (lag 0 = 1)."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    n = len(x)
    denom = float(np.dot(x, x))
    if n < 2 or denom <= 0:
        return np.zeros(max_lag + 1)
    out = np.empty(max_lag + 1)
    for lag in range(max_lag + 1):
        if lag >= n:
            out[lag] = 0.0
            continue
        out[lag] = float(np.dot(x[: n - lag], x[lag:])) / denom * (n / (n - lag))
    return out


def dominant_frequency(
    x: np.ndarray, fs: float, fmin: float, fmax: float
) -> tuple[float, float]:
    """(frequency of the largest spectral peak inside [fmin, fmax], fraction
    of total power that lies inside that band). Hann-windowed rFFT."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 8:
        return 0.0, 0.0
    w = np.hanning(n)
    spec = np.abs(np.fft.rfft((x - x.mean()) * w)) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    total = float(spec[1:].sum())
    band = (freqs >= fmin) & (freqs <= fmax)
    if total <= 0 or not band.any():
        return 0.0, 0.0
    i = int(np.argmax(np.where(band, spec, 0.0)))
    return float(freqs[i]), float(spec[band].sum() / total)


def harmonic_ratio(x: np.ndarray, fs: float, stride_hz: float, n_harmonics: int = 20) -> float:
    """Harmonic ratio of a stride-periodic signal (Menz et al. 2003).

    Sum of the amplitudes at even multiples of the stride frequency (the
    in-phase, symmetric components) divided by the sum at odd multiples. A
    smooth, symmetric gait pushes power into the even harmonics; a limp adds
    odd ones. Amplitudes are read from the rFFT bin nearest each harmonic.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 16 or stride_hz <= 0:
        return 0.0
    spec = np.abs(np.fft.rfft((x - x.mean()) * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    even = odd = 0.0
    for k in range(1, n_harmonics + 1):
        f = k * stride_hz
        if f >= fs / 2:
            break
        amp = float(spec[int(np.argmin(np.abs(freqs - f)))])
        if k % 2 == 0:
            even += amp
        else:
            odd += amp
    return even / odd if odd > 0 else 0.0


def trapezoid_cumulative(x: np.ndarray, dt: float) -> np.ndarray:
    """Cumulative trapezoidal integral, same length as x, starting at 0."""
    x = np.asarray(x, dtype=float)
    out = np.zeros_like(x)
    if len(x) > 1:
        out[1:] = np.cumsum((x[1:] + x[:-1]) * 0.5 * dt)
    return out


def robust_sd(x: np.ndarray) -> float:
    """1.4826 x median absolute deviation — an SD that one outlier cannot move."""
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return 0.0
    med = float(np.median(x))
    return 1.4826 * float(np.median(np.abs(x - med)))
