"""Check-in digest: the highlight must be the patient's informative report,
never a bare acknowledgment; topics and tone come from their own words."""

from app.engine.checkin_digest import digest
from app.seed.conversations import CONVERSATIONS


def _messages(patient_id: str, index: int) -> list[dict]:
    _, _, msgs = CONVERSATIONS[patient_id][index]
    return [{"who": who, "text": text} for who, text in msgs]


def test_acknowledgment_never_wins():
    """Marcus's latest check-in ends with 'Okay, I will.' — the digest must
    quote his symptom report instead."""
    d = digest(_messages("marcus", -1))
    assert d["highlight"] is not None
    assert "okay" not in d["highlight"].lower()
    assert "worse" in d["highlight"].lower() or "feverish" in d["highlight"].lower()


def test_marcus_topics_and_tone():
    d = digest(_messages("marcus", -1))
    assert "Pain" in d["topics"]
    assert "Fever/chills" in d["topics"]
    assert d["tone"] == "worse"


def test_linda_sleep_story():
    d = digest(_messages("linda", 1))
    assert "Sleep" in d["topics"]
    assert d["highlight"] is not None
    assert len(d["highlight"]) >= 20


def test_steady_tone():
    d = digest(
        [
            {"who": "copilot", "text": "How are you today?"},
            {"who": "patient", "text": "About the same as yesterday, honestly."},
        ]
    )
    assert d["tone"] == "steady"


def test_empty_and_ack_only():
    assert digest([])["highlight"] is None
    d = digest(
        [
            {"who": "copilot", "text": "Please call the clinic if it worsens."},
            {"who": "patient", "text": "Okay, I will."},
        ]
    )
    # nothing informative to quote: fall back to the only patient line rather
    # than fabricating, but topics stay empty
    assert d["topics"] == []


def test_api_includes_digest(client):
    body = client.get("/api/patients/marcus/checkins").json()
    latest = body["checkins"][0]
    assert "digest" in latest
    assert latest["digest"]["highlight"] is not None
    assert "okay" not in latest["digest"]["highlight"].lower()
    assert isinstance(latest["digest"]["topics"], list)
