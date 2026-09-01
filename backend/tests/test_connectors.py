"""Connector contract, the ingest guards, and the single day definition.

Rows these tests write are SIX_MIN_WALK. The seed emits VITALS + FUNCTIONAL +
GAIT_EXTRA plus derived active-energy/calories/sleep-stages and never this, and
it appears in neither pipeline.ANALYZED_METRICS nor confidence.KEY_METRICS — so
a day these tests add, restate or tombstone is a day no seeded row also
occupies, and nothing here can move a pinned golden tier.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.connectors.apple_healthkit import AppleHealthKitConnector
from app.connectors.base import CanonicalObservation, local_date_of
from app.connectors.capabilities import CAPABILITIES, provider_supports
from app.connectors.ingest import (
    MAX_BATCH_OBSERVATIONS,
    MAX_FUTURE_DAYS,
    MAX_PREOP_BACKFILL_DAYS,
    ingest_observations,
)
from app.connectors.junction import JunctionConnector
from app.connectors.mock import MockConnector, daily_observation
from app.connectors.registry import PROVIDERS, get_connector
from app.connectors.terra import TerraConnector
from app.engine.dataload import load_daily_series
from app.models.enums import Granularity, MetricType, SourceProvider
from app.models.observation import Observation
from app.models.patient import Patient

INERT = MetricType.SIX_MIN_WALK


def _payload(patient_id="james", day=None):
    day = day or date.today().isoformat()
    return {
        "patient_id": patient_id,
        "provider": "fitbit",
        "records": [
            {"metric_type": "steps", "date": day, "value": 9100.0, "unit": "count"},
            {"metric_type": "resting_hr", "date": day, "value": 61.0, "unit": "bpm"},
        ],
    }


def _inert(patient_id: str, day: date, value: float = 500.0) -> CanonicalObservation:
    """A daily-summary row on a metric the engine never analyzes."""
    return daily_observation(patient_id, SourceProvider.MOCK, INERT, day, value)


def _keyed(external_id: str, granularity: Granularity, value: float, **extra):
    """A row on dedupe branch 1 — keyed on the provider's record id alone."""
    day = date.today()
    return CanonicalObservation(
        patient_id="james",
        source_provider=SourceProvider.MOCK,
        metric_type=INERT,
        unit="m",
        value_num=value,
        start_time=datetime.combine(day, time.min),
        end_time=datetime.combine(day, time(23, 59, 59)),
        granularity=granularity,
        external_id=external_id,
        **extra,
    )


def _count(db) -> int:
    return db.scalar(select(func.count(Observation.id)))


def test_mock_normalize_pinned_format():
    observations = MockConnector().normalize(_payload())
    assert len(observations) == 2
    assert observations[0].patient_id == "james"
    assert observations[0].granularity == "daily_summary"


def test_the_demo_connector_cannot_write_under_another_providers_name():
    """/webhooks/wearables/mock is unsigned by design, so the provider in the
    body is provenance and never identity.

    dedupe_key leads with the provider: honouring the claim put an anonymous
    POST's rows directly on top of a real connector's rows, restating a
    patient's genuine history in place (200 {"updated": 20}) rather than
    adding demo data beside it."""
    observations = MockConnector().normalize(_payload())
    assert all(o.source_provider == SourceProvider.MOCK for o in observations)
    assert observations[0].dedupe_key.startswith("mock:james:steps:")
    # a real fitbit row for the same patient, metric and day keeps its own key
    real = daily_observation(
        "james", SourceProvider.FITBIT, MetricType.STEPS,
        date.fromisoformat(_payload()["records"][0]["date"]), 9100.0,
    )
    assert real.dedupe_key != observations[0].dedupe_key
    # the claim is kept as provenance
    assert observations[0].raw_payload["claimed_provider"] == "fitbit"


def test_mock_normalize_still_rejects_an_unknown_provider():
    with pytest.raises(ValueError):
        MockConnector().normalize({**_payload(), "provider": "not-a-provider"})


def test_ingest_rejects_physiologically_impossible_values(db):
    """A single impossible reading is not a small error: a baseline is a mean
    over ten days, so one 'resting HR' of 200 moves the reference twelve beats
    and blinds the channel that decides the patient's tier."""
    day = date.today()
    good = daily_observation("james", SourceProvider.MOCK, MetricType.RESTING_HR, day, 61.0)
    bad = daily_observation("james", SourceProvider.MOCK, MetricType.RESTING_HR, day, 200.0)
    before = _count(db)
    with pytest.raises(ValueError, match="impossible"):
        ingest_observations(db, [good, bad])
    assert _count(db) == before  # all-or-nothing: the good row is not written either
    assert ingest_observations(db, [good]) == (1, 0, 0)


