"""MedPull Sports: the third variant.

An athlete is a ``Patient`` row with ``account_kind="sports"``, no hospital,
and the same email/password credential, consent and wearable stream the
personal tier uses. Everything that is specific to sport hangs off it here:
the organisation and team they play for, the staff who coach them, the
performance tests they log, the sessions that make up their training load,
the daily wellness they report, and the injuries they are coming back from
with the rehab measures that decide when they are ready.

Separate tables, on purpose: a clinic chart never has a vertical jump, and
the console never reads any of these. The team dashboard (``app/sports/api``)
is the only reader outside the athlete's own app.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SPORTS = ("basketball", "tennis", "soccer")
SPORT_LABELS = {"basketball": "Basketball", "tennis": "Tennis", "soccer": "Soccer"}

# What the athlete is to their program today. Decided by the rehab engine for
# an injured athlete and by the staff for everyone; the roster board reads it.
STATUSES = ("available", "modified", "out")
STATUS_LABELS = {"available": "Available", "modified": "Modified", "out": "Out"}

LEVELS = ("pro", "ncaa_d1", "ncaa_d2", "ncaa_d3", "juco", "high_school", "club", "recreational")
LEVEL_LABELS = {
    "pro": "Professional", "ncaa_d1": "NCAA Division I", "ncaa_d2": "NCAA Division II",
    "ncaa_d3": "NCAA Division III", "juco": "Junior college", "high_school": "High school",
    "club": "Club / academy", "recreational": "Recreational",
}


class SportsOrg(Base):
    """A program: a university's athletics department, a franchise, a club."""

    __tablename__ = "sports_orgs"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # slug: "rice"
    name: Mapped[str] = mapped_column(String)
    short_name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # college | pro | club | academy
    city: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String)
    conference: Mapped[str | None] = mapped_column(String, nullable=True)
    level: Mapped[str] = mapped_column(String, default="ncaa_d1")
    # The code an athlete types to join without a staff invitation.
    join_code: Mapped[str | None] = mapped_column(String, nullable=True)
    # Brand colours as hex, for the team dashboard's accent only.
    colors: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    timezone: Mapped[str] = mapped_column(String, default="America/Chicago")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class SportsTeam(Base):
    __tablename__ = "sports_teams"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # "rice-mbb"
    org_id: Mapped[str] = mapped_column(ForeignKey("sports_orgs.id"), index=True)
    name: Mapped[str] = mapped_column(String)  # "Men's Basketball"
    sport: Mapped[str] = mapped_column(String)
    sex: Mapped[str | None] = mapped_column(String, nullable=True)  # M | F | mixed
    season: Mapped[str] = mapped_column(String, default="2026-27")
    # Where the season is: preseason | in_season | postseason | offseason.
    phase: Mapped[str] = mapped_column(String, default="in_season")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class SportsStaff(Base):
    """A coach, strength coach, athletic trainer, sports scientist or team
    physician. Reads the team dashboard; messages land on the athlete's
    thread signed with the staff member's name."""

    __tablename__ = "sports_staff"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("sports_orgs.id"), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("sports_teams.id"), nullable=True)
    name: Mapped[str] = mapped_column(String)
    # head_coach | assistant_coach | strength | athletic_trainer | sports_scientist | physician
    role: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    # Whether the athlete's app shows this person as someone they can write to.
    athlete_facing: Mapped[bool] = mapped_column(Boolean, default=True)


