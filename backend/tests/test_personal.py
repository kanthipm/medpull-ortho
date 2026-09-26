"""The personal tier: joining, the paywall, the readouts, the plan, the
coach, pairing with a clinic chart, the console's blindness to subscribers,
and the storage prefix. Every account created here is removed afterwards
so the session-scoped seeded database is the roster again."""

from __future__ import annotations

import base64
import json
import math
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import delete, select

from app.config import settings
from app.connectors.base import CanonicalObservation
from app.connectors.ingest import ingest_observations
from app.models.enums import Granularity
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider
from app.models.mobile import Message
from app.models.patient import Patient
from app.models.personal import Entitlement, PersonalLog, PersonalProfile
from app.personal import metrics
from app.personal.data import PersonalData
from tests.test_mobile import _forget_patient

PHONE = "+15125559001"


def _forget(db, patient_id: str) -> None:
    from app.models.personal import Consent, PersonalCredential

    for model in (PersonalLog, Entitlement, PersonalProfile, Consent, PersonalCredential):
        db.execute(delete(model).where(model.patient_id == patient_id))
    db.commit()
    _forget_patient(db, patient_id)


EMAIL = "ada@example.com"
PASSWORD = "run-fast-sleep-well"


def _consent(research: bool = True) -> dict:
    from app.personal.auth import CONSENT_VERSION

    return {"version": CONSENT_VERSION, "signature": "Ada Runner",
            "scopes": {"beta_ack": True, "data_storage": True, "ai_processing": True,
                       "research_use": research}}


