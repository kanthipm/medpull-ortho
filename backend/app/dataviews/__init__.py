"""The reads behind the console's Data tab (``app/api/data.py``).

Each module builds one view as plain JSON from what is already stored:

* ``roster``    the roster by data family: who has what, how recent
* ``readings``  one chart's sources, its stored readings page by page, and
                what the latest stored assessment says
* ``series``    one chart's daily series against the person's own baseline,
                rebuilt in memory the way the engine builds it, and the
                nights behind the sleep numbers
* ``reported``  one chart's day-by-day grid of what was reported and what
                was done on the exercise calendar

None of them writes. A GET that commits re-uploads the whole database on
AWS, so nothing here runs the engine's write path (``run_patient``,
``ensure_current``, ``baseline_store.establish``): the assessment is read as
stored, and anything recomputed is recomputed in memory and thrown away.
The routes decide who may ask; these functions take the charts they are
given.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta


def window_start(today: date, days: int) -> date:
    """The first day of a window of ``days`` calendar days ending today."""
    return today - timedelta(days=days - 1)


def iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
