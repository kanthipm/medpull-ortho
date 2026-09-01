from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.aws import storage
from app.aws.config import aws_settings
from app.aws.middleware import S3SqliteMiddleware
from app.config import PROJECT_DIR
from app.database import ensure_schema

app = FastAPI(title="MedPull Recovery Copilot", version="1.0.0")

# Additive only — creates tables the models declare and this database predates.
# Every request path goes through get_db(), which does the same check; this one
# covers the startup warmer, which opens its own session.
ensure_schema()


@app.on_event("startup")
def warm_caches() -> None:
    """Generate any missing assessments + narratives in the background so the
    first page load doesn't wait on a cold LLM."""
    import logging
    import threading

    if not aws_settings.warm_caches_on_startup:
        # Off on Lambda: it would re-run per cold start and race other
        # instances. The deploy seeds and warms the database once instead.
        logging.getLogger(__name__).info("Startup cache warming disabled")
        return

    def _warm() -> None:
        try:
            from app.database import SessionLocal
            from app.engine.pipeline import run_all
            from app.llm.insights import get_daily_briefing, get_patient_insight
            from app.models.enums import InsightKind
            from app.models.patient import Patient
            from sqlalchemy import select

            db = SessionLocal()
            try:
                run_all(db)
                for pid in db.scalars(select(Patient.id)).all():
                    for kind in (
                        InsightKind.WORKLIST_REASON,
                        InsightKind.PATIENT_SUMMARY,
                        InsightKind.SUGGESTED_ACTIONS,
                    ):
                        get_patient_insight(db, kind, pid)
                get_daily_briefing(db)
                logging.getLogger(__name__).info("Insight caches warmed")
            finally:
                db.close()
        except Exception:  # noqa: BLE001 — warming must never take the app down
            logging.getLogger(__name__).exception("Cache warming failed")

    threading.Thread(target=_warm, name="insight-warmer", daemon=True).start()

# Dev convenience: the Vite dev server proxies /api, but allow direct calls too.
# On AWS, CloudFront serves the SPA and the API from one origin, so no request
# is ever cross-origin and this middleware never fires.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keeps the SQLite file in /tmp in sync with the durable copy in S3. Inert
# unless S3_BUCKET is set, so a local run is unaffected.
if storage.enabled():
    storage.install_change_tracking()
    app.add_middleware(S3SqliteMiddleware)

app.include_router(api_router)

# Single-process demo mode: serve the built SPA. API routes are registered
# above, so they win; everything else falls back to index.html for client
# routing (deep links like /patients/marcus).
# Resolved once so the containment check below compares like with like even
# when the checkout itself sits behind a symlink.
DIST = (PROJECT_DIR / "frontend" / "dist").resolve()
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    def _segments(full_path: str) -> list[str]:
        """Path segments after dot-segment resolution, the way a filesystem
        (and `.resolve()` below) reads the same string.

        The catch-all param is percent-DECODED but not normalized, so the raw
        string is not a safe thing to prefix-test: `//api/x`, `/./api/x` and
        `/%2e/api/x` all address the API namespace while starting with none of
        the strings a `startswith("api/")` test would recognize. Backslashes
        are folded in because `.resolve()` treats them as ordinary filename
        characters but a client (or a Windows-ish proxy) may not."""
        out: list[str] = []
        for raw in full_path.replace("\\", "/").split("/"):
            if raw in ("", "."):
                continue
            if raw == "..":
                if out:
                    out.pop()
                continue
            out.append(raw)
        return out

    def _bundled_file(full_path: str) -> Path | None:
        """Resolve a catch-all path inside the built SPA, or None if it escapes.

        The path param arrives verbatim: uvicorn normalizes neither dot segments
        nor percent-encoding, and an absolute param would swallow the join with
        the bundle root outright. So containment is re-checked after resolution,
        which settles symlinks pointing out of the tree at the same time."""
        try:
            candidate = (DIST / full_path).resolve()
        except (OSError, ValueError):
            # Unresolvable — a null byte, or a symlink loop. Never a bundle file.
            return None
        if not candidate.is_relative_to(DIST) or not candidate.is_file():
            return None
        return candidate

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> Response:
        # The API namespace is server-owned: an unmatched path under it is a
        # mistake, not a deep link, and answering index.html would hand the
        # caller 200 text/html where it expected JSON. That is precisely how a
        # router that failed to import used to look from the outside — a
        # worklist page silently rendering the shell instead of erroring — so
        # this namespace 404s rather than falling through.
        if _segments(full_path)[:1] == ["api"]:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = _bundled_file(full_path) if full_path else None
        if candidate is not None:
            return FileResponse(candidate)
        # index.html must always revalidate: it points at content-hashed
        # bundles, and a cached copy would keep serving a stale build.
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
