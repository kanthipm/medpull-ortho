"""Walking-bout detection.

Real-world gait metrics are only meaningful over stretches of actual walking:
a value computed across standing, fidgeting and sitting is a value of nothing.
The detector slides a 2 s window (1 s hop) over the orientation-free
acceleration magnitude and marks it as walking when three things hold at
once:

1. the band-passed signal has enough energy (std > MIN_STD m/s^2: a pocketed
   phone on a walking person moves far more than one on a seated person),
2. the dominant frequency sits in the step band (STEP_BAND, 0.8-3.2 Hz, i.e.
   48-192 steps/min — slow post-operative walking with a frame included),
3. at least MIN_BAND_RATIO of the spectral power lies inside that band, so a
   single jolt with no periodicity does not qualify.

Marked windows are merged (gaps up to MERGE_GAP_S bridged) and a run shorter
than MIN_BOUT_S is discarded: Mobilise-D's real-world validation shows the
per-bout speed error falls sharply once a bout holds ten or more strides, and
ten seconds at a post-operative cadence is roughly that.
"""

from __future__ import annotations

import numpy as np

from app.engine.mobility.dsp import bandpass, dominant_frequency

WINDOW_S = 2.0
HOP_S = 1.0
MIN_STD = 0.35            # m/s^2
STEP_BAND = (0.8, 3.2)    # Hz
MIN_BAND_RATIO = 0.30
MERGE_GAP_S = 2.0
MIN_BOUT_S = 10.0


def detect_bouts(a_mag: np.ndarray, fs: float) -> list[tuple[int, int]]:
    """Sample-index [start, end) pairs of walking bouts in the window."""
    n = len(a_mag)
    win = int(WINDOW_S * fs)
    hop = int(HOP_S * fs)
    if n < win:
        return []
    x = bandpass(a_mag, 0.5, 6.0, fs)
    flags: list[tuple[int, int]] = []
    for start in range(0, n - win + 1, hop):
        seg = x[start:start + win]
        if float(seg.std()) < MIN_STD:
            continue
        f, ratio = dominant_frequency(seg, fs, *STEP_BAND)
        if STEP_BAND[0] <= f <= STEP_BAND[1] and ratio >= MIN_BAND_RATIO:
            flags.append((start, start + win))
    if not flags:
        return []
    merged: list[list[int]] = [list(flags[0])]
    gap = int(MERGE_GAP_S * fs)
    for s, e in flags[1:]:
        if s - merged[-1][1] <= gap:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    min_len = int(MIN_BOUT_S * fs)
    return [(s, min(e, n)) for s, e in merged if e - s >= min_len]
