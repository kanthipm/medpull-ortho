"""Signing in, out, back in and across the three account kinds.

One person can hold a hospital chart, the personal space paired with it and
an athlete account (app/sports), all under one mobile number. These tests
walk every door the app has — find my record, join, the phone sign-in, the
email login, the space switch — after an athlete signs out, and pin down
what each must do. Every row created here is removed afterwards so the
session-scoped seeded database is the roster again.
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import delete, select

from app.config import settings
from app.models.mobile import PatientSession
from app.models.patient import Patient
from app.models.personal import Consent
from app.personal import auth
from tests.test_mobile import _FakeResponse, _forget_patient
from tests.test_personal import _consent, _forget, _join

ATHLETE_PWD = "owls-2026-test"


@pytest.fixture(autouse=True)
def _paywall_on(monkeypatch):
    # The receipt paths below are dormant by default (no paid product yet).
    monkeypatch.setattr(settings, "personal_paywall", True)


def _forget_athlete(db, patient_id: str) -> None:
    from app.sports.seed import _reset

    _reset(db, patient_id)


def _athlete(client, phone: str | None, email: str, name: str = "Steve Test") -> tuple[dict, dict]:
    body = {"name": name, "email": email, "password": ATHLETE_PWD, "consent": _consent(),
            "sport": "basketball", "level": "club", "phone": phone, "device_name": "iPhone (test)"}
    resp = client.post("/api/mobile/sports/join", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["me"]["patient"]["account_kind"] == "sports"
    return {"Authorization": f"Bearer {data['session_token']}"}, data


def _chart(db, patient_id: str) -> Patient:
    db.expire_all()
    return db.get(Patient, patient_id)


def _consents(db, patient_id: str) -> list[Consent]:
    return list(db.scalars(select(Consent).where(Consent.patient_id == patient_id)
                           .order_by(Consent.id)).all())


# --- the reported bug ----------------------------------------------------------------------------


def test_athlete_signs_out_then_enrols_on_the_chart_with_the_same_number(client, db):
    """Steve's case: the athlete account carries his number, he signs out of
    the sports side, then finds his hospital record. The chart enrols, the
    athlete keeps the number, and the same person re-finding the record
    later neither re-signs the consent nor grows a second consent row."""
    phone = "+15125558101"
    headers, data = _athlete(client, phone, "signin.paths.1@athletes.medpull.demo")
    ath = data["me"]["patient"]["id"]
    try:
        assert client.post("/api/mobile/signout", headers=headers).status_code == 200
        assert client.get("/api/mobile/me", headers=headers).status_code == 401
        assert client.post("/api/mobile/profiles/switch", headers=headers,
                           json={"patient_id": ath}).status_code == 401

        found = client.post("/api/mobile/patients/search", json={
            "hospital_id": "hosp_demo", "name": "Steve", "phone": phone}).json()["candidates"]
        assert [c["patient_id"] for c in found] == ["steve"]
        enrolled = client.post("/api/mobile/enroll", json={
            "patient_id": "steve", "hospital_id": "hosp_demo", "phone": phone,
            "consent": _consent(), "device_name": "iPhone (test)"})
        assert enrolled.status_code == 200, enrolled.text
        me = enrolled.json()["me"]
        assert me["patient"]["id"] == "steve" and me["patient"]["account_kind"] == "clinic"
        assert me["consent"]["needs_consent"] is False
        assert _chart(db, "steve").phone == phone
        assert _chart(db, ath).phone == phone, "the athlete's number must survive"
        # The care team's texts still find the chart, not the athlete row.
        from app.tasks import service as tasks

        assert tasks.patient_for_phone(db, phone).id == "steve"

        # Back for a second time: the same consent already on file is not
        # recorded twice, and the server says nothing needs signing.
        again = client.post("/api/mobile/enroll", json={
            "patient_id": "steve", "hospital_id": "hosp_demo", "phone": phone,
            "consent": _consent(), "device_name": "iPhone (test)"})
        assert again.status_code == 200, again.text
        assert again.json()["me"]["consent"]["needs_consent"] is False
        assert len(_consents(db, "steve")) == 1
        plain = client.post("/api/mobile/enroll", json={
            "patient_id": "steve", "hospital_id": "hosp_demo", "phone": phone})
        assert plain.status_code == 200 and plain.json()["me"]["consent"]["needs_consent"] is False

        # And the athlete can still get back in by email, on either door.
        for door in ("/api/mobile/sports/login", "/api/mobile/personal/login"):
            back = client.post(door, json={"email": "signin.paths.1@athletes.medpull.demo",
                                           "password": ATHLETE_PWD})
            assert back.status_code == 200, back.text
            assert back.json()["me"]["patient"]["id"] == ath
    finally:
        db.execute(delete(Consent).where(Consent.patient_id == "steve"))
        db.execute(delete(PatientSession).where(PatientSession.patient_id == "steve"))
        _chart(db, "steve").phone = None
        db.commit()
        _forget_athlete(db, ath)


def test_paired_chart_and_space_plus_an_athlete_all_share_the_number(client, db):
    """The full picture of Steve's rows: a chart paired with a personal
    space, and an athlete account beside them, one number on all three.
    Enrolling on the chart is open and takes nothing off anybody."""
    phone = "+15125558102"
    headers, data = _join(client, phone=phone, email="signin.paths.2@example.com")
    personal_id = data["me"]["patient"]["id"]
    clinic_id = None
    ath = None
    try:
        linked = client.post("/api/mobile/personal/link-hospital", headers=headers, json={
            "mode": "join", "hospital_id": "hosp_demo", "had_surgery": False})
        assert linked.status_code == 200, linked.text
        clinic_id = linked.json()["me"]["patient"]["id"]
        assert _chart(db, clinic_id).phone == phone
        _, adata = _athlete(client, phone, "signin.paths.2@athletes.medpull.demo")
        ath = adata["me"]["patient"]["id"]

        enrolled = client.post("/api/mobile/enroll", json={
            "patient_id": clinic_id, "hospital_id": "hosp_demo", "phone": phone})
        assert enrolled.status_code == 200, enrolled.text
        for pid in (clinic_id, personal_id, ath):
            assert _chart(db, pid).phone == phone, pid
        # The switch between the two paired spaces still works from the chart.
        chart_headers = {"Authorization": f"Bearer {enrolled.json()['session_token']}"}
        switched = client.post("/api/mobile/profiles/switch", headers=chart_headers,
                               json={"patient_id": personal_id})
        assert switched.status_code == 200 and switched.json()["me"]["patient"]["id"] == personal_id
        # The athlete is never one of the spaces to switch to.
        assert client.post("/api/mobile/profiles/switch", headers=chart_headers,
                           json={"patient_id": ath}).status_code == 403
    finally:
        if ath:
            _forget_athlete(db, ath)
        if clinic_id:
            db.execute(delete(Consent).where(Consent.patient_id == clinic_id))
            db.commit()
            _forget_patient(db, clinic_id)
        _forget(db, personal_id)


def test_verified_enrolment_moves_the_number_off_another_chart_but_not_off_the_athlete(
    client, db, monkeypatch
):
    """With a texted code the enrolment is proven, so a stale clinic chart
    carrying the number loses it (as before) while the athlete account,
    the same person's other row, keeps it."""
    from app.notifications import sendblue

    phone = "+15125558103"
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "sendblue_api_key", "k")
    monkeypatch.setattr(settings, "sendblue_api_secret", "s")
    monkeypatch.setattr(settings, "mobile_otp_required", True)
    monkeypatch.setattr(sendblue, "_post_message",
                        lambda to, content: sent.append((to, content)) or _FakeResponse())
    _, adata = _athlete(client, phone, "signin.paths.3@athletes.medpull.demo")
    ath = adata["me"]["patient"]["id"]
    stale = _chart(db, "kanthi")
    stale.phone = phone  # a clinician's typo on somebody else's chart
    db.commit()
    try:
        started = client.post("/api/mobile/enroll", json={
            "patient_id": "guest", "hospital_id": "hosp_demo", "phone": phone})
        assert started.status_code == 200 and started.json()["status"] == "verification_required"
        code = sent[-1][1].split("is ")[1].split(".")[0]
        ok = client.post("/api/mobile/enroll/verify",
                         json={"verification_id": started.json()["verification_id"], "code": code})
        assert ok.status_code == 200 and ok.json()["verified"] is True
        assert _chart(db, "guest").phone == phone
        assert _chart(db, "kanthi").phone is None
        assert _chart(db, ath).phone == phone
    finally:
        _chart(db, "kanthi").phone = None
        _chart(db, "guest").phone = None
        db.execute(delete(PatientSession).where(PatientSession.patient_id == "guest"))
        db.commit()
        _forget_athlete(db, ath)


