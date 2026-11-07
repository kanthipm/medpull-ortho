"""H.I.R.T. Physical Therapy — the lifter demo org.

One PT clinic as one org of the clinic facet: the Harris Institute for
Rehabilitative Therapies, a cash-pay practice inside Rise Gym in Tomball,
Texas, whose patients are lifters who train in a 24/7 gym between hour-long
one-on-one visits. The gap the demo tests is the time between visits: a
lifter overloads a tendon too fast, or quietly stops coming, and the clinic
finds out at the next visit or never.

Nothing here has a wearable. Every number comes from the daily text check-in
(tasks/service.LIFTER_CHECKIN_QUESTIONS): pain, anything new since the
visit, the night, whether today's program got done, and how hard and how
long the training was. The history is fourteen days anchored to today, one
evening check-in per day, shaped so the morning shortlist reads the way the
experiment was pitched:

* Cole Whitaker — patellar tendinopathy, progressive loading. Two light
  weeks as prescribed, then this week he went back to his old leg day: six
  sessions at RPE 8-9, load 1.6x its recent average, pain 3 → 6. HIGH.
* Rafael Quintero — came in through a free 20-minute shoulder screen,
  started the program, then a new job: no check-in for three days. MEDIUM,
  went quiet.
* Devon Castellanos — low back, return to lifting. Still lifting, but the
  back program itself slipped: done on under half of the last three days.
  MEDIUM.
* Tessa Marlowe — Achilles tendinopathy, progressive loading. Load held,
  pain easing, program done every day. LOW.
* June Halvorsen — lumbar disc, return to lifting. Steady. LOW.

Every lifter is fictional. The seed (app/seed/seed.py) and the demo fill
(app/seed/demo_fill.py) both write the history through ``write_history``,
so a scratch database and the deployed one carry the same fourteen days.

Demo orgs: see the module docstring of app/seed/patients.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from app.models.enums import CareRole, ProcedureType
from app.seed.specs import CareTeamSpec, HospitalSpec, PatientSpec

HOSPITAL_ID = "hirt"
TZ = "America/Chicago"
PROGRAM_DAYS = 14
QSET = "checkin_lifter"

HIRT_HOSPITAL = HospitalSpec(
    HOSPITAL_ID, "H.I.R.T. Physical Therapy", "Tomball", "TX", "Rise Gym", TZ,
)
# Both physical therapists. Dr. Harris owns the clinic and evaluates every
# lifter (the surgeon slot, which is what the drafts say "Dr. Harris" with);
# Dr. Gregg is the day-to-day user, so she carries three of the five rows.
HIRT_CARE_TEAM: list[CareTeamSpec] = [
    CareTeamSpec("ct_harris", "Dr. Sean Harris", CareRole.PT),
    CareTeamSpec("ct_gregg", "Dr. Ashley Gregg", CareRole.PT),
]

PATHWAYS = {
    "hirt-cole": "Patellar tendinopathy · progressive loading",
    "hirt-tessa": "Achilles tendinopathy · progressive loading",
    "hirt-devon": "Low back · return to lifting",
    "hirt-june": "Lumbar disc · return to lifting",
    "hirt-rafael": "Free screen · shoulder · program",
}


def _lifter(pid: str, name: str, age: int, sex: str, assigned: str) -> PatientSpec:
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    pathway = PATHWAYS[pid]
    return PatientSpec(
        id=pid, name=name, initials=initials, age=age, sex=sex,
        procedure=ProcedureType.NONE, procedure_display=pathway, postop_day=PROGRAM_DAYS,
        provider=None, device_model="", surgeon_id="ct_harris", discharge_offset=0,
        hospital_id=HOSPITAL_ID, care_pathway=pathway, assigned_id=assigned,
    )


HIRT_PATIENTS: list[PatientSpec] = [
    _lifter("hirt-cole", "Cole Whitaker", 31, "M", "ct_gregg"),
    _lifter("hirt-tessa", "Tessa Marlowe", 29, "F", "ct_gregg"),
    _lifter("hirt-devon", "Devon Castellanos", 42, "M", "ct_harris"),
    _lifter("hirt-june", "June Halvorsen", 48, "F", "ct_harris"),
    _lifter("hirt-rafael", "Rafael Quintero", 24, "M", "ct_gregg"),
]
HIRT_IDS = frozenset(p.id for p in HIRT_PATIENTS)

PHONES = {
    "hirt-cole": "+12815550131", "hirt-tessa": "+12815550132", "hirt-devon": "+12815550133",
    "hirt-june": "+12815550134", "hirt-rafael": "+12815550135",
}
MRNS = {
    "hirt-cole": "RG-0412", "hirt-tessa": "RG-0418", "hirt-devon": "RG-0397",
    "hirt-june": "RG-0403", "hirt-rafael": "RG-0431",
}


@dataclass(frozen=True)
class CheckinDay:
    """One evening's answers to the lifter check-in, ``days_ago`` days back."""

    days_ago: int
    answers: dict[str, Any] = field(default_factory=dict)
    hour: int = 20
    minute: int = 40

    def at(self, today: date) -> datetime:
        return datetime.combine(today - timedelta(days=self.days_ago), time(self.hour, self.minute))


