"""Step detection and the temporal gait parameters.

Steps are found on the band-passed (0.5-3.5 Hz) acceleration magnitude, one
peak per foot contact whichever way the phone is oriented. Peaks closer than
MIN_STEP_S (0.30 s, a 200 steps/min ceiling) collapse to the taller one. The
amplitude threshold adapts to the bout: a pocketed phone feels the near leg's
contact more than the far leg's, so the threshold is a fraction
(HEIGHT_FRACTION) of the median of the UPPER half of the candidate peaks —
low enough to keep the quieter contralateral contacts, high enough to drop
noise bumps.

From the step instants:
- step times      dt_i = t_{i+1} - t_i
- cadence         60 / mean(dt)                      [steps/min]
- stride times    dt_i + dt_{i+1}                    [s]
- step-time CV    sd(dt) / mean(dt)                  [%]  (a variability
                  measure used in fall-risk work, Hausdorff 2001)

A bout is accepted as walking only when cadence is plausible (40-200 spm),
the step-time CV is under MAX_CV (real walking, even impaired, is far more
regular than fidgeting) and at least MIN_STEPS were found.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.engine.mobility.dsp import bandpass, find_peaks

MIN_STEP_S = 0.30
HEIGHT_FRACTION = 0.35
MIN_STEPS = 8
CADENCE_RANGE = (40.0, 200.0)
MAX_CV = 0.40


@dataclass
class StepTiming:
    peaks: np.ndarray          # sample indices, relative to the bout start
    step_times: np.ndarray     # s
    cadence_spm: float
    step_time_cv: float        # fraction (0.03 = 3 %)
    stride_time_s: float
    n_steps: int

    @property
    def valid(self) -> bool:
        return (
            self.n_steps >= MIN_STEPS
            and CADENCE_RANGE[0] <= self.cadence_spm <= CADENCE_RANGE[1]
            and self.step_time_cv <= MAX_CV
        )


def detect_steps(a_mag: np.ndarray, fs: float) -> np.ndarray:
    x = bandpass(a_mag, 0.5, 3.5, fs)
    peaks = find_peaks(x, int(MIN_STEP_S * fs))
    if len(peaks) == 0:
        return peaks
    heights = x[peaks]
    upper = heights[heights >= np.median(heights)]
    threshold = HEIGHT_FRACTION * float(np.median(upper))
    return peaks[heights >= threshold]


def timing(peaks: np.ndarray, fs: float) -> StepTiming:
    peaks = np.asarray(peaks, dtype=int)
    if len(peaks) < 2:
        return StepTiming(peaks, np.array([]), 0.0, 1.0, 0.0, int(len(peaks)))
    dt = np.diff(peaks) / fs
    mean_dt = float(dt.mean())
    cv = float(dt.std(ddof=1) / mean_dt) if len(dt) > 1 and mean_dt > 0 else 1.0
    strides = dt[:-1] + dt[1:] if len(dt) > 1 else dt * 2.0
    return StepTiming(
        peaks=peaks, step_times=dt, cadence_spm=60.0 / mean_dt if mean_dt > 0 else 0.0,
        step_time_cv=cv, stride_time_s=float(strides.mean()), n_steps=int(len(peaks)),
    )