# --- the other doors -----------------------------------------------------------------------------


def test_enroll_never_claims_a_personal_or_athlete_row(client, db):
    headers, data = _join(client, phone=None, email="signin.paths.4@example.com")
    personal_id = data["me"]["patient"]["id"]
    _, adata = _athlete(client, None, "signin.paths.4@athletes.medpull.demo")
    ath = adata["me"]["patient"]["id"]
    try:
        for pid in (personal_id, ath):
            resp = client.post("/api/mobile/enroll", json={
                "patient_id": pid, "hospital_id": "hosp_demo", "phone": "+15125558104"})
            assert resp.status_code == 404, (pid, resp.text)
        # Nor does a personal space pair with an athlete row as if it were a chart.
        assert client.post("/api/mobile/personal/link-hospital", headers=headers, json={
            "mode": "enroll", "hospital_id": "hosp_demo", "patient_id": ath}).status_code == 404
    finally:
        _forget_athlete(db, ath)
        _forget(db, personal_id)


def test_join_shares_an_athletes_number_but_points_at_a_chart_or_a_space(client, db):
    phone = "+15125558105"
    _, adata = _athlete(client, phone, "signin.paths.5@athletes.medpull.demo")
    ath = adata["me"]["patient"]["id"]
    joined_id = None
    personal_id = None
    try:
        joined = client.post("/api/mobile/join", json={
            "hospital_id": "hosp_demo", "name": "Steve Joiner", "phone": phone})
        assert joined.status_code == 200, joined.text
        joined_id = joined.json()["me"]["patient"]["id"]
        assert _chart(db, joined_id).phone == phone and _chart(db, ath).phone == phone
        # Now a chart holds it: the next join is sent to find that record.
        dup = client.post("/api/mobile/join", json={
            "hospital_id": "hosp_demo", "name": "Steve Joiner", "phone": phone})
        assert dup.status_code == 409 and "find your record" in dup.json()["detail"]
        # A personal space holding a number is sent back into the app, even
        # when an athlete row holds it too; a chart always wins the message.
        _, pdata = _join(client, phone="+15125558106", email="signin.paths.5@example.com")
        personal_id = pdata["me"]["patient"]["id"]
        _, a2 = _athlete(client, "+15125558106", "signin.paths.5b@athletes.medpull.demo")
        try:
            personal_409 = client.post("/api/mobile/join", json={
                "hospital_id": "hosp_demo", "name": "Ada Runner", "phone": "+15125558106"})
            assert personal_409.status_code == 409
            assert "sign in" in personal_409.json()["detail"]
        finally:
            _forget_athlete(db, a2["me"]["patient"]["id"])
    finally:
        _forget_athlete(db, ath)
        if joined_id:
            _forget_patient(db, joined_id)
        if personal_id:
            _forget(db, personal_id)


