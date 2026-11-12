"""The showcase: one roster of fictional people across the three versions
of the product, and the one fill that keeps all of them current.

The demo console switches between Clinic, Personal and Sports, and the demo
iPhone app signs in as any of these people without an account. Both read
the same registry here, so a persona the console shows is one the phone can
become.

* ``REGISTRY`` — who exists, by version and org. Clinic personas come from
  the clinic fill's roster (``demo_fill.build_roster``) and athletes from
  the sports seed's (``app.sports.seed.ROSTER``), so a person added to
  either is on the list without being typed again. Personal members are
  not in it: they are whoever ``app.personal.showcase.members`` returns for
  the database in hand.
* ``personas`` — the registry and the members intersected with the rows
  that exist, in the shape ``GET /api/demo/personas`` returns.
* ``resolve`` — the persona and its row for an id, or None: the only ids
  the demo routes will sign a phone in as.
* ``fill_showcase`` — (re)anchor every demo org to today: the clinic
  personas and the H.I.R.T. lifters (``demo_fill.fill``), the sports
  rosters (``app/sports/seed.py``) and the Personal members
  (``app/personal/showcase.py``). Idempotent; refuses off the demo stack.
* ``reset_day`` — put one clinic persona's exercise day back the way the
  fill left it, so a walkthrough can be run again.

    DEMO_MODE=true uv run python -m app.seed.seed --reset

builds a complete showcase database from nothing (the seed ends with
``fill_showcase`` on a demo stack); ``scripts/push_demo_fill.py`` and the
Lambda action ``showcase_fill`` run the fill against a deployed one.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import ProcedureType
from app.models.patient import Patient
from app.models.showcase import ShowcaseState
from app.personal import showcase as personal_showcase
from app.personal.scope import CLINIC, PERSONAL, SPORTS, is_clinic
from app.seed import demo_fill, hirt

logger = logging.getLogger(__name__)

VERSIONS = ("clinic", "personal", "sports")
VERSION_LABELS = {"clinic": "Clinic", "personal": "Personal", "sports": "Sports"}
VERSION_BLURBS = {
    "clinic": "Followed by a clinic between visits",
    "personal": "A member reading their own body",
    "sports": "An athlete on a team's board",
}
PERSONAL_ORG = ("personal", "MedPull Personal")
# The two athletes the sports seed leaves on no team. Listed under an org of
# their own so the phone can become them; it is not a team and has no board.
INDEPENDENT_ORG = ("independent", "Independent athletes")

# The one to open first in each org. An org none of these is in (a team the
# sports seed adds later, the Personal members) leads with its first row.
HEROES = frozenset({
    "hirt-cole", "dana", "linda", "robert", "sofia", "james",
    "jalen-okoro", "camila-ortega", "sloane-whitaker",
})
# H.I.R.T. is the pilot the showcase is built round, so it leads the clinic list.
CLINIC_ORG_ORDER = (hirt.HOSPITAL_ID, demo_fill.DEMO_HOSPITAL)

# What each scenario of the sports seed reads as today, in a few words.
SPORTS_STORIES = {
    "star": "Starter, sleeping well, steady all month",
    "healthy": "Steady",
    "sleep_debt": "Short nights for ten days, recovery down",
    "load_spike": "Training load jumped this week",
    "acl": "ACL rehab: running and jumping, no contact yet",
    "ankle": "Right ankle sprain, day nine: modified",
    "tendon": "Left patellar tendon: jump load managed",
    "hamstring": "Hamstring strain: back to sprinting, not yet full speed",
    "unwell": "Running a temperature, resting heart rate up",
    "fresh": "Fresh after a light week",
    "freshman": "First year on the roster",
    "taper": "Tapering into the opener",
    "tennis_solo": "Serving shoulder: no serving for two weeks",
    "soccer_solo": "Hamstring strain, back to sprinting",
}

# The key the day of the last fill is stored under (``showcase_state``).
FILLED_ON = "filled_on"


@dataclass(frozen=True)
class Persona:
    """One fictional person the showcase can show and the phone can become."""

    id: str
    name: str
    version: str  # clinic | personal | sports
    org_id: str  # hospital id, "personal", or the team id
    org_name: str
    tagline: str  # one line under the name: the program, the goal, the position
    detail: str = ""  # what today's story is ("Load spike, pain rising")
    hero: bool = False  # the one to open first in its org


def _clinic_personas() -> list[Persona]:
    """Every chart the clinic fill authors, H.I.R.T. first."""
    from app.seed.patients import HOSPITALS, ORTHO_DEMO_HOSPITALS

    names = {h.id: h.name for h in (*HOSPITALS, *ORTHO_DEMO_HOSPITALS)}
    legacy, demo, lifters = demo_fill.build_roster()
    order = {org: i for i, org in enumerate(CLINIC_ORG_ORDER)}
    out = []
    for p in (*lifters, *demo, *legacy):
        spec = p.spec
        # A lifter's and a general-care chart's display line is the whole
        # story; a surgical one reads better with the day beside it.
        tagline = (spec.procedure_display if spec.procedure == ProcedureType.NONE
                   else f"{spec.procedure_display} · day {spec.postop_day}")
        out.append(Persona(
            id=spec.id, name=spec.name, version="clinic", org_id=spec.hospital_id,
            org_name=names[spec.hospital_id], tagline=tagline, detail=p.story,
            hero=spec.id in HEROES,
        ))
    return sorted(out, key=lambda p: order.get(p.org_id, len(order)))


def _sports_personas() -> list[Persona]:
    """Every athlete the sports seed writes, by team."""
    from app.sports import seed as sports

    teams = {t["id"]: t for t in sports.TEAMS}
    orgs = {o["id"]: o for o in sports.ORGS}
    out = []
    for spec in sports.ROSTER:
        if spec.team_id is not None:
            team = teams[spec.team_id]
            org_id, org_name = team["id"], f"{orgs[team['org_id']]['short_name']} · {team['name']}"
            parts = [spec.position, f"#{spec.jersey}" if spec.jersey else None, spec.class_year]
        else:
            org_id, org_name = INDEPENDENT_ORG
            parts = [spec.sport.capitalize(), spec.position]
        out.append(Persona(
            id=spec.id, name=spec.name, version="sports", org_id=org_id, org_name=org_name,
            tagline=" · ".join(part for part in parts if part),
            detail=SPORTS_STORIES.get(spec.scenario, ""), hero=spec.id in HEROES,
        ))
    return out


REGISTRY: tuple[Persona, ...] = (*_clinic_personas(), *_sports_personas())


def persona(persona_id: str) -> Persona | None:
    """The registry entry for an id, or None. A Personal member is not in
    the registry (members are whoever the database holds): use ``resolve``
    to answer for any id the demo routes accept."""
    return next((p for p in REGISTRY if p.id == persona_id), None)


def _kind(patient: Patient) -> str:
    """The version a row belongs to."""
    kind = patient.account_kind or CLINIC
    return kind if kind in (PERSONAL, SPORTS) else CLINIC


def _member_personas(db: Session) -> list[tuple[Persona, Patient]]:
    """The demo members of MedPull Personal in this database, each as a
    persona: the goal they joined with as the line under the name."""
    from app.models.personal import GOAL_LABELS, PersonalProfile

    members = personal_showcase.members(db)
    if not members:
        return []
    profiles = {
        p.patient_id: p for p in db.scalars(
            select(PersonalProfile).where(PersonalProfile.patient_id.in_([m.id for m in members]))
        )
    }
    out = []
    for row in members:
        profile = profiles.get(row.id)
        goal = GOAL_LABELS.get(profile.goal, profile.goal) if profile else ""
        sport = (profile.sport or "").strip() if profile else ""
        out.append((Persona(
            id=row.id, name=row.name, version="personal", org_id=PERSONAL_ORG[0],
            org_name=PERSONAL_ORG[1], tagline=" · ".join(part for part in (goal, sport) if part),
            detail=(profile.injury or "") if profile else "",
        ), row))
    return out


def _listed(db: Session) -> list[tuple[Persona, Patient]]:
    """Every persona that exists in this database, with its row: registry
    entries whose row is there and of the entry's kind, then the members."""
    rows = {
        row.id: row for row in db.scalars(
            select(Patient).where(Patient.id.in_([p.id for p in REGISTRY]))
        )
    }
    listed = [(p, rows[p.id]) for p in REGISTRY if p.id in rows and _kind(rows[p.id]) == p.version]
    return listed + _member_personas(db)


