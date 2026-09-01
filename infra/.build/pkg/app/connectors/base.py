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
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.models.enums import Granularity, MetricType, SourceProvider


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

    @property
    def dedupe_key(self) -> str:
        return (
            f"{self.source_provider}:{self.patient_id}:{self.metric_type}:"
            f"{self.start_time.isoformat()}:{self.end_time.isoformat()}"
        )


@dataclass
class OAuthResult:
    authorized: bool
    provider_user_id: str | None = None
    scopes: list[str] = field(default_factory=list)


class WearableConnector(ABC):
    """Contract every data source implements.

    Real connectors (Terra, Junction, direct OAuth APIs) will be async network
    clients; the mock connector generates data locally. Callers must treat all
    of them identically.
    """

    provider: SourceProvider

    @abstractmethod
    def authorize(self, patient_id: str) -> str:
        """Begin auth for a patient; returns the URL to send the patient to
        (OAuth consent page / aggregator widget). Mock returns a no-op URL."""

    @abstractmethod
    def handle_oauth_callback(self, patient_id: str, params: dict[str, Any]) -> OAuthResult:
        """Complete the OAuth code exchange and persist tokens."""

    @abstractmethod
    def register_webhook(self, callback_url: str) -> bool:
        """Register our ingestion endpoint with the provider (if push-based)."""

    @abstractmethod
    def fetch_historical(
        self,
        patient_id: str,
        start: date,
        end: date,
        metric_types: list[MetricType] | None = None,
    ) -> list[CanonicalObservation]:
        """Pull a historical range (initial back-fill after connect)."""

    @abstractmethod
    def normalize(self, raw_payload: dict[str, Any]) -> list[CanonicalObservation]:
        """Translate one provider webhook/API payload into canonical rows."""
