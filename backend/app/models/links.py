"""Links a text carries into the patient app.

One opaque token per link, at ``https://<host>/a/<token>``. The host's
apple-app-site-association claims ``/a/*`` for the iPhone app, so a tap in
Messages opens the app at the screen the link names; with no app installed
the same URL lands on the web and continues in the browser. Only the token's
hash is stored, like a session's.

A link names a *place* (today's exercises, one exercise, the program, a
task, the thread), never a credential by itself: whether it may also sign
the phone in is decided when it is redeemed (``app/links.py``).
"""

from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# What a link can open. ``ref_id`` is the assignment id for ``exercise``, the
# task id for ``task`` and ``checkin``; the rest carry none.
KINDS = ("today", "exercise", "program", "task", "checkin", "thread", "measure", "progress")


class AppLink(Base):
    __tablename__ = "app_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    kind: Mapped[str] = mapped_column(String, default="today")
    ref_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # The day the link is about (today's plan, a day on the program).
    day: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    # The thread line that carried it, when one did.
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stamped on the first redeem and the latest; a link stays usable until
    # it expires (a text is re-read, and iMessage fetches it for a preview).
    first_opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    open_count: Mapped[int] = mapped_column(Integer, default=0)