def _join(client, phone=PHONE, goal="performance", email=EMAIL, **extra):
    body = {"name": "Ada Runner", "email": email, "password": PASSWORD, "consent": _consent(),
            "phone": phone, "goal": goal, "sport": "running",
            "weekly_target_minutes": 240, "device_name": "iPhone (test)", **extra}
    resp = client.post("/api/mobile/personal/join", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "enrolled"
    return {"Authorization": f"Bearer {data['session_token']}"}, data


def _seed_stream(db, patient_id: str, days: int = 40, *, hrv_dip_last: bool = False) -> None:
    """A plausible athlete's month: steady HRV and RHR with day-to-day noise,
    seven-hour nights, a training load with a hard weekend."""
    rng = np.random.default_rng(7)
    today = date.today()
    rows = []
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        hrv = 62 + rng.normal(0, 5)
        rhr = 52 + rng.normal(0, 1.5)
        if hrv_dip_last and i <= 2:
            hrv -= 22
            rhr += 7
        sleep = 7.2 + rng.normal(0, 0.5)
        energy = 500 + rng.normal(0, 80) + (400 if d.weekday() in (5, 6) else 0)
        stages = {"deep": round(sleep * 0.2, 2), "rem": round(sleep * 0.22, 2),
                  "light": round(sleep * 0.5, 2), "awake": round(sleep * 0.08, 2),
                  "bedtime_start": datetime.combine(d - timedelta(days=1), time(22, 40)).isoformat(),
                  "bedtime_stop": datetime.combine(d, time(6, 30)).isoformat()}
        for metric, value, unit, vjson in (
            (M.HRV_RMSSD, hrv, "ms", None), (M.RESTING_HR, rhr, "bpm", None),
            (M.SLEEP_DURATION, sleep, "h", None), (M.SLEEP_STAGES, sleep, "h", stages),
            (M.ACTIVE_ENERGY, energy, "kcal", None), (M.STEPS, 8000 + rng.normal(0, 1500), "count", None),
            (M.RESPIRATORY_RATE, 14.5 + rng.normal(0, 0.4), "br/min", None),
        ):
            rows.append(CanonicalObservation(
                patient_id=patient_id, source_provider=SourceProvider.APPLE, metric_type=metric,
                unit=unit, value_num=round(float(value), 2), value_json=vjson,
                start_time=datetime.combine(d, time(0, 0)),
                end_time=datetime.combine(d, time(23, 59, 59)),
                granularity=Granularity.DAILY_SUMMARY, source_device_id="apple_health:test",
            ))
    ingest_observations(db, rows)


# --- joining and the paywall ---------------------------------------------------------------


def test_personal_join_creates_a_space_off_every_roster(client, db):
    headers, data = _join(client)
    me = data["me"]
    pid = me["patient"]["id"]
    try:
        assert me["patient"]["mode"] == "personal"
        assert me["patient"]["account_kind"] == "personal"
        assert me["patient"]["hospital"] is None
        assert me["patient"]["care_team"] == []
        assert me["subscription"]["state"] == "trial"
        assert me["subscription"]["days_left"] >= settings.personal_trial_days - 1
        assert [p["kind"] for p in me["profiles"]] == ["personal"]
        db.expire_all()
        row = db.get(Patient, pid)
        assert row.account_kind == "personal" and row.hospital_id is None
        assert db.get(PersonalProfile, pid).goal == "performance"
        # Invisible to the console.
        worklist = client.get("/api/worklist").json()
        assert pid not in {r["id"] for r in worklist["patients"]}
        for hospital in client.get("/api/mobile/hospitals").json()["hospitals"]:
            found = client.post("/api/mobile/patients/search",
                                json={"hospital_id": hospital["id"], "name": "Ada Runner"}).json()
            assert found["candidates"] == []
        # The profile round-trips.
        prof = client.get("/api/mobile/personal/profile", headers=headers).json()
        assert prof["profile"]["sport"] == "running"
        patched = client.patch("/api/mobile/personal/profile", headers=headers,
                               json={"sleep_target_hours": 8}).json()
        assert patched["profile"]["sleep_target_hours"] == 8
    finally:
        _forget(db, pid)


def test_personal_join_refuses_a_bad_goal_and_a_taken_number(client, db):
    base = {"name": "Ada Runner", "email": EMAIL, "password": PASSWORD, "consent": _consent()}
    resp = client.post("/api/mobile/personal/join", json={**base, "phone": PHONE, "goal": "levitation"})
    assert resp.status_code == 422
    headers, data = _join(client)
    pid = data["me"]["patient"]["id"]
    try:
        again = client.post("/api/mobile/personal/join",
                            json={**base, "name": "Ada Two", "phone": PHONE, "goal": "sleep"})
        assert again.status_code == 409
        assert "sign in" in again.json()["detail"]
        other_email = client.post("/api/mobile/personal/join",
                                  json={**base, "email": "ada2@example.com", "phone": PHONE, "goal": "sleep"})
        assert other_email.status_code == 409 and "number" in other_email.json()["detail"]
        # A hospital join with a personal number is sent back into the app.
        hosp = client.post("/api/mobile/join", json={
            "hospital_id": "hosp_demo", "name": "Ada Runner", "phone": PHONE})
        assert hosp.status_code == 409
        # A number alone never opens the account without a texted code.
        back = client.post("/api/mobile/personal/signin", json={"phone": PHONE})
        assert back.status_code == 409
        assert client.post("/api/mobile/personal/signin",
                           json={"phone": "+15125559999"}).status_code == 404
    finally:
        _forget(db, pid)


def test_join_needs_email_password_and_consent(client, db):
    base = {"name": "Ada Runner", "goal": "everyday"}
    assert client.post("/api/mobile/personal/join", json={**base, "email": "nope",
                       "password": PASSWORD, "consent": _consent()}).status_code == 422
    assert client.post("/api/mobile/personal/join", json={**base, "email": EMAIL,
                       "password": "short", "consent": _consent()}).status_code == 422
    missing = client.post("/api/mobile/personal/join", json={**base, "email": EMAIL, "password": PASSWORD})
    assert missing.status_code == 422 and "consent" in missing.json()["detail"].lower()
    partial = dict(_consent())
    partial["scopes"] = {**partial["scopes"], "data_storage": False}
    refused = client.post("/api/mobile/personal/join", json={**base, "email": EMAIL,
                          "password": PASSWORD, "consent": partial})
    assert refused.status_code == 422 and "Store my health data" in refused.json()["detail"]
    stale = dict(_consent())
    stale["version"] = "2020-01-01.0"
    assert client.post("/api/mobile/personal/join", json={**base, "email": EMAIL,
                       "password": PASSWORD, "consent": stale}).status_code == 409
    # The form itself is public, versioned, and says it is a beta.
    doc = client.get("/api/mobile/consent").json()
    assert doc["beta"] is True and doc["version"] and "beta" in doc["text"].lower()
    assert {s["key"] for s in doc["scopes"]} == {"beta_ack", "data_storage", "ai_processing", "research_use"}


def test_login_lockout_reset_and_consent_archive(client, db, monkeypatch):
    from app.models.personal import Consent
    from app.personal import auth
    from app.storage import blobs

    headers, data = _join(client, phone=None)
    pid = data["me"]["patient"]["id"]
    try:
        me = data["me"]
        assert me["consent"]["needs_consent"] is False
        assert me["consent"]["version"] == auth.CONSENT_VERSION
        assert me["features"]["beta"] is True
        row = db.scalar(select(Consent).where(Consent.patient_id == pid))
        assert row.scopes["research_use"] is True and row.signature == "Ada Runner"
        assert row.text_sha256 == auth.consent_hash()
        # The full form landed in the lake, under the personal prefix.
        assert row.archived_key.startswith(f"personal/{pid}/lake/consent/")
        archived = json.loads((blobs.local_root() / row.archived_key).read_text())
        assert archived["text"] == auth.CONSENT_TEXT and archived["scopes"]["beta_ack"] is True
        # Login: right password in, wrong one out, eight wrong ones lock.
        ok = client.post("/api/mobile/personal/login", json={"email": EMAIL.upper(), "password": PASSWORD})
        assert ok.status_code == 200 and ok.json()["me"]["patient"]["id"] == pid
        assert client.post("/api/mobile/personal/login",
                           json={"email": EMAIL, "password": "wrong-wrong"}).status_code == 401
        assert client.post("/api/mobile/personal/login",
                           json={"email": "nobody@example.com", "password": PASSWORD}).status_code == 401
        for _ in range(7):
            client.post("/api/mobile/personal/login", json={"email": EMAIL, "password": "wrong-wrong"})
        locked = client.post("/api/mobile/personal/login", json={"email": EMAIL, "password": PASSWORD})
        assert locked.status_code == 423
        from app.models.personal import PersonalCredential

        cred = db.get(PersonalCredential, pid)
        cred.locked_until = None
        db.commit()
        # Change the password while signed in; the old one stops working.
        assert client.post("/api/mobile/personal/password/change", headers=headers,
                           json={"current_password": "nope-nope", "new_password": "x" * 9}).status_code == 401
        assert client.post("/api/mobile/personal/password/change", headers=headers,
                           json={"current_password": PASSWORD, "new_password": "new-pass-word"}).status_code == 200
        assert client.post("/api/mobile/personal/login",
                           json={"email": EMAIL, "password": PASSWORD}).status_code == 401
        assert client.post("/api/mobile/personal/login",
                           json={"email": EMAIL, "password": "new-pass-word"}).status_code == 200
        # Forgot: without a phone or texts nothing goes out, and the answer
        # does not say whether the email exists.
        forgot = client.post("/api/mobile/personal/password/forgot", json={"email": EMAIL}).json()
        assert forgot["sent"] is False and forgot["verification_id"] is None
        unknown = client.post("/api/mobile/personal/password/forgot", json={"email": "x@y.zz"}).json()
        assert unknown == forgot
        # The research scope can be withdrawn without a new signature.
        off = client.patch("/api/mobile/personal/consent/research", headers=headers,
                           json={"allowed": False}).json()
        assert off["consent"]["scopes"]["research_use"] is False
        # Deleting the account removes the rows and the lake.
        gone = client.delete("/api/mobile/personal/account", headers=headers)
        assert gone.status_code == 200, gone.text
        db.expire_all()
        assert db.get(Patient, pid) is None
        assert db.get(PersonalCredential, pid) is None
        assert not (blobs.local_root() / "personal" / pid).exists()
        assert client.get("/api/mobile/me", headers=headers).status_code == 401
        assert client.post("/api/mobile/personal/login",
                           json={"email": EMAIL, "password": "new-pass-word"}).status_code == 401
    finally:
        if db.get(Patient, pid) is not None:
            _forget(db, pid)


def test_password_reset_by_texted_code(client, db, monkeypatch):
    from app.notifications import sendblue
    from tests.test_mobile import _FakeResponse

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "sendblue_api_key", "k")
    monkeypatch.setattr(settings, "sendblue_api_secret", "s")
    monkeypatch.setattr(sendblue, "_post_message",
                        lambda phone, content: sent.append((phone, content)) or _FakeResponse())
    headers, data = _join(client, phone="+15125559011", email="reset@example.com")
    pid = data["me"]["patient"]["id"]
    try:
        forgot = client.post("/api/mobile/personal/password/forgot",
                             json={"email": "reset@example.com"}).json()
        assert forgot["sent"] is True and forgot["verification_id"]
        code = sent[-1][1].split("is ")[1].split(".")[0]
        bad = client.post("/api/mobile/personal/password/reset", json={
            "verification_id": forgot["verification_id"], "code": "000000", "password": "brand-new-pw"})
        assert bad.status_code == 401
        good = client.post("/api/mobile/personal/password/reset", json={
            "verification_id": forgot["verification_id"], "code": code, "password": "brand-new-pw"})
        assert good.status_code == 200 and good.json()["me"]["patient"]["id"] == pid
        assert client.post("/api/mobile/personal/login",
                           json={"email": "reset@example.com", "password": "brand-new-pw"}).status_code == 200
    finally:
        _forget(db, pid)


