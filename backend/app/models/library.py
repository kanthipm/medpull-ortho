"""Care-plan library tables and the next-step execution log.

``TaskTemplate`` and ``MessageTemplate`` are the library the console
assigns from (seeded content plus what clinicians save); ``CareAction`` is
the record of a recommended next step being executed or dismissed, which is
what keeps an executed step from being recommended again during its
cooldown. ``TaskVerification`` carries the provenance of an adherence record
(which data confirmed it, the count behind it): the record table itself
belongs to the patient-app session, so the verification engine keeps its
side of the story in a table of its own keyed by (task, day).
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaskTemplate(Base):
    __tablename__ = "task_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # library slug ("uc1_early_three_walks"); None for a clinician-saved custom
    key: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    title: Mapped[str] = mapped_column(String)            # patient-facing, plain, number-free
    why: Mapped[str] = mapped_column(String)              # patient-facing one line
    clinical_target: Mapped[str] = mapped_column(String, default="")  # provider-facing
    task_kind: Mapped[str] = mapped_column(String, default="custom")   # patient-app kind
    verify_kind: Mapped[str] = mapped_column(String, default="custom") # plan.verify_kinds
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    schedule: Mapped[str] = mapped_column(String, default="daily")
    phase: Mapped[str] = mapped_column(String, default="ongoing")
    feeds: Mapped[list[Any]] = mapped_column(JSON, default=list)      # ["M1", "M14"]
    # pathway keys ("ortho_tka") or domains ("ortho"); [] = every pathway
    pathways: Mapped[list[Any]] = mapped_column(JSON, default=list)
    use_case: Mapped[str] = mapped_column(String, default="custom")   # "UC1".."UC12" | custom
    source: Mapped[str] = mapped_column(String, default="library")    # library | custom | ai
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)      # quick-invoke chip
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String, default="library")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(String)             # may use {first} and {surgeon}
    tone: Mapped[str] = mapped_column(String, default="warm")
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String, default="library")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String, default="library")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CareAction(Base):
    """One recommended next step executed (or dismissed) for a patient."""

    __tablename__ = "care_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    step_key: Mapped[str] = mapped_column(String)
    action_type: Mapped[str] = mapped_column(String)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    executed_by: Mapped[str] = mapped_column(String, default="provider")
    # {"task_ids": [...]} | {"message_id", "status"} | {"notification_ids"} | {"note"}
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # "Not now": hides the step for its cooldown without executing it.
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)


class TaskVerification(Base):
    """Provenance for one adherence record: what confirmed it and the count
    behind it (steps over a band, walks counted, logs seen)."""

    __tablename__ = "task_verifications"
    __table_args__ = (UniqueConstraint("task_id", "date", name="uq_task_verification_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("adherence_tasks.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    # "data:<metric>" | "self_report" | "provider"
    source: Mapped[str] = mapped_column(String, default="self_report")
    count: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
