from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String
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
        Index("ix_obs_patient_local_date", "patient_id", "local_date"),
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
    timezone: Mapped[str] = mapped_column(String, default="America/New_York")  # IANA tz id
    utc_offset_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The patient-local calendar day — the auditable unit of RTM day-counting,
    # materialized at ingest (connectors/base.local_date_of) so no reader has
    # to call func.date(start_time): a West Coast patient's evening activity
    # must not land on the next UTC day. This column is the product's single
    # day definition — RTM counts it (rtm/coverage.py) and the engine builds
    # its post-op day axis from it (engine/dataload.py), so the two cannot
    # drift apart whatever tz an observation arrives in.
    local_date: Mapped[date] = mapped_column(Date)
    granularity: Mapped[Granularity] = mapped_column(String)
    # Laterality/site — without these, operative-vs-contralateral comparison is
    # unrepresentable and two devices (one per wrist) collide on dedupe.
    body_site: Mapped[str | None] = mapped_column(String, nullable=True)
    side: Mapped[str | None] = mapped_column(String, nullable=True)  # left|right|bilateral
    # Restatement machinery: providers routinely revise rows (Apple resting HR,
    # Garmin sleep, WHOOP edits). external_id is the provider's stable record
    # id; revision counts accepted restatements; source_updated_at orders them;
    # payload_hash short-circuits byte-identical redeliveries.
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # Tombstone: HealthKit/Health Connect deliver deletions; a hard delete
    # would silently inflate historical RTM day counts on recompute.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Set at normalize()/seed time. Mock webhook rows and unsigned deliveries
    # are structurally incapable of counting toward a billed monitoring day.
    qualifies_for_rtm: Mapped[bool] = mapped_column(Boolean, default=False)
    is_patient_reported: Mapped[bool] = mapped_column(Boolean, default=False)
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
