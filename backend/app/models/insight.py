from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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
from app.models.enums import InsightKind, RiskLevel, TrajectoryState


class RiskAssessment(Base):
    """Output of one engine run for one patient. Latest row per patient is live."""

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    risk_level: Mapped[RiskLevel] = mapped_column(String)
    risk_score: Mapped[float] = mapped_column(Float)
    # [{code, text, metric_type, severity}] — typed reason codes; consumed by UI + LLM prompts
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    data_confidence: Mapped[float] = mapped_column(Float)
    trajectory_state: Mapped[TrajectoryState] = mapped_column(String)
    trajectory_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Full serialized AnalyticsBundle — metric cards / charts read from here.
    analytics: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_hash: Mapped[str] = mapped_column(String, index=True)
    engine_version: Mapped[str] = mapped_column(String)


class Insight(Base):
    """Cached LLM (or deterministic-fallback) narrative output, keyed by input hash."""

    __tablename__ = "insights"
    __table_args__ = (Index("ix_insights_lookup", "patient_id", "kind", "input_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.id"), nullable=True  # NULL = roster-level daily briefing
    )
    kind: Mapped[InsightKind] = mapped_column(String)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_hash: Mapped[str] = mapped_column(String)
    llm_provider: Mapped[str] = mapped_column(String)  # "groq" | "fallback"
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class EstablishedBaseline(Base):
    """The patient's pre-op norm for one metric, as established the first time
    the engine saw enough pre-op history to compute it.

    Why this is stored rather than recomputed from whatever is on file today:
    compute_baseline() reads every day with a negative post-op index as pre-op,
    so a back-fill delivered weeks after surgery does not extend the pre-op
    record — it REWRITES the reference every z-score is measured against, and
    it does so silently. Fourteen backdated days at 95 bpm move a patient's
    resting-HR baseline from 64 to 84 and drop them from HIGH to MEDIUM with a
    200 OK and no trace on any screen.

    A personal baseline is a clinical reference, not a running statistic: it is
    established once, from the history that existed at the time, and after that
    a correction to it is an operator decision (a forced recompute), never a
    side effect of an inbound webhook. Only pre-op baselines are stored — a
    post-op anchor is provisional by construction, and must stay free to be
    replaced by the real thing if pre-op history ever arrives.
    """

    __tablename__ = "established_baselines"
    __table_args__ = (
        UniqueConstraint("patient_id", "metric_type", name="uq_established_baseline"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    metric_type: Mapped[str] = mapped_column(String)
    mean: Mapped[float] = mapped_column(Float)
    sd: Mapped[float] = mapped_column(Float)
    n_days: Mapped[int] = mapped_column(Integer)
    window: Mapped[str] = mapped_column(String)
    # post-op day indices the mean was taken from (all negative)
    window_days: Mapped[list[Any]] = mapped_column(JSON, default=list)
    established_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    engine_version: Mapped[str] = mapped_column(String, default="")
