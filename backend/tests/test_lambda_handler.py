"""The Lambda entrypoint, driven with the event shapes AWS actually sends.

app.lambda_handler does real work at import time — the writable-path guard, the
SSM fetch, the cold-start hydrate — so these tests import it fresh under a
patched environment rather than relying on module state from another test.
"""

import importlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from app.aws import storage
from app.aws.config import aws_settings
from app.config import settings
from tests.test_aws_storage import FakeS3


# app.config and app.aws.* are deliberately NOT rebuilt: the tests monkeypatch
# attributes on the `settings`, `aws_settings` and `storage` module objects, and
# a rebuild would hand the handler fresh instances that never saw those patches.
# Everything else under app.* is rebuilt as one unit — see _import_handler.
def _rebuildable(name: str) -> bool:
    return (
        name.startswith("app.")
        and name != "app.config"
        and name != "app.aws"
        and not name.startswith("app.aws.")
    )


def _detach(name: str) -> None:
    """Forget a module completely: sys.modules *and* the parent package.

    Popping sys.modules alone is not enough. Importing app.seed.seed also binds
    `seed` as an attribute of the app.seed package object, and that attribute
    survives the pop — so anything reaching the module by attribute walk rather
    than by import keeps finding the discarded one. pytest's
    monkeypatch.setattr("app.seed.seed.run_seed", ...) resolves exactly that
    way, which had it patching a dead module while the handler imported a live
    one and ran the *real* seed against the developer's database.
    """
    sys.modules.pop(name, None)
    parent_name, _, leaf = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if parent is not None:
        try:
            delattr(parent, leaf)
        except AttributeError:
            pass


def _attach(name: str, module) -> None:
    parent_name, _, leaf = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if parent is not None:
        setattr(parent, leaf, module)


@pytest.fixture(autouse=True)
def _restore_module_graph():
    """Put sys.modules back exactly as it was after every test in this file.

    _import_handler rebuilds app.* on purpose, and those rebuilt modules are
    poison for every later test file: the fresh `Base` has no models registered
    on it, and the fresh sessionmaker is bound to this file's throwaway
    database. Leaving them behind used to strand app.seed.seed on an empty
    metadata and take twenty tests in tests/test_api.py down with it, depending
    on file order. Restoring by identity — not by re-importing — keeps the
    class objects the rest of the suite already holds references to.
    """
    snapshot = {k: v for k, v in sys.modules.items() if k == "app" or k.startswith("app.")}
    try:
        yield
    finally:
        for name in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
            if name not in snapshot:
                _detach(name)
        sys.modules.update(snapshot)
        for name, module in snapshot.items():
            _attach(name, module)
        # The rebuilt sessionmaker this file hooked is gone with the restore,
        # but drop any listener sitting on the restored one too: a leaked
        # after_commit hook marks the database dirty for the rest of the run.
        storage.uninstall_change_tracking()


def _import_handler(monkeypatch, tmp_path, *, db_dir=None, secret=""):
    """Import app.lambda_handler with AWS wiring pointed at a fake S3.

    The whole app.* graph is rebuilt, not just app.lambda_handler: on Lambda
    this module tree is imported exactly once, in this order, so a faithful
    cold start has to start from nothing. Rebuilding only app.database and
    app.main — as this helper used to — is worse than rebuilding nothing,
    because app.api.* keep the *previous* get_db and therefore the previous
    engine. The handler under test then served every request off a sessionmaker
    that storage.install_change_tracking had never hooked, so a POST committed
    without ever marking the database dirty and the upload was silently skipped.
    """
    fake = FakeS3()
    # tmp_path is per-test and already lives under /tmp, so it satisfies the
    # handler's writable-path guard while keeping runs isolated. A shared fixed
    # filename left a database behind that the next run would hydrate from.
    db_path = f"{db_dir}/recovery-copilot-handler-test.db" if db_dir else f"{tmp_path}/recovery-copilot-handler-test.db"

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(aws_settings, "s3_bucket", "test-bucket")
    monkeypatch.setattr(aws_settings, "origin_verify_secret", secret)
    monkeypatch.setattr(storage, "client", lambda: fake)
    monkeypatch.setattr(storage, "_client", fake)
    monkeypatch.setattr(storage, "_state", {"etag": None, "checked_at": 0.0, "dirty": False})

    # Deepest first, so each module's parent package is still around to be
    # cleaned when its child is detached.
    for mod in sorted(filter(_rebuildable, list(sys.modules)), key=lambda n: -n.count(".")):
        _detach(mod)
    # Import the model package explicitly so the freshly built Base carries the
    # full schema. app.main pulls in most of it through the routers, but
    # _seeded_db_bytes below builds a database off Patient.metadata and needs
    # every table, not just the ones some router happened to reach.
    importlib.import_module("app.models")
    module = importlib.import_module("app.lambda_handler")
    return module, fake