def test_clinic_enrolment_records_consent_when_offered(client, db):
    from app.models.personal import Consent

    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Cal Consent", "phone": "+15125559012",
        "consent": _consent(research=False)})
    assert joined.status_code == 200, joined.text
    pid = joined.json()["me"]["patient"]["id"]
    try:
        assert joined.json()["me"]["consent"]["needs_consent"] is False
        row = db.scalar(select(Consent).where(Consent.patient_id == pid))
        assert row is not None and row.scopes["research_use"] is False
        # An existing account with no consent is told so, and can accept in place.
        assert client.post("/api/mobile/enroll", json={
            "patient_id": "ana", "hospital_id": "hosp_demo", "phone": "+15125559013"}).status_code in (200, 409)
    finally:
        db.execute(delete(Consent).where(Consent.patient_id == pid))
        db.commit()
        _forget_patient(db, pid)


def test_day_and_ai_results_land_in_the_lake(client, db):
    from app.storage import blobs

    headers, data = _join(client, phone=None, email="lake@example.com")
    pid = data["me"]["patient"]["id"]
    try:
        _seed_stream(db, pid, days=12)
        client.post("/api/mobile/personal/day", headers=headers, json={})
        client.get("/api/mobile/personal/insights/sleep", headers=headers)
        client.post("/api/mobile/agent", headers=headers, json={"text": "energy is a 7", "channel": "app"})
        lake = blobs.local_root() / "personal" / pid / "lake"
        day = json.loads((lake / "days" / f"{date.today().isoformat()}.json").read_text())
        assert day["verdict"]["kind"] and day["brief"]["brief"] and "readiness" in day["panels"]
        assert "series" not in day["panels"]["hrv"]
        assert any((lake / "ai" / "personal_brief").iterdir())
        assert any((lake / "ai" / "personal_deep").iterdir())
        assert any((lake / "coach").iterdir())
        assert any((lake / "events").iterdir())
    finally:
        _forget(db, pid)


def test_paywall_closes_when_the_trial_ends(client, db):
    headers, data = _join(client, goal="everyday")
    pid = data["me"]["patient"]["id"]
    try:
        assert client.get("/api/mobile/personal/dashboard", headers=headers).status_code == 200
        row = db.scalar(select(Entitlement).where(Entitlement.patient_id == pid))
        row.expires_at = datetime.now() - timedelta(days=1)
        db.commit()
        closed = client.get("/api/mobile/personal/dashboard", headers=headers)
        assert closed.status_code == 402
        paywall = json.loads(closed.headers["X-MedPull-Paywall"])
        assert paywall["state"] == "expired" and paywall["trial_used"] is True
        # The profile, subscription and switching still answer.
        assert client.get("/api/mobile/personal/subscription", headers=headers).status_code == 200
        assert client.get("/api/mobile/me", headers=headers).status_code == 200
    finally:
        _forget(db, pid)


def _fake_jws(payload: dict) -> str:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    header = b64(json.dumps({"alg": "ES256", "x5c": []}).encode())
    body = b64(json.dumps(payload).encode())
    return f"{header}.{body}.{b64(b'0' * 64)}"


