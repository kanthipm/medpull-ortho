import base64
import hashlib
import hmac
import inspect
import time
from datetime import date, datetime

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models.adherence import AdherenceTask
from app.models.enums import (
    GUARDRAIL_SENTENCE,
    CareRole,
    InsightKind,
    InteractionKind,
    MetricType,
    NotificationChannel,
    NotificationStatus,
    SourceProvider,
)
from app.models.insight import Insight
from app.models.notification import Notification, NotificationPreference
from app.models.observation import Observation, WebhookEvent
from app.models.patient import CareTeamMember, Device
from app.models.rtm import ProviderTimeLog, RtmDocument, RtmInteraction


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["db_ok"] is True
    assert body["llm_provider"] == "fallback"


def test_worklist_shape_and_ordering(client):
    body = client.get("/api/worklist").json()
    assert body["stats"]["total"] == 10
    assert body["briefing"]["text"]
    priorities = [p["priority"] for p in body["patients"]]
    order = {"high": 0, "medium": 1, "missing_data": 2, "low": 3}
    assert priorities == sorted(priorities, key=lambda p: order[p])
    assert body["patients"][0]["id"] == "marcus"
    row = body["patients"][0]
    for field in ("reason", "postop_day", "assigned_provider", "data_confidence", "trajectory"):
        assert field in row


def test_patient_detail(client):
    body = client.get("/api/patients/marcus").json()
    assert body["risk"]["level"] == "high"
    assert body["summary"]["text"].strip()
    assert 1 <= len(body["actions"]) <= 4
    assert body["rtm"]["window_days"] == 30
    assert body["device"]["provider"] == "apple"


def test_patient_404(client):
    assert client.get("/api/patients/nobody").status_code == 404


def test_metrics_endpoint(client):
    body = client.get("/api/patients/marcus/metrics").json()
    assert body["composite"]["level"] == "high"
    keys = {m["metric_key"] for m in body["metrics"]}
    assert "walking_asymmetry_pct" in keys  # apple patient gets gait cards
    body2 = client.get("/api/patients/linda/metrics").json()
    keys2 = {m["metric_key"] for m in body2["metrics"]}
    assert "walking_asymmetry_pct" not in keys2  # fitbit patient: no gait card


def test_timeline(client):
    events = client.get("/api/patients/marcus/timeline").json()["events"]
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "surgery"
    assert kinds[-1] == "today"
    assert "change_point" in kinds


def test_checkins_newest_first(client):
    checkins = client.get("/api/patients/marcus/checkins").json()["checkins"]
    times = [c["occurred_at"] for c in checkins]
    assert times == sorted(times, reverse=True)
    assert checkins[0]["messages"][0]["who"] in ("patient", "copilot")


def test_observations_series(client):
    body = client.get("/api/patients/marcus/observations?metric_type=steps&days=30").json()
    assert body["unit"] == "count"
    assert len(body["points"]) > 10
    assert client.get("/api/patients/marcus/observations?metric_type=zzz").status_code == 400


def test_integrations(client):
    providers = client.get("/api/integrations").json()["providers"]
    assert len(providers) == 10
    by_key = {p["key"]: p for p in providers}
    assert by_key["mock"]["status"] == "mock_connected"
    assert by_key["apple"]["gait_capable"] is True
    assert by_key["fitbit"]["gait_capable"] is False
    assert client.post("/api/integrations/fitbit/connect").status_code == 501
    assert client.post("/api/integrations/nope/connect").status_code == 404


def test_webhook_flow(client):
    payload = {
        "patient_id": "elena",
        "provider": "apple",
        "records": [
            {"metric_type": "steps", "date": date.today().isoformat(), "value": 11000.0,
             "unit": "count"}
        ],
    }
    first = client.post("/api/webhooks/wearables/mock", json=payload).json()
    assert first["accepted"] is True
    replay = client.post("/api/webhooks/wearables/mock", json=payload).json()
    assert replay["duplicates"] >= 1
    assert client.post("/api/webhooks/wearables/nope", json={}).status_code == 404
    assert client.post("/api/webhooks/wearables/garmin", json={}).status_code == 501
    assert client.post("/api/webhooks/wearables/mock", json={"bad": 1}).status_code == 422


