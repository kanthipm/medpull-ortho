"""Console credentials: the tokens that bind a console session to an org.

One row per token ever minted. The token itself is never stored, only its
SHA-256, so a copy of the database cannot be turned into a sign-in. ``kind``
says what the holder sees: ``all`` is staff (everything, like the global
``CONSOLE_ACCESS_TOKEN``), ``hospital`` one clinic's charts, ``sports_org``
one program's team boards, ``team`` one board. Revocation is a timestamp
rather than a delete, so a revoked token stays on record: who had what, and
until when. Minting and resolving live in ``app/console_credentials.py``.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConsoleCredential(Base):
    __tablename__ = "console_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String)  # all | hospital | sports_org | team
    # The hospital id, sports org id or team id the credential is bound to;
    # NULL for ``all``.
    org_id: Mapped[str | None] = mapped_column(String, nullable=True)
    label: Mapped[str] = mapped_column(String)  # "HIRT console"
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
