"""Seeded recovery tasks + 14-day adherence records.

Adherence rates roughly follow risk: struggling patients complete less.
Deterministic via the same seeded-rng scheme as the generators.
"""

from dataclasses import dataclass

from app.models.enums import AdherenceStatus
from app.seed.generators import _rng


@dataclass(frozen=True)
class TaskSpec:
    title: str
    why: str
    verified_by: str


TASKS: dict[str, list[TaskSpec]] = {
    "marcus": [
        TaskSpec("Walk 10 minutes, twice daily", "Restores knee motion and circulation", "step data"),
        TaskSpec("Quad sets, 3 sets of 10", "Rebuilds thigh strength that guards the joint", "self-report"),
        TaskSpec("Ice + elevate 20 minutes after exercise", "Controls swelling", "self-report"),
    ],
    "linda": [
        TaskSpec("Pendulum swings, 3x daily", "Keeps the shoulder from stiffening", "self-report"),
        TaskSpec("Wear sling except during exercises", "Protects the repair while it heals", "self-report"),
    ],
    "robert": [
        TaskSpec("Walk 5 minutes every 2 waking hours", "Frequent short walks protect the spine", "step data"),
        TaskSpec("No bending, lifting, or twisting", "Protects the surgical site", "self-report"),
    ],
    "sofia": [
        TaskSpec("Boot on for all weight-bearing", "Protects the fixation while bone heals", "self-report"),
        TaskSpec("Ankle alphabet, 2x daily", "Restores range of motion", "self-report"),
        TaskSpec("Progressive walking per PT plan", "Rebuilds load tolerance", "step data"),
    ],
    "aisha": [
        TaskSpec("Walk to the corner, twice daily", "Builds hip endurance", "step data"),
        TaskSpec("Hip abduction exercises, 2x daily", "Strengthens the muscles that stop the limp", "self-report"),
        TaskSpec("Use the cane on longer walks", "Keeps gait symmetric while strength returns", "self-report"),
    ],
    "priya": [
        TaskSpec("Wear the watch during the day", "Lets your care team see your recovery", "device sync"),
        TaskSpec("Walk a little every day", "Builds hip endurance", "step data"),
    ],
    "grace": [
        TaskSpec("Ankle pumps every hour while awake", "Prevents blood clots", "self-report"),
        TaskSpec("Stand with walker 3x daily", "Early mobility speeds recovery", "self-report"),
    ],
    "david": [
        TaskSpec("PT program, 4 sessions weekly", "Graft-safe strength progression", "PT attendance"),
        TaskSpec("No running or pivoting", "Protects the graft until cleared", "self-report"),
    ],
    "james": [
        TaskSpec("Walk 1 mile daily", "Maintains the gains from rehab", "step data"),
        TaskSpec("Stair practice, 10 steps up/down", "Restores confidence on stairs", "self-report"),
    ],
    "elena": [
        TaskSpec("Strengthening plan, 3x weekly", "Protects the repaired meniscus", "self-report"),
        TaskSpec("Avoid deep squats and twisting", "Lets the repair mature", "self-report"),
    ],
}

# target completion rate per patient over the last 14 days
RATES: dict[str, float] = {
    "marcus": 0.62,
    "linda": 0.78,
    "robert": 0.60,
    "sofia": 0.74,
    "aisha": 0.70,
    "priya": 0.45,
    "grace": 0.92,
    "david": 0.95,
    "james": 0.90,
    "elena": 0.88,
}


def daily_statuses(patient_id: str, n_tasks: int, n_days: int = 14) -> list[list[AdherenceStatus]]:
    """[day][task] -> status, deterministic per patient."""
    r = _rng(patient_id, "adherence")
    rate = RATES.get(patient_id, 0.85)
    out: list[list[AdherenceStatus]] = []
    for _ in range(n_days):
        day: list[AdherenceStatus] = []
        for _ in range(n_tasks):
            roll = r.random()
            if roll < rate:
                day.append(AdherenceStatus.VERIFIED)
            elif roll < rate + 0.15:
                day.append(AdherenceStatus.SELF_ATTESTED)
            else:
                day.append(AdherenceStatus.MISSED)
        out.append(day)
    return out