def test_apple_transaction_grants_access_in_lenient_mode(client, db, monkeypatch):
    monkeypatch.setattr(settings, "apple_subscription_verify", "lenient")
    headers, data = _join(client, goal="sleep")
    pid = data["me"]["patient"]["id"]
    try:
        db.scalar(select(Entitlement).where(Entitlement.patient_id == pid)).expires_at = \
            datetime.now() - timedelta(days=1)
        db.commit()
        assert client.get("/api/mobile/personal/dashboard", headers=headers).status_code == 402
        expires = int((datetime.now() + timedelta(days=30)).timestamp() * 1000)
        jws = _fake_jws({
            "bundleId": settings.ios_bundle_id,
            "productId": "com.medpull.recovery.personal.monthly",
            "originalTransactionId": "2000000001", "transactionId": "2000000002",
            "expiresDate": expires, "purchaseDate": expires - 30 * 86400000,
            "environment": "Xcode", "type": "Auto-Renewable Subscription",
        })
        resp = client.post("/api/mobile/personal/subscription/apple", headers=headers,
                           json={"jws": jws, "environment": "Xcode"})
        assert resp.status_code == 200, resp.text
        state = resp.json()["subscription"]
        assert state["state"] == "active" and state["source"] == "apple"
        assert state["verified"] is False
        assert client.get("/api/mobile/personal/dashboard", headers=headers).status_code == 200
        # A renewal updates the same row; a different app or product is refused.
        renew = client.post("/api/mobile/personal/subscription/apple", headers=headers,
                            json={"jws": _fake_jws({
                                "bundleId": settings.ios_bundle_id,
                                "productId": "com.medpull.recovery.personal.monthly",
                                "originalTransactionId": "2000000001",
                                "transactionId": "2000000003",
                                "expiresDate": expires + 30 * 86400000})})
        assert renew.status_code == 200
        assert len(db.scalars(select(Entitlement).where(
            Entitlement.patient_id == pid, Entitlement.source == "apple")).all()) == 1
        wrong = client.post("/api/mobile/personal/subscription/apple", headers=headers,
                            json={"jws": _fake_jws({"bundleId": "com.other", "productId": "x"})})
        assert wrong.status_code == 422
        assert client.post("/api/mobile/personal/subscription/apple", headers=headers,
                           json={"jws": "not a token at all, sorry"}).status_code == 422
    finally:
        _forget(db, pid)


def test_strict_mode_refuses_an_unchained_transaction(client, db, monkeypatch):
    monkeypatch.setattr(settings, "apple_subscription_verify", "strict")
    headers, data = _join(client)
    pid = data["me"]["patient"]["id"]
    try:
        jws = _fake_jws({"bundleId": settings.ios_bundle_id,
                         "productId": "com.medpull.recovery.personal.monthly"})
        resp = client.post("/api/mobile/personal/subscription/apple", headers=headers,
                           json={"jws": jws})
        assert resp.status_code == 422
        assert "chain" in resp.json()["detail"].lower()
    finally:
        _forget(db, pid)


# --- the readouts -----------------------------------------------------------------------


def _data_from(series: dict[str, pd.Series], today: date) -> PersonalData:
    data = PersonalData(today=today, since=today - timedelta(days=89))
    data.series = series
    return data


def _daily(values: list[float], today: date) -> pd.Series:
    n = len(values)
    return pd.Series(values, index=[today - timedelta(days=n - 1 - i) for i in range(n)])


class _Profile:
    goal = "performance"
    sport = "running"
    weekly_target_minutes = 240
    sleep_target_hours = None
    injury = None


class _Patient:
    id = "p"
    age = 34
    sex = "F"


def test_readiness_is_fifty_at_baseline_and_drops_when_hrv_falls():
    today = date.today()
    hrv = [60.0] * 30
    rhr = [52.0] * 30
    sleep = [7.5] * 30
    steady = _data_from({
        str(M.HRV_RMSSD): _daily(hrv, today), str(M.RESTING_HR): _daily(rhr, today),
        str(M.SLEEP_DURATION): _daily(sleep, today),
    }, today)
    board = metrics.compute_dashboard(steady, _Patient(), _Profile())
    score = board["panels"]["readiness"]["extra"]["score"]
    assert 45 <= score <= 55, score
    assert board["verdict"]["kind"] == "steady"

    dipped = _data_from({
        str(M.HRV_RMSSD): _daily(hrv[:-1] + [38.0], today),
        str(M.RESTING_HR): _daily(rhr[:-1] + [60.0], today),
        str(M.SLEEP_DURATION): _daily(sleep[:-1] + [5.0], today),
    }, today)
    low = metrics.compute_dashboard(dipped, _Patient(), _Profile())
    assert low["panels"]["readiness"]["extra"]["score"] < 34
    assert low["panels"]["resting_hr"]["status"] == "flag"
    assert "Last night" in low["panels"]["resting_hr"]["finding"]
    assert low["panels"]["readiness"]["extra"]["band"] == "red"
    assert low["verdict"]["kind"] == "rest"
    comps = {c["key"]: c for c in low["panels"]["readiness"]["extra"]["components"]}
    assert comps["hrv"]["z"] < -2 and comps["resting_hr"]["z"] < -2 and comps["sleep"]["z"] < -1


