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
``write_schedule`` sits beside it: the exercise calendar each therapist
laid out (docs/dev/hep-schedule.md), with the past days' outcomes shaped
to the same five stories.

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


# --- the schedule -----------------------------------------------------------------
#
# The calendar each lifter's therapist laid out: program day 0 through today
# + 7, in catalog exercises that fit the pathway, three to five on a training
# day, with the past days' outcomes matching the check-in story above. Today's
# rows and the week ahead are open. Nothing here carries a clip: bytes need
# an object store, and scripts/seed_hirt_media.py adds placeholders.

# How far past today the calendar is filled in.
SCHEDULE_AHEAD = 7
MON_WED_FRI = (0, 2, 4)
TUE_THU_SAT = (1, 3, 5)


@dataclass(frozen=True)
class ScheduledExercise:
    """One exercise on a lifter's calendar: its dose (counts, hold, side,
    the load in hand and the effort it should feel like), the therapist's
    words to the patient, what she asks for with it (a clip of the attempt,
    the wearable on: off | optional | required), and the weekdays it falls
    on (Monday is 0; None is every day)."""

    key: str
    sets: int | None = None
    reps: int | None = None
    hold_seconds: int | None = None
    side: str = "not_applicable"
    note: str = ""
    weekdays: tuple[int, ...] | None = None
    load_kg: float | None = None
    rpe_target: int | None = None
    video_requirement: str = "optional"
    wearable_requirement: str = "optional"


SCHEDULE: dict[str, tuple[ScheduledExercise, ...]] = {
    # Dr. Gregg wants to see Cole's loaded work and how hard he is pushing it.
    "hirt-cole": (
        ScheduledExercise("functional_step_ups", sets=3, reps=10, side="left",
                          note="Slow on the way down.", weekdays=MON_WED_FRI, load_kg=10,
                          rpe_target=7, video_requirement="required"),
        ScheduledExercise("functional_wall_sits", sets=3, hold_seconds=30,
                          note="Knees over the ankles, not past the toes.", weekdays=MON_WED_FRI,
                          rpe_target=7, video_requirement="required"),
        ScheduledExercise("functional_mini_squats", sets=3, reps=12,
                          note="Only as deep as stays comfortable.", weekdays=MON_WED_FRI),
        ScheduledExercise("knee_terminal_extensions", sets=3, reps=15, side="left",
                          note="Squeeze the thigh at the top.", weekdays=MON_WED_FRI),
        ScheduledExercise("knee_heel_slides", sets=2, reps=10, side="left",
                          note="Every day, after your warm-up."),
    ),
    # Tessa's calf raises are done with the watch on, for the heart rate.
    "hirt-tessa": (
        ScheduledExercise("ankle_calf_raises", sets=3, reps=15, side="right",
                          note="Slow on the way down — count to three.",
                          wearable_requirement="required"),
        ScheduledExercise("ankle_dorsiflexion_stretch", sets=3, hold_seconds=30, side="right",
                          note="Heel stays down."),
        ScheduledExercise("balance_single_leg_stance", sets=3, hold_seconds=30, side="right",
                          note="Fingertips on the counter if you need them.",
                          weekdays=TUE_THU_SAT),
    ),
    # Devon and June: a clip and the wearable welcome, neither asked for.
    "hirt-devon": (
        ScheduledExercise("back_bird_dog", sets=3, reps=8,
                          note="Slow and level; nothing in the back should move."),
        ScheduledExercise("hip_glute_bridges", sets=3, reps=12, note="Squeeze at the top, no arch."),
        ScheduledExercise("back_pelvic_tilts", sets=2, reps=10),
        ScheduledExercise("back_cat_cow", sets=2, reps=8, note="Breathe with it."),
    ),
    "hirt-june": (
        ScheduledExercise("back_pelvic_tilts", sets=2, reps=10),
        ScheduledExercise("back_bird_dog", sets=3, reps=8, note="Reach long, stay level."),
        ScheduledExercise("hip_glute_bridges", sets=3, reps=10),
        ScheduledExercise("functional_sit_to_stand", sets=3, reps=8,
                          note="Hinge from the hips, chest up."),
    ),
    # Rafael's band work tells the wearable nothing, so it is not asked for.
    "hirt-rafael": (
        ScheduledExercise("shoulder_pendulum_swings", sets=2, reps=20, side="right",
                          note="Let the arm hang; small circles."),
        ScheduledExercise("shoulder_wall_slides", sets=3, reps=10, side="right"),
        ScheduledExercise("shoulder_band_external_rotation", sets=3, reps=12, side="right",
                          note="Elbow tucked to your side.", wearable_requirement="off"),
        ScheduledExercise("shoulder_scapular_retractions", sets=3, reps=12,
                          note="Shoulders down and back, not up."),
    ),
}

