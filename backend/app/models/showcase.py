"""What the showcase remembers about itself: a handful of named facts.

One row per fact, keyed by name. Today there is one, ``filled_on``: the day
``app.seed.showcase.fill_showcase`` last anchored the demo orgs to, which
``/api/health`` reports so a console or a phone can tell a current demo
from one that has aged. A key/value table rather than a column somewhere
because nothing else in the schema is about the deployment as a whole.
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ShowcaseState(Base):
    __tablename__ = "showcase_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
