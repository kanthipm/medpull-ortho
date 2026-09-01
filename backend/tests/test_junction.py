"""The Junction connector: normalization semantics, webhook resolution and
dispatch, the link / back-fill / disconnect lifecycle against a fake Junction,
and the HTTP client's back-off.

Every observation these tests write belongs to a patient created here and
removed at module teardown, so nothing can move a seeded patient's pinned
golden tier. Payload shapes follow ``junction-api-sdk`` 1.4.0, the SDK
Junction generates from its own API definition.
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete, func, select

from app.config import settings
from app.connectors.base import PatientContext
from app.connectors.ingest import MAX_PREOP_BACKFILL_DAYS
from app.connectors.junction import (
    BRAND_BY_SLUG,
    JunctionConnector,
    _split_event,
)
from app.connectors.junction_client import (
    JunctionClient,
    JunctionError,
    JunctionNotConfigured,
    base_url_for,
)
from app.connectors.registry import junction_connector
from app.models.connection import WearableConnection
from app.models.enums import ConnectionStatus, Granularity, ProcedureType
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider as P
from app.models.insight import EstablishedBaseline, Insight, RiskAssessment
from app.models.notification import Notification
from app.models.observation import Observation, WebhookEvent
from app.models.patient import Device, Patient
from app.models.rtm import MonitoringWindow

PATIENT = "jx_test"
USER_ID = "user-jx-0001"
CLIENT_USER_ID = "mp_testclientuser"
SIGNING_KEY = b"junction-test-signing-key"
SECRET = "whsec_" + base64.b64encode(SIGNING_KEY).decode()
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
SANDBOX = "https://api.sandbox.us.junction.com"


# --- fixtures ------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def jx_patient(seeded_db):
    """A patient of our own, west of the server, removed with everything that
    hangs off it once the module is done."""
    db = seeded_db
    surgery = TODAY - timedelta(days=12)
    db.add(
        Patient(
            id=PATIENT,
            name="Jax Test",
            initials="JT",
            age=60,
            sex="F",
            procedure_type=ProcedureType.TKA,
            procedure_display="Total Knee Replacement (TKA)",
            surgery_date=surgery,
            discharge_date=surgery + timedelta(days=2),
            timezone="America/Los_Angeles",
            surgeon_id="ct_alvarez",
            assigned_provider_id="ct_alvarez",
        )
    )
    db.commit()
    yield PATIENT
    db.expire_all()
    for model in (
        Observation,
        Device,
        WearableConnection,
        RiskAssessment,
        EstablishedBaseline,
        MonitoringWindow,
        Notification,
        Insight,
    ):
        db.execute(delete(model).where(model.patient_id == PATIENT))
    db.execute(delete(WebhookEvent).where(WebhookEvent.provider == "junction"))
    db.execute(delete(Patient).where(Patient.id == PATIENT))
    db.commit()


def _reset_connection(db, environment: str | None = None) -> WearableConnection:
    db.expire_all()
    db.execute(delete(WearableConnection).where(WearableConnection.patient_id == PATIENT))
    db.execute(delete(Device).where(Device.patient_id == PATIENT))
    conn = WearableConnection(
        patient_id=PATIENT,
        aggregator=P.JUNCTION,
        external_user_id=USER_ID,
        client_user_id=CLIENT_USER_ID,
        environment=environment or settings.junction_environment,
        status=ConnectionStatus.PENDING_LINK,
    )
    db.add(conn)
    db.commit()
    return conn


@pytest.fixture()
def connection(db, jx_patient):
    return _reset_connection(db)


@pytest.fixture()
def signing_secret(monkeypatch):
    monkeypatch.setattr(settings, "junction_webhook_secret", SECRET)
    return SECRET


class FakeJunction:
    """An httpx transport standing in for the Junction API."""

    def __init__(self, *, summaries=None, timeseries=None, providers=None):
        self.summaries = summaries or {}
        self.timeseries = timeseries or {}
        self.providers = providers or []
        self.requests: list[httpx.Request] = []
        self.known_client_ids: set[str] = set()
        self.transport = httpx.MockTransport(self.handle)

    def calls(self, method: str, prefix: str) -> list[httpx.Request]:
        return [
            r for r in self.requests if r.method == method and r.url.path.startswith(prefix)
        ]

    def _user(self, client_user_id: str) -> dict:
        return {
            "user_id": USER_ID,
            "client_user_id": client_user_id,
            "team_id": "team-1",
            "created_on": "2026-08-01T10:00:00+00:00",
            "connected_sources": [],
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        method, path = request.method, request.url.path
        if method == "POST" and path == "/v2/user":
            body = json.loads(request.content)
            self.known_client_ids.add(body["client_user_id"])
            return httpx.Response(200, json=self._user(body["client_user_id"]))
        if method == "GET" and path.startswith("/v2/user/resolve/"):
            client_user_id = path.rsplit("/", 1)[1]
            if client_user_id in self.known_client_ids:
                return httpx.Response(200, json=self._user(client_user_id))
            return httpx.Response(404, json={"detail": "User not found"})
        if method == "POST" and path == "/v2/link/token":
            return httpx.Response(
                200,
                json={
                    "link_token": "lt_test",
                    "link_web_url": "https://link.junction.com/?token=lt_test",
                    "expires_at": "2026-09-01T12:00:00Z",
                },
            )
        if method == "GET" and path.startswith("/v2/user/providers/"):
            return httpx.Response(200, json={"providers": self.providers})
        if method == "POST" and path.startswith("/v2/user/refresh/"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "user_id": USER_ID,
                    "refreshed_sources": ["oura"],
                    "in_progress_sources": ["garmin"],
                    "failed_sources": [],
                },
            )
        if method == "DELETE" and path.startswith("/v2/user/"):
            return httpx.Response(200, json={"success": True})
        if method == "GET" and path.startswith("/v2/summary/"):
            resource = path.split("/")[3]
            return httpx.Response(200, json={resource: self.summaries.get(resource, [])})
        if method == "GET" and "/v2/timeseries/" in path:
            resource = path.split("/")[4]
            blocks = self.timeseries.get(resource, [])
            return httpx.Response(
                200, json={"groups": {"oura": blocks} if blocks else {}, "next_cursor": None}
            )
        if method == "GET" and path == "/v2/team/svix/url":
            return httpx.Response(200, json={"url": "https://app.svix.com/portal/test"})
        return httpx.Response(404, json={"detail": f"no route for {method} {path}"})


@pytest.fixture()
def fake(monkeypatch):
    """Point the registered connector at a fake Junction and turn the key on."""
    fake = FakeJunction()
    connector = junction_connector()
    monkeypatch.setattr(settings, "junction_api_key", "sk_us_test")
    monkeypatch.setattr(settings, "junction_environment", "sandbox")
    monkeypatch.setattr(
        connector,
        "_client_factory",
        lambda: JunctionClient(
            "sk_us_test", SANDBOX, transport=fake.transport, sleep=lambda _s: None
        ),
    )
    return fake


# --- payload builders ------------------------------------------------------------


def envelope(event_type, data, *, user_id=USER_ID, client_user_id=CLIENT_USER_ID):
    return {
        "event_type": event_type,
        "team_id": "team-1",
        "user_id": user_id,
        "client_user_id": client_user_id,
        "data": data,
    }


def sleep_summary(day=YESTERDAY, provider="oura", **over):
    rec = {
        "id": "sleep-1",
        "user_id": USER_ID,
        "date": f"{day.isoformat()}T00:00:00+00:00",
        "calendar_date": day.isoformat(),
        "bedtime_start": f"{(day - timedelta(days=1)).isoformat()}T06:00:00+00:00",
        "bedtime_stop": f"{day.isoformat()}T14:00:00+00:00",
        "type": "long_sleep",
        "timezone_offset": -25200,
        "duration": 28800,
        "total": 25200,
        "awake": 3600,
        "light": 12600,
        "rem": 6300,
        "deep": 6300,
        "score": 80,
        "hr_lowest": 48,
        "hr_average": 55,
        "hr_resting": None,
        "efficiency": 87.5,
        "latency": 600,
        "temperature_delta": -0.2,
        "skin_temperature": None,
        "state": "confirmed",
        "average_hrv": 52.0,
        "respiratory_rate": 14.2,
        "source": {"provider": provider, "type": "ring", "app_id": None, "device_id": None},
        "created_at": f"{day.isoformat()}T15:00:00+00:00",
        "updated_at": f"{day.isoformat()}T15:00:00+00:00",
    }
    rec.update(over)
    return rec


def activity_summary(day=YESTERDAY, provider="fitbit", **over):
    rec = {
        "id": "act-1",
        "user_id": USER_ID,
        "date": f"{day.isoformat()}T00:00:00+00:00",
        "calendar_date": day.isoformat(),
        "calories_total": 2100.0,
        "calories_active": 500.0,
        "steps": 6400,
        "distance": 4200.0,
        "low": 120.0,
        "medium": 30.0,
        "high": 0.0,
        "floors_climbed": 3,
        "time_zone": "America/Los_Angeles",
        "timezone_offset": -25200,
        "heart_rate": {"avg_bpm": 72, "min_bpm": 50, "max_bpm": 130, "resting_bpm": 58},
        "source": {"provider": provider, "type": "watch", "app_id": None, "device_id": None},
        "created_at": f"{day.isoformat()}T23:00:00+00:00",
        "updated_at": f"{day.isoformat()}T23:00:00+00:00",
    }
    rec.update(over)
    return rec


def workout(day=YESTERDAY, provider="garmin", **over):
    rec = {
        "id": "wk-1",
        "user_id": USER_ID,
        "title": "Morning walk",
        "timezone_offset": -25200,
        "average_hr": 95,
        "max_hr": 120,
        "distance": 1500.0,
        "calendar_date": day.isoformat(),
        "time_start": f"{day.isoformat()}T16:00:00+00:00",
        "time_end": f"{day.isoformat()}T16:35:00+00:00",
        "calories": 120.0,
        "sport": {"id": 1, "name": "Walking", "slug": "walking"},
        "moving_time": 1800,
        "provider_id": "garmin-123",
        "source": {"provider": provider, "type": "watch"},
        "created_at": f"{day.isoformat()}T17:00:00+00:00",
        "updated_at": f"{day.isoformat()}T17:00:00+00:00",
    }
    rec.update(over)
    return rec


def sample_block(day=YESTERDAY, provider="oura", values=(96.0, 96.5, 97.0), unit="%"):
    return {
        "source": {"provider": provider, "type": "ring"},
        "data": [
            {
                "timestamp": f"{day.isoformat()}T0{i}:00:00+00:00",
                "value": value,
                "unit": unit,
                "type": None,
                "timezone_offset": -25200,
            }
            for i, value in enumerate(values)
        ],
    }


def interval_block(day=YESTERDAY, provider="fitbit", values=(120.0, 80.0)):
    return {
        "source": {"provider": provider, "type": "watch"},
        "data": [
            {
                "start": f"{day.isoformat()}T1{i}:00:00+00:00",
                "end": f"{day.isoformat()}T1{i}:15:00+00:00",
                "value": value,
                "unit": "count",
                "timezone_offset": -25200,
            }
            for i, value in enumerate(values)
        ],
    }


def svix_headers(body: bytes, key: bytes = SIGNING_KEY) -> dict[str, str]:
    msg_id = "msg_test"
    stamp = str(int(time.time()))
    digest = hmac.new(key, f"{msg_id}.{stamp}.".encode() + body, hashlib.sha256).digest()
    return {
        "svix-id": msg_id,
        "svix-timestamp": stamp,
        "svix-signature": "v1," + base64.b64encode(digest).decode(),
        "content-type": "application/json",
    }


def post_signed(client, payload: dict, key: bytes = SIGNING_KEY):
    body = json.dumps(payload).encode()
    return client.post("/api/webhooks/wearables/junction", content=body, headers=svix_headers(body, key))


def rows_for(db, metric: M | None = None) -> list[Observation]:
    db.expire_all()
    stmt = select(Observation).where(
        Observation.patient_id == PATIENT, Observation.source_provider == P.JUNCTION
    )
    if metric is not None:
        stmt = stmt.where(Observation.metric_type == metric)
    return list(db.scalars(stmt))


CTX = PatientContext(PATIENT, "America/Los_Angeles")
connector_under_test = JunctionConnector()


# --- normalization ---------------------------------------------------------------


def test_sleep_summary_maps_every_metric_with_the_right_semantics():
    rows = connector_under_test.normalize(
        envelope("daily.data.sleep.created", sleep_summary()), CTX
    )
    by_metric = {r.metric_type: r for r in rows}
    assert set(by_metric) == {
        M.SLEEP_DURATION, M.SLEEP_STAGES, M.HRV_RMSSD, M.RESPIRATORY_RATE,
        M.SKIN_TEMP_DELTA, M.RESTING_HR,
    }
    assert by_metric[M.SLEEP_DURATION].value_num == 7.0  # `total` (asleep), not `duration`
    assert by_metric[M.SLEEP_DURATION].unit == "h"
    assert by_metric[M.SLEEP_STAGES].value_json["deep"] == 1.75
    assert by_metric[M.SLEEP_STAGES].value_json["awake"] == 1.0
    assert by_metric[M.HRV_RMSSD].value_num == 52.0
    assert by_metric[M.SKIN_TEMP_DELTA].value_num == -0.2
    # Oura's resting HR is a sleep statistic: hr_resting, else the nightly low
    assert by_metric[M.RESTING_HR].value_num == 48.0
    for row in rows:
        assert row.source_provider is P.JUNCTION
        assert row.granularity is Granularity.DAILY_SUMMARY
        assert row.local_date == YESTERDAY  # the calendar_date, whatever the bedtimes
        assert row.external_id == "sleep-1"
        assert row.source_device_id == "oura"
        # the provider's stamp is flattened to naive UTC, the form SQLite
        # hands back, so a later restatement can be ordered against it
        assert row.source_updated_at == datetime.combine(YESTERDAY, datetime.min.time()).replace(hour=15)
        assert row.source_updated_at.tzinfo is None
        assert row.qualifies_for_rtm is True
        assert row.is_patient_reported is False
        assert row.raw_payload["event_type"] == "daily.data.sleep.created"
        assert "sleep_stream" not in row.raw_payload


def test_daily_resting_hr_providers_take_it_from_activity_not_sleep():
    """One definition per provider: Fitbit's RHR is the daily figure on the
    activity summary, and its sleep summary contributes none."""
    sleep_rows = connector_under_test.normalize(
        envelope("daily.data.sleep.created", sleep_summary(provider="fitbit")), CTX
    )
    assert M.RESTING_HR not in {r.metric_type for r in sleep_rows}
    activity_rows = connector_under_test.normalize(
        envelope("daily.data.activity.created", activity_summary(provider="fitbit")), CTX
    )
    by_metric = {r.metric_type: r for r in activity_rows}
    assert set(by_metric) == {M.STEPS, M.CALORIES, M.ACTIVE_ENERGY, M.RESTING_HR}
    assert by_metric[M.STEPS].value_num == 6400.0
    assert by_metric[M.CALORIES].value_num == 2100.0
    assert by_metric[M.ACTIVE_ENERGY].value_num == 500.0
    assert by_metric[M.RESTING_HR].value_num == 58.0
    assert by_metric[M.STEPS].timezone == "America/Los_Angeles"  # the summary's own zone
    # and the reverse: an Oura activity summary never contributes a daily RHR
    oura_rows = connector_under_test.normalize(
        envelope("daily.data.activity.created", activity_summary(provider="oura")), CTX
    )
    assert M.RESTING_HR not in {r.metric_type for r in oura_rows}


def test_apple_hrv_lands_in_the_sdnn_channel():
    """Apple HealthKit only measures SDNN; a stream labelled rmssd cannot
    convert it, so it must not join the RMSSD control chart."""
    rows = connector_under_test.normalize(
        envelope("daily.data.sleep.created", sleep_summary(provider="apple_health_kit")), CTX
    )
    metrics = {r.metric_type for r in rows}
    assert M.HRV_SDNN in metrics and M.HRV_RMSSD not in metrics
    block = envelope("daily.data.hrv.created", sample_block(provider="apple_health_kit", values=(40.0,), unit="rmssd"))
    assert {r.metric_type for r in connector_under_test.normalize(block, CTX)} == {M.HRV_SDNN}
    block = envelope("daily.data.hrv.created", sample_block(provider="oura", values=(40.0,), unit="rmssd"))
    assert {r.metric_type for r in connector_under_test.normalize(block, CTX)} == {M.HRV_RMSSD}


def test_absolute_and_delta_temperature_never_swap():
    whoop = sleep_summary(provider="whoop_v2", skin_temperature=33.4, temperature_delta=None)
    rows = connector_under_test.normalize(envelope("daily.data.sleep.created", whoop), CTX)
    by_metric = {r.metric_type: r for r in rows}
    assert by_metric[M.SKIN_TEMP].value_num == 33.4
    assert M.SKIN_TEMP_DELTA not in by_metric
    oura = connector_under_test.normalize(envelope("daily.data.sleep.created", sleep_summary()), CTX)
    assert M.SKIN_TEMP not in {r.metric_type for r in oura}
    def thermometer(site: str | None, value: float) -> dict:
        sample = {
            "start": f"{YESTERDAY.isoformat()}T15:00:00+00:00",
            "end": f"{YESTERDAY.isoformat()}T15:01:00+00:00",
            "value": value,
            "unit": "°C",
            "timezone_offset": -25200,
        }
        if site is not None:
            sample["sensor_location"] = site
        return envelope(
            "daily.data.body_temperature.created",
            {"source": {"provider": "withings", "type": "unknown"}, "data": [sample]},
        )

    # a wrist (or unsaid) site is the skin series; a core-site thermometer
    # reading would read as a fever against a 33 °C wrist baseline and has no
    # metric of its own yet, so it is skipped and counted
    (row,) = connector_under_test.normalize(thermometer("wrist", 33.6), CTX)
    assert row.metric_type is M.SKIN_TEMP and row.body_site == "wrist"
    (row,) = connector_under_test.normalize(thermometer(None, 33.4), CTX)
    assert row.metric_type is M.SKIN_TEMP and row.body_site is None
    for site in ("temporal_artery", "mouth", "rectum", "ear", "armpit", "forehead"):
        rows, dropped = connector_under_test._normalize_event(thermometer(site, 37.9), CTX)
        assert rows == [] and dropped == 1, site
    delta = envelope("daily.data.body_temperature_delta.created", sample_block(values=(-0.3,), unit="°C"))
    assert {r.metric_type for r in connector_under_test.normalize(delta, CTX)} == {M.SKIN_TEMP_DELTA}


def test_only_the_long_sleep_session_is_the_nights_sleep():
    """A nap, a sub-three-hour short_sleep or an in-progress recording on the
    same calendar day would be averaged with the night by the engine and
    halve it; each is skipped, so a genuinely short night reads as missing
    rather than as a wrong number."""
    for sleep_type in ("acknowledged_nap", "unknown", "short_sleep"):
        rec = sleep_summary(type=sleep_type, total=7200)
        assert connector_under_test.normalize(envelope("daily.data.sleep.created", rec), CTX) == []


def test_workout_becomes_an_exercise_session_in_local_wall_time():
    (row,) = connector_under_test.normalize(
        envelope("daily.data.workouts.created", workout()), CTX
    )
    assert row.metric_type is M.EXERCISE_SESSION
    assert row.value_num == 30.0  # moving_time, not the elapsed 35 minutes
    assert row.granularity is Granularity.SESSION
    # 16:00Z at an offset of -7h is 09:00 on the same calendar day, stored naive
    assert row.start_time == datetime.combine(YESTERDAY, datetime.min.time()).replace(hour=9)
    assert row.start_time.tzinfo is None
    assert row.local_date == YESTERDAY
    assert row.external_id == "wk-1"
    assert row.value_json["sport"] == "walking"
    assert row.source_device_id == "garmin"


def test_point_samples_become_instant_rows_and_totals_are_not_ingested(monkeypatch):
    rows = connector_under_test.normalize(
        envelope("daily.data.blood_oxygen.created", sample_block()), CTX
    )
    assert [r.value_num for r in rows] == [96.0, 96.5, 97.0]
    assert {r.granularity for r in rows} == {Granularity.INSTANT}
    assert {r.metric_type for r in rows} == {M.SPO2}
    assert len({r.dedupe_key for r in rows}) == 3
    # 00:00Z at -7h is the previous evening: the sample sits on that local day
    assert rows[0].local_date == YESTERDAY - timedelta(days=1)
    assert rows[0].start_time.hour == 17
    # intraday step buckets would average against the daily summary — never ingested
    assert connector_under_test.normalize(
        envelope("daily.data.steps.created", interval_block()), CTX
    ) == []
    # heart-rate samples are opt-in
    heart = envelope("daily.data.heartrate.created", sample_block(values=(70.0, 72.0), unit="bpm"))
    assert connector_under_test.normalize(heart, CTX) == []
    monkeypatch.setattr(settings, "junction_ingest_heart_rate_samples", True)
    assert {r.metric_type for r in connector_under_test.normalize(heart, CTX)} == {M.HR_SAMPLE}
    # interval samples keep their interval
    resp = envelope("daily.data.respiratory_rate.created", interval_block(values=(14.0,)))
    (row,) = connector_under_test.normalize(resp, CTX)
    assert row.granularity is Granularity.INTERVAL and row.end_time > row.start_time


def test_sample_identity_survives_the_dst_fall_back_hour_and_offset_changes():
    """01:30 happens twice on the fall-back night. Keyed on wall time the two
    samples would be one row; keyed on the instant they stay two, and the
    same instant restated under a new offset stays one."""
    first = {"timestamp": "2026-11-01T08:30:00+00:00", "value": 96.0, "timezone_offset": -25200}
    second = {"timestamp": "2026-11-01T09:30:00+00:00", "value": 95.0, "timezone_offset": -28800}
    block = {"source": {"provider": "oura"}, "data": [first, second]}
    rows = connector_under_test.normalize(envelope("daily.data.blood_oxygen.created", block), CTX)
    assert [r.start_time.hour for r in rows] == [1, 1]  # both 01:30 on the wall clock
    assert rows[0].dedupe_key != rows[1].dedupe_key
    restated = {"timestamp": "2026-11-01T08:30:00+00:00", "value": 96.5, "timezone_offset": -28800}
    (row,) = connector_under_test.normalize(
        envelope("daily.data.blood_oxygen.updated", {"source": {"provider": "oura"}, "data": [restated]}), CTX
    )
    assert row.dedupe_key == rows[0].dedupe_key


def test_implausible_values_are_dropped_row_by_row():
    """A batch is not refused for one impossible number: refusing would only
    make Junction retry a delivery that can never become acceptable."""
    rec = sleep_summary(average_hrv=999.0)
    rows, dropped = connector_under_test._normalize_event(
        envelope("daily.data.sleep.created", rec), CTX
    )
    assert dropped == 1
    assert M.HRV_RMSSD not in {r.metric_type for r in rows}
    assert M.SLEEP_DURATION in {r.metric_type for r in rows}


def test_manual_entries_are_patient_reported_and_never_billable():
    rows = connector_under_test.normalize(
        envelope("daily.data.activity.created", activity_summary(provider="manual")), CTX
    )
    assert rows and all(r.is_patient_reported and not r.qualifies_for_rtm for r in rows)


def test_normalize_refuses_without_a_resolved_patient_or_a_valid_envelope():
    payload = envelope("daily.data.sleep.created", sleep_summary())
    with pytest.raises(ValueError, match="resolved"):
        connector_under_test.normalize(payload)
    with pytest.raises(ValueError, match="event_type"):
        connector_under_test.normalize({"data": {}}, CTX)
    with pytest.raises(ValueError, match="data object"):
        connector_under_test.normalize({"event_type": "daily.data.sleep.created"}, CTX)
    with pytest.raises(ValueError, match="calendar_date"):
        connector_under_test.normalize(
            envelope("daily.data.sleep.created", {**sleep_summary(), "calendar_date": None, "date": None}), CTX
        )
    assert _split_event("historical.data.sleep.created") == ("historical", "sleep", "created")
    assert _split_event("provider.connection.error") == ("provider", "connection", "error")
    # a resource we do not ingest is silently nothing, not an error
    assert connector_under_test.normalize(envelope("daily.data.glucose.created", {"source": {}, "data": []}), CTX) == []
    assert connector_under_test.normalize(envelope("daily.data.body.created", {"id": "b1", "calendar_date": YESTERDAY.isoformat(), "weight": 80.0, "source": {"provider": "withings"}}), CTX) == []


def test_a_restated_summary_keys_to_the_same_row():
    first = connector_under_test.normalize(envelope("daily.data.sleep.created", sleep_summary()), CTX)
    second = connector_under_test.normalize(
        envelope("daily.data.sleep.updated", sleep_summary(total=21600, updated_at=f"{TODAY.isoformat()}T09:00:00+00:00")), CTX
    )
    keys = lambda rows: {r.metric_type: r.dedupe_key for r in rows}  # noqa: E731
    assert keys(first) == keys(second)
    # two providers reporting the same night stay separate rows
    other = connector_under_test.normalize(
        envelope("daily.data.sleep.created", sleep_summary(id="sleep-2", provider="whoop_v2")), CTX
    )
    assert keys(first)[M.SLEEP_DURATION] != keys(other)[M.SLEEP_DURATION]


# --- resolution ------------------------------------------------------------------


def test_resolve_patient_reads_the_connection_table_and_nothing_else(db, connection):
    connector = junction_connector()
    payload = envelope("daily.data.sleep.created", sleep_summary())
    assert connector.resolve_patient(db, payload) == PATIENT
    # a patient_id in the body is not consulted
    assert connector.resolve_patient(db, {**payload, "patient_id": "marcus"}) == PATIENT
    assert connector.resolve_patient(db, envelope("x.y.z", {}, user_id="user-nobody")) is None
    with pytest.raises(ValueError, match="user_id"):
        connector.resolve_patient(db, {"event_type": "daily.data.sleep.created", "data": {}})
    # the two ids are issued together; a pair that disagrees maps to nobody
    assert connector.resolve_patient(db, envelope("x.y.z", {}, client_user_id="mp_other")) is None
    connection.status = ConnectionStatus.DISCONNECTED
    db.commit()
    assert connector.resolve_patient(db, payload) is None


# --- webhook end to end ----------------------------------------------------------


def test_signed_sleep_delivery_is_ingested_restated_and_replayed(client, db, connection, signing_secret):
    payload = envelope("daily.data.sleep.created", sleep_summary())
    first = post_signed(client, payload)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["accepted"] is True and body["kind"] == "data"
    assert body["ingested"] == 6 and body["skipped_out_of_window"] == 0
    assert len(rows_for(db)) == 6

    replay = post_signed(client, payload).json()
    assert replay["duplicates"] == 6 and replay["ingested"] == 0

    restated = envelope(
        "daily.data.sleep.updated",
        sleep_summary(total=21600, updated_at=f"{TODAY.isoformat()}T09:00:00+00:00"),
    )
    updated = post_signed(client, restated).json()
    assert updated["updated"] >= 1 and updated["ingested"] == 0
    (duration,) = rows_for(db, M.SLEEP_DURATION)
    assert duration.value_num == 6.0 and duration.revision == 1

    db.expire_all()
    device = db.get(Device, f"junction:{USER_ID}:oura")
    assert device is not None and device.source_provider == P.OURA
    assert device.last_sync_at is not None
    conn = db.get(WearableConnection, connection.id)
    assert conn.last_data_at is not None and conn.last_event_at is not None
    assert db.scalar(select(RiskAssessment).where(RiskAssessment.patient_id == PATIENT)) is not None
    event = db.scalars(
        select(WebhookEvent).where(WebhookEvent.provider == "junction").order_by(WebhookEvent.id.desc())
    ).first()
    assert event.status == "processed" and event.signature_valid is True


def test_unsigned_and_missigned_deliveries_are_rejected(client, db, connection, signing_secret):
    payload = envelope("daily.data.sleep.created", sleep_summary())
    assert client.post("/api/webhooks/wearables/junction", json=payload).status_code == 401
    assert post_signed(client, payload, key=b"another-key").status_code == 401
    db.expire_all()
    event = db.scalars(
        select(WebhookEvent).where(WebhookEvent.provider == "junction").order_by(WebhookEvent.id.desc())
    ).first()
    assert event.status == "rejected" and event.signature_valid is False


def test_without_a_secret_every_delivery_is_rejected(client, connection):
    assert settings.junction_webhook_secret == ""
    payload = envelope("daily.data.sleep.created", sleep_summary())
    assert post_signed(client, payload).status_code == 401


def test_delivery_for_an_unmapped_user_is_recorded_and_ignored(client, db, connection, signing_secret):
    before = len(rows_for(db))
    payload = envelope("daily.data.sleep.created", sleep_summary(), user_id="user-nobody", client_user_id="mp_nobody")
    response = post_signed(client, payload)
    assert response.status_code == 202
    assert response.json()["ignored"] is True and response.json()["reason"] == "unmapped_user"
    assert len(rows_for(db)) == before
    db.expire_all()
    event = db.scalars(
        select(WebhookEvent).where(WebhookEvent.provider == "junction").order_by(WebhookEvent.id.desc())
    ).first()
    assert event.status == "ignored"


def test_out_of_window_rows_are_dropped_and_counted(client, db, connection, signing_secret):
    patient = db.get(Patient, PATIENT)
    stale = patient.surgery_date - timedelta(days=MAX_PREOP_BACKFILL_DAYS + 1)
    before = len(rows_for(db))
    response = post_signed(client, envelope("daily.data.sleep.created", sleep_summary(day=stale, id="sleep-old")))
    assert response.status_code == 200
    body = response.json()
    assert body["ingested"] == 0 and body["skipped_out_of_window"] == 6
    assert len(rows_for(db)) == before


def test_malformed_envelope_is_a_422(client, db, connection, signing_secret):
    response = post_signed(client, {"event_type": "daily.data.sleep.created", "user_id": USER_ID})
    assert response.status_code == 422
    response = post_signed(client, {"event_type": "daily.data.sleep.created", "data": {}})
    assert response.status_code == 422  # no user_id: malformed, not merely unknown


def test_connection_events_maintain_devices_and_the_snapshot(client, db, connection, signing_secret):
    created = envelope(
        "provider.connection.created",
        {
            "user_id": USER_ID,
            "provider": {"name": "Garmin", "slug": "garmin", "logo": "https://x/garmin.png"},
            "source": {"name": "Garmin", "slug": "garmin", "logo": "https://x/garmin.png"},
            "external_user_id": "garmin-user-9",
            "resource_availability": {"sleep": {"status": "available", "scope_requirements": None}},
        },
    )
    response = post_signed(client, created)
    assert response.status_code == 200 and response.json()["kind"] == "connection"
    db.expire_all()
    device = db.get(Device, f"junction:{USER_ID}:garmin")
    assert device.source_provider == P.GARMIN and device.device_model == "Garmin via Junction"
    assert device.status == "connected"
    conn = db.get(WearableConnection, connection.id)
    assert conn.status == ConnectionStatus.LINKED
    assert [p["slug"] for p in conn.providers] == ["garmin"]

    errored = envelope(
        "provider.connection.error",
        {
            "provider": "garmin",
            "user_id": USER_ID,
            "message": "The user revoked access",
            "error_type": "token_refresh_failed",
            "error_details": "invalid_grant",
        },
    )
    assert post_signed(client, errored).status_code == 200
    db.expire_all()
    assert db.get(Device, f"junction:{USER_ID}:garmin").status == "error"
    conn = db.get(WearableConnection, connection.id)
    assert conn.status == ConnectionStatus.ERROR
    assert "token_refresh_failed" in conn.last_error
    # a late or replayed reading is not evidence the grant is back
    late = envelope("daily.data.sleep.created", sleep_summary(id="late-garmin", provider="garmin"))
    assert post_signed(client, late).status_code == 200
    db.expire_all()
    device = db.get(Device, f"junction:{USER_ID}:garmin")
    assert device.status == "error" and device.last_sync_at is not None


def test_historical_event_pulls_the_window_through_the_api(client, db, connection, signing_secret, fake):
    patient = db.get(Patient, PATIENT)
    fake.summaries["sleep"] = [
        sleep_summary(day=YESTERDAY - timedelta(days=2), id="hist-1"),
        sleep_summary(day=YESTERDAY - timedelta(days=1), id="hist-2"),
        # inside Junction's window but before ours: dropped, never refused
        sleep_summary(day=patient.surgery_date - timedelta(days=90), id="hist-old"),
    ]
    historical = envelope(
        "historical.data.sleep.created",
        {
            "user_id": USER_ID,
            "start_date": "2020-01-01T00:00:00+00:00",
            "end_date": f"{TODAY.isoformat()}T00:00:00+00:00",
            "is_final": True,
            "provider": "oura",
        },
    )
    response = post_signed(client, historical)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "historical" and body["ingested"] == 12
    assert body["skipped_out_of_window"] == 6
    assert "pulled sleep" in body["note"] and "from oura" in body["note"]
    (call,) = fake.calls("GET", "/v2/summary/sleep/")
    floor = (patient.surgery_date - timedelta(days=MAX_PREOP_BACKFILL_DAYS)).isoformat()
    assert call.url.params["start_date"] == floor  # clamped to the ingestible window
    assert call.url.params["provider"] == "oura"
    db.expire_all()
    conn = db.get(WearableConnection, connection.id)
    assert conn.last_backfill_at is not None


def test_historical_event_without_an_api_key_is_recorded_not_pulled(client, connection, signing_secret):
    assert settings.junction_api_key == ""
    historical = envelope(
        "historical.data.activity.created",
        {"user_id": USER_ID, "start_date": "2026-01-01", "end_date": TODAY.isoformat(), "provider": "oura"},
    )
    body = post_signed(client, historical).json()
    assert body["kind"] == "historical" and body["ingested"] == 0
    assert "JUNCTION_API_KEY" in body["note"]


def test_aggregator_outage_during_a_pull_is_a_502_so_junction_retries(client, db, connection, signing_secret, fake, monkeypatch):
    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={"retry-after": "1"}, json={"detail": "maintenance"})

    connector = junction_connector()
    monkeypatch.setattr(
        connector, "_client_factory",
        lambda: JunctionClient("sk_us_test", SANDBOX, transport=httpx.MockTransport(down), sleep=lambda _s: None),
    )
    historical = envelope(
        "historical.data.sleep.created",
        {"user_id": USER_ID, "start_date": "2026-01-01", "end_date": TODAY.isoformat(), "provider": "oura"},
    )
    response = post_signed(client, historical)
    assert response.status_code == 502
    db.expire_all()
    event = db.scalars(
        select(WebhookEvent).where(WebhookEvent.provider == "junction").order_by(WebhookEvent.id.desc())
    ).first()
    assert event.status == "failed" and "503" in event.error


# --- lifecycle through the API ---------------------------------------------------


def test_link_flow_creates_a_junction_user_once_and_mints_links(client, db, fake):
    db.execute(delete(WearableConnection).where(WearableConnection.patient_id == PATIENT))
    db.commit()
    patient = db.get(Patient, PATIENT)

    first = client.post(f"/api/patients/{PATIENT}/wearables/junction/link")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["link_url"].startswith("https://link.junction.com/")
    assert body["expires_at"] == "2026-09-01T12:00:00Z"
    assert body["connection"]["status"] == "pending_link"
    assert body["connection"]["environment"] == "sandbox"

    (create,) = fake.calls("POST", "/v2/user")
    sent = json.loads(create.content)
    assert sent["client_user_id"].startswith("mp_") and PATIENT not in sent["client_user_id"]
    assert sent["fallback_time_zone"] == "America/Los_Angeles"
    floor = patient.surgery_date - timedelta(days=MAX_PREOP_BACKFILL_DAYS)
    # month-granular on purpose: the exact floor would hand Junction the surgery date
    assert sent["ingestion_start"] == floor.replace(day=1).isoformat()
    assert create.headers["x-vital-api-key"] == "sk_us_test"

    second = client.post(f"/api/patients/{PATIENT}/wearables/junction/link")
    assert second.status_code == 200
    assert len(fake.calls("POST", "/v2/user")) == 1  # the same Junction user is reused
    assert len(fake.calls("POST", "/v2/link/token")) == 2  # tokens are one-time

    view = client.get(f"/api/patients/{PATIENT}/wearables").json()
    assert view["aggregator"]["configured"] is True
    assert view["connection"]["external_user_id"] == USER_ID
    assert view["connection"]["last_link_issued_at"] is not None


def test_a_failed_token_call_does_not_orphan_the_junction_user(client, db, fake, monkeypatch):
    db.execute(delete(WearableConnection).where(WearableConnection.patient_id == PATIENT))
    db.commit()
    connector = junction_connector()
    healthy_factory = connector._client_factory

    def token_down(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/link/token":
            return httpx.Response(500, json={"detail": "link service down"})
        return fake.handle(request)

    monkeypatch.setattr(
        connector, "_client_factory",
        lambda: JunctionClient(
            "sk_us_test", SANDBOX, transport=httpx.MockTransport(token_down), sleep=lambda _s: None
        ),
    )
    assert client.post(f"/api/patients/{PATIENT}/wearables/junction/link").status_code == 502
    db.expire_all()
    conn = connector.connection_for(db, PATIENT)
    assert conn is not None and conn.external_user_id == USER_ID  # the user we made is on file
    assert conn.status == ConnectionStatus.PENDING_LINK

    monkeypatch.setattr(connector, "_client_factory", healthy_factory)
    assert client.post(f"/api/patients/{PATIENT}/wearables/junction/link").status_code == 200
    assert len(fake.calls("POST", "/v2/user")) == 1  # reused, not recreated


def test_a_chunked_backfill_pins_the_baseline_once(db, connection, monkeypatch):
    """Sliced under the ceiling, a back-fill must not let slice two establish
    a pre-op reference from whatever slice one happened to hold."""
    from app.connectors import ingest as ingest_module
    from app.engine import baseline_store

    calls: list[str] = []
    monkeypatch.setattr(
        baseline_store, "ensure_established", lambda db_, pid: calls.append(pid)
    )
    monkeypatch.setattr(ingest_module, "MAX_BATCH_OBSERVATIONS", 2)
    rows = connector_under_test.normalize(
        envelope("daily.data.blood_oxygen.created", sample_block(values=(95.0, 96.0, 97.0, 98.0, 99.0))),
        CTX,
    )
    assert len(rows) == 5
    assert ingest_module.ingest_in_batches(db, rows) == (5, 0, 0)
    assert calls == [PATIENT]  # once for the delivery, not once per slice


def test_link_requires_configuration_and_a_real_patient(client):
    assert settings.junction_api_key == ""
    assert client.post(f"/api/patients/{PATIENT}/wearables/junction/link").status_code == 503
    assert client.get("/api/patients/ghost/wearables").status_code == 404


def test_an_account_from_the_other_environment_is_refused(client, db, fake):
    _reset_connection(db, environment="production")
    assert client.post(f"/api/patients/{PATIENT}/wearables/junction/link").status_code == 409
    assert client.post(f"/api/patients/{PATIENT}/wearables/junction/backfill", json={}).status_code == 409


def test_patient_wearables_refresh_syncs_the_snapshot(client, db, connection, fake):
    fake.providers = [
        {
            "name": "Oura",
            "slug": "oura",
            "logo": "https://x/oura.png",
            "created_on": "2026-08-20T10:00:00+00:00",
            "status": "connected",
            "external_user_id": "oura-77",
            "resource_availability": {},
        }
    ]
    view = client.get(f"/api/patients/{PATIENT}/wearables?refresh=true").json()
    assert view["refresh_error"] is None
    assert view["connection"]["status"] == "linked"
    assert [p["slug"] for p in view["connection"]["providers"]] == ["oura"]
    assert any(d["id"] == f"junction:{USER_ID}:oura" and d["via_junction"] for d in view["devices"])


def test_backfill_pulls_every_resource_ingests_and_reports(client, db, connection, fake):
    fake.summaries = {
        "activity": [activity_summary(day=YESTERDAY - timedelta(days=1), id="bf-act", provider="oura")],
        "sleep": [sleep_summary(day=YESTERDAY - timedelta(days=1), id="bf-sleep")],
        "workouts": [workout(day=YESTERDAY - timedelta(days=1), id="bf-wk", provider="oura")],
        "body": [{"id": "bf-body", "calendar_date": YESTERDAY.isoformat(), "weight": 70.0, "source": {"provider": "oura"}}],
    }
    fake.timeseries = {"blood_oxygen": [sample_block(day=YESTERDAY - timedelta(days=1))]}
    response = client.post(f"/api/patients/{PATIENT}/wearables/junction/backfill", json={"refresh": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True and body["complete"] is True
    assert set(body["resources"]) >= {"activity", "sleep", "workouts", "blood_oxygen", "respiratory_rate", "hrv"}
    assert "heartrate" not in body["resources"]  # opt-in stream, off
    # 3 activity (oura: no daily RHR) + 6 sleep + 1 workout + 3 SpO2 = 13 rows
    assert body["ingested"] == 13
    assert body["dropped_implausible"] == 0
    (refresh_call,) = fake.calls("POST", "/v2/user/refresh/")
    # Junction is told how long to wait for the provider pulls, inside our own deadline
    assert 1.0 <= float(refresh_call.url.params["timeout"]) < 4.0
    assert body["refresh"]["refreshed_sources"] == ["oura"]
    assert body["refresh"]["in_progress_sources"] == ["garmin"]  # not a failure
    for call in fake.calls("GET", "/v2/summary/"):
        assert call.url.params["end_date"] == (TODAY + timedelta(days=1)).isoformat()
    db.expire_all()
    conn = db.get(WearableConnection, connection.id)
    assert conn.last_backfill_at is not None and conn.last_data_at is not None
    assert db.get(Device, f"junction:{USER_ID}:oura").last_sync_at is not None
    # a second pass is all duplicates
    again = client.post(f"/api/patients/{PATIENT}/wearables/junction/backfill", json={}).json()
    assert again["ingested"] == 0 and again["duplicates"] == 13


def test_disconnect_retires_the_mapping_and_late_deliveries_are_ignored(client, db, connection, fake, signing_secret):
    post_signed(client, envelope("daily.data.sleep.created", sleep_summary(id="pre-disconnect")))
    response = client.delete(f"/api/patients/{PATIENT}/wearables/junction")
    assert response.status_code == 200, response.text
    assert response.json()["remote"] == "deleted"
    assert response.json()["connection"]["status"] == "disconnected"
    assert fake.calls("DELETE", f"/v2/user/{USER_ID}")
    db.expire_all()
    assert all(d.status == "revoked" for d in db.get(Patient, PATIENT).devices)
    # history stays; new deliveries for the retired user go nowhere
    assert rows_for(db)
    late = post_signed(client, envelope("daily.data.sleep.created", sleep_summary(id="post-disconnect")))
    assert late.status_code == 202
    assert client.delete(f"/api/patients/{PATIENT}/wearables/junction").status_code == 200  # idempotent
    assert client.delete("/api/patients/marcus/wearables/junction").status_code == 404


def test_integrations_and_status_report_the_aggregator(client, fake, signing_secret):
    body = client.get("/api/integrations").json()
    by_key = {p["key"]: p for p in body["providers"]}
    assert by_key["junction"]["status"] == "live"
    assert by_key["oura"]["status"] == "via_junction" and by_key["oura"]["junction_slug"] == "oura"
    assert by_key["apple"]["status"] == "needs_app"
    assert body["aggregator"]["configured"] is True
    assert body["aggregator"]["webhook_secret_configured"] is True
    assert body["aggregator"]["base_url"] == SANDBOX
    status = client.get("/api/integrations/junction/status?limit=5").json()
    assert status["connections"]["total"] >= 1
    assert isinstance(status["recent_events"], list) and len(status["recent_events"]) <= 5
    assert status["recent_events"][0]["event_type"]
    # No route hands out Junction's pre-authenticated Svix portal link.
    assert client.get("/api/integrations/junction/webhook-portal").status_code == 404
    assert client.post("/api/integrations/oura/connect").status_code == 409
    assert client.post("/api/integrations/junction/connect").json()["status"] == "live"


def test_unverified_bodies_are_bounded_and_never_stored(client, db, connection, signing_secret):
    """Anyone who knows the URL can POST to it. What they send must not fill
    the table, reach the console's recent-deliveries list, or crash the
    verifier."""
    before = db.scalar(select(func.count(WebhookEvent.id)).where(WebhookEvent.provider == "junction"))
    junk = json.dumps({"event_type": "<img src=x>", "user_id": USER_ID, "pad": "x" * 5000}).encode()
    response = client.post(
        "/api/webhooks/wearables/junction", content=junk, headers={"content-type": "application/json"}
    )
    assert response.status_code == 401
    db.expire_all()
    event = db.scalars(
        select(WebhookEvent).where(WebhookEvent.provider == "junction").order_by(WebhookEvent.id.desc())
    ).first()
    assert event.status == "rejected" and event.payload["rejected"] is True
    assert "pad" not in event.payload and event.payload["bytes"] == len(junk)
    assert event.payload["sha256"] == hashlib.sha256(junk).hexdigest()
    recent = client.get("/api/integrations/junction/status?limit=1").json()["recent_events"][0]
    assert recent["status"] == "rejected" and recent["event_type"] is None
    # oversized: refused before anything is verified, parsed or recorded
    huge = b"{" + b" " * 1_000_001 + b"}"
    assert client.post("/api/webhooks/wearables/junction", content=huge).status_code == 413
    after = db.scalar(select(func.count(WebhookEvent.id)).where(WebhookEvent.provider == "junction"))
    assert after == before + 1
    # a hostile byte in the signature header is "does not match", not a 500
    # (the test client refuses to send one, so the verifier is probed directly
    # with the latin-1 text Starlette would hand it)
    from app.api.webhooks import _verify_svix, _verify_terra

    headers = svix_headers(junk)
    headers["svix-signature"] = "v1,\xe9\xff"
    assert _verify_svix(SECRET, headers, junk) is False
    assert _verify_terra("secret", {"terra-signature": f"t={int(time.time())},v1=\xe9"}, junk) is False


def test_disconnect_reports_what_junction_actually_did(client, db, fake):
    """The local mapping is always retired; the remote outcome must be told
    truthfully, because 'retired here, still collecting there' is exactly
    what a consent withdrawal must not hide."""
    _reset_connection(db)

    def gone(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "User not found"})

    connector = junction_connector()
    factory = connector._client_factory
    connector._client_factory = lambda: JunctionClient(
        "sk_us_test", SANDBOX, transport=httpx.MockTransport(gone), sleep=lambda _s: None
    )
    try:
        body = client.delete(f"/api/patients/{PATIENT}/wearables/junction").json()
    finally:
        connector._client_factory = factory
    assert body["remote"] == "not_found"
    assert body["connection"]["status"] == "disconnected"
    assert "not deleted" in body["connection"]["last_error"]

    # a 200 whose body says success=false is not a deletion either
    _reset_connection(db)

    def refused(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False})

    connector._client_factory = lambda: JunctionClient(
        "sk_us_test", SANDBOX, transport=httpx.MockTransport(refused), sleep=lambda _s: None
    )
    try:
        body = client.delete(f"/api/patients/{PATIENT}/wearables/junction").json()
    finally:
        connector._client_factory = factory
    assert body["remote"].startswith("failed") and "success=False" in body["remote"]
    assert "not deleted" in body["connection"]["last_error"]

    # an account on the other host cannot be reached from this deployment
    _reset_connection(db, environment="production")
    body = client.delete(f"/api/patients/{PATIENT}/wearables/junction").json()
    assert body["remote"] == "environment_mismatch"
    assert not fake.calls("DELETE", "/v2/user/")
    assert "production" in body["connection"]["last_error"]


# --- the client ------------------------------------------------------------------


def test_client_backs_off_on_429_and_gives_up_on_a_client_error():
    attempts: list[int] = []
    sleeps: list[float] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(429, headers={"retry-after": "2"}, json={"detail": "slow down"})
        return httpx.Response(200, json={"user_id": USER_ID})

    client = JunctionClient("sk", SANDBOX, transport=httpx.MockTransport(flaky), sleep=sleeps.append)
    assert client.get_user(USER_ID) == {"user_id": USER_ID}
    assert len(attempts) == 3
    assert len(sleeps) == 2 and all(2.0 <= s <= 2.25 for s in sleeps)  # Retry-After, jittered

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bad client_user_id"})

    client = JunctionClient("sk", SANDBOX, transport=httpx.MockTransport(broken), sleep=sleeps.append)
    with pytest.raises(JunctionError) as excinfo:
        client.create_user("x")
    assert excinfo.value.status == 400 and "bad client_user_id" in str(excinfo.value)

    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "User not found"})

    client = JunctionClient("sk", SANDBOX, transport=httpx.MockTransport(missing))
    assert client.resolve_user("nobody") is None
    with pytest.raises(JunctionError):
        client.create_link_token(USER_ID)  # 404 is only tolerated where it means "none"


def test_client_never_starts_an_attempt_past_its_deadline():
    """On Lambda the request holds a 25 s write lock; a call that has run out
    of budget must fail fast rather than open one more 8 s socket."""
    attempts: list[int] = []

    def slow_then_ok(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503, headers={"retry-after": "3"}, json={"detail": "busy"})

    client = JunctionClient("sk", SANDBOX, transport=httpx.MockTransport(slow_then_ok), sleep=lambda _s: None)
    with pytest.raises(JunctionError, match="503"):
        client._request("GET", f"/v2/user/{USER_ID}", deadline_s=1.0)
    assert len(attempts) == 1  # no retry fits inside a 1 s budget
    with pytest.raises(JunctionError, match="already spent"):
        client._request("GET", f"/v2/user/{USER_ID}", deadline_s=0.0)
    assert len(attempts) == 1


def test_client_follows_timeseries_pages_and_flattens_groups():
    pages: list[str | None] = []

    def paged(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        pages.append(cursor)
        if cursor is None:
            return httpx.Response(200, json={"groups": {"oura": [sample_block()], "fitbit": [sample_block(provider="fitbit")]}, "next_cursor": "page-2"})
        return httpx.Response(200, json={"groups": {"oura": [sample_block(values=(95.0,))]}, "next_cursor": None})

    client = JunctionClient("sk", SANDBOX, transport=httpx.MockTransport(paged))
    blocks = client.timeseries_grouped("blood_oxygen", USER_ID, YESTERDAY, TODAY)
    assert pages == [None, "page-2"]
    assert [b["source"]["provider"] for b in blocks] == ["oura", "fitbit", "oura"]


def test_hosts_and_configuration():
    assert base_url_for("sandbox", "us") == SANDBOX
    assert base_url_for("production", "eu") == "https://api.eu.junction.com"
    assert base_url_for("Production", "US") == "https://api.us.junction.com"
    with pytest.raises(JunctionError):
        base_url_for("staging", "us")
    assert settings.junction_api_key == ""
    with pytest.raises(JunctionNotConfigured):
        JunctionClient.from_settings()
    with pytest.raises(JunctionNotConfigured):
        JunctionClient("", SANDBOX)
    assert BRAND_BY_SLUG["whoop_v2"] is P.WHOOP and BRAND_BY_SLUG["apple_health_kit"] is P.APPLE