# Pain after the work, by program day 0..13, for the days that were done.
# Cole's climbs with his leg day; everyone else stays low.
PAIN_AFTER: dict[str, tuple[int, ...]] = {
    "hirt-cole": (2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 4, 4, 5, 6),
    "hirt-tessa": (2, 2, 2, 1, 2, 1, 1, 1, 1, 0, 1, 1, 0, 1),
    "hirt-devon": (4, 4, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3),
    "hirt-june": (2, 2, 2, 1, 2, 1, 2, 1, 1, 2, 1, 1, 1, 1),
    "hirt-rafael": (3, 2, 3, 2, 2, 3, 2, 2, 3, 2, 2, 3, 2, 2),
}
# How hard it felt (RPE 0–10), by program day, for the days that were done.
# Cole's climbs with his pain — the week he went back to his old leg day —
# while the others sit where their therapist put them.
EFFORT: dict[str, tuple[int, ...]] = {
    "hirt-cole": (5, 5, 5, 5, 5, 5, 5, 5, 6, 7, 7, 7, 8, 8),
    "hirt-tessa": (5, 5, 6, 5, 5, 5, 6, 6, 5, 5, 5, 6, 5, 6),
    "hirt-devon": (6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6),
    "hirt-june": (4, 4, 4, 4, 5, 5, 5, 4, 4, 5, 4, 4, 4, 5),
    "hirt-rafael": (6, 6, 7, 6, 6, 7, 6, 6, 7, 6, 6, 7, 6, 6),
}
# The week Cole went back to his old leg day he loaded the step-ups heavier
# than prescribed: 16 kg in hand against the 10 on the sheet, from program
# day 8. That is the load trend the board shows under his name.
COLE_HEAVY_FROM = 8
COLE_HEAVY_KG = 16.0
# Who wears a watch while training: Tessa, whose calf raises ask for it.
WEARS_WATCH = frozenset({"hirt-tessa"})
# When each lifter starts the day's exercises, local time. Each row's
# session (8–14 minutes) follows the one before it with a minute between,
# and the row is marked done the moment its session ends.
DONE_AT: dict[str, time] = {
    "hirt-cole": time(18, 40), "hirt-tessa": time(7, 15), "hirt-devon": time(21, 10),
    "hirt-june": time(8, 30), "hirt-rafael": time(19, 20),
}
SESSION_MINUTES = (8, 14)


def _session_minutes(program_day: int, order: int) -> int:
    """How long a session ran, 8–14 minutes, varying by day and position
    so the calendar does not read as a metronome."""
    low, high = SESSION_MINUTES
    return low + (program_day * 3 + order * 2) % (high - low + 1)


def _load_done(patient_id: str, program_day: int, item: ScheduledExercise) -> float | None:
    """The load the lifter reported: what was prescribed, except Cole's
    heavy week on the step-ups."""
    if (patient_id == "hirt-cole" and item.key == "functional_step_ups"
            and program_day >= COLE_HEAVY_FROM):
        return COLE_HEAVY_KG
    return item.load_kg
# What a lifter typed under a done day: (lifter, program day, exercise).
DONE_NOTES: dict[tuple[str, int, str], str] = {
    ("hirt-cole", 11, "knee_heel_slides"): "Knee was stiff all morning.",
    ("hirt-cole", 13, "knee_heel_slides"): "Knee's talking on the way down stairs.",
    ("hirt-tessa", 7, "ankle_calf_raises"): "Full set without the pinch.",
    ("hirt-june", 13, "functional_sit_to_stand"): "Easy today.",
}
# Devon's two skips, both the same reason.
DEVON_SKIPPED = frozenset({(11, "back_bird_dog"), (13, "back_cat_cow")})
SKIP_REASON = "Long shift"


@dataclass(frozen=True)
class Review:
    """A therapist's look at one done day: the exercise, which done day of
    it counting back from the latest (0 is the latest), and her note. The
    latest done day of an exercise is left alone where the media script
    puts a return clip on it, so the review queue has something to show."""

    patient_id: str
    key: str
    back: int
    note: str


