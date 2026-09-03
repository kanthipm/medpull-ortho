"""Check-in digest: the highlight must be the patient's informative report,
never a bare acknowledgment; topics and tone come from their own words."""

from app.engine.checkin_digest import digest
from app.seed.conversations import CONVERSATIONS


def _messages(patient_id: str, index: int) -> list[dict]:
    _, _, msgs = CONVERSATIONS[patient_id][index]
    return [{"who": who, "text": text} for who, text in msgs]


FEVER_CHECKIN = [
        {"who": "copilot", "text": "Good morning. Checking in — how are you feeling?"},
        {"who": "patient", "text": "Honestly, worse. My pain has gotten worse and I felt feverish last night."},
        {"who": "copilot", "text": "I'm sorry you're feeling worse. Did you take your temperature?"},
        {"who": "patient", "text": "I didn't have a thermometer handy, but I was sweating and had chills."},
        {"who": "copilot", "text": "Understood. Is the knee still warm and swollen today?"},
        {"who": "patient", "text": "Yes, it's warm to the touch and pretty swollen."},
        {"who": "copilot", "text": "Thank you for telling me. If you develop severe pain or a fever, call the clinic right away."},
        {"who": "patient", "text": "Okay, I will."},
    ]


def test_acknowledgment_never_wins():
    """A check-in that ends with 'Okay, I will.' — the digest must quote the
    symptom report instead."""
    d = digest(FEVER_CHECKIN)
    assert d["highlight"] is not None
    assert "okay" not in d["highlight"].lower()
    assert "worse" in d["highlight"].lower() or "feverish" in d["highlight"].lower()


def test_symptom_topics_and_tone():
    d = digest(FEVER_CHECKIN)
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
    body = client.get("/api/patients/linda/checkins").json()
    latest = body["checkins"][0]
    assert "digest" in latest
    assert latest["digest"]["highlight"] is not None
    assert "okay" not in latest["digest"]["highlight"].lower()
    assert isinstance(latest["digest"]["topics"], list)
