"""Outcome measures a clinic schedules, and the change that counts.

Two kinds. ``asked`` instruments are free to use and short, so the person is
asked the questions themselves: the numeric pain rating, and the
patient-specific functional scale (the function goals). ``entered``
instruments are published questionnaires whose wording is not ours to
reproduce (several are licensed): the clinic gives its own copy and the
total is typed in, by the therapist or by the person.

``threshold`` is a published change threshold, in points, with where it
comes from. It is a starting point, not a verdict: the page shows the
change beside it and the source under it, a clinic can set its own, and an
instrument with no number here simply shows the change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    short: str
    mode: str                 # asked | entered
    low: float
    high: float
    higher_is_better: bool
    about: str
    threshold: float | None = None
    threshold_kind: str = ""  # "Minimal important change" | "Minimal detectable change"
    source: str = ""
    note: str = ""


INSTRUMENTS: dict[str, Instrument] = {i.key: i for i in (
    Instrument(
        "nprs", "Numeric pain rating", "NPRS", "asked", 0, 10, False,
        "Pain right now, 0 to 10.",
        2, "Minimal important change",
        "Ostelo et al., Spine 2008 (consensus, low back pain); Childs et al., Spine 2005.",
    ),
    Instrument(
        "psfs", "Patient-specific functional scale", "PSFS", "asked", 0, 10, True,
        "The person's own activities, each rated 0 (unable) to 10 (as before); the score is "
        "their average.",
        2, "Minimal detectable change",
        "Stratford et al., Physiotherapy Canada 1995: 2 points on the average, 3 on one "
        "activity (90% confidence).",
    ),
    Instrument(
        "visa_p", "VISA-P (patellar tendon)", "VISA-P", "entered", 0, 100, True,
        "Victorian Institute of Sport Assessment, patellar tendon. Enter the total.",
        13, "Minimal important change",
        "Hernandez-Sanchez et al., Br J Sports Med 2014 (athletes with patellar tendinopathy).",
    ),
    Instrument(
        "visa_a", "VISA-A (Achilles tendon)", "VISA-A", "entered", 0, 100, True,
        "Victorian Institute of Sport Assessment, Achilles tendon. Enter the total.",
        14, "Minimal important change",
        "Lagas et al., J Orthop Sports Phys Ther 2021 (midportion, at 12 weeks; 7 points at "
        "24 weeks).",
        "The threshold depends on the follow-up: 14 points at 12 weeks, 7 at 24.",
    ),
    Instrument(
        "odi", "Oswestry Disability Index", "ODI", "entered", 0, 100, False,
        "Low back disability, as a percentage. Enter the total.",
        10, "Minimal important change",
        "Ostelo et al., Spine 2008 (consensus: 10 points, or 30% of the baseline score).",
        "A licensed questionnaire: use the clinic's own copy.",
    ),
    Instrument(
        "lefs", "Lower Extremity Functional Scale", "LEFS", "entered", 0, 80, True,
        "Lower-limb function, 0 to 80. Enter the total.",
        9, "Minimal detectable change",
        "Binkley et al., Phys Ther 1999 (minimal detectable change and minimal clinically "
        "important difference both 9 points, 90% confidence).",
    ),
    Instrument(
        "quickdash", "QuickDASH", "QuickDASH", "entered", 0, 100, False,
        "Arm, shoulder and hand disability, 0 to 100. Enter the total.",
        None, "", "",
        "No threshold is set here: published values vary by condition. Set the clinic's own.",
    ),
    Instrument(
        "acl_rsi", "ACL-RSI", "ACL-RSI", "entered", 0, 100, True,
        "Readiness to return to sport after an ACL injury, 0 to 100. Enter the total.",
        None, "", "",
        "No threshold is set here. Set the clinic's own.",
    ),
)}


def describe(key: str, threshold_override: float | None = None) -> dict:
    i = INSTRUMENTS[key]
    threshold = threshold_override if threshold_override is not None else i.threshold
    return {
        "key": i.key, "name": i.name, "short": i.short, "mode": i.mode,
        "low": i.low, "high": i.high, "higher_is_better": i.higher_is_better,
        "about": i.about, "threshold": threshold,
        "threshold_is_clinic": threshold_override is not None,
        "threshold_kind": i.threshold_kind if threshold_override is None else "The clinic's own",
        "source": i.source, "note": i.note,
    }


def catalog(overrides: dict[str, float] | None = None) -> list[dict]:
    overrides = overrides or {}
    return [describe(k, overrides.get(k)) for k in INSTRUMENTS]


def change_read(key: str, first: float, latest: float,
                threshold: float | None) -> dict:
    """The change from the first score to the latest, said plainly: how many
    points, in which direction, and whether it is past the threshold. No
    word about the person; that is the therapist's."""
    i = INSTRUMENTS[key]
    delta = round(latest - first, 1)
    improved = delta > 0 if i.higher_is_better else delta < 0
    direction = "no change" if delta == 0 else ("better" if improved else "worse")
    past = threshold is not None and abs(delta) >= threshold
    return {"delta": delta, "direction": direction, "past_threshold": bool(past)}
