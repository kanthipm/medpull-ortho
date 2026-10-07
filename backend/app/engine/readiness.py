"""How far a metric is from its first reading, in days — one shape for every
surface.

Every metric needs some minimum history before it can say anything: a
baseline to compare against, a pair of nights, a week of load. Until then
the card used to read "Building baseline" and nothing else, which told
neither the clinician nor the patient how long to wait. A readiness object
answers that the same way everywhere:

    have       units already in hand (days of steps, nights with stages, ...)
    need       units the FIRST reading needs
    firm       units an ESTABLISHED reading needs (>= need); between need and
               firm the reading is shown but labelled provisional
    left       units still to collect before the first reading, assuming the
               data keeps arriving once a day — the "x days left" the UI prints
    firm_left  units still to collect before the reading is established
    stage      "collecting" (no reading yet), "provisional" (shown, thin) or
               "established"
    unit       what is being counted ("days", "nights", "paired days", ...)
    note       what has to arrive, in words the card can print

``extra_wait`` is for the engine's day-2 rule: days 0-1 after surgery are an
expected perturbation and never count toward a baseline, so a patient on
day 0 has two days to wait before the first countable day — and the UI
should say three days, not one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Readiness:
    ready: bool
    stage: str
    have: int
    need: int
    firm: int
    left: int
    firm_left: int
    unit: str = "days"
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def readiness(
    have: int,
    need: int,
    firm: int | None = None,
    *,
    unit: str = "days",
    note: str | None = None,
    extra_wait: int = 0,
    ready: bool | None = None,
) -> Readiness:
    """Build a readiness object from counts.

    ``ready`` may be forced: a metric that has its ``need`` but is held back
    by something a count cannot express (its newest reading is stale, say)
    reports ``ready=False`` with ``left=0`` so the UI says "waiting on new
    data" instead of printing a countdown that is already at zero.
    """
    have = max(0, int(have))
    need = max(1, int(need))
    firm = max(need, int(firm if firm is not None else need))
    extra = max(0, int(extra_wait))
    is_ready = have >= need if ready is None else bool(ready)
    left = 0 if is_ready else max(0, need - have) + extra
    firm_left = 0 if have >= firm else max(0, firm - have) + extra
    if not is_ready:
        stage = "collecting"
    elif have < firm:
        stage = "provisional"
    else:
        stage = "established"
    return Readiness(
        ready=is_ready, stage=stage, have=have, need=need, firm=firm, left=left,
        firm_left=firm_left, unit=unit, note=note,
    )


def days_left_text(r: Readiness | dict[str, Any] | None) -> str | None:
    """"2 more days" / "1 more night" / "ready" — the chip text, or None
    when nothing useful can be said."""
    if r is None:
        return None
    data = r.to_dict() if isinstance(r, Readiness) else r
    if data.get("ready"):
        if data.get("stage") == "provisional" and data.get("firm_left"):
            n = int(data["firm_left"])
            return f"early read · firms up in {n} {_unit(data.get('unit', 'days'), n)}"
        return None
    n = int(data.get("left") or 0)
    if n <= 0:
        return "waiting on new data"
    return f"{n} more {_unit(data.get('unit', 'days'), n)}"


def _unit(unit: str, n: int) -> str:
    unit = (unit or "days").strip()
    if n == 1 and unit.endswith("s"):
        # "days" -> "day", "nights" -> "night", "paired days" -> "paired day"
        return unit[:-1]
    return unit