def test_acwr_flags_a_load_spike_and_form_follows_banister():
    today = date.today()
    load = [400.0] * 40 + [1300.0] * 5
    data = _data_from({str(M.ACTIVE_ENERGY): _daily(load, today)}, today)
    panel = metrics.load_panel(data, _Profile())
    assert panel.extra["acwr"] > metrics.ACWR_SPIKE
    assert panel.status == "flag"
    assert panel.extra["fatigue"] > panel.extra["fitness"]  # form negative after the spike
    assert panel.extra["form"] < 0
    steady = _data_from({str(M.ACTIVE_ENERGY): _daily([400.0] * 45, today)}, today)
    calm = metrics.load_panel(steady, _Profile())
    assert 0.95 <= calm.extra["acwr"] <= 1.05
    assert calm.status == "ok"


def test_sleep_debt_accumulates_and_need_grows_with_a_target():
    today = date.today()
    nights = [7.5] * 25 + [5.5] * 5
    data = _data_from({str(M.SLEEP_DURATION): _daily(nights, today)}, today)
    panel = metrics.sleep_panel(data, _Profile(), None)
    assert panel.extra["debt_hours"] > 4
    assert panel.status == "flag"

    class Target(_Profile):
        sleep_target_hours = 9.0

    target = metrics.sleep_panel(data, Target(), None)
    assert target.extra["need_hours"] == 9.0


def test_hrv_panel_reports_the_swc_band_in_raw_units():
    today = date.today()
    rng = np.random.default_rng(3)
    hrv = list(60 + rng.normal(0, 4, 30))
    data = _data_from({str(M.HRV_RMSSD): _daily(hrv, today)}, today)
    panel = metrics.hrv_panel(data)
    lo, hi = panel.extra["swc_low"], panel.extra["swc_high"]
    assert lo < panel.extra["baseline_mean"] < hi
    assert panel.extra["statistic"] == "RMSSD"
    assert "ms" in panel.finding
    assert math.isfinite(panel.extra["balance"])


def test_body_panel_counts_adverse_overnight_signals_together():
    today = date.today()
    n = 30
    data = _data_from({
        str(M.RESTING_HR): _daily([52.0] * (n - 1) + [61.0], today),
        str(M.HRV_RMSSD): _daily([60.0] * (n - 1) + [40.0], today),
        str(M.RESPIRATORY_RATE): _daily([14.0] * (n - 1) + [17.5], today),
        str(M.SKIN_TEMP_DELTA): _daily([0.0] * (n - 1) + [0.9], today),
    }, today)
    panel = metrics.body_panel(data)
    assert panel.extra["adverse"] >= 3
    assert panel.status == "flag"
    assert "strain" in panel.status_text.lower()
    assert "diagnos" not in panel.finding.lower()


def test_session_rpe_becomes_the_load_when_sessions_are_logged():
    today = date.today()
    energy = _daily([500.0] * 40, today)
    data = _data_from({str(M.ACTIVE_ENERGY): energy}, today)
    # Ten logged sessions over the last three weeks, one hard block last week.
    days = [today - timedelta(days=i) for i in (1, 2, 3, 4, 6, 9, 12, 15, 18, 21)]
    data.logs = {
        "rpe": pd.Series([8, 8, 7, 8, 5, 6, 5, 6, 5, 5], index=days).sort_index(),
        "session_minutes": pd.Series([70, 60, 75, 65, 40, 45, 40, 45, 40, 40], index=days).sort_index(),
    }
    panel = metrics.load_panel(data, _Profile())
    assert panel.extra["source"] == "session RPE" and panel.extra["unit"] == "AU"
    assert panel.extra["acwr"] > 1.3  # the hard week shows as a rising ratio
    # Without enough logged sessions the device's energy stands in.
    data.logs = {"rpe": pd.Series([7.0], index=[today]), "session_minutes": pd.Series([60.0], index=[today])}
    assert metrics.load_panel(data, _Profile()).extra["source"] == "active energy"


def test_overreach_watch_tallies_the_signs():
    today = date.today()
    n = 45
    rng = np.random.default_rng(5)
    calm = _data_from({
        str(M.HRV_RMSSD): _daily(list(60 + rng.normal(0, 3, n)), today),
        str(M.RESTING_HR): _daily(list(52 + rng.normal(0, 1, n)), today),
        str(M.SLEEP_DURATION): _daily([7.6] * n, today),
        str(M.ACTIVE_ENERGY): _daily([450.0] * n, today),
    }, today)
    board = metrics.compute_dashboard(calm, _Patient(), _Profile())
    assert board["panels"]["overreach"]["status"] == "ok"
    assert "overreach" in board["sections"]
    strained = _data_from({
        str(M.HRV_RMSSD): _daily(list(60 + rng.normal(0, 3, n - 7)) + [46.0] * 7, today),
        str(M.RESTING_HR): _daily(list(52 + rng.normal(0, 1, n - 7)) + [57.0] * 7, today),
        str(M.SLEEP_DURATION): _daily([7.6] * (n - 7) + [5.6] * 7, today),
        str(M.ACTIVE_ENERGY): _daily([450.0] * (n - 7) + [1100.0] * 7, today),
    }, today)
    hot = metrics.compute_dashboard(strained, _Patient(), _Profile())
    over = hot["panels"]["overreach"]
    assert over["status"] == "flag" and over["extra"]["score"] >= metrics.OVERREACH_FLAG
    labels = {d["label"] for d in over["extra"]["drivers"]}
    assert {"Resting HR", "Sleep debt"} <= labels
    assert labels & {"Load spike", "Load rising"}
    assert "diagnos" not in over["finding"].lower()
    # Trends and the week travel with the dashboard.
    assert hot["trends"]["hrv"]["weeks_with_data"] >= 6
    assert len(hot["trends"]["hrv"]["weeks"]) == metrics.TREND_WEEKS
    week = hot["week"]
    assert week["metrics"]["sleep"]["this"] < week["metrics"]["sleep"]["last"]
    assert week["metrics"]["load"]["delta_pct"] > 50
    assert any("Sleep averaged" in h for h in week["highlights"])
    digest = hot["digest"]
    assert "overreach" in digest and "week" in digest


