"""Hospitals — the first thing a patient picks in the app.

A patient belongs to at most one hospital, and the app's patient search is
scoped to the hospital the person chose, so a name typed on the onboarding
screen is matched against one roster rather than the whole database.
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # slug, e.g. "hosp_medpull"
    name: Mapped[str] = mapped_column(String)
    system: Mapped[str | None] = mapped_column(String, nullable=True)  # health system, if any
    city: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(String, default="America/Chicago")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    access_token: Mapped[str | None] = mapped_column(String, nullable=True)  # dashboard login token
