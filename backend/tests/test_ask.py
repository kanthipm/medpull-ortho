import pytest

from app.llm import ask as ask_mod
from app.llm import provider as provider_mod
from app.llm.ask import (
    ASK_SYSTEM,
    COMPOSE_SYSTEM,
    VERIFY_SYSTEM,
    _render_block,
    _roster_context,
    _validate_ask,
    ask,
    fallback_ask,
)
from app.llm.insights import BANNED
from app.llm.provider import LLMError
from app.models.enums import GUARDRAIL_SENTENCE


@pytest.fixture()
def groq_configured(monkeypatch):
    """Presents a configured, healthy Groq and restores the cooldown state
    afterwards, so a simulated outage cannot leak into the next test."""
    monkeypatch.setattr(provider_mod.settings, "groq_api_key", "test-key")
    monkeypatch.setitem(provider_mod._cooldowns, "groq", 0.0)
    monkeypatch.setitem(provider_mod._rejections, "groq", 0)
    assert provider_mod.provider_name() == "groq"
    return provider_mod


class FakeLLM:
    """Routes a completion to a reply keyed by which system prompt it used —
    the three legs of retrieve → verify → compose are different calls."""

    def __init__(
        self,
        retrieved: dict,
        verdicts: dict[str, dict],
        composed: dict | None = None,
    ) -> None:
        self.retrieved = retrieved
        self.verdicts = verdicts
        self.composed = composed
        self.verified_blocks: list[str] = []
        self.calls: list[str] = []

    def __call__(self, system: str, user: str, **kwargs) -> dict:
        if system is ASK_SYSTEM:
            self.calls.append("retrieve")
            return self.retrieved
        if system is VERIFY_SYSTEM:
            self.calls.append("verify")
            self.verified_blocks.append(user)
            patient_id = user.split("id=", 1)[1].split(" ", 1)[0]
            # anything the deterministic retriever also proposed defaults to
            # "no", which is what a strict verifier does with an off-topic block
            return self.verdicts.get(patient_id, {"match": False, "evidence": ""})
        assert system is COMPOSE_SYSTEM
        self.calls.append("compose")
        if self.composed is None:
            raise LLMError("compose unavailable")
        return self.composed


def test_ask_fever_finds_marcus(db):
    result = ask(db, "Who has a fever or elevated temperature?")
    assert "marcus" in result["patient_ids"]
    assert "Marcus" in result["answer"]
    assert result["provider"] == "fallback"


def test_ask_behind_schedule(db):
    result = ask(db, "Which patients are behind schedule?")
    assert set(result["patient_ids"]) >= {"sofia", "aisha"}


def test_ask_missing_data(db):
    result = ask(db, "Anyone with device data gaps?")
    assert result["patient_ids"] == ["priya"]


def test_ask_procedure_filter(db):
    result = ask(db, "Show me my hip patients")
    assert set(result["patient_ids"]) >= {"aisha", "grace"}
    assert all(pid in {"aisha", "grace", "priya"} for pid in result["patient_ids"])


def test_ask_unmatchable_question_is_honest(db):
    roster = _roster_context(db)
    result = fallback_ask("What's the weather like?", roster)
    assert result["patient_ids"] == []
    assert "couldn't match" in result["answer"]


def test_ask_never_uses_banned_language(db):
    for question in ("who has a fever", "who is behind", "who needs review"):
        result = ask(db, question)
        assert not BANNED.search(result["answer"])


def test_ask_is_cached(db):
    first = ask(db, "who has a fever?")
    second = ask(db, "who has a fever?")
    assert first["generated_at"] == second["generated_at"]


def test_ask_endpoint(client):
    response = client.post("/api/ask", json={"question": "Who reported fever this week?"})
    assert response.status_code == 200
    body = response.json()
    assert "marcus" in body["patient_ids"]
    assert client.post("/api/ask", json={"question": "hi"}).status_code == 422


def test_draft_message_endpoint(client):
    body = client.post("/api/patients/marcus/actions/draft-message").json()
    assert 20 <= len(body["message"]) <= 320
    assert not BANNED.search(body["message"])
    assert "Marcus" in body["message"]
    # temperature is marcus's top signal — the fallback draft should ask about it
    assert "temperature" in body["message"].lower()


def test_render_block_carries_evidence_the_verifier_needs(db):
    """The verify step sees ONLY this string, so everything a match can be
    justified from has to be in it — and labelled as quote or measurement."""
    roster = {p["id"]: p for p in _roster_context(db)}
    block = _render_block(roster["marcus"])
    header, *lines = block.splitlines()
    assert header.startswith("PATIENT id=marcus | Marcus Reyes")
    assert "priority: high" in header
    assert "trajectory:" in header and "adherence:" in header and "data confidence:" in header
    assert any(line.startswith("  monitoring: ") for line in lines)
    assert any(line.startswith('  said: "') for line in lines)
    # one patient's block must never carry another patient's name
    assert "James" not in block