def test_personal_space_with_an_athletes_number_needs_no_code_and_pairs_with_nothing(client, db):
    """personal/join once took any non-personal holder for a hospital chart:
    an athlete row made it demand a code (and refuse without texts), and a
    verified join would have paired the space with the athlete row."""
    phone = "+15125558107"
    _, adata = _athlete(client, phone, "signin.paths.6@athletes.medpull.demo")
    ath = adata["me"]["patient"]["id"]
    personal_id = None
    try:
        headers, data = _join(client, phone=phone, email="signin.paths.6@example.com")
        personal_id = data["me"]["patient"]["id"]
        assert data["status"] == "enrolled"
        assert _chart(db, personal_id).linked_patient_id is None
        assert _chart(db, ath).linked_patient_id is None
        assert _chart(db, personal_id).phone == phone and _chart(db, ath).phone == phone
        assert [p["kind"] for p in data["me"]["profiles"]] == ["personal"]
        # The phone sign-in finds the personal space, not the athlete.
        back = client.post("/api/mobile/personal/signin", json={"phone": phone})
        assert back.status_code == 409  # no texts on this server: use the email login
    finally:
        _forget_athlete(db, ath)
        if personal_id:
            _forget(db, personal_id)


def test_console_leaves_the_persons_other_rows_alone(client, db):
    """The console's phone card and app-link list see only clinic charts: a
    personal space or an athlete account sharing the number is reported,
    never moved and never offered as a record to fold into the chart."""
    from app import identity

    phone = "+15125558108"
    _, adata = _athlete(client, phone, "signin.paths.7@athletes.medpull.demo", name="Guest Athlete")
    ath = adata["me"]["patient"]["id"]
    try:
        result = identity.set_phone(db, _chart(db, "guest"), phone)
        assert result["phone"] == phone and result["moved_from"] == []
        assert result["shared_with"] == [ath]
        assert _chart(db, ath).phone == phone
        # Another CHART holding it is still refused, then moved with force.
        with pytest.raises(identity.IdentityError) as refused:
            identity.set_phone(db, _chart(db, "kanthi"), phone)
        assert refused.value.extra["holders"] == ["guest"]
        moved = identity.set_phone(db, _chart(db, "kanthi"), phone, force=True)
        assert moved["moved_from"] == ["guest"] and moved["shared_with"] == [ath]
        assert _chart(db, ath).phone == phone
        # The app-link candidates for the chart never include the athlete.
        ids = {c["patient_id"] for c in identity.link_candidates(db, _chart(db, "kanthi"))}
        assert ath not in ids
    finally:
        _chart(db, "kanthi").phone = None
        _chart(db, "guest").phone = None
        db.commit()
        _forget_athlete(db, ath)


