"""The home exercise program (HEP): a clinic's exercise library, the plans a
clinician assigns from it, and what the patient app reads back.

Separate from the care-plan task library (``app/plan``) on purpose: a task
there is a check-in with data verification, while an exercise here is dosed
(sets, reps, hold, frequency, side) and carries a reviewed demonstration.

* ``models``   the tables (exercises, media, plans, completions, assignments,
               invitations)
* ``catalog``  the standard library and its idempotent seed
* ``service``  search, custom exercises, payloads, which clip an exercise plays
* ``plans``    the standing prescription and its published snapshots
* ``schedule`` the calendar: one exercise on one patient's day, and what came back
               (the session, the completion, the therapist's review)
* ``templates`` programs: a clinic's exercises-by-weekday, applied from a date
* ``media``    a clinic's own demonstration clips
* ``api``      the console routes under ``/api/hep`` (the patient's are
               ``app/api/exercises.py``)
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_ensured = False


def ensure_ready(db: Session) -> None:
    """Upsert the standard catalog once per process (the plan router does
    the same for its library). A failure is logged and retried on the next
    request rather than failing the read."""
    global _ensured
    if _ensured:
        return
    from app.hep.catalog import ensure_catalog

    try:
        ensure_catalog(db)
    except Exception:  # noqa: BLE001 — a catalog upsert must never fail a request
        logger.exception("HEP catalog upsert failed")
        db.rollback()
        return
    _ensured = True


def reset_ready() -> None:
    global _ensured
    _ensured = False
