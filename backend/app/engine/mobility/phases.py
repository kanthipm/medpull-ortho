"""Gait phases from the thigh gyroscope: step asymmetry and double support.

A phone in a front trouser pocket rides on the thigh, and the thigh's
angular velocity about the mediolateral axis is a clean, well-described
signal (Aminian et al. 2002 for the shank; the thigh version is used in
exoskeleton phase detection). Over one stride the thigh:

  heel strike (HS)    the thigh is at peak flexion; angular velocity
                      crosses from positive (flexing) to NEGATIVE
  stance              the thigh extends: angular velocity negative
  ~50 % of the cycle  peak hip extension: angular velocity crosses back to
                      POSITIVE. This reversal coincides with the OTHER foot's
                      heel strike (c), which lands at ~50 % in symmetric gait.
  pre-swing / swing   the thigh flexes fast: the large positive lobe, whose
                      steepest rise is the leg being unloaded at toe-off (TO)
  next HS             the next positive-to-negative zero crossing

So from one thigh the model reads, per stride (HS_k-1 -> HS_k):
  stance                   HS_k-1 -> TO_k;  swing  TO_k -> HS_k
  which foot each accelerometer contact belongs to: a contact within
  0.15 s of a thigh heel strike is the instrumented leg's, the rest are the
  other leg's — so both feet's step times come from one detector.

Outputs
- step-time asymmetry index  |mean ipsi - mean contra| / mean(all) x 100 [%]
  (Robinson's symmetry index, the form most TKA gait papers report),
  SIGNED positive when the instrumented leg's step is the slower one, and
  carried with the pocket side so the console can say which leg.
- double support %  100 x (1 - 2 * swing / stride). Derivation: with both
  feet on the ground except during each swing, single support per stride is
  swing_ipsi + swing_contra; assuming the contralateral swing equals the one
  measured, double support = stride - 2 * swing. Healthy walking (swing ~40 %
  of stride) gives ~20 %, the textbook figure.

Both assume the sagittal axis is the gyroscope's principal axis over the
bout (PCA), and the sign of that axis is chosen so that the faster lobe
(swing) is positive. What this does NOT do: it does not measure the
contralateral swing, so an asymmetric patient's double support carries the
instrumented side's bias — the same limitation Apple documents for the
iPhone. Record the pocket side, alternate it, and the two estimates bracket
the truth.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.engine.mobility.dsp import find_peaks, lowpass

GYRO_LP_HZ = 6.0
MIN_SWING_PEAK_S = 0.5
PEAK_FRACTION = 0.5
MIN_STRIDES = 4
SWING_FRACTION_RANGE = (0.20, 0.60)
LABEL_TOLERANCE_S = 0.15


@dataclass
class Phases:
    heel_strikes: np.ndarray      # sample indices (ipsilateral)
    contra_strikes: np.ndarray    # sample indices (contralateral, one per stride)
    toe_offs: np.ndarray          # sample indices (ipsilateral, one per stride)
    ipsi_step_s: np.ndarray
    contra_step_s: np.ndarray
    swing_s: np.ndarray
    stride_s: np.ndarray
    asymmetry_pct: float          # signed: + when the instrumented leg steps slower
    double_support_pct: float
    n_strides: int

    @property
    def valid(self) -> bool:
        if self.n_strides < MIN_STRIDES:
            return False
        frac = float(np.mean(self.swing_s / self.stride_s))
        return SWING_FRACTION_RANGE[0] <= frac <= SWING_FRACTION_RANGE[1]


def sagittal_axis(gyro: np.ndarray) -> np.ndarray:
    """Unit vector of the largest-variance direction of angular velocity."""
    g = np.asarray(gyro, dtype=float)
    g = g - g.mean(axis=0)
    cov = g.T @ g / max(len(g) - 1, 1)
    vals, vecs = np.linalg.eigh(cov)
    axis = vecs[:, int(np.argmax(vals))]
    return axis / (np.linalg.norm(axis) or 1.0)


def _zero_crossings(w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    s = np.sign(w)
    s[s == 0] = 1
    d = np.diff(s)
    up = np.where(d > 0)[0] + 1      # negative -> positive
    down = np.where(d < 0)[0] + 1    # positive -> negative
    return up, down


def phases(gyro: np.ndarray, fs: float, step_peaks: np.ndarray | None = None) -> Phases | None:
    """Gait phases for one bout.

    ``step_peaks`` are the accelerometer's foot-contact instants for the same
    bout (both feet). When given, the gyroscope's heel strikes are used only
    to LABEL them — a contact within LABEL_TOLERANCE_S of a thigh heel strike
    is the instrumented leg's — and both feet's step times come from the
    same accelerometer detector, so the asymmetry is not biased by the two
    sensors' different timing. Without them the reversal crossing stands in
    for the contralateral heel strike.
    """
    if gyro is None or len(gyro) < int(3 * fs):
        return None
    axis = sagittal_axis(gyro)
    w = lowpass(gyro @ axis, GYRO_LP_HZ, fs)
    # Orient the axis so the faster (swing) lobe is positive.
    pos = w[w > 0]
    neg = -w[w < 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    if float(np.percentile(neg, 95)) > float(np.percentile(pos, 95)):
        w = -w
    min_dist = int(MIN_SWING_PEAK_S * fs)
    swing_peaks = find_peaks(w, min_dist)
    if len(swing_peaks) < MIN_STRIDES + 1:
        return None
    heights = w[swing_peaks]
    swing_peaks = swing_peaks[heights >= PEAK_FRACTION * float(np.median(heights))]
    up, down = _zero_crossings(w)
    dw = np.gradient(w) * fs

    hs: list[int] = []
    contra: list[int] = []
    to: list[int] = []
    for p in swing_peaks:
        after = down[down > p]
        before = up[up < p]
        if len(after) == 0 or len(before) == 0:
            continue
        h, c = int(after[0]), int(before[-1])
        # Toe-off: the steepest rise of the flexion lobe between the reversal
        # and the swing peak.
        seg = dw[c:p + 1]
        t_off = c + int(np.argmax(seg)) if len(seg) else c
        hs.append(h)
        contra.append(c)
        to.append(t_off)
    if len(hs) < MIN_STRIDES + 1:
        return None
    hs_a, c_a, to_a = np.array(hs), np.array(contra), np.array(to)
    # Swing peak k sits inside the stride that ENDS at HS_k: the stride runs
    # HS_k-1 -> HS_k, the reversal c_k and the toe-off TO_k fall inside it.
    stride = np.diff(hs_a) / fs                  # HS_k-1 -> HS_k
    swing = (hs_a[1:] - to_a[1:]) / fs           # TO_k -> HS_k
    ok = (stride > 0.5) & (stride < 3.0) & (swing > 0)
    if ok.sum() < MIN_STRIDES:
        return None
    stride, swing = stride[ok], swing[ok]

    labelled = _labelled_step_times(step_peaks, hs_a, fs) if step_peaks is not None else None
    if labelled is not None:
        ipsi, contra_step = labelled
    else:
        ipsi = ((hs_a[1:] - c_a[1:]) / fs)[ok]           # c_k -> HS_k
        contra_step = ((c_a[1:] - hs_a[:-1]) / fs)[ok]   # HS_k-1 -> c_k
    mean_all = float((ipsi.mean() + contra_step.mean()) / 2.0)
    asym = float((ipsi.mean() - contra_step.mean()) / mean_all * 100.0) if mean_all > 0 else 0.0
    ds = float(np.mean(100.0 * (1.0 - 2.0 * swing / stride)))
    return Phases(
        heel_strikes=hs_a, contra_strikes=c_a, toe_offs=to_a,
        ipsi_step_s=ipsi, contra_step_s=contra_step, swing_s=swing, stride_s=stride,
        asymmetry_pct=asym, double_support_pct=float(np.clip(ds, 0.0, 60.0)),
        n_strides=int(ok.sum()),
    )


def _labelled_step_times(
    step_peaks: np.ndarray, heel_strikes: np.ndarray, fs: float
) -> tuple[np.ndarray, np.ndarray] | None:
    """Split the accelerometer's step times into the instrumented leg's and
    the other leg's, using the thigh heel strikes as labels."""
    peaks = np.asarray(step_peaks, dtype=int)
    if len(peaks) < 6 or len(heel_strikes) == 0:
        return None
    tol = int(LABEL_TOLERANCE_S * fs)
    nearest = np.abs(peaks[:, None] - heel_strikes[None, :]).min(axis=1)
    is_ipsi = nearest <= tol
    share = float(is_ipsi.mean())
    if not (0.30 <= share <= 0.70):
        return None
    dt = np.diff(peaks) / fs
    ends_ipsi = is_ipsi[1:]
    ipsi, contra = dt[ends_ipsi], dt[~ends_ipsi]
    if len(ipsi) < 3 or len(contra) < 3:
        return None
    return ipsi, contra


def alternating_asymmetry(step_times: np.ndarray) -> float | None:
    """Fallback without a gyroscope: split consecutive step times into the two
    alternating feet and report the unsigned symmetry index. Which foot is
    which is unknown, so the sign is not."""
    dt = np.asarray(step_times, dtype=float)
    if len(dt) < 6:
        return None
    a, b = dt[0::2], dt[1::2]
    mean_all = float((a.mean() + b.mean()) / 2.0)
    return float(abs(a.mean() - b.mean()) / mean_all * 100.0) if mean_all > 0 else None
