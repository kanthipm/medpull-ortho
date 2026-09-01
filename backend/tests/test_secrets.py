"""app/aws/secrets.py: the cold-start SSM loader, exercised against a fake
boto3 so the Groq-only path is provably unchanged by the Junction additions
and the failure modes are the ones the module promises."""

import logging
import sys
import types

import pytest

from app.aws import secrets
from app.aws.config import aws_settings
from app.config import settings


class ParameterNotFound(Exception):
    """boto3 raises a dynamically generated class by this name."""


class FakeSsm:
    def __init__(self, values: dict[str, object]):
        self.values = values
        self.calls: list[str] = []

    def get_parameter(self, Name: str, WithDecryption: bool):  # noqa: N803 — boto3's casing
        self.calls.append(Name)
        value = self.values.get(Name, ParameterNotFound())
        if isinstance(value, Exception):
            raise value
        return {"Parameter": {"Value": value}}


@pytest.fixture()
def fake_boto3(monkeypatch):
    ssm = FakeSsm({})
    module = types.ModuleType("boto3")
    module.client = lambda service: ssm  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", module)
    monkeypatch.setattr(secrets, "_loaded", False)
    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(settings, "junction_api_key", "")
    monkeypatch.setattr(settings, "junction_webhook_secret", "")
    monkeypatch.setattr(aws_settings, "groq_api_key_parameter", "")
    monkeypatch.setattr(aws_settings, "junction_api_key_parameter", "")
    monkeypatch.setattr(aws_settings, "junction_webhook_secret_parameter", "")
    return ssm


def test_groq_only_behaves_as_before(fake_boto3, monkeypatch):
    monkeypatch.setattr(aws_settings, "groq_api_key_parameter", "/rc/groq")
    fake_boto3.values["/rc/groq"] = "  gsk_test  "
    secrets.load()
    assert settings.groq_api_key == "gsk_test"  # stripped
    assert settings.junction_api_key == "" and settings.junction_webhook_secret == ""
    assert fake_boto3.calls == ["/rc/groq"]
    secrets.load()
    assert fake_boto3.calls == ["/rc/groq"]  # one attempt per cold start


def test_all_three_load_and_one_failure_does_not_block_the_others(fake_boto3, monkeypatch, caplog):
    monkeypatch.setattr(aws_settings, "groq_api_key_parameter", "/rc/groq")
    monkeypatch.setattr(aws_settings, "junction_api_key_parameter", "/rc/junction")
    monkeypatch.setattr(aws_settings, "junction_webhook_secret_parameter", "/rc/whsec")
    fake_boto3.values.update(
        {"/rc/groq": RuntimeError("AccessDeniedException"), "/rc/junction": "sk_us_x", "/rc/whsec": "whsec_x"}
    )
    with caplog.at_level(logging.INFO):
        secrets.load()
    assert settings.groq_api_key == ""  # the failure is logged, not raised
    assert settings.junction_api_key == "sk_us_x"
    assert settings.junction_webhook_secret == "whsec_x"
    assert fake_boto3.calls == ["/rc/groq", "/rc/junction", "/rc/whsec"]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "Groq API key" in warnings[0].getMessage()
    assert warnings[0].exc_info is not None  # a genuine access error keeps its traceback


def test_a_parameter_that_was_never_stored_is_one_info_line(fake_boto3, monkeypatch, caplog):
    """The deploy always names the Junction parameters; with nothing stored
    under them the connector is simply idle, and a cold start must not read
    like an IAM problem."""
    monkeypatch.setattr(aws_settings, "junction_api_key_parameter", "/rc/junction")
    monkeypatch.setattr(aws_settings, "junction_webhook_secret_parameter", "/rc/whsec")
    with caplog.at_level(logging.INFO):
        secrets.load()
    assert settings.junction_api_key == "" and settings.junction_webhook_secret == ""
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("not stored" in m and "/rc/junction" in m for m in infos)
    assert any("not stored" in m and "/rc/whsec" in m for m in infos)


def test_an_empty_value_is_a_warning_and_no_names_is_a_no_op(fake_boto3, monkeypatch, caplog):
    secrets.load()
    assert fake_boto3.calls == []  # nothing configured: no SSM call, no flag set
    assert secrets._loaded is False
    monkeypatch.setattr(aws_settings, "junction_api_key_parameter", "/rc/junction")
    fake_boto3.values["/rc/junction"] = "   "
    with caplog.at_level(logging.WARNING):
        secrets.load()
    assert settings.junction_api_key == ""
    assert any("is empty" in r.getMessage() for r in caplog.records)