def test_mock_normalize_rejects_malformed():
    with pytest.raises(ValueError):
        MockConnector().normalize({"nope": True})


def test_mock_normalize_caps_the_batch():
    day = date.today().isoformat()
    record = {"metric_type": "steps", "date": day, "value": 1.0, "unit": "count"}
    payload = {
        "patient_id": "james",
        "provider": "fitbit",
        "records": [record] * (MAX_BATCH_OBSERVATIONS + 1),
    }
    with pytest.raises(ValueError, match="ceiling"):
        MockConnector().normalize(payload)


def test_ingest_is_idempotent(db):
    observations = [_inert("james", date.today())]
    first = ingest_observations(db, observations)
    second = ingest_observations(db, observations)
    assert first == (1, 0, 0)   # (ingested, updated, duplicates)
    assert second == (0, 0, 1)  # byte-identical redelivery is a duplicate, never an update


def test_ingest_rejects_a_backdated_batch(db):
    """A pre-op back-fill from before the patient's history is not more data —
    compute_baseline() takes every negative day, so it rewrites the reference."""
    patient = db.get(Patient, "james")
    stale = patient.surgery_date - timedelta(days=MAX_PREOP_BACKFILL_DAYS + 1)
    before = _count(db)
    with pytest.raises(ValueError, match="ingestible window"):
        ingest_observations(db, [_inert("james", stale, 95.0)])
    assert _count(db) == before  # all-or-nothing: nothing written


def test_ingest_rejects_a_future_batch(db):
    patient = db.get(Patient, "james")
    ahead = date.today() + timedelta(days=MAX_FUTURE_DAYS + 1)
    before = _count(db)
    with pytest.raises(ValueError, match="ingestible window"):
        ingest_observations(db, [_inert("james", ahead, 110.0)])
    assert _count(db) == before
    assert patient.surgery_date < ahead


def test_ingest_accepts_the_window_edges(db):
    patient = db.get(Patient, "james")
    floor = patient.surgery_date - timedelta(days=MAX_PREOP_BACKFILL_DAYS)
    ceiling = date.today() + timedelta(days=MAX_FUTURE_DAYS)
    assert ingest_observations(db, [_inert("james", floor), _inert("james", ceiling)]) == (
        2,
        0,
        0,
    )


def test_ingest_rejects_an_oversized_batch(db):
    day = date.today()
    batch = [_inert("james", day, float(i)) for i in range(3)] * (
        MAX_BATCH_OBSERVATIONS // 3 + 1
    )
    before = _count(db)
    with pytest.raises(ValueError, match="ceiling"):
        ingest_observations(db, batch)
    assert _count(db) == before


def test_ingest_rejects_an_unknown_patient(db):
    before = _count(db)
    with pytest.raises(ValueError, match="unknown patient"):
        ingest_observations(db, [_inert("ghost", date.today())])
    assert _count(db) == before


def test_engine_ignores_tombstoned_observations(db):
    """A provider tombstone must stop driving baselines, z-scores and charts."""
    patient = db.get(Patient, "james")
    day = date.today() - timedelta(days=2)
    index = (day - patient.surgery_date).days

    assert ingest_observations(db, [_inert("james", day, 501.0)]) == (1, 0, 0)
    assert index in load_daily_series(db, "james", patient.surgery_date)[str(INERT)].index

    tombstone = _inert("james", day, 501.0)
    tombstone.deleted = True
    assert ingest_observations(db, [tombstone]) == (0, 1, 0)

    series = load_daily_series(db, "james", patient.surgery_date)
    assert index not in series.get(str(INERT), {})


def test_engine_day_axis_is_the_materialized_local_date(db):
    """The engine and the RTM day counter must agree on which day a reading is.

    23:30 in Los Angeles is already the next calendar day in New York — the
    zone this row is stamped with — so start_time.date() and local_date name
    different days, and only local_date is the auditable one.
    """
    patient = db.get(Patient, "james")
    local_day = date.today() - timedelta(days=4)
    start = datetime.combine(
        local_day, time(23, 30), tzinfo=ZoneInfo("America/Los_Angeles")
    )
    observation = CanonicalObservation(
        patient_id="james",
        source_provider=SourceProvider.MOCK,
        metric_type=INERT,
        unit="m",
        value_num=777.0,
        start_time=start,
        end_time=start,
        granularity=Granularity.DAILY_SUMMARY,
        timezone="America/New_York",
    )
    assert observation.start_time.date() != observation.local_date
    assert ingest_observations(db, [observation]) == (1, 0, 0)

    series = load_daily_series(db, "james", patient.surgery_date)[str(INERT)]
    assert (observation.local_date - patient.surgery_date).days in series.index
    assert (observation.start_time.date() - patient.surgery_date).days not in series.index


