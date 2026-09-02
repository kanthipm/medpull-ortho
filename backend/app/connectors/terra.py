"""Terra aggregator connector — scaffolded, not yet implemented.

Terra (tryterra.co) was one of the two aggregators evaluated for production;
Junction (``junction.py``) is the one that shipped. Terra stays scaffolded
because a signed BAA is listed only under its custom-priced Enterprise plan,
which rules the $399–499/mo tier out for PHI at startup pricing.

What a real implementation needs (researched mid-2026):
- Terra dev account + API key + signing secret; BAA executed (Terra is
  HIPAA/SOC-2, BAA available). Pricing: ~$399/mo incl. 100k credits
  (~200 credits/user/mo).
- authorize(): POST /auth/generateWidgetSession -> widget URL for the patient.
- handle_oauth_callback(): Terra redirects with user_id; store the
  terra_user_id <-> patient_id mapping (models/connection.py already holds
  one aggregator account per patient, keyed by aggregator).
- register_webhook(): configured in the Terra dashboard; verify the
  "terra-signature" header (HMAC-SHA256 with the signing secret) on every
  delivery — api/webhooks.py already carries that verifier.
- normalize(): map Terra's Activity/Daily/Sleep/Body models onto MetricType;
  Terra passes Apple mobility metrics (walking speed/asymmetry/steadiness)
  through for Apple-sourced users only.
- fetch_historical(): GET /activity /daily /sleep with time ranges for
  back-fill after connect.
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
    "TerraConnector is scaffolding for the production Terra integration. "
    "See the module docstring for what a real implementation requires."
)


class TerraConnector(WearableConnector):
    provider = SourceProvider.TERRA

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
