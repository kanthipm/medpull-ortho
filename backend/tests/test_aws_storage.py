"""S3-backed SQLite persistence.

Exercised against a fake S3 that implements the two conditional-write
semantics the design leans on — ``If-None-Match: *`` as an atomic create and
``If-Match: <etag>`` as a compare-and-swap. Those are the only S3 behaviours
that matter here, and faking them keeps the suite offline and instant.
"""

import time
from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.aws import storage
from app.aws.config import aws_settings
from app.config import settings


class FakeS3:
    """In-memory stand-in for the handful of S3 calls storage.py makes."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.etags: dict[str, str] = {}
        self._counter = 0
        self.put_calls = 0

    def _next_etag(self) -> str:
        self._counter += 1
        return f'"etag-{self._counter}"'

    @staticmethod
    def _error(code: str, status: int, op: str) -> ClientError:
        return ClientError(
            {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}}, op
        )

    def head_object(self, Bucket, Key):  # noqa: N803 — boto3 casing
        if Key not in self.objects:
            raise self._error("404", 404, "HeadObject")
        return {"ETag": self.etags[Key], "ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise self._error("NoSuchKey", 404, "GetObject")
        import io

        return {"Body": io.BytesIO(self.objects[Key]), "ETag": self.etags[Key]}

    def put_object(self, Bucket, Key, Body, IfMatch=None, IfNoneMatch=None, **kwargs):  # noqa: N803
        self.put_calls += 1
        if IfNoneMatch == "*" and Key in self.objects:
            raise self._error("PreconditionFailed", 412, "PutObject")
        if IfMatch is not None and self.etags.get(Key) != IfMatch:
            raise self._error("PreconditionFailed", 412, "PutObject")
        self.objects[Key] = Body if isinstance(Body, bytes) else Body.encode()
        self.etags[Key] = self._next_etag()
        return {"ETag": self.etags[Key]}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objects.pop(Key, None)
        self.etags.pop(Key, None)
        return {}

    def download_file(self, Bucket, Key, filename):  # noqa: N803
        if Key not in self.objects:
            raise self._error("404", 404, "HeadObject")
        Path(filename).write_bytes(self.objects[Key])


@pytest.fixture()
def s3(tmp_path, monkeypatch):
    """A configured, isolated storage module backed by FakeS3."""
    fake = FakeS3()
    db_path = tmp_path / "recovery.db"

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(aws_settings, "s3_bucket", "test-bucket")
    monkeypatch.setattr(storage, "_client", fake)
    monkeypatch.setattr(storage, "client", lambda: fake)
    monkeypatch.setattr(storage, "_dispose_engine", lambda: None)
    monkeypatch.setattr(
        storage, "_state", {"etag": None, "checked_at": 0.0, "dirty": False}
    )
    fake.db_path = db_path
    return fake


def test_disabled_without_bucket(tmp_path, monkeypatch):
    monkeypatch.setattr(aws_settings, "s3_bucket", "")
    assert storage.enabled() is False
    # Every entrypoint must be inert, so a laptop run never touches AWS.
    assert storage.hydrate() is False
    assert storage.persist() is False
    storage.acquire_lock()
    storage.release_lock()


def test_local_db_path_rejects_non_sqlite(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql://host/db")
    with pytest.raises(RuntimeError, match="only supports SQLite"):
        _ = aws_settings.local_db_path


# --------------------------------------------------------------------------
# hydrate
# --------------------------------------------------------------------------


def test_hydrate_downloads_when_local_is_missing(s3):
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"remote-v1")

    assert storage.hydrate() is True
    assert s3.db_path.read_bytes() == b"remote-v1"


def test_hydrate_missing_remote_object_is_not_fatal(s3):
    # A freshly created bucket, before the seed action has ever run.
    assert storage.hydrate() is False
    assert not s3.db_path.exists()


def test_hydrate_skips_within_freshness_ttl(s3):
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")
    storage.hydrate()

    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v2")
    assert storage.hydrate() is False  # TTL still covers us
    assert s3.db_path.read_bytes() == b"v1"

    # force is what a mutating request uses: never build on a stale base.
    assert storage.hydrate(force=True) is True
    assert s3.db_path.read_bytes() == b"v2"


def test_hydrate_after_ttl_expiry_picks_up_a_new_version(s3, monkeypatch):
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")
    storage.hydrate()
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v2")

    monkeypatch.setattr(aws_settings, "freshness_ttl_seconds", 0.0)
    assert storage.hydrate() is True
    assert s3.db_path.read_bytes() == b"v2"


def test_hydrate_is_a_noop_when_the_etag_is_unchanged(s3, monkeypatch):
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")
    storage.hydrate()
    monkeypatch.setattr(aws_settings, "freshness_ttl_seconds", 0.0)

    assert storage.hydrate(force=True) is False  # same etag => no download


def test_hydrate_clears_the_dirty_flag(s3):
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")
    storage.mark_dirty()
    storage.hydrate(force=True)
    assert storage.is_dirty() is False


# --------------------------------------------------------------------------
# persist
# --------------------------------------------------------------------------


def test_persist_creates_the_object_when_it_does_not_exist(s3):
    s3.db_path.write_bytes(b"local-v1")
    assert storage.persist(conditional=True) is True
    assert s3.objects[aws_settings.s3_db_key] == b"local-v1"
    assert storage.is_dirty() is False


def test_persist_conditional_round_trip(s3):
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")
    storage.hydrate()

    s3.db_path.write_bytes(b"v2")
    assert storage.persist(conditional=True) is True
    assert s3.objects[aws_settings.s3_db_key] == b"v2"


def test_persist_conditional_loses_a_race_without_clobbering(s3):
    """A read path that only refreshed derived caches must never overwrite a
    mutation another instance committed in the meantime."""
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")
    storage.hydrate()

    # Another Lambda instance commits a real mutation.
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"someone-elses-write")

    s3.db_path.write_bytes(b"my-derived-cache-write")
    storage.mark_dirty()
    assert storage.persist(conditional=True) is False
    assert s3.objects[aws_settings.s3_db_key] == b"someone-elses-write"
    # State is reset so the next request re-reads the winner instead of
    # retrying a write it can never win.
    assert storage.is_dirty() is False
    assert storage.hydrate(force=True) is True
    assert s3.db_path.read_bytes() == b"someone-elses-write"


def test_persist_unconditional_overwrites(s3):
    """What a mutating request does while holding the lock."""
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")
    storage.hydrate()
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v2")

    s3.db_path.write_bytes(b"authoritative")
    assert storage.persist(conditional=False) is True
    assert s3.objects[aws_settings.s3_db_key] == b"authoritative"


def test_persist_without_a_local_file_is_a_noop(s3):
    assert storage.persist() is False
    assert aws_settings.s3_db_key not in s3.objects


def test_persist_reraises_non_conflict_errors(s3, monkeypatch):
    s3.db_path.write_bytes(b"x")

    def boom(**kwargs):
        raise FakeS3._error("AccessDenied", 403, "PutObject")

    monkeypatch.setattr(s3, "put_object", boom)
    with pytest.raises(ClientError):
        storage.persist(conditional=True)


# --------------------------------------------------------------------------
# distributed write lock
# --------------------------------------------------------------------------


def test_lock_is_exclusive(s3, monkeypatch):
    monkeypatch.setattr(aws_settings, "lock_acquire_timeout_seconds", 0.2)
    storage.acquire_lock()
    with pytest.raises(storage.LockUnavailable):
        storage.acquire_lock()  # a second instance must not get in


def test_lock_is_reacquirable_after_release(s3):
    storage.acquire_lock()
    storage.release_lock()
    storage.acquire_lock()  # must not raise
    storage.release_lock()
    assert aws_settings.s3_lock_key not in s3.objects


def test_expired_lock_is_broken(s3, monkeypatch):
    """A Lambda that dies mid-request leaves its lock behind; the TTL is what
    stops that from wedging every future write."""
    monkeypatch.setattr(aws_settings, "lock_acquire_timeout_seconds", 1.0)
    s3.put_object("test-bucket", aws_settings.s3_lock_key, str(time.time() - 1).encode())

    storage.acquire_lock()
    assert aws_settings.s3_lock_key in s3.objects


def test_expired_lock_is_not_taken_from_the_writer_that_broke_it_first(s3, monkeypatch):
    """Reading the lock and replacing it are two calls. If another writer breaks
    the expired lock and takes it in between, this one must back off — clearing
    whatever is there at that point hands the database to two writers at once."""
    monkeypatch.setattr(aws_settings, "lock_acquire_timeout_seconds", 0.2)
    s3.put_object("test-bucket", aws_settings.s3_lock_key, str(time.time() - 1).encode())
    original_get = s3.get_object

    def racing_get(Bucket, Key):  # noqa: N803 — boto3 casing
        stale = original_get(Bucket=Bucket, Key=Key)
        if Key == aws_settings.s3_lock_key:
            # The other writer wins the break and starts its own request, while
            # we are still holding the expired object it replaced.
            s3.delete_object(Bucket=Bucket, Key=Key)
            s3.put_object(
                Bucket=Bucket, Key=Key, Body=str(time.time() + 60).encode(), IfNoneMatch="*"
            )
        return stale

    monkeypatch.setattr(s3, "get_object", racing_get)

    with pytest.raises(storage.LockUnavailable):
        storage.acquire_lock()
    # The live lock is still the other writer's, not a replacement of ours.
    assert float(s3.objects[aws_settings.s3_lock_key]) > time.time()


def test_unexpired_lock_is_not_broken(s3, monkeypatch):
    monkeypatch.setattr(aws_settings, "lock_acquire_timeout_seconds", 0.2)
    s3.put_object("test-bucket", aws_settings.s3_lock_key, str(time.time() + 60).encode())

    with pytest.raises(storage.LockUnavailable):
        storage.acquire_lock()


def test_write_lock_context_manager_releases_on_error(s3):
    with pytest.raises(ValueError):
        with storage.write_lock():
            assert aws_settings.s3_lock_key in s3.objects
            raise ValueError("handler blew up")
    assert aws_settings.s3_lock_key not in s3.objects


# --------------------------------------------------------------------------
# middleware
# --------------------------------------------------------------------------


def _commit(content: bytes) -> None:
    aws_settings.local_db_path.write_bytes(content)
    storage.mark_dirty()


def _app_with_middleware():
    from app.aws.middleware import S3SqliteMiddleware

    app = FastAPI()
    app.add_middleware(S3SqliteMiddleware)

    @app.get("/read")
    def read() -> dict:
        return {"ok": True}

    # The handlers below mutate the database file themselves, the way a real
    # commit does — writing it from the test body instead would just get
    # overwritten by the hydrate the middleware runs first, which is the point.
    @app.get("/read-that-writes")
    def read_that_writes() -> dict:
        _commit(b"v1-plus-warmed-caches")  # a lazily recomputed assessment
        return {"ok": True}

    @app.post("/write")
    def write() -> dict:
        assert aws_settings.s3_lock_key in storage.client().objects, "handler ran unlocked"
        _commit(b"v2-with-a-new-task")
        return {"ok": True}

    @app.post("/write-that-fails")
    def write_that_fails() -> dict:
        _commit(b"partial-work")
        raise RuntimeError("committed, then blew up")

    @app.post("/write-with-interloper")
    def write_with_interloper() -> dict:
        # Simulates a read path on another instance landing its derived
        # write-back between this request's locked hydrate and its upload —
        # GETs never take the lock, so this interleaving is legal.
        storage.client().put_object(
            Bucket="test-bucket",
            Key=aws_settings.s3_db_key,
            Body=b"interloper-derived-write",
        )
        _commit(b"the-provider-mutation")
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_middleware_read_does_not_lock_or_upload(s3):
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")
    before = s3.put_calls

    assert _app_with_middleware().get("/read").status_code == 200
    assert s3.put_calls == before  # a clean read writes nothing back
    assert aws_settings.s3_lock_key not in s3.objects


def test_middleware_read_persists_derived_writes(s3):
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")
    storage.hydrate()

    assert _app_with_middleware().get("/read-that-writes").status_code == 200
    assert s3.objects[aws_settings.s3_db_key] == b"v1-plus-warmed-caches"


def test_middleware_write_holds_the_lock_and_uploads(s3):
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")

    assert _app_with_middleware().post("/write").status_code == 200
    assert s3.objects[aws_settings.s3_db_key] == b"v2-with-a-new-task"
    assert aws_settings.s3_lock_key not in s3.objects  # released


def test_middleware_releases_the_lock_when_a_handler_raises(s3):
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")

    response = _app_with_middleware().post("/write-that-fails")
    assert response.status_code == 500
    assert aws_settings.s3_lock_key not in s3.objects
    # Work committed before the exception is still durable.
    assert s3.objects[aws_settings.s3_db_key] == b"partial-work"


def test_middleware_returns_503_when_the_lock_is_held(s3, monkeypatch):
    monkeypatch.setattr(aws_settings, "lock_acquire_timeout_seconds", 0.2)
    s3.put_object("test-bucket", aws_settings.s3_lock_key, str(time.time() + 60).encode())

    response = _app_with_middleware().post("/write")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "2"


def test_middleware_is_bypassed_entirely_when_disabled(monkeypatch):
    monkeypatch.setattr(aws_settings, "s3_bucket", "")
    assert _app_with_middleware().get("/read").status_code == 200


def test_middleware_read_write_back_must_lose_to_a_newer_mutation(s3):
    """Pins conditional=True on the read path. A derived write-back computed
    from a stale base must never clobber a mutation another instance committed
    in the meantime — flipping the flag to an unconditional upload is silent
    loss of provider-authored data, and this test is what catches it."""
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")
    storage.hydrate()
    client = _app_with_middleware()
    # Another instance commits a provider mutation after our hydrate.
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"provider-mutation")

    assert client.get("/read-that-writes").status_code == 200
    assert s3.objects[aws_settings.s3_db_key] == b"provider-mutation"


def test_middleware_write_upload_must_beat_an_interleaved_derived_write(s3):
    """Pins conditional=False on the mutation path. The locked upload must win
    over a read path's write-back that slipped in mid-request — a conditional
    upload here would 412, be silently discarded, and hand the client a 200
    for a mutation that never became durable."""
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")

    assert _app_with_middleware().post("/write-with-interloper").status_code == 200
    assert s3.objects[aws_settings.s3_db_key] == b"the-provider-mutation"
    assert aws_settings.s3_lock_key not in s3.objects  # released


def test_middleware_read_serves_the_response_despite_a_failed_write_back(s3, monkeypatch):
    """Pins the try/except around the read path's persist: a transient S3
    error while writing back regenerable rows must never turn an
    already-computed 200 into a 500."""
    s3.put_object("test-bucket", aws_settings.s3_db_key, b"v1")
    storage.hydrate()
    client = _app_with_middleware()

    def boom(**kwargs):
        raise FakeS3._error("AccessDenied", 403, "PutObject")

    monkeypatch.setattr(s3, "put_object", boom)
    assert client.get("/read-that-writes").status_code == 200


# --------------------------------------------------------------------------
# change tracking
# --------------------------------------------------------------------------


def test_session_commit_marks_the_database_dirty(s3, db):
    """A GET that lazily recomputes an assessment has to be detectable, and
    the HTTP verb cannot tell us that — the sessionmaker can.

    Uninstalled again on the way out: the listener stays on this sessionmaker,
    which is the suite-wide one every other test commits through, so one left
    behind here marks the database dirty for the rest of the run — which is
    exactly the leak that used to make tests/test_lambda_handler.py pass for
    the wrong reason.
    """
    storage.install_change_tracking()
    try:
        assert storage.is_dirty() is False
        db.commit()
        assert storage.is_dirty() is True
    finally:
        storage.uninstall_change_tracking()


def test_change_tracking_install_is_idempotent_and_reversible(s3, db):
    """Two installs must not stack two listeners, or one uninstall would leave
    the database silently dirtying itself forever."""
    storage.install_change_tracking()
    storage.install_change_tracking()
    storage.uninstall_change_tracking()

    db.commit()
    assert storage.is_dirty() is False