def test_local_date_of_resolves_aware_instants_into_the_stamped_zone():
    aware = datetime(2026, 8, 20, 23, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert local_date_of(aware, "America/New_York") == date(2026, 8, 21)
    assert local_date_of(aware, "America/Los_Angeles") == date(2026, 8, 20)
    # Naive instants are already patient-local wall time and are trusted as-is.
    assert local_date_of(datetime(2026, 8, 20, 23, 30), "Asia/Tokyo") == date(2026, 8, 20)


def test_dedupe_key_prefers_the_provider_record_id():
    """Branch 1: a restated row arrives with the same id and different times."""
    first = _keyed("whoop-sleep-9", Granularity.SESSION, 1.0)
    second = _keyed("whoop-sleep-9", Granularity.DAILY_SUMMARY, 2.0)
    assert first.dedupe_key == second.dedupe_key
    assert first.dedupe_key == f"mock:james:{INERT}:whoop-sleep-9"


def test_dedupe_key_separates_interval_rows_by_offset_device_and_side():
    """Branch 3: two devices, two wrists, and two instants must not collide."""
    start = datetime(2026, 8, 20, 8, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    end = datetime(2026, 8, 20, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles"))

    def interval(device: str | None, side: str | None) -> CanonicalObservation:
        return CanonicalObservation(
            patient_id="james",
            source_provider=SourceProvider.MOCK,
            metric_type=INERT,
            unit="m",
            value_num=12.0,
            start_time=start,
            end_time=end,
            granularity=Granularity.INTERVAL,
            source_device_id=device,
            side=side,
        )

    keys = {
        interval(None, None).dedupe_key,
        interval("iphone", None).dedupe_key,
        interval("watch", None).dedupe_key,
        interval("watch", "left").dedupe_key,
        interval("watch", "right").dedupe_key,
    }
    assert len(keys) == 5
    # _utc_iso normalizes the offset, so the same instant expressed in another
    # zone is one row, not two.
    same_instant = interval("watch", "left")
    same_instant.start_time = start.astimezone(ZoneInfo("America/New_York"))
    same_instant.end_time = end.astimezone(ZoneInfo("America/New_York"))
    assert same_instant.dedupe_key == interval("watch", "left").dedupe_key


def test_restatement_writes_granularity_through(db):
    """Branch 1 does not pin granularity, so a bucket restated as a daily
    summary keys to the same row and must not keep the stale granularity."""
    first = _keyed("restate-granularity", Granularity.INTERVAL, 100.0)
    second = _keyed("restate-granularity", Granularity.DAILY_SUMMARY, 100.0)
    assert first.dedupe_key == second.dedupe_key

    assert ingest_observations(db, [first]) == (1, 0, 0)
    # granularity is in the payload hash, so this is a restatement, not a duplicate
    assert ingest_observations(db, [second]) == (0, 1, 0)

    row = db.scalar(select(Observation).where(Observation.dedupe_key == first.dedupe_key))
    assert row.granularity == Granularity.DAILY_SUMMARY
    assert row.revision == 1


def test_restatement_cannot_promote_a_row_into_the_billable_set(db):
    """rtm/coverage.py counts qualifies_for_rtm rows, so a redelivery over an
    unsigned path must never be able to set it."""
    first = _keyed("rtm-guard", Granularity.DAILY_SUMMARY, 10.0)
    second = _keyed("rtm-guard", Granularity.DAILY_SUMMARY, 11.0, qualifies_for_rtm=True)

    assert ingest_observations(db, [first]) == (1, 0, 0)
    assert ingest_observations(db, [second]) == (0, 1, 0)

    row = db.scalar(select(Observation).where(Observation.dedupe_key == first.dedupe_key))
    assert row.value_num == 11.0  # the measurement is restated
    assert row.qualifies_for_rtm is False  # the billing flag is not


def test_registry_shape():
    assert len(PROVIDERS) == 10
    assert get_connector(SourceProvider.MOCK) is not None
    assert get_connector(SourceProvider.FITBIT) is None  # scaffolded only


def test_gait_capability_is_apple_only():
    gait = MetricType.WALKING_ASYMMETRY_PCT
    real_providers = [p for p in CAPABILITIES if p not in (SourceProvider.MOCK,)]
    supporting = {p for p in real_providers if provider_supports(p, gait)}
    assert supporting == {SourceProvider.APPLE}


def test_stub_connectors_raise_not_implemented():
    for connector in (TerraConnector(), JunctionConnector(), AppleHealthKitConnector()):
        with pytest.raises(NotImplementedError):
            connector.authorize("marcus")
        with pytest.raises(NotImplementedError):
            connector.normalize({})
