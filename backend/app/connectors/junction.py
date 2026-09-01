"""Junction (fka Vital) aggregator connector — the live wearable path.

One integration in front of Oura, Fitbit/Google Health, Garmin, WHOOP,
Withings, Polar and Dexcom, plus Apple HealthKit and Android Health Connect
through Junction's mobile SDK once a patient app exists. HIPAA-native with a
BAA at the floor price, which is what disqualified Terra.

How the pieces fit:

* **Identity.** One Junction *user* per patient, created from the provider
  console (``authorize``) under an opaque ``client_user_id``. The mapping is
  ``models/connection.py``; every webhook is resolved through it and never
  through anything in the body (``resolve_patient``).
* **Linking.** ``authorize`` returns a hosted Link URL. The clinic hands it to
  the patient (copy, print, read out); the patient signs in to their device's
  cloud account on Junction's page. Junction then emits
  ``provider.connection.created`` and starts a back-fill, announcing each
  resource with ``historical.data.<resource>.created`` — an event with no
  data, which is our cue to pull the range through the API.
* **Data.** ``daily.data.<resource>.created|updated`` deliveries carry one
  summary (activity / sleep / body / workouts) or one grouped timeseries
  block. ``normalize`` maps them onto ``MetricType`` with the semantics the
  engine expects, and ``ingest.py`` upserts by dedupe key so ``.updated``
  restates in place.

Semantics that are easy to get wrong, decided here once:

* Resting heart rate has two definitions in the wild — a daily figure
  (Apple, Fitbit, Garmin, Withings) and a sleep statistic (Oura, WHOOP,
  Polar). Each provider gets exactly one, chosen by ``SLEEP_RHR_PROVIDERS``,
  so a patient's series never alternates between the two.
* Apple HealthKit's only HRV identifier is SDNN. Junction labels the stream
  "rmssd" for every provider, but a label cannot convert a statistic, so
  Apple-sourced HRV lands in ``HRV_SDNN`` (stored and charted, not scored:
  the engine's control chart is RMSSD-only by design).
* Temperature: ``temperature_delta`` / ``body_temperature_delta`` are
  deviations from the device's own baseline and go to ``SKIN_TEMP_DELTA``;
  ``skin_temperature`` / ``body_temperature`` are absolute and go to
  ``SKIN_TEMP``. Never the other way round.
* Intraday totals (steps, calories, distance timeseries) are **not**
  ingested. The daily summary is the row; ``engine/dataload.py`` averages
  every row on a day, so 96 fifteen-minute step buckets beside an 8,000-step
  summary would score the day as 160 steps.
* Naps and in-progress recordings are not the night's sleep and are skipped;
  Junction restates an in-progress session when it completes.
* Out-of-window and physiologically impossible rows are dropped and counted
  rather than refused: refusing makes Junction retry a delivery that will
  never become acceptable.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta, timezone as dt_timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.connectors.base import (
    CanonicalObservation,
    Delivery,
    OAuthResult,
    PatientContext,
    WearableConnector,
)
from app.connectors.ingest import PLAUSIBLE_RANGE, ingestible_window
from app.connectors.junction_client import (
    SUMMARY_RESOURCES,
    JunctionClient,
    JunctionError,
    JunctionNotConfigured,
    configured,
)
from app.models.connection import WearableConnection
from app.models.enums import ConnectionStatus, Granularity
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider as P
from app.models.patient import Device, Patient

logger = logging.getLogger(__name__)

AGGREGATOR = P.JUNCTION

# Junction provider slug -> the brand it is, for the Device row and the
# Integrations page. Anything not listed is recorded under the aggregator.
BRAND_BY_SLUG: dict[str, P] = {
    "apple_health_kit": P.APPLE,
    "fitbit": P.FITBIT,
    "google_health": P.GOOGLE_HEALTH,
    "garmin": P.GARMIN,
    "oura": P.OURA,
    "whoop": P.WHOOP,
    "whoop_v2": P.WHOOP,
    "withings": P.WITHINGS,
    "dexcom": P.DEXCOM,
    "dexcom_v3": P.DEXCOM,
    "polar": P.POLAR,
    "samsung_health": P.SAMSUNG,
    "health_connect": P.HEALTH_CONNECT,
}
# The current slug per brand. Cloud (OAuth) providers connect from the hosted
# Link page; the Apple and Android providers are Junction *mobile SDK*
# sources and need the companion patient app, which does not exist yet.
SLUG_BY_BRAND: dict[P, str] = {
    P.OURA: "oura",
    P.FITBIT: "fitbit",
    P.GOOGLE_HEALTH: "google_health",
    P.GARMIN: "garmin",
    P.WHOOP: "whoop_v2",
    P.WITHINGS: "withings",
    P.POLAR: "polar",
    P.DEXCOM: "dexcom_v3",
    P.APPLE: "apple_health_kit",
    P.HEALTH_CONNECT: "health_connect",
    P.SAMSUNG: "samsung_health",
}
SDK_ONLY_SLUGS = frozenset({"apple_health_kit", "health_connect", "samsung_health"})
LINKABLE_BRANDS = frozenset(
    brand for brand, slug in SLUG_BY_BRAND.items() if slug not in SDK_ONLY_SLUGS
)

# Providers whose resting heart rate is a sleep statistic (Oura's lowest
# nightly HR, WHOOP's recovery RHR) rather than a daily figure.
SLEEP_RHR_PROVIDERS = frozenset(
    {"oura", "whoop", "whoop_v2", "ultrahuman", "eight_sleep", "polar"}
)
# Providers whose HRV is SDNN however the stream is labelled.
SDNN_PROVIDERS = frozenset({"apple_health_kit"})
# Junction's slug for data a person typed into a health app by hand.
MANUAL_PROVIDERS = frozenset({"manual"})

UNITS: dict[M, str] = {
    M.STEPS: "count",
    M.RESTING_HR: "bpm",
    M.HR_SAMPLE: "bpm",
    M.HRV_RMSSD: "ms",
    M.HRV_SDNN: "ms",
    M.SLEEP_DURATION: "h",
    M.SLEEP_STAGES: "h",
    M.ACTIVE_ENERGY: "kcal",
    M.CALORIES: "kcal",
    M.EXERCISE_SESSION: "min",
    M.SPO2: "%",
    M.RESPIRATORY_RATE: "breaths/min",
    M.SKIN_TEMP: "degC",
    M.SKIN_TEMP_DELTA: "degC",
}

# Timeseries resources that are ingested and the metric each lands in. Totals
# (steps, calories_active, distance) are deliberately absent — see the module
# docstring. heartrate is gated by settings.junction_ingest_heart_rate_samples.
TIMESERIES_METRIC: dict[str, M] = {
    "blood_oxygen": M.SPO2,
    "respiratory_rate": M.RESPIRATORY_RATE,
    "hrv": M.HRV_RMSSD,
    "body_temperature_delta": M.SKIN_TEMP_DELTA,
    "body_temperature": M.SKIN_TEMP,
    "heartrate": M.HR_SAMPLE,
}
# Metrics each summary resource can produce, for metric_types filtering.
SUMMARY_METRICS: dict[str, frozenset[M]] = {
    "activity": frozenset({M.STEPS, M.CALORIES, M.ACTIVE_ENERGY, M.RESTING_HR}),
    "sleep": frozenset(
        {
            M.SLEEP_DURATION,
            M.SLEEP_STAGES,
            M.HRV_RMSSD,
            M.HRV_SDNN,
            M.RESPIRATORY_RATE,
            M.SKIN_TEMP_DELTA,
            M.SKIN_TEMP,
            M.RESTING_HR,
        }
    ),
    "workouts": frozenset({M.EXERCISE_SESSION}),
    "body": frozenset(),  # weight / body fat have no MetricType yet
}
PULLABLE_RESOURCES = ("activity", "sleep", "workouts", *TIMESERIES_METRIC)

# A back-fill is pulled inside one HTTP request (a webhook or the console's
# Backfill button) and the API function has a 30 s ceiling, so the pull gets a
# budget and reports what it did not reach rather than timing out silently.
DEFAULT_PULL_BUDGET_S = 20.0


@dataclass
class LinkSession:
    url: str
    expires_at: str | None
    connection: WearableConnection


@dataclass
class PullReport:
    observations: list[CanonicalObservation] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)  # pulled to completion
    skipped: list[str] = field(default_factory=list)  # not reached inside the budget
    dropped: int = 0  # implausible rows discarded at normalize
    start: date | None = None
    end: date | None = None

    @property
    def complete(self) -> bool:
        return not self.skipped


# --- parsing helpers ---------------------------------------------------------


def _split_event(event_type: Any) -> tuple[str, str, str]:
    """'daily.data.sleep.created' -> ('daily', 'sleep', 'created');
    'provider.connection.created' -> ('provider', 'connection', 'created')."""
    if not isinstance(event_type, str) or not event_type:
        raise ValueError("Junction webhook payload must carry an event_type")
    parts = event_type.split(".")
    if len(parts) == 4 and parts[1] == "data":
        return parts[0], parts[2], parts[3]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    raise ValueError(f"Unrecognized Junction event_type {event_type!r}")


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _utc_naive(value: datetime | None) -> datetime | None:
    """Aware -> naive UTC. Provider stamps are compared against what SQLite
    hands back, which is naive, and Python refuses to order the two."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(dt_timezone.utc).replace(tzinfo=None)