class SportsProfile(Base):
    """The athlete behind a sports account."""

    __tablename__ = "sports_profiles"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), primary_key=True)
    sport: Mapped[str] = mapped_column(String)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("sports_orgs.id"), nullable=True, index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("sports_teams.id"), nullable=True, index=True)
    # Linked to the staff: on a team roster the staff see this athlete.
    coach_linked: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[str | None] = mapped_column(String, nullable=True)
    jersey: Mapped[str | None] = mapped_column(String, nullable=True)
    class_year: Mapped[str | None] = mapped_column(String, nullable=True)  # Fr | So | Jr | Sr | Gr
    level: Mapped[str] = mapped_column(String, default="ncaa_d1")
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    wingspan_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    standing_reach_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    dominant_side: Mapped[str | None] = mapped_column(String, nullable=True)  # left | right
    status: Mapped[str] = mapped_column(String, default="available")
    status_note: Mapped[str | None] = mapped_column(String, nullable=True)
    units: Mapped[str] = mapped_column(String, default="imperial")
    # Female athletes who opt in: cycle tracking feeds readiness wording.
    cycle_tracking: Mapped[bool] = mapped_column(Boolean, default=False)
    # Connected team devices that are not live integrations (Catapult, VERT,
    # force plates...) and any per-athlete preferences: {"devices": {...}}.
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class SportsTest(Base):
    """One performance test result: a vertical jump, a lane agility time, a
    Nordic hamstring force, a Yo-Yo level. ``side`` separates a left-leg
    hop from a right-leg hop so asymmetry can be computed."""

    __tablename__ = "sports_tests"
    __table_args__ = (Index("ix_sports_tests_patient_key_date", "patient_id", "test_key", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    test_key: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String)
    side: Mapped[str | None] = mapped_column(String, nullable=True)  # left | right | None
    # manual | force_plate | timing_gates | dynamometer | phone | wearable | staff | import
    source: Mapped[str] = mapped_column(String, default="manual")
    device: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class SportsSession(Base):
    """A practice, game, lift, shootaround or rehab session, with the load
    measures a team's devices produce when they are connected."""

    __tablename__ = "sports_sessions"
    __table_args__ = (Index("ix_sports_sessions_patient_date", "patient_id", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    # practice | game | lift | shootaround | conditioning | individual | rehab | match | training
    kind: Mapped[str] = mapped_column(String, default="practice")
    minutes: Mapped[float] = mapped_column(Float)
    rpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Foster session load: minutes × RPE, in arbitrary units.
    load_au: Mapped[float | None] = mapped_column(Float, nullable=True)
    player_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    jumps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jump_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_speed_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    accelerations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decelerations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String, default="manual")  # manual | catapult | kinexon | ...
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class SportsWellness(Base):
    """The morning wellness answers no device measures: sleep quality,
    fatigue, soreness, stress, mood (the Hooper index) plus hydration, pain
    and, when tracked, cycle phase. One row per key per day."""

    __tablename__ = "sports_wellness"
    __table_args__ = (Index("ix_sports_wellness_patient_date", "patient_id", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    key: Mapped[str] = mapped_column(String)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="app")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class SportsInjury(Base):
    """An injury the athlete is managing or has come back from."""

    __tablename__ = "sports_injuries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    injury_key: Mapped[str] = mapped_column(String)  # acl_reconstruction, ankle_sprain, ...
    label: Mapped[str] = mapped_column(String)
    side: Mapped[str | None] = mapped_column(String, nullable=True)
    body_region: Mapped[str] = mapped_column(String)  # knee | ankle | hamstring | ...
    date_of_injury: Mapped[date] = mapped_column(Date)
    date_of_surgery: Mapped[date | None] = mapped_column(Date, nullable=True)
    graft: Mapped[str | None] = mapped_column(String, nullable=True)
    mechanism: Mapped[str | None] = mapped_column(String, nullable=True)
    grade: Mapped[str | None] = mapped_column(String, nullable=True)
    # active | cleared (returned to full play) | resolved
    status: Mapped[str] = mapped_column(String, default="active")
    # The phase the engine last placed the athlete in (1-based), and a staff
    # override when a clinician decides otherwise.
    phase: Mapped[int] = mapped_column(Integer, default=1)
    phase_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cleared_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    clinician: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class SportsRehabMeasure(Base):
    """One rehab measurement on one injury: knee flexion in degrees, effusion
    grade, quad strength in newtons per side, a hop distance per side, a
    questionnaire score. The rehab engine reads these to place the athlete
    in a phase and tick return-to-sport criteria."""

    __tablename__ = "sports_rehab_measures"
    __table_args__ = (Index("ix_sports_rehab_injury_key_date", "injury_id", "measure_key", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    injury_id: Mapped[int] = mapped_column(ForeignKey("sports_injuries.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    measure_key: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String)
    side: Mapped[str | None] = mapped_column(String, nullable=True)  # involved | uninvolved | left | right
    source: Mapped[str] = mapped_column(String, default="manual")  # manual | phone | dynamometer | staff
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class SportsEvent(Base):
    """The team calendar: practices, games, travel, lifts, days off."""

    __tablename__ = "sports_events"
    __table_args__ = (Index("ix_sports_events_team_date", "team_id", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("sports_teams.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[str | None] = mapped_column(String, nullable=True)  # "19:00"
    kind: Mapped[str] = mapped_column(String)  # practice | game | lift | travel | off | shootaround
    title: Mapped[str] = mapped_column(String)
    opponent: Mapped[str | None] = mapped_column(String, nullable=True)
    home: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
