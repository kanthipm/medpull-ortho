"""Terra aggregator connector — scaffolded, not yet implemented.

Terra (tryterra.co) is one of the two recommended aggregators for production
(the other is Junction). One integration covers Apple Health, Fitbit, Garmin,
Oura, Whoop, Samsung, Withings, Dexcom, Polar and ~500 more sources behind a
single OAuth widget + webhook stream.

What a real implementation needs (researched mid-2026):
- Terra dev account + API key + signing secret; BAA executed (Terra is
  HIPAA/SOC-2, BAA available). Pricing: ~$399/mo incl. 100k credits
  (~200 credits/user/mo).
- authorize(): POST /auth/generateWidgetSession -> widget URL for the patient.
- handle_oauth_callback(): Terra redirects with user_id; store the
  terra_user_id <-> patient_id mapping.
- register_webhook(): configured in the Terra dashboard; verify the
  "terra-signature" header (HMAC-SHA256 with the signing secret) on every
  delivery — wire that into api/webhooks.py's signature hook.
- normalize(): map Terra's Activity/Daily/Sleep/Body models onto MetricType;
  Terra passes Apple mobility metrics (walking speed/asymmetry/steadiness)
  through for Apple-sourced users only.
- fetch_historical(): GET /activity /daily /sleep with time ranges for
  back-fill after connect.
"""

from datetime import date
from typing import Any

from app.connectors.base import CanonicalObservation, OAuthResult, WearableConnector
from app.models.enums import MetricType, SourceProvider

_MSG = (
    "TerraConnector is scaffolding for the production Terra integration. "
    "See the module docstring for what a real implementation requires."
)


class TerraConnector(WearableConnector):
    provider = SourceProvider.MOCK  # becomes the per-user source provider once live

    def authorize(self, patient_id: str) -> str:
        raise NotImplementedError(_MSG)

    def handle_oauth_callback(self, patient_id: str, params: dict[str, Any]) -> OAuthResult:
        raise NotImplementedError(_MSG)

    def register_webhook(self, callback_url: str) -> bool:
        raise NotImplementedError(_MSG)

    def fetch_historical(
        self,
        patient_id: str,
        start: date,
        end: date,
        metric_types: list[MetricType] | None = None,
    ) -> list[CanonicalObservation]:
        raise NotImplementedError(_MSG)

    def normalize(self, raw_payload: dict[str, Any]) -> list[CanonicalObservation]:
        raise NotImplementedError(_MSG)
