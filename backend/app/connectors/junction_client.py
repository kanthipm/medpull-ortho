"""Synchronous HTTP client for the Junction (fka Vital) API.

Deliberately thin: it knows the hosts, the auth header, the handful of
endpoints the connector uses, and how to back off. Everything that decides
what a payload *means* lives in ``connectors/junction.py`` so it can be tested
against recorded shapes without a network.

Contract (verified against ``junction-api-sdk`` 1.4.0, the SDK Junction
generates from its own API definition):

* Hosts are per environment and region. The legacy ``*.tryvital.io`` names are
  still served, but new integrations use ``*.junction.com``.
* Auth is the ``x-vital-api-key`` header. Keys are per team and per
  environment, so a production key against the sandbox host is a 401 —
  never a silent cross-environment write.
* Rate limiting is a soft per-endpoint quota. 429 and 503 both carry
  ``Retry-After`` and both mean back off; the documented client strategy is
  exponential backoff with jitter. Webhook deliveries do not count.

Every call is bounded, twice over. The API function behind CloudFront has a
hard 30 s ceiling, and on AWS every mutating request holds the S3 write lock
for its whole duration under a 25 s TTL (``app/aws/config.py``): a handler
that outlives the TTL lets a concurrent writer break the lock and one of the
two then silently discards the other's rows. So a retry that honours a 60 s
``Retry-After`` would only convert a rate limit into lost data: waits are
capped at MAX_RETRY_WAIT_S, each attempt's socket timeout is clipped to what
is left of the call's deadline, no attempt starts once the deadline is
spent, and the defaults leave room for the ingest and recompute that follow.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

API_KEY_HEADER = "x-vital-api-key"
# Per-attempt socket timeout and per-call wall-clock deadline. Both sit well
# under the 25 s write-lock TTL so the request that made the call can still
# ingest, recompute and persist before the lock can be broken.
DEFAULT_TIMEOUT_S = 8.0
DEFAULT_DEADLINE_S = 15.0
MAX_ATTEMPTS = 3
MAX_RETRY_WAIT_S = 4.0
# Below this much remaining budget an attempt cannot complete; give up instead.
MIN_ATTEMPT_S = 0.5
# Pagination guard for grouped timeseries: a page is at most a few thousand
# samples, and twenty of them is more than any resource the connector ingests
# produces over the ingestible window.
MAX_TIMESERIES_PAGES = 20

HOSTS: dict[tuple[str, str], str] = {
    ("sandbox", "us"): "https://api.sandbox.us.junction.com",
    ("sandbox", "eu"): "https://api.sandbox.eu.junction.com",
    ("production", "us"): "https://api.us.junction.com",
    ("production", "eu"): "https://api.eu.junction.com",
}

SUMMARY_RESOURCES = ("activity", "sleep", "body", "workouts")


class JunctionError(RuntimeError):
    """A call the API answered with an error, or could not answer at all."""

    def __init__(self, message: str, *, status: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


class JunctionNotConfigured(JunctionError):
    """No API key: the connector is scaffolding until one is set."""


def base_url_for(environment: str, region: str) -> str:
    env = (environment or "sandbox").strip().lower()
    reg = (region or "us").strip().lower()
    try:
        return HOSTS[(env, reg)]
    except KeyError:
        raise JunctionError(
            f"Unknown Junction environment/region {environment!r}/{region!r}; "
            f"expected one of {sorted(HOSTS)}"
        ) from None


def configured() -> bool:
    return bool(settings.junction_api_key.strip())


def resolved_base_url() -> str:
    override = settings.junction_base_url.strip()
    if override:
        return override.rstrip("/")
    return base_url_for(settings.junction_environment, settings.junction_region)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    header = response.headers.get("retry-after")
    if not header:
        return None
    try:
        return max(0.0, float(header))
    except ValueError:
        return None  # an HTTP-date form; fall back to the backoff schedule


class JunctionClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not api_key:
            raise JunctionNotConfigured("JUNCTION_API_KEY is not set")
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._timeout = timeout
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={API_KEY_HEADER: api_key, "accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, **kwargs: Any) -> JunctionClient:
        if not configured():
            raise JunctionNotConfigured("JUNCTION_API_KEY is not set")
        return cls(settings.junction_api_key.strip(), resolved_base_url(), **kwargs)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> JunctionClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- transport -----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        deadline_s: float = DEFAULT_DEADLINE_S,
        not_found_ok: bool = False,
    ) -> Any:
        """One logical call: retries on 429/503/5xx/transport failure with a
        capped, jittered backoff, and never past `deadline_s` of wall clock —
        the first attempt included, whose socket timeout is clipped to what
        is left of the budget."""
        limit = time.monotonic() + deadline_s
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        last_error: JunctionError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            remaining = limit - time.monotonic()
            if remaining < MIN_ATTEMPT_S:
                if last_error is None:
                    last_error = JunctionError(
                        f"Junction {method} {path} not attempted: the call's "
                        f"{deadline_s:.1f}s deadline is already spent"
                    )
                break
            try:
                response = self._http.request(
                    method, path, params=clean_params, json=json,
                    timeout=min(self._timeout, remaining),
                )
            except httpx.HTTPError as e:
                last_error = JunctionError(f"Junction {method} {path} failed: {e}")
                logger.warning("Junction transport error on %s %s: %s", method, path, e)
                response = None
            if response is not None:
                if response.status_code < 400:
                    return self._body(response)
                if response.status_code == 404 and not_found_ok:
                    return None
                detail = self._detail(response)
                last_error = JunctionError(
                    f"Junction {method} {path} answered {response.status_code}: {detail}",
                    status=response.status_code,
                    detail=detail,
                )
                if response.status_code not in (429, 503) and response.status_code < 500:
                    raise last_error  # a client error will not improve on retry
            if attempt == MAX_ATTEMPTS:
                break
            wait = self._backoff(attempt, response)
            if time.monotonic() + wait + MIN_ATTEMPT_S >= limit:
                break
            self._sleep(wait)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _backoff(attempt: int, response: httpx.Response | None) -> float:
        hinted = _retry_after_seconds(response) if response is not None else None
        if hinted is None:
            hinted = 2 ** (attempt - 1)
        return min(MAX_RETRY_WAIT_S, hinted) + random.uniform(0.0, 0.25)

    @staticmethod
    def _body(response: httpx.Response) -> Any:
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise JunctionError(
                f"Junction answered {response.status_code} with a non-JSON body",
                status=response.status_code,
            ) from None

    @staticmethod
    def _detail(response: httpx.Response) -> Any:
        try:
            body = response.json()
        except ValueError:
            return response.text[:300]
        if isinstance(body, dict):
            return body.get("detail", body)
        return body

    # -- users ---------------------------------------------------------------

    def create_user(
        self,
        client_user_id: str,
        *,
        fallback_time_zone: str | None = None,
        ingestion_start: date | None = None,
        ingestion_end: date | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"client_user_id": client_user_id}
        if fallback_time_zone:
            body["fallback_time_zone"] = fallback_time_zone
        if ingestion_start is not None:
            body["ingestion_start"] = ingestion_start.isoformat()
        if ingestion_end is not None:
            body["ingestion_end"] = ingestion_end.isoformat()
        return self._request("POST", "/v2/user", json=body)

    def resolve_user(self, client_user_id: str) -> dict[str, Any] | None:
        return self._request("GET", f"/v2/user/resolve/{client_user_id}", not_found_ok=True)

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        return self._request("GET", f"/v2/user/{user_id}", not_found_ok=True)

    def delete_user(self, user_id: str) -> dict[str, Any] | None:
        return self._request("DELETE", f"/v2/user/{user_id}", not_found_ok=True)

    def refresh_user(
        self, user_id: str, *, deadline_s: float = DEFAULT_DEADLINE_S
    ) -> dict[str, Any] | None:
        """Ask Junction to re-pull from every connected provider now."""
        return self._request(
            "POST", f"/v2/user/refresh/{user_id}", not_found_ok=True, deadline_s=deadline_s
        )

    def connected_providers(self, user_id: str) -> list[dict[str, Any]]:
        body = self._request("GET", f"/v2/user/providers/{user_id}", not_found_ok=True)
        if not body:
            return []
        providers = body.get("providers", []) if isinstance(body, dict) else body
        return [p for p in providers if isinstance(p, dict)]

    def deregister_provider(self, user_id: str, provider_slug: str) -> dict[str, Any] | None:
        return self._request(
            "DELETE", f"/v2/user/{user_id}/{provider_slug}", not_found_ok=True
        )

    # -- link ----------------------------------------------------------------

    def create_link_token(
        self,
        user_id: str,
        *,
        redirect_url: str | None = None,
        provider: str | None = None,
        filter_on_providers: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"user_id": user_id}
        if redirect_url:
            body["redirect_url"] = redirect_url
        if provider:
            body["provider"] = provider
        if filter_on_providers:
            body["filter_on_providers"] = list(filter_on_providers)
        return self._request("POST", "/v2/link/token", json=body)

    # -- data ----------------------------------------------------------------

    def summaries(
        self,
        resource: str,
        user_id: str,
        start: date,
        end: date,
        *,
        provider: str | None = None,
        deadline_s: float = DEFAULT_DEADLINE_S,
    ) -> list[dict[str, Any]]:
        """Daily summaries: ``activity``, ``sleep``, ``body`` or ``workouts``.

        The response wraps the list under the resource's own name
        (``{"sleep": [...]}``)."""
        if resource not in SUMMARY_RESOURCES:
            raise ValueError(f"{resource!r} is not a summary resource")
        body = self._request(
            "GET",
            f"/v2/summary/{resource}/{user_id}",
            params={
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "provider": provider,
            },
            deadline_s=deadline_s,
        )
        if not isinstance(body, dict):
            return []
        rows = body.get(resource) or []
        return [r for r in rows if isinstance(r, dict)]

    def timeseries_grouped(
        self,
        resource: str,
        user_id: str,
        start: date,
        end: date,
        *,
        provider: str | None = None,
        deadline_s: float = DEFAULT_DEADLINE_S,
    ) -> list[dict[str, Any]]:
        """Every ``{"source": ..., "data": [...]}`` block for a timeseries
        resource over the range, following ``next_cursor`` across pages."""
        blocks: list[dict[str, Any]] = []
        cursor: str | None = None
        limit = time.monotonic() + deadline_s
        for _ in range(MAX_TIMESERIES_PAGES):
            remaining = limit - time.monotonic()
            if remaining <= 0:
                logger.warning(
                    "Junction %s timeseries for %s hit the deadline; returning %d blocks",
                    resource, user_id, len(blocks),
                )
                break
            body = self._request(
                "GET",
                f"/v2/timeseries/{user_id}/{resource}/grouped",
                params={
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "provider": provider,
                    "cursor": cursor,
                },
                deadline_s=remaining,
            )
            if not isinstance(body, dict):
                break
            groups = body.get("groups") or {}
            for group_blocks in groups.values():
                for block in group_blocks or []:
                    if isinstance(block, dict):
                        blocks.append(block)
            cursor = body.get("next_cursor") or body.get("next")
            if not cursor:
                break
        return blocks

    # Deliberately absent: GET /v2/team/svix/url. It answers with a
    # pre-authenticated Svix App Portal link — the message log of every
    # delivered payload plus endpoint and secret control — and this console
    # has no authentication to gate such a thing behind. Operators reach the
    # portal from app.junction.com instead.
