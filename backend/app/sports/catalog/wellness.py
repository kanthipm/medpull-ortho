"""The morning wellness questionnaire and the subjective keys the recovery
board reads. Scales are 0–10 in the direction that reads naturally to an
athlete (10 = slept great, 10 = very sore); the Hooper index is computed
from them by the recovery engine with the sleep item inverted."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WellnessSpec:
    key: str
    label: str
    prompt: str
    low: str      # what 0 means
    high: str     # what 10 means
    # "good" when a high number is good (sleep quality, energy, mood), "bad"
    # when a high number is a problem (fatigue, soreness, stress, pain).
    direction: str
    daily: bool = True
    personal_key: str | None = None   # the personal-tier log key it also feeds
    symbol: str = "face.smiling"
    hooper: bool = False
    female_only: bool = False
    kind: str = "scale"   # scale | choice | number | yes_no
    options: tuple[str, ...] = ()
    unit: str = ""


WELLNESS: dict[str, WellnessSpec] = {}


def _add(spec: WellnessSpec) -> None:
    WELLNESS[spec.key] = spec


_add(WellnessSpec("sleep_quality", "Sleep quality", "How did you sleep?", "Terrible", "Great",
                  "good", personal_key="sleep_quality", symbol="bed.double.fill", hooper=True))
_add(WellnessSpec("fatigue", "Fatigue", "How tired are you right now?", "Fresh", "Exhausted",
                  "bad", symbol="battery.25percent", hooper=True))
_add(WellnessSpec("soreness", "Muscle soreness", "How sore are your muscles?", "None", "Very sore",
                  "bad", personal_key="soreness", symbol="figure.strengthtraining.traditional", hooper=True))
_add(WellnessSpec("stress", "Stress", "How stressed do you feel?", "Relaxed", "Very stressed",
                  "bad", symbol="brain.head.profile", hooper=True))
_add(WellnessSpec("mood", "Mood", "How is your mood?", "Low", "Great", "good",
                  personal_key="mood", symbol="face.smiling"))
_add(WellnessSpec("energy", "Energy", "How much energy do you have?", "Empty", "Full", "good",
                  personal_key="energy", symbol="bolt.fill"))
_add(WellnessSpec("pain", "Pain", "Any pain today? Rate the worst spot.", "None", "Worst", "bad",
                  symbol="bandage.fill"))
_add(WellnessSpec("readiness_self", "Readiness to train", "How ready do you feel to go hard today?",
                  "Not at all", "All the way", "good", symbol="gauge.with.dots.needle.67percent"))
_add(WellnessSpec("hydration", "Hydration", "Urine colour this morning (1 pale to 8 dark)?",
                  "Pale", "Dark", "bad", symbol="drop.fill", kind="number", unit="shade"))
_add(WellnessSpec("body_mass_kg", "Morning weight", "Weight this morning, before food.",
                  "", "", "good", symbol="scalemass.fill", kind="number", unit="kg"))
_add(WellnessSpec("illness", "Feeling unwell", "Any signs of illness (sore throat, runny nose, fever)?",
                  "No", "Yes", "bad", symbol="thermometer.medium", kind="yes_no"))
_add(WellnessSpec("cycle_phase", "Cycle phase", "Where are you in your cycle?", "", "", "good",
                  symbol="moon.circle.fill", female_only=True, kind="choice",
                  options=("menstrual", "follicular", "ovulatory", "luteal", "unsure")))
_add(WellnessSpec("cycle_day", "Cycle day", "Day of your cycle (1 = first day of bleeding).",
                  "", "", "good", symbol="calendar", female_only=True, kind="number", unit="day"))
_add(WellnessSpec("note", "Anything else", "Anything your staff should know?", "", "", "good",
                  symbol="text.bubble", kind="text"))

HOOPER_KEYS = ("sleep_quality", "fatigue", "soreness", "stress")
CYCLE_PHASES = {"menstrual": 1.0, "follicular": 2.0, "ovulatory": 3.0, "luteal": 4.0, "unsure": 0.0}


def wellness_view(spec: WellnessSpec) -> dict[str, Any]:
    return {
        "key": spec.key, "label": spec.label, "prompt": spec.prompt, "low": spec.low,
        "high": spec.high, "direction": spec.direction, "daily": spec.daily,
        "symbol": spec.symbol, "hooper": spec.hooper, "female_only": spec.female_only,
        "kind": spec.kind, "options": list(spec.options), "unit": spec.unit,
    }