def test_notifications_flow(client):
    notifications = client.get("/api/notifications?status=all").json()["notifications"]
    assert any(n["kind"] == "priority_high" and n["patient_id"] == "marcus" for n in notifications)
    target = notifications[0]
    assert client.post(f"/api/notifications/{target['id']}/read").json()["ok"] is True
    assert client.post("/api/notifications/read-all").json()["ok"] is True


def test_notification_preferences_roundtrip(client):
    prefs = client.get("/api/notification-preferences").json()
    channels = {p["channel"]: p for p in prefs}
    assert channels["in_app"]["available"] is True
    assert channels["sms"]["available"] is False
    updated = client.put(
        "/api/notification-preferences",
        json=[{"channel": "in_app", "enabled": False, "min_priority": "high"}],
    ).json()
    assert {p["channel"]: p for p in updated}["in_app"]["enabled"] is False
    client.put(
        "/api/notification-preferences",
        json=[{"channel": "in_app", "enabled": True, "min_priority": "high"}],
    )


def test_recompute(client):
    body = client.post("/api/patients/sofia/recompute").json()
    assert body["risk_level"] == "medium"


# --- notification preferences ------------------------------------------------

def test_notification_preferences_upsert_scoped_to_one_recipient(client, db):
    """Preferences are stored per care-team member. A recipient with no row yet
    is the ordinary case (anyone added after the seed), so the PUT has to create
    one — and it must leave everybody else's row alone."""
    db.add(CareTeamMember(id="ct_newcomer", name="Dana Reed, RN", role=CareRole.NURSE))
    db.commit()
    try:
        updated = client.put(
            "/api/notification-preferences?recipient_id=ct_newcomer",
            json=[{"channel": "in_app", "enabled": False, "min_priority": "medium"}],
        ).json()
        assert {p["channel"]: p for p in updated}["in_app"]["enabled"] is False

        db.expire_all()
        created = db.scalars(
            select(NotificationPreference).where(
                NotificationPreference.recipient_id == "ct_newcomer"
            )
        ).all()
        assert [(p.channel, p.enabled, p.min_priority) for p in created] == [
            (NotificationChannel.IN_APP, False, "medium")
        ]
        untouched = db.scalars(
            select(NotificationPreference).where(
                NotificationPreference.recipient_id == "ct_alvarez",
                NotificationPreference.channel == NotificationChannel.IN_APP,
            )
        ).all()
        assert untouched and all(p.enabled for p in untouched)
    finally:
        for row in db.scalars(
            select(NotificationPreference).where(
                NotificationPreference.recipient_id == "ct_newcomer"
            )
        ).all():
            db.delete(row)
        db.delete(db.get(CareTeamMember, "ct_newcomer"))
        db.commit()


def test_notification_preferences_refuse_an_undeliverable_channel(client):
    """SMS and email are stubs: enabling one writes `sent_stub` rows the bell
    never lists, so the toggle would promise a delivery that cannot happen.
    Turning one off stays legal — that is the safe direction."""
    assert (
        client.put(
            "/api/notification-preferences",
            json=[{"channel": "sms", "enabled": True, "min_priority": "high"}],
        ).status_code
        == 422
    )
    channels = {p["channel"]: p for p in client.get("/api/notification-preferences").json()}
    assert channels["sms"]["enabled"] is False
    assert (
        client.put(
            "/api/notification-preferences",
            json=[{"channel": "sms", "enabled": False, "min_priority": "high"}],
        ).status_code
        == 200
    )


def test_notification_preferences_reject_before_writing_anything(client):
    """A batch is one transaction: an undeliverable channel anywhere in the list
    must not leave the valid entries applied."""
    assert (
        client.put(
            "/api/notification-preferences",
            json=[
                {"channel": "in_app", "enabled": False, "min_priority": "high"},
                {"channel": "email", "enabled": True, "min_priority": "high"},
            ],
        ).status_code
        == 422
    )
    channels = {p["channel"]: p for p in client.get("/api/notification-preferences").json()}
    assert channels["in_app"]["enabled"] is True