def test_startup_fixer_leaves_athletes_and_spaces_off_every_roster(client, db):
    """_ensure_hospitals gives orphaned charts a hospital. It must skip a
    personal space and an athlete account — and undo the damage where an
    earlier form of the check had already put athletes on the roster."""
    from app.main import _ensure_hospitals

    _, adata = _athlete(client, None, "signin.paths.8@athletes.medpull.demo")
    ath = adata["me"]["patient"]["id"]
    _, pdata = _join(client, phone=None, email="signin.paths.8@example.com")
    personal_id = pdata["me"]["patient"]["id"]
    try:
        row = _chart(db, ath)
        row.hospital_id = "hosp_demo"  # what the old fixer did on every cold start
        db.commit()
        _ensure_hospitals()
        assert _chart(db, ath).hospital_id is None
        assert _chart(db, personal_id).hospital_id is None
        found = client.post("/api/mobile/patients/search",
                            json={"hospital_id": "hosp_demo", "name": "Steve Test"}).json()
        assert ath not in {c["patient_id"] for c in found["candidates"]}
    finally:
        _forget_athlete(db, ath)
        _forget(db, personal_id)


def test_texts_reach_the_chart_not_the_athlete_with_the_fresher_session(client, db):
    from app.tasks import service as tasks

    phone = "+15125558109"
    headers, adata = _athlete(client, phone, "signin.paths.9@athletes.medpull.demo")
    ath = adata["me"]["patient"]["id"]
    try:
        chart = _chart(db, "guest")
        chart.phone = phone
        db.commit()
        # The athlete is the one using the app right now.
        assert client.get("/api/mobile/me", headers=headers).status_code == 200
        assert tasks.patient_for_phone(db, phone).id == "guest"
    finally:
        _chart(db, "guest").phone = None
        db.commit()
        _forget_athlete(db, ath)


# --- sessions and the consent ---------------------------------------------------------------------


def test_signout_of_one_space_leaves_the_other_spaces_session_alone(client, db):
    headers, data = _join(client, phone=None, email="signin.paths.10@example.com")
    personal_id = data["me"]["patient"]["id"]
    clinic_id = None
    try:
        linked = client.post("/api/mobile/personal/link-hospital", headers=headers, json={
            "mode": "join", "hospital_id": "hosp_demo", "had_surgery": False})
        assert linked.status_code == 200, linked.text
        clinic_id = linked.json()["me"]["patient"]["id"]
        clinic_headers = {"Authorization": f"Bearer {linked.json()['session_token']}"}
        # Sign the personal token out: the chart's token still works, and a
        # switch from it mints a fresh personal token; the old one stays dead.
        assert client.post("/api/mobile/signout", headers=headers).status_code == 200
        assert client.get("/api/mobile/me", headers=headers).status_code == 401
        assert client.get("/api/mobile/me", headers=clinic_headers).status_code == 200
        switched = client.post("/api/mobile/profiles/switch", headers=clinic_headers,
                               json={"patient_id": personal_id})
        assert switched.status_code == 200
        fresh = {"Authorization": f"Bearer {switched.json()['session_token']}"}
        assert client.get("/api/mobile/me", headers=fresh).status_code == 200
        assert client.get("/api/mobile/me", headers=headers).status_code == 401
        # Signing out is idempotent, and a revoked token cannot sign out
        # anything else.
        assert client.post("/api/mobile/signout", headers=headers).status_code == 200
        assert client.get("/api/mobile/me", headers=clinic_headers).status_code == 200
    finally:
        if clinic_id:
            db.execute(delete(Consent).where(Consent.patient_id == clinic_id))
            db.commit()
            _forget_patient(db, clinic_id)
        _forget(db, personal_id)


