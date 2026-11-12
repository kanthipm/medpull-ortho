"""The demo members of MedPull Personal.

The Personal tier has no console of its own: a subscriber's space is
theirs, and every console roster query filters them out
(``app/personal/scope.py``). The showcase needs something to show, so the
demo stack carries a handful of fictional members, each marked in
``PersonalProfile.settings["showcase"]``, and only rows with that mark are
ever listed or opened by the console's Personal pages
(``app/api/console_personal.py``) — and only while ``DEMO_MODE`` is on.

The functions below are the contract the fill, the persona list and the
console call against.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.patient import Patient

# The key in PersonalProfile.settings that marks a generated member.
MARK = "showcase"


def is_showcase(db: Session, patient: Patient | None) -> bool:
    """Whether ``patient`` is a generated demo member (a personal row whose
    profile carries the mark). A real subscriber is never one."""
    return False


def members(db: Session) -> list[Patient]:
    """Every generated demo member, hero first. Empty off the demo stack."""
    return []


def seed_personal(db: Session, today: date | None = None) -> list[str]:
    """Create or refresh the demo members, anchored to ``today``; returns
    their patient ids. Idempotent, and never touches a row without the mark."""
    return []