def test_read_all_only_clears_the_channel_the_bell_lists(client, db):
    """`read-all` clears the bell, and the bell lists IN_APP only. Marking an
    out-of-band row read retires an alert nobody was ever shown."""
    out_of_band = Notification(
        patient_id="marcus",
        recipient_id="ct_alvarez",
        kind="priority_high",
        title="Marcus Reyes — high recovery priority",
        body="Resting heart rate rising. Review at /patients/marcus.",
        channel=NotificationChannel.SMS,
        status=NotificationStatus.UNREAD,
    )
    db.add(out_of_band)
    db.commit()
    row_id = out_of_band.id
    try:
        body = client.post("/api/notifications/read-all").json()
        assert body["ok"] is True
        db.expire_all()
        assert db.get(Notification, row_id).status == NotificationStatus.UNREAD
        listed = client.get("/api/notifications?status=all").json()["notifications"]
        assert row_id not in [n["id"] for n in listed]
    finally:
        db.delete(db.get(Notification, row_id))
        db.commit()


# --- tombstones, caches, ordering --------------------------------------------

def test_observations_exclude_provider_tombstones(client, db):
    """connectors/ingest promises every reader filters `deleted_at`; a deleted
    day must leave the chart instead of lingering as a stale point."""
    row = db.scalars(
        select(Observation)
        .where(
            Observation.patient_id == "marcus",
            Observation.metric_type == MetricType.STEPS,
            Observation.deleted_at.is_(None),
        )
        .order_by(Observation.start_time.desc())
        .limit(1)
    ).first()
    stamp = row.start_time.isoformat()
    row.deleted_at = datetime.now()
    db.commit()
    try:
        points = client.get(
            "/api/patients/marcus/observations?metric_type=steps&days=30"
        ).json()["points"]
        assert stamp not in [p["t"] for p in points]
    finally:
        row.deleted_at = None
        db.commit()


def test_recompute_busts_the_briefing_but_not_the_ask_cache(client, db):
    """Recompute is per patient. The roster briefing embeds this patient's
    reason so it has to go; the roster Q&A cache is keyed on questions this
    patient's numbers do not appear in, and rebuilding it costs an LLM call
    per cached question."""
    briefing = Insight(
        patient_id=None,
        kind=InsightKind.DAILY_BRIEFING,
        content={"text": "seeded briefing"},
        input_hash="test-briefing-hash",
        llm_provider="fallback",
    )
    ask = Insight(
        patient_id=None,
        kind=InsightKind.ASK,
        content={"answer": "seeded answer"},
        input_hash="test-ask-hash",
        llm_provider="fallback",
    )
    db.add_all([briefing, ask])
    db.commit()
    briefing_id, ask_id = briefing.id, ask.id
    try:
        response = client.post("/api/patients/sofia/recompute")
        assert response.status_code == 200
        db.expire_all()
        assert db.get(Insight, briefing_id) is None
        assert db.get(Insight, ask_id) is not None
        assert (
            db.scalars(
                select(Insight).where(Insight.patient_id == "sofia")
            ).all()
            == []
        )
    finally:
        stale = db.get(Insight, ask_id)
        if stale is not None:
            db.delete(stale)
        db.commit()


def test_patient_device_is_the_most_recently_connected(client, db):
    """A patient who upgrades a watch keeps both rows; the detail card must name
    the current device rather than whichever row happened to be written first."""
    extra = Device(
        id="dev_linda_upgrade",
        patient_id="linda",
        source_provider=SourceProvider.GARMIN,
        device_model="Garmin Venu 4",
        connected_at=datetime.now(),
        last_sync_at=None,
    )
    db.add(extra)
    db.commit()
    try:
        device = client.get("/api/patients/linda").json()["device"]
        assert device["provider"] == "garmin"
        assert device["model"] == "Garmin Venu 4"
    finally:
        db.delete(db.get(Device, "dev_linda_upgrade"))
        db.commit()