def test_brief_has_a_headline_and_the_week_endpoint_answers(client, db):
    headers, data = _join(client, phone=None, email="week@example.com")
    pid = data["me"]["patient"]["id"]
    try:
        _seed_stream(db, pid, days=20)
        day = client.post("/api/mobile/personal/day", headers=headers, json={}).json()
        assert day["brief"]["headline"] and len(day["brief"]["headline"].split()) <= 12
        assert day["brief"]["headline"] not in day["brief"]["brief"]
        week = client.get("/api/mobile/personal/week", headers=headers)
        assert week.status_code == 200, week.text
        body = week.json()
        assert body["week"]["metrics"]["readiness"]["this"] is not None
        assert body["review"]["domain"] == "weekly" and body["trends"]["sleep"]["weeks"]
    finally:
        _forget(db, pid)


def test_dashboard_orders_sections_by_goal_and_handles_no_data():
    today = date.today()
    empty = _data_from({}, today)
    for goal in ("performance", "sleep", "recovery", "everyday"):
        class P(_Profile):
            pass
        P.goal = goal
        board = metrics.compute_dashboard(empty, _Patient(), P())
        assert board["sections"][0] == metrics.SECTIONS_BY_GOAL[goal][0]
        assert board["verdict"]["kind"] == "unknown"
        assert all(p["status"] == "nodata" for p in board["panels"].values())
        assert board["fingerprint"]


def test_dashboard_endpoint_reads_the_stream_and_writes_the_plan(client, db):
    headers, data = _join(client)
    pid = data["me"]["patient"]["id"]
    try:
        _seed_stream(db, pid)
        resp = client.post("/api/mobile/personal/day", headers=headers, json={"text": False})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        board = body["dashboard"]
        assert board["days_with_data"] >= 30
        assert board["panels"]["readiness"]["extra"]["score"] is not None
        assert board["panels"]["hrv"]["status"] != "nodata"
        assert board["panels"]["load"]["extra"]["acwr"] is not None
        assert board["panels"]["sleep"]["extra"]["bedtime_sd_min"] is not None
        assert board["sections"][0] == "readiness"
        assert "digest" not in board
        # The brief is the deterministic renderer (no key in tests) and
        # carries the personal guardrail, never the clinic one.
        assert body["brief"]["provider"] == "fallback"
        assert body["brief"]["guardrail"].startswith("Guidance for training")
        assert len(body["brief"]["brief"].split()) >= 8
        # The plan: a recurring check-in plus today's items, written once.
        tasks = client.get("/api/mobile/tasks", headers=headers).json()["open"]
        kinds = sorted(t["kind"] for t in tasks)
        assert "checkin" in kinds and len(tasks) >= 2
        checkin = next(t for t in tasks if t["kind"] == "checkin")
        assert [q["id"] for q in checkin["questions"]][:2] == ["energy", "soreness"]
        again = client.post("/api/mobile/personal/day", headers=headers, json={})
        assert again.json()["plan"]["created"] == []
        assert len(client.get("/api/mobile/tasks", headers=headers).json()["open"]) == len(tasks)
        # The thread got the brief once, with a button into the check-in.
        lines = client.get("/api/mobile/messages", headers=headers).json()["messages"]
        briefs = [m for m in lines if m["action"] and m["action"]["kind"] == "personal_brief"]
        assert len(briefs) == 1 and briefs[0]["action"]["task_id"] == checkin["id"]
        # Answering the check-in lands in the subjective log and the panel.
        done = client.post(f"/api/mobile/tasks/{checkin['id']}/complete", headers=headers,
                           json={"answers": {"energy": 7, "soreness": 3, "sleep_quality": "ok",
                                             "mood": "good", "note": "legs heavy"}})
        assert done.status_code == 200, done.text
        db.expire_all()
        logs = {row.key: row for row in db.scalars(
            select(PersonalLog).where(PersonalLog.patient_id == pid)).all()}
        assert logs["energy"].value_num == 7 and logs["sleep_quality"].value_num == 6
        assert logs["note"].text == "legs heavy"
        dash = client.get("/api/mobile/personal/dashboard", headers=headers).json()
        subj = dash["dashboard"]["panels"]["subjective"]
        assert subj["status"] != "nodata"
        # Deep dives answer for every domain and refuse an unknown one.
        for domain in ("recovery", "training", "sleep", "weekly"):
            deep = client.get(f"/api/mobile/personal/insights/{domain}", headers=headers)
            assert deep.status_code == 200, deep.text
            assert deep.json()["domain"] == domain and deep.json()["body"]
        assert client.get("/api/mobile/personal/insights/astrology",
                          headers=headers).status_code == 404
        # The export carries the profile, the readouts and the log.
        export = client.post("/api/mobile/personal/export", headers=headers).json()
        assert export["url"] is None and export["data"]["profile"]["goal"] == "performance"
        assert export["data"]["logs"]["energy"]
    finally:
        _forget(db, pid)


