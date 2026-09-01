from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String
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