# --- patient actions ---------------------------------------------------------

@pytest.fixture()
def action_ledger(db):
    """Every action logs an interaction and billable provider time as a side
    effect, and the seeded database is session-scoped with no rollback. The RTM
    stages pinned in test_rtm.py read those same tables, so an action test has
    to take its rows back out."""
    tracked = (ProviderTimeLog, RtmInteraction, AdherenceTask, Notification, RtmDocument)
    high_water = {model: (db.scalar(select(func.max(model.id))) or 0) for model in tracked}
    yield
    db.expire_all()
    for model, mark in high_water.items():
        for row in db.scalars(select(model).where(model.id > mark)).all():
            db.delete(row)
    db.commit()



def test_assign_task_is_recorded_but_untracked(client, db, action_ledger):
    """The task row exists and the time is billable, but nothing reads it back:
    compute_adherence reads AdherenceRecord only and there is no completion
    endpoint. The response says so rather than implying tracking."""
    body = client.post(
        "/api/patients/grace/actions/assign-task",
        json={"title": "Walk 10 minutes twice daily", "why": "Rebuild gait tolerance"},
    ).json()
    assert body["ok"] is True
    assert body["status"] == "assigned_untracked"
    assert body["task"]["title"] == "Walk 10 minutes twice daily"

    db.expire_all()
    task = db.get(AdherenceTask, body["task"]["id"])
    assert task.patient_id == "grace" and task.why == "Rebuild gait tolerance"
    logged = db.scalars(
        select(RtmInteraction)
        .where(
            RtmInteraction.patient_id == "grace",
            RtmInteraction.kind == InteractionKind.ASSIGN_TASK,
        )
        .order_by(RtmInteraction.id.desc())
        .limit(1)
    ).first()
    assert logged is not None and "Walk 10 minutes twice daily" in logged.detail
    assert client.post(
        "/api/patients/grace/actions/assign-task", json={"title": "   "}
    ).status_code == 422


def test_message_is_a_queued_stub(client, db, action_ledger):
    body = client.post(
        "/api/patients/grace/actions/message",
        json={"text": "Checking in — how is the hip feeling today?"},
    ).json()
    assert body == {"status": "queued_stub"}
    db.expire_all()
    logged = db.scalars(
        select(RtmInteraction)
        .where(
            RtmInteraction.patient_id == "grace",
            RtmInteraction.kind == InteractionKind.MESSAGE,
        )
        .order_by(RtmInteraction.id.desc())
        .limit(1)
    ).first()
    assert logged is not None and "Message queued" in logged.detail
    assert client.post(
        "/api/patients/grace/actions/message", json={"text": " "}
    ).status_code == 422


def test_escalate_notifies_the_assigned_provider(client, db, action_ledger):
    assert client.post("/api/patients/grace/actions/escalate").json()["ok"] is True
    db.expire_all()
    notification = db.scalars(
        select(Notification)
        .where(Notification.patient_id == "grace", Notification.kind == "escalation")
        .order_by(Notification.id.desc())
        .limit(1)
    ).first()
    assert notification is not None
    assert notification.recipient_id == "ct_alvarez"
    assert notification.channel == NotificationChannel.IN_APP
    assert notification.status == NotificationStatus.UNREAD
    listed = client.get("/api/notifications?status=unread").json()["notifications"]
    assert notification.id in [n["id"] for n in listed]


def test_update_plan_logs_chart_review(client, db, action_ledger):
    assert client.post(
        "/api/patients/grace/actions/update-plan",
        json={"summary": "Hold HEP progression until swelling settles"},
    ).json()["ok"] is True
    db.expire_all()
    logged = db.scalars(
        select(RtmInteraction)
        .where(
            RtmInteraction.patient_id == "grace",
            RtmInteraction.kind == InteractionKind.UPDATE_PLAN,
        )
        .order_by(RtmInteraction.id.desc())
        .limit(1)
    ).first()
    assert logged is not None and "swelling" in logged.detail
    assert client.post(
        "/api/patients/grace/actions/update-plan", json={"summary": "  "}
    ).status_code == 422


