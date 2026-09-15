"""The insight layer's model-call switch: a read that is not allowed to call
the model must still answer (deterministically), must not poison the
real-provider cache key, and must leave the next permitted read free to
regenerate with the model."""

from sqlalchemy import delete, select

from app.llm import insights
from app.models.enums import InsightKind
from app.models.insight import Insight


def _clear(db, patient_id: str, kind: InsightKind) -> None:
    db.execute(
        delete(Insight).where(Insight.patient_id == patient_id, Insight.kind == kind)
    )
    db.commit()


def test_allow_llm_false_serves_fallback_without_filling_the_model_key(db, monkeypatch):
    patient_id, kind = "robert", InsightKind.PATIENT_SUMMARY
    calls: list[str] = []

    def fake_complete_json(system, user, **kwargs):
        calls.append(user)
        return {"summary": "Robert is six days out with activity sliding and sleep holding. " * 2}

    monkeypatch.setattr(insights, "provider_name", lambda: "groq")
    monkeypatch.setattr(insights, "model_name", lambda: "fake-model")
    monkeypatch.setattr(insights, "complete_json", fake_complete_json)
    _clear(db, patient_id, kind)
    try:
        assert insights.insight_is_cached(db, kind, patient_id) is False

        served = insights.get_patient_insight(db, kind, patient_id, allow_llm=False)
        assert served.llm_provider == "fallback"
        assert calls == []  # no model call was made
        # The deterministic row lives under its own key: the model key is still empty.
        assert insights.insight_is_cached(db, kind, patient_id) is False

        # A second disallowed read is a cache hit on the fallback row, not a rewrite.
        again = insights.get_patient_insight(db, kind, patient_id, allow_llm=False)
        assert again.id == served.id

        # The next permitted read regenerates with the model and caches it.
        fresh = insights.get_patient_insight(db, kind, patient_id)
        assert fresh.llm_provider == "groq"
        assert len(calls) == 1
        assert insights.insight_is_cached(db, kind, patient_id) is True
        rows = db.scalars(
            select(Insight).where(Insight.patient_id == patient_id, Insight.kind == kind)
        ).all()
        assert {r.llm_provider for r in rows} == {"fallback", "groq"}
    finally:
        _clear(db, patient_id, kind)


def test_low_tier_worklist_reason_never_needs_the_model(db, monkeypatch):
    """Stable patients' reasons are deliberate fallback text (see
    get_patient_insight), so the cache probe reports them as free."""
    monkeypatch.setattr(insights, "provider_name", lambda: "groq")
    assert insights.insight_is_cached(db, InsightKind.WORKLIST_REASON, "james") is True