def test_revoked_session_row_is_not_reused_by_a_new_login(client, db):
    _, adata = _athlete(client, None, "signin.paths.11@athletes.medpull.demo")
    ath = adata["me"]["patient"]["id"]
    try:
        first = adata["session_token"]
        assert client.post("/api/mobile/signout",
                           headers={"Authorization": f"Bearer {first}"}).status_code == 200
        again = client.post("/api/mobile/sports/login",
                            json={"email": "signin.paths.11@athletes.medpull.demo",
                                  "password": ATHLETE_PWD})
        assert again.status_code == 200
        second = again.json()["session_token"]
        assert second != first
        rows = {hashlib.sha256(t.encode()).hexdigest(): t for t in (first, second)}
        sessions = db.scalars(select(PatientSession).where(PatientSession.patient_id == ath)).all()
        by_hash = {s.token_hash: s for s in sessions}
        assert by_hash[hashlib.sha256(first.encode()).hexdigest()].revoked_at is not None
        assert by_hash[hashlib.sha256(second.encode()).hexdigest()].revoked_at is None
        assert len(rows) == 2
    finally:
        _forget_athlete(db, ath)


def test_consent_is_recorded_once_per_version_and_again_when_the_version_moves(
    client, db, monkeypatch
):
    headers, data = _join(client, phone=None, email="signin.paths.12@example.com")
    pid = data["me"]["patient"]["id"]
    try:
        assert len(_consents(db, pid)) == 1
        # Accepting the same version again (a second phone, a re-login that
        # still sends the form) adds nothing.
        same = client.post("/api/mobile/consent", headers=headers, json=_consent())
        assert same.status_code == 200 and same.json()["consent"]["needs_consent"] is False
        assert len(_consents(db, pid)) == 1
        # A changed answer is a new acceptance.
        changed = client.post("/api/mobile/consent", headers=headers, json=_consent(research=False))
        assert changed.status_code == 200
        assert len(_consents(db, pid)) == 2
        assert _consents(db, pid)[-1].scopes["research_use"] is False
        # A new version re-gates the account and records once more.
        previous = auth.CONSENT_VERSION
        monkeypatch.setattr(auth, "CONSENT_VERSION", "2099-01-01.1")
        me = client.get("/api/mobile/me", headers=headers).json()
        assert me["consent"]["needs_consent"] is True
        assert me["consent"]["current_version"] == "2099-01-01.1"
        stale = client.post("/api/mobile/consent", headers=headers,
                            json={**_consent(), "version": previous})
        assert stale.status_code == 409
        fresh = client.post("/api/mobile/consent", headers=headers,
                            json={**_consent(), "version": "2099-01-01.1"})
        assert fresh.status_code == 200 and fresh.json()["consent"]["needs_consent"] is False
        assert len(_consents(db, pid)) == 3
    finally:
        _forget(db, pid)


# --- the App Store -------------------------------------------------------------------------------


def test_strict_production_server_accepts_a_sandbox_transaction(client, db, monkeypatch):
    """App Review and TestFlight buy in the sandbox. A strict Production
    server must honour those, refuse anything else (Xcode), and record the
    grant as verified."""
    from app.personal import subscription as sub
    from tests.test_personal import _fake_jws

    monkeypatch.setattr(settings, "apple_subscription_verify", "strict")
    monkeypatch.setattr(settings, "apple_environment", "Production")
    # The chain check itself is exercised elsewhere; here it stands in for a
    # payload that reached Apple's root.
    monkeypatch.setattr(sub, "verify_strict", lambda jws: sub.decode_jws(jws)[1])
    headers, data = _join(client, phone=None, email="signin.paths.13@example.com")
    pid = data["me"]["patient"]["id"]
    try:
        from datetime import datetime, timedelta

        expires = int((datetime.now() + timedelta(days=30)).timestamp() * 1000)
        tx = {"bundleId": settings.ios_bundle_id,
              "productId": "com.medpull.recovery.personal.annual",
              "originalTransactionId": "4000000001", "transactionId": "4000000002",
              "expiresDate": expires, "purchaseDate": expires - 365 * 86400000}
        sandbox = client.post("/api/mobile/personal/subscription/apple", headers=headers,
                              json={"jws": _fake_jws({**tx, "environment": "Sandbox"})})
        assert sandbox.status_code == 200, sandbox.text
        assert sandbox.json()["entitlement"]["verified"] is True
        assert sandbox.json()["subscription"]["state"] == "active"
        production = client.post("/api/mobile/personal/subscription/apple", headers=headers,
                                 json={"jws": _fake_jws({**tx, "environment": "Production"})})
        assert production.status_code == 200
        xcode = client.post("/api/mobile/personal/subscription/apple", headers=headers,
                            json={"jws": _fake_jws({**tx, "originalTransactionId": "4000000009",
                                                    "environment": "Xcode"})})
        assert xcode.status_code == 422 and "Xcode" in xcode.json()["detail"]
    finally:
        _forget(db, pid)
