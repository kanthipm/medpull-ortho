"""The patient check-in sender. httpx is always faked — no test can send."""

import httpx
import pytest

from app.config import settings
from app.notifications import sendblue
from app.notifications.sendblue import CheckinSendResult, send_checkin_message


class _FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code

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

    result = send_checkin_message("(512) 491-7035", "Steve", "https://medpull.example/checkin/abc")

    assert result == CheckinSendResult(sent=True, detail="sent")
    (call,) = calls
    assert call["url"] == sendblue.SEND_URL
    assert call["headers"] == {"sb-api-key-id": "key-id", "sb-api-secret-key": "key-secret"}
    assert call["json"] == {
        "number": "+15124917035",
        "content": (
            "Hi Steve, your MedPull recovery check-in is ready. "
            "Tap here to begin: https://medpull.example/checkin/abc"
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

    assert send_checkin_message("5124917035", "Steve", "https://x.example/c").sent
    assert "from_number" not in calls[0]


def test_unconfigured_keys_never_touch_the_network(monkeypatch):
    def explode(*a, **kw):
        raise AssertionError("HTTP call attempted without Sendblue keys")

    monkeypatch.setattr(sendblue.httpx, "post", explode)

    result = send_checkin_message("+15124917035", "Steve", "https://x.example/c")
    assert result.sent is False
    assert "not configured" in result.detail


def test_unusable_phone_number_fails_before_any_request(configured, monkeypatch):
    def explode(*a, **kw):
        raise AssertionError("HTTP call attempted with an unusable phone")

    monkeypatch.setattr(sendblue.httpx, "post", explode)

    result = send_checkin_message("12", "Steve", "https://x.example/c")
    assert result.sent is False
    assert "phone" in result.detail


def test_api_error_reports_the_status_code(configured, monkeypatch):
    monkeypatch.setattr(sendblue.httpx, "post", lambda *a, **kw: _FakeResponse(401))

    result = send_checkin_message("+15124917035", "Steve", "https://x.example/c")
    assert result.sent is False
    assert result.status_code == 401
    assert "401" in result.detail


def test_transport_failure_reports_cleanly(configured, monkeypatch):
    def fake_post(*a, **kw):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(sendblue.httpx, "post", fake_post)

    result = send_checkin_message("+15124917035", "Steve", "https://x.example/c")
    assert result.sent is False
    assert result.detail.startswith("request failed")
    assert result.status_code is None