def test_recovery_goal_surfaces_the_care_metrics(client, db):
    headers, data = _join(client, goal="recovery", procedure_type="ACL",
                          anchor_date=(date.today() - timedelta(days=20)).isoformat(),
                          injury="ACL, left")
    pid = data["me"]["patient"]["id"]
    try:
        db.expire_all()
        row = db.get(Patient, pid)
        assert str(row.procedure_type) == "ACL"
        assert row.surgery_date == date.today() - timedelta(days=20)
        _seed_stream(db, pid, days=19)
        dash = client.get("/api/mobile/personal/dashboard", headers=headers).json()
        assert dash["care"] is not None
        assert dash["care"]["pathway"] == "ortho_acl"
        assert {m["id"] for m in dash["care"]["metrics"]} >= {"M1", "M12", "M17"}
        assert dash["dashboard"]["sections"][1] == "care"
        tasks = client.post("/api/mobile/personal/day", headers=headers, json={}).json()
        checkin = next(t for t in client.get("/api/mobile/tasks", headers=headers).json()["open"]
                       if t["kind"] == "checkin")
        assert any(q["id"] == "pain" for q in checkin["questions"])
        assert tasks["plan"]["checkin_id"] == checkin["id"]
    finally:
        _forget(db, pid)


# --- the coach ---------------------------------------------------------------------------


def test_coach_logs_readings_and_keeps_notes_without_a_care_team(client, db):
    headers, data = _join(client)
    pid = data["me"]["patient"]["id"]
    try:
        from app.models.notification import Notification

        before = len(db.scalars(select(Notification).where(Notification.patient_id == pid)).all())
        resp = client.post("/api/mobile/agent", headers=headers,
                           json={"text": "my pain is a 3 today", "channel": "app"})
        assert resp.status_code == 200
        assert "Logged pain 3/10" in resp.json()["reply"]
        db.expire_all()
        sore = db.scalar(select(PersonalLog).where(PersonalLog.patient_id == pid,
                                                   PersonalLog.key == "soreness"))
        assert sore is not None and sore.value_num == 3
        # A red flag gets the emergency script without a care-team promise.
        flag = client.post("/api/mobile/agent", headers=headers,
                           json={"text": "I have chest pain", "channel": "app"}).json()
        assert flag["flagged"] is True
        assert "911" in flag["reply"] and "care team" not in flag["reply"].lower()
        after = len(db.scalars(select(Notification).where(Notification.patient_id == pid)).all())
        assert after == before  # nobody to notify
        # The empty-hands reply speaks the coach's language.
        generic = client.post("/api/mobile/agent", headers=headers,
                              json={"text": "hmm", "channel": "app"}).json()
        assert "readouts" in generic["reply"] or "how you feel" in generic["reply"]
    finally:
        _forget(db, pid)


# --- two spaces --------------------------------------------------------------------------


def test_clinic_patient_adds_a_personal_space_and_switches(client, db):
    # A throwaway chart of its own (the seeded roster is shared across the
    # session and other files leave phones and sessions on it).
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Ben Clinic", "phone": "+15125559002",
        "had_surgery": True, "procedure_type": "TKA",
        "surgery_date": (date.today() - timedelta(days=12)).isoformat(),
    })
    assert joined.status_code == 200, joined.text
    clinic_id = joined.json()["me"]["patient"]["id"]
    clinic_headers = {"Authorization": f"Bearer {joined.json()['session_token']}"}
    personal_id = None
    try:
        _seed_stream(db, clinic_id, days=11)
        added = client.post("/api/mobile/personal/add", headers=clinic_headers,
                            json={"goal": "recovery"})
        assert added.status_code == 200, added.text
        body = added.json()
        personal_id = body["me"]["patient"]["id"]
        personal_headers = {"Authorization": f"Bearer {body['session_token']}"}
        assert body["me"]["patient"]["mode"] == "personal"
        assert [p["kind"] for p in body["profiles"]] == ["personal", "clinic"]
        db.expire_all()
        chart = db.get(Patient, clinic_id)
        me = db.get(Patient, personal_id)
        assert chart.linked_patient_id == personal_id and me.linked_patient_id == clinic_id
        assert me.observations_from == clinic_id and me.phone == chart.phone
        assert str(me.procedure_type) == "TKA"  # the recovery goal inherits the operation
        # The personal space reads the chart's stream.
        dash = client.get("/api/mobile/personal/dashboard", headers=personal_headers).json()
        assert dash["dashboard"]["days_with_data"] > 5
        portfolio = client.get("/api/mobile/portfolio", headers=personal_headers).json()
        assert portfolio["metrics"]
        # Switching both ways issues a session for the other row.
        back = client.post("/api/mobile/profiles/switch", headers=personal_headers,
                           json={"patient_id": clinic_id})
        assert back.status_code == 200
        assert back.json()["me"]["patient"]["id"] == clinic_id
        forth = client.post("/api/mobile/profiles/switch", headers=clinic_headers,
                            json={"patient_id": personal_id})
        assert forth.json()["me"]["patient"]["mode"] == "personal"
        assert client.post("/api/mobile/profiles/switch", headers=clinic_headers,
                           json={"patient_id": "reyes"}).status_code == 403
        # A second personal space on the same chart is refused.
        assert client.post("/api/mobile/personal/add", headers=clinic_headers,
                           json={"goal": "sleep"}).status_code == 409
        # The chart is on the worklist and the personal space is not; nor is
        # it offered as something to fold into a chart.
        rows = client.get("/api/worklist").json()["patients"]
        assert clinic_id in {r["id"] for r in rows} and personal_id not in {r["id"] for r in rows}
        candidates = client.get(f"/api/patients/{clinic_id}/app-link/candidates").json()
        assert personal_id not in {c["patient_id"] for c in candidates["candidates"]}
        # A clinic re-enroll with the shared number leaves the pair intact.
        again = client.post("/api/mobile/enroll", json={
            "patient_id": clinic_id, "hospital_id": "hosp_demo", "phone": "+15125559002"})
        assert again.status_code == 200, again.text
        db.expire_all()
        assert db.get(Patient, personal_id).phone == "+15125559002"
        assert db.get(Patient, clinic_id).phone == "+15125559002"
    finally:
        if personal_id:
            _forget(db, personal_id)
        db.expire_all()
        chart = db.get(Patient, clinic_id)
        if chart is not None:
            chart.linked_patient_id = None
            db.commit()
        _forget_patient(db, clinic_id)