def _parse_day(value: Any) -> date | None:
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _local_wall_time(instant: datetime, offset_s: Any, tz_id: str) -> datetime:
    """Naive patient-local wall time for an instant.

    The provider's own offset wins when it is present: it says where the
    device actually was (a patient travelling east of home) where the
    patient's zone can only say where they usually are. Naive instants are
    trusted as already-local, the convention every reader assumes.
    """
    if instant.tzinfo is None:
        return instant
    offset = _number(offset_s)
    if offset is not None:
        shifted = instant.astimezone(dt_timezone.utc) + timedelta(seconds=int(offset))
        return shifted.replace(tzinfo=None)
    try:
        zone = ZoneInfo(tz_id)
    except (KeyError, ValueError):
        zone = ZoneInfo("America/New_York")
    return instant.astimezone(zone).replace(tzinfo=None)


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    return datetime.combine(day, dt_time.min), datetime.combine(day, dt_time(23, 59, 59))


def _source_of(rec: dict[str, Any]) -> dict[str, Any]:
    source = rec.get("source")
    return source if isinstance(source, dict) else {}


def _slug_of(source: dict[str, Any]) -> str:
    slug = source.get("provider") or source.get("slug") or ""
    return slug if isinstance(slug, str) else ""


# --- the connector -----------------------------------------------------------