def _url_event(method="GET", path="/api/health", headers=None, body=None):
    """A Lambda Function URL payload (format 2.0)."""
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "abc.lambda-url.us-east-1.on.aws", **(headers or {})},
        "requestContext": {
            "accountId": "anonymous",
            "apiId": "abc",
            "domainName": "abc.lambda-url.us-east-1.on.aws",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "203.0.113.1",
                "userAgent": "pytest",
            },
            "requestId": "req-1",
            "stage": "$default",
            "time": "01/Jan/2026:00:00:00 +0000",
            "timeEpoch": 1767225600000,
        },
        "body": body,
        "isBase64Encoded": False,
    }


def test_refuses_a_database_path_outside_tmp(monkeypatch, tmp_path):
    """/var/task is read-only, and app.config's default points inside it — this
    has to fail loudly at import, not mysteriously at the first query.

    /var/task is used verbatim rather than a tmp_path: pytest's tmp_path lives
    under /tmp, so it would satisfy the guard and prove nothing.
    """
    with pytest.raises(RuntimeError, match="must live under /tmp"):
        _import_handler(monkeypatch, tmp_path, db_dir="/var/task")


def test_serves_an_http_event(monkeypatch, tmp_path):
    handler, fake = _import_handler(monkeypatch, tmp_path)
    # The cold-start hydrate found no object; seed the bucket the way the deploy
    # does, then serve a request off it.
    seeded = _seeded_db_bytes()
    fake.objects[aws_settings.s3_db_key] = seeded
    fake.etags[aws_settings.s3_db_key] = '"seeded"'

    response = handler.handler(_url_event(), None)

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert payload["status"] == "ok"
    assert payload["db_ok"] is True
    # No key configured in the test env, so the deterministic renderer is active.
    assert payload["llm_provider"] == "fallback"
    # And the request really was served off the hydrated copy: the read-path
    # hydrate downloaded the seeded bytes into the path the engine is bound to.
    assert aws_settings.local_db_path.read_bytes() == seeded
    conn = sqlite3.connect(aws_settings.local_db_path)
    try:
        assert conn.execute("SELECT v FROM hydrate_marker").fetchone()[0] == "from-s3"
    finally:
        conn.close()


def test_app_builds_with_the_s3_middleware_wired(monkeypatch, tmp_path):
    """The whole persistence design hangs on app.main installing the middleware
    when storage is enabled. A refactor that drops or reorders that guard must
    not ship behind a green suite."""
    handler, _ = _import_handler(monkeypatch, tmp_path)
    from app.aws.middleware import S3SqliteMiddleware

    assert any(m.cls is S3SqliteMiddleware for m in handler.app.user_middleware)


def test_mutating_request_locks_and_uploads_through_the_real_app(monkeypatch, tmp_path):
    """A POST through the real Mangum+FastAPI stack must take the S3 write lock,
    release it, and land its commit durably in the bucket — the property the
    whole deployment exists to provide."""
    handler, fake = _import_handler(monkeypatch, tmp_path)
    seeded = _seeded_db_bytes()
    fake.objects[aws_settings.s3_db_key] = seeded
    fake.etags[aws_settings.s3_db_key] = '"seeded"'

    lock_taken = {"during_request": False}
    orig_put = fake.put_object

    def spying_put(Bucket, Key, Body, **kwargs):  # noqa: N803 — boto3 casing
        if Key == aws_settings.s3_lock_key:
            lock_taken["during_request"] = True
        return orig_put(Bucket=Bucket, Key=Key, Body=Body, **kwargs)

    monkeypatch.setattr(fake, "put_object", spying_put)

    response = handler.handler(
        _url_event(method="POST", path="/api/notifications/read-all"), None
    )

    assert response["statusCode"] == 200
    assert lock_taken["during_request"], "mutating request never took the write lock"
    assert aws_settings.s3_lock_key not in fake.objects  # and released it
    # The commit was uploaded: the object was rewritten under the lock.
    assert fake.etags[aws_settings.s3_db_key] != '"seeded"'


def test_origin_verification_rejects_a_direct_caller(monkeypatch, tmp_path):
    handler, _ = _import_handler(monkeypatch, tmp_path, secret="s3cret")

    response = handler.handler(_url_event(), None)
    assert response["statusCode"] == 403

    response = handler.handler(_url_event(headers={"x-origin-verify": "guess"}), None)
    assert response["statusCode"] == 403


