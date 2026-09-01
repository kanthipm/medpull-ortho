from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import AdherenceStatus


class AdherenceTask(Base):
    """An assigned recovery task (exercises, walking goals, wound care...)."""

    __tablename__ = "adherence_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    title: Mapped[str] = mapped_column(String)
    why: Mapped[str] = mapped_column(String)          # clinical rationale shown to patient
    verified_by: Mapped[str] = mapped_column(String)  # e.g. "step data", "self-report"
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AdherenceRecord(Base):
    __tablename__ = "adherence_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("adherence_tasks.id"))
    date: Mapped[date] = mapped_column(Date)
    status: Mapped[AdherenceStatus] = mapped_column(String)
