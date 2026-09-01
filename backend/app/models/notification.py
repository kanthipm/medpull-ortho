from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import NotificationChannel, NotificationStatus


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    recipient_id: Mapped[str | None] = mapped_column(
        ForeignKey("care_team_members.id"), nullable=True
    )
    # priority_high (engine, on a non-HIGH -> HIGH edge) | escalation (a
    # provider pressing Escalate on the patient page)
    kind: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(String)
    channel: Mapped[NotificationChannel] = mapped_column(String)
    status: Mapped[NotificationStatus] = mapped_column(String, default="unread")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("care_team_members.id"))
    channel: Mapped[NotificationChannel] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_priority: Mapped[str] = mapped_column(String, default="high")  # high|medium
