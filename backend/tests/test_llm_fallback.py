import re
import time

import httpx
import pytest
from sqlalchemy import func, select

from app.llm import documentation as documentation_mod
from app.llm import groq as groq_mod
from app.llm import insights as insights_mod
from app.llm import provider as provider_mod
from app.llm.insights import BANNED, get_daily_briefing, get_patient_insight
from app.llm.provider import LLMError
from app.models.enums import GUARDRAIL_SENTENCE, InsightKind
from app.models.insight import Insight

LONG_BODY = (
    "Recovery is progressing with steady step counts and stable vitals. Skin "
    "temperature and resting heart rate are within the personal baseline range, "
    "and the patient reports sleeping through the night."
)


@pytest.fixture()
def groq_configured(monkeypatch):
    """Presents a configured, healthy Groq to the code under test and restores
    the cooldown/rejection state afterwards, so one test's simulated outage can
    never leak into the next."""
    monkeypatch.setattr(provider_mod.settings, "groq_api_key", "test-key")
    monkeypatch.setitem(provider_mod._cooldowns, "groq", 0.0)
    monkeypatch.setitem(provider_mod._rejections, "groq", 0)
    assert provider_mod.provider_name() == "groq"
    return provider_mod


def _insight_rows(db, patient_id, kind) -> int:
    return db.scalar(
        select(func.count(Insight.id)).where(
            Insight.patient_id == patient_id, Insight.kind == kind
        )
    )


def _narratives(content) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, dict):
        return [s for v in content.values() for s in _narratives(v)]
    if isinstance(content, list):
        return [s for v in content for s in _narratives(v)]
    return []


def test_all_kinds_generate_valid_content(db):
    for kind in (
        InsightKind.WORKLIST_REASON,
        InsightKind.PATIENT_SUMMARY,
        InsightKind.SUGGESTED_ACTIONS,
    ):
        insight = get_patient_insight(db, kind, "marcus")
        assert insight.llm_provider == "fallback"
        assert insight.content
    briefing = get_daily_briefing(db)
    assert "Marcus" in briefing.content["briefing"]


def test_summary_ends_with_guardrail(db):
    for patient_id in ("marcus", "priya", "david"):
        insight = get_patient_insight(db, InsightKind.PATIENT_SUMMARY, patient_id)
        assert insight.content["summary"].endswith(GUARDRAIL_SENTENCE)


def test_no_banned_phrases_anywhere(db):
    for patient_id in ("marcus", "linda", "priya", "david"):
        for kind in (
            InsightKind.WORKLIST_REASON,
            InsightKind.PATIENT_SUMMARY,
            InsightKind.SUGGESTED_ACTIONS,
        ):
            content = get_patient_insight(db, kind, patient_id).content
            for text in _narratives(content):
                scrubbed = text.replace(GUARDRAIL_SENTENCE, "")
                assert not BANNED.search(scrubbed), (patient_id, kind, text)


def test_cache_returns_same_row(db):
    a = get_patient_insight(db, InsightKind.PATIENT_SUMMARY, "marcus")
    b = get_patient_insight(db, InsightKind.PATIENT_SUMMARY, "marcus")
    assert a.id == b.id


def test_diagnostic_llm_output_is_rejected(db, monkeypatch):
    """A provider emitting diagnostic language must be silently replaced."""
    monkeypatch.setattr(insights_mod, "provider_name", lambda: "groq")
    monkeypatch.setattr(
        insights_mod,
        "complete_json",
        lambda system, user, **kw: {"summary": "We detected an infection in the knee. " * 4},
    )
    insight = get_patient_insight(db, InsightKind.PATIENT_SUMMARY, "linda")
    assert insight.llm_provider == "fallback"
    assert "detected" not in insight.content["summary"]
    assert insight.content["summary"].endswith(GUARDRAIL_SENTENCE)


def test_worklist_reason_length_contract(db):
    for patient_id in ("marcus", "linda", "sofia"):
        reason = get_patient_insight(db, InsightKind.WORKLIST_REASON, patient_id).content["reason"]
        assert 0 < len(reason) <= 90


def test_banned_regex_shape():
    assert re.search(BANNED, "Detected a problem")
    assert re.search(BANNED, "possible diagnosis")
    assert not re.search(BANNED, "signals for clinician review")


def test_groq_cooldown_prevents_hammering(groq_configured):
    """A failed Groq call trips a cooldown so subsequent requests skip its
    retry budget entirely instead of hanging every page load on a dead key."""
    groq_configured.note_groq_failure()
    # cooling down: no Ollama in tests, so the deterministic renderer takes over
    assert groq_configured.provider_name() == "fallback"
    groq_configured._cooldowns["groq"] = 0.0  # expire — Groq is probed again
    assert groq_configured.provider_name() == "groq"


