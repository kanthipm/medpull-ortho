"""S3-backed persistence for the demo SQLite database on AWS Lambda.

A Lambda instance gets an ephemeral ``/tmp`` that dies with the execution
environment, so the durable copy of ``recovery.db`` lives in S3 and every
instance hydrates from it. Two access patterns, deliberately different:

* **Mutating requests** (anything but GET/HEAD/OPTIONS) take a distributed
  lock — an S3 object created with ``If-None-Match: *``, which S3 makes atomic
  — re-hydrate under it, run, then write back. Writes are therefore fully
  serialized across concurrent instances: no lost updates on the data a
  provider actually authored (assigned tasks, escalations).

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
import secrets
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
    # The write lock this process believes it holds: the token written into
    # the lock object, and the ETag S3 gave that write. Both are needed to
    # tell "still ours" from "someone broke it and holds it now".
    "lock_token": None,
    "lock_etag": None,
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


def _mark_dirty_on_commit(_session) -> None:
    mark_dirty()


def install_change_tracking() -> None:
    """Flag the database dirty whenever any session commits.

    Hooking the sessionmaker rather than the HTTP verb is what lets a GET that
    quietly refreshed an assessment still get written back.

    The listener is scoped to the sessionmaker it is registered on, not to the
    Session class: a session built by a *different* sessionmaker bound to the
    same engine does not fire it. That is why this asks the registry whether
    the hook is already there rather than latching a flag — a rebuilt
    app.database means a new sessionmaker that genuinely needs hooking, and
    only sessions from that one will report.
    """
    from sqlalchemy import event

    from app.database import SessionLocal

    if event.contains(SessionLocal, "after_commit", _mark_dirty_on_commit):
        return
    event.listen(SessionLocal, "after_commit", _mark_dirty_on_commit)


def uninstall_change_tracking() -> None:
    """Remove the commit hook. The inverse of install_change_tracking, and the
    only way to scope one: the listener outlives the request that installed it,
    so a caller that installs one and walks away keeps flagging every later
    commit made through that sessionmaker."""
    from sqlalchemy import event

    from app.database import SessionLocal

    if not event.contains(SessionLocal, "after_commit", _mark_dirty_on_commit):
        return
    event.remove(SessionLocal, "after_commit", _mark_dirty_on_commit)


# --------------------------------------------------------------------------
# hydrate
# --------------------------------------------------------------------------


def _dispose_engine() -> None:
    """Drop pooled connections before the file underneath them is replaced.

    Without this, SQLAlchemy would keep serving queries from a file handle
    pointing at the unlinked old inode — reads would silently return the
    pre-download data forever.
    """
    from app.database import engine, schema_needs_recheck

    engine.dispose()
    # The file about to land here is a different database, possibly written
    # before a table the models now declare.
    schema_needs_recheck()


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
    elif not holds_lock():
        # An unconditional upload is only safe under the lock. Ours was broken
        # while the handler ran, so the base this file was built on is stale
        # and uploading it would undo whatever the new holder committed.
        logger.error(
            "Refusing an unconditional upload: the write lock was taken over "
            "while this request ran. Discarding local writes."
        )
        with _lock:
            # Force a re-download before anything reads this file again, and
            # make sure a later conditional persist cannot publish these rows.
            _state["etag"] = None
            _state["checked_at"] = 0.0
            _state["dirty"] = False
        raise LockLost("The database write lock was taken over mid-request")

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


class LockLost(RuntimeError):
    """The write lock was broken by another writer while we held it.

    An unconditional upload at that point would overwrite whatever the new
    holder committed — the failure mode is a row that comes back from the
    dead minutes after it was deleted. The caller must discard its work and
    let the client retry instead.
    """


def acquire_lock() -> None:
    """Serialize mutating requests across Lambda instances.

    ``If-None-Match: *`` makes S3 object creation a compare-and-swap, which is
    all a mutex needs. A holder that dies mid-request leaves the object behind,
    so every lock carries its own expiry and a later writer takes it over.
    """
    if not enabled():
        return

    deadline = time.monotonic() + aws_settings.lock_acquire_timeout_seconds
    delay = 0.05
    while True:
        expires_at = time.time() + aws_settings.lock_ttl_seconds
        token = secrets.token_hex(8)
        try:
            response = client().put_object(
                Bucket=aws_settings.s3_bucket,
                Key=aws_settings.s3_lock_key,
                Body=_lock_body(token, expires_at),
                IfNoneMatch="*",
            )
            _hold_lock(token, response.get("ETag"))
            return
        except Exception as e:  # noqa: BLE001
            if not (hasattr(e, "response") and _is_conflict(e)):
                raise
        if _take_over_expired_lock(expires_at, token):
            return
        if time.monotonic() >= deadline:
            raise LockUnavailable("Timed out waiting for the database write lock")
        time.sleep(delay)
        delay = min(delay * 2, 0.5)


def _lock_body(token: str, expires_at: float) -> bytes:
    """The lock object's contents. The expiry stays first and bare so an older
    build, which read the whole body as a float, still parses it."""
    return f"{expires_at}\n{token}".encode()


def _parse_lock(raw: bytes) -> tuple[float, str | None]:
    text = raw.decode(errors="replace")
    expiry, _, token = text.partition("\n")
    try:
        held_until = float(expiry.strip() or 0)
    except ValueError:
        held_until = 0.0
    return held_until, (token.strip() or None)


def _hold_lock(token: str, etag: str | None) -> None:
    with _lock:
        _state["lock_token"] = token
        _state["lock_etag"] = etag


def _forget_lock() -> None:
    with _lock:
        _state["lock_token"] = None
        _state["lock_etag"] = None


def holds_lock() -> bool:
    """Whether the lock object still carries our token.

    The TTL exists so a writer that died cannot wedge the database, which
    means a live-but-slow writer can have its lock broken out from under it.
    Checking before the upload is what stops that writer from overwriting
    the new holder's work.
    """
    if not enabled():
        return True
    with _lock:
        token = _state["lock_token"]
    if token is None:
        return False
    try:
        obj = client().get_object(Bucket=aws_settings.s3_bucket, Key=aws_settings.s3_lock_key)
        _held_until, held_token = _parse_lock(obj["Body"].read())
    except Exception as e:  # noqa: BLE001
        if hasattr(e, "response") and _is_missing(e):
            return False  # released or deleted: not ours any more
        raise
    return held_token == token


def _take_over_expired_lock(expires_at: float, token: str) -> bool:
    """Claim a lock whose holder died. Returns True if this process now holds it.

    Reading the lock and clearing it are two round trips, and another writer
    may break and retake it in between — deleting whatever is there at that
    point drops a lock somebody is actively holding. Overwriting under
    ``If-Match`` folds the break and the acquire into one compare-and-swap
    instead, so a lock that changed since the read is left alone.
    """
    try:
        obj = client().get_object(Bucket=aws_settings.s3_bucket, Key=aws_settings.s3_lock_key)
        held_etag = obj["ETag"]
        held_until, _held_token = _parse_lock(obj["Body"].read())
    except Exception:  # noqa: BLE001
        # Already released, or a body no float can be made of. Either way this
        # is not ours to break: fall back to the plain create on the next pass.
        return False
    if time.time() < held_until:
        return False
    logger.warning("Breaking an expired database write lock (held past %.0f)", held_until)
    try:
        response = client().put_object(
            Bucket=aws_settings.s3_bucket,
            Key=aws_settings.s3_lock_key,
            Body=_lock_body(token, expires_at),
            IfMatch=held_etag,
        )
    except Exception as e:  # noqa: BLE001
        if hasattr(e, "response") and _is_conflict(e):
            # Another writer broke it first and is holding the replacement.
            logger.debug("Lock takeover raced with another writer", exc_info=True)
            return False
        raise
    _hold_lock(token, response.get("ETag"))
    return True


def release_lock() -> None:
    """Drop the lock, but only if it is still ours.

    A writer whose lock was broken used to delete it on the way out, taking
    the new holder's lock with it and letting a third writer in beside them.
    """
    if not enabled():
        return
    try:
        if not holds_lock():
            logger.warning("Not releasing the write lock: another writer holds it now")
            return
        client().delete_object(Bucket=aws_settings.s3_bucket, Key=aws_settings.s3_lock_key)
    except Exception:  # noqa: BLE001 — the TTL is the backstop
        logger.warning("Failed to release the database write lock", exc_info=True)
    finally:
        _forget_lock()


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