def test_regenerate_replaces_a_draft_in_place(client, action_ledger):
    """The happy path: a draft regenerates to a fresh, guarded body under the
    same document id, and stays a draft."""
    docs = client.get("/api/patients/aisha/rtm/documents").json()["documents"]
    note = next(d for d in docs if d["kind"] == "encounter_note")
    assert note["status"] == "draft"
    fresh = client.post(
        f"/api/patients/aisha/rtm/documents/{note['id']}/regenerate"
    ).json()
    assert fresh["ok"] is True
    assert fresh["document"]["id"] == note["id"]
    assert fresh["document"]["status"] == "draft"
    assert fresh["document"]["body"].endswith(GUARDRAIL_SENTENCE)
    after = client.get("/api/patients/aisha/rtm/documents").json()["documents"]
    assert [d["id"] for d in after] == [d["id"] for d in docs]


# --- webhook signature verification ------------------------------------------

_SVIX_KEY = b"junction-signing-key-bytes"
_SVIX_SECRET = "whsec_" + base64.b64encode(_SVIX_KEY).decode()
_TERRA_SECRET = "terra-signing-secret"
_BODY = b'{"patient_id":"elena","records":[]}'


def _svix_headers(body: bytes = _BODY, timestamp: int | None = None) -> dict[str, str]:
    msg_id = "msg_2abcDEF"
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    signed = f"{msg_id}.{stamp}.".encode() + body
    digest = hmac.new(_SVIX_KEY, signed, hashlib.sha256).digest()
    return {
        "svix-id": msg_id,
        "svix-timestamp": stamp,
        "svix-signature": "v1," + base64.b64encode(digest).decode(),
    }