def resolve(db: Session, persona_id: str) -> tuple[Persona, Patient] | None:
    """The persona and its row for an id the showcase knows — a registry id
    whose row exists, or a demo member — or None. Nothing else can be signed
    into from the demo routes: not a real chart, not a real subscriber."""
    row = db.get(Patient, persona_id)
    if row is None:
        return None
    entry = persona(persona_id)
    if entry is not None:
        return (entry, row) if _kind(row) == entry.version else None
    if personal_showcase.is_showcase(db, row):
        return next(((p, r) for p, r in _member_personas(db) if r.id == row.id), None)
    return None


def _latest_tiers(db: Session, patient_ids: list[str]) -> dict[str, str]:
    """The risk tier on each chart's latest stored assessment. Read as
    stored: nothing is computed here, so a chart never scored has none."""
    from app.models.insight import RiskAssessment

    rows = db.execute(
        select(RiskAssessment.patient_id, RiskAssessment.risk_level)
        .where(RiskAssessment.patient_id.in_(patient_ids))
        .order_by(RiskAssessment.computed_at, RiskAssessment.id)
    )
    return {patient_id: str(level) for patient_id, level in rows}


def _having(db: Session, column, patient_ids: list[str]) -> set[str]:
    """Which of ``patient_ids`` have at least one row in the column's table."""
    return set(db.scalars(select(column).where(column.in_(patient_ids)).distinct()))