def test_validate_normalizes_every_valid_kind():
    """The accept path: each kind's contract is normalized, not just rejected.

    The guardrail sentence contains the word "diagnosis", so a summary that
    carries it must survive the banned-phrase scan — that exemption is the
    only reason the product's own disclaimer is publishable."""
    reason = insights_mod._validate(
        InsightKind.WORKLIST_REASON, {"reason": "  Skin temp +0.4 · RHR +8 vs baseline  "}
    )
    assert reason == {"reason": "Skin temp +0.4 · RHR +8 vs baseline"}

    summary = insights_mod._validate(InsightKind.PATIENT_SUMMARY, {"summary": LONG_BODY})
    assert summary["summary"] == f"{LONG_BODY} {GUARDRAIL_SENTENCE}"
    already = insights_mod._validate(
        InsightKind.PATIENT_SUMMARY, {"summary": f"{LONG_BODY} {GUARDRAIL_SENTENCE}"}
    )
    assert already["summary"].count(GUARDRAIL_SENTENCE) == 1

    actions = insights_mod._validate(
        InsightKind.SUGGESTED_ACTIONS,
        {
            "actions": [
                {"title": "Call the patient today", "detail": "Signals moved together.",
                 "urgency": "today"},
                {"title": "x" * 90, "urgency": "immediately"},
                {"title": "Third", "detail": "", "urgency": "routine"},
                {"title": "Fourth", "detail": "", "urgency": "this_week"},
                {"title": "Fifth — over the cap", "detail": "", "urgency": "routine"},
            ]
        },
    )["actions"]
    assert len(actions) == 4
    assert len(actions[1]["title"]) == 60
    assert actions[1]["urgency"] == "routine"  # unknown urgency is not passed through
    assert actions[1]["detail"] == ""

    briefing = insights_mod._validate(InsightKind.DAILY_BRIEFING, {"briefing": LONG_BODY})
    assert briefing == {"briefing": LONG_BODY}


def test_validate_rejects_off_contract_output():
    assert insights_mod._validate(InsightKind.WORKLIST_REASON, {"reason": " "}) is None
    assert insights_mod._validate(InsightKind.WORKLIST_REASON, {"reason": "x" * 111}) is None
    assert insights_mod._validate(InsightKind.PATIENT_SUMMARY, {"summary": "too short"}) is None
    assert insights_mod._validate(InsightKind.SUGGESTED_ACTIONS, {"actions": []}) is None
    assert insights_mod._validate(InsightKind.SUGGESTED_ACTIONS, {"actions": "call them"}) is None
    assert insights_mod._validate(InsightKind.DAILY_BRIEFING, {"briefing": "all fine"}) is None
    assert insights_mod._validate(InsightKind.WORKLIST_REASON, {}) is None
    # the scan reaches into nested values, not just the top-level string
    assert insights_mod._validate(
        InsightKind.SUGGESTED_ACTIONS,
        {"actions": [{"title": "Review", "detail": "Infection detected in the incision."}]},
    ) is None


def test_document_validation_matches_the_insight_contract():
    """RTM documents are billable and provider-signed, so they run the same
    guardrail-append + banned-phrase scan as the narratives."""
    ok = documentation_mod._validate({"title": "RTM encounter note — day 14", "body": LONG_BODY})
    assert ok["body"].endswith(GUARDRAIL_SENTENCE)
    assert documentation_mod._validate(
        {"title": "t" * 90, "body": f"{LONG_BODY} {GUARDRAIL_SENTENCE}"}
    ) == {"title": "t" * 60, "body": f"{LONG_BODY} {GUARDRAIL_SENTENCE}"}
    assert documentation_mod._validate({"title": "", "body": LONG_BODY}) is None
    assert documentation_mod._validate({"title": "RTM note", "body": "too short"}) is None
    assert documentation_mod._validate({"body": LONG_BODY}) is None
    assert documentation_mod._validate(
        {"title": "RTM note", "body": f"We diagnosed an infection. {LONG_BODY}"}
    ) is None


def test_low_risk_reason_is_served_from_cache(db, groq_configured, monkeypatch):
    """A deliberate LLM skip must cache. It used to be keyed as though the LLM
    had produced it, so every read missed, re-rendered and INSERTed — eight new
    rows and a commit on every worklist load, forever."""
    monkeypatch.setattr(
        insights_mod, "complete_json",
        lambda *a, **kw: pytest.fail("a low-risk reason must not call the LLM"),
    )
    first = get_patient_insight(db, InsightKind.WORKLIST_REASON, "david")
    assert first.llm_provider == "fallback"
    before = _insight_rows(db, "david", InsightKind.WORKLIST_REASON)
    ids = {get_patient_insight(db, InsightKind.WORKLIST_REASON, "david").id for _ in range(5)}
    assert ids == {first.id}
    assert _insight_rows(db, "david", InsightKind.WORKLIST_REASON) == before


