"""Local Ollama client — the zero-key real-LLM path.

Uses the NATIVE /api/chat endpoint (not the OpenAI shim) for the same reasons
the kiosk does: `format: "json"` constrains decoding to valid JSON, and
`think: false` suppresses reasoning-model chain-of-thought, which would
otherwise consume the whole token budget before any content is emitted.
"""

import json
import logging

import httpx

from app.config import settings
from app.llm.provider import LLMError

logger = logging.getLogger(__name__)

TIMEOUT = 120.0
KEEP_ALIVE = "30m"  # keep the model resident between insight generations


def complete_json(
    system: str, user: str, num_predict: int = 700, temperature: float = 0.45
) -> dict:
    if not settings.ollama_url:
        raise LLMError("Ollama disabled (no OLLAMA_URL)")
    body = {
        "model": settings.ollama_model,
        "stream": False,
        "think": False,
        "format": "json",
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": temperature, "num_predict": num_predict},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        response = httpx.post(f"{settings.ollama_url}/api/chat", json=body, timeout=TIMEOUT)
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
        if not content.strip():
            raise LLMError("Ollama returned empty content (model may be thinking-only)")
        return json.loads(content)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        raise LLMError(f"Ollama call failed: {e}") from e
