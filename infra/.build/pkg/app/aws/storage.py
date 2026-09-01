"""S3-backed persistence for the demo SQLite database on AWS Lambda.

A Lambda instance gets an ephemeral ``/tmp`` that dies with the execution
environment, so the durable copy of ``recovery.db`` lives in S3 and every
instance hydrates from it. Two access patterns, deliberately different:

* **Mutating requests** (anything but GET/HEAD/OPTIONS) take a distributed
  lock — an S3 object created with ``If-None-Match: *``, which S3 makes atomic
  — re-hydrate under it, run, then write back. Writes are therefore fully
  serialized across concurrent instances: no lost updates on the data a
  provider actually authored (assigned tasks, escalations, RTM time,
  approved documents).

* **Read requests** never take the lock. They can still dirty the database,
  because the engine recomputes assessments and the LLM layer fills insight
  caches lazily on GET paths — the input hash includes today's date, so the
  first read of each day rewrites every assessment. Those rows are *derived*
  and regenerable, so they go back with a conditional ``If-Match: <etag>`` and
  are simply dropped when another instance won the race.

The whole module is inert when ``S3_BUCKET`` is unset, which is how the app
keeps running unchanged on a laptop.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from pathlib import Path

from app.aws.config import aws_settings

logger = logging.getLogger(__name__)

# Botocore raises these for a failed conditional write. 412 is the documented
# response for a violated If-Match/If-None-Match; 409 shows up when two writers
# collide on the same key at the same instant.
_CONFLICT_CODES = {"PreconditionFailed", "ConditionalRequestConflict", "412", "409"}

_lock = threading.Lock()
_state: dict = {
    "etag": None,  # ETag the local file was hydrated from
    "checked_at": 0.0,  # monotonic clock of the last S3 freshness check
    "dirty": False,  # a session committed since the last successful upload
}

_client = None


def enabled() -> bool:
    return aws_settings.enabled


def client():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            config=Config(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=3,
                read_timeout=10,
            ),
        )
    return _client


def _is_conflict(error) -> bool:
    code = str(error.response.get("Error", {}).get("Code", ""))
    status = str(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", ""))
    return code in _CONFLICT_CODES or status in _CONFLICT_CODES


def _is_missing(error) -> bool:
    code = str(error.response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}


# --------------------------------------------------------------------------
# dirty tracking
# --------------------------------------------------------------------------


def mark_dirty() -> None:
    with _lock:
        _state["dirty"] = True


def is_dirty() -> bool:
    with _lock:
        return bool(_state["dirty"])


def install_change_tracking() -> None:
    """Flag the database dirty whenever any session commits.

    Hooking the sessionmaker rather than the HTTP verb is what lets a GET that
    quietly refreshed an assessment still get written back.
    """
    from sqlalchemy import event

    from app.database import SessionLocal

    if getattr(install_change_tracking, "_installed", False):
        return
    event.listen(SessionLocal, "after_commit", lambda _session: mark_dirty())
    install_change_tracking._installed = True  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# hydrate
# --------------------------------------------------------------------------


def _dispose_engine() -> None:
    """Drop pooled connections before the file underneath them is replaced.

    Without this, SQLAlchemy would keep serving queries from a file handle
    pointing at the unlinked old inode — reads would silently return the
    pre-download data forever.
    """
    from app.database import engine

    engine.dispose()


def hydrate(force: bool = False) -> bool:
    """Make the local file match S3. Returns True if it downloaded.

    ``force`` skips the freshness TTL — used under the write lock, where a
    stale read would turn into a lost update.
    """
    if not enabled():
        return False

    path = aws_settings.local_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.monotonic()

    with _lock:
        local_etag = _state["etag"]
        fresh_enough = (
            not force
            and path.exists()
            and local_etag is not None
            and now - _state["checked_at"] < aws_settings.freshness_ttl_seconds
        )
    if fresh_enough:
        return False

    try:
        head = client().head_object(Bucket=aws_settings.s3_bucket, Key=aws_settings.s3_db_key)
    except Exception as e:  # noqa: BLE001 — a missing object is a valid state
        if hasattr(e, "response") and _is_missing(e):
            logger.warning(
                "s3://%s/%s does not exist yet — run the seed action to create it",
                aws_settings.s3_bucket,
                aws_settings.s3_db_key,
            )
            with _lock:
                _state["checked_at"] = now
            return False
        raise

    remote_etag = head["ETag"]
    with _lock:
        _state["checked_at"] = now
        if path.exists() and _state["etag"] == remote_etag:
            return False

    # Download beside the target and rename: a half-written database must never
    # be visible to a query, and os.replace is atomic within a filesystem.
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".hydrate-")
    os.close(fd)
    try:
        client().download_file(aws_settings.s3_bucket, aws_settings.s3_db_key, tmp_name)
        _dispose_engine()
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise

    with _lock:
        _state["etag"] = remote_etag
        _state["dirty"] = False
    logger.info("Hydrated %s from s3 (etag %s)", path, remote_etag)
    return True


# --------------------------------------------------------------------------
# persist
# --------------------------------------------------------------------------


def persist(conditional: bool = True) -> bool:
    """Upload the local database. Returns True when S3 accepted the write.

    ``conditional=True`` guards the write with the ETag we hydrated from, so a
    read path that only touched regenerable caches loses gracefully instead of
    clobbering someone else's committed work. Call with ``conditional=False``
    only while holding the write lock.
    """
    if not enabled():
        return False

    path = aws_settings.local_db_path
    if not path.exists():
        return False

    extra: dict = {}
    if conditional:
        with _lock:
            etag = _state["etag"]
        # No known ETag means we believe the object does not exist; If-None-Match
        # makes that belief safe to act on.
        extra = {"IfMatch": etag} if etag else {"IfNoneMatch": "*"}

    with path.open("rb") as fh:
        body = fh.read()

    try:
        response = client().put_object(
            Bucket=aws_settings.s3_bucket,
            Key=aws_settings.s3_db_key,
            Body=body,
            ContentType="application/vnd.sqlite3",
            **extra,
        )
    except Exception as e:  # noqa: BLE001
        if conditional and hasattr(e, "response") and _is_conflict(e):
            # Another instance wrote first. Everything a read path produces is
            # derived from the observation set and will be recomputed, so drop
            # our copy and re-read theirs on the next request.
            logger.info("Conditional upload lost a race — discarding derived writes")
            with _lock:
                _state["etag"] = None
                _state["checked_at"] = 0.0
                _state["dirty"] = False
            return False
        raise

    with _lock:
        _state["etag"] = response.get("ETag")
        _state["dirty"] = False
    return True


# --------------------------------------------------------------------------
# distributed write lock
# --------------------------------------------------------------------------


class LockUnavailable(RuntimeError):
    pass


def acquire_lock() -> None:
    """Serialize mutating requests across Lambda instances.

    ``If-None-Match: *`` makes S3 object creation a compare-and-swap, which is
    all a mutex needs. A holder that dies mid-request leaves the object behind,
    so every lock carries its own expiry and a later writer may break it.
    """
    if not enabled():
        return

    deadline = time.monotonic() + aws_settings.lock_acquire_timeout_seconds
    delay = 0.05
    while True:
        expires_at = time.time() + aws_settings.lock_ttl_seconds
        try:
            client().put_object(
                Bucket=aws_settings.s3_bucket,
                Key=aws_settings.s3_lock_key,
                Body=str(expires_at).encode(),
                IfNoneMatch="*",
            )
            return
        except Exception as e:  # noqa: BLE001
            if not (hasattr(e, "response") and _is_conflict(e)):
                raise
        _break_lock_if_expired()
        if time.monotonic() >= deadline:
            raise LockUnavailable("Timed out waiting for the database write lock")
        time.sleep(delay)
        delay = min(delay * 2, 0.5)


def _break_lock_if_expired() -> None:
    try:
        obj = client().get_object(Bucket=aws_settings.s3_bucket, Key=aws_settings.s3_lock_key)
        expires_at = float(obj["Body"].read().decode() or 0)
    except Exception as e:  # noqa: BLE001
        if hasattr(e, "response") and _is_missing(e):
            return  # already released; the next create will win
        return  # unreadable lock body — let the acquire loop time out instead
    if time.time() < expires_at:
        return
    logger.warning("Breaking an expired database write lock (held past %.0f)", expires_at)
    try:
        client().delete_object(Bucket=aws_settings.s3_bucket, Key=aws_settings.s3_lock_key)
    except Exception:  # noqa: BLE001 — a concurrent breaker deleting it first is fine
        logger.debug("Lock delete raced with another writer", exc_info=True)


def release_lock() -> None:
    if not enabled():
        return
    try:
        client().delete_object(Bucket=aws_settings.s3_bucket, Key=aws_settings.s3_lock_key)
    except Exception:  # noqa: BLE001 — the TTL is the backstop
        logger.warning("Failed to release the database write lock", exc_info=True)


class write_lock:  # noqa: N801 — used as a context manager, reads better lowercase
    """``with write_lock():`` — hold the lock across a whole mutating request."""

    def __enter__(self) -> "write_lock":
        acquire_lock()
        return self

    def __exit__(self, *exc_info) -> None:
        release_lock()


# --------------------------------------------------------------------------
# cold start
# --------------------------------------------------------------------------


def bootstrap() -> None:
    """Called once per execution environment, before the first request."""
    if not enabled():
        return
    install_change_tracking()
    hydrate(force=True)
