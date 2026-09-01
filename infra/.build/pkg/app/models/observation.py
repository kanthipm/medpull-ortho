from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import Granularity, MetricType, SourceProvider


class Observation(Base):
    """Canonical normalized store for all external health data (Open mHealth-style).

    Every wearable/EHR/lab source — mocked today, real later — lands here via a
    connector's normalize() so the engine and frontend never see provider payloads.
    """

    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_obs_patient_metric_time", "patient_id", "metric_type", "start_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    source_provider: Mapped[SourceProvider] = mapped_column(String)
    source_device_id: Mapped[str | None] = mapped_column(String, nullable=True)
    metric_type: Mapped[MetricType] = mapped_column(String)
    unit: Mapped[str] = mapped_column(String)  # "count", "bpm", "ms", "h", "%", "degC", "m/s"
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    timezone: Mapped[str] = mapped_column(String, default="America/New_York")
    granularity: Mapped[Granularity] = mapped_column(String)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    dedupe_key: Mapped[str] = mapped_column(String, unique=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="received")  # received|processed|failed
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