def test_validate_ask_keeps_only_real_ids_and_clean_prose():
    valid = {"marcus", "james"}
    ok = _validate_ask(
        {"answer": "  Marcus is the one to look at.  ", "patient_ids": ["marcus", "ghost"]},
        valid,
    )
    assert ok == {"answer": "Marcus is the one to look at.", "patient_ids": ["marcus"]}
    assert _validate_ask({"answer": "Fine.", "patient_ids": []}, valid)["patient_ids"] == []
    assert _validate_ask({"patient_ids": []}, valid) is None
    assert _validate_ask({"answer": "   ", "patient_ids": []}, valid) is None
    assert _validate_ask({"answer": "x" * 701, "patient_ids": []}, valid) is None
    assert _validate_ask({"answer": "We detected an infection.", "patient_ids": []}, valid) is None
    # the product's own disclaimer contains "diagnosis" and must stay publishable
    assert _validate_ask(
        {"answer": f"Marcus is stable. {GUARDRAIL_SENTENCE}", "patient_ids": []}, valid
    ) is not None


def test_ask_llm_verifies_every_candidate_before_citing_it(db, groq_configured, monkeypatch):
    """Retrieval over-includes on purpose; the answer and the worklist filter
    are built from the per-patient verification, never from retrieval."""
    llm = FakeLLM(
        retrieved={
            "answer": "Marcus and James both look feverish.",
            "patient_ids": ["marcus", "james"],
        },
        verdicts={
            "marcus": {"match": True, "evidence": "skin temperature elevated vs baseline"},
            "james": {"match": False, "evidence": ""},
        },
        composed={"answer": "Marcus Reyes: skin temperature is elevated vs his baseline."},
    )
    monkeypatch.setattr(ask_mod, "complete_json", llm)
    result = ask_mod._ask_llm("Who has a fever?", _roster_context(db), {"marcus", "james"})
    assert result["patient_ids"] == ["marcus"]  # james was retrieved, then rejected
    assert result["answer"] == "Marcus Reyes: skin temperature is elevated vs his baseline."
    assert llm.calls == ["retrieve", "verify", "verify", "compose"]
    # each verification saw one patient and one patient only
    assert all(block.count("PATIENT id=") == 1 for block in llm.verified_blocks)


def test_ask_llm_falls_back_to_verified_evidence_when_composing_fails(
    db, groq_configured, monkeypatch
):
    llm = FakeLLM(
        retrieved={"answer": "Marcus.", "patient_ids": ["marcus"]},
        verdicts={"marcus": {"match": True, "evidence": "resting HR rising vs baseline"}},
        composed=None,  # the composer is unavailable
    )
    monkeypatch.setattr(ask_mod, "complete_json", llm)
    result = ask_mod._ask_llm("Who has a rising heart rate?", _roster_context(db), {"marcus"})
    assert result["patient_ids"] == ["marcus"]
    assert result["answer"] == "1 match: Marcus Reyes — resting HR rising vs baseline"


def test_ask_llm_drops_a_candidate_whose_evidence_is_diagnostic(
    db, groq_configured, monkeypatch
):
    llm = FakeLLM(
        retrieved={"answer": "Marcus.", "patient_ids": ["marcus"]},
        verdicts={"marcus": {"match": True, "evidence": "wound infection detected"}},
        composed={"answer": "Marcus Reyes needs a call."},
    )
    monkeypatch.setattr(ask_mod, "complete_json", llm)
    result = ask_mod._ask_llm("Who has an infection?", _roster_context(db), {"marcus"})
    assert result["patient_ids"] == []
    assert result["answer"] == "No patients on the roster match that right now."


