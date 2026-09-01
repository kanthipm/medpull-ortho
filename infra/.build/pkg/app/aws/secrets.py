"""Load the Groq API key from SSM Parameter Store at cold start.

Standard Parameter Store parameters are free, so the key stays out of the
function's plaintext environment (where anyone with console read access would
see it) at no cost. Fetched once per execution environment and cached by the
module, so the per-request cost is zero.

No-op when GROQ_API_KEY_PARAMETER is unset — a plain GROQ_API_KEY env var or a
local .env keeps working exactly as before.
"""

import logging

from app.aws.config import aws_settings
from app.config import settings

logger = logging.getLogger(__name__)

_loaded = False


def load() -> None:
    global _loaded
    if _loaded or not aws_settings.groq_api_key_parameter:
        return
    _loaded = True  # one attempt per cold start; a retry storm helps nobody

    try:
        import boto3

        response = boto3.client("ssm").get_parameter(
            Name=aws_settings.groq_api_key_parameter, WithDecryption=True
        )
        value = response["Parameter"]["Value"].strip()
    except Exception:  # noqa: BLE001 — the app is designed to run without a key
        logger.warning(
            "Could not read Groq key from SSM parameter %r — falling back to the "
            "deterministic renderer",
            aws_settings.groq_api_key_parameter,
            exc_info=True,
        )
        return

    if value:
        settings.groq_api_key = value
        logger.info("Loaded Groq API key from SSM")
    else:
        logger.warning("SSM parameter %r is empty", aws_settings.groq_api_key_parameter)