def _day(
    days_ago: int, pain: int, *, program: str = "all", rpe: int | None = None, minutes: int = 0,
    sleep: str = "well", swelling: str = "no", new_pain: str = "no", note: str | None = None,
    hour: int = 20, minute: int = 40,
) -> CheckinDay:
    """A rest day is minutes 0 with no effort asked; a training day carries
    both. The order matches the question set, so the transcript reads in it."""
    answers: dict[str, Any] = {
        "pain": pain, "swelling": swelling, "new_pain": new_pain, "sleep": sleep,
        "program": program,
    }
    if minutes > 0 and rpe is not None:
        answers["rpe"] = rpe
    answers["minutes"] = minutes
    if note:
        answers["note"] = note
    return CheckinDay(days_ago, answers, hour, minute)


def _program_day(d: int) -> int:
    """Program day d (0 = the day they started, fourteen days ago) as days ago."""
    return PROGRAM_DAYS - d


# --- the five histories -----------------------------------------------------------
#
# Each list is program days 0..13 (today is day 14 and its evening check-in
# has not happened yet). Session load is RPE x minutes; the load ratio the
# tier and the M1 tile share is the 7-day mean over the mean from day 2
# (care/load.load_windows), so the first week has to stay light for Cole's
# third week to read 1.6x.

COLE: list[CheckinDay] = [
    _day(_program_day(0), 3, minutes=0, note="First session with Dr. Harris today. Knee's been nagging on stairs for a couple of months."),
    _day(_program_day(1), 3, rpe=5, minutes=45),
    _day(_program_day(2), 2, minutes=0),
    _day(_program_day(3), 3, rpe=5, minutes=50),
    _day(_program_day(4), 3, minutes=0),
    _day(_program_day(5), 2, rpe=5, minutes=45, note="Slow tempo squats feel fine. Boring, but fine."),
    _day(_program_day(6), 3, minutes=0),
    _day(_program_day(7), 3, rpe=5, minutes=50),
    _day(_program_day(8), 3, rpe=7, minutes=65, note="Jumped back in with the guys on leg day."),
    _day(_program_day(9), 4, rpe=8, minutes=70),
    _day(_program_day(10), 4, rpe=8, minutes=75, sleep="rough"),
    _day(_program_day(11), 5, minutes=0, note="Rest day. Knee was stiff all morning."),
    _day(_program_day(12), 5, rpe=9, minutes=75, sleep="rough"),
    _day(_program_day(13), 6, rpe=8, minutes=80, swelling="yes", sleep="rough",
         note="Back on my old leg day all week. Knee's talking on the way down stairs and a bit puffy under the kneecap tonight."),
]

