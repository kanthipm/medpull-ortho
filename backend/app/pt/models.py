"""Tables for the between-visits record (see the package docstring)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClinicSetting(Base):
    """One clinic's own settings, as one JSON document: the thresholds its
    flags fire on, how many exercises a day may carry before the calendar
    asks, the words that make a question one for today, and the defaults of
    the next-morning check. Absent, every value is the product's default
    (``app/pt/settings.py``)."""

    __tablename__ = "pt_clinic_settings"

    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)


class PatientSetting(Base):
    """One person's own settings where they differ from the clinic's: the
    next-morning check (on or off, the pain ceiling that counts as settled)
    and the Friday check-in."""

    __tablename__ = "pt_patient_settings"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)


class RedFlagText(Base):
    """The clinic's fixed words for one worrying thing a person may text.

    ``phrases`` are what to listen for; ``text`` is what goes back. It goes
    back only once a clinician has approved it (``status`` approved), word
    for word, and never from a model. A draft still raises the alert; it
    just sends nothing."""

    __tablename__ = "pt_red_flag_texts"
    __table_args__ = (UniqueConstraint("hospital_id", "key", name="uq_red_flag_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    key: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    phrases: Mapped[list[Any]] = mapped_column(JSON, default=list)
    text: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="draft")  # draft | approved
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class PainArea(Base):
    """A body area a person's pain is in. ``evaluation`` rows are what the
    therapist recorded at the visit; ``reported`` rows are areas the person
    named since. A reported area that is not among the evaluation's is the
    "new area" the morning list puts first."""

    __tablename__ = "pt_pain_areas"
    __table_args__ = (UniqueConstraint("patient_id", "region", name="uq_pain_area"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    region: Mapped[str] = mapped_column(String)  # app.pt.regions.REGIONS
    source: Mapped[str] = mapped_column(String, default="evaluation")  # evaluation | reported
    noted_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    # Set when the therapist has seen a reported area at a visit: it stops
    # being new without being forgotten.
    seen_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class MorningCheck(Base):
    """The morning after a loaded session: how the pain is now and whether
    the person is stiffer than usual. ``settled`` is the clinic's own rule
    applied to the answer (pain at or under the ceiling, and not stiffer);
    it is empty until the person answers."""

    __tablename__ = "pt_morning_checks"
    __table_args__ = (UniqueConstraint("patient_id", "session_day", name="uq_morning_check"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    session_day: Mapped[date] = mapped_column(Date)  # the day the load was done
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    asked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pain: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-10
    stiffer: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ceiling: Mapped[int] = mapped_column(Integer, default=3)  # the ceiling in force when asked
    settled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class FunctionGoal(Base):
    """Something the person wants to get back to, in their words ("pull 315
    from the floor"). Up to three are active at a time."""

    __tablename__ = "pt_function_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    text: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String, default="patient")  # patient | care team id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FunctionRating(Base):
    """How able the person is to do one goal today: 0 unable, 10 as before."""

    __tablename__ = "pt_function_ratings"
    __table_args__ = (UniqueConstraint("goal_id", "rated_on", name="uq_function_rating"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("pt_function_goals.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    rated_on: Mapped[date] = mapped_column(Date)
    score: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String, default="patient")  # patient | clinic


class WeekCheckin(Base):
    """The Friday word on the week: how it went, and what is different about
    the next one. The therapist reads it beside next week's draft."""

    __tablename__ = "pt_week_checkins"
    __table_args__ = (UniqueConstraint("patient_id", "week_start", name="uq_week_checkin"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date)  # the Monday of the week it is about
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    asked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    went: Mapped[str | None] = mapped_column(String, nullable=True)  # better | same | worse
    change_note: Mapped[str | None] = mapped_column(String, nullable=True)


class Protocol(Base):
    """A clinic's protocol as phases, each with the criteria its therapists
    look for before the next one."""

    __tablename__ = "pt_protocols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, default="")
    # [{"name", "goal", "criteria": ["...", ...]}]
    phases: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String, default="provider")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PatientPhase(Base):
    """One phase of one person's program. Exactly one is ``current``. It
    ends when a therapist says so: the criteria are a checklist she ticks,
    not a rule the software runs."""

    __tablename__ = "pt_patient_phases"
    __table_args__ = (Index("ix_patient_phase_order", "patient_id", "position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    protocol_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protocol_name: Mapped[str] = mapped_column(String, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String)
    goal: Mapped[str] = mapped_column(String, default="")
    # [{"text", "met": bool, "met_at": iso | None, "met_by": care team id | None}]
    criteria: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="upcoming")  # upcoming | current | done
    started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    advanced_by: Mapped[str | None] = mapped_column(String, nullable=True)


class Measurement(Base):
    """A number from a test: the therapist's on a test day (a force plate, a
    hop, a strength test), or one the person timed at home (a hold)."""

    __tablename__ = "pt_test_results"
    __table_args__ = (Index("ix_test_results_patient_day", "patient_id", "tested_on"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    hospital_id: Mapped[str | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)
    tested_on: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String)  # app.pt.tests.KINDS, or "custom"
    label: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String, default="na")  # left | right | both | na
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String, default="")
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="clinic")  # clinic | patient
    entered_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Handoff(Base):
    """What a therapist wants a person's trainer to know: the limits, the
    caps, what to report back. It is a page behind a link, and the link
    exists only once the person has said yes to sharing it."""

    __tablename__ = "pt_handoffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    trainer_name: Mapped[str] = mapped_column(String, default="")
    limits: Mapped[list[Any]] = mapped_column(JSON, default=list)  # ["...", ...]
    report_back: Mapped[str] = mapped_column(String, default="")
    # Also show this week's exercises and their ceilings on the page.
    include_week: Mapped[bool] = mapped_column(Boolean, default=True)
    # draft | awaiting (the person has been asked) | active | declined | revoked
    status: Mapped[str] = mapped_column(String, default="draft")
    # The link's secret, set when the person agrees. Kept as it is (not as a
    # hash) because the therapist copies the link from the chart again later;
    # the page behind it holds limits and doses, nothing from the record.
    token: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    authorised_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String, default="provider")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    open_count: Mapped[int] = mapped_column(Integer, default=0)


class ClipComment(Base):
    """A therapist's remark on a person's clip: at a moment in it
    (``at_ms``), or on the whole of it; typed, or spoken (a voice note kept
    as an attachment on the person's thread)."""

    __tablename__ = "pt_clip_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("exercise_assignments.id"), index=True
    )
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    at_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(String, default="")
    voice_attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachments.id"), nullable=True
    )
    by: Mapped[str] = mapped_column(String, default="provider")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class OutcomeSchedule(Base):
    """An outcome measure a person is asked for on a rhythm."""

    __tablename__ = "pt_outcome_schedules"
    __table_args__ = (UniqueConstraint("patient_id", "instrument", name="uq_outcome_schedule"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    instrument: Mapped[str] = mapped_column(String)  # app.pt.instruments.INSTRUMENTS
    every_days: Mapped[int] = mapped_column(Integer, default=14)
    next_due: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(String, default="provider")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class OutcomeScore(Base):
    """One score of one outcome measure on one day."""

    __tablename__ = "pt_outcome_scores"
    __table_args__ = (Index("ix_outcome_scores_patient", "patient_id", "instrument", "scored_on"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    instrument: Mapped[str] = mapped_column(String)
    scored_on: Mapped[date] = mapped_column(Date)
    total: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String, default="clinic")  # clinic | patient
    entered_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ClinicVisit(Base):
    """A visit to the clinic, on the calendar beside the exercises: what
    "since your last visit" is counted from and what "next session" means."""

    __tablename__ = "pt_clinic_visits"
    __table_args__ = (Index("ix_clinic_visits_day", "hospital_id", "visit_on"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    visit_on: Mapped[date] = mapped_column(Date)
    at: Mapped[str | None] = mapped_column(String, nullable=True)  # "14:30"
    kind: Mapped[str] = mapped_column(String, default="visit")  # visit | evaluation | test_day
    note: Mapped[str] = mapped_column(String, default="")
    created_by: Mapped[str] = mapped_column(String, default="provider")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CalendarMark(Base):
    """A day marked on a person's calendar that is not an exercise: a rest
    day, set on purpose, so an empty day reads as a decision."""

    __tablename__ = "pt_calendar_marks"
    __table_args__ = (UniqueConstraint("patient_id", "day", "kind", name="uq_calendar_mark"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String, default="rest")
    note: Mapped[str] = mapped_column(String, default="")
    created_by: Mapped[str] = mapped_column(String, default="provider")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class FlagEvent(Base):
    """A flag that was up on a chart on a day: one row per chart, flag and
    day, written when the chart is scored. The rules page counts these."""

    __tablename__ = "pt_flag_events"
    __table_args__ = (UniqueConstraint("patient_id", "code", "day", name="uq_flag_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    code: Mapped[str] = mapped_column(String)
    day: Mapped[date] = mapped_column(Date)