def test_origin_verification_accepts_cloudfront(monkeypatch, tmp_path):
    handler, fake = _import_handler(monkeypatch, tmp_path, secret="s3cret")
    fake.objects[aws_settings.s3_db_key] = _seeded_db_bytes()
    fake.etags[aws_settings.s3_db_key] = '"seeded"'

    response = handler.handler(_url_event(headers={"X-Origin-Verify": "s3cret"}), None)
    assert response["statusCode"] == 200


def test_seed_action_runs_under_the_lock_and_uploads(monkeypatch, tmp_path):
    handler, fake = _import_handler(monkeypatch, tmp_path)

    called = {}

    def fake_run_seed(reset=False):
        called["reset"] = reset
        assert aws_settings.s3_lock_key in fake.objects, "seed ran without the write lock"
        aws_settings.local_db_path.write_bytes(b"freshly-seeded")
        return {"patients": 10}

    monkeypatch.setattr("app.seed.seed.run_seed", fake_run_seed)

    result = handler.handler({"action": "seed"}, None)

    assert result == {"ok": True, "uploaded": True, "counts": {"patients": 10}}
    assert called["reset"] is True
    assert fake.objects[aws_settings.s3_db_key] == b"freshly-seeded"
    assert aws_settings.s3_lock_key not in fake.objects  # released


def test_unknown_admin_action_is_reported(monkeypatch, tmp_path):
    handler, _ = _import_handler(monkeypatch, tmp_path)
    result = handler.handler({"action": "drop-everything"}, None)
    assert result["ok"] is False
    assert "drop-everything" in result["error"]


def _seeded_db_bytes() -> bytes:
    """Bytes of a real SQLite file with the app's schema plus a marker row that
    lets a test prove the hydrated copy is what actually got served."""
    import tempfile

    from sqlalchemy import create_engine

    # The metadata hangs off the models, which registered on the Base that was
    # live at conftest import — reaching it through a model class keeps this
    # correct even after app.database has been rebuilt by _import_handler.
    from app.models.patient import Patient

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "seed.db"
        engine = create_engine(f"sqlite:///{path}")
        Patient.metadata.create_all(engine)
        engine.dispose()
        conn = sqlite3.connect(path)
        try:
            conn.execute("CREATE TABLE hydrate_marker (v TEXT)")
            conn.execute("INSERT INTO hydrate_marker VALUES ('from-s3')")
            conn.commit()
        finally:
            conn.close()
        return path.read_bytes()


def test_the_rebuilt_app_shares_one_database_binding(monkeypatch, tmp_path):
    """Every module the handler serves through must resolve to the *same*
    app.database.

    This is the invariant behind the upload assertion above, and it fails in a
    much more confusing way: rebuilding app.database while app.api.* keep the
    previous get_db gives an app that reads one file, a change-tracking hook
    installed on a sessionmaker nobody uses, and — because a fresh Base has no
    models registered on it — a schema that exists nowhere. Asserting it
    directly turns a twenty-test cascade in another file into one clear
    failure here.
    """
    handler, _ = _import_handler(monkeypatch, tmp_path)

    import app.database
    from app.api import patients, worklist
    from app.models.patient import Patient

    assert patients.get_db is app.database.get_db
    assert worklist.get_db is app.database.get_db
    assert str(app.database.engine.url).endswith("recovery-copilot-handler-test.db")
    # The handler's app was built from these same modules, not a cached one.
    assert handler.app is __import__("app.main", fromlist=["app"]).app
    # A fresh Base with no models on it is the other half of the old failure.
    assert Patient.metadata is app.database.Base.metadata
    assert "observations" in app.database.Base.metadata.tables


def test_detaching_a_module_also_clears_the_parent_package(monkeypatch, tmp_path):
    """Popping sys.modules is only half of forgetting a module.

    `import app.seed.seed` also binds `seed` as an attribute of the app.seed
    package object, and that binding survives the pop. Anything that reaches a
    module by attribute walk instead of by import then keeps finding the
    discarded copy — pytest's own monkeypatch.setattr("app.seed.seed.run_seed")
    resolves exactly that way, so it patched a dead module while the handler
    imported a live one and ran the *real* seed. That is a test helper firing a
    full re-seed at whatever database happens to be configured, which is worth
    a guard of its own.
    """
    import app as app_pkg

    importlib.import_module("app.seed.seed")
    assert getattr(app_pkg, "seed", None) is not None

    _detach("app.seed.seed")
    _detach("app.seed")
    assert not hasattr(app_pkg, "seed"), (
        "the parent package still points at the discarded module"
    )

    # And a fresh import resolves to the same object by both routes.
    fresh = importlib.import_module("app.seed.seed")
    assert app_pkg.seed.seed is fresh
    assert sys.modules["app.seed.seed"] is fresh
