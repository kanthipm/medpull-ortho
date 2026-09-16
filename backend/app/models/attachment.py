"""A file on the patient <-> care team thread: a photo of an incision, a
sheet of exercises, a letter from the clinic.

Only the record lives here; the bytes are in object storage
(``app/storage/blobs.py``), because the database is one SQLite file every
Lambda instance downloads. A row carries what a reader needs in order to
decide whether to show a thumbnail or a filename, and enough provenance to
answer "who put this here, from where" a year later.

A row exists before its bytes do. The upload is two steps — the API says
where to put the file, the client puts it, the API confirms it arrived — so
an unconfirmed row is the normal state for a few seconds and a leaked one
(the client vanished mid-upload) is swept later.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Where a file came from. Not the same question as who sent the message:
# an inbound MMS arrives on "sms" from the patient, and a clinician's PDF
# arrives on "console".
SOURCES = ("app", "console", "sms")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    # The line it hangs off. Null until the message is written, which is the
    # order the app uses: upload first, then send with the attachment ids.
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True, index=True
    )
    # patient | care_team | copilot, matching Message.sender.
    uploaded_by: Mapped[str] = mapped_column(String, default="patient")
    uploaded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("care_team_members.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(String, default="app")
    # Validated against blobs.ALLOWED_TYPES before anything is stored: it
    # decides the extension and the Content-Type a browser will act on.
    content_type: Mapped[str] = mapped_column(String)
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    # Content hash of what actually arrived. Two identical uploads are still
    # two rows — they were two acts — but this is what proves a file is the
    # one that was stored.
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    # Opaque key in object storage. Unique so a confirm cannot be replayed
    # onto another row, and never derived from anything a reader knows.
    storage_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    # What the person called it, sanitised. Shown for a document; an image
    # needs no name.
    filename: Mapped[str | None] = mapped_column(String, nullable=True)
    # Where the bytes came from when they were not uploaded to us: an inbound
    # picture message arrives as a link on the provider's CDN, credential-free
    # and public, so it is copied here and this is kept only so a fetch that
    # timed out can be retried. Cleared once the bytes are ours.
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # Set when the bytes have been seen in storage. Nothing is shown to
    # anybody before this.
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # A withdrawn file. The object is deleted for real; the row stays so the
    # thread can say something was removed rather than silently losing a line.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    message = relationship("Message")

    @property
    def is_image(self) -> bool:
        return self.content_type.startswith("image/")

    @property
    def available(self) -> bool:
        return self.confirmed_at is not None and self.deleted_at is None
