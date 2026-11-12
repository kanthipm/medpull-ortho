"""The showcase: one roster of fictional people across the three versions
of the product, and the one fill that keeps all of them current.

The demo console switches between Clinic, Personal and Sports, and the demo
iPhone app signs in as any of these people without an account. Both read
the same registry here, so a persona the console shows is one the phone can
become.

* ``REGISTRY`` — who exists, by version and org.
* ``personas`` — the registry intersected with the rows that exist, in the
  shape ``GET /api/demo/personas`` returns.
* ``fill_showcase`` — (re)anchor every demo org to today: the clinic
  personas and the H.I.R.T. lifters (``demo_fill``), the sports rosters
  (``app/sports/seed.py``) and the Personal members
  (``app/personal/showcase.py``). Idempotent; refuses off the demo stack.

The bodies below are the contract the demo routes and the Lambda action
call against.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

VERSIONS = ("clinic", "personal", "sports")


@dataclass(frozen=True)
class Persona:
    """One fictional person the showcase can show and the phone can become."""

    id: str
    name: str
    version: str  # clinic | personal | sports
    org_id: str  # hospital id, "personal", or the team id
    org_name: str
    tagline: str  # one line under the name: the program, the goal, the position
    detail: str = ""  # what today's story is ("Load spike, pain rising")
    hero: bool = False  # the one to open first in its org


REGISTRY: tuple[Persona, ...] = ()


def persona(persona_id: str) -> Persona | None:
    """The registry entry for an id, or None: only registry ids can be
    signed into from the demo routes."""
    return next((p for p in REGISTRY if p.id == persona_id), None)


def personas(db: Session) -> dict:
    """The persona list by version and org, for ``GET /api/demo/personas``."""
    return {"as_of": date.today().isoformat(), "versions": []}


def fill_showcase(db: Session, today: date | None = None, *, force: bool = False) -> dict:
    """Bring every demo org up to ``today``. Returns a small report."""
    return {"filled_on": (today or date.today()).isoformat(), "personas": 0}
