"""Deterministic per-check-in digest: what did the patient actually report?

Turns a transcript into (1) the patient's most clinically informative quote,
(2) topic chips, and (3) the trend the patient described in their own words.
Pure text analysis — no LLM, no numbers invented — so the check-in history
renders instantly and identically every time. Acknowledgment lines ("Okay, I
will.") are never chosen as the highlight.
"""

import re
from typing import Any

# topic -> keyword fragments matched case-insensitively inside patient messages
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "pain": ["pain", "sore", "hurt", "ache", "aching"],
    "swelling": ["swollen", "swelling", "puffier", "puffy"],
    "warmth": ["warm", "redness", "red around"],
    "fever": ["fever", "feverish", "chills", "sweating", "temperature"],
    "sleep": ["sleep", "slept", "woke", "waking", "rough night", "position"],
    "exercises": ["exercise", "exercises", "pendulum", "therapy", "stretches", "reps"],
    "activity": ["walk", "walked", "walking", "steps", "tired", "worn out", "fatigue"],
    "medication": ["pills", "medication", "meds", "dose"],
    "incision": ["incision", "drainage", "bandage", "scar"],
    "dizziness": ["dizzy", "dizziness", "lightheaded"],
}

TOPIC_LABELS: dict[str, str] = {
    "pain": "Pain",
    "swelling": "Swelling",
    "warmth": "Warmth",
    "fever": "Fever/chills",
    "sleep": "Sleep",
    "exercises": "Exercises",
    "activity": "Activity",
    "medication": "Medication",
    "incision": "Incision",
    "dizziness": "Dizziness",
}

_WORSE = ["worse", "creeping up", "increasing", "gotten worse", "more swollen", "badly again"]
_BETTER = ["better", "improving", "easier", "less pain", "manageable"]
_STEADY = ["about the same", "same story", "no change", "nothing new"]

# Pure acknowledgments and empty answers — never worth quoting on their own.
_ACK = re.compile(
    r"^(okay|ok|yes|yeah|no|sure|thanks|thank you|alright|will do|i will|okay,? i will)[.! ]*$",
    re.IGNORECASE,
)


def _patient_texts(messages: list[Any]) -> list[str]:
    texts = []
    for m in messages:
        who = m.get("who") if isinstance(m, dict) else m.who
        text = m.get("text") if isinstance(m, dict) else m.text
        if who == "patient" and text:
            texts.append(text.strip())
    return texts


def _topics(texts: list[str]) -> list[str]:
    joined = " ".join(texts).lower()
    found = [
        TOPIC_LABELS[topic]
        for topic, keywords in TOPIC_KEYWORDS.items()
        if any(k in joined for k in keywords)
    ]
    return found[:4]


def _tone(texts: list[str]) -> str | None:
    joined = " ".join(texts).lower()
    if any(k in joined for k in _WORSE):
        return "worse"
    if any(k in joined for k in _BETTER):
        return "better"
    if any(k in joined for k in _STEADY):
        return "steady"
    return None


def _score(text: str) -> int:
    lowered = text.lower()
    hits = sum(
        1
        for keywords in TOPIC_KEYWORDS.values()
        for k in keywords
        if k in lowered
    )
    trend = sum(1 for k in _WORSE + _BETTER if k in lowered)
    length_bonus = 1 if len(text) > 40 else 0
    return hits * 2 + trend * 2 + length_bonus


def digest(messages: list[Any]) -> dict[str, Any]:
    """Digest one check-in's messages into {highlight, topics, tone}."""
    texts = _patient_texts(messages)
    candidates = [t for t in texts if not _ACK.match(t) and len(t) >= 20]

    highlight: str | None = None
    if candidates:
        # max() keeps the FIRST best-scoring line; later lines win ties only if
        # strictly better, so the digest quotes the earliest strong report.
        highlight = max(candidates, key=_score)
        if _score(highlight) == 0:
            highlight = max(candidates, key=len)
    elif texts:
        highlight = max(texts, key=len)

    return {
        "highlight": highlight,
        "topics": _topics(texts),
        "tone": _tone(texts),
    }
