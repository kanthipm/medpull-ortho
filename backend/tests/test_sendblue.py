"""The patient check-in sender. httpx is always faked — no test can send."""

import httpx
import pytest

from app.config import settings
from app.notifications import sendblue
from app.notifications.sendblue import CheckinSendResult, send_checkin_message


class _FakeResponse:
    def __init__(self, status_code: int = 200, body: dict | None = None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}", request=None, response=self
            )


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "sendblue_api_key", "key-id")
    monkeypatch.setattr(settings, "sendblue_api_secret", "key-secret")
    monkeypatch.setattr(settings, "sendblue_from_number", "+15049081262")


def test_sends_formatted_message_with_normalized_phone(configured, monkeypatch):
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _FakeResponse()

    monkeypatch.setattr(sendblue.httpx, "post", fake_post)

    result = send_checkin_message("(512) 491-7035", "https://medpull.example/checkin/abc")

    assert result == CheckinSendResult(sent=True, detail="sent")
    (call,) = calls
    assert call["url"] == sendblue.SEND_URL
    assert call["headers"] == {"sb-api-key-id": "key-id", "sb-api-secret-key": "key-secret"}
    assert call["json"] == {
        "number": "+15124917035",
        # The link sits on its own labelled line so iMessage renders it as a
        # tappable link rather than burying it mid-sentence.
        "content": (
            "Your MedPull recovery check-in is ready.\n\n"
            "Start your check-in: https://medpull.example/checkin/abc"
        ),
        "from_number": "+15049081262",
    }
    assert call["timeout"] == sendblue.TIMEOUT_S


def test_from_number_omitted_when_unset(configured, monkeypatch):
    monkeypatch.setattr(settings, "sendblue_from_number", "")
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _FakeResponse()

    monkeypatch.setattr(sendblue.httpx, "post", fake_post)

    assert send_checkin_message("5124917035", "https://x.example/c").sent
    assert "from_number" not in calls[0]


def test_unconfigured_keys_never_touch_the_network(monkeypatch):
    def explode(*a, **kw):
        raise AssertionError("HTTP call attempted without Sendblue keys")

    monkeypatch.setattr(sendblue.httpx, "post", explode)

    result = send_checkin_message("+15124917035", "https://x.example/c")
    assert result.sent is False
    assert "not configured" in result.detail


def test_unusable_phone_number_fails_before_any_request(configured, monkeypatch):
    def explode(*a, **kw):
        raise AssertionError("HTTP call attempted with an unusable phone")

    monkeypatch.setattr(sendblue.httpx, "post", explode)

    result = send_checkin_message("12", "https://x.example/c")
    assert result.sent is False
    assert "phone" in result.detail


def test_api_error_reports_the_status_code(configured, monkeypatch):
    monkeypatch.setattr(sendblue.httpx, "post", lambda *a, **kw: _FakeResponse(401))

    result = send_checkin_message("+15124917035", "https://x.example/c")
    assert result.sent is False
    assert result.status_code == 401
    assert "401" in result.detail


def test_transport_failure_reports_cleanly(configured, monkeypatch):
    def fake_post(*a, **kw):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(sendblue.httpx, "post", fake_post)

    result = send_checkin_message("+15124917035", "https://x.example/c")
    assert result.sent is False
    assert result.detail.startswith("request failed")
    assert result.status_code is None


def test_api_error_carries_sendblues_reason(configured, monkeypatch):
    """The account's own number as the recipient is the one 400 a demo hits:
    the console must read "Cannot send messages to self", not just "400"."""
    monkeypatch.setattr(
        sendblue.httpx, "post",
        lambda *a, **kw: _FakeResponse(400, {"status": "ERROR", "message": "Cannot send messages to self"}),
    )
    result = sendblue.send_sms("+15049081262", "hi")
    assert result.sent is False and result.status_code == 400
    assert result.detail.startswith("Sendblue answered 400: Cannot send messages to self")
    # and the detail goes on to say what to do about it
    assert "own sending number" in result.detail


def test_a_rejection_in_a_200_body_is_not_a_send(configured, monkeypatch):
    """Sendblue echoes the message object with status ERROR for a rejection
    it made before queueing, and answers 200. Treating that as sent marked
    the thread line "texted" for a message nobody received."""
    monkeypatch.setattr(
        sendblue.httpx, "post",
        lambda *a, **kw: _FakeResponse(200, {
            "status": "ERROR",
            "error_message": "This phone number is not defined.",
            "number": "+15125550123", "is_outbound": True,
        }),
    )
    result = sendblue.send_sms("+15125550123", "hello")
    assert result.sent is False
    assert result.detail.startswith("This phone number is not defined.")
    # and it is a fault in OUR account, not about this recipient
    assert result.config_fault is True


def test_a_recipient_level_failure_is_not_reported_as_a_config_fault(configured, monkeypatch):
    monkeypatch.setattr(
        sendblue.httpx, "post",
        lambda *a, **kw: _FakeResponse(400, {"status": "ERROR",
                                             "message": "Cannot send messages to self"}),
    )
    result = sendblue.send_sms("+15049081262", "hello")
    assert result.sent is False and result.config_fault is False
    assert "Cannot send messages to self" in result.detail
    assert "own sending number" in result.detail  # and what to do about it


def test_the_missing_from_number_is_a_config_fault(configured, monkeypatch):
    monkeypatch.setattr(
        sendblue.httpx, "post",
        lambda *a, **kw: _FakeResponse(400, {
            "status": "ERROR", "error_message": 'missing required parameter: "from_number"'}),
    )
    result = sendblue.send_sms("+15125550123", "hello")
    assert result.sent is False and result.config_fault is True


