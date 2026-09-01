"""SPA static serving: nothing outside frontend/dist may ever leave the process.

The catch-all takes the path param verbatim — uvicorn normalizes neither dot
segments nor percent-encoding — so these tests hand the app the same string the
wire does. httpx (which TestClient wraps) collapses a literal `../` before the
request leaves the client, so that one case drives the ASGI app directly.
"""

import asyncio
from collections.abc import Iterator
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.config import BACKEND_DIR, PROJECT_DIR

DIST = PROJECT_DIR / "frontend" / "dist"
# Outside the bundle, always present in a checkout, and unmistakable in a body.
CANARY = BACKEND_DIR / "pyproject.toml"
CANARY_MARK = b"recovery-copilot-backend"

pytestmark = pytest.mark.skipif(
    not DIST.exists(), reason="frontend/dist is unbuilt, so the SPA routes are unregistered"
)


def _raw_get(client: TestClient, path: str) -> tuple[int, bytes]:
    """GET `path` with no client-side rewriting, the way uvicorn delivers it."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    status = 0
    body = bytearray()

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            body.extend(message.get("body", b""))

    asyncio.run(client.app(scope, receive, send))
    return status, bytes(body)


def _is_index(body: bytes) -> bool:
    return b'<div id="root">' in body


@pytest.fixture()
def escape_symlink() -> Iterator[str]:
    """A symlink inside the bundle aimed at a file outside it, removed after."""
    link = DIST / "test-escape-link.toml"
    try:
        link.symlink_to(CANARY)
    except OSError as exc:  # noqa: BLE001 — a read-only bundle just skips this case
        pytest.skip(f"cannot create a symlink in the bundle: {exc}")
    try:
        yield link.name
    finally:
        link.unlink()


def test_literal_dot_segments_cannot_escape(client):
    """The verbatim `../../` form uvicorn passes through must not read the tree."""
    rel = CANARY.relative_to(PROJECT_DIR)
    status, body = _raw_get(client, f"/../../{rel}")
    assert status == 200
    assert CANARY_MARK not in body
    assert _is_index(body)


def test_percent_encoded_dot_segments_cannot_escape(client):
    """`%2e%2e%2f` survives every client that normalizes the literal form."""
    rel = str(CANARY.relative_to(PROJECT_DIR)).replace("/", "%2f")
    r = client.get(f"/%2e%2e%2f%2e%2e%2f{rel}")
    assert r.status_code == 200
    assert CANARY_MARK not in r.content
    assert _is_index(r.content)


def test_absolute_path_param_cannot_escape(client):
    """An absolute param would otherwise swallow the join with the bundle root."""
    r = client.get("/" + quote(str(CANARY), safe=""))
    assert r.status_code == 200
    assert CANARY_MARK not in r.content
    assert _is_index(r.content)


def test_symlink_out_of_the_bundle_cannot_escape(client, escape_symlink):
    """Containment is checked after resolution, so an in-tree name is not enough."""
    r = client.get(f"/{escape_symlink}")
    assert r.status_code == 200
    assert CANARY_MARK not in r.content
    assert _is_index(r.content)


def test_hashed_asset_still_serves(client):
    """/assets is the SPA's own mount and must keep serving bundle bytes."""
    asset = next(p for p in sorted((DIST / "assets").iterdir()) if p.is_file())
    r = client.get(f"/assets/{asset.name}")
    assert r.status_code == 200
    assert r.content == asset.read_bytes()


def test_bundled_root_file_still_serves(client):
    """Files the build drops beside index.html are served by the catch-all."""
    extra = next(
        (p for p in sorted(DIST.iterdir()) if p.is_file() and p.name != "index.html"), None
    )
    if extra is None:
        pytest.skip("the bundle has no non-index file at its root")
    r = client.get(f"/{extra.name}")
    assert r.status_code == 200
    assert r.content == extra.read_bytes()


def test_deep_link_falls_through_to_index(client):
    """Client routing depends on unknown in-tree paths returning the shell."""
    r = client.get("/patients/marcus")
    assert r.status_code == 200
    assert _is_index(r.content)
    assert r.headers["cache-control"] == "no-cache"


def test_root_serves_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert _is_index(r.content)
    assert r.headers["cache-control"] == "no-cache"


def test_an_unknown_api_path_404s_instead_of_serving_the_shell(client):
    """/api is the server's namespace, and the SPA catch-all sits behind it.

    A mistyped or removed API route that answers 200 text/html is a genuinely
    confusing failure: the caller gets a JSON parse error somewhere far from
    the cause. It is also exactly how a router that failed to import presents
    from the outside — the reason app/api/__init__.py no longer swallows
    ImportError — so the namespace has to 404 rather than fall through.
    """
    response = client.get("/api/practice-overview")  # the real one is /api/practice/overview
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")

    # The real route still answers, and a client deep link still gets the shell.
    assert client.get("/api/practice/overview").status_code == 200
    spa = client.get("/patients/marcus")
    assert spa.status_code == 200
    assert "text/html" in spa.headers["content-type"]


@pytest.mark.parametrize(
    "path",
    ["//api/practice-overview", "//api", "/./api/practice-overview",
     "/nope/../api/practice-overview", "///api///practice-overview",
     "/../api/practice-overview"],
)
def test_unnormalized_api_paths_404_instead_of_serving_the_shell(client, path):
    """The guard has to read the path the way the filesystem does.

    The catch-all param is percent-decoded but NOT dot-segment-normalized, so
    every form here addresses /api while starting with none of the strings a
    raw `startswith("api/")` test recognizes — and each one used to fall
    through to index.html, handing a caller 200 text/html where it asked for
    JSON. A doubled slash is not exotic: any client that joins a base URL
    ending in "/" to a path starting with "/" produces one.
    """
    status, body = _raw_get(client, path)
    assert status == 404, f"{path} fell through to the SPA"
    assert not _is_index(body)
    assert b'"detail"' in body
