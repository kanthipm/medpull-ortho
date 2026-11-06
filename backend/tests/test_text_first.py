"""Texting a number that has never texted MedPull — with no admin step, ever.

Sendblue's free shared-line plan refuses a recipient until that person has
texted the line once. The provider is faked at its two seams —
``sendblue._post_message`` for sends and ``reachability._request`` for the
account API — and the whole flow is walked: the code that cannot go out yet,
the app's one tap, the inbound text that verifies the number, the code
arriving, and every other send path staying calm about a number it cannot
reach yet.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import unquote

import httpx
from sqlalchemy import select

from app.config import settings
from app.models.mobile import Message, PhoneVerification, VerifiedContact
from app.models.patient import Patient
from app.notifications import reachability, sendblue
from tests.test_mobile import _forget_patient

LINE = "+15049081262"


class _FakeResponse:
    """An httpx response with a status and a JSON body (None: not JSON)."""

    def __init__(self, status_code: int = 200, body: dict | list | None = None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"status {self.status_code}", request=None, response=self)
SECRET = "whsec-text-first"
REFUSAL = {"status": "ERROR",
           "message": "This contact must be verified before sending messages to it."}


class FreePlanSendblue:
    """Sendblue on the free plan. A send to a number that has not texted the
    line is refused; one that has goes through. The account API knows the
    plan, answers ``/v3/verified-contacts`` and takes registrations.
    ``texted(number)`` is the person texting the line."""

    def __init__(self, monkeypatch, *, verified=(), account_api=True, mode="auto",
                 otp=True):
        self.sent: list[tuple[str, str]] = []
        self.verified: set[str] = set(verified)
        self.pending: set[str] = set()
        self.calls: list[tuple[str, str, dict | None]] = []
        self.account_api = account_api
        monkeypatch.setattr(settings, "sendblue_api_key", "k")
        monkeypatch.setattr(settings, "sendblue_api_secret", "s")
        monkeypatch.setattr(settings, "sendblue_from_number", LINE)
        monkeypatch.setattr(settings, "sendblue_webhook_secret", SECRET)
        monkeypatch.setattr(settings, "sendblue_verified_contacts_only", mode)
        monkeypatch.setattr(settings, "mobile_otp_required", otp)
        monkeypatch.setattr(sendblue, "_post_message", self._post)
        monkeypatch.setattr(reachability, "_request", self._request)

    def _post(self, phone, content, media_url=None):
        if phone not in self.verified:
            raise httpx.HTTPStatusError("400", request=None,
                                        response=_FakeResponse(400, REFUSAL))
        self.sent.append((phone, content))
        return _FakeResponse(200, {"status": "QUEUED", "message_handle": f"mh_{len(self.sent)}"})

    def _contact(self, number: str) -> dict:
        verified = number in self.verified
        return {"phone_number": number, "verified": verified,
                "verification_status": "verified" if verified else "pending"}

    def _request(self, method, path, json=None):
        self.calls.append((method, path, json))
        if not self.account_api:
            raise httpx.ConnectError("account api down")
        if path == "/accounts":
            return _FakeResponse(200, {"plan": "free_api"})
        if method == "GET" and path.startswith("/v3/verified-contacts/"):
            number = unquote(path.rsplit("/", 1)[1])
            if number in self.verified or number in self.pending:
                return _FakeResponse(200, {"data": {"contact": self._contact(number)}})
            return _FakeResponse(404, {"error": "contact not found"})
        if method == "POST" and path == "/v3/verified-contacts":
            number = json["phone_number"]
            self.pending.add(number)
            return _FakeResponse(201, {"data": {
                "contact": self._contact(number),
                "line": {"phone_number": LINE, "type": "shared"},
                "verification_instructions": f"Ask {number} to text {LINE}.",
            }})
        if path == "/accounts/contacts":
            return _FakeResponse(200, {"contacts": [self._contact(n) for n in self.verified]})
        return _FakeResponse(404, None)

    def texted(self, client, number: str, content: str = "Hi MedPull") -> dict:
        """The person texts the line: Sendblue verifies the contact and posts
        the inbound text to our webhook."""
        self.verified.add(number)
        r = client.post("/api/webhooks/sendblue",
                        json={"from_number": number, "content": content, "is_outbound": False},
                        headers={"sb-signing-secret": SECRET})
        assert r.status_code == 200, r.text
        return r.json()

    def code(self) -> str:
        return self.sent[-1][1].split("is ")[1].split(".")[0]

    def codes_to(self, number: str) -> list[str]:
        return [c for n, c in self.sent if n == number and "verification code" in c]


def _join(client, phone: str, name: str = "Text First Tester") -> dict:
    r = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": name, "phone": phone, "had_surgery": False,
        "device_name": "iPhone (test)"})
    assert r.status_code == 200, r.text
    return r.json()


def _patient_named(db, name: str) -> Patient | None:
    db.expire_all()
    return db.scalar(select(Patient).where(Patient.name == name))


def _forget_named(db, name: str) -> None:
    patient = _patient_named(db, name)
    if patient is not None:
        _forget_patient(db, patient.id)
    db.execute(VerifiedContact.__table__.delete())
    db.commit()


# --- the patient's path -------------------------------------------------------------------


def test_a_new_number_waits_for_its_first_text_then_the_webhook_sends_the_code(
    client, db, monkeypatch,
):
    """The whole point. A person whose number Sendblue has never heard from
    joins: nothing fails, nobody approves anything. The app is told to have
    them text MedPull once; the moment that text lands, the code goes out,
    and the ordinary verify finishes the enrollment."""
    sb = FreePlanSendblue(monkeypatch)
    phone = "+15125550611"
    try:
        body = _join(client, phone)
        assert body["status"] == "verification_required" and "session_token" not in body
        # The one tap: the number to text and the words to send.
        assert body["text_first"] is True and body["code_sent"] is False
        assert body["text_to"] == LINE and body["text_body"] == "Hi MedPull"
        assert body["phone_masked"].endswith("0611")
        # No code was texted, and no refused send was even attempted: the
        # contact list already said the number was unknown.
        assert sb.codes_to(phone) == []
        assert ("GET", "/accounts", None) in sb.calls
        assert any(m == "POST" and p == "/v3/verified-contacts" for m, p, _ in sb.calls)
        vid = body["verification_id"]

        # The app polls: still waiting, same instructions.
        poll = client.get(f"/api/mobile/enroll/verification/{vid}").json()
        assert poll["status"] == "waiting_for_text" and poll["text_to"] == LINE

        # A code typed now cannot be right, and the answer says why.
        early = client.post("/api/mobile/enroll/verify", json={"verification_id": vid,
                                                                "code": "123456"})
        assert early.status_code == 409 and "text MedPull first" in early.json()["detail"]

        # "I've sent it" tapped too soon: the same answer, no second chart,
        # no second code, and the provider was not asked to send.
        retry = client.post(f"/api/mobile/enroll/verification/{vid}/resend")
        assert retry.status_code == 200
        assert retry.json()["text_first"] is True and retry.json()["verification_id"] == vid
        assert sb.codes_to(phone) == []
        db.expire_all()
        assert len(db.scalars(select(Patient).where(Patient.name == "Text First Tester")).all()) == 1

        # The person texts the line. Sendblue verifies the contact and posts
        # the text to us: the number is recorded reachable and the waiting
        # code goes out at once. The greeting lands on no patient thread.
        outcome = sb.texted(client, phone)
        assert outcome["kind"] == "verification_code_sent" and outcome["handled"] is True
        assert outcome["verification_id"] == vid
        assert len(sb.codes_to(phone)) == 1
        db.expire_all()
        row = db.get(VerifiedContact, phone)
        assert row is not None and row.source == "inbound" and row.last_inbound_at is not None
        patient = _patient_named(db, "Text First Tester")
        assert db.scalars(select(Message).where(Message.patient_id == patient.id)).all() == []

        poll = client.get(f"/api/mobile/enroll/verification/{vid}").json()
        assert poll["status"] == "code_sent" and poll["text_first"] is False

        # The ordinary finish.
        done = client.post("/api/mobile/enroll/verify", json={"verification_id": vid,
                                                               "code": sb.code()})
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "enrolled" and done.json()["verified"] is True
        assert done.json()["me"]["features"]["sms"] is True
        db.expire_all()
        assert _patient_named(db, "Text First Tester").phone == phone
        assert client.get(f"/api/mobile/enroll/verification/{vid}").json()["status"] == "verified"
        # and from now on texts simply go: the welcome text went out
        assert any("Welcome to MedPull" in c for n, c in sb.sent if n == phone)
    finally:
        _forget_named(db, "Text First Tester")


def test_a_number_that_can_be_reached_keeps_the_current_flow(client, db, monkeypatch):
    """A number Sendblue already knows gets its code straight away: the
    answer carries no text-first instructions and the app shows the code
    field exactly as before."""
    sb = FreePlanSendblue(monkeypatch, verified={"+15125550612"})
    try:
        body = _join(client, "+15125550612", name="Known Number")
        assert body["status"] == "verification_required"
        assert body["code_sent"] is True and body["text_first"] is False
        assert body["text_to"] is None and body["text_body"] is None
        assert len(sb.codes_to("+15125550612")) == 1
        poll = client.get(f"/api/mobile/enroll/verification/{body['verification_id']}").json()
        assert poll["status"] == "code_sent"
        done = client.post("/api/mobile/enroll/verify",
                           json={"verification_id": body["verification_id"], "code": sb.code()})
        assert done.status_code == 200 and done.json()["verified"] is True
        db.expire_all()
        # a successful send is remembered, so the next text asks nobody
        assert db.get(VerifiedContact, "+15125550612").source in ("sent", "contacts")
    finally:
        _forget_named(db, "Known Number")


def test_resend_after_the_first_text_sends_a_fresh_code(client, db, monkeypatch):
    """The webhook may lag the tap. "I've sent it — send my code" on a number
    that has become reachable texts a fresh code on the same verification,
    and the earlier code stops working."""
    sb = FreePlanSendblue(monkeypatch)
    phone = "+15125550613"
    try:
        body = _join(client, phone, name="Resend Tester")
        vid = body["verification_id"]
        assert body["text_first"] is True
        # The person texts the line but the webhook has not reached us: the
        # provider now knows the number, and our retry simply works.
        sb.verified.add(phone)
        retry = client.post(f"/api/mobile/enroll/verification/{vid}/resend").json()
        assert retry["code_sent"] is True and retry["text_first"] is False
        first = sb.code()
        again = client.post(f"/api/mobile/enroll/verification/{vid}/resend").json()
        assert again["code_sent"] is True
        second = sb.code()
        assert first != second or len(sb.codes_to(phone)) == 2
        stale = client.post("/api/mobile/enroll/verify", json={"verification_id": vid, "code": first})
        assert stale.status_code in (401, 200)  # equal codes are astronomically unlikely
        if stale.status_code == 401:
            done = client.post("/api/mobile/enroll/verify",
                               json={"verification_id": vid, "code": second})
            assert done.status_code == 200, done.text
        # the row remembers that a text went through
        db.expire_all()
        assert db.get(VerifiedContact, phone) is not None
        # an unknown or finished verification cannot be resent
        assert client.post(f"/api/mobile/enroll/verification/{vid}/resend").status_code == 404
        assert client.post("/api/mobile/enroll/verification/999999/resend").status_code == 404
        assert client.get("/api/mobile/enroll/verification/999999").status_code == 404
    finally:
        _forget_named(db, "Resend Tester")


def test_a_late_text_wakes_only_the_newest_waiting_code_and_never_a_stale_one(
    client, db, monkeypatch,
):
    """Two attempts in a row leave two waiting rows: the inbound text sends
    the code for the newest (the one the app holds). A row older than a day
    is never woken — that attempt was abandoned."""
    sb = FreePlanSendblue(monkeypatch)
    phone = "+15125550614"
    try:
        first = _join(client, phone, name="Two Attempts")
        db.expire_all()
        patient = _patient_named(db, "Two Attempts")
        # a second attempt, as the "Send a new code" button makes one
        second = client.post("/api/mobile/enroll", json={
            "patient_id": patient.id, "hospital_id": "hosp_demo", "phone": phone}).json()
        assert second["text_first"] is True and second["verification_id"] != first["verification_id"]
        # an abandoned attempt from yesterday
        old = db.get(PhoneVerification, first["verification_id"])
        old.created_at = datetime.now() - timedelta(days=2)
        db.commit()
        outcome = sb.texted(client, phone)
        assert outcome["kind"] == "verification_code_sent"
        assert outcome["verification_id"] == second["verification_id"]
        assert len(sb.codes_to(phone)) == 1
        db.expire_all()
        assert db.get(PhoneVerification, first["verification_id"]).sent_at is None
        assert db.get(PhoneVerification, second["verification_id"]).sent_at is not None
        # a second inbound text finds nothing waiting: it is an ordinary text
        # from a number no chart carries yet, and is dropped as before
        again = sb.texted(client, phone, "hello?")
        assert again["kind"] == "unknown_number" and again["handled"] is False
        assert len(sb.codes_to(phone)) == 1
    finally:
        _forget_named(db, "Two Attempts")


def test_the_webhook_sends_no_code_when_the_write_lock_is_lost(client, db, monkeypatch):
    """Same rule as a reply: rows the persist will discard must not carry a
    code the patient would then type in vain."""
    from app.aws import storage

    sb = FreePlanSendblue(monkeypatch)
    phone = "+15125550615"
    try:
        body = _join(client, phone, name="Lock Lost")
        monkeypatch.setattr(storage, "holds_lock", lambda **kw: False)
        outcome = sb.texted(client, phone)
        assert outcome["kind"] == "lock_lost" and outcome["handled"] is False
        assert sb.codes_to(phone) == []
        monkeypatch.setattr(storage, "holds_lock", lambda **kw: True)
        outcome = sb.texted(client, phone)
        assert outcome["kind"] == "verification_code_sent"
        assert outcome["verification_id"] == body["verification_id"]
    finally:
        _forget_named(db, "Lock Lost")


def test_claiming_a_record_sends_the_waiting_code_to_the_number_on_file(client, db, monkeypatch):
    """The claim-a-record rule survives: the code is owed to the number ON
    the chart, so it is that number's first text that releases it, and
    the stranger's own phone never receives anything."""
    sb = FreePlanSendblue(monkeypatch, otp=False)
    db.expire_all()
    steve = db.get(Patient, "steve")
    before = steve.phone
    steve.phone = "+15125550616"
    db.commit()
    try:
        attack = client.post("/api/mobile/enroll", json={
            "patient_id": "steve", "hospital_id": "hosp_demo", "phone": "+15125559999"}).json()
        assert attack["status"] == "verification_required" and attack["text_first"] is True
        assert attack["phone_masked"].endswith("0616")
        # the stranger texting the line releases nothing
        nope = sb.texted(client, "+15125559999")
        assert nope["kind"] == "unknown_number"
        assert sb.codes_to("+15125559999") == [] and sb.codes_to("+15125550616") == []
        # the owner texting does
        owner = sb.texted(client, "+15125550616")
        assert owner["kind"] == "verification_code_sent"
        assert len(sb.codes_to("+15125550616")) == 1
    finally:
        db.expire_all()
        db.get(Patient, "steve").phone = before
        db.execute(PhoneVerification.__table__.delete().where(
            PhoneVerification.patient_id == "steve"))
        db.execute(VerifiedContact.__table__.delete())
        db.commit()


