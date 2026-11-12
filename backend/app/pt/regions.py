"""Body areas, in the words a person uses for them.

An area is stored as ``<area>`` or ``<area>:<side>`` ("knee:left", "low
back"). The check-in asks the area and then the side, each as one choice a
text can answer with a word or a number.
"""

from __future__ import annotations

# What the "where is it?" question offers, in the order it offers them. Lower
# case: these are the option values a task answer carries.
AREAS = (
    "neck", "shoulder", "elbow", "wrist or hand", "upper back", "low back",
    "hip or groin", "thigh", "knee", "shin or calf", "achilles", "ankle or foot",
    "somewhere else",
)
# Areas that sit on the middle of the body: no side is asked for them.
MIDLINE = {"neck", "upper back", "low back", "somewhere else"}
SIDES = ("left", "right", "both")
SIDE_OPTIONS = ("left", "right", "both", "middle")


def make(area: str, side: str | None = None) -> str:
    """The stored key for an area and a side. Raises ValueError on an area
    this list does not have."""
    area = (area or "").strip().lower()
    if area not in AREAS:
        raise ValueError(f"Unknown area: {area or '(none)'}")
    side = (side or "").strip().lower()
    if area in MIDLINE or side not in SIDES:
        return area
    return f"{area}:{side}"


def parse(region: str) -> tuple[str, str | None]:
    area, _, side = (region or "").partition(":")
    return area, (side or None)


def valid(region: str) -> bool:
    area, side = parse(region)
    return area in AREAS and (side is None or side in SIDES)


def label(region: str) -> str:
    """"Left knee", "Low back", "Both shoulders" would be wrong for "wrist
    or hand", so a both-sides area reads "Both sides, wrist or hand"."""
    area, side = parse(region)
    name = "Achilles" if area == "achilles" else area
    if side in ("left", "right"):
        return f"{side.capitalize()} {name}"
    if side == "both":
        return f"Both sides, {name}"
    return name[:1].upper() + name[1:]


def covers(known: str, reported: str) -> bool:
    """Whether an area on file already accounts for one a person names: the
    same area, and the same side unless either of them names no side (or
    the one on file is both)."""
    known_area, known_side = parse(known)
    area, side = parse(reported)
    if known_area != area:
        return False
    return known_side is None or side is None or known_side == side or known_side == "both"


def is_new(reported: str, known: list[str]) -> bool:
    return not any(covers(k, reported) for k in known)