def test_health_reports_whether_texting_can_work(client, configured, monkeypatch):
    monkeypatch.setattr(sendblue, "_last_config_fault", None)
    monkeypatch.setattr(sendblue, "_last_failure", None)
    body = client.get("/api/health").json()
    assert body["sms"]["configured"] is True
    assert body["sms"]["from_number"] == "+15049081262"
    # a configuration fault, once seen, is reported until the process restarts
    monkeypatch.setattr(
        sendblue.httpx, "post",
        lambda *a, **kw: _FakeResponse(400, {
            "status": "ERROR", "error_message": "This phone number is not defined."}),
    )
    sendblue.send_sms("+15125550123", "hello")
    reported = client.get("/api/health").json()["sms"]
    assert reported["config_fault"] == "This phone number is not defined."
    assert "SENDBLUE_FROM_NUMBER" in reported["hint"]


def test_a_failed_text_puts_the_reason_on_the_thread(client, db, configured, monkeypatch):
    from app.models.mobile import Message
    from sqlalchemy import select

    monkeypatch.setattr(
        sendblue.httpx, "post",
        lambda *a, **kw: _FakeResponse(400, {
            "status": "ERROR", "error_message": "This phone number is not defined."}),
    )
    db.expire_all()
    patient = db.get(__import__("app.models.patient", fromlist=["Patient"]).Patient, "grace")
    patient.phone = "+15125550777"
    db.commit()
    resp = client.post("/api/patients/grace/actions/message", json={"text": "How is today?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "stored_sms_failed"
    assert "not defined" in body["detail"]
    assert "not defined" in body["message"]["delivery_detail"]
    db.expire_all()
    row = db.scalars(select(Message).where(Message.patient_id == "grace")
                     .order_by(Message.id.desc()).limit(1)).one()
    assert row.delivery_status == "failed"
    assert row.delivery_detail.startswith(
        "Sendblue answered 400: This phone number is not defined.")
    # the patient app sees the same line, and the same reason
    from sqlalchemy import delete

    db.execute(delete(Message).where(Message.patient_id == "grace"))
    db.get(__import__("app.models.patient", fromlist=["Patient"]).Patient, "grace").phone = None
    db.commit()
    monkeypatch.setattr(sendblue, "_last_config_fault", None)


def test_a_refused_unverified_number_is_unreachable_not_failed(configured, monkeypatch):
    """Sendblue's own wording is a dead end on its own — "must be verified"
    by whom, how? The answer is the honest state plus the one thing that
    fixes it: the number has not texted MedPull yet, so ask them to. It is
    not a failure of the deployment and must not light the health banner."""
    monkeypatch.setattr(sendblue, "_last_config_fault", None)
    monkeypatch.setattr(sendblue, "_last_failure", None)
    monkeypatch.setattr(sendblue, "_last_unreachable", None)
    monkeypatch.setattr(
        sendblue.httpx, "post",
        lambda *a, **kw: _FakeResponse(400, {
            "status": "ERROR",
            "error_message": "This contact must be verified before sending messages to it."}),
    )
    result = sendblue.send_sms("+18588666257", "hello")
    assert result.sent is False
    # recipient-scoped, so not an account fault...
    assert result.config_fault is False
    # ...but a number we cannot reach YET, and the detail says what unblocks
    # it, naming the number to text
    assert result.unreachable is True
    assert result.detail.startswith("Not reachable by text yet")
    assert "+15049081262" in result.detail
    assert sendblue.delivery_status_for(result) == "unreachable"
    # health keeps the account clean and reports the number apart
    status = sendblue.status()
    assert status["config_fault"] is None and status["last_failure"] is None
    assert status["reachability"]["last_unreachable"] == "+18588666257"
    assert status["reachability"]["text_to"] == "+15049081262"
    # the same wording when the refusal comes as a 200 with status ERROR
    monkeypatch.setattr(
        sendblue.httpx, "post",
        lambda *a, **kw: _FakeResponse(200, {
            "status": "ERROR", "error_message": "No contact found for this number."}),
    )
    again = sendblue.send_sms("+18588666258", "hello")
    assert again.unreachable is True and again.sent is False


def test_a_real_recipient_failure_still_carries_the_hint(configured, monkeypatch):
    """A failure that is neither the account's nor the verified-contact rule
    keeps Sendblue's words and the operator hint, and does reach the banner."""
    monkeypatch.setattr(sendblue, "_last_config_fault", None)
    monkeypatch.setattr(sendblue, "_last_failure", None)
    monkeypatch.setattr(
        sendblue.httpx, "post",
        lambda *a, **kw: _FakeResponse(400, {"status": "ERROR",
                                             "message": "Cannot send messages to self"}),
    )
    result = sendblue.send_sms("+15049081262", "hello")
    assert result.sent is False and result.unreachable is False
    assert sendblue.delivery_status_for(result) == "failed"
    status = sendblue.status()
    assert status["last_failure"] == "Cannot send messages to self"
    assert "own sending number" in status["hint"]


def test_a_delivered_message_clears_the_failure_banner(configured, monkeypatch):
    monkeypatch.setattr(sendblue, "_last_config_fault", None)
    monkeypatch.setattr(sendblue, "_last_failure", "something older")
    monkeypatch.setattr(sendblue.httpx, "post",
                        lambda *a, **kw: _FakeResponse(200, {"message_handle": "mh_ok"}))
    assert sendblue.send_sms("+15125550123", "hello").sent is True
    assert sendblue.status()["last_failure"] is None