def sms_view() -> dict:
    """The line the demo texts from and the words that open it, for the
    phone's "text us first" step."""
    from app.notifications import sendblue

    return {
        "number": settings.sendblue_from_number or None,
        "text_body": settings.sendblue_text_first_body,
        "configured": sendblue.configured(),
    }


def personas(db: Session) -> dict:
    """The persona list by version and org, for ``GET /api/demo/personas``.
    Only rows that exist are listed, and a version with nobody in it is left
    out. Reads only: the tier is the stored one and the ``has`` marks are
    existence queries."""
    from app.hep.models import ExerciseAssignment
    from app.models.hospital import Hospital
    from app.models.mobile import Message
    from app.models.patient import Device

    listed = _listed(db)
    ids = [row.id for _, row in listed]
    # A member paired with a chart reads the chart's wearable stream.
    stream = {row.id: row.observations_from or row.id for _, row in listed}
    tiers = _latest_tiers(db, [row.id for entry, row in listed if entry.version == "clinic"])
    wearable = _having(db, Device.patient_id, sorted(set(stream.values())))
    exercises = _having(db, ExerciseAssignment.patient_id, ids)
    thread = _having(db, Message.patient_id, ids)
    hospitals = dict(db.execute(select(Hospital.id, Hospital.name)).all())

    orgs: dict[tuple[str, str], dict] = {}
    for entry, row in listed:
        org = orgs.setdefault((entry.version, entry.org_id), {
            "id": entry.org_id,
            "name": hospitals.get(entry.org_id, entry.org_name) if entry.version == "clinic"
            else entry.org_name,
            "personas": [],
        })
        org["personas"].append({
            "id": row.id,
            "name": row.name,
            "hero": entry.hero,
            "tagline": entry.tagline,
            "detail": entry.detail,
            "account_kind": _kind(row),
            # The risk tier is the clinic's read; a member and an athlete have none.
            "tier": tiers.get(row.id),
            "has": {
                "wearable": stream[row.id] in wearable,
                "exercises": row.id in exercises,
                "thread": row.id in thread,
            },
        })
    for org in orgs.values():
        # One hero per org, first in its list.
        if not any(p["hero"] for p in org["personas"]):
            org["personas"][0]["hero"] = True
        org["personas"].sort(key=lambda p: not p["hero"])
    versions = []
    for key in VERSIONS:
        version_orgs = [org for (version, _), org in orgs.items() if version == key]
        if version_orgs:
            versions.append({"key": key, "label": VERSION_LABELS[key],
                             "blurb": VERSION_BLURBS[key], "orgs": version_orgs})
    return {"as_of": date.today().isoformat(), "sms": sms_view(), "versions": versions}