def _terra_headers(body: bytes = _BODY, timestamp: int | None = None) -> dict[str, str]:
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    signed = f"{stamp}.".encode() + body
    digest = hmac.new(_TERRA_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return {"terra-signature": f"t={stamp},v1={digest}"}


def test_verify_svix_accepts_only_a_matching_signature():
    from app.api.webhooks import SKEW_TOLERANCE_S, _verify_svix

    assert _verify_svix(_SVIX_SECRET, _svix_headers(), _BODY) is True
    # rotation: several candidates, one of them current
    rotated = _svix_headers()
    rotated["svix-signature"] = "v1,bm90LXRoZS1zaWduYXR1cmU= " + rotated["svix-signature"]
    assert _verify_svix(_SVIX_SECRET, rotated, _BODY) is True
    # the signature is over the raw bytes, so any edit invalidates it
    assert _verify_svix(_SVIX_SECRET, _svix_headers(), _BODY + b" ") is False
    # a downgraded version prefix is not a v1 candidate
    downgraded = _svix_headers()
    downgraded["svix-signature"] = downgraded["svix-signature"].replace("v1,", "v0,")
    assert _verify_svix(_SVIX_SECRET, downgraded, _BODY) is False
    # replay outside the skew window
    stale = _svix_headers(timestamp=int(time.time()) - SKEW_TOLERANCE_S - 1)
    assert _verify_svix(_SVIX_SECRET, stale, _BODY) is False
    # unparseable timestamp, unparseable secret, missing headers
    broken = _svix_headers()
    broken["svix-timestamp"] = "not-a-timestamp"
    assert _verify_svix(_SVIX_SECRET, broken, _BODY) is False
    assert _verify_svix("whsec_abcde", _svix_headers(), _BODY) is False
    for header in ("svix-id", "svix-timestamp", "svix-signature"):
        incomplete = _svix_headers()
        del incomplete[header]
        assert _verify_svix(_SVIX_SECRET, incomplete, _BODY) is False


def test_verify_terra_accepts_only_a_matching_signature():
    from app.api.webhooks import SKEW_TOLERANCE_S, _verify_terra

    assert _verify_terra(_TERRA_SECRET, _terra_headers(), _BODY) is True
    # rotation: any v1 value may match
    rotated = _terra_headers()
    stamp = rotated["terra-signature"].split(",")[0]
    rotated["terra-signature"] = (
        f"{stamp},v1=deadbeef," + rotated["terra-signature"].split(",", 1)[1]
    )
    assert _verify_terra(_TERRA_SECRET, rotated, _BODY) is True
    assert _verify_terra(_TERRA_SECRET, _terra_headers(), _BODY + b" ") is False
    assert _verify_terra("wrong-secret", _terra_headers(), _BODY) is False
    # a v0 value carrying the right digest must not be honoured
    downgraded = _terra_headers()
    downgraded["terra-signature"] = downgraded["terra-signature"].replace("v1=", "v0=")
    assert _verify_terra(_TERRA_SECRET, downgraded, _BODY) is False
    stale = _terra_headers(timestamp=int(time.time()) - SKEW_TOLERANCE_S - 1)
    assert _verify_terra(_TERRA_SECRET, stale, _BODY) is False
    assert _verify_terra(_TERRA_SECRET, {}, _BODY) is False
    assert _verify_terra(_TERRA_SECRET, {"terra-signature": "v1=deadbeef"}, _BODY) is False


def test_verify_signature_fails_closed(monkeypatch):
    """Two rejection branches, both silent from the caller's side: a provider
    with no scheme at all, and a scheme whose secret was never configured."""
    from app.api.webhooks import verify_signature

    assert verify_signature(SourceProvider.APPLE, _svix_headers(), _BODY) is False
    assert settings.junction_webhook_secret == ""
    assert settings.terra_signing_secret == ""
    assert verify_signature(SourceProvider.JUNCTION, _svix_headers(), _BODY) is False
    assert verify_signature(SourceProvider.TERRA, _terra_headers(), _BODY) is False
    # the same deliveries verify once the secrets exist, so the rejections above
    # were the missing secret and not a bad signature
    monkeypatch.setattr(settings, "junction_webhook_secret", _SVIX_SECRET)
    monkeypatch.setattr(settings, "terra_signing_secret", _TERRA_SECRET)
    assert verify_signature(SourceProvider.JUNCTION, _svix_headers(), _BODY) is True
    assert verify_signature(SourceProvider.TERRA, _terra_headers(), _BODY) is True
    # the demo path declares it needs no secret
    assert verify_signature(SourceProvider.MOCK, {}, b"{}") is True


def test_webhook_rejects_an_unverified_delivery(client, db, monkeypatch):
    """The 401 path is unreachable over HTTP today — mock's verifier is a
    constant True and no aggregator is in the registry — so stand a failing
    scheme in mock's place to exercise it."""
    from app.api import webhooks

    monkeypatch.setitem(
        webhooks.SIGNATURE_SCHEMES,
        SourceProvider.MOCK,
        webhooks.SignatureScheme(
            lambda secret, headers, body: False, lambda: "", requires_secret=False
        ),
    )
    payload = {
        "patient_id": "elena",
        "provider": "apple",
        "records": [
            {"metric_type": "steps", "date": date.today().isoformat(), "value": 12345.0,
             "unit": "count"}
        ],
    }
    assert client.post("/api/webhooks/wearables/mock", json=payload).status_code == 401

    db.expire_all()
    event = db.scalars(
        select(WebhookEvent)
        .where(WebhookEvent.provider == "mock")
        .order_by(WebhookEvent.id.desc())
        .limit(1)
    ).first()
    assert event.signature_valid is False
    assert event.status == "rejected"
    assert event.error == "signature verification failed"
    # rejected before a single observation row was written
    points = client.get(
        "/api/patients/elena/observations?metric_type=steps&days=2"
    ).json()["points"]
    assert 12345.0 not in [p["v"] for p in points]


# --- wiring ------------------------------------------------------------------

def _api_endpoints():
    """Every handler under /api. FastAPI keeps an included router as a single
    nested node, so the tree has to be walked rather than listed."""
    from app.api import api_router

    pending = list(api_router.routes)
    while pending:
        route = pending.pop()
        nested = getattr(route, "original_router", None)
        if nested is not None:
            pending.extend(nested.routes)
        elif hasattr(route, "endpoint"):
            yield route


def test_every_router_is_wired(client):
    """A router dropped at import time used to fall through to the SPA
    catch-all as 200 text/html with no log line, so its absence has to be an
    assertion rather than a silent 'route not found'."""
    from app.main import app

    paths = set(app.openapi()["paths"])
    for path in (
        "/api/health",
        "/api/worklist",
        "/api/patients/{patient_id}",
        "/api/notifications",
        "/api/notification-preferences",
        "/api/integrations",
        "/api/webhooks/wearables/{provider}",
        "/api/ask",
        "/api/patients/{patient_id}/rtm",
    ):
        assert path in paths


def test_every_api_route_runs_on_the_threadpool():
    """The engine, SQLAlchemy and the connectors are all synchronous. FastAPI
    only moves plain `def` handlers off the event loop, so one `async def`
    route blocks every concurrent request for the length of its pipeline."""
    coroutine_routes = [
        route.name
        for route in _api_endpoints()
        if inspect.iscoroutinefunction(route.endpoint)
    ]
    assert coroutine_routes == []


def test_monitoring_window_is_unique_per_patient_and_window(db):
    """coverage.update_window() selects then inserts. Without the constraint a
    second writer that missed the select inserts a twin, and get_current()
    serves whichever copy won the id race."""
    from sqlalchemy.exc import IntegrityError

    from app.models.rtm import MonitoringWindow

    existing = db.scalars(
        select(MonitoringWindow).where(MonitoringWindow.patient_id == "marcus").limit(1)
    ).first()
    assert existing is not None
    db.add(
        MonitoringWindow(
            patient_id=existing.patient_id,
            window_start=existing.window_start,
            window_end=existing.window_end,
            days_with_data=existing.days_with_data,
            qualifies_16_of_30=existing.qualifies_16_of_30,
        )
    )
    try:
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()


def test_disabling_every_channel_silences_the_notification(db):
    """The settings screen lets a provider switch every channel off. The
    notifier used to read only the *enabled* rows and fall back to in-app on an
    empty result, which made "turned everything off" indistinguishable from
    "never set anything" — so the one channel the provider had just disabled
    was the one they kept getting.

    Puts the seeded preferences and the notification table back on the way out:
    every other test in the suite reads this roster.
    """
    from app.models.insight import RiskAssessment
    from app.models.patient import Patient
    from app.notifications.service import notify_high_priority

    patient = db.get(Patient, "marcus")
    recipient = patient.assigned_provider_id
    prefs = db.scalars(
        select(NotificationPreference).where(
            NotificationPreference.recipient_id == recipient
        )
    ).all()
    assert prefs, "the seed gives every care-team member a full preference set"
    was = {p.channel: p.enabled for p in prefs}
    assessment = db.scalar(
        select(RiskAssessment)
        .where(RiskAssessment.patient_id == "marcus")
        .order_by(RiskAssessment.computed_at.desc())
        .limit(1)
    )

    def _ids() -> set[int]:
        return set(
            db.scalars(
                select(Notification.id).where(Notification.patient_id == "marcus")
            ).all()
        )

    before = _ids()
    try:
        for p in prefs:
            p.enabled = False
        db.commit()
        notify_high_priority(db, patient, assessment)
        db.commit()
        assert _ids() == before, "a provider who silenced every channel still got notified"

        # The fallback still protects a recipient who never set preferences.
        for p in prefs:
            db.delete(p)
        db.commit()
        notify_high_priority(db, patient, assessment)
        db.commit()
        assert len(_ids()) == len(before) + 1
    finally:
        for created in _ids() - before:
            db.delete(db.get(Notification, created))
        for channel, enabled in was.items():
            row = db.scalar(
                select(NotificationPreference).where(
                    NotificationPreference.recipient_id == recipient,
                    NotificationPreference.channel == channel,
                )
            )
            if row is None:
                db.add(
                    NotificationPreference(
                        recipient_id=recipient, channel=channel, enabled=enabled
                    )
                )
            else:
                row.enabled = enabled
        db.commit()