class JunctionConnector(WearableConnector):
    provider = AGGREGATOR
    drops_out_of_window_rows = True

    def __init__(self, client_factory: Any = None):
        # Injectable for tests: a callable returning a JunctionClient (or a
        # stand-in). The default builds one from settings on every call so a
        # key set after import (the Lambda SSM path) is picked up.
        self._client_factory = client_factory or JunctionClient.from_settings

    # -- configuration ---------------------------------------------------------

    @staticmethod
    def is_configured() -> bool:
        return configured()

    def _client(self) -> JunctionClient:
        return self._client_factory()

    # -- connections -----------------------------------------------------------

    @staticmethod
    def connection_for(db: Session, patient_id: str) -> WearableConnection | None:
        return db.scalar(
            select(WearableConnection).where(
                WearableConnection.aggregator == AGGREGATOR,
                WearableConnection.patient_id == patient_id,
            )
        )

    @staticmethod
    def connection_by_user(db: Session, external_user_id: str) -> WearableConnection | None:
        return db.scalar(
            select(WearableConnection).where(
                WearableConnection.aggregator == AGGREGATOR,
                WearableConnection.external_user_id == external_user_id,
            )
        )

    def active_connection(self, db: Session, patient_id: str) -> WearableConnection:
        """The patient's live connection, or a ValueError / 409-flavoured
        JunctionError explaining exactly why there is not one."""
        conn = self.connection_for(db, patient_id)
        if conn is None or conn.status == ConnectionStatus.DISCONNECTED:
            raise ValueError(f"{patient_id} has no active Junction connection")
        if conn.environment != settings.junction_environment:
            raise JunctionError(
                f"{patient_id}'s Junction account was created in the "
                f"{conn.environment} environment and this deployment is configured "
                f"for {settings.junction_environment}; disconnect and link again",
                status=409,
            )
        return conn

    def resolve_patient(self, db: Session, raw_payload: dict[str, Any]) -> str | None:
        user_id = raw_payload.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("Junction webhook payload must carry a user_id")
        conn = self.connection_by_user(db, user_id)
        if conn is None:
            return None
        claimed = raw_payload.get("client_user_id")
        if isinstance(claimed, str) and claimed and claimed != conn.client_user_id:
            # The two ids are issued together; a pair that disagrees is a
            # delivery for some other account that happens to reuse a user id.
            logger.warning(
                "Junction delivery for user %s carries client_user_id %r, expected %r",
                user_id, claimed, conn.client_user_id,
            )
            return None
        if conn.status == ConnectionStatus.DISCONNECTED:
            return None
        return conn.patient_id

    # -- linking ---------------------------------------------------------------

    def create_link(self, db: Session, patient_id: str) -> LinkSession:
        """Ensure the patient has a Junction user and mint a Link URL for it.

        Idempotent from the console's point of view: a second click reuses the
        same Junction user (resolved by our opaque client_user_id) and mints a
        fresh token, because tokens are one-time and short-lived.
        """
        patient = db.get(Patient, patient_id)
        if patient is None:
            raise ValueError(f"Unknown patient: {patient_id}")
        env = settings.junction_environment
        conn = self.connection_for(db, patient_id)
        if conn is not None and conn.environment != env:
            raise JunctionError(
                f"{patient_id}'s Junction account belongs to the {conn.environment} "
                f"environment; disconnect it before linking under {env}",
                status=409,
            )
        with self._client() as client:
            if conn is None or conn.status == ConnectionStatus.DISCONNECTED:
                # A fresh opaque reference every time an account is (re)created:
                # a disconnect deleted the previous Junction user, and reusing
                # its client_user_id would either collide with the tombstone
                # or resolve to it.
                client_user_id = f"mp_{uuid.uuid4().hex}"
                floor, _ceiling = ingestible_window(patient.surgery_date, date.today())
                user = client.resolve_user(client_user_id) or client.create_user(
                    client_user_id,
                    fallback_time_zone=patient.timezone,
                    # Junction's own ingestion bound, so the aggregator never
                    # even pulls history the ingest window would drop.
                    ingestion_start=floor,
                )
                user_id = user.get("user_id") if isinstance(user, dict) else None
                if not isinstance(user_id, str) or not user_id:
                    raise JunctionError("Junction did not return a user_id for the new user")
                if conn is None:
                    conn = WearableConnection(
                        patient_id=patient_id,
                        aggregator=AGGREGATOR,
                        client_user_id=client_user_id,
                        external_user_id=user_id,
                        environment=env,
                    )
                    db.add(conn)
                else:
                    conn.client_user_id = client_user_id
                    conn.external_user_id = user_id
                    conn.environment = env
                conn.status = ConnectionStatus.PENDING_LINK
                conn.providers = None
                conn.last_error = None
                db.flush()

            token = client.create_link_token(
                conn.external_user_id,
                redirect_url=settings.junction_link_redirect_url.strip() or None,
            )
        url = token.get("link_web_url") if isinstance(token, dict) else None
        if not isinstance(url, str) or not url:
            raise JunctionError("Junction did not return a link_web_url")
        conn.last_link_issued_at = datetime.now()
        db.commit()
        return LinkSession(url=url, expires_at=token.get("expires_at"), connection=conn)

    def authorize(self, db: Session, patient_id: str) -> str:
        return self.create_link(db, patient_id).url

    def sync_providers(self, db: Session, patient_id: str) -> list[dict[str, Any]]:
        """Refresh the connection's provider snapshot (and Device rows) from
        what Junction currently reports for the user."""
        conn = self.active_connection(db, patient_id)
        with self._client() as client:
            providers = client.connected_providers(conn.external_user_id)
        snapshot: list[dict[str, Any]] = []
        for p in providers:
            slug = p.get("slug") if isinstance(p.get("slug"), str) else None
            if not slug:
                continue
            status = str(p.get("status") or "connected")
            error = p.get("error_details") if isinstance(p.get("error_details"), dict) else None
            entry = {
                "slug": slug,
                "name": p.get("name") or slug,
                "status": status,
                "connected_at": p.get("created_on"),
                "error": error.get("error_message") if error else None,
            }
            snapshot.append(entry)
            self._upsert_device(
                db, conn, slug, entry["name"],
                status="error" if status == "error" else "connected",
                connected_at=_utc_naive(_parse_dt(p.get("created_on"))),
            )
        self._store_snapshot(conn, snapshot)
        db.commit()
        return snapshot

    def handle_oauth_callback(
        self, db: Session, patient_id: str, params: dict[str, Any]
    ) -> OAuthResult:
        """Junction Link redirects back with nothing we need to exchange; the
        connection itself is announced by webhook. Treat the callback as a
        cue to refresh the provider snapshot."""
        conn = self.active_connection(db, patient_id)
        snapshot = self.sync_providers(db, patient_id)
        connected = [p["slug"] for p in snapshot if p["status"] == "connected"]
        return OAuthResult(
            authorized=bool(connected),
            provider_user_id=conn.external_user_id,
            scopes=connected,
        )

    def disconnect(self, db: Session, patient_id: str) -> dict[str, Any]:
        """Deregister the patient at Junction and retire the local mapping.

        Observations already ingested stay: they are the patient's history.
        Late deliveries for the old user id are ignored by resolve_patient.
        """
        conn = self.connection_for(db, patient_id)
        if conn is None:
            raise ValueError(f"{patient_id} has no Junction connection")
        remote = "skipped"
        if conn.status != ConnectionStatus.DISCONNECTED:
            try:
                with self._client() as client:
                    client.delete_user(conn.external_user_id)
                remote = "deleted"
            except JunctionNotConfigured:
                remote = "not_configured"
            except JunctionError as e:
                # Local state is retired regardless: a connection the console
                # says is gone must stop routing data whatever Junction thinks.
                logger.warning("Junction user %s could not be deleted: %s", conn.external_user_id, e)
                remote = f"failed: {e}"
        conn.status = ConnectionStatus.DISCONNECTED
        conn.last_error = None
        for device in self._devices_for(db, conn):
            device.status = "revoked"
        db.commit()
        return {"remote": remote, "connection": conn}

    def register_webhook(self, callback_url: str) -> bool:
        """Junction endpoints are registered in its dashboard (a Svix portal),
        not through the API. What this can do is confirm the other half is in
        place: a delivery is only ever accepted when the signing secret is
        configured (api/webhooks.py fails closed)."""
        if not settings.junction_webhook_secret:
            logger.warning(
                "JUNCTION_WEBHOOK_SECRET is not set; deliveries to %s will be rejected",
                callback_url,
            )
            return False
        return True

    def webhook_portal_url(self) -> str | None:
        with self._client() as client:
            return client.svix_portal_url()

    def request_refresh(self, conn: WearableConnection) -> None:
        """Ask Junction to re-pull from every provider linked to this user
        now, ahead of a back-fill read."""
        with self._client() as client:
            client.refresh_user(conn.external_user_id)

    # -- devices ---------------------------------------------------------------

    @staticmethod
    def device_id(conn: WearableConnection, slug: str) -> str:
        return f"junction:{conn.external_user_id}:{slug}"

    def _devices_for(self, db: Session, conn: WearableConnection) -> list[Device]:
        prefix = f"junction:{conn.external_user_id}:"
        return list(
            db.scalars(
                select(Device).where(
                    Device.patient_id == conn.patient_id, Device.id.like(prefix + "%")
                )
            )
        )

    def _upsert_device(
        self,
        db: Session,
        conn: WearableConnection,
        slug: str,
        name: str | None,
        *,
        status: str = "connected",
        connected_at: datetime | None = None,
        synced_at: datetime | None = None,
    ) -> Device:
        device = db.get(Device, self.device_id(conn, slug))
        if device is None:
            device = Device(
                id=self.device_id(conn, slug),
                patient_id=conn.patient_id,
                source_provider=BRAND_BY_SLUG.get(slug, AGGREGATOR),
                device_model=f"{name or slug} via Junction",
                connected_at=connected_at or datetime.now(),
                status=status,
            )
            db.add(device)
        else:
            device.status = status
            if name and device.device_model != f"{name} via Junction":
                device.device_model = f"{name} via Junction"
        if synced_at is not None:
            device.last_sync_at = synced_at
        return device

    @staticmethod
    def _store_snapshot(conn: WearableConnection, snapshot: list[dict[str, Any]]) -> None:
        conn.providers = snapshot
        connected = [p for p in snapshot if p.get("status") == "connected"]
        errored = [p for p in snapshot if p.get("status") == "error"]
        if connected:
            conn.status = ConnectionStatus.LINKED
            conn.last_error = None
        elif errored:
            conn.status = ConnectionStatus.ERROR
            first = errored[0]
            conn.last_error = f"{first['slug']}: {first.get('error') or 'connection error'}"
        elif conn.status != ConnectionStatus.DISCONNECTED:
            conn.status = ConnectionStatus.PENDING_LINK

    # -- webhook dispatch ------------------------------------------------------

    def receive(
        self, db: Session, raw_payload: dict[str, Any], patient: PatientContext
    ) -> Delivery:
        event_type = raw_payload.get("event_type")
        family, resource, action = _split_event(event_type)
        data = raw_payload.get("data")
        if not isinstance(data, dict):
            raise ValueError(f"Junction {event_type} payload must carry a data object")
        conn = self.connection_for(db, patient.id)
        if conn is None:
            raise ValueError(f"No Junction connection for {patient.id}")
        conn.last_event_at = datetime.now()

        if family == "provider" and resource == "connection":
            note = self._apply_connection_event(db, conn, action, data)
            db.commit()
            return Delivery("connection", note=note)

        if family == "historical":
            return self._receive_historical(db, conn, patient, resource, data, event_type)

        if family == "daily":
            observations, dropped = self._normalize_event(raw_payload, patient)
            if observations:
                conn.last_data_at = datetime.now()
                self.mark_synced(db, conn, observations)
            db.commit()
            note = f"dropped {dropped} implausible row(s)" if dropped else None
            if not observations and resource not in SUMMARY_RESOURCES:
                if resource not in TIMESERIES_METRIC:
                    note = f"{resource} is not ingested"
                elif resource == "heartrate" and not settings.junction_ingest_heart_rate_samples:
                    note = "heart-rate samples are off (JUNCTION_INGEST_HEART_RATE_SAMPLES)"
            return Delivery("data", observations, note=note)

        db.commit()
        return Delivery("ignored", note=f"{event_type} is not handled")

    def _apply_connection_event(
        self, db: Session, conn: WearableConnection, action: str, data: dict[str, Any]
    ) -> str:
        snapshot = list(conn.providers or [])
        by_slug = {p.get("slug"): p for p in snapshot if isinstance(p, dict)}
        now = datetime.now()
        if action == "created":
            provider = data.get("provider") or data.get("source") or {}
            slug = provider.get("slug") if isinstance(provider, dict) else None
            if not isinstance(slug, str) or not slug:
                raise ValueError("provider.connection.created carries no provider slug")
            name = provider.get("name") if isinstance(provider, dict) else None
            entry = by_slug.get(slug) or {"slug": slug}
            entry.update(
                {
                    "name": name or entry.get("name") or slug,
                    "status": "connected",
                    "connected_at": entry.get("connected_at") or now.isoformat(),
                    "error": None,
                }
            )
            if slug not in by_slug:
                snapshot.append(entry)
            self._upsert_device(db, conn, slug, entry["name"], connected_at=now)
            self._store_snapshot(conn, snapshot)
            return f"{slug} connected"
        if action == "error":
            slug = data.get("provider")
            if not isinstance(slug, str) or not slug:
                raise ValueError("provider.connection.error carries no provider slug")
            message = data.get("message") or data.get("error_details") or "connection error"
            error_type = data.get("error_type") or "unknown"
            entry = by_slug.get(slug) or {"slug": slug, "name": slug, "connected_at": None}
            entry.update({"status": "error", "error": f"{error_type}: {message}"})
            if slug not in by_slug:
                snapshot.append(entry)
            self._upsert_device(db, conn, slug, entry.get("name"), status="error")
            self._store_snapshot(conn, snapshot)
            return f"{slug} error: {error_type}"
        return f"provider.connection.{action} is not handled"

    def _receive_historical(
        self,
        db: Session,
        conn: WearableConnection,
        patient: PatientContext,
        resource: str,
        data: dict[str, Any],
        event_type: Any,
    ) -> Delivery:
        if resource not in PULLABLE_RESOURCES:
            db.commit()
            return Delivery("historical", note=f"{resource} is not ingested")
        if not self.is_configured():
            db.commit()
            return Delivery(
                "historical",
                note=f"{resource} back-fill available but JUNCTION_API_KEY is not set",
            )
        db_patient = db.get(Patient, patient.id)
        if db_patient is None:
            raise ValueError(f"Unknown patient: {patient.id}")
        start = _parse_day(data.get("start_date"))
        end = _parse_day(data.get("end_date"))
        provider = data.get("provider") if isinstance(data.get("provider"), str) else None
        report = self.pull(
            db, conn, db_patient, [resource], start=start, end=end, provider=provider
        )
        conn.last_backfill_at = datetime.now()
        if report.observations:
            conn.last_data_at = datetime.now()
            self.mark_synced(db, conn, report.observations)
        db.commit()
        window = f"{report.start}..{report.end}" if report.start else "empty window"
        note = f"pulled {resource} for {window}"
        if provider:
            note += f" from {provider}"
        if report.dropped:
            note += f", dropped {report.dropped} implausible row(s)"
        if not report.complete:
            note += "; pull hit the time budget — run a backfill to finish"
        return Delivery("historical", report.observations, note=note)

    def mark_synced(
        self, db: Session, conn: WearableConnection, observations: list[CanonicalObservation]
    ) -> None:
        """Stamp last_sync_at on the Device row behind each source that just
        delivered, creating the row if data arrived before its connection
        event did (a back-fill can)."""
        now = datetime.now()
        for slug in sorted({o.source_device_id for o in observations if o.source_device_id}):
            self._upsert_device(db, conn, slug, None, synced_at=now)

    # -- pulling ---------------------------------------------------------------

    def pull(
        self,
        db: Session,
        conn: WearableConnection,
        patient: Patient,
        resources: list[str] | tuple[str, ...] = PULLABLE_RESOURCES,
        *,
        start: date | None = None,
        end: date | None = None,
        provider: str | None = None,
        metric_types: list[M] | None = None,
        budget_s: float = DEFAULT_PULL_BUDGET_S,
    ) -> PullReport:
        """Pull summaries and timeseries for a patient over a date range,
        clamped to the ingestible window and bounded by a wall-clock budget."""
        floor, ceiling = ingestible_window(patient.surgery_date, date.today())
        lo = max(start or floor, floor)
        hi = min(end or ceiling, ceiling)
        report = PullReport(start=lo, end=hi)
        if lo > hi:
            report.resources = list(resources)
            return report
        wanted = set(metric_types) if metric_types else None
        ctx = PatientContext(patient.id, patient.timezone)
        limit = time.monotonic() + budget_s
        with self._client() as client:
            for resource in resources:
                if resource not in PULLABLE_RESOURCES:
                    continue
                if resource == "heartrate" and not settings.junction_ingest_heart_rate_samples:
                    continue
                produced = SUMMARY_METRICS.get(resource) or {TIMESERIES_METRIC[resource]}
                if resource == "hrv":
                    produced = {M.HRV_RMSSD, M.HRV_SDNN}
                if wanted is not None and not (produced & wanted):
                    continue
                remaining = limit - time.monotonic()
                if remaining <= 0:
                    report.skipped.append(resource)
                    continue
                if resource in SUMMARY_RESOURCES:
                    rows = client.summaries(
                        resource, conn.external_user_id, lo, hi,
                        provider=provider, deadline_s=remaining,
                    )
                    for rec in rows:
                        obs, dropped = self._normalize_summary(
                            resource, rec, ctx, f"pull.{resource}"
                        )
                        report.observations.extend(obs)
                        report.dropped += dropped
                else:
                    blocks = client.timeseries_grouped(
                        resource, conn.external_user_id, lo, hi,
                        provider=provider, deadline_s=remaining,
                    )
                    for block in blocks:
                        obs, dropped = self._normalize_block(
                            resource, block, ctx, f"pull.{resource}"
                        )
                        report.observations.extend(obs)
                        report.dropped += dropped
                report.resources.append(resource)
        return report

    def fetch_historical(
        self,
        db: Session,
        patient_id: str,
        start: date,
        end: date,
        metric_types: list[M] | None = None,
    ) -> list[CanonicalObservation]:
        conn = self.active_connection(db, patient_id)
        patient = db.get(Patient, patient_id)
        if patient is None:
            raise ValueError(f"Unknown patient: {patient_id}")
        return self.pull(
            db, conn, patient, start=start, end=end, metric_types=metric_types
        ).observations

    # -- normalization ---------------------------------------------------------

    def normalize(
        self, raw_payload: dict[str, Any], patient: PatientContext | None = None
    ) -> list[CanonicalObservation]:
        return self._normalize_event(raw_payload, patient)[0]

    def _normalize_event(
        self, raw_payload: dict[str, Any], patient: PatientContext | None
    ) -> tuple[list[CanonicalObservation], int]:
        if patient is None:
            raise ValueError(
                "Junction deliveries are resolved to a patient through the connections "
                "table; normalize() needs the resolved PatientContext"
            )
        event_type = raw_payload.get("event_type")
        family, resource, _action = _split_event(event_type)
        data = raw_payload.get("data")
        if not isinstance(data, dict):
            raise ValueError(f"Junction {event_type} payload must carry a data object")
        if family != "daily":
            return [], 0
        if resource in SUMMARY_RESOURCES:
            return self._normalize_summary(resource, data, patient, event_type)
        if resource in TIMESERIES_METRIC:
            return self._normalize_block(resource, data, patient, event_type)
        return [], 0

    def _normalize_summary(
        self, resource: str, rec: dict[str, Any], patient: PatientContext, event_type: str
    ) -> tuple[list[CanonicalObservation], int]:
        if resource == "activity":
            return self._activity(rec, patient, event_type)
        if resource == "sleep":
            return self._sleep(rec, patient, event_type)
        if resource == "workouts":
            return self._workout(rec, patient, event_type)
        return [], 0  # body: no MetricType for weight / body fat yet

    def _daily_rows(
        self,
        resource: str,
        rec: dict[str, Any],
        patient: PatientContext,
        event_type: str,
        values: list[tuple[M, float | None, dict[str, Any] | None]],
    ) -> tuple[list[CanonicalObservation], int]:
        day = _parse_day(rec.get("calendar_date")) or _parse_day(rec.get("date"))
        if day is None:
            raise ValueError(f"Junction {resource} summary carries no calendar_date")
        source = _source_of(rec)
        slug = _slug_of(source)
        record_id = rec.get("id")
        external_id = (
            str(record_id) if isinstance(record_id, (str, int)) and record_id != ""
            else f"{resource}:{slug or 'unknown'}:{day.isoformat()}"
        )
        tz_id = rec.get("time_zone") if isinstance(rec.get("time_zone"), str) else patient.timezone
        start, end = _day_bounds(day)
        provenance = {
            "event_type": event_type,
            "resource": resource,
            "junction_id": record_id,
            "calendar_date": day.isoformat(),
            "source": source,
        }
        rows: list[CanonicalObservation] = []
        dropped = 0
        for metric, value, extra in values:
            if value is None:
                continue
            if not self._plausible(metric, value, patient.id, day):
                dropped += 1
                continue
            rows.append(
                CanonicalObservation(
                    patient_id=patient.id,
                    source_provider=AGGREGATOR,
                    metric_type=metric,
                    unit=UNITS[metric],
                    value_num=round(value, 3),
                    value_json=extra,
                    start_time=start,
                    end_time=end,
                    granularity=Granularity.DAILY_SUMMARY,
                    source_device_id=slug or None,
                    timezone=tz_id,
                    external_id=external_id,
                    source_updated_at=_utc_naive(_parse_dt(rec.get("updated_at"))),
                    qualifies_for_rtm=slug not in MANUAL_PROVIDERS,
                    is_patient_reported=slug in MANUAL_PROVIDERS,
                    raw_payload=provenance,
                )
            )
        return rows, dropped

    def _activity(
        self, rec: dict[str, Any], patient: PatientContext, event_type: str
    ) -> tuple[list[CanonicalObservation], int]:
        slug = _slug_of(_source_of(rec))
        heart = rec.get("heart_rate") if isinstance(rec.get("heart_rate"), dict) else {}
        values: list[tuple[M, float | None, dict[str, Any] | None]] = [
            (M.STEPS, _number(rec.get("steps")), None),
            (M.CALORIES, _number(rec.get("calories_total")), None),
            (M.ACTIVE_ENERGY, _number(rec.get("calories_active")), None),
        ]
        if slug not in SLEEP_RHR_PROVIDERS:
            values.append((M.RESTING_HR, _number(heart.get("resting_bpm")), None))
        return self._daily_rows("activity", rec, patient, event_type, values)

    def _sleep(
        self, rec: dict[str, Any], patient: PatientContext, event_type: str
    ) -> tuple[list[CanonicalObservation], int]:
        sleep_type = rec.get("type") or "long_sleep"
        if sleep_type in ("unknown", "acknowledged_nap"):
            # unknown = still recording (restated on completion); a nap is
            # not the night's sleep and would halve the day's duration.
            return [], 0
        slug = _slug_of(_source_of(rec))
        total_s = _number(rec.get("total"))
        total_h = total_s / 3600.0 if total_s is not None else None
        stages: dict[str, Any] = {}
        for stage in ("deep", "rem", "light", "awake"):
            seconds = _number(rec.get(stage))
            if seconds is not None:
                stages[stage] = round(seconds / 3600.0, 2)
        for key in (
            "score", "efficiency", "latency", "hr_average", "hr_lowest",
            "bedtime_start", "bedtime_stop", "state", "type",
        ):
            if rec.get(key) is not None:
                stages[key] = rec[key]
        hrv_metric = M.HRV_SDNN if slug in SDNN_PROVIDERS else M.HRV_RMSSD
        values: list[tuple[M, float | None, dict[str, Any] | None]] = [
            (M.SLEEP_DURATION, total_h, None),
            (M.SLEEP_STAGES, total_h, stages or None),
            (hrv_metric, _number(rec.get("average_hrv")), None),
            (M.RESPIRATORY_RATE, _number(rec.get("respiratory_rate")), None),
            (M.SKIN_TEMP_DELTA, _number(rec.get("temperature_delta")), None),
            (M.SKIN_TEMP, _number(rec.get("skin_temperature")), None),
        ]
        if slug in SLEEP_RHR_PROVIDERS:
            rhr = _number(rec.get("hr_resting"))
            if rhr is None:
                rhr = _number(rec.get("hr_lowest"))
            values.append((M.RESTING_HR, rhr, None))
        return self._daily_rows("sleep", rec, patient, event_type, values)

    def _workout(
        self, rec: dict[str, Any], patient: PatientContext, event_type: str
    ) -> tuple[list[CanonicalObservation], int]:
        start = _parse_dt(rec.get("time_start"))
        end = _parse_dt(rec.get("time_end"))
        if start is None or end is None or end < start:
            return [], 0
        source = _source_of(rec)
        slug = _slug_of(source)
        moving = _number(rec.get("moving_time"))
        seconds = moving if moving is not None else (end - start).total_seconds()
        minutes = seconds / 60.0
        if not self._plausible(M.EXERCISE_SESSION, minutes, patient.id, start.date()):
            return [], 1
        record_id = rec.get("id") or rec.get("provider_id")
        sport = rec.get("sport") if isinstance(rec.get("sport"), dict) else {}
        detail = {
            "sport": sport.get("slug") or sport.get("name"),
            "title": rec.get("title"),
            "average_hr": rec.get("average_hr"),
            "max_hr": rec.get("max_hr"),
            "calories": rec.get("calories"),
            "distance_m": rec.get("distance"),
            "steps": rec.get("steps"),
        }
        offset = rec.get("timezone_offset")
        row = CanonicalObservation(
            patient_id=patient.id,
            source_provider=AGGREGATOR,
            metric_type=M.EXERCISE_SESSION,
            unit=UNITS[M.EXERCISE_SESSION],
            value_num=round(minutes, 1),
            value_json={k: v for k, v in detail.items() if v is not None},
            start_time=_local_wall_time(start, offset, patient.timezone),
            end_time=_local_wall_time(end, offset, patient.timezone),
            granularity=Granularity.SESSION,
            source_device_id=slug or None,
            timezone=patient.timezone,
            external_id=str(record_id) if record_id else None,
            source_updated_at=_utc_naive(_parse_dt(rec.get("updated_at"))),
            qualifies_for_rtm=slug not in MANUAL_PROVIDERS,
            is_patient_reported=slug in MANUAL_PROVIDERS,
            raw_payload={
                "event_type": event_type,
                "resource": "workouts",
                "junction_id": rec.get("id"),
                "provider_id": rec.get("provider_id"),
                "calendar_date": rec.get("calendar_date"),
                "source": source,
            },
        )
        return [row], 0

    def _normalize_block(
        self, resource: str, block: dict[str, Any], patient: PatientContext, event_type: str
    ) -> tuple[list[CanonicalObservation], int]:
        metric = TIMESERIES_METRIC[resource]
        if metric is M.HR_SAMPLE and not settings.junction_ingest_heart_rate_samples:
            return [], 0
        source = _source_of(block)
        slug = _slug_of(source)
        if resource == "hrv" and slug in SDNN_PROVIDERS:
            metric = M.HRV_SDNN
        samples = block.get("data")
        if not isinstance(samples, list):
            return [], 0
        provenance = {"event_type": event_type, "resource": resource, "source": source}
        rows: list[CanonicalObservation] = []
        dropped = 0
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            value = _number(sample.get("value"))
            if value is None:
                continue
            start = _parse_dt(sample.get("start")) or _parse_dt(sample.get("timestamp"))
            if start is None:
                continue
            end = _parse_dt(sample.get("end")) if sample.get("end") else None
            offset = sample.get("timezone_offset")
            local_start = _local_wall_time(start, offset, patient.timezone)
            local_end = _local_wall_time(end, offset, patient.timezone) if end else local_start
            if local_end < local_start:
                local_end = local_start
            if not self._plausible(metric, value, patient.id, local_start.date()):
                dropped += 1
                continue
            site = sample.get("sensor_location")
            rows.append(
                CanonicalObservation(
                    patient_id=patient.id,
                    source_provider=AGGREGATOR,
                    metric_type=metric,
                    unit=UNITS[metric],
                    value_num=round(value, 3),
                    start_time=local_start,
                    end_time=local_end,
                    granularity=Granularity.INTERVAL if end else Granularity.INSTANT,
                    source_device_id=slug or None,
                    timezone=patient.timezone,
                    body_site=site if isinstance(site, str) else None,
                    qualifies_for_rtm=slug not in MANUAL_PROVIDERS,
                    is_patient_reported=slug in MANUAL_PROVIDERS,
                    raw_payload=provenance,
                )
            )
        return rows, dropped

    @staticmethod
    def _plausible(metric: M, value: float, patient_id: str, day: date) -> bool:
        bounds = PLAUSIBLE_RANGE.get(str(metric))
        if bounds is None:
            return True
        low, high = bounds
        if low <= value <= high:
            return True
        logger.warning(
            "Dropping implausible Junction %s for %s on %s: %s (plausible %s..%s)",
            metric, patient_id, day, value, low, high,
        )
        return False