def test_llm_backed_reason_is_generated_once_then_cached(db, groq_configured, monkeypatch):
    """The skip is narrow: a patient who is not stable still gets one LLM call,
    and its accepted output caches like any other row."""
    calls = []
    monkeypatch.setattr(
        insights_mod, "complete_json",
        lambda *a, **kw: calls.append(1) or {"reason": "Skin temp +0.4 · RHR +8 vs baseline"},
    )
    first = get_patient_insight(db, InsightKind.WORKLIST_REASON, "marcus")
    assert first.llm_provider == "groq"
    assert first.content == {"reason": "Skin temp +0.4 · RHR +8 vs baseline"}
    second = get_patient_insight(db, InsightKind.WORKLIST_REASON, "marcus")
    assert second.id == first.id
    assert len(calls) == 1


def test_repeated_invalid_output_degrades_like_an_outage(db, groq_configured, monkeypatch):
    """Parseable JSON that fails validation raises nothing, so it used to arm
    no cooldown: 13 calls per request, every request, forever. A short run of
    rejections now cools the provider down exactly like a failed call."""
    calls = []
    monkeypatch.setattr(
        insights_mod, "complete_json",
        lambda *a, **kw: calls.append(1) or {"reason": "x" * 200},  # over the 110-char cap
    )
    monkeypatch.setattr(insights_mod, "PROMPT_VERSION", "storm-test")
    patient_ids = ["aisha", "linda", "marcus", "priya", "robert", "sofia"]
    for patient_id in patient_ids:
        insight = get_patient_insight(db, InsightKind.WORKLIST_REASON, patient_id)
        assert insight.llm_provider == "fallback"
    assert len(calls) == provider_mod._REJECT_STRIKES
    assert groq_configured.provider_name() == "fallback"

    # and the next request pays nothing at all
    for patient_id in patient_ids:
        get_patient_insight(db, InsightKind.WORKLIST_REASON, patient_id)
    assert len(calls) == provider_mod._REJECT_STRIKES


def test_an_accepted_answer_clears_the_rejection_streak(db, groq_configured, monkeypatch):
    """Only CONSECUTIVE rejections count — one off-contract answer must not
    cost a working provider its turn."""
    replies = [{"reason": "x" * 200}, {"reason": "Sleep down 2.1h vs baseline"},
               {"reason": "x" * 200}, {"reason": "x" * 200}]
    monkeypatch.setattr(insights_mod, "complete_json", lambda *a, **kw: replies.pop(0))
    monkeypatch.setattr(insights_mod, "PROMPT_VERSION", "streak-test")
    for patient_id in ("aisha", "linda", "marcus", "sofia"):
        get_patient_insight(db, InsightKind.WORKLIST_REASON, patient_id)
    assert replies == []  # all four calls were made
    assert groq_configured.provider_name() == "groq"
    assert provider_mod._rejections.get("groq", 0) == 2


def test_warm_briefing_costs_no_per_patient_lookups(db, monkeypatch):
    """The briefing used to build its roster BEFORE consulting its own cache,
    so a cache hit still cost one insight lookup per patient."""
    assert get_daily_briefing(db).content["briefing"]
    monkeypatch.setattr(
        insights_mod, "get_patient_insight",
        lambda *a, **kw: pytest.fail("a cached briefing must not touch the roster"),
    )
    assert get_daily_briefing(db).content["briefing"]


def test_cached_series_is_bounded(db, monkeypatch):
    """Every engine recompute — and every calendar day — turns the cache key
    over, so without a bound the table grows for the life of the deployment."""
    kind = InsightKind.SUGGESTED_ACTIONS
    for version in range(insights_mod.KEEP_PER_SERIES + 4):
        monkeypatch.setattr(insights_mod, "PROMPT_VERSION", f"prune-{version}")
        newest = get_patient_insight(db, kind, "elena")
    assert _insight_rows(db, "elena", kind) == insights_mod.KEEP_PER_SERIES
    assert db.get(Insight, newest.id) is not None  # the live row survives its own prune


