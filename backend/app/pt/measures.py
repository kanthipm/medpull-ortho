"""The tests a clinic types results for, and the holds a person times at
home. A kind says what is measured and in which unit; "custom" carries its
own label and unit. Nothing here interprets a number: two sides of the same
test on the same day are set beside each other as a ratio, and that is all.
"""

from __future__ import annotations

# key: (label, unit, sided, who usually enters it)
KINDS: dict[str, tuple[str, str, bool, str]] = {
    "isometric_knee_extension": ("Isometric knee extension", "N", True, "clinic"),
    "isometric_plantarflexion": ("Isometric plantarflexion", "N", True, "clinic"),
    "isometric_mid_thigh_pull": ("Isometric mid-thigh pull", "N", False, "clinic"),
    "countermovement_jump": ("Countermovement jump height", "cm", False, "clinic"),
    "single_leg_hop": ("Single-leg hop for distance", "cm", True, "clinic"),
    "triple_hop": ("Triple hop for distance", "cm", True, "clinic"),
    "calf_raise_reps": ("Single-leg calf raises to fatigue", "reps", True, "clinic"),
    "grip_strength": ("Grip strength", "kg", True, "clinic"),
    "shoulder_external_rotation": ("Isometric shoulder external rotation", "N", True, "clinic"),
    "strength_rm": ("Strength test (rep max)", "kg", False, "clinic"),
    "plank_hold": ("Front plank hold", "s", False, "patient"),
    "side_plank_hold": ("Side plank hold", "s", True, "patient"),
    "back_extension_hold": ("Back extension hold", "s", False, "patient"),
    "wall_sit_hold": ("Wall sit hold", "s", False, "patient"),
    "single_leg_stance": ("Single-leg stance", "s", True, "patient"),
    "custom": ("Custom", "", False, "clinic"),
}
# The holds a person can be asked to time at home.
HOLDS = ("plank_hold", "side_plank_hold", "back_extension_hold", "wall_sit_hold",
         "single_leg_stance")
SIDES = ("left", "right", "both", "na")
VALUE_MAX = 100_000.0


def describe(kind: str) -> dict:
    label, unit, sided, who = KINDS[kind]
    return {"key": kind, "label": label, "unit": unit, "sided": sided, "entered_by": who,
            "hold": kind in HOLDS}


def catalog() -> list[dict]:
    return [describe(k) for k in KINDS]
