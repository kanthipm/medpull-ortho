"""Load secrets from SSM Parameter Store at cold start.

Standard Parameter Store parameters are free, so the keys stay out of the
function's plaintext environment (where anyone with console read access would
see them) at no cost. Fetched once per execution environment and cached by the
module, so the per-request cost is zero.

Three parameters, each optional and each a no-op when its name is unset, so a
plain env var or a local .env keeps working exactly as before:

* ``GROQ_API_KEY_PARAMETER`` → ``settings.groq_api_key``
* ``JUNCTION_API_KEY_PARAMETER`` → ``settings.junction_api_key``
* ``JUNCTION_WEBHOOK_SECRET_PARAMETER`` → ``settings.junction_webhook_secret``
"""

import logging

from app.aws.config import aws_settings
from app.config import settings

logger = logging.getLogger(__name__)

_loaded = False


def _parameters() -> list[tuple[str, str, str]]:
    """(parameter name, settings attribute, human label) for every configured secret."""
    return [
        (aws_settings.groq_api_key_parameter, "groq_api_key", "Groq API key"),
        (aws_settings.junction_api_key_parameter, "junction_api_key", "Junction API key"),
        (
            aws_settings.junction_webhook_secret_parameter,
            "junction_webhook_secret",
            "Junction webhook secret",
        ),
    ]


def _read(name: str, label: str) -> str | None:
    try:
        import boto3

        response = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)
        return response["Parameter"]["Value"].strip()
    except Exception:  # noqa: BLE001 — the app is designed to run without any secret
        logger.warning(
            "Could not read the %s from SSM parameter %r — continuing without it",
            label,
            name,
            exc_info=True,
        )
        return None


def load() -> None:
    global _loaded
    wanted = [(name, attr, label) for name, attr, label in _parameters() if name]
    if _loaded or not wanted:
        return
    _loaded = True  # one attempt per cold start; a retry storm helps nobody

    for name, attr, label in wanted:
        value = _read(name, label)
        if value is None:
            continue
        if value:
            setattr(settings, attr, value)
            logger.info("Loaded the %s from SSM", label)
        else:
            logger.warning("SSM parameter %r (%s) is empty", name, label)