def test_ask_does_not_cache_an_outage_as_a_finding(db, groq_configured, monkeypatch):
    """A cooldown tripping inside the verify loop silently dropped every
    candidate and answered "no patients match" — attributed to the provider
    and served from cache long after the provider came back."""
    question = "Who has a fever right now?"

    def outage(system, user, **kwargs):
        if system is ASK_SYSTEM:
            return {"answer": "Marcus.", "patient_ids": ["marcus"]}
        provider_mod.note_groq_failure()  # the verify leg is where the outage lands
        raise LLMError("Groq call failed: simulated outage")

    monkeypatch.setattr(ask_mod, "complete_json", outage)
    during = ask(db, question)
    assert during["provider"] == "fallback"
    assert during["answer"] != "No patients on the roster match that right now."
    assert "marcus" in during["patient_ids"]

    groq_configured._cooldowns["groq"] = 0.0  # the provider recovers
    healthy = FakeLLM(
        retrieved={"answer": "Marcus.", "patient_ids": ["marcus"]},
        verdicts={"marcus": {"match": True, "evidence": "skin temperature elevated vs baseline"}},
        composed={"answer": "Marcus Reyes: skin temperature elevated vs baseline."},
    )
    monkeypatch.setattr(ask_mod, "complete_json", healthy)
    after = ask(db, question)
    assert healthy.calls, "the outage answer must not be served from cache"
    assert after["provider"] == "groq"
    assert after["answer"] == "Marcus Reyes: skin temperature elevated vs baseline."


def test_ask_caches_a_real_no_match_answer(db, groq_configured, monkeypatch):
    """The other half of the same rule: a verified "nothing matches" IS a
    finding about the roster, and it caches like any other answer."""
    question = "Which patients have a rash?"
    llm = FakeLLM(
        retrieved={"answer": "Nobody.", "patient_ids": []},
        verdicts={},
        composed=None,
    )
    monkeypatch.setattr(ask_mod, "complete_json", llm)
    first = ask(db, question)
    assert first["provider"] == "groq"
    assert first["answer"] == "No patients on the roster match that right now."
    calls_after_first = len(llm.calls)
    second = ask(db, question)
    assert second["generated_at"] == first["generated_at"]
    assert len(llm.calls) == calls_after_first


def test_a_partial_outage_is_never_answered_as_a_finding(db, groq_configured, monkeypatch):
    """The half the cooldown-based check could not see.

    When some candidate checks fail and others succeed, the composed answer
    names only the survivors and reads exactly like a complete answer — "1
    match: Marcus" while two patients were never looked at. The old guard
    inferred the outage from provider_name() changing, so it only covered
    providers whose failures cool down, and on a tier that trips no cooldown
    the outage-shaped answer was persisted as a real-provider finding and
    served from cache on every later ask of that question.
    """
    question = "Who has signs of infection today?"
    seen: list[str] = []

    def partial(system, user, **kwargs):
        if system is ASK_SYSTEM:
            return {"answer": "Several.", "patient_ids": ["marcus", "linda", "sofia"]}
        if system is VERIFY_SYSTEM:
            seen.append(user)
            if len(seen) == 1:
                return {"match": True, "evidence": "skin temperature elevated vs baseline"}
            raise LLMError("verification unavailable")  # no cooldown tripped
        return {"answer": "Marcus Reyes: skin temperature elevated."}

    monkeypatch.setattr(ask_mod, "complete_json", partial)
    assert provider_mod.provider_name() == "groq"  # the provider still looks healthy
    result = ask(db, question)
    assert len(seen) > 1, "the premise: some checks ran, some failed"
    assert provider_mod.provider_name() == "groq"
    assert result["provider"] == "fallback"
    assert result["answer"] != "Marcus Reyes: skin temperature elevated."

    # and it was not cached as a provider answer: the next ask retries
    seen.clear()
    ask(db, question)
    assert seen, "a degraded answer must not satisfy a real-provider cache key"


def test_a_rotation_of_questions_stays_cached(db, groq_configured, monkeypatch):
    """Every /ask answer lives in one (patient_id=NULL, kind='ask') series, so
    the per-series cap evicted by recency across UNRELATED questions.

    With more questions in rotation than the cap, nothing was ever a hit
    again: each round re-ran retrieve → verify → compose for every question,
    forever. Pruning that was introduced to stop unbounded LLM calls became an
    unbounded-LLM-call path of its own.
    """
    from app.llm import insights as insights_mod

    questions = [
        f"Which patients have concern number {n}?"
        for n in range(insights_mod.KEEP_PER_SERIES + 4)
    ]
    llm = FakeLLM(
        retrieved={"answer": "Marcus.", "patient_ids": ["marcus"]},
        verdicts={"marcus": {"match": True, "evidence": "skin temperature elevated"}},
        composed={"answer": "Marcus Reyes: skin temperature elevated."},
    )
    monkeypatch.setattr(ask_mod, "complete_json", llm)
    for question in questions:
        ask(db, question)
    assert llm.calls, "the premise: the first round really called the provider"

    llm.calls.clear()
    for question in questions:
        result = ask(db, question)
        assert result["provider"] == "groq"
    assert llm.calls == [], "a second round of the same questions must be free"
