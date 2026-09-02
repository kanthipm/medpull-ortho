"""A patient's account with a wearable aggregator.

Junction (and Terra, when it ships) hold one *user* per patient and deliver
every webhook keyed by that user's id, never by anything the patient typed.
This row is the only place the two identities meet, and it is the mapping
``api/webhooks.py`` resolves a delivery through: an event for a user id with
no row here is recorded and ignored, because trusting an id inside the body
would let anyone with the endpoint URL write into a patient's chart.

The ``client_user_id`` is the reference *we* gave the aggregator. It is an
opaque token, not the patient slug or anything derived from PHI — Junction's
own guidance, and also the reason a leaked aggregator export cannot be joined
back to a chart without this table.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import ConnectionStatus, SourceProvider


class WearableConnection(Base):
    __tablename__ = "wearable_connections"
    __table_args__ = (
        # One aggregator account per patient, and one patient per aggregator
        # account: a Junction user id that mapped to two charts would let one
        # patient's readings score another's tier.
        UniqueConstraint("aggregator", "patient_id", name="uq_wearable_connection_patient"),
        UniqueConstraint(
            "aggregator", "external_user_id", name="uq_wearable_connection_external_user"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    aggregator: Mapped[SourceProvider] = mapped_column(String)  # "junction"
    # The aggregator's id for this patient — what every webhook carries.
    external_user_id: Mapped[str] = mapped_column(String, index=True)
    # The opaque reference we registered with the aggregator.
    client_user_id: Mapped[str] = mapped_column(String, unique=True)
    # sandbox | production. A sandbox user is meaningless against the
    # production host and vice versa, so the API refuses to act on a row made
    # in the other environment rather than confusing a 404 for a lost user.
    environment: Mapped[str] = mapped_column(String)
    status: Mapped[ConnectionStatus] = mapped_column(
        String, default=ConnectionStatus.PENDING_LINK
    )
    # Snapshot of the providers the aggregator reports as connected for this
    # user: [{slug, name, status, connected_at, error?}]. Refreshed from
    # provider.connection.* events and from the aggregator on demand.
    providers: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    last_link_issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Any verified delivery for this user, whatever it carried.
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # The last delivery or pull that wrote or restated an observation.
    last_data_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_backfill_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)

    patient = relationship("Patient")