# --- the fill ------------------------------------------------------------------------


class ShowcaseRefused(RuntimeError):
    """``fill_showcase`` was asked to run on a deployment that is not the demo."""


def refusal(force: bool = False) -> str | None:
    """Why the fill may not run on this deployment, or None when it may.
    The fictional rosters never belong on the real app, so anything but the
    demo stack has to be asked for twice."""
    if settings.demo_mode or force:
        return None
    return (
        "refusing to fill the showcase: this deployment is not in demo mode "
        "(DEMO_MODE is off). The fictional rosters are for the demo stack; pass "
        "force to fill this database anyway."
    )


def filled_on(bind) -> str | None:
    """The day the showcase was last filled (ISO), or None when it never
    was. ``bind`` is a Session or a Connection; this only reads."""
    return bind.execute(
        select(ShowcaseState.value).where(ShowcaseState.key == FILLED_ON)
    ).scalar()


def _stamp(db: Session, today: date) -> None:
    row = db.get(ShowcaseState, FILLED_ON)
    if row is None:
        row = ShowcaseState(key=FILLED_ON)
        db.add(row)
    row.value = today.isoformat()
    row.updated_at = datetime.now()


@dataclass
class _Held:
    """What a presenter left on the personas, taken before a refill and put
    back after it: bound phone numbers by persona id, and app sessions as
    column values."""

    phones: dict[str, str] = field(default_factory=dict)
    sessions: list[dict] = field(default_factory=list)


def _hold(db: Session) -> _Held:
    """The app sessions and the bound (non-placeholder) phone numbers of
    every persona in the database. The clinic fill keeps both by itself; the
    sports seed deletes each athlete and writes them again, which would sign
    a phone out and drop its number, so the fill takes them first and
    ``_restore`` puts back whatever is missing afterwards."""
    from app.models.mobile import PatientSession

    ids = [row.id for _, row in _listed(db)]
    held = _Held()
    for patient_id, phone in db.execute(
        select(Patient.id, Patient.phone).where(Patient.id.in_(ids), Patient.phone.is_not(None))
    ):
        if not demo_fill.is_placeholder_phone(phone):
            held.phones[patient_id] = phone
    columns = [c.name for c in PatientSession.__table__.columns if c.name != "id"]
    for session in db.scalars(select(PatientSession).where(PatientSession.patient_id.in_(ids))):
        held.sessions.append({name: getattr(session, name) for name in columns})
    return held


def _restore(db: Session, held: _Held) -> dict[str, int]:
    """Put back the sessions and phone numbers a refill removed. A session
    still there is left alone, and a number another chart has taken since is
    not given to two (one number, one chart: an inbound text must land on
    one thread). Returns how many of each were put back."""
    from app.models.mobile import PatientSession

    owners = sorted({s["patient_id"] for s in held.sessions})
    present = set(db.scalars(
        select(PatientSession.token_hash).where(PatientSession.patient_id.in_(owners))
    ))
    alive = set(db.scalars(select(Patient.id).where(Patient.id.in_(owners))))
    sessions = 0
    for values in held.sessions:
        if values["token_hash"] in present or values["patient_id"] not in alive:
            continue
        db.add(PatientSession(**values))
        sessions += 1
    phones = 0
    for patient_id, phone in held.phones.items():
        patient = db.get(Patient, patient_id)
        if patient is None or patient.phone == phone:
            continue
        taken = db.scalar(select(Patient.id).where(Patient.phone == phone, Patient.id != patient_id))
        if taken is not None:
            continue
        patient.phone = phone
        phones += 1
    db.commit()
    return {"sessions": sessions, "phones": phones}