REVIEWS: tuple[Review, ...] = (
    Review("hirt-cole", "functional_step_ups", 1,
           "Depth looks good. Slow the lowering a touch more — count to three on the way down."),
    Review("hirt-cole", "functional_wall_sits", 0,
           "Knees are tracking over the ankles now. Keep the hold honest at thirty."),
    Review("hirt-june", "back_bird_dog", 1,
           "Lovely and level. Reach a little longer through the heel next time."),
)
# How long after the lifter finished the therapist looked at it.
REVIEW_DELAY = timedelta(hours=2, minutes=20)

# What the past fourteen days read on a fresh fill, per lifter. Fourteen
# days hold every weekday exactly twice, so these do not move with the
# weekday the fill lands on; today's rows and the week ahead are always
# open, and the tests count those from the calendar. Pinned by the tests.
EXPECTED_SCHEDULE: dict[str, dict[str, int]] = {
    "hirt-cole": {"done": 38, "skipped": 0, "missed": 0},
    "hirt-tessa": {"done": 34, "skipped": 0, "missed": 0},
    "hirt-devon": {"done": 10, "skipped": 2, "missed": 44},
    "hirt-june": {"done": 56, "skipped": 0, "missed": 0},
    "hirt-rafael": {"done": 48, "skipped": 0, "missed": 8},
}
# What each lifter's rows ask for, where it is not the default (optional,
# optional): (video_requirement, wearable_requirement) by exercise. Pinned
# by the tests, which also check that every other row is the default.
EXPECTED_REQUIREMENTS: dict[str, dict[str, tuple[str, str]]] = {
    "hirt-cole": {"functional_step_ups": ("required", "optional"),
                  "functional_wall_sits": ("required", "optional")},
    "hirt-tessa": {"ankle_calf_raises": ("optional", "required")},
    "hirt-devon": {},
    "hirt-june": {},
    "hirt-rafael": {"shoulder_band_external_rotation": ("optional", "off")},
}
# (load_kg, rpe_target) where a row carries either; every other row has neither.
EXPECTED_LOADS: dict[str, dict[str, tuple[float | None, int | None]]] = {
    "hirt-cole": {"functional_step_ups": (10.0, 7), "functional_wall_sits": (None, 7)},
}
# How many done days each lifter's therapist has reviewed with a note.
EXPECTED_REVIEWS: dict[str, int] = {"hirt-cole": 2, "hirt-june": 1}


def _outcome(patient_id: str, program_day: int, key: str) -> tuple[str, str | None]:
    """What a past day's row reads: ``done``, ``skipped`` with the reason, or
    ``assigned`` (missed). Each lifter's rule is their story: Devon did the
    first two days, two of the four a week later and little else; Rafael
    did everything until he went quiet; the other three did it all."""
    if patient_id == "hirt-devon":
        if (program_day, key) in DEVON_SKIPPED:
            return "skipped", SKIP_REASON
        if program_day in (0, 1) or (
            program_day == 7 and key in ("back_bird_dog", "hip_glute_bridges")
        ):
            return "done", None
        return "assigned", None
    if patient_id == "hirt-rafael":
        return ("done", None) if program_day <= 11 else ("assigned", None)
    return "done", None


def ensure_consent(db, patient_id: str) -> int:
    """The lifters enrolled by text and accepted the beta terms in the room.
    Without a row the app stops at the consent screen the first time a
    phone — or the demo screen's frame — opens as them. Idempotent; returns
    the number of rows added (0 or 1)."""
    from app.models.patient import Patient
    from app.models.personal import Consent
    from app.personal import auth

    patient = db.get(Patient, patient_id)
    if patient is None or auth.current_consent(db, patient) is not None:
        return 0
    db.add(Consent(
        patient_id=patient_id, kind=auth.CONSENT_KIND, version=auth.CONSENT_VERSION,
        text_sha256=auth.consent_hash(),
        scopes={"data_storage": True, "ai_processing": True, "research_use": True, "beta_ack": True},
        signature=patient.name, device_name="enrolled by text",
    ))
    db.flush()
    return 1