def test_personal_space_joins_a_hospital_and_keeps_its_own_stream(client, db):
    headers, data = _join(client, phone="+15125559003", goal="everyday")
    pid = data["me"]["patient"]["id"]
    clinic_id = None
    try:
        _seed_stream(db, pid, days=10)
        resp = client.post("/api/mobile/personal/link-hospital", headers=headers,
                           json={"mode": "join", "hospital_id": "hosp_demo"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        clinic_id = body["me"]["patient"]["id"]
        assert body["status"] == "linked"
        assert body["me"]["patient"]["mode"] == "general"
        assert body["me"]["patient"]["hospital"]["id"] == "hosp_demo"
        assert body["link"]["observations"]["moved"] > 50
        db.expire_all()
        me = db.get(Patient, pid)
        assert me.observations_from == clinic_id and me.linked_patient_id == clinic_id
        # The readings now live on the chart; the personal side still sees them.
        from app.models.observation import Observation

        assert db.scalar(select(Observation.id).where(Observation.patient_id == pid)) is None
        dash = client.get("/api/mobile/personal/dashboard", headers=headers).json()
        assert dash["dashboard"]["days_with_data"] >= 10
        # The chart is on the worklist; the personal space is not.
        rows = {r["id"] for r in client.get("/api/worklist").json()["patients"]}
        assert clinic_id in rows and pid not in rows
        assert client.post("/api/mobile/personal/link-hospital", headers=headers,
                           json={"mode": "join", "hospital_id": "hosp_demo"}).status_code == 409
    finally:
        _forget(db, pid)
        if clinic_id:
            _forget_patient(db, clinic_id)


def test_daily_run_writes_every_entitled_subscriber_once(client, db):
    from app.personal import daily

    headers, data = _join(client, phone="+15125559004")
    pid = data["me"]["patient"]["id"]
    try:
        _seed_stream(db, pid, days=12)
        first = daily.run(db, text=False)
        assert pid in first["done"] and first["texted"] == 0
        second = daily.run(db, text=False)
        assert pid in second["done"]
        briefs = db.scalars(select(Message).where(Message.patient_id == pid,
                                                  Message.action_kind == "personal_brief")).all()
        assert len(briefs) == 1
        # An expired subscriber is skipped.
        db.scalar(select(Entitlement).where(Entitlement.patient_id == pid)).expires_at = \
            datetime.now() - timedelta(days=1)
        db.commit()
        third = daily.run(db, text=False)
        assert pid in third["skipped"]
    finally:
        _forget(db, pid)


# The Lambda action itself is covered in tests/test_lambda_handler.py, which
# owns the fake-S3 handler import.


# --- storage -------------------------------------------------------------------------------


def test_personal_files_use_their_own_prefix_and_bucket(client, db, monkeypatch):
    from app.aws.config import aws_settings
    from app.storage import blobs

    headers, data = _join(client, phone="+15125559005")
    pid = data["me"]["patient"]["id"]
    try:
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        # The direct route takes the bytes as the body with the type header.
        up = client.post("/api/mobile/attachments/direct", headers={**headers,
                         "Content-Type": "image/png"}, content=png)
        assert up.status_code == 200, up.text
        row_id = up.json()["attachment"]["id"]
        from app.models.attachment import Attachment

        row = db.get(Attachment, row_id)
        assert row.storage_key.startswith(f"personal/{pid}/")
        assert blobs.owned_by(row.storage_key, pid)
        # Bucket routing is a pure function of the key and the settings. The
        # patches are scoped so the cleanup below never sees a bucket name
        # (with one set, blobs would reach for a real S3 client).
        with monkeypatch.context() as m:
            m.setattr(aws_settings, "s3_bucket", "clinic-bucket")
            m.setattr(aws_settings, "personal_s3_bucket", "personal-bucket")
            assert blobs.bucket_for(row.storage_key) == "personal-bucket"
            assert blobs.bucket_for(f"attachments/{pid}/x.png") == "clinic-bucket"
            m.setattr(aws_settings, "personal_s3_bucket", "")
            assert blobs.bucket_for(row.storage_key) == "clinic-bucket"
        assert not aws_settings.s3_bucket
    finally:
        _forget(db, pid)


@pytest.mark.parametrize("goal", ["performance", "sleep", "recovery", "everyday"])
def test_plan_items_follow_the_verdict(goal):
    from app.personal import plan

    class P:
        sport = "cycling"
    P.goal = goal
    for kind in ("push", "steady", "easy", "rest", "unknown"):
        board = {"verdict": {"kind": kind, "reason": "because"},
                 "panels": {"sleep": {"extra": {"debt_hours": 3.0, "mean_bedtime": "23:10"}}}}
        items = plan._items_for(board, P())
        assert 1 <= len(items) <= plan.MAX_ITEMS
        assert all(i["kind"] in ("exercise", "walk", "workout", "custom", "sleep") for i in items)
        if goal == "sleep":
            assert items[0]["kind"] == "sleep" and "Lights out by" in items[0]["title"]