def ensure_consents(db: Session) -> int:
    """The beta consent on file for every persona of every version, so no
    app opened as one of them lands on the consent screen. Returns rows added."""
    added = sum(
        hirt.ensure_consent(db, row.id, device_name="demo persona") for _, row in _listed(db)
    )
    db.commit()
    return added


def fill_showcase(
    db: Session,
    today: date | None = None,
    *,
    force: bool = False,
    suppress_phones: bool = False,
    warm: bool = False,
    pause: float = 2.0,
    say: Callable[[str], None] = logger.info,
) -> dict:
    """Bring every demo org up to ``today``: the clinic personas and the
    H.I.R.T. lifters, the sports rosters, the Personal members. Raises
    ``ShowcaseRefused`` unless this is the demo stack (``DEMO_MODE``) or
    ``force`` is given: the fictional rosters never belong on the real app.

    Idempotent: a second run on the same day leaves the same rows. Across a
    run every persona keeps its app sessions and any phone number that is
    not a 555 placeholder. ``suppress_phones``, ``warm`` and ``pause`` are
    the clinic fill's (``demo_fill.fill``); ``say`` receives progress lines.

    Returns ``{"filled_on", "personas", "clinic": {...}, "sports": {...},
    "personal": [...member ids], "kept": {"sessions", "phones"},
    "consents"}``, where ``personas`` counts everyone the showcase now lists.
    """
    refused = refusal(force)
    if refused is not None:
        raise ShowcaseRefused(refused)
    from app.sports.seed import seed_sports

    today = today or date.today()
    held = _hold(db)
    clinic = demo_fill.fill(db, today, suppress_phones=suppress_phones, warm=warm, pause=pause,
                            say=say)
    sports = seed_sports(db, today)
    say(f"sports: {sports}")
    members = list(personal_showcase.seed_personal(db, today))
    say(f"personal: {len(members)} member(s)")
    kept = _restore(db, held)
    consents = ensure_consents(db)
    _stamp(db, today)
    db.commit()
    listed = len(_listed(db))
    say(f"showcase filled for {today.isoformat()}: {listed} persona(s)")
    return {
        "filled_on": today.isoformat(),
        "personas": listed,
        "clinic": clinic,
        "sports": sports,
        "personal": members,
        "kept": kept,
        "consents": consents,
    }


# --- putting a day back ---------------------------------------------------------------

# Everything a session, a completion, a skip and a review leave on an
# exercise row. Cleared, the row is as the therapist laid it out.
_OUTCOME_FIELDS = (
    "started_at", "ended_at", "duration_s", "pain_before", "wearable_worn", "hr_avg", "hr_max",
    "completed_at", "pain_after", "effort", "sets_done", "reps_done", "load_done_kg", "note",
    "completion_source", "video_attachment_id", "skip_reason",
)
_REVIEW_FIELDS = ("reviewed_at", "reviewed_by", "review_note")