def write_schedule(db, patient_id: str, today: date) -> dict[str, int]:
    """One lifter's calendar, program day 0 through today + 7, with the past
    days' outcomes: each done day as a session (started, ended, how long,
    pain before and after, effort, what was done), and the therapist's
    reviews. Needs the catalog for the exercise rows and upserts it if a
    key is missing; replaces any schedule the lifter already has, so a
    refill is clean. Returns row counts."""
    from sqlalchemy import delete, select

    from app.hep.catalog import ensure_catalog
    from app.hep.models import Exercise, ExerciseAssignment

    items = SCHEDULE.get(patient_id)
    counts = {"assignments": 0, "done": 0, "skipped": 0, "reviews": 0,
              "consents": ensure_consent(db, patient_id)}
    if not items:
        return counts
    spec = next(p for p in HIRT_PATIENTS if p.id == patient_id)
    keys = {item.key for item in items}

    def _exercises() -> dict[str, Exercise]:
        return {e.key: e for e in db.scalars(select(Exercise).where(Exercise.key.in_(keys)))}

    exercises = _exercises()
    if keys - set(exercises):
        ensure_catalog(db)
        exercises = _exercises()
    db.execute(delete(ExerciseAssignment).where(ExerciseAssignment.patient_id == patient_id))
    start = today - timedelta(days=PROGRAM_DAYS)
    laid_out = datetime.combine(start, time(9, 0))
    for offset in range(PROGRAM_DAYS + SCHEDULE_AHEAD + 1):
        day = start + timedelta(days=offset)
        order = 0
        clock = datetime.combine(day, DONE_AT[patient_id])
        for item in items:
            if item.weekdays is not None and day.weekday() not in item.weekdays:
                continue
            row = ExerciseAssignment(
                hospital_id=HOSPITAL_ID, patient_id=patient_id, exercise_id=exercises[item.key].id,
                scheduled_for=day, sort_order=order, sets=item.sets, reps=item.reps,
                hold_seconds=item.hold_seconds, side=item.side, load_kg=item.load_kg,
                rpe_target=item.rpe_target, clinician_instructions=item.note,
                assigned_by=spec.assigned_id, video_requirement=item.video_requirement,
                wearable_requirement=item.wearable_requirement, status="assigned",
                created_at=laid_out, updated_at=laid_out,
            )
            if day < today:
                status, reason = _outcome(patient_id, offset, item.key)
                if status == "done":
                    minutes = _session_minutes(offset, order)
                    started, ended = clock, clock + timedelta(minutes=minutes)
                    clock = ended + timedelta(minutes=1)
                    row.status, row.completed_at, row.updated_at = "done", ended, ended
                    row.started_at, row.ended_at, row.duration_s = started, ended, minutes * 60
                    row.pain_after = PAIN_AFTER[patient_id][offset]
                    row.pain_before = max(row.pain_after - 1, 0)
                    row.effort = EFFORT[patient_id][offset]
                    row.sets_done, row.reps_done = item.sets, item.reps
                    row.load_done_kg = _load_done(patient_id, offset, item)
                    row.wearable_worn = True if patient_id in WEARS_WATCH else None
                    row.note = DONE_NOTES.get((patient_id, offset, item.key))
                    row.completion_source = "app"
                    counts["done"] += 1
                elif status == "skipped":
                    row.status, row.skip_reason = "skipped", reason
                    row.updated_at = datetime.combine(day, time(22, 5))
                    counts["skipped"] += 1
            db.add(row)
            order += 1
            counts["assignments"] += 1
    db.commit()
    counts["reviews"] = write_reviews(db, patient_id)
    return counts


def write_reviews(db, patient_id: str) -> int:
    """The therapist's reviews of one lifter's done days (``REVIEWS``): the
    review on the row, and her note as one line on the thread under her
    name, the way the console's review writes it. A refill replaces the
    lines an earlier fill wrote. Returns the number of reviews written."""
    from sqlalchemy import delete, select

    from app.hep.models import Exercise, ExerciseAssignment
    from app.hep.schedule import review_line
    from app.models.mobile import Message

    specs = [r for r in REVIEWS if r.patient_id == patient_id]
    if not specs:
        return 0
    db.execute(delete(Message).where(
        Message.patient_id == patient_id, Message.sender == "care_team", Message.channel == "app",
        Message.text.like("About your %"),
    ))
    reviewer = next(p for p in HIRT_PATIENTS if p.id == patient_id).assigned_id
    written = 0
    for spec in specs:
        exercise = db.scalar(select(Exercise).where(Exercise.key == spec.key))
        done = db.scalars(
            select(ExerciseAssignment).where(
                ExerciseAssignment.patient_id == patient_id,
                ExerciseAssignment.exercise_id == exercise.id,
                ExerciseAssignment.status == "done",
            ).order_by(ExerciseAssignment.scheduled_for.desc())
        ).all()
        if len(done) <= spec.back:
            continue
        row = done[spec.back]
        at = row.completed_at + REVIEW_DELAY
        row.reviewed_at, row.reviewed_by, row.review_note = at, reviewer, spec.note
        row.updated_at = at
        db.add(Message(
            patient_id=patient_id, sender="care_team", sender_id=reviewer, channel="app",
            text=review_line(exercise.title, spec.note, has_clip=False), authored_by="care_team",
            created_at=at, read_by_care_team_at=at, read_by_patient_at=at + timedelta(hours=1),
        ))
        written += 1
    db.commit()
    return written


