"""Request-scoped glue between FastAPI and the S3-backed database.

Read requests get a cheap freshness check; mutating requests get a distributed
lock held across the whole handler. See app/aws/storage.py for why the two
paths differ.
"""

import functools
import logging

from anyio.to_thread import run_sync
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.aws import storage

logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class S3SqliteMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not storage.enabled():
            return await call_next(request)

        if request.method in SAFE_METHODS:
            return await self._read(request, call_next)
        return await self._write(request, call_next)

    async def _read(self, request: Request, call_next) -> Response:
        await run_sync(storage.hydrate)
        response = await call_next(request)
        if storage.is_dirty():
            # Derived rows only (recomputed assessments, warmed insight caches).
            # Conditional, so losing the race costs nothing but a recompute.
            try:
                await run_sync(functools.partial(storage.persist, conditional=True))
            except Exception:  # noqa: BLE001 — never fail a served response over a cache
                logger.warning("Failed to persist derived writes", exc_info=True)
        return response

    async def _write(self, request: Request, call_next) -> Response:
        try:
            await run_sync(storage.acquire_lock)
        except storage.LockUnavailable:
            logger.warning("Write lock unavailable for %s %s", request.method, request.url.path)
            return JSONResponse(
                {"detail": "Database is busy, please retry."},
                status_code=503,
                headers={"Retry-After": "2"},
            )
        try:
            # Re-read under the lock: another instance may have committed since
            # this one last looked, and a stale base would silently drop it.
            await run_sync(functools.partial(storage.hydrate, force=True))
            try:
                return await call_next(request)
            finally:
                # Runs on the error path too: a handler that committed and then
                # raised still has durable work sitting in /tmp.
                if storage.is_dirty():
                    await run_sync(functools.partial(storage.persist, conditional=False))
        finally:
            await run_sync(storage.release_lock)
