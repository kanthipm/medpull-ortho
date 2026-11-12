"""Sorting what a person writes, and the clinic's fixed words.

Two jobs, both by plain rules a clinician can read and change, and neither
by a model.

**Questions.** A line a person typed is a question when it asks one. A
question goes to *today* when it carries one of the clinic's always-today
words (pain, swelling, "before my session": ``app/pt/settings.py``), and to
the *weekly* block otherwise, where the therapist answers a week's worth at
once. A clinician can move any line either way. Nothing here replies.

**Red flags.** A short list of things a clinic never wants to sit unread
(numbness in the saddle area, a calf that is hot and swollen). A line that
matches one is marked, goes to today, and raises the care team's notice.
What goes back to the person is the clinic's own text for that entry, word
for word, and only once a clinician has approved it. Until then the reply
is the one fixed line below, which promises nothing and says where an
emergency belongs. The assistant never answers a line that matched.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mobile import Message
from app.models.patient import Patient
from app.pt import settings as pt_settings
from app.pt.models import RedFlagText

TODAY, WEEKLY = "today", "weekly"

# What goes back when a line matches an entry the clinic has not written (or
# not approved) its own words for. Fixed here; never generated.
STANDING_REPLY = (
    "Your message has gone to your care team, marked urgent. This line is not watched "
    "around the clock: if this feels like an emergency, call 911."
)

_QUESTION = re.compile(
    r"\?|^\s*(can|could|should|shall|is|are|am|do|does|did|how|what|when|where|why|which|"
    r"will|would|may|ok to|okay to|is it ok|is it okay)\b",
    re.IGNORECASE,
)

# The entries a clinic starts with: what to listen for, and nothing to say
# until a clinician writes it. ``starter`` is a draft for her to rewrite, with
# a blank she has to fill before it can be approved.
STARTERS: tuple[dict[str, Any], ...] = (
    {
        "key": "saddle_numbness", "label": "Numbness between the legs or around the saddle area",
        "phrases": ["saddle", "numb between my legs", "numbness between my legs", "numb groin",
                    "numb around my groin", "can't feel when i wipe"],
    },
    {
        "key": "bladder_bowel", "label": "A change in bladder or bowel control",
        "phrases": ["can't pee", "cannot pee", "can't urinate", "wet myself", "lost control of my bladder",
                    "lost control of my bowel", "bowel control", "bladder control", "incontinence"],
    },
    {
        "key": "leg_weakness", "label": "Weakness that is spreading or new foot drop",
        "phrases": ["foot drop", "foot is dragging", "leg gave out and", "legs are getting weaker",
                    "leg is getting weaker", "can't lift my foot", "weakness is spreading"],
    },
    {
        "key": "calf_swelling", "label": "A calf that is painful, swollen, warm or red",
        "phrases": ["calf is swollen", "swollen calf", "calf is hot", "calf is warm", "calf is red",
                    "calf swelling"],
    },
    {
        "key": "chest_breath", "label": "Chest pain or trouble breathing",
        "phrases": ["chest pain", "chest is tight", "can't breathe", "cannot breathe",
                    "short of breath", "shortness of breath"],
    },
)
STARTER_TEXT = (
    "Please call the clinic now at [clinic phone number] about this. If you cannot reach us, "
    "go to the nearest emergency department."
)
TEXT_LIMIT = 480
PHRASE_LIMIT = 60
MAX_PHRASES = 24


class RedFlagError(ValueError):
    """An entry the page cannot save; the message is for the person typing."""


# --- questions ---------------------------------------------------------------------------


def is_question(text: str) -> bool:
    return bool(_QUESTION.search(text or ""))


def _has(words: list[str], text: str) -> str | None:
    lowered = f" {re.sub(r'[^a-z0-9’ ]+', ' ', (text or '').lower().replace(chr(39), '’'))} "
    for word in words:
        needle = word.lower().replace("'", "’").strip()
        if needle and f" {needle} " in lowered:
            return word
        # A word list is short and typed by people: also take a leading match
        # so "swell" finds "swelling" without anyone writing a pattern.
        if needle and re.search(rf"(?<![a-z0-9]){re.escape(needle)}", lowered):
            return word
    return None


def classify(text: str, words: list[str]) -> str | None:
    """Where a typed line goes: today, the weekly block, or nowhere (it is
    not a question and carries none of the clinic's words)."""
    hit = _has(words, text)
    if is_question(text):
        return TODAY if hit else WEEKLY
    return TODAY if hit and len((text or "").split()) >= 3 else None


# --- red flags ---------------------------------------------------------------------------


def ensure_entries(db: Session, hospital_id: str) -> list[RedFlagText]:
    """The clinic's entries, with the starters added the first time anyone
    looks (as drafts: they listen, they send nothing). Idempotent."""
    rows = db.scalars(
        select(RedFlagText).where(RedFlagText.hospital_id == hospital_id).order_by(RedFlagText.id)
    ).all()
    have = {r.key for r in rows}
    added = False
    for starter in STARTERS:
        if starter["key"] in have:
            continue
        row = RedFlagText(hospital_id=hospital_id, key=starter["key"], label=starter["label"],
                          phrases=list(starter["phrases"]), text=STARTER_TEXT, status="draft")
        db.add(row)
        rows.append(row)
        added = True
    if added:
        db.flush()
    return rows


def match(db: Session, hospital_id: str | None, text: str) -> RedFlagText | None:
    if not hospital_id or not (text or "").strip():
        return None
    for row in ensure_entries(db, hospital_id):
        if _has([str(p) for p in (row.phrases or [])], text):
            return row
    return None


def entry_view(row: RedFlagText) -> dict[str, Any]:
    return {
        "id": row.id, "key": row.key, "label": row.label, "phrases": list(row.phrases or []),
        "text": row.text or "", "status": row.status,
        "approved_by": row.approved_by,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        # What a person is sent today if their line matches this entry.
        "sends": (row.text if row.status == "approved" else STANDING_REPLY),
        "sends_own_words": row.status == "approved",
    }


def _clean_phrases(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise RedFlagError("phrases must be a list")
    out: list[str] = []
    for item in value:
        phrase = " ".join(str(item).lower().split())
        if not phrase:
            continue
        if len(phrase) > PHRASE_LIMIT:
            raise RedFlagError(f"A phrase is at most {PHRASE_LIMIT} characters")
        if len(phrase) < 4:
            raise RedFlagError("A phrase needs at least four characters, or it matches everything")
        if phrase not in out:
            out.append(phrase)
    if not out:
        raise RedFlagError("An entry needs at least one phrase to listen for")
    if len(out) > MAX_PHRASES:
        raise RedFlagError(f"At most {MAX_PHRASES} phrases per entry")
    return out


def save_entry(db: Session, hospital_id: str, *, entry_id: int | None, label: str | None,
               phrases: Any, text: str | None, by: str | None) -> RedFlagText:
    """Create or edit an entry. Any change to its words puts it back to
    draft: what was approved is no longer what would be sent."""
    ensure_entries(db, hospital_id)
    now = datetime.now()
    if entry_id is None:
        clean_label = " ".join((label or "").split())[:120]
        if not clean_label:
            raise RedFlagError("Name what this entry is for")
        key = re.sub(r"[^a-z0-9]+", "_", clean_label.lower()).strip("_")[:40] or "entry"
        taken = set(db.scalars(select(RedFlagText.key).where(RedFlagText.hospital_id == hospital_id)))
        base, n = key, 2
        while key in taken:
            key, n = f"{base}_{n}", n + 1
        row = RedFlagText(hospital_id=hospital_id, key=key, label=clean_label, phrases=[],
                          text="", status="draft")
        db.add(row)
    else:
        row = db.get(RedFlagText, entry_id)
        if row is None or row.hospital_id != hospital_id:
            raise RedFlagError("Unknown entry")
        if label is not None and " ".join(label.split()):
            row.label = " ".join(label.split())[:120]
    if phrases is not None:
        row.phrases = _clean_phrases(phrases)
    elif entry_id is None:
        raise RedFlagError("An entry needs at least one phrase to listen for")
    if text is not None:
        words = text.strip()
        if len(words) > TEXT_LIMIT:
            raise RedFlagError(f"The text is at most {TEXT_LIMIT} characters")
        if words != (row.text or ""):
            row.text = words
            row.status, row.approved_by, row.approved_at = "draft", None, None
    row.updated_by, row.updated_at = by, now
    db.commit()
    return row


def approve_entry(db: Session, hospital_id: str, entry_id: int, *, by: str, approved: bool
                  ) -> RedFlagText:
    """A clinician puts her name to an entry's words (or takes it off). The
    words must be finished: nothing empty, no blank left in brackets."""
    from app.models.patient import CareTeamMember

    row = db.get(RedFlagText, entry_id)
    if row is None or row.hospital_id != hospital_id:
        raise RedFlagError("Unknown entry")
    if not approved:
        row.status, row.approved_by, row.approved_at = "draft", None, None
    else:
        member = db.get(CareTeamMember, by) if by else None
        if member is None:
            raise RedFlagError("Pick the clinician who is approving these words")
        if not (row.text or "").strip():
            raise RedFlagError("Write the text before approving it")
        if "[" in row.text or "]" in row.text:
            raise RedFlagError("Fill in the part in brackets before approving the text")
        row.status, row.approved_by, row.approved_at = "approved", member.id, datetime.now()
    row.updated_by, row.updated_at = by, datetime.now()
    db.commit()
    return row


def delete_entry(db: Session, hospital_id: str, entry_id: int) -> None:
    row = db.get(RedFlagText, entry_id)
    if row is None or row.hospital_id != hospital_id:
        raise RedFlagError("Unknown entry")
    db.delete(row)
    db.commit()


# --- a line arrives -----------------------------------------------------------------------


def on_patient_line(db: Session, patient: Patient, message: Message) -> dict[str, Any]:
    """Sort one line a person typed (in the app or by text) and say what, if
    anything, the clinic's standing words answer it with.

    Returns ``{"red_flag": entry or None, "reply": str or None, "by": care
    team id or None, "triage": "today" | "weekly" | None}``. ``reply`` is
    set only for a red flag: the clinic's approved text, else the standing
    line. The caller sends it and writes its thread line; this function
    only marks the message and raises the notice. The caller commits."""
    text = message.text or ""
    now = datetime.now()
    entry = match(db, patient.hospital_id, text)
    if entry is not None:
        message.triage, message.triage_by, message.triage_at = TODAY, "rule", now
        message.red_flag = entry.key
        from app.models.enums import NotificationChannel
        from app.models.notification import Notification

        db.add(Notification(
            patient_id=patient.id, recipient_id=patient.assigned_provider_id,
            kind="red_flag", title=f"{patient.name} — {entry.label}",
            body=f"They wrote: “{text[:300]}”", channel=NotificationChannel.IN_APP,
        ))
        approved = entry.status == "approved" and (entry.text or "").strip()
        return {"red_flag": entry, "reply": entry.text if approved else STANDING_REPLY,
                "by": entry.approved_by if approved else None, "triage": TODAY}
    words = pt_settings.read(db, patient.hospital_id)["triage_words"]
    where = classify(text, words)
    if where is not None:
        message.triage, message.triage_by, message.triage_at = where, "rule", now
    return {"red_flag": None, "reply": None, "by": None, "triage": where}


def applies_to(patient: Patient) -> bool:
    """Whose lines are sorted: a clinic chart's. A subscriber's and an
    athlete's spaces have no clinic reading a weekly block."""
    from app.personal.scope import is_clinic

    return is_clinic(patient)
