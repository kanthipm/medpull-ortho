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

    id: Mapped[str] = mapped_column(String, primary_key=True)  # slug, e.g. "steve"
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
    # --- patient-app identity (all nullable: the roster predates the app) ---
    hospital_id: Mapped[str | None] = mapped_column(
        ForeignKey("hospitals.id"), nullable=True, index=True
    )
    # E.164. Where Sendblue texts task invitations, and how an inbound text is
    # matched back to a chart. Never seeded from code — entered in the app.
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Hospital-issued medical record number, when the roster has one.
    mrn: Mapped[str | None] = mapped_column(String, nullable=True)
    # Which care pathway the engine scores this patient against ("ortho_tka",
    # "heart_failure", "copd", ...). NULL derives it from procedure_type.
    care_pathway: Mapped[str | None] = mapped_column(String, nullable=True)
    # --- the personal tier (app/personal) ---
    # "clinic": a chart on a hospital roster, followed by a care team (every
    # row before the personal tier existed). "personal": a subscriber's own
    # profile — no hospital, no care team, never on a worklist. The console
    # enumerates rosters through app.personal.scope.clinic_patients(), which
    # is what keeps the two apart.
    account_kind: Mapped[str] = mapped_column(String, default="clinic")
    # One person, two rows: a clinic chart and its personal profile point at
    # each other here, so the app can switch between them and the personal
    # side can read the chart's wearable stream (see observations_from).
    linked_patient_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.id"), nullable=True
    )
    # When set, this row has no wearable stream of its own: readers resolve
    # observations through app.personal.scope.data_patient_id(), which returns
    # this id. Set on a personal profile linked to a clinic chart, because the
    # phone's Health SDK can be signed into one aggregator user at a time and
    # the chart is the one the care team is watching.
    observations_from: Mapped[str | None] = mapped_column(
        ForeignKey("patients.id"), nullable=True
    )

    surgeon: Mapped[CareTeamMember] = relationship(foreign_keys=[surgeon_id])
    hospital = relationship("Hospital")
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
    # connected | stale | error (the aggregator reported a terminal provider
    # error, e.g. a revoked OAuth grant) | revoked (disconnected by an operator)
    status: Mapped[str] = mapped_column(String, default="connected")

    patient: Mapped[Patient] = relationship(back_populates="devices")
