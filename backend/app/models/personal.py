"""The personal tier: a subscriber's profile, their entitlement, and the
daily things they log that no wearable measures.

A personal account is a ``Patient`` row with ``account_kind="personal"`` and
no hospital; the rows here hang off it. They are deliberately separate
tables rather than more columns on ``patients``: a clinic chart never has a
goal, a subscription or a training log, and the console never reads these.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# What a personal subscriber said they want out of the app. The goal decides
# which metrics lead, which tasks the plan writes, and how the coach talks.
GOALS = ("recovery", "performance", "sleep", "everyday")
GOAL_LABELS = {
    "recovery": "Recover from an injury or surgery",
    "performance": "Train and perform",
    "sleep": "Sleep and recover better",
    "everyday": "Everyday health",
}


class PersonalProfile(Base):
    __tablename__ = "personal_profiles"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), primary_key=True)
    goal: Mapped[str] = mapped_column(String, default="everyday")
    # "running", "cycling", "lifting", "team sport", ... free text, for the
    # coach and the plan's wording. Empty for the non-training goals.
    sport: Mapped[str | None] = mapped_column(String, nullable=True)
    # Performance: the training minutes a week they are aiming for.
    weekly_target_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Sleep: the hours they want, when they said one; else the engine's own
    # estimate of their need stands in.
    sleep_target_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Recovery: what they are coming back from, in their words ("ACL, left").
    injury: Mapped[str | None] = mapped_column(String, nullable=True)
    # A date that matters to the goal: the surgery or injury date for
    # recovery, an event for performance. The Patient's anchor date mirrors it.
    anchor_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    units: Mapped[str] = mapped_column(String, default="metric")  # metric | imperial
    # Whether the morning brief and check-in go out by text too (Sendblue).
    sms_briefs: Mapped[bool] = mapped_column(Boolean, default=True)
    # Local hour the daily plan is written and the brief texted.
    brief_hour: Mapped[int] = mapped_column(Integer, default=7)
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class Entitlement(Base):
    """What lets a personal account past the paywall, and where it came from.

    One row per grant: the trial every account starts on, then each Apple
    subscription (keyed by its original transaction id, so a renewal updates
    the row rather than adding one), and a complimentary grant an operator
    writes by hand. The account's status is the best of its live rows.
    """

    __tablename__ = "entitlements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    source: Mapped[str] = mapped_column(String)  # trial | apple | comp
    product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    original_transaction_id: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True
    )
    transaction_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Sandbox | Production | Xcode, as the signed transaction says.
    environment: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active | expired | revoked
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    # True when the transaction's signature chained to Apple's root. A lenient
    # deployment (no App Store Connect yet) records the grant with False.
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class PersonalCredential(Base):
    """The login: an email and a password hash, one per personal account.

    Hashing is scrypt from the standard library (a per-account salt, the
    parameters recorded in the hash string so they can be raised later).
    Eight failed attempts lock the account for fifteen minutes; the counter
    lives here rather than in memory because Lambda instances share nothing.
    """

    __tablename__ = "personal_credentials"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Consent(Base):
    """What the person agreed to, when, and the exact words they saw.

    One row per acceptance. The text is stored by hash and archived in full
    to the personal bucket (app/personal/archive.py) so a later reader can
    see precisely what version 2026-09-26.1 said, whatever the code says now.
    """

    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    kind: Mapped[str] = mapped_column(String, default="beta")   # beta
    version: Mapped[str] = mapped_column(String)
    text_sha256: Mapped[str] = mapped_column(String)
    # {"data_storage": true, "ai_processing": true, "research_use": true, "beta_ack": true}
    scopes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # The name they typed as a signature.
    signature: Mapped[str | None] = mapped_column(String, nullable=True)
    device_name: Mapped[str | None] = mapped_column(String, nullable=True)
    app_version: Mapped[str | None] = mapped_column(String, nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # Where the full record landed in object storage, once archived.
    archived_key: Mapped[str | None] = mapped_column(String, nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PersonalLog(Base):
    """One subjective reading a day: energy, soreness, mood, sleep quality,
    the RPE of yesterday's session, a free note. Written from the personal
    check-in and the coach; read by the personal metrics beside the
    wearable stream, which cannot measure any of these."""

    __tablename__ = "personal_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    # energy | soreness | mood | sleep_quality | rpe | session_minutes | note
    key: Mapped[str] = mapped_column(String)
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="checkin")  # checkin | coach | app
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
