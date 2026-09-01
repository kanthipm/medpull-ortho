from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


_schema_checked = False


def ensure_schema() -> None:
    """Create any table the models declare and the file does not have.

    There are no migrations: the database is built once by `seed --reset` and
    lives on from there (on AWS, as one SQLite file in S3). Adding a table to
    the models therefore reaches an existing deployment only if something
    creates it — otherwise every request that touches it fails with "no such
    table" until someone rebuilds the demo roster from scratch.

    `create_all(checkfirst=True)` is additive and idempotent: it issues DDL
    only for tables that are absent and never alters one that exists. The flag
    keeps it to a single round trip per process, and storage hydration clears
    the flag when it swaps the file underneath us.
    """
    global _schema_checked
    if _schema_checked:
        return
    import app.models  # noqa: F401 — register every table on Base.metadata

    Base.metadata.create_all(engine, checkfirst=True)
    _schema_checked = True


def schema_needs_recheck() -> None:
    """Called when the database file is replaced (S3 hydrate): the new file is
    a different database and may predate a table the models declare."""
    global _schema_checked
    _schema_checked = False


def get_db() -> Generator[Session, None, None]:
    ensure_schema()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