TESSA: list[CheckinDay] = [
    _day(_program_day(0), 5, rpe=5, minutes=45, note="Heel's stiff first thing, loosens after the warm-up."),
    _day(_program_day(1), 5, minutes=0),
    _day(_program_day(2), 4, rpe=6, minutes=45),
    _day(_program_day(3), 4, minutes=0),
    _day(_program_day(4), 4, rpe=5, minutes=50),
    _day(_program_day(5), 4, minutes=0),
    _day(_program_day(6), 3, rpe=6, minutes=40),
    _day(_program_day(7), 3, rpe=6, minutes=45, note="Calf raises up to the full set without the pinch."),
    _day(_program_day(8), 3, minutes=0),
    _day(_program_day(9), 3, rpe=5, minutes=50),
    _day(_program_day(10), 2, minutes=0),
    _day(_program_day(11), 3, rpe=6, minutes=45),
    _day(_program_day(12), 2, minutes=0),
    _day(_program_day(13), 2, rpe=6, minutes=50, note="Best week yet. Morning stiffness is nearly gone."),
]

DEVON: list[CheckinDay] = [
    _day(_program_day(0), 4, rpe=6, minutes=50, note="Deadlifts are back at 60 percent. Back feels okay."),
    _day(_program_day(1), 4, minutes=0),
    _day(_program_day(2), 3, rpe=6, minutes=50, program="some"),
    _day(_program_day(3), 4, minutes=0),
    _day(_program_day(4), 4, rpe=6, minutes=55),
    _day(_program_day(5), 3, minutes=0),
    _day(_program_day(6), 4, rpe=6, minutes=50, program="some"),
    _day(_program_day(7), 4, rpe=6, minutes=50),
    _day(_program_day(8), 5, minutes=0, sleep="rough"),
    _day(_program_day(9), 4, rpe=6, minutes=50, program="some"),
    _day(_program_day(10), 4, minutes=0, program="some"),
    _day(_program_day(11), 5, rpe=6, minutes=55, program="none", note="Work's been brutal this week."),
    _day(_program_day(12), 4, minutes=0, program="some", sleep="rough"),
    _day(_program_day(13), 4, rpe=6, minutes=50, program="none",
         note="Lifted, but haven't had time for the back work in days."),
]

JUNE: list[CheckinDay] = [
    _day(_program_day(0), 4, rpe=4, minutes=40, note="Nervous about loading the back again, but it went fine."),
    _day(_program_day(1), 4, minutes=0),
    _day(_program_day(2), 4, rpe=4, minutes=40),
    _day(_program_day(3), 3, minutes=0),
    _day(_program_day(4), 3, rpe=5, minutes=40),
    _day(_program_day(5), 3, minutes=0),
    _day(_program_day(6), 3, rpe=5, minutes=40),
    _day(_program_day(7), 3, rpe=4, minutes=45),
    _day(_program_day(8), 2, minutes=0),
    _day(_program_day(9), 3, rpe=5, minutes=40, program="some"),
    _day(_program_day(10), 2, minutes=0),
    _day(_program_day(11), 2, rpe=4, minutes=45),
    _day(_program_day(12), 2, minutes=0),
    _day(_program_day(13), 2, rpe=5, minutes=45, note="Hinging without thinking about it now."),
]

# Rafael checked in every evening for eleven days and then stopped: the
# last line is three days old.
RAFAEL: list[CheckinDay] = [
    _day(_program_day(0), 3, rpe=7, minutes=60, hour=21, minute=15, note="Shoulder's fine on everything except overhead."),
    _day(_program_day(1), 2, rpe=7, minutes=60, hour=21, minute=15),
    _day(_program_day(2), 3, rpe=7, minutes=60, hour=21, minute=15, program="some"),
    _day(_program_day(3), 2, minutes=0, hour=21, minute=15),
    _day(_program_day(4), 2, rpe=7, minutes=60, hour=21, minute=15),
    _day(_program_day(5), 3, rpe=7, minutes=60, hour=21, minute=15),
    _day(_program_day(6), 2, minutes=0, hour=21, minute=15, program="some"),
    _day(_program_day(7), 2, rpe=7, minutes=60, hour=21, minute=15),
    _day(_program_day(8), 3, rpe=7, minutes=60, hour=21, minute=15),
    _day(_program_day(9), 2, rpe=7, minutes=60, hour=21, minute=15, program="some"),
    _day(_program_day(10), 2, minutes=0, hour=21, minute=15),
    _day(_program_day(11), 3, rpe=7, minutes=60, hour=21, minute=15,
         note="New job starts Monday. Might be a hectic week."),
]

