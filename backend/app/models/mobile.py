"""Patient-app state: sessions, phone verification, and the two-way message
thread between a patient and their care team.

Nothing here is reachable from the provider console's unauthenticated routes
except the message thread, which the console reads and replies to. The
session token is the patient app's credential; only its hash is stored, like
the check-in invite token.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PatientSession(Base):
    __tablename__ = "patient_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    device_name: Mapped[str | None] = mapped_column(String, nullable=True)
    app_version: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    patient = relationship("Patient")


class PhoneVerification(Base):
    """A one-time code texted during onboarding. Only hashes are stored."""

    __tablename__ = "phone_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    phone: Mapped[str] = mapped_column(String)  # E.164
    code_hash: Mapped[str] = mapped_column(String)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Message(Base):
    """One line of the patient <-> care team thread.

    ``sender`` is who wrote it: ``patient``, ``care_team`` (a person in the
    console) or ``copilot`` (an automated reply). ``channel`` is where it was
    written: ``app``, ``sms``, ``voice`` or ``console``.
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    sender: Mapped[str] = mapped_column(String)
    sender_id: Mapped[str | None] = mapped_column(
        ForeignKey("care_team_members.id"), nullable=True
    )
    text: Mapped[str] = mapped_column(String)
    channel: Mapped[str] = mapped_column(String, default="app")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    read_by_patient_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_by_care_team_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # sent | delivered | failed | None (nothing was sent out-of-band for this line)
    # Who stands behind this message: "care_team" when a clinician wrote,
    # approved or triggered it, "ai" when the copilot produced it on its own.
    # NULL on rows written before the distinction existed, read as "ai" —
    # untagged is the default everywhere, and only a clinician's name is a
    # claim worth making. ``sender`` says which side of the thread a message
    # is on; this says whether a person authorised what it claims.
    authored_by: Mapped[str | None] = mapped_column(String, nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String, nullable=True)
    # Why a send failed, in the provider's own words ("This phone number is
    # not defined."). Without it a clinician saw "not delivered" and had no
    # way to tell a landline from a broken Sendblue account.
    delivery_detail: Mapped[str | None] = mapped_column(String, nullable=True)
    external_handle: Mapped[str | None] = mapped_column(String, nullable=True)
    # An action the app offers on this line, drawn as a button under the
    # bubble: "open_task" opens ``action_task_id`` in the app. NULL on every
    # line that is only words, which is nearly all of them.
    #
    # It exists because a text cannot carry a button. A patient who has the
    # app gets no link in their SMS at all (the content is already theirs,
    # behind their session); what they get is this row, and the app turns it
    # into one tap. The texted link is the fallback for somebody who has
    # never enrolled.
    action_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    action_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action_label: Mapped[str | None] = mapped_column(String, nullable=True)

    def action_view(self) -> dict | None:
        """The button a client should draw under this line, or None for a
        line that is only words.

        Lives on the model because both the patient app and the console
        thread render it and the two must not drift, and because everything
        it needs is already loaded — it costs no query.
        """
        if not self.action_kind:
            return None
        return {
            "kind": self.action_kind,
            "task_id": self.action_task_id,
            "label": self.action_label or "Open",
        }
