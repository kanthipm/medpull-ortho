"""Apple HealthKit connector — scaffolded, not yet implemented.

HealthKit is strategically important for orthopedic recovery because Apple's
mobility metrics — walking speed, step length, walking asymmetry %,
double-support %, walking steadiness, stair speeds, six-minute walk — exist on
no other platform, and gait quality is the strongest wearable signal for
lower-limb recovery.

Hard constraints (why this cannot be a pure server-side connector):
- HealthKit is an ON-DEVICE store. There is no server pull API: a companion
  iOS app (or the aggregator's iOS SDK embedded in the MedPull patient app)
  must read HealthKit locally and push to our ingestion endpoint. Junction's
  ``apple_health_kit`` provider is exactly that SDK path, which is why the
  Junction connector lists Apple Health as needing the companion app rather
  than as linkable from the hosted widget.
- Background delivery is throttled by iOS — data arrives in batches, not
  real-time. Design for late, out-of-order back-fill (ingest.py already
  upserts idempotently by dedupe_key).
- Apple signs no BAA: HIPAA responsibility begins the moment data reaches our
  backend. PHI handling follows the repo's KNOWN_ISSUES.md conventions.
- Mobility metrics are measured primarily by iPhone carried near the waist
  (iOS 14+); treat walking asymmetry / double-support as trend indicators,
  not clinical-grade gait lab values (validation literature: good agreement
  for speed/step length, moderate for asymmetry).

The push path when implemented: the iOS app POSTs batches to
/api/webhooks/wearables/apple in the canonical record format; normalize()
maps HKQuantityType identifiers onto MetricType.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from app.connectors.base import (
    CanonicalObservation,
    OAuthResult,
    PatientContext,
    WearableConnector,
)
from app.models.enums import MetricType, SourceProvider

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_MSG = (
    "AppleHealthKitConnector requires the companion iOS app path — HealthKit "
    "has no server pull API. See the module docstring."
)


class AppleHealthKitConnector(WearableConnector):
    provider = SourceProvider.APPLE

    def authorize(self, db: Session, patient_id: str) -> str:
        raise NotImplementedError(_MSG)

    def handle_oauth_callback(
        self, db: Session, patient_id: str, params: dict[str, Any]
    ) -> OAuthResult:
        raise NotImplementedError(_MSG)

    def register_webhook(self, callback_url: str) -> bool:
        raise NotImplementedError(_MSG)

    def fetch_historical(
        self,
        db: Session,
        patient_id: str,
        start: date,
        end: date,
        metric_types: list[MetricType] | None = None,
    ) -> list[CanonicalObservation]:
        raise NotImplementedError(_MSG)

    def normalize(
        self, raw_payload: dict[str, Any], patient: PatientContext | None = None
    ) -> list[CanonicalObservation]:
        raise NotImplementedError(_MSG)
