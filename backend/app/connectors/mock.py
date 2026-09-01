"""Mock connector — the only fully-implemented data source in v1.

It plays two roles:
1. Webhook demo: normalize() parses the demo webhook payload format so the
   full ingestion path (webhook -> normalize -> idempotent upsert -> engine
   recompute) can be exercised without any real provider.
2. Historical generation: fetch_historical() produces realistic seeded daily
   data (delegating to the seed generators) for any patient/date range.

The payload format it accepts mirrors what an aggregator webhook would carry:
{"patient_id": "...", "provider": "apple", "records":
  [{"metric_type": "steps", "date": "2026-07-10", "value": 4200.0, "unit": "count"}]}

normalize() parses an untrusted body, so it enforces the batch ceiling here and
leaves the per-patient date window to ingest, which is the one place every
connector's output passes through.
"""

from datetime import date, datetime, time
from typing import Any

from app.connectors.base import CanonicalObservation, OAuthResult, WearableConnector
from app.connectors.ingest import MAX_BATCH_OBSERVATIONS
from app.models.enums import Granularity, MetricType, SourceProvider

UNITS: dict[MetricType, str] = {
    MetricType.STEPS: "count",
    MetricType.RESTING_HR: "bpm",
    MetricType.HR_SAMPLE: "bpm",
    MetricType.HRV_RMSSD: "ms",
    MetricType.SLEEP_DURATION: "h",
    MetricType.SLEEP_STAGES: "h",
    MetricType.ACTIVE_ENERGY: "kcal",
    MetricType.EXERCISE_SESSION: "min",
    MetricType.SPO2: "%",
    MetricType.RESPIRATORY_RATE: "breaths/min",
    MetricType.SKIN_TEMP: "degC",
    MetricType.WALKING_SPEED: "m/s",
    MetricType.STEP_LENGTH: "m",
    MetricType.DOUBLE_SUPPORT_PCT: "%",
    MetricType.WALKING_ASYMMETRY_PCT: "%",
    MetricType.WALKING_STEADINESS: "score",
    MetricType.STAIR_SPEED_UP: "m/s",
    MetricType.STAIR_SPEED_DOWN: "m/s",
    MetricType.SIX_MIN_WALK: "m",
    MetricType.CALORIES: "kcal",
}


def daily_observation(
    patient_id: str,
    provider: SourceProvider,
    metric: MetricType,
    day: date,
    value: float,
    raw: dict[str, Any] | None = None,
    tz_id: str | None = None,
) -> CanonicalObservation:
    """One daily-summary row for `day`, dated in the patient's wall time.

    `day` is already a patient-local calendar day, so the times are naive and
    local_date resolves back to `day` in any zone. tz_id is carried through so
    a caller that knows the patient's zone (Patient.timezone) can stamp it on
    the row; it does not move the day.
    """
    return CanonicalObservation(
        patient_id=patient_id,
        source_provider=provider,
        metric_type=metric,
        unit=UNITS[metric],
        value_num=round(float(value), 3),
        start_time=datetime.combine(day, time.min),
        end_time=datetime.combine(day, time(23, 59, 59)),
        granularity=Granularity.DAILY_SUMMARY,
        raw_payload=raw,
        **({"timezone": tz_id} if tz_id else {}),
    )


class MockConnector(WearableConnector):
    provider = SourceProvider.MOCK

    def authorize(self, patient_id: str) -> str:
        return "mock://connected"

    def handle_oauth_callback(self, patient_id: str, params: dict[str, Any]) -> OAuthResult:
        return OAuthResult(authorized=True, provider_user_id=f"mock-{patient_id}")

    def register_webhook(self, callback_url: str) -> bool:
        return True

    def fetch_historical(
        self,
        patient_id: str,
        start: date,
        end: date,
        metric_types: list[MetricType] | None = None,
    ) -> list[CanonicalObservation]:
        # Local import: the seed package imports connectors for ingestion.
        from app.seed.generators import generate_range

        return generate_range(patient_id, start, end, metric_types)

    def normalize(self, raw_payload: dict[str, Any]) -> list[CanonicalObservation]:
        """Parse a demo webhook body into canonical rows, stamped MOCK.

        The body's `provider` field is provenance, never identity. This
        endpoint is unsigned by design (`_verify_mock` accepts every delivery),
        so honouring a caller-supplied provider let an anonymous POST write
        under another provider's name — and because dedupe_key leads with the
        provider, those rows landed ON a real connector's existing rows and
        restated them in place. Twenty of a patient's genuine pre-op readings
        were rewritten to 95 bpm / 38.5 °C by one unauthenticated request that
        answered 200 {"updated": 20}. Stamping MOCK confines the demo path to
        its own keyspace, where the worst it can do is add demo rows.
        """
        patient_id = raw_payload.get("patient_id")
        provider_key = raw_payload.get("provider", "mock")
        records = raw_payload.get("records", [])
        if not patient_id or not isinstance(records, list):
            raise ValueError(
                "Mock webhook payload must have patient_id and a records list; "
                'expected {"patient_id", "provider", "records": [{"metric_type", "date", "value"}]}'
            )
        # Cap before building rows, not after: the ceiling is there so an
        # unbounded body cannot be materialized in the first place. Dates are
        # bounded downstream in ingest, which knows the patient's surgery date.
        if len(records) > MAX_BATCH_OBSERVATIONS:
            raise ValueError(
                f"Mock webhook payload carries {len(records)} records; the ingest "
                f"ceiling is {MAX_BATCH_OBSERVATIONS}"
            )
        # Still validated, so a typo'd provider is a 422 rather than a silent
        # relabel — but the claim is recorded, not obeyed.
        claimed = SourceProvider(provider_key)

        out: list[CanonicalObservation] = []
        for rec in records:
            metric = MetricType(rec["metric_type"])
            day = date.fromisoformat(rec["date"])
            raw = dict(rec)
            if claimed is not SourceProvider.MOCK:
                raw["claimed_provider"] = str(claimed)
            out.append(
                daily_observation(
                    patient_id, SourceProvider.MOCK, metric, day,
                    float(rec["value"]), raw=raw,
                )
            )
        return out