HISTORY: dict[str, list[CheckinDay]] = {
    "hirt-cole": COLE, "hirt-tessa": TESSA, "hirt-devon": DEVON, "hirt-june": JUNE,
    "hirt-rafael": RAFAEL,
}

# What the morning should read, on a fresh fill. Pinned by the tests.
EXPECTED_TIERS = {
    "hirt-cole": "high", "hirt-rafael": "medium", "hirt-devon": "medium",
    "hirt-tessa": "low", "hirt-june": "low",
}


def write_history(db, patient_id: str, today: date) -> dict[str, int]:
    """The fourteen days for one lifter: a check-in transcript per evening,
    exactly as completing the lifter check-in writes one (the same prompt /
    answer pairs), and the training observations the answers produce
    (tasks/reported.py). Returns row counts."""
    from app.connectors.ingest import ingest_observations
    from app.models.checkin import Checkin, CheckinMessage
    from app.tasks.reported import reported_observations
    from app.tasks.service import transcript

    days = HISTORY.get(patient_id, [])
    observations = []
    for day in days:
        at = day.at(today)
        checkin = Checkin(patient_id=patient_id, occurred_at=at, channel="sms")
        db.add(checkin)
        db.flush()
        seq = 0
        for prompt, text in transcript(QSET, day.answers):
            db.add(CheckinMessage(checkin_id=checkin.id, seq=seq, who="copilot", text=prompt))
            db.add(CheckinMessage(checkin_id=checkin.id, seq=seq + 1, who="patient", text=text))
            seq += 2
        observations.extend(reported_observations(patient_id, day.answers, at, tz_id=TZ))
    db.commit()
    ingested = 0
    if observations:
        ingested, _, _ = ingest_observations(db, observations)
    return {"checkins": len(days), "observations": ingested}


def ensure_org(db) -> int:
    """The hospital and its two therapists, for a database that predates
    them (the deployed one, under demo_fill). Idempotent; returns rows added."""
    from app.models import CareTeamMember, Hospital, NotificationPreference
    from app.models.enums import NotificationChannel

    added = 0
    if db.get(Hospital, HIRT_HOSPITAL.id) is None:
        h = HIRT_HOSPITAL
        db.add(Hospital(id=h.id, name=h.name, system=h.system, city=h.city, state=h.state,
                        timezone=h.timezone))
        added += 1
    for ct in HIRT_CARE_TEAM:
        if db.get(CareTeamMember, ct.id) is None:
            db.add(CareTeamMember(id=ct.id, name=ct.name, role=ct.role))
            for channel, enabled in ((NotificationChannel.IN_APP, True),
                                     (NotificationChannel.SMS, False),
                                     (NotificationChannel.EMAIL, False)):
                db.add(NotificationPreference(recipient_id=ct.id, channel=channel, enabled=enabled))
            added += 1
    db.commit()
    return added


__all__ = [
    "HOSPITAL_ID", "TZ", "PROGRAM_DAYS", "QSET", "HIRT_HOSPITAL", "HIRT_CARE_TEAM",
    "HIRT_PATIENTS", "HIRT_IDS", "PATHWAYS", "PHONES", "MRNS", "CheckinDay", "HISTORY",
    "EXPECTED_TIERS", "write_history", "ensure_org",
]