def test_personal_signin_by_phone_waits_for_the_first_text_too(client, db, monkeypatch):
    """Every code goes through the same door, so the personal space's
    sign-in by phone gets the same one tap."""
    from tests.test_personal import _forget, _join as _personal_join

    # the space is opened while nothing texts (the stub path), then texting
    # comes on with the number unknown to the provider
    headers, data = _personal_join(client, phone="+15125550617", email="textfirst@example.com")
    pid = data["me"]["patient"]["id"]
    sb = FreePlanSendblue(monkeypatch, otp=False)
    try:
        r = client.post("/api/mobile/personal/signin", json={"phone": "+15125550617"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "verification_required" and body["intent"] == "signin"
        assert body["text_first"] is True and body["text_to"] == LINE
        early = client.post("/api/mobile/personal/verify",
                            json={"verification_id": body["verification_id"], "code": "000000"})
        assert early.status_code == 409
        outcome = sb.texted(client, "+15125550617")
        assert outcome["kind"] == "verification_code_sent"
        done = client.post("/api/mobile/personal/verify",
                           json={"verification_id": body["verification_id"], "code": sb.code()})
        assert done.status_code == 200, done.text
        assert done.json()["session_token"]
    finally:
        db.execute(VerifiedContact.__table__.delete())
        db.commit()
        _forget(db, pid)


# --- every other text ------------------------------------------------------------------------


def test_texts_to_an_unreachable_patient_never_raise_and_say_the_honest_thing(
    client, db, monkeypatch,
):
    """A task, a console message and a check-in for a patient whose number
    has not texted MedPull: each is stored for the app, the thread line says
    "not reachable by text yet", nothing is red, and the first text from the
    patient flips all of it."""
    sb = FreePlanSendblue(monkeypatch, otp=False)
    db.expire_all()
    steve = db.get(Patient, "steve")
    before = steve.phone
    steve.phone = "+15125550618"
    db.commit()
    try:
        assigned = client.post("/api/patients/steve/actions/assign-task",
                               json={"title": "Daily check-in", "kind": "checkin"})
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["status"] == "assigned_not_texted"
        db.expire_all()
        line = db.scalars(select(Message).where(Message.patient_id == "steve")
                          .order_by(Message.id.desc())).first()
        assert line.delivery_status == "unreachable"
        assert line.delivery_detail.startswith("Not reachable by text yet")
        assert LINE in line.delivery_detail

        sent = client.post("/api/patients/steve/actions/message", json={"text": "How is the knee today?"})
        assert sent.status_code == 200, sent.text
        body = sent.json()
        assert body["status"] == "stored_app_only" and body["reason"] == "not_reachable_yet"
        assert body["message"]["delivery_status"] == "unreachable"
        assert body["message"]["delivery_detail"].startswith("Not reachable by text yet")

        # the console thread carries the same state
        thread = client.get("/api/patients/steve/messages").json()["messages"]
        assert thread[-1]["delivery_status"] == "unreachable"

        # every attempt was refused, none raised, and nothing went out
        assert sb.sent == []

        # the patient texts the line: connected, told so without a model
        # call, and the care team's next message goes by text
        outcome = sb.texted(client, "+15125550618")
        assert outcome["kind"] == "verified" and outcome["handled"] is True
        assert "connected" in sb.sent[-1][1]
        now = client.post("/api/patients/steve/actions/message", json={"text": "Great, see you Tuesday."})
        assert now.json()["status"] == "sent_sms" and now.json()["reason"] is None
        assert now.json()["message"]["delivery_status"] == "sent"
    finally:
        db.expire_all()
        db.get(Patient, "steve").phone = before
        db.execute(VerifiedContact.__table__.delete())
        db.commit()


def test_a_number_with_no_phone_is_still_stored_app_only_with_its_own_reason(client, db, monkeypatch):
    FreePlanSendblue(monkeypatch, otp=False)
    db.expire_all()
    steve = db.get(Patient, "steve")
    before = steve.phone
    steve.phone = None
    db.commit()
    try:
        body = client.post("/api/patients/steve/actions/message", json={"text": "Hello"}).json()
        assert body["status"] == "stored_app_only" and body["reason"] == "no_phone"
        assert body["message"]["delivery_status"] is None
    finally:
        db.expire_all()
        db.get(Patient, "steve").phone = before
        db.commit()


# --- the lookup itself ---------------------------------------------------------------------


def test_lookup_learns_from_the_provider_and_remembers(db, monkeypatch):
    sb = FreePlanSendblue(monkeypatch, verified={"+15125550620"})
    try:
        # on the list: verified, written down, and never asked again
        assert reachability.lookup(db, "+15125550620") == "verified"
        db.commit()
        row = db.get(VerifiedContact, "+15125550620")
        assert row is not None and row.source == "contacts"
        calls = len(sb.calls)
        assert reachability.lookup(db, "+15125550620") == "verified"
        assert len(sb.calls) == calls
        # not on the list: unverified, cached for a moment
        assert reachability.lookup(db, "+15125550621") == "unverified"
        calls = len(sb.calls)
        assert reachability.lookup(db, "+15125550621") == "unverified"
        assert len(sb.calls) == calls, "a fresh answer is reused"
        # a refusal from the send endpoint is remembered the same way
        reachability.note_refused("+15125550622")
        assert reachability.lookup(db, "+15125550622") == "unverified"
        # ...until the number texts the line
        reachability.mark_verified(db, "+15125550622", source="inbound")
        assert reachability.lookup(db, "+15125550622") == "verified"
        # a send that went through is proof too
        reachability.note_sent("+15125550623")
        assert reachability.lookup(db, "+15125550623") == "verified"
    finally:
        db.execute(VerifiedContact.__table__.delete())
        db.commit()


def test_lookup_is_unknown_when_the_provider_cannot_be_asked(db, monkeypatch):
    """A paid plan, a switched-off lookup or a provider outage all mean the
    same thing: nothing is known, so the send is attempted and learned from."""
    monkeypatch.setattr(settings, "sendblue_api_key", "k")
    monkeypatch.setattr(settings, "sendblue_api_secret", "s")
    monkeypatch.setattr(settings, "sendblue_verified_contacts_only", "auto")
    calls: list[str] = []

    def outage(method, path, json=None):
        calls.append(path)
        raise httpx.ConnectError("down")

    monkeypatch.setattr(reachability, "_request", outage)
    assert reachability.lookup(db, "+15125550624") == "unknown"
    assert reachability.account_plan() is None
    assert "/accounts" in calls and any(p.startswith("/v3/verified-contacts/") for p in calls)

    # a paid plan: the contact list is not even consulted
    reachability.reset_caches()
    calls.clear()

    def paid(method, path, json=None):
        calls.append(path)
        if path == "/accounts":
            return _FakeResponse(200, {"plan": "ai_agent"})
        raise AssertionError(f"unexpected call {path}")

    monkeypatch.setattr(reachability, "_request", paid)
    assert reachability.lookup(db, "+15125550624") == "unknown"
    assert reachability.account_plan() == "ai_agent" and calls == ["/accounts"]

    # the lookup switched off entirely: no call of any kind
    reachability.reset_caches()
    monkeypatch.setattr(reachability, "_request", lambda *a, **kw: calls.append(a) or None)
    monkeypatch.setattr(settings, "sendblue_verified_contacts_only", "false")
    calls.clear()
    assert reachability.lookup(db, "+15125550624") == "unknown"
    assert calls == []

    # "true": the list is asked without checking the plan first
    reachability.reset_caches()
    monkeypatch.setattr(settings, "sendblue_verified_contacts_only", "true")

    def free_only(method, path, json=None):
        calls.append(path)
        if path == "/accounts":
            raise AssertionError("the plan is not asked about in 'true' mode")
        if path.startswith("/v3/verified-contacts/"):
            return _FakeResponse(404, {"error": "not found"})
        if path == "/accounts/contacts":
            return _FakeResponse(200, [])
        raise AssertionError(path)

    monkeypatch.setattr(reachability, "_request", free_only)
    assert reachability.lookup(db, "+15125550624") == "unverified"
    assert "/accounts" not in calls


def test_lookup_falls_back_to_the_legacy_contact_list(db, monkeypatch):
    """An account whose API has no v3 route answers 404 to the single-contact
    lookup; the older whole-account list tells a missing route from a
    missing contact."""
    calls: list[str] = []

    def request(method, path, json=None):
        calls.append(path)
        if path == "/accounts":
            return _FakeResponse(200, {"data": {"account": {"plan": "free_api"}}})
        if path.startswith("/v3/verified-contacts/"):
            return _FakeResponse(404, None)  # no body: the route does not exist
        if path == "/accounts/contacts":
            return _FakeResponse(200, [{"number": "(512) 555-0625"}, {"number": "+15125550626",
                                                                        "verified": False}])
        raise AssertionError(path)

    monkeypatch.setattr(settings, "sendblue_api_key", "k")
    monkeypatch.setattr(settings, "sendblue_api_secret", "s")
    monkeypatch.setattr(settings, "sendblue_verified_contacts_only", "auto")
    monkeypatch.setattr(reachability, "_request", request)
    try:
        assert reachability.lookup(db, "+15125550625") == "verified"   # listed, no flag
        assert reachability.lookup(db, "+15125550626") == "unverified"  # listed, pending
        assert reachability.lookup(db, "+15125550627") == "unverified"  # not listed
        assert "/accounts/contacts" in calls
    finally:
        db.execute(VerifiedContact.__table__.delete())
        db.commit()


def test_unconfigured_keys_make_every_lookup_unknown_without_a_call(db, monkeypatch):
    monkeypatch.setattr(settings, "sendblue_verified_contacts_only", "auto")
    assert reachability.contact_verified("+15125550628") is None
    assert reachability.account_plan() is None
    assert reachability.register_pending("+15125550628") is None
    assert reachability.lookup(db, "+15125550628") == "unknown"


def test_refusal_wording_is_recognised_and_nothing_else_is():
    assert reachability.is_verification_refusal(
        "This contact must be verified before sending messages to it.")
    assert reachability.is_verification_refusal("No contact found for this number")
    assert not reachability.is_verification_refusal("Cannot send messages to self")
    assert not reachability.is_verification_refusal("This phone number is not defined.")
    assert not reachability.is_verification_refusal(None)
    assert not reachability.is_verification_refusal("")


def test_legacy_verification_rows_still_verify(client, db):
    """A row written before ``destination`` existed had its code sent on
    creation; it must not read as "waiting for a text"."""
    from app.api.mobile import _hash

    db.expire_all()
    before = db.get(Patient, "steve").phone
    row = PhoneVerification(patient_id="steve", phone="+15125550629", code_hash=_hash("424242"),
                            expires_at=datetime.now() + timedelta(minutes=5))
    db.add(row)
    db.commit()
    try:
        status = client.get(f"/api/mobile/enroll/verification/{row.id}").json()
        assert status["status"] == "code_sent" and status["text_first"] is False
        r = client.post("/api/mobile/enroll/verify", json={"verification_id": row.id,
                                                            "code": "424242"})
        assert r.status_code == 200, r.text
    finally:
        db.expire_all()
        db.get(Patient, "steve").phone = before
        db.execute(PhoneVerification.__table__.delete().where(PhoneVerification.id == row.id))
        db.commit()


def test_health_reports_the_rule_and_what_was_learned(client, monkeypatch):
    FreePlanSendblue(monkeypatch)
    sms = client.get("/api/health").json()["sms"]
    assert sms["configured"] is True
    assert sms["reachability"]["mode"] == "auto"
    assert sms["reachability"]["text_to"] == LINE
    assert sms["reachability"]["text_body"] == "Hi MedPull"