# --- programs ---------------------------------------------------------------------


@dataclass(frozen=True)
class ProgramTemplate:
    """A program the clinic keeps: drawn from one lifter's schedule."""

    name: str
    description: str
    weeks: int
    pattern: str  # the lifter whose SCHEDULE entry it is made of
    created_by: str


TEMPLATES: tuple[ProgramTemplate, ...] = (
    ProgramTemplate(
        "Patellar tendinopathy · phase 2",
        "Progressive loading for the knee: step-ups, wall sits, mini squats and terminal knee "
        "extensions three days a week, heel slides every day. Clips of the step-ups and the "
        "wall sits.",
        3, "hirt-cole", "ct_gregg",
    ),
    ProgramTemplate(
        "Lumbar · return to lifting",
        "Back to hinging under load: pelvic tilts, bird dog, glute bridges and sit-to-stand "
        "every day.",
        2, "hirt-june", "ct_harris",
    ),
)


def _template_items(items: tuple[ScheduledExercise, ...]) -> list[dict[str, Any]]:
    return [{
        "exercise_key": i.key,
        "weekdays": list(i.weekdays) if i.weekdays is not None else None,
        "sets": i.sets, "reps": i.reps, "hold_seconds": i.hold_seconds, "side": i.side,
        "load_kg": i.load_kg, "rpe_target": i.rpe_target, "clinician_instructions": i.note,
        "video_requirement": i.video_requirement, "wearable_requirement": i.wearable_requirement,
    } for i in items]


def ensure_templates(db) -> int:
    """The clinic's two programs, written through the same code the console
    uses so the items are exactly what it would have stored. A program the
    clinic already has by that name is left as it is — a therapist's edits
    survive a refill. Returns rows added."""
    from sqlalchemy import select

    from app.hep import templates as programs
    from app.hep.catalog import ensure_catalog
    from app.hep.models import Exercise

    added = 0
    for spec in TEMPLATES:
        if programs.find_template(db, HOSPITAL_ID, spec.name) is not None:
            continue
        keys = {i.key for i in SCHEDULE[spec.pattern]}
        if keys - set(db.scalars(select(Exercise.key).where(Exercise.key.in_(keys)))):
            ensure_catalog(db)
        programs.create_template(
            db, HOSPITAL_ID, name=spec.name, description=spec.description, weeks=spec.weeks,
            items=_template_items(SCHEDULE[spec.pattern]), actor=spec.created_by,
        )
        added += 1
    return added


def ensure_org(db) -> int:
    """The hospital, its two therapists and its programs, for a database
    that predates them (the deployed one, under demo_fill). Idempotent;
    returns rows added."""
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
    return added + ensure_templates(db)


__all__ = [
    "HOSPITAL_ID", "TZ", "PROGRAM_DAYS", "QSET", "HIRT_HOSPITAL", "HIRT_CARE_TEAM",
    "HIRT_PATIENTS", "HIRT_IDS", "PATHWAYS", "PHONES", "MRNS", "CheckinDay", "HISTORY",
    "EXPECTED_TIERS", "write_history", "ensure_org",
    "SCHEDULE_AHEAD", "ScheduledExercise", "SCHEDULE", "PAIN_AFTER", "EFFORT", "REVIEWS",
    "EXPECTED_SCHEDULE", "EXPECTED_REQUIREMENTS", "EXPECTED_LOADS", "EXPECTED_REVIEWS",
    "write_schedule", "write_reviews", "TEMPLATES", "ensure_templates",
]
