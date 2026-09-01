"""LLM provider selection and dispatch.

Priority: Groq (when a key is configured and not cooling down) → local Ollama
(when reachable and the configured model is present) → deterministic fallback.
The Ollama probe is cached briefly so worklist rendering doesn't ping the
socket per patient, and a Groq that fails (exhausted rate limit, outage) or
that keeps returning output the product rejects trips a cooldown so requests
stop paying for it and drop to the next tier immediately instead of hanging
every page load.
"""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


_ollama_probe: dict = {"at": 0.0, "ok": False}
_PROBE_TTL = 60.0

_cooldowns: dict[str, float] = {}
_COOLDOWN_S = 180.0
# Consecutive rejected completions before a provider is treated as unavailable.
# One off-contract answer is noise; a run of them is an outage in everything
# but name — and unlike an outage nothing raises, so without this a drifted
# model is re-asked for every insight of every request indefinitely.
_REJECT_STRIKES = 3
_rejections: dict[str, int] = {}


def _cool_down(provider: str) -> None:
    _cooldowns[provider] = time.monotonic() + _COOLDOWN_S
    _rejections.pop(provider, None)
    logger.warning("%s unavailable — cooling down for %.0fs", provider.capitalize(), _COOLDOWN_S)


def _cooling_down(provider: str) -> bool:
    return time.monotonic() < _cooldowns.get(provider, 0.0)


def note_provider_failure(provider: str) -> None:
    """Called by a provider client after a call fails.

    Every real-LLM tier needs this hook, not just Groq. Without it a provider
    that is reachable but broken is re-asked for every insight of every
    request, forever: a worklist render is thirteen calls, and on the Ollama
    tier each one may wait TIMEOUT=120s. For the cooldown window insights
    render via the next tier instantly; one probe call after expiry
    rediscovers the provider on its own.
    """
    if provider == "fallback":
        return
    _cool_down(provider)


def note_groq_failure() -> None:
    """Back-compatible alias for the Groq client's failure hook."""
    note_provider_failure("groq")


def note_invalid_output(provider: str) -> None:
    """Called when a provider returns parseable JSON that product validation
    rejects. Output that can never be shown is as useless as no output at all,
    so a short run of rejections degrades exactly like a failed call: the
    provider cools down and the deterministic renderer takes over."""
    if provider == "fallback":
        return
    _rejections[provider] = _rejections.get(provider, 0) + 1
    if _rejections[provider] >= _REJECT_STRIKES:
        _cool_down(provider)


def note_valid_output(provider: str) -> None:
    """Clears the rejection streak — only consecutive rejections count, so an
    occasional off-contract answer never costs a working provider its turn."""
    _rejections.pop(provider, None)


def _groq_available() -> bool:
    return bool(settings.groq_api_key) and not _cooling_down("groq")


def _ollama_available() -> bool:
    if not settings.ollama_url or _cooling_down("ollama"):
        return False
    now = time.monotonic()
    if now - _ollama_probe["at"] < _PROBE_TTL:
        return _ollama_probe["ok"]
    ok = False
    try:
        response = httpx.get(f"{settings.ollama_url}/api/tags", timeout=2.0)
        response.raise_for_status()
        models = [m.get("name", "") for m in response.json().get("models", [])]
        ok = settings.ollama_model in models
        if not ok and models:
            logger.warning(
                "Ollama is up but model %r is not pulled (available: %s)",
                settings.ollama_model, ", ".join(models[:5]),
            )
    except httpx.HTTPError:
        ok = False
    _ollama_probe.update(at=now, ok=ok)
    return ok


def provider_name() -> str:
    if _groq_available():
        return "groq"
    if _ollama_available():
        return "ollama"
    return "fallback"


def model_name() -> str | None:
    provider = provider_name()
    if provider == "groq":
        return settings.groq_model
    if provider == "ollama":
        return settings.ollama_model
    return None


def complete_json(
    system: str, user: str, num_predict: int = 700, temperature: float = 0.45
) -> dict:
    """Dispatch one JSON completion to the active real-LLM provider.
    Raises LLMError when none is available or the call fails."""
    provider = provider_name()
    if provider == "groq":
        from app.llm import groq

        return groq.complete_json(system, user, temperature=temperature)
    if provider == "ollama":
        from app.llm import ollama

        return ollama.complete_json(system, user, num_predict=num_predict, temperature=temperature)
    raise LLMError("No LLM provider available")
