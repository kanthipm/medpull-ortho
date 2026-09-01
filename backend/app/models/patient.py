from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import CareRole, ProcedureType, SourceProvider


class CareTeamMember(Base):
    __tablename__ = "care_team_members"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[CareRole] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # slug, e.g. "marcus"
    name: Mapped[str] = mapped_column(String)
    initials: Mapped[str] = mapped_column(String)
    age: Mapped[int] = mapped_column(Integer)
    sex: Mapped[str] = mapped_column(String)  # "M" | "F"
    procedure_type: Mapped[ProcedureType] = mapped_column(String)
    procedure_display: Mapped[str] = mapped_column(String)  # "Total Knee Replacement (TKA)"
    surgery_date: Mapped[date] = mapped_column(Date)
    discharge_date: Mapped[date] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String, default="America/New_York")
    surgeon_id: Mapped[str] = mapped_column(ForeignKey("care_team_members.id"))
    assigned_provider_id: Mapped[str] = mapped_column(ForeignKey("care_team_members.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    surgeon: Mapped[CareTeamMember] = relationship(foreign_keys=[surgeon_id])
    assigned_provider: Mapped[CareTeamMember] = relationship(foreign_keys=[assigned_provider_id])
    # Newest connection first: a patient who upgrades a watch keeps both rows,
    # and readers that take devices[0] as "the" device need that to be stable
    # rather than whichever row the planner returned.
    devices: Mapped[list["Device"]] = relationship(
        back_populates="patient", order_by="(Device.connected_at.desc(), Device.id)"
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    source_provider: Mapped[SourceProvider] = mapped_column(String)
    device_model: Mapped[str] = mapped_column(String)  # "Apple Watch Series 10"
    connected_at: Mapped[datetime] = mapped_column(DateTime)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="connected")  # connected|stale|revoked

    patient: Mapped[Patient] = relationship(back_populates="devices")
