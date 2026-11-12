"""The texts the exercise calendar sends, each carrying a link that opens
the app at the right screen (``app/links.py``).

Three callers, three functions; every one returns None when nothing was
sent (no phone on the chart, texting not configured, the patient opted out)
and never raises into the route that called it: a text that cannot go out
must not undo the assignment or the review it announces.

* ``notify_assigned`` — the therapist put exercises on a day and asked for
  the lifter to be told (``POST /api/hep/schedule`` with ``text_patient``).
* ``notify_review`` — the therapist replied to a clip
  (``POST /api/hep/schedule/{id}/review`` with a note).
* ``text_today`` — "text today's plan" from the console, and the morning
  reminder run.

The bodies below are the contract the calendar code calls against.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:  # pragma: no cover
    from app.hep.models import ExerciseAssignment
    from app.models.patient import Patient


def notify_assigned(
    db: Session,
    patient: "Patient",
    rows: "list[ExerciseAssignment]",
    *,
    base_url: str | None = None,
    by: str | None = None,
) -> dict | None:
    """Text ``patient`` that ``rows`` were added to their calendar, with a
    link to the first day among them. ``by`` is the care-team member id the
    text is signed with. Returns ``{"sent": bool, "status": str, "detail":
    str | None, "message_id": int | None, "link": str}`` or None."""
    return None


def notify_review(
    db: Session,
    row: "ExerciseAssignment",
    *,
    base_url: str | None = None,
) -> dict | None:
    """Text the patient that their therapist replied to the clip on ``row``,
    with a link to that exercise. Same return shape as ``notify_assigned``."""
    return None


def text_today(
    db: Session,
    patient: "Patient",
    *,
    base_url: str | None = None,
    day: date | None = None,
    by: str | None = None,
) -> dict | None:
    """Text ``patient`` the plan for ``day`` (default today): how many
    exercises, the first title, and a link to the day. Same return shape."""
    return None
