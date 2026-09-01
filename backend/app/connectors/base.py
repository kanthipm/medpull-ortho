"""Provider-agnostic wearable connector contract.

Design (from integration research, mid-2026):
- Long-term strategy is aggregator-first (Terra or Junction) plus a thin Apple
  HealthKit companion-app path for gait metrics, which are Apple-exclusive.
- Every source — aggregator webhook, direct OAuth API, native app sync, or the
  mock generator — implements this same interface and emits
  CanonicalObservation rows. Nothing downstream (engine, API, frontend) may
  depend on a specific provider.
- Ingestion is idempotent: dedupe_key is deterministic per (provider, patient,
  metric, window) so re-delivered webhooks and back-fills upsert cleanly.
- There is exactly one day definition: local_date_of() resolves the patient-
  local calendar day once, at ingest, and readers index the materialized column
  rather than re-deriving a day of their own from start_time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone as dt_timezone
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from app.models.enums import Granularity, MetricType, SourceProvider

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def local_date_of(start_time: datetime, tz_id: str) -> date:
    """The patient-local calendar day an instant belongs to.

    Aware datetimes are converted into the observation's zone; naive ones are
    trusted as already-local wall time (the seed and mock paths).

    This is the product's only day definition. The column it materializes is
    what the RTM day counter counts (rtm/coverage.py) and what the engine's
    post-op day axis is built from (engine/dataload.py); no reader may derive a
    second day from start_time, because func.date() on a naive UTC instant
    moves a West Coast evening onto the next calendar day and the two
    definitions would then disagree about which day a reading belongs to.
    """
    if start_time.tzinfo is not None:
        return start_time.astimezone(ZoneInfo(tz_id)).date()
    return start_time.date()


def _utc_iso(t: datetime) -> str:
    """Offset-stable instant for dedupe keys: aware → UTC; naive unchanged.

    A naive isoformat() emits no offset, so across a DST fall-back two distinct
    instants would collide (lost row) and a device timezone change would split
    one instant into two keys (duplicate row)."""
    if t.tzinfo is not None:
        return t.astimezone(dt_timezone.utc).isoformat()
    return t.isoformat()


@dataclass
class CanonicalObservation:
    """Normalized unit of health data — mirrors the observations table."""

    patient_id: str
    source_provider: SourceProvider
    metric_type: MetricType
    unit: str
    start_time: datetime
    end_time: datetime
    granularity: Granularity
    value_num: float | None = None
    value_json: dict[str, Any] | None = None
    source_device_id: str | None = None
    timezone: str = "America/New_York"
    raw_payload: dict[str, Any] | None = None
    # Restatement + provenance (Phase 0): the provider's stable record id, its
    # own last-modified stamp, laterality, and the RTM/PRO flags.
    external_id: str | None = None
    source_updated_at: datetime | None = None
    body_site: str | None = None
    side: str | None = None
    qualifies_for_rtm: bool = False
    is_patient_reported: bool = False
    deleted: bool = False  # provider-delivered tombstone (HealthKit deletedObjects)

    @property
    def local_date(self) -> date:
        return local_date_of(self.start_time, self.timezone)

    @property
    def dedupe_key(self) -> str:
        """Identity of the underlying measurement, not of one delivery of it.

        Provider record ids win when they exist — a WHOOP sleep edit arrives
        with the same UUID and different times, and must land on the same row.
        Daily summaries key on the local calendar day so a restated total whose
        window boundary shifted by a second cannot double-count the day.
        Interval rows carry granularity, device and side: a daily summary and
        an intraday bucket over the same window, an iPhone and a Watch, or two
        wrists must never collide."""
        if self.external_id:
            return (
                f"{self.source_provider}:{self.patient_id}:{self.metric_type}:"
                f"{self.external_id}"
            )
        if self.granularity is Granularity.DAILY_SUMMARY:
            return (
                f"{self.source_provider}:{self.patient_id}:{self.metric_type}:daily:"
                f"{self.local_date.isoformat()}:{self.side or 'na'}"
            )
        return (
            f"{self.source_provider}:{self.patient_id}:{self.metric_type}:"
            f"{self.granularity}:{_utc_iso(self.start_time)}:{_utc_iso(self.end_time)}:"
            f"{self.source_device_id or 'na'}:{self.side or 'na'}"
        )


@dataclass
class OAuthResult:
    authorized: bool
    provider_user_id: str | None = None
    scopes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PatientContext:
    """What a connector is told about the patient a payload was resolved to.

    Resolution happens *before* normalization and never from the body: the
    webhook handler asks the connector which patient a delivery belongs to
    (``resolve_patient``), loads that patient, and hands the connector this
    context. A connector therefore cannot be talked into writing under a
    patient id it merely read out of an inbound payload.
    """

    id: str
    timezone: str = "America/New_York"


@dataclass
class Delivery:
    """What one webhook delivery turned out to be, decided by the connector.

    ``kind`` is ``data`` (observations to ingest), ``connection`` (a device was
    linked or failed), ``historical`` (a back-fill window became available and
    was pulled) or ``ignored`` (verified, recorded, nothing to do).
    """

    kind: str
    observations: list[CanonicalObservation] = field(default_factory=list)
    note: str | None = None


class WearableConnector(ABC):
    """Contract every data source implements.

    Real connectors (Junction today, Terra when it ships) are network clients;
    the mock connector generates data locally. Callers must treat all of them
    identically: the webhook handler and the integrations API only ever call
    the methods below.
    """

    provider: SourceProvider

    # An aggregator restates and back-fills months of history as a matter of
    # course, so rows dated outside the patient's ingestible window are
    # routine and are dropped before ingest, with the count reported. The demo
    # connector keeps ingest's all-or-nothing rejection: there an out-of-window
    # date is a bug in the caller and should be loud.
    drops_out_of_window_rows: bool = False

    @abstractmethod
    def authorize(self, db: Session, patient_id: str) -> str:
        """Begin auth for a patient; returns the URL to send the patient to
        (OAuth consent page / aggregator widget). Mock returns a no-op URL."""

    @abstractmethod
    def handle_oauth_callback(
        self, db: Session, patient_id: str, params: dict[str, Any]
    ) -> OAuthResult:
        """Complete the OAuth code exchange and persist tokens."""

    @abstractmethod
    def register_webhook(self, callback_url: str) -> bool:
        """Register our ingestion endpoint with the provider (if push-based)."""

    @abstractmethod
    def fetch_historical(
        self,
        db: Session,
        patient_id: str,
        start: date,
        end: date,
        metric_types: list[MetricType] | None = None,
    ) -> list[CanonicalObservation]:
        """Pull a historical range (initial back-fill after connect)."""

    @abstractmethod
    def normalize(
        self, raw_payload: dict[str, Any], patient: PatientContext | None = None
    ) -> list[CanonicalObservation]:
        """Translate one provider webhook/API payload into canonical rows.

        ``patient`` is the resolved patient for connectors that key deliveries
        on an external user id. The demo connector, whose body *is* the
        identity, ignores it."""

    def resolve_patient(self, db: Session, raw_payload: dict[str, Any]) -> str | None:
        """Which patient a delivery belongs to, or None if it maps to nobody.

        The default reads the body, which is acceptable only for the unsigned
        demo connector — there the endpoint is a developer tool and the body
        is the request. A real connector overrides this to look the payload's
        external user id up in the connections table, and returns None for a
        user it has never issued, so the handler records and ignores the
        delivery instead of writing it anywhere.

        Raises ValueError for a body that is malformed rather than unknown.
        """
        patient_id = raw_payload.get("patient_id")
        if not isinstance(patient_id, str) or not patient_id:
            raise ValueError("Webhook payload must carry a patient_id")
        return patient_id

    def receive(
        self, db: Session, raw_payload: dict[str, Any], patient: PatientContext
    ) -> Delivery:
        """Process one verified delivery for a resolved patient.

        The default treats every delivery as data. A connector whose provider
        also sends lifecycle events (a device linked, a back-fill window ready)
        overrides this to act on them and returns the matching ``Delivery``
        kind, so the handler can record what happened without knowing the
        provider's event vocabulary.
        """
        return Delivery("data", self.normalize(raw_payload, patient))
