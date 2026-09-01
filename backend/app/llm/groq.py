"""Groq chat-completions client (OpenAI-compatible API, free tier).

The free tier enforces a tokens-per-minute budget (12k TPM on the 70B model),
so 429s are normal during bursts — the client honors Groq's retry-after and
paces itself briefly. When retries don't recover (an exhausted daily quota, an
outage), it reports the failure to the provider layer, which cools Groq down
so the next requests skip straight to Ollama/fallback instead of every page
load paying this retry budget.
"""

import json
import re
import time

import httpx

from app.config import settings
from app.llm.provider import LLMError, note_groq_failure

BASE_URL = "https://api.groq.com/openai/v1"
TIMEOUT = 8.0
RETRIABLE = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
# Short on purpose: a burst 429 usually clears in seconds; anything longer is
# a quota/outage problem the provider-level cooldown handles better than a
# blocked request thread would.
MAX_TOTAL_WAIT = 10.0
# What DEADLINE actually bounds: elapsed wall clock across the whole call —
# retry sleeps, connect, and the time spent receiving a response. Handing
# `timeout=` to httpx does NOT do this. An httpx read timeout bounds the gap
# between two received bytes, so an upstream (or a proxy in front of it) that
# dribbles one chunk every second resets it forever: a 75-second dribble took
# 75 seconds to return under a 15-second "deadline", holding a request thread
# the whole time. The response is therefore streamed and the clock checked
# after every chunk, which is what makes the bound hold.
#
# The one slack: a socket read already in flight when the budget runs out
# still gets its own timeout to finish or fail, so the worst case is DEADLINE
# plus one attempt's timeout rather than DEADLINE exactly. It does not grow
# with how long the upstream keeps talking, which is the property that
# matters — a thread parked for 75 seconds is what this exists to prevent.
DEADLINE = 15.0
# A chat completion is a few kilobytes. Anything approaching this is a wrong
# endpoint or a hostile body, and it is read into memory, so it is capped.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _sleep_fits(pause: float, started: float) -> bool:
    """A pause is only taken when it fits inside the deadline as well as the
    retry budget — slow attempts spend the same clock, so the budget alone
    does not bound the call."""
    return pause > 0 and time.monotonic() - started + pause <= DEADLINE


def _retry_after_seconds(headers: httpx.Headers, text: str) -> float:
    header = headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    # Groq also embeds "Please try again in 7.66s" / "in 350ms" in the body.
    match = re.search(r"try again in ([\d.]+)(ms|s)", text)
    if match:
        value = float(match.group(1))
        return value / 1000.0 if match.group(2) == "ms" else value
    return 5.0


def _fetch(body: dict, headers: dict, budget: float) -> tuple[int, httpx.Headers, str]:
    """One attempt, bounded by `budget` seconds of wall clock.

    Streamed rather than buffered by httpx so the elapsed time can be checked
    between chunks: that check, not the socket timeout, is what stops a slow
    dribble from outliving the deadline. Raises httpx.ReadTimeout when the
    budget runs out mid-response, which the caller already treats as a
    retriable transport failure.
    """
    limit = time.monotonic() + budget
    with httpx.Client(timeout=budget) as client:
        with client.stream(
            "POST", f"{BASE_URL}/chat/completions", json=body, headers=headers
        ) as response:
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise httpx.ReadTimeout(
                        f"Groq response exceeded {MAX_RESPONSE_BYTES} bytes",
                        request=response.request,
                    )
                if time.monotonic() >= limit:
                    raise httpx.ReadTimeout(
                        "Groq call exceeded its deadline while reading the response",
                        request=response.request,
                    )
            return (
                response.status_code,
                response.headers,
                b"".join(chunks).decode("utf-8", errors="replace"),
            )


def complete_json(system: str, user: str, temperature: float = 0.45) -> dict:
    if not settings.groq_api_key:
        raise LLMError("No GROQ_API_KEY configured")

    body = {
        "model": settings.groq_model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    last_error: Exception | str | None = None
    waited = 0.0
    started = time.monotonic()
    for attempt in range(MAX_ATTEMPTS):
        # The attempt's own timeout is clipped to what is left of the deadline,
        # so a slow response can never carry the call past it.
        remaining = DEADLINE - (time.monotonic() - started)
        if remaining <= 0:
            break
        try:
            status, response_headers, text = _fetch(
                body, headers, min(TIMEOUT, remaining)
            )
            if status in RETRIABLE:
                last_error = f"Groq {status}: {text[:160]}"
                pause = min(
                    _retry_after_seconds(response_headers, text) + 0.5,
                    MAX_TOTAL_WAIT - waited,
                )
                if attempt == MAX_ATTEMPTS - 1 or not _sleep_fits(pause, started):
                    break
                time.sleep(pause)
                waited += pause
                continue
            if status >= 400:
                raise httpx.HTTPStatusError(
                    f"Groq {status}: {text[:160]}", request=None, response=None
                )
            content = json.loads(text)["choices"][0]["message"]["content"]
            return json.loads(content)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            last_error = e
            pause = min(1.5 * (attempt + 1), MAX_TOTAL_WAIT - waited)
            if attempt == MAX_ATTEMPTS - 1 or not _sleep_fits(pause, started):
                break
            time.sleep(pause)
            waited += pause
    note_groq_failure()
    raise LLMError(f"Groq call failed: {last_error}")
