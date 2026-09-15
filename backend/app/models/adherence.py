from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import AdherenceStatus


class AdherenceTask(Base):
    """An assigned recovery task (exercises, walking goals, wound care...).

    Originally a static row the seed wrote and the adherence engine scored
    records against. The patient app made it a live thing: a task is created
    by the care team (or the daily check-in schedule), texted to the patient
    through Sendblue, and completed in the app, by text, or by voice. The
    lifecycle columns below are all nullable or defaulted so the additive
    schema step can add them to a database that predates the app.
    """

    __tablename__ = "adherence_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    title: Mapped[str] = mapped_column(String)
    why: Mapped[str] = mapped_column(String)          # clinical rationale shown to patient
    verified_by: Mapped[str] = mapped_column(String)  # e.g. "step data", "self-report"
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # checkin | exercise | walk | medication | wound_check | custom
    kind: Mapped[str] = mapped_column(String, default="custom")
    # pending (created) | sent (texted) | done | skipped
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # app | sms | voice | web | console
    completed_via: Mapped[str | None] = mapped_column(String, nullable=True)
    # The web/deep-link token's hash (the raw token is in the text message).
    token_hash: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    # Free-form state: the SMS conversation cursor, the answers given, etc.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AdherenceRecord(Base):
    __tablename__ = "adherence_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("adherence_tasks.id"))
    date: Mapped[date] = mapped_column(Date)
    status: Mapped[AdherenceStatus] = mapped_column(String)
