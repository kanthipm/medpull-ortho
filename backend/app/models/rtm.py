from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import DocumentKind, DocumentStatus, InteractionKind, TimeLogActivity


class MonitoringWindow(Base):
    """RTM monitoring-day coverage per rolling 30-day window, counted from
    enrollment. The day count picks the CPT code: 98985 covers 2-15 monitoring
    days in the window, 98977 covers >=16 (SPEC.md §8, rtm/readiness.py)."""

    __tablename__ = "monitoring_windows"
    # One row per patient per window. coverage.update_window() selects then
    # inserts, so without this a second writer that misses the select inserts a
    # twin and get_current() can serve whichever copy won the id race.
    __table_args__ = (
        UniqueConstraint("patient_id", "window_start", name="uq_monitoring_window"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    window_start: Mapped[date] = mapped_column(Date)
    window_end: Mapped[date] = mapped_column(Date)
    days_with_data: Mapped[int] = mapped_column(Integer)
    qualifies_16_of_30: Mapped[bool] = mapped_column(Boolean)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class EnrollmentStatus(Base):
    """CPT 98975 enrollment state — education, consent, baseline. One row per
    patient; `complete` is derived, stored for cheap worklist queries."""

    __tablename__ = "rtm_enrollment"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), primary_key=True)
    education_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    education_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consent_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    baseline_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    baseline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # recovery pathway assigned during enrollment, e.g. "TKA standard"
    pathway: Mapped[str | None] = mapped_column(String, nullable=True)


class ProviderTimeLog(Base):
    """Provider review/treatment-management time (CPT 98979/98980/98981).
    `interactive` marks a live patient interaction (call), which the
    treatment-management codes require. Readiness sums a rolling 30-day window
    on `occurred_at` rather than calendar months, which are flaky near a month
    boundary (rtm/readiness.py)."""

    __tablename__ = "rtm_time_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("care_team_members.id"))
    activity: Mapped[TimeLogActivity] = mapped_column(String)
    seconds: Mapped[int] = mapped_column(Integer)
    interactive: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # "YYYY-MM" stamp kept for export and audit. Nothing in the app reads it:
    # every minutes calculation runs off occurred_at.
    month: Mapped[str] = mapped_column(String, index=True)


class RtmInteraction(Base):
    """Auto-logged treatment-management action (message, call, follow-up,
    escalation, plan update) — the audit trail behind the readiness card."""

    __tablename__ = "rtm_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("care_team_members.id"))
    kind: Mapped[InteractionKind] = mapped_column(String)
    detail: Mapped[str] = mapped_column(String, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RtmDocument(Base):
    """AI-generated RTM documentation (encounter notes, monthly summaries) —
    drafts until a provider approves them."""

    __tablename__ = "rtm_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    kind: Mapped[DocumentKind] = mapped_column(String)
    # {"title": ..., "body": ...} — body is guardrail-validated narrative
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    llm_provider: Mapped[str] = mapped_column(String)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(String, default=DocumentStatus.DRAFT)
    month: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(
        ForeignKey("care_team_members.id"), nullable=True
    )
