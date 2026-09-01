from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Checkin(Base):
    """A completed recovery conversation (patient <-> copilot)."""

    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    channel: Mapped[str] = mapped_column(String, default="app")  # app|sms|kiosk

    messages: Mapped[list["CheckinMessage"]] = relationship(
        back_populates="checkin", order_by="CheckinMessage.seq"
    )


class CheckinMessage(Base):
    __tablename__ = "checkin_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checkin_id: Mapped[int] = mapped_column(ForeignKey("checkins.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    who: Mapped[str] = mapped_column(String)  # "patient" | "copilot"
    text: Mapped[str] = mapped_column(String)

    checkin: Mapped[Checkin] = relationship(back_populates="messages")
