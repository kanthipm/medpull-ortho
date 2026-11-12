"""The texts the exercise calendar sends, each carrying a link that opens
the app at the right screen (``app/links.py``).

Three callers, three functions; every one returns None when nothing was
sent (no phone on the chart, a placeholder number, texting not configured,
the patient opted out) and never raises into the route that called it: a
text that cannot go out must not undo the assignment or the review it
announces.

* ``notify_assigned`` — the therapist put exercises on a day and asked for
  the lifter to be told (``POST /api/hep/schedule`` with ``text_patient``).
* ``notify_review`` — the therapist replied to a clip
  (``POST /api/hep/schedule/{id}/review`` with a note).
* ``text_today`` — "text today's plan" from the console, and the morning
  reminder run (``app/hep/reminders.py``).

Each goes through ``sendblue.compose`` and ``sendblue.send_sms`` like every
other patient text, and each leaves one line on the thread: channel
``sms``, the delivery state, and the link's place as a button
(``Message.action_view``) so the app offers the same tap the text did. The
words are the SMS's own: straight apostrophes, no name, nothing clinical
beyond an exercise title and what the therapist herself wrote.

A function here commits its own rows. A text cannot be unsent, and the
link in it only opens while its row exists, so call these after your own
commit rather than inside a transaction you may still roll back.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import links
from app.aws import storage
from app.hep.models import Exercise, ExerciseAssignment
from app.llm.insights import BANNED
from app.models.mobile import Message
from app.models.patient import CareTeamMember, Patient
from app.notifications import reachability, sendblue

logger = logging.getLogger(__name__)

# The longest first sentence of a review note that rides in the text; a
# longer one stays behind the link, where the whole note is.
SHORT_NOTE = 140
CARE_TEAM = "Your care team"
REST_DAY = "Rest is part of the program."

# A text is read as GSM-7 where it can be: a curly quote or a long dash
# turns the whole message into the 70-character encoding.
_PLAIN = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", " ": " ",
})


# --- whether a text can go at all ----------------------------------------------------


def cannot_text(patient: Patient) -> tuple[str, str] | None:
    """Why this chart cannot be texted, as ``(code, sentence)``, or None
    when a send can be tried. The sentence is for the clinician who pressed
    the button. Codes: ``no_phone``, ``placeholder``, ``opted_out``,
    ``not_configured``."""
    if not patient.phone:
        return "no_phone", "This chart has no phone number, so there is nowhere to text."
    if reachability.is_placeholder(patient.phone):
        return (
            "placeholder",
            "This chart's number is a 555 placeholder. Bind a real phone to it from the "
            "demo app, then text again.",
        )
    if patient.sms_opt_out_at is not None:
        return (
            "opted_out",
            f"This number replied STOP on {_month_day(patient.sms_opt_out_at.date())}, so "
            "MedPull no longer texts it. Texts resume when they reply START.",
        )
    if not sendblue.configured():
        return "not_configured", "Texting is not set up on this server, so nothing was sent."
    return None


# --- words -----------------------------------------------------------------------------


def _month_day(day: date) -> str:
    return f"{day.strftime('%b')} {day.day}"


def day_word(day: date, today: date) -> str:
    """How a text names a day: today, tomorrow, the weekday inside a week,
    the weekday and date beyond it."""
    ahead = (day - today).days
    if ahead == 0:
        return "today"
    if ahead == 1:
        return "tomorrow"
    if 1 < ahead < 7:
        return day.strftime("%A")
    return f"{day.strftime('%A')}, {_month_day(day)}"


def _count(n: int, noun: str = "exercise") -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _clean(text: str, patient: Patient) -> str:
    """One variable piece of a text (an exercise title, the therapist's
    sentence) in SMS characters, with the patient's own name taken back
    out. The therapist's name is never passed through here: it is the one
    name the text is meant to carry."""
    return sendblue.redact_name(" ".join((text or "").translate(_PLAIN).split()), patient.name)


def _titles(db: Session, rows: list[ExerciseAssignment], patient: Patient) -> list[str]:
    titles = []
    for row in rows:
        exercise = db.get(Exercise, row.exercise_id)
        titles.append(_clean(exercise.title if exercise else "an exercise", patient))
    return titles


def _member(db: Session, *member_ids: str | None) -> CareTeamMember | None:
    """The first of ``member_ids`` that names a care-team member."""
    for member_id in member_ids:
        member = db.get(CareTeamMember, member_id) if member_id else None
        if member is not None and (member.name or "").strip():
            return member
    return None


def first_sentence(note: str, patient: Patient) -> str:
    """The opening sentence of a review note when it is short enough to
    ride in the text, else nothing. Wording the thread would refuse
    (``BANNED``) never rides either."""
    text = _clean(note, patient)
    found = re.match(r"(.+?[.!?])(?:\s|$)", text)
    sentence = found.group(1) if found else text
    if not sentence or len(sentence) > SHORT_NOTE or BANNED.search(sentence):
        return ""
    return sentence if sentence[-1] in ".!?" else sentence + "."


def _day_rows(db: Session, patient_id: str, day: date) -> list[ExerciseAssignment]:
    return list(db.scalars(
        select(ExerciseAssignment)
        .where(ExerciseAssignment.patient_id == patient_id,
               ExerciseAssignment.scheduled_for == day)
        .order_by(ExerciseAssignment.sort_order, ExerciseAssignment.id)
    ).all())


def _day_link(day: date, today: date) -> tuple[str, str]:
    """The link kind and its label for a day: today's list, or the program
    opened at that day."""
    if day == today:
        return "today", "Open today's plan"
    return "program", "Open your program"


def assigned_body(who: str, first_day: date, titles: list[str], other_days: int,
                  today: date) -> str:
    """The assignment text: who added how many for which day, the first
    title, and how many other days carry more."""
    body = f"{who} added {_count(len(titles))} for {day_word(first_day, today)}: {titles[0]}"
    if len(titles) > 1:
        body += f" and {len(titles) - 1} more"
    body += "."
    if other_days:
        body += (" 1 more day is on your program." if other_days == 1
                 else f" {other_days} more days are on your program.")
    return body


def review_body(who: str, title: str, sentence: str, *, has_clip: bool) -> str:
    """The review text: who replied to which exercise's clip, and her first
    sentence when it was short enough to carry."""
    what = f"replied to your {title} clip" if has_clip else f"left a note on your {title}"
    return f"{who} {what}." + (f" {sentence}" if sentence else "")


def today_body(day: date, today: date, titles: list[str], open_titles: list[str],
               all_done: bool) -> str:
    """The plan text for one day: how many exercises and the first title,
    or the variant for a day with nothing on it, partly done, or finished.
    ``titles`` are the day's rows in order, ``open_titles`` the ones still
    to do."""
    word = day_word(day, today)
    if not titles:
        when = word if word in ("today", "tomorrow") else f"on {word}"
        return f"Nothing assigned {when}. {REST_DAY}"
    lead = {"today": "Today's plan", "tomorrow": "Tomorrow's plan"}.get(word, f"Plan for {word}")
    if not open_titles:
        if not all_done:
            return f"{lead}: nothing left to do."
        if len(titles) == 1:
            return f"{lead}: {titles[0]} is marked done."
        return f"{lead}: all {len(titles)} exercises are marked done."
    if len(open_titles) < len(titles):
        return (f"{lead}: {len(open_titles)} of {_count(len(titles))} left, "
                f"starting with {open_titles[0]}.")
    if len(titles) == 1:
        return f"{lead}: 1 exercise, {titles[0]}."
    return f"{lead}: {len(titles)} exercises, starting with {titles[0]}."


# --- the send ----------------------------------------------------------------------------


def _send(
    db: Session,
    patient: Patient,
    body: str,
    *,
    kind: str,
    link_label: str,
    base_url: str | None,
    ref_id: int | None = None,
    day: date | None = None,
    member: CareTeamMember | None = None,
    tag: bool = False,
    media_url: str | None = None,
) -> dict | None:
    """Mint the link, text ``body`` with it, and leave the thread line.

    ``member`` is the clinician who stands behind the text: the line is
    hers on the thread. ``tag`` adds the "(your care team)" prefix for a
    body that does not already name her."""
    # The link only opens while its row exists. Under a write lock that has
    # been taken over, everything written here is about to be discarded, so
    # nothing is sent rather than a text whose link is dead on arrival.
    if not storage.holds_lock(unknown_as_held=True):
        logger.warning("Not texting %s: the database write lock was taken over", patient.id)
        return None
    link, token = links.mint_link(db, patient, kind, ref_id=ref_id, day=day)
    url = links.text_url(token, base_url)
    text = sendblue.compose(body, member=member if tag else None, link=url, link_label=link_label)
    delivery = (sendblue.send_sms(patient.phone, text, media_url=media_url) if media_url
                else sendblue.send_sms(patient.phone, text))
    message = Message(
        patient_id=patient.id,
        sender="care_team" if member is not None else "copilot",
        sender_id=member.id if member is not None else None,
        channel="sms",
        text=text,
        authored_by="care_team" if member is not None else "ai",
        delivery_status=sendblue.delivery_status_for(delivery),
        delivery_detail=sendblue.delivery_detail_for(delivery),
        external_handle=delivery.message_handle,
        action_kind=f"open_{kind}",
        action_label=link_label,
        action_ref=None if ref_id is None else str(ref_id),
        action_day=day,
        action_url=url,
    )
    db.add(message)
    db.flush()
    link.message_id = message.id
    db.commit()
    if not delivery.sent:
        logger.info("Exercise text for %s not sent: %s", patient.id, delivery.detail)
    return {
        "sent": delivery.sent,
        "status": message.delivery_status,
        "detail": message.delivery_detail,
        "message_id": message.id,
        "link": url,
        # The number has not texted the line yet (Sendblue's free plan): not
        # a fault, and it clears the moment the person texts MedPull once.
        "unreachable": bool(delivery.unreachable),
    }


def _guarded(db: Session, what: str, patient_id: str, send) -> dict | None:
    """Run one of the three texts so that nothing it does reaches the
    caller as an exception."""
    try:
        return send()
    except Exception:  # noqa: BLE001 — a text must never fail the write it announces
        logger.exception("%s text for %s failed", what, patient_id)
        db.rollback()
        return None


def notify_assigned(
    db: Session,
    patient: Patient,
    rows: list[ExerciseAssignment],
    *,
    base_url: str | None = None,
    by: str | None = None,
) -> dict | None:
    """Text ``patient`` that ``rows`` were added to their calendar, with a
    link to the first day among them. ``by`` is the care-team member id the
    text is signed with. Returns ``{"sent": bool, "status": str, "detail":
    str | None, "message_id": int | None, "link": str}`` or None.

    Days already behind today are the therapist logging what was done, not
    news for the lifter: only today and later count, and rows with none of
    those send nothing."""

    def send() -> dict | None:
        today = date.today()
        upcoming = sorted((r for r in rows if r.scheduled_for >= today),
                          key=lambda r: (r.scheduled_for, r.sort_order or 0, r.id or 0))
        if not upcoming or cannot_text(patient) is not None:
            return None
        first_day = upcoming[0].scheduled_for
        first = [r for r in upcoming if r.scheduled_for == first_day]
        other_days = len({r.scheduled_for for r in upcoming}) - 1
        member = _member(db, by, first[0].assigned_by, patient.assigned_provider_id)
        kind, label = _day_link(first_day, today)
        body = assigned_body(member.name.strip() if member else CARE_TEAM, first_day,
                             _titles(db, first, patient), other_days, today)
        return _send(db, patient, body, kind=kind, link_label=label, base_url=base_url,
                     day=first_day, member=member)

    return _guarded(db, "Assignment", patient.id, send)


def notify_review(
    db: Session,
    row: ExerciseAssignment,
    *,
    base_url: str | None = None,
) -> dict | None:
    """Text the patient that their therapist replied to the clip on ``row``,
    with a link to that exercise. Same return shape as ``notify_assigned``.
    A review with no note said nothing to the patient, so it sends nothing."""

    def send() -> dict | None:
        patient = db.get(Patient, row.patient_id)
        note = (row.review_note or "").strip()
        if patient is None or not note or cannot_text(patient) is not None:
            return None
        member = _member(db, row.reviewed_by, patient.assigned_provider_id)
        body = review_body(
            member.name.strip() if member else CARE_TEAM,
            _titles(db, [row], patient)[0],
            first_sentence(note, patient),
            has_clip=row.video_attachment_id is not None,
        )
        return _send(db, patient, body, kind="exercise", link_label="See the reply",
                     base_url=base_url, ref_id=row.id, day=row.scheduled_for, member=member)

    return _guarded(db, "Review", row.patient_id, send)


def text_today(
    db: Session,
    patient: Patient,
    *,
    base_url: str | None = None,
    day: date | None = None,
    by: str | None = None,
) -> dict | None:
    """Text ``patient`` the plan for ``day`` (default today): how many
    exercises, the first title, and a link to the day. Same return shape.

    ``by`` names the clinician who asked for it, and the text is tagged
    with her name; without it the text is the app's own (the morning run)
    and carries no tag."""

    def send() -> dict | None:
        if cannot_text(patient) is not None:
            return None
        today = date.today()
        the_day = day or today
        rows = _day_rows(db, patient.id, the_day)
        open_rows = [r for r in rows if r.status == "assigned"]
        kind, label = _day_link(the_day, today)
        body = today_body(
            the_day, today, _titles(db, rows, patient), _titles(db, open_rows, patient),
            all_done=bool(rows) and all(r.status == "done" for r in rows),
        )
        member = _member(db, by)
        return _send(db, patient, body, kind=kind, link_label=label, base_url=base_url,
                     day=the_day, member=member, tag=True)

    return _guarded(db, "Today's plan", patient.id, send)


WELCOME_BODY = ("You're connected to the MedPull demo. Texts for this demo person now reach "
                "this phone.")


def welcome(db: Session, patient: Patient, *, base_url: str | None = None) -> dict | None:
    """The first text to a phone the demo app just bound to a persona
    (``app/api/demo_phone.py``): one line saying it worked, a link that
    opens the app on today, and the line's contact card so later texts
    arrive under a name instead of a number. Same return shape as the rest."""

    def send() -> dict | None:
        if cannot_text(patient) is not None:
            return None
        from app.notifications import contact_card

        return _send(db, patient, WELCOME_BODY, kind="today", link_label="Open the app",
                     base_url=base_url, day=date.today(),
                     media_url=contact_card.card_url(patient.hospital_id))

    return _guarded(db, "Welcome", patient.id, send)
