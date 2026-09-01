"""Junction (formerly Vital) aggregator connector — scaffolded, not yet implemented.

Junction (junction.com, fka tryvital.com) is the alternative aggregator to
Terra: ~$0.50/user/mo with a $300/mo floor, 300+ devices, plus lab-ordering
APIs if MedPull later adds laboratory data to the intelligence engine.

What a real implementation needs:
- Junction workspace + API key; BAA (enterprise tier).
- authorize(): create a Link token (POST /v2/link/token) -> Junction Link
  widget URL for the patient's device sign-in.
- handle_oauth_callback(): Link completion webhook carries the vital user_id;
  persist the mapping to patient_id.
- register_webhook(): configure endpoint in the dashboard; verify the
  svix-signature headers (Junction uses Svix for webhook delivery).
- normalize(): map Junction resources (activity, sleep, body, workouts,
  vitals timeseries) onto MetricType.
- Their native Health SDK is the path for Apple HealthKit / Android Health
  Connect data, including Apple-only gait metrics.
"""

from datetime import date
from typing import Any

from app.connectors.base import CanonicalObservation, OAuthResult, WearableConnector
from app.models.enums import MetricType, SourceProvider

_MSG = (
    "JunctionConnector is scaffolding for the production Junction (fka Vital) "
    "integration. See the module docstring for requirements."
)


class JunctionConnector(WearableConnector):
    provider = SourceProvider.MOCK

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
