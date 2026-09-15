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
    _add_missing_columns()
    _schema_checked = True


def _sql_literal(value: object) -> str | None:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def _add_missing_columns() -> None:
    """Add columns the models declare and an existing table lacks.

    ``create_all`` never alters a table, so before this a new column on an
    existing model reached a deployment only through a full reseed — which on
    AWS means throwing away every real patient's observations. The patient
    app added columns to ``patients`` and ``adherence_tasks``; this makes
    those (and any later ones) an ``ALTER TABLE ... ADD COLUMN`` instead.

    Additive only, and only for columns that can be added to a populated
    table: nullable ones, or NOT NULL ones with a scalar default the DDL can
    carry (SQLite refuses a NOT NULL column without one). Anything else is
    logged and left for a reseed, never guessed at. Python-side defaults
    (``default=datetime.now``) are per-row and cannot be expressed in DDL, so
    such a column must be nullable to be added here.
    """
    import logging

    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    added: list[str] = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing:
                continue
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                ddl = (
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" '
                    f"{column.type.compile(engine.dialect)}"
                )
                default = column.default
                literal = (
                    _sql_literal(default.arg)
                    if default is not None and getattr(default, "is_scalar", False)
                    else None
                )
                if literal is not None:
                    ddl += f" DEFAULT {literal}"
                elif not column.nullable:
                    logging.getLogger(__name__).error(
                        "Cannot add NOT NULL column %s.%s without a scalar default; "
                        "reseed to pick it up",
                        table.name, column.name,
                    )
                    continue
                conn.execute(text(ddl))
                added.append(f"{table.name}.{column.name}")
    if added:
        logging.getLogger(__name__).info("Schema: added column(s) %s", ", ".join(added))


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
