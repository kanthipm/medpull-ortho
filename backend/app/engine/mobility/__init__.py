"""MedPull's own mobility engine: gait, stairs, steadiness, the six-minute
walk, joint range of motion and the stress index, computed from raw phone
sensor windows and daily vitals with one algorithm for every device.

Module map (read in this order):
  frames     the raw window, resampling and gravity alignment
  dsp        the numpy filters / peak finder / spectral helpers everything uses
  bouts      which seconds of a window are walking
  steps      step instants, cadence, step-time variability
  phases     thigh-gyroscope gait phases: signed asymmetry, double support
  spatial    inverted-pendulum step length and walking speed (+ GPS calibration)
  stability  the 0-100 walking-steadiness index
  stairs     barometric stair ascent / descent speed
  active     the six-minute walk and the phone-inclinometer range of motion
  stress     the daily 0-100 stress index from HRV / resting HR / respiration
  pipeline   window -> bouts -> canonical observation rows

docs/methods/custom-metrics-methodology.md is the reviewer-facing statement
of every input, function and assumption in here; keep the two in step.
"""

from app.engine.mobility.active import range_of_motion, six_minute_walk
from app.engine.mobility.frames import MotionWindow
from app.engine.mobility.pipeline import (
    VERSION,
    WindowResult,
    observations_for,
    process_window,
    session_row,
)
from app.engine.mobility.stress import stress_index_series

__all__ = [
    "VERSION", "MotionWindow", "WindowResult", "process_window", "observations_for",
    "session_row", "six_minute_walk", "range_of_motion", "stress_index_series",
]