def test_groq_deadline_is_hard(groq_configured, monkeypatch):
    """DEADLINE has to bound the whole call, sleeps AND slow attempts. The
    exception-path sleep was unguarded, so one completion could run ~26s —
    long enough for seven of them to blow the 30s Lambda ceiling."""

    class FakeClock:
        """Stands in for `time` so the budget is spent without waiting."""

        def __init__(self) -> None:
            self.now = 0.0
            self.sleeps: list[float] = []

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += seconds

    clock = FakeClock()
    attempts: list[float] = []

    def hang(body, headers, budget):
        attempts.append(budget)
        clock.now += budget  # every attempt burns its whole budget
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(groq_mod, "time", clock)
    monkeypatch.setattr(groq_mod, "_fetch", hang)
    with pytest.raises(LLMError):
        groq_mod.complete_json("system", "user")
    assert attempts  # it really did try
    assert all(t <= groq_mod.TIMEOUT for t in attempts)
    assert clock.now <= groq_mod.DEADLINE


def test_a_dribbling_response_cannot_outlive_the_deadline(groq_configured, monkeypatch):
    """The deadline has to bound RECEIVING, not just connecting.

    An httpx read timeout bounds the gap between two bytes, so an upstream
    that sends one chunk every second resets it indefinitely: measured against
    a stub that dribbled for 75 seconds, a call under a 15-second "deadline"
    took 75 seconds and held a request thread for all of it. The body is
    streamed and the clock checked between chunks so the wait is bounded by
    the budget instead of by the sender's patience.
    """

    class FakeClock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.now += seconds

    clock = FakeClock()
    chunks_read = 0

    class DribblingResponse:
        request = None
        status_code = 200
        headers = httpx.Headers({})

        def iter_bytes(self):
            nonlocal chunks_read
            while True:  # a sender that never stops
                clock.now += 1.5
                chunks_read += 1
                yield b'{"choices":'

    class FakeStream:
        def __enter__(self):
            return DribblingResponse()

        def __exit__(self, *exc):
            return False

    class FakeClient:
        def __init__(self, **kwargs):
            self.timeout = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, *args, **kwargs):
            return FakeStream()

    monkeypatch.setattr(groq_mod, "time", clock)
    monkeypatch.setattr(httpx, "Client", FakeClient)

    with pytest.raises(httpx.ReadTimeout):
        groq_mod._fetch({}, {}, budget=groq_mod.DEADLINE)
    assert chunks_read > 1  # it really did read a dribble
    assert clock.now <= groq_mod.DEADLINE + 1.5  # bounded by the budget, not the sender


def test_a_runaway_response_body_is_capped(groq_configured, monkeypatch):
    """The body is read into memory, so an endless one is refused rather than
    accumulated."""

    class HugeResponse:
        request = None
        status_code = 200
        headers = httpx.Headers({})

        def iter_bytes(self):
            while True:
                yield b"x" * 65536

    class FakeStream:
        def __enter__(self):
            return HugeResponse()

        def __exit__(self, *exc):
            return False

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, *args, **kwargs):
            return FakeStream()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    with pytest.raises(httpx.ReadTimeout, match="bytes"):
        groq_mod._fetch({}, {}, budget=groq_mod.DEADLINE)


def test_a_failing_ollama_cools_down_like_a_failing_groq(monkeypatch):
    """Every real-LLM tier needs the failure hook, not just Groq.

    With the daemon reachable but /api/chat failing, nothing called
    _cool_down('ollama'): the probe kept reporting Ollama available and every
    worklist render paid thirteen more calls of up to TIMEOUT=120s each,
    request after request, indefinitely.
    """
    from app.llm import ollama as ollama_mod

    monkeypatch.setattr(provider_mod.settings, "groq_api_key", "")
    monkeypatch.setattr(provider_mod.settings, "ollama_url", "http://127.0.0.1:65535")
    monkeypatch.setitem(provider_mod._cooldowns, "ollama", 0.0)
    monkeypatch.setitem(provider_mod._ollama_probe, "at", time.monotonic())
    monkeypatch.setitem(provider_mod._ollama_probe, "ok", True)
    assert provider_mod.provider_name() == "ollama"

    def boom(url, **kwargs):
        raise httpx.ConnectError("model runner crashed")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(LLMError):
        ollama_mod.complete_json("system", "user")

    assert provider_mod._cooling_down("ollama")
    assert provider_mod.provider_name() == "fallback"


def test_an_empty_ollama_completion_also_cools_down(monkeypatch):
    """A model that answers with nothing is as unusable as one that refuses to
    answer, and it raises through a different path."""
    from app.llm import ollama as ollama_mod

    monkeypatch.setattr(provider_mod.settings, "ollama_url", "http://127.0.0.1:65535")
    monkeypatch.setitem(provider_mod._cooldowns, "ollama", 0.0)

    class Empty:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "   "}}

    monkeypatch.setattr(httpx, "post", lambda url, **kwargs: Empty())
    with pytest.raises(LLMError):
        ollama_mod.complete_json("system", "user")
    assert provider_mod._cooling_down("ollama")