def reset_day(db: Session, patient: Patient, today: date | None = None) -> dict[str, int]:
    """Put a clinic persona's exercise day back so a walkthrough can be run
    again. Anything other than a clinic chart is left alone and reports zeros.

    An exercise row that was started, done or skipped today goes back to
    ``assigned`` with its session, completion and review cleared and its
    return clip taken off (today's rows, and an earlier day's caught up on
    today); a row done before today and only reviewed today loses the review
    and stays done. The thread loses the lines that work wrote today: the
    "Did …" line of each completion, the therapist's "About your …" note of
    each review, and any text that carried a link to one of those rows. The
    care team's bell loses the notices those lines raised. A clip stays in
    storage as a file on no line. Nothing the fill wrote is touched: its
    rows for today are open, and its done days and reviews are dated earlier.

    Returns ``{"reopened": rows back to assigned, "removed": thread lines
    removed}``.
    """
    from app.hep.models import Exercise, ExerciseAssignment
    from app.models.attachment import Attachment
    from app.models.links import AppLink
    from app.models.mobile import Message
    from app.models.notification import Notification

    if not is_clinic(patient):
        return {"reopened": 0, "removed": 0}
    today = today or date.today()
    midnight = datetime.combine(today, time.min)
    rows = db.scalars(
        select(ExerciseAssignment).where(
            ExerciseAssignment.patient_id == patient.id,
            or_(
                ExerciseAssignment.scheduled_for == today,
                ExerciseAssignment.started_at >= midnight,
                ExerciseAssignment.completed_at >= midnight,
                ExerciseAssignment.reviewed_at >= midnight,
                (ExerciseAssignment.status == "skipped") & (ExerciseAssignment.updated_at >= midnight),
            ),
        )
    ).all()
    titles = dict(db.execute(
        select(Exercise.id, Exercise.title).where(Exercise.id.in_({r.exercise_id for r in rows}))
    ).all())
    todays = db.scalars(
        select(Message).where(Message.patient_id == patient.id, Message.created_at >= midnight)
    ).all()

    now = datetime.now()
    reopened = 0
    doomed: dict[int, Message] = {}
    undone: list[int] = []
    for row in rows:
        title = titles.get(row.exercise_id, "the exercise")
        reviewed_today = row.reviewed_at is not None and row.reviewed_at >= midnight
        review_only = (
            row.scheduled_for != today and row.status == "done"
            and row.completed_at is not None and row.completed_at < midnight
        )
        untouched = (
            row.status == "assigned" and row.started_at is None and row.reviewed_at is None
        )
        if untouched or (review_only and not reviewed_today):
            continue
        undone.append(row.id)
        if reviewed_today:
            for message in todays:
                if message.sender == "care_team" and message.text.startswith(f"About your {title}"):
                    doomed[message.id] = message
        for name in _REVIEW_FIELDS:
            setattr(row, name, None)
        row.updated_at = now
        if review_only:
            continue
        for message in todays:
            if message.sender == "patient" and message.text.startswith(f"Did {title}"):
                doomed[message.id] = message
        if row.video_attachment_id is not None:
            clip = db.get(Attachment, row.video_attachment_id)
            if clip is not None and clip.message_id is not None:
                line = db.get(Message, clip.message_id)
                if line is not None:
                    doomed[line.id] = line
        for name in _OUTCOME_FIELDS:
            setattr(row, name, None)
        row.status = "assigned"
        reopened += 1

    if undone:
        # A text about one of these rows (the therapist replied, a clip is
        # still needed) carried a link to it; the line goes with the rest.
        linked = db.scalars(
            select(AppLink.message_id).where(
                AppLink.patient_id == patient.id, AppLink.kind == "exercise",
                AppLink.ref_id.in_([str(i) for i in undone]),
                AppLink.created_at >= midnight, AppLink.message_id.is_not(None),
            )
        ).all()
        for message in todays:
            if message.id in linked:
                doomed[message.id] = message

    if doomed:
        ids = list(doomed)
        for clip in db.scalars(select(Attachment).where(Attachment.message_id.in_(ids))):
            clip.message_id = None
        bodies = {m.text[:400] for m in doomed.values() if m.sender == "patient"}
        if bodies:
            db.execute(delete(Notification).where(
                Notification.patient_id == patient.id, Notification.kind == "patient_message",
                Notification.created_at >= midnight, Notification.body.in_(bodies),
            ))
        db.execute(delete(Message).where(Message.id.in_(ids)))
    db.commit()
    return {"reopened": reopened, "removed": len(doomed)}
