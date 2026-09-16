"""Tasks: created by the care team, texted through Sendblue, completed in the
app, by text, by voice, or on the web page the text links to.

One task is one ``AdherenceTask`` row. Completing it writes the answers as a
``Checkin`` transcript (so the existing check-in history, digest and
narrative prompts see them unchanged) and one ``AdherenceRecord`` for the day
(so the adherence rate finally moves — before the app nothing wrote one).

The SMS conversation is a cursor stored on the task's ``payload``: which
question is being asked and the answers so far. Every inbound text for a
patient with an active cursor is read as an answer to that question; a
patient with no cursor who replies "1" to a task text starts one.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.checkin import Checkin, CheckinMessage
from app.models.enums import AdherenceStatus, NotificationChannel
from app.models.mobile import Message
from app.models.notification import Notification
from app.models.patient import CareTeamMember, Patient
from app.notifications import sendblue

logger = logging.getLogger(__name__)

KINDS = ("checkin", "exercise", "walk", "medication", "wound_check", "custom")
OPEN_STATUSES = ("pending", "sent")
COMPLETION_CHANNELS = ("app", "sms", "voice", "web", "console")

KIND_LABELS = {
    "checkin": "Daily check-in",
    "exercise": "Exercises",
    "walk": "Walk",
    "medication": "Medication",
    "wound_check": "Incision check",
    "custom": "Task",
}

# The daily check-in. api/checkin.py serves the same list on the tokenized
# web form, so a check-in answered by text, in the app or on the web page
# produces the same transcript.
CHECKIN_QUESTIONS: list[dict[str, Any]] = [
    {"id": "pain", "prompt": "How's your pain today, 0 to 10?", "kind": "scale"},
    {"id": "swelling", "prompt": "Any new swelling around the incision?", "kind": "yes_no"},
    {"id": "fever", "prompt": "Any fever or chills?", "kind": "yes_no"},
    {"id": "sleep", "prompt": "How did you sleep?", "kind": "choice",
     "options": ["well", "rough"]},
    {"id": "exercises", "prompt": "Did you get your exercises in?", "kind": "choice",
     "options": ["all", "some", "none"]},
    {"id": "note", "prompt": "Anything else you want the care team to know?", "kind": "text"},
]

# The same check-in for a patient who did not have surgery: no incision, no
# post-op exercises. Picked by ``create_task`` (payload["qset"]) so a
# general patient is never asked about swelling around an incision.
GENERAL_CHECKIN_QUESTIONS: list[dict[str, Any]] = [
    {"id": "pain", "prompt": "Any pain today, 0 to 10?", "kind": "scale"},
    {"id": "sleep", "prompt": "How did you sleep?", "kind": "choice",
     "options": ["well", "rough"]},
    {"id": "activity", "prompt": "Did you get some activity in today?", "kind": "choice",
     "options": ["all", "some", "none"]},
    {"id": "note", "prompt": "Anything else you want the care team to know?", "kind": "text"},
]

QUESTION_SETS: dict[str, list[dict[str, Any]]] = {
    "checkin": CHECKIN_QUESTIONS,
    "checkin_general": GENERAL_CHECKIN_QUESTIONS,
    "exercise": [
        {"id": "exercises", "prompt": "Did you get through the set?", "kind": "choice",
         "options": ["all", "some", "none"]},
        {"id": "pain", "prompt": "Pain during the exercises, 0 to 10?", "kind": "scale"},
        {"id": "note", "prompt": "Anything that felt off?", "kind": "text"},
    ],
    "walk": [
        {"id": "minutes", "prompt": "How many minutes did you walk?", "kind": "number",
         "min": 0, "max": 600},
        {"id": "pain", "prompt": "Pain while walking, 0 to 10?", "kind": "scale"},
    ],
    "medication": [
        {"id": "taken", "prompt": "Did you take it as prescribed?", "kind": "yes_no"},
        {"id": "note", "prompt": "Any side effects or questions?", "kind": "text"},
    ],
    "wound_check": [
        {"id": "swelling", "prompt": "Any new swelling around the incision?", "kind": "yes_no"},
        {"id": "redness", "prompt": "Any spreading redness or warmth?", "kind": "yes_no"},
        {"id": "drainage", "prompt": "Any drainage from the incision?", "kind": "yes_no"},
        {"id": "fever", "prompt": "Any fever or chills?", "kind": "yes_no"},
    ],
    "custom": [
        {"id": "done", "prompt": "Did you get this done?", "kind": "yes_no"},
        {"id": "note", "prompt": "Anything to add?", "kind": "text"},
    ],
}

# Answers become the patient's own words so checkin_digest picks up topics
# and reported trend exactly as it does for seeded transcripts.
PHRASES: dict[str, dict[str, str]] = {
    "swelling": {"yes": "It looks more swollen than yesterday.", "no": "No new swelling."},
    "fever": {"yes": "I've felt feverish with some chills.", "no": "No fever or chills."},
    "sleep": {"well": "I slept fine.", "rough": "It was a rough night, I kept waking up."},
    "exercises": {
        "all": "I did all my exercises.",
        "some": "I did some of my exercises.",
        "none": "I couldn't do my exercises today.",
    },
    "redness": {
        "yes": "There's some redness spreading around the incision.",
        "no": "No new redness around the incision.",
    },
    "drainage": {
        "yes": "There's some drainage from the incision.",
        "no": "The incision is dry, no drainage.",
    },
    "taken": {
        "yes": "I took my medication as prescribed.",
        "no": "I missed a dose of my medication.",
    },
    "done": {"yes": "I got it done.", "no": "I couldn't get to it today."},
    "activity": {
        "all": "I got my activity in today.",
        "some": "I got some activity in today.",
        "none": "I didn't get any activity in today.",
    },
}

# Answers that should reach the care team as an alert, not just a transcript.
_ALERT_ANSWERS = {("fever", "yes"), ("drainage", "yes"), ("redness", "yes")}
_ALERT_PAIN = 8

_YES = {"yes", "y", "yeah", "yep", "yup", "sure", "true", "1"}
_NO = {"no", "n", "nope", "nah", "false", "0", "none"}



def surgical(patient: Patient) -> bool:
    """Had an operation (followed along a recovery curve) vs. a general patient."""
    return str(patient.procedure_type) != "NONE"


# A care-plan task carries its schedule under payload["care"]. "once" is the
# only one-shot schedule: every other kind is something the patient does again
# tomorrow, so completing it today must not retire it.
RECURRING_SCHEDULES = ("daily", "am_pm", "weekly", "ongoing")


def _care(task: AdherenceTask) -> dict[str, Any]:
    payload = task.payload if isinstance(task.payload, dict) else {}
    care = payload.get("care")
    return care if isinstance(care, dict) else {}


def schedule_of(task: AdherenceTask) -> str:
    """The task's schedule. A task with no care payload (assigned ad hoc from
    the console, or seeded) is one-shot: nothing says it repeats."""
    return str(_care(task).get("schedule") or "once")


def is_recurring(task: AdherenceTask) -> bool:
    return schedule_of(task) in RECURRING_SCHEDULES


def last_done_on(task: AdherenceTask) -> date | None:
    """The day this task was last completed or skipped, from the payload the
    completion writes (``completed_at`` is not enough: it is overwritten and
    a recurring task's status goes back to open)."""
    payload = task.payload if isinstance(task.payload, dict) else {}
    raw = payload.get("last_done")
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None
    if task.completed_at is not None:
        return task.completed_at.date()
    return None


def due_again(task: AdherenceTask, today: date | None = None) -> bool:
    """True when a closed recurring task is owed again today."""
    if not task.active or not is_recurring(task):
        return False
    done = last_done_on(task)
    return done is None or done < (today or date.today())


def closed_for_now(task: AdherenceTask, today: date | None = None) -> bool:
    """True when the patient has nothing to do on this task right now: a
    one-shot task that is finished, or a recurring one already done today."""
    if task.status in OPEN_STATUSES:
        return False
    return not due_again(task, today)


def question_set_key(task: AdherenceTask) -> str:
    payload = task.payload if isinstance(task.payload, dict) else {}
    qset = payload.get("qset")
    if isinstance(qset, str) and qset in QUESTION_SETS:
        return qset
    return task.kind if task.kind in QUESTION_SETS else "custom"


def questions_for(task: AdherenceTask) -> list[dict[str, Any]]:
    """The questions this task asks: its kind's set, unless creation pinned
    another (a general patient's check-in)."""
    return QUESTION_SETS[question_set_key(task)]


# --- answers -------------------------------------------------------------------


def answer_to_text(question: dict[str, Any], raw: Any) -> str:
    """The patient's sentence for one answer, or ValueError if it is not one
    the question accepts."""
    kind = question["kind"]
    qid = question["id"]
    if kind == "scale":
        value = _int(raw)
        if value is None or not 0 <= value <= 10:
            raise ValueError(f"{qid} must be a whole number from 0 to 10")
        if qid == "pain":
            return f"My pain is about {value} out of 10."
        return f"{question['prompt']} {value}."
    if kind == "number":
        value = _int(raw)
        lo, hi = question.get("min", 0), question.get("max", 10_000)
        if value is None or not lo <= value <= hi:
            raise ValueError(f"{qid} must be a whole number from {lo} to {hi}")
        if qid == "minutes":
            return f"I walked about {value} minutes."
        return f"{question['prompt']} {value}."
    if kind in ("yes_no", "choice"):
        options = question.get("options") or ["yes", "no"]
        value = str(raw).strip().lower()
        if value not in options:
            raise ValueError(f"Invalid answer for {qid}")
        phrase = PHRASES.get(qid, {}).get(value)
        return phrase if phrase is not None else f"{question['prompt']} {value}."
    if kind == "text":
        text = str(raw).strip()
        if len(text) > 2000:
            raise ValueError("note is too long")
        if not text:
            raise ValueError("note is empty")
        return text
    raise ValueError(f"Unknown question kind {kind}")


def parse_free_answer(question: dict[str, Any], text: str) -> Any | None:
    """Read a texted or spoken answer. None when it cannot be read."""
    body = text.strip().lower()
    kind = question["kind"]
    if kind in ("scale", "number"):
        m = re.search(r"-?\d+", body)
        if not m:
            return None
        value = int(m.group())
        lo, hi = (0, 10) if kind == "scale" else (question.get("min", 0), question.get("max", 10_000))
        return value if lo <= value <= hi else None
    if kind == "yes_no":
        first = body.split()[0].strip(".,!") if body else ""
        if first in _YES or body.startswith("yes"):
            return "yes"
        if first in _NO or body.startswith("no"):
            return "no"
        return None
    if kind == "choice":
        options: list[str] = question["options"]
        # by index ("1"), by word ("some"), by prefix ("rou" -> rough), by synonym
        if body.isdigit() and 1 <= int(body) <= len(options):
            return options[int(body) - 1]
        for opt in options:
            if body == opt or body.startswith(opt) or opt.startswith(body) and len(body) >= 2:
                return opt
        synonyms = {
            "all": {"all of them", "everything", "every", "yes", "did them all"},
            "some": {"a few", "partly", "part", "most", "half"},
            "none": {"no", "nothing", "didn't", "did not", "couldn't", "skipped"},
            "well": {"good", "great", "fine", "ok", "okay", "slept well"},
            "rough": {"bad", "badly", "poor", "poorly", "terrible", "awful", "not great"},
        }
        for opt in options:
            if any(s in body for s in synonyms.get(opt, set())):
                return opt
        return None
    if kind == "text":
        return text.strip() or None
    return None


def answer_hint(question: dict[str, Any]) -> str:
    kind = question["kind"]
    if kind == "scale":
        return "(reply a number from 0 to 10)"
    if kind == "number":
        return "(reply a number)"
    if kind == "yes_no":
        return "(yes or no)"
    if kind == "choice":
        return "(" + " / ".join(question["options"]) + ")"
    return "(or reply skip)"


def _int(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str) and re.fullmatch(r"\s*-?\d+\s*", raw):
        return int(raw)
    return None


# --- creation & dispatch ---------------------------------------------------------


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def mint_token(task: AdherenceTask) -> str:
    """A fresh link for this task, keeping the one already texted alive.

    The raw token is never stored, so re-minting used to 404 the link in the
    original text the moment the patient asked for another one. The previous
    hash is kept beside the current one and ``find_by_token`` accepts either,
    so both texts work.
    """
    token = secrets.token_urlsafe(24)
    previous = task.token_hash
    task.token_hash = _hash(token)
    if previous and previous != task.token_hash:
        payload = dict(task.payload or {})
        payload["prev_token_hash"] = previous
        task.payload = payload
    return token


def task_url(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/t/{token}"


def deep_link(task: AdherenceTask) -> str:
    return f"{settings.mobile_app_scheme}://tasks/{task.id}"


def find_by_token(db: Session, token: str) -> AdherenceTask | None:
    digest = _hash(token)
    task = db.scalar(select(AdherenceTask).where(AdherenceTask.token_hash == digest))
    if task is not None:
        return task
    # The link from an earlier text for a task whose token was re-minted.
    return db.scalar(
        select(AdherenceTask).where(
            AdherenceTask.payload["prev_token_hash"].as_string() == digest
        )
    )


def create_task(
    db: Session,
    patient: Patient,
    *,
    title: str,
    why: str = "",
    kind: str = "custom",
    due_at: datetime | None = None,
    notify: bool = True,
    base_url: str = "",
    created_by: str | None = None,
) -> tuple[AdherenceTask, sendblue.CheckinSendResult | None]:
    if kind not in KINDS:
        raise ValueError(f"Unknown task kind: {kind}")
    title = title.strip()
    if not title:
        raise ValueError("Task title is required")
    task = AdherenceTask(
        patient_id=patient.id,
        title=title[:120],
        why=(why or "").strip()[:200] or "Assigned by care team",
        verified_by="step data" if kind == "walk" else "self-report",
        kind=kind,
        status="pending",
        created_at=datetime.now(),
        due_at=due_at,
        payload={"created_by": created_by} if created_by else {},
    )
    if kind == "checkin" and not surgical(patient):
        task.payload = {**(task.payload or {}), "qset": "checkin_general"}
    db.add(task)
    db.flush()
    result = dispatch(db, task, patient, base_url) if notify else None
    db.commit()
    return task, result


def assigning_clinician(db: Session, task: AdherenceTask) -> CareTeamMember | None:
    """The clinician who assigned this task, when one did.

    ``create_task`` records them on the payload. A task with no ``created_by``
    was produced by the system — a recurring schedule firing, a plan step the
    copilot executed — and nobody's name belongs on it.
    """
    created_by = (task.payload or {}).get("created_by")
    if not created_by:
        return None
    return db.get(CareTeamMember, created_by)


def dispatch(
    db: Session, task: AdherenceTask, patient: Patient, base_url: str
) -> sendblue.CheckinSendResult:
    """Text the patient about the task. Records the attempt on the thread
    either way, so the console can see what the patient was (or was not)
    sent."""
    if not patient.phone:
        return sendblue.CheckinSendResult(sent=False, detail="patient has no phone number on file")
    token = mint_token(task)
    url = task_url(base_url, token) if base_url else deep_link(task)
    # A task a clinician assigned goes out under their name: "do this" carries
    # different weight from a person than from an app. A task the system
    # scheduled has no clinician behind it and stays untagged.
    member = assigning_clinician(db, task)
    result = sendblue.send_task_message(
        patient.phone, task.title, url, member=member, patient_name=patient.name
    )
    db.add(
        Message(
            patient_id=patient.id,
            sender="care_team" if member is not None else "copilot",
            sender_id=member.id if member is not None else None,
            channel="sms",
            text=sendblue.compose(
                sendblue.TASK_TEMPLATE.format(title=task.title[:80]),
                member=member, link=url, link_label="Open the task",
            ),
            authored_by="care_team" if member is not None else "ai",
            delivery_status="sent" if result.sent else "failed",
            delivery_detail=None if result.sent else result.detail,
            external_handle=result.message_handle,
        )
    )
    if result.sent:
        task.status = "sent"
        task.sent_at = datetime.now()
        # A recurring task texted again today is owed again: clear the marker
        # so the app and the SMS conversation both treat it as open.
        if is_recurring(task):
            payload = dict(task.payload or {})
            payload.pop("last_done", None)
            task.payload = payload
    else:
        logger.info("Task %s for %s not texted: %s", task.id, patient.id, result.detail)
    return result


def open_tasks(db: Session, patient_id: str, today: date | None = None) -> list[AdherenceTask]:
    """What the patient still has to do right now.

    Two kinds of row qualify: one that has never been answered (pending or
    texted), and an active *recurring* care-plan task that was answered on an
    earlier day — a daily walk is owed again today, and retiring it on its
    first completion was why an assigned plan emptied out of the app after one
    check and never came back.
    """
    today = today or date.today()
    rows = db.scalars(
        select(AdherenceTask)
        .where(AdherenceTask.patient_id == patient_id, AdherenceTask.active.is_(True))
        .order_by(AdherenceTask.due_at.is_(None), AdherenceTask.due_at, AdherenceTask.id)
    ).all()
    return [t for t in rows if t.status in OPEN_STATUSES or due_again(t, today)]


def recent_tasks(db: Session, patient_id: str, limit: int = 30) -> list[AdherenceTask]:
    return list(
        db.scalars(
            select(AdherenceTask)
            .where(AdherenceTask.patient_id == patient_id)
            .order_by(AdherenceTask.id.desc())
            .limit(limit)
        ).all()
    )


# --- completion ------------------------------------------------------------------


def transcript(kind: str, answers: dict[str, Any]) -> list[tuple[str, str]]:
    """(prompt, patient sentence) pairs for the answers given. ``kind`` is a
    task kind or a question-set key. Raises ValueError on an answer the
    question does not accept."""
    pairs: list[tuple[str, str]] = []
    for q in QUESTION_SETS.get(kind, QUESTION_SETS["custom"]):
        raw = answers.get(q["id"])
        if raw is None or raw == "":
            continue
        pairs.append((q["prompt"], answer_to_text(q, raw)))
    return pairs


def _adherence_status(kind: str, answers: dict[str, Any]) -> AdherenceStatus:
    if kind == "exercise" and str(answers.get("exercises", "")).lower() == "none":
        return AdherenceStatus.MISSED
    if kind == "medication" and str(answers.get("taken", "")).lower() == "no":
        return AdherenceStatus.MISSED
    if kind == "custom" and str(answers.get("done", "")).lower() == "no":
        return AdherenceStatus.MISSED
    if kind == "walk" and _int(answers.get("minutes")) == 0:
        return AdherenceStatus.MISSED
    return AdherenceStatus.SELF_ATTESTED


def _alerts(answers: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for qid, value in answers.items():
        if (qid, str(value).lower()) in _ALERT_ANSWERS:
            out.append(
                {
                    "fever": "Reported fever or chills",
                    "drainage": "Reported drainage from the incision",
                    "redness": "Reported spreading redness around the incision",
                }[qid]
            )
    pain = _int(answers.get("pain"))
    if pain is not None and pain >= _ALERT_PAIN:
        out.append(f"Reported pain {pain}/10")
    return out


def notify_care_team(db: Session, patient: Patient, title: str, body: str, kind: str) -> None:
    db.add(
        Notification(
            patient_id=patient.id,
            recipient_id=patient.assigned_provider_id,
            kind=kind,
            title=title,
            body=body[:400],
            channel=NotificationChannel.IN_APP,
        )
    )


def complete_task(
    db: Session, task: AdherenceTask, answers: dict[str, Any], via: str
) -> Checkin | None:
    """Mark the task done with the answers given.

    Writes the transcript as a ``Checkin`` (when there is anything to say),
    one ``AdherenceRecord`` for today, and an in-app alert for the care team
    when an answer is one they would want to see today. Idempotent guard: a
    task completes once; a second completion is a ValueError the caller
    turns into 409.
    """
    if closed_for_now(task):
        raise ValueError(
            "This task was already completed today" if is_recurring(task)
            else "This task was already completed"
        )
    if not task.active:
        raise ValueError("This task is no longer part of the plan")
    if via not in COMPLETION_CHANNELS:
        raise ValueError(f"Unknown completion channel {via}")
    answers = {k: v for k, v in (answers or {}).items() if v is not None and v != ""}
    pairs = transcript(question_set_key(task), answers)
    if not pairs and task.kind == "checkin":
        raise ValueError("No answers given")

    patient = db.get(Patient, task.patient_id)
    now = datetime.now()
    checkin: Checkin | None = None
    if pairs:
        checkin = Checkin(
            patient_id=task.patient_id,
            occurred_at=now,
            channel=via if via in ("app", "sms", "voice") else "app",
        )
        db.add(checkin)
        db.flush()
        seq = 0
        for prompt, text in pairs:
            db.add(CheckinMessage(checkin_id=checkin.id, seq=seq, who="copilot", text=prompt))
            db.add(CheckinMessage(checkin_id=checkin.id, seq=seq + 1, who="patient", text=text))
            seq += 2

    today = date.today()
    task.status = "done"
    task.completed_at = now
    task.completed_via = via
    task.result = {"answers": answers, "checkin_id": checkin.id if checkin else None}
    payload = dict(task.payload or {})
    payload.pop("sms", None)
    # The day the patient answered. A recurring task reads this to know it is
    # owed again tomorrow; a one-shot task is simply done.
    payload["last_done"] = today.isoformat()
    task.payload = payload
    record = db.scalar(
        select(AdherenceRecord).where(
            AdherenceRecord.task_id == task.id, AdherenceRecord.date == today
        )
    )
    status = _adherence_status(task.kind, answers)
    if record is None:
        db.add(
            AdherenceRecord(
                patient_id=task.patient_id, task_id=task.id, date=today, status=status
            )
        )
    else:
        record.status = status

    if patient is not None:
        for alert in _alerts(answers):
            notify_care_team(
                db, patient, f"{patient.name} — {alert}",
                f"From today's {KIND_LABELS.get(task.kind, 'task').lower()} ({via}).",
                "patient_report",
            )
    db.commit()
    return checkin


def skip_task(db: Session, task: AdherenceTask, via: str) -> None:
    if closed_for_now(task):
        raise ValueError(
            "This task was already answered today" if is_recurring(task)
            else "This task was already completed"
        )
    today = date.today()
    task.status = "skipped"
    task.completed_at = datetime.now()
    task.completed_via = via
    payload = dict(task.payload or {})
    payload.pop("sms", None)
    payload["last_done"] = today.isoformat()
    task.payload = payload
    if db.scalar(
        select(AdherenceRecord).where(
            AdherenceRecord.task_id == task.id, AdherenceRecord.date == today
        )
    ) is None:
        db.add(
            AdherenceRecord(
                patient_id=task.patient_id, task_id=task.id, date=today,
                status=AdherenceStatus.MISSED,
            )
        )
    db.commit()


# --- the SMS conversation ----------------------------------------------------------

# Only words that can mean nothing but "walk me through the task you texted".
# "yes", "ok" and "y" used to live here, which meant a patient answering their
# nurse's question with "yes" got a task questionnaire instead of a reply, and
# the nurse never saw the answer. Anything else goes to the copilot, which
# passes it to the care team.
# How long the model may take to answer an inbound text. The whole
# webhook runs inside the database write lock (app/aws/middleware.py),
# whose TTL is 25 s, and that budget also covers downloading the
# database at the start and uploading it at the end. The provider's own
# default bound plus one in-flight attempt lands close enough to the TTL
# to risk the lock being broken mid-request, so this path asks for less
# and takes the deterministic reply when the model cannot make it.
SMS_REPLY_DEADLINE_S = 7.0

START_WORDS = {"1", "start", "begin", "ready"}
APP_WORDS = {"2", "app", "link", "open"}
SKIP_WORDS = {"skip", "-", "n/a", "na", "pass", "next"}
STOP_WORDS = {"stop", "cancel", "quit", "later"}


@dataclass(frozen=True)
class InboundOutcome:
    patient_id: str | None
    handled: bool
    reply: str | None
    kind: str  # conversation_step | task_started | task_completed | task_cancelled |
    # link_sent | no_tasks | message | unknown_number | empty
    delivery: sendblue.CheckinSendResult | None = None


def _active_conversation(tasks: list[AdherenceTask]) -> AdherenceTask | None:
    for t in tasks:
        sms = (t.payload or {}).get("sms")
        if isinstance(sms, dict) and "step" in sms:
            return t
    return None


def _texted_task(tasks: list[AdherenceTask]) -> AdherenceTask | None:
    """The task a "1" is answering: the one texted most recently, since that
    is the text in front of the patient. Falls back to the newest open task."""
    if not tasks:
        return None
    sent = [t for t in tasks if t.sent_at is not None]
    if sent:
        return max(sent, key=lambda t: (t.sent_at, t.id))
    return max(tasks, key=lambda t: t.id)


def _prompt(task: AdherenceTask, step: int, lead: str = "") -> str:
    qs = questions_for(task)
    q = qs[step]
    return f"{lead}{q['prompt']} {answer_hint(q)}".strip()


def start_conversation(task: AdherenceTask) -> str:
    payload = dict(task.payload or {})
    payload["sms"] = {"step": 0, "answers": {}, "started_at": datetime.now().isoformat()}
    task.payload = payload
    n = len(questions_for(task))
    lead = f"{task.title} — {n} quick question{'s' if n != 1 else ''}. "
    return _prompt(task, 0, lead)


def advance_conversation(db: Session, task: AdherenceTask, body: str) -> tuple[str, str]:
    """Consume one texted answer. Returns (reply, outcome kind)."""
    payload = dict(task.payload or {})
    sms = dict(payload.get("sms") or {"step": 0, "answers": {}})
    qs = questions_for(task)
    step = int(sms.get("step", 0))
    answers = dict(sms.get("answers") or {})
    lowered = body.strip().lower()

    if lowered in STOP_WORDS:
        payload.pop("sms", None)
        task.payload = payload
        return "No problem — I'll leave it for now. Reply 1 whenever you want to pick it up.", "task_cancelled"

    if lowered not in SKIP_WORDS:
        value = parse_free_answer(qs[step], body)
        if value is None:
            return f"Sorry, I didn't catch that. {qs[step]['prompt']} {answer_hint(qs[step])}", "conversation_step"
        answers[qs[step]["id"]] = value
    step += 1

    if step >= len(qs):
        payload.pop("sms", None)
        task.payload = payload
        try:
            complete_task(db, task, answers, via="sms")
        except ValueError as e:
            return f"I couldn't record that: {e}. Reply 1 to start over.", "conversation_step"
        return "Thanks — that's all sent to your care team. Reply anytime if something changes.", "task_completed"

    sms.update(step=step, answers=answers)
    payload["sms"] = sms
    task.payload = payload
    return _prompt(task, step), "conversation_step"


def patient_for_phone(db: Session, phone: str) -> Patient | None:
    """The chart a number belongs to. Numbers are meant to be unique, but a
    roster can carry the same one twice (a clinician typed it on a chart the
    patient later signed up beside). Then the record that is actually using
    the app wins, and after that the newest."""
    from app.models.mobile import PatientSession

    rows = db.scalars(select(Patient).where(Patient.phone == phone)).all()
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    def last_seen(p: Patient) -> datetime:
        seen = db.scalar(
            select(PatientSession.last_seen_at)
            .where(PatientSession.patient_id == p.id, PatientSession.revoked_at.is_(None))
            .order_by(PatientSession.last_seen_at.desc())
            .limit(1)
        )
        return seen or datetime.min

    return max(rows, key=lambda p: (last_seen(p), p.created_at or datetime.min))


def handle_inbound_sms(
    db: Session, from_phone: str, text: str, *, base_url: str = "",
    message_handle: str | None = None,
) -> InboundOutcome:
    """Everything an inbound Sendblue text can mean, in one place.

    Order: a patient mid-conversation is answering the current question;
    "1" (or a start word) begins the most recent open task by text; "2"
    asks for the app link; anything else is a message for the care team,
    answered by the patient copilot. The reply is texted back and both
    lines land on the message thread so the console sees the exchange.
    """
    phone = sendblue.normalize_phone(from_phone)
    if phone is None:
        return InboundOutcome(None, False, None, "unknown_number")
    patient = patient_for_phone(db, phone)
    if patient is None:
        logger.info("Inbound text from a number no patient has on file")
        return InboundOutcome(None, False, None, "unknown_number")
    body = (text or "").strip()
    if not body:
        return InboundOutcome(patient.id, False, None, "empty")
    # Sendblue retries a delivery it did not get a 2xx for. The same text
    # processed twice would answer a conversation question twice, so the
    # message handle is the dedupe key when the payload carries one.
    if message_handle and db.scalar(
        select(Message.id).where(
            Message.sender == "patient", Message.external_handle == message_handle
        ).limit(1)
    ) is not None:
        return InboundOutcome(patient.id, False, None, "duplicate")

    db.add(Message(patient_id=patient.id, sender="patient", channel="sms", text=body[:2000],
                   external_handle=message_handle))
    db.flush()

    tasks = open_tasks(db, patient.id)
    active = _active_conversation(tasks)
    lowered = body.lower()
    if active is not None:
        reply, kind = advance_conversation(db, active, body)
    elif lowered in START_WORDS:
        task = _texted_task(tasks)
        if task is None:
            reply, kind = "You're all caught up — nothing is waiting right now.", "no_tasks"
        else:
            reply, kind = start_conversation(task), "task_started"
    elif lowered in APP_WORDS:
        task = _texted_task(tasks)
        if task is None:
            reply, kind = "Nothing is waiting right now. Open the MedPull app anytime to see your plan.", "no_tasks"
        else:
            token = mint_token(task)
            url = task_url(base_url, token) if base_url else deep_link(task)
            reply, kind = f"Here you go: {url}", "link_sent"
    else:
        from app.agent.copilot import respond

        # The thread lines are written here (with the delivery status), so the
        # copilot records neither the patient's line nor its own reply.
        result = respond(db, patient, body, channel="sms", record_patient_line=False,
                         record_reply=False, default_to_care_team=True,
                         deadline_s=SMS_REPLY_DEADLINE_S)
        reply, kind = result["reply"], "message"

    # The copilot answering a text speaks for itself: no clinician tag, and
    # no name — compose strips one the model may have reached for.
    reply = sendblue.compose(reply, patient_name=patient.name)

    # A text cannot be unsent, and this reply only makes sense if the rows
    # behind it survive. The whole handler runs under the database write
    # lock; if that lock has been taken over, the persist after this request
    # will refuse and everything here is discarded — including the dedupe
    # row — so sending now would text the patient and then answer them a
    # second time when the provider retries. Better to send nothing: the
    # retry finds no record and runs the exchange cleanly.
    from app.aws import storage

    if not storage.holds_lock(unknown_as_held=True):
        logger.warning(
            "Not replying to %s: the database write lock was taken over, so this "
            "exchange will be discarded and retried", patient.id,
        )
        return InboundOutcome(patient.id, False, None, "lock_lost")

    delivery = sendblue.send_sms(phone, reply)
    db.add(
        Message(
            patient_id=patient.id,
            sender="copilot",
            channel="sms",
            text=reply,
            authored_by="ai",
            delivery_status="sent" if delivery.sent else "failed",
            delivery_detail=None if delivery.sent else delivery.detail,
            external_handle=delivery.message_handle,
        )
    )
    db.commit()
    return InboundOutcome(patient.id, True, reply, kind, delivery)
