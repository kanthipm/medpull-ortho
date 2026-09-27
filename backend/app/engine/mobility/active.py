"""The two patient-administered tests: the six-minute walk and joint range
of motion. Both are computed here from what the phone recorded so the same
rules apply to every phone.

Six-minute walk distance
    The supervised clinic test walks a marked corridor for six minutes; the
    distance is the outcome (ATS 2002). The in-app version times six minutes
    and estimates distance from the best evidence the phone has, in order:
      1. GPS path length, when the phone reported horizontal accuracy within
         GPS_MAX_ACCURACY_M for the walk (outdoors; Salvi 2020 found a bias
         of about -1 m and limits of agreement of +-37 m against a trundle
         wheel);
      2. the phone's own pedometer distance (Apple's CMPedometer is
         calibrated per user from GPS walks, and indoors it is the best
         single estimate);
      3. steps x mean step length from the inverted-pendulum model over the
         IMU recorded during the test;
      4. steps x 0.415 x stature (the classical step-length heuristic) as a
         last resort.
    The method used, the step count and the per-minute cadence (from which
    the endurance fade, minute 6 vs minute 1, is reported) travel in
    value_json.

Range of motion (phone inclinometer)
    The validated protocol (Chew et al. 2024, PLOS One: n = 30 TKA, MAD 4.5
    deg flexion, 2.2 deg extension against goniometry) rests the phone's long
    edge on the limb segment and reads its tilt from the gravity vector.
    The app records a REFERENCE hold and a MOVEMENT hold, ~2 s each; here
    the segment's tilt is the angle between the phone's long axis (device
    +y) and the horizontal plane, from the median gravity vector of each
    hold, and the joint angle is the change in tilt between the holds:

        tilt  = atan2(-g_y, -g_z)             [deg from horizontal, -180..180]
        angle = |tilt_move - tilt_reference|  [deg]

    with the phone's top end toward the joint (knee, hip, shoulder) and the
    screen up in the reference position, so the tilt keeps counting past
    vertical and a 120-degree knee is not folded back to 60.

    Protocols name what the two holds mean:
      knee_flexion_supine    reference: leg straight on the bed (shin ~0 deg);
                             movement: heel slid to maximum flexion. Angle =
                             knee flexion.
      knee_extension_supine  reference: the bed (phone flat); movement: knee
                             pressed to maximum extension with the heel
                             propped. Angle = residual flexion; 0 is full
                             extension and the sign records hyperextension.
      hip_flexion_supine     phone on the thigh; reference thigh flat.
      shoulder_flexion_standing / shoulder_abduction_standing
                             phone on the upper arm; reference arm hanging.
    A hold whose tilt wanders more than HOLD_MAX_SD deg is marked unsteady.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

GPS_MAX_ACCURACY_M = 12.0
STEP_LENGTH_HEIGHT_RATIO = 0.415
HOLD_MAX_SD = 3.0
PROTOCOLS = {
    "knee_flexion_supine": ("knee", "flexion"),
    "knee_extension_supine": ("knee", "extension"),
    "hip_flexion_supine": ("hip", "flexion"),
    "shoulder_flexion_standing": ("shoulder", "flexion"),
    "shoulder_abduction_standing": ("shoulder", "abduction"),
}


@dataclass
class SixMinuteWalk:
    distance_m: float
    method: str
    steps: int | None
    cadence_spm: float | None
    minute_cadence: list[float]
    fade_pct: float | None       # (minute 6 - minute 1) / minute 1 x 100
    detail: dict[str, Any]


def six_minute_walk(
    duration_s: float,
    steps: int | None,
    height_cm: float | None,
    gps_distance_m: float | None = None,
    gps_accuracy_m: float | None = None,
    pedometer_distance_m: float | None = None,
    imu_distance_m: float | None = None,
    imu_steps: int | None = None,
    minute_steps: list[int] | None = None,
) -> SixMinuteWalk | None:
    """Distance over the test. ``imu_*`` are what the mobility pipeline found
    in the IMU recorded during the walk, when the app sent it."""
    if duration_s <= 0:
        return None
    n_steps = imu_steps if imu_steps else steps
    scale = min(360.0 / duration_s, 1.5)  # a test cut short is scaled up, capped
    if (gps_distance_m and gps_distance_m > 0 and gps_accuracy_m is not None
            and gps_accuracy_m <= GPS_MAX_ACCURACY_M):
        distance, method = float(gps_distance_m), "gps"
    elif pedometer_distance_m and pedometer_distance_m > 0:
        distance, method = float(pedometer_distance_m), "pedometer"
    elif imu_distance_m and imu_distance_m > 0:
        distance, method = float(imu_distance_m), "imu_inverted_pendulum"
    elif n_steps and height_cm:
        distance, method = n_steps * STEP_LENGTH_HEIGHT_RATIO * height_cm / 100.0, "steps_x_height"
    else:
        return None
    distance *= scale
    cadence = 60.0 * n_steps / duration_s if n_steps else None
    minute = [float(v) for v in (minute_steps or [])]
    fade = None
    if len(minute) >= 6 and minute[0] > 0:
        fade = round((minute[5] - minute[0]) / minute[0] * 100.0, 1)
    return SixMinuteWalk(
        distance_m=round(distance, 1), method=method, steps=n_steps,
        cadence_spm=round(cadence, 1) if cadence else None, minute_cadence=minute,
        fade_pct=fade,
        detail={"duration_s": round(duration_s, 1), "scaled": scale != 1.0,
                "gps_accuracy_m": gps_accuracy_m},
    )


@dataclass
class RangeOfMotion:
    joint: str
    movement: str
    protocol: str
    angle_deg: float
    tilt_reference_deg: float
    tilt_movement_deg: float
    reference_sd_deg: float
    movement_sd_deg: float
    steady: bool


def _tilts(samples: np.ndarray) -> np.ndarray:
    """Tilt of the phone's long axis in its own y-z (sagittal) plane, degrees
    from horizontal, over the full -180..180 range: atan2(-g_y, -g_z). With
    the phone flat and screen up (gravity along -z) the tilt is 0; with its
    top end raised to vertical (gravity along -y) it is 90; past vertical
    the screen turns over and the tilt keeps counting. asin alone would fold
    a 120-degree knee back to 60."""
    g = np.asarray(samples, dtype=float).reshape(-1, 3)
    return np.degrees(np.arctan2(-g[:, 1], -g[:, 2]))


def range_of_motion(
    protocol: str, reference: np.ndarray, movement: np.ndarray
) -> RangeOfMotion | None:
    if protocol not in PROTOCOLS:
        return None
    ref, mov = _tilts(reference), _tilts(movement)
    if len(ref) < 3 or len(mov) < 3:
        return None
    joint, kind = PROTOCOLS[protocol]
    tilt_ref, tilt_mov = float(np.median(ref)), float(np.median(mov))
    sd_ref, sd_mov = float(ref.std(ddof=1)), float(mov.std(ddof=1))
    angle = tilt_mov - tilt_ref
    if kind != "extension":
        angle = abs(angle)
    return RangeOfMotion(
        joint=joint, movement=kind, protocol=protocol, angle_deg=round(float(angle), 1),
        tilt_reference_deg=round(tilt_ref, 1), tilt_movement_deg=round(tilt_mov, 1),
        reference_sd_deg=round(sd_ref, 2), movement_sd_deg=round(sd_mov, 2),
        steady=max(sd_ref, sd_mov) <= HOLD_MAX_SD,
    )
