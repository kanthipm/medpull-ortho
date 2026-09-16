"""Per-patient signal shaping.

Each scenario perturbs the generic recovery-shaped generators so the
intelligence engine has something true to find. The numbers here and the
engine's thresholds were tuned together; golden tests in tests/test_golden.py
pin the resulting risk tiers.
"""

from dataclasses import dataclass, field

from app.models.enums import MetricType as M


@dataclass(frozen=True)
class Ramp:
    """Linear ramp applied to a metric over [start_day, end_day] (post-op days).
    At start_day nothing is applied; at end_day the full effect is applied and
    it persists for all later days. add is absolute; mult scales toward
    mult_to (1.0 = no change)."""

    metric: M
    start_day: int
    end_day: int
    add: float = 0.0
    mult_to: float = 1.0

    def factor(self, day: int) -> float:
        if day <= self.start_day:
            return 0.0
        if day >= self.end_day:
            return 1.0
        return (day - self.start_day) / (self.end_day - self.start_day)


@dataclass(frozen=True)
class ScenarioSpec:
    # multiplier on the expected-curve trajectory (1.0 on-track, <1 behind, >1 ahead)
    track: float = 1.0
    # functional metrics stop improving after this post-op day
    plateau_after: int | None = None
    # fraction of post-op days with no data at all (device not worn/synced)
    dropout_frac: float = 0.0
    ramps: tuple[Ramp, ...] = field(default_factory=tuple)


SCENARIOS: dict[str, ScenarioSpec] = {
    # Possible early infection pattern: coupled vitals shift + activity collapse
    # starting day 6. The engine should see EWMA flags on RHR/temp/HRV, a high
    # composite deviation index, and a trajectory change-point.
    "marcus": ScenarioSpec(
        ramps=(
            Ramp(M.RESTING_HR, 4, 8, add=8.0),
            Ramp(M.SKIN_TEMP, 4, 8, add=0.7),
            Ramp(M.HRV_RMSSD, 4, 8, mult_to=0.78),
            Ramp(M.STEPS, 4, 8, mult_to=0.60),
            Ramp(M.WALKING_SPEED, 4, 8, mult_to=0.75),
        ),
    ),
    # Sleep disruption + mildly elevated RHR — worth watching, not urgent.
    # (RHR bump kept below the EWMA flag threshold so this stays MEDIUM.)
    "linda": ScenarioSpec(
        ramps=(
            Ramp(M.SLEEP_DURATION, 6, 8, mult_to=0.75),
            Ramp(M.RESTING_HR, 6, 10, add=1.0),
        ),
    ),
    # Slow adverse drift (CUSUM territory): activity sliding a few % per day.
    "robert": ScenarioSpec(
        ramps=(
            Ramp(M.STEPS, 1, 6, mult_to=0.72),
            Ramp(M.HRV_RMSSD, 1, 6, mult_to=0.90),
        ),
    ),
    # Persistently ~15% below the expected curve — behind trajectory.
    "sofia": ScenarioSpec(track=0.82),
    # Recovery plateau: improvement stops at day 8, which also keeps gait
    # asymmetry naturally elevated (the asymmetry curve follows recovery
    # progress, so freezing progress freezes the limp).
    "aisha": ScenarioSpec(plateau_after=8),
    # Device barely worn: most days missing -> data-confidence gate.
    "priya": ScenarioSpec(dropout_frac=0.70),
    # Normal early post-op, thin history.
    "grace": ScenarioSpec(),
    "david": ScenarioSpec(track=1.02),
    "james": ScenarioSpec(track=1.08),
    "elena": ScenarioSpec(track=1.12),
}


def get_scenario(patient_id: str) -> ScenarioSpec:
    return SCENARIOS.get(patient_id, ScenarioSpec())
