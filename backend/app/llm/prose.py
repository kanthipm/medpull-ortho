"""Model-written prose is read by clinicians, so it must not carry engine codes.

The insight prompts hand the model the analytics JSON, where a tier is
``"level": "missing_data"``, and the model sometimes echoes that verbatim: a
worklist row once read "No postoperative data reported · risk missing_data".
Cleaning the text where it leaves the API also covers insights that are
already cached, and needs no prompt change. Bumping PROMPT_VERSION would
regenerate every cached insight at once and run into Groq's rate limit.
"""

import re

# "risk missing_data", "risk: high" -> the phrase a clinician would say.
_RISK_PHRASE = re.compile(r"\brisk[\s:=]+(high|medium|low|missing_data)\b", re.IGNORECASE)
# Any remaining identifier with an underscore: missing_data, COMPOSITE_HIGH.
_CODE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")

_RISK_WORDS = {
    "high": "high risk",
    "medium": "medium risk",
    "low": "low risk",
    "missing_data": "not enough data to assess risk",
}


def _words(match: re.Match[str]) -> str:
    token = match.group(0)
    spaced = token.replace("_", " ")
    # An all-caps code reads as shouting in a sentence.
    return spaced.lower() if token.isupper() else spaced


def humanize_codes(text: str) -> str:
    """Turn engine identifiers inside model prose into words."""
    if not text:
        return text
    text = _RISK_PHRASE.sub(lambda m: _RISK_WORDS[m.group(1).lower()], text)
    return _CODE.sub(_words, text)
