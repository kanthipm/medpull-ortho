"""The demo members of MedPull Personal.

The Personal tier has no console of its own: a subscriber's space is
theirs, and every console roster query filters them out
(``app/personal/scope.py``). The showcase needs something to show, so the
demo stack carries a handful of fictional members, each marked in
``PersonalProfile.settings["showcase"]``, and only rows with that mark are
ever listed or opened by the console's Personal pages
(``app/api/console_personal.py``) — and only while ``DEMO_MODE`` is on.

Four members, one per goal, each a real personal account made the way a
sign-up makes one (``create_personal_account``, a credential, the beta
consent, the trial and a complimentary grant):

* **Jordan Avery** (sleep): two short weeks behind them, four better
  nights since; the debt is coming down and readiness is climbing back.
* **Samira Haddad** (performance, a runner): a camp week on top of an easy
  one. She logs every run, so her load reads from session RPE.
* **Theo Okafor** (recovery): forty days after an ACL reconstruction, with
  the care section a recovery goal adds.
* **Nora Lindgren** (everyday): nine days in, a watch for four of them and
  no sleep from it yet: the "still learning you" state, honestly reached.

Every stream is a fixed film replayed against ``today``: the numbers are a
function of the member id and of how many days ago a day is, never of the
calendar, so the same story is on screen every morning and a second run on
the same day writes the same rows. A refresh keeps the account (the row,
its login, its app sessions, a phone the demo bound to it) and rewrites
everything generated around it.

Every member here is fictional: invented names, emails on a demo domain.
Any of them signs in to the app with their email and ``PASSWORD``.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.connectors.base import CanonicalObservation
from app.connectors.ingest import ingest_observations
from app.engine.curves import curve_mid, recovery_progress
from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.checkin import Checkin, CheckinMessage
from app.models.enums import AdherenceStatus, Granularity, ProcedureType
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider as SP
from app.models.mobile import Message, PatientSession
from app.models.patient import Device, Patient
from app.models.personal import (
    GOAL_LABELS,
    Consent,
    Entitlement,
    PersonalCredential,
    PersonalLog,
    PersonalProfile,
)
from app.personal import auth, daily, identity, insights, plan, subscription
from app.personal.data import load_personal_data
from app.personal.logs import PERSONAL_QSETS, record, record_task_answers
from app.personal.metrics import compute_dashboard
from app.personal.scope import PERSONAL, is_personal
from app.tasks import service as tasks

logger = logging.getLogger(__name__)

# The key in PersonalProfile.settings that marks a generated member.
MARK = "showcase"

PASSWORD = "medpull-demo-2026"
EMAIL_DOMAIN = "members.medpull.demo"
TZ = "America/Chicago"
# How far back a full member's streams go: the readouts' own window.
DAYS = 90
HOURLY_DAYS = 14
CHECKIN_DAYS = 30
# Today is a day in progress. Its steps and active energy stop after this
# hour, as a phone that last synced in the early afternoon would have them.
SO_FAR_HOUR = 13
# The mornings before today whose plan and brief are replayed onto the thread.
REPLAYED_MORNINGS = (2, 1)
COMP_DAYS = 3650


# --- who they are ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Gear:
    """One device on a member's account."""

    slug: str            # the device row's suffix and the observations' source device
    provider: SP
    model: str
    since: int           # days ago it was connected
    synced: time         # this morning's sync


@dataclass
class Night:
    """What a ring or watch reports for the night that ended on a day. A
    field left None is a signal that device did not deliver."""

    hrv: float | None = None
    rhr: float | None = None
    sleep: float | None = None      # hours asleep
    bed: float = 22.5               # clock hour it began; 24.5 is half past midnight
    efficiency: float = 0.9
    deep: float = 0.20              # share of the night
    rem: float = 0.22
    rr: float | None = None
    temp: float | None = None       # skin temperature, change from the wearer's own norm
    spo2: float | None = None


@dataclass
class Workout:
    kind: str
    minutes: float
    hour: float
    average_hr: int
    kcal_per_min: float
    steps_per_min: float = 0.0
    km: float | None = None


@dataclass
class Life:
    """A member's days, keyed by how many days ago each one is (0 = today)."""

    span: int = DAYS
    peaks: tuple[float, ...] = (8.0, 12.5, 18.0)   # the hours their steps cluster around
    kcal_per_step: float = 0.035
    nights: dict[int, Night] = field(default_factory=dict)
    steps: dict[int, float] = field(default_factory=dict)       # a whole day's, workouts apart
    workouts: dict[int, list[Workout]] = field(default_factory=dict)
    gait: dict[int, dict[M, float]] = field(default_factory=dict)
    vo2: dict[int, float] = field(default_factory=dict)
    hrr: dict[int, float] = field(default_factory=dict)
    # The morning check-in's answers, as the app would post them.
    checkins: dict[int, dict[str, Any]] = field(default_factory=dict)
    # Sessions the member logged themselves: (minutes, RPE).
    logged: dict[int, tuple[float, float]] = field(default_factory=dict)


Noise = Callable[[str, int], float]


@dataclass(frozen=True)
class Member:
    id: str
    first: str           # create_personal_account derives the id from it: "<first>-me"
    name: str
    sex: str
    born: date
    goal: str
    tagline: str
    detail: str
    joined: int          # days ago they opened the space
    gear: tuple[Gear, ...]
    nights_from: int     # index into gear: who delivers the overnight signals
    days_from: int       # ...steps and active energy
    workouts_from: int   # ...workouts, VO2 max and heart-rate recovery
    life: Callable[[Noise], Life]
    hrv: M = M.HRV_RMSSD
    gait_from: int | None = None
    hero: bool = False
    sport: str | None = None
    weekly_target_minutes: int | None = None
    sleep_target_hours: float | None = None
    injury: str | None = None
    procedure: str | None = None
    postop_day: int | None = None

    @property
    def email(self) -> str:
        return f"{self.name.lower().replace(' ', '.')}@{EMAIL_DOMAIN}"


def _rng(member_id: str, salt: str) -> np.random.Generator:
    digest = hashlib.sha256(f"{member_id}:{salt}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def _noise(member_id: str) -> Noise:
    """Standard-normal draws by signal and by days ago, the same on every run."""
    drawn: dict[str, np.ndarray] = {}

    def z(key: str, i: int) -> float:
        if key not in drawn:
            drawn[key] = _rng(member_id, f"noise:{key}").standard_normal(DAYS + 1)
        return float(drawn[key][i])

    return z


def _felt(sleep_hours: float, energy: int) -> tuple[str, str]:
    """The check-in's two choice answers, from the night and the morning."""
    quality = "great" if sleep_hours >= 7.6 else "ok" if sleep_hours >= 6.7 else "rough"
    mood = "good" if energy >= 6 else "flat" if energy >= 4 else "low"
    return quality, mood


# --- Jordan: two short weeks, four better nights -----------------------------------------------

JORDAN_ROUGH = range(4, 18)   # days ago: the fortnight of late nights


def _jordan(z: Noise) -> Life:
    life = Life(peaks=(8.0, 12.5, 18.5), kcal_per_step=0.032)
    for i in range(DAYS):
        rough = i in JORDAN_ROUGH
        worn = (JORDAN_ROUGH[-1] - i) / (len(JORDAN_ROUGH) - 1) if rough else 0.0
        # The last four nights follow the script closely: they are the story.
        quiet = 0.3 if i < 4 else 1.0
        night = Night(
            hrv=56.0 * (1 + 0.055 * quiet * z("hrv", i)),
            rhr=54.0 + 1.1 * quiet * z("rhr", i),
            sleep=7.85 + 0.26 * z("sleep", i),
            bed=22.55 + 0.28 * z("bed", i),
            efficiency=0.915 + 0.015 * z("eff", i),
            deep=0.21, rem=0.23,
            rr=14.2 + 0.3 * z("rr", i),
            temp=0.07 * z("temp", i),
            spo2=97.3 + 0.3 * z("spo2", i),
        )
        steps = 8800.0 * (1 + 0.13 * z("steps", i))
        if rough:
            night.sleep = 6.25 + 0.2 * z("sleep", i)
            night.bed = 24.15 + 0.4 * z("bed", i)
            night.hrv *= 0.90 - 0.10 * worn
            night.rhr += 2.0 + 2.5 * worn
            night.efficiency -= 0.05
            night.deep, night.rem = 0.17, 0.20
            night.rr += 0.35 * worn
            steps *= 0.86
        elif i < 4:
            night.sleep = (8.1, 8.0, 7.6, 7.2)[i] + 0.04 * z("sleep", i)
            night.bed = (22.3, 22.35, 22.6, 23.1)[i]
            night.hrv *= (1.0, 0.97, 0.93, 0.87)[i]
            night.rhr += (0.2, 0.9, 1.8, 3.0)[i]
        life.nights[i] = night
        life.steps[i] = steps

        # Two lifts and a run in an ordinary week; the run goes first when
        # the nights get short. A stretch and an easy jog on the way back.
        cycle = i % 7
        sessions: list[Workout] = []
        if cycle in (1, 4):
            sessions.append(Workout("strength training", (36.0 if rough else 46.0) + 2 * z("gym", i),
                                    18.5, 116, 6.0))
        elif cycle == 6 and not rough:
            sessions.append(Workout("running", 31.0 + 2 * z("run", i), 7.0, 144, 10.5, 165.0, 5.2))
        elif i == 3:
            sessions.append(Workout("running", 26.0, 17.75, 138, 9.5, 160.0, 3.9))
        elif i == 2:
            sessions.append(Workout("yoga", 25.0, 18.0, 92, 3.2))
        if sessions:
            life.workouts[i] = sessions

        if i < CHECKIN_DAYS and i not in (9, 14):   # two mornings skipped in the thick of it
            energy = 7 + round(0.6 * z("energy", i))
            if rough:
                energy = 5 - round(1.6 * worn + 0.4 * z("energy", i))
            elif i < 4:
                energy = (7, 6, 6, 5)[i]
            energy = int(min(10, max(1, energy)))
            quality, mood = _felt(night.sleep, energy)
            answers: dict[str, Any] = {
                "energy": energy,
                "soreness": int(max(0, 1 + round(0.7 * z("sore", i)))),
                "sleep_quality": quality, "mood": mood,
            }
            if i == 12:
                answers["note"] = "Launch week. In bed after midnight again."
            if i == 4:
                answers["note"] = "Last late night. The launch ships today."
            life.checkins[i] = answers

    # He found "Log a session" eleven days ago: enough for the journal, not
    # yet the fortnight the load panel wants before it reads from session RPE.
    for i, rpe in ((11, 6), (8, 6), (4, 7), (3, 4), (2, 3), (1, 6)):
        life.logged[i] = (round(life.workouts[i][0].minutes), float(rpe))
    life.vo2 = {83: 42.9, 69: 43.1, 55: 43.2, 41: 43.4, 27: 43.3, 20: 43.1, 3: 42.9}
    life.hrr = {83: 28.0, 62: 29.0, 48: 30.0, 34: 29.0, 20: 27.0, 3: 27.0}
    return life


# --- Samira: a camp week on top of an easy one ------------------------------------------------

# Days ago -> (minutes, RPE, what it was).
SAMIRA_CAMP = {6: (55, 6, "trail running"), 5: (70, 7, "trail running"), 4: (45, 4, "running"),
               3: (95, 7, "trail running"), 2: (60, 6, "trail running"), 1: (125, 8, "trail running")}
# By day of her seven-day cycle (days ago modulo 7).
SAMIRA_EASY_WEEK = {1: (60, 4), 2: (30, 3), 4: (35, 5), 6: (40, 6)}
SAMIRA_USUAL_WEEK = {1: (85, 5), 2: (35, 3), 4: (45, 7), 5: (40, 3), 6: (50, 7)}


def _samira(z: Noise) -> Life:
    life = Life(peaks=(6.5, 12.5, 17.5), kcal_per_step=0.03)
    for i in range(DAYS):
        quiet = 0.35 if i < 7 else 1.0
        night = Night(
            hrv=68.0 * (1 + 0.055 * quiet * z("hrv", i)),
            rhr=47.0 + 1.1 * quiet * z("rhr", i),
            sleep=7.65 + 0.3 * z("sleep", i),
            bed=22.1 + 0.25 * z("bed", i),
            efficiency=0.925 + 0.015 * z("eff", i),
            deep=0.22, rem=0.23,
            rr=13.6 + 0.3 * z("rr", i),
            temp=0.07 * z("temp", i),
            spo2=96.9 + 0.3 * z("spo2", i),
        )
        if i == 0:
            night.hrv *= 0.955
            night.rhr += 1.0
            night.sleep = 8.3
        elif i <= 4:
            night.hrv *= 0.93
            night.rhr += 2.0
            if i == 1:
                night.sleep = 7.9
        elif i <= 6:
            night.hrv *= 0.97
            night.rhr += 0.8
        life.nights[i] = night
        life.steps[i] = 6500.0 * (1 + 0.12 * z("steps", i))

        cycle = i % 7
        run: tuple[float, float, str] | None = None
        if i in SAMIRA_CAMP:
            run = SAMIRA_CAMP[i]
        elif 7 <= i <= 13 and cycle in SAMIRA_EASY_WEEK:
            run = (*SAMIRA_EASY_WEEK[cycle], "running")
        elif i > 13 and cycle in SAMIRA_USUAL_WEEK:
            minutes, rpe = SAMIRA_USUAL_WEEK[cycle]
            run = (minutes + round(3 * z("run", i)), rpe, "running")
        if run is not None:
            minutes, rpe, kind = run
            pace = 6.3 - 0.22 * rpe + (0.9 if kind == "trail running" else 0.0)   # min per km
            life.workouts[i] = [Workout(kind, float(minutes), 6.5 if cycle in (1, 4) else 17.5,
                                        int(124 + 6.5 * rpe), 7.5 + rpe, 168.0,
                                        round(minutes / pace, 1))]
            life.logged[i] = (float(minutes), float(rpe))

        if i < CHECKIN_DAYS and i != 20:
            energy = int(min(10, max(1, 7 + round(0.7 * z("energy", i)))))
            soreness = int(max(0, 2 + round(0.7 * z("sore", i))))
            if i <= 6:
                energy = (5, 5, 6, 6, 7, 6, 7)[i]
                soreness = (6, 6, 5, 5, 3, 4, 3)[i]
            quality, mood = _felt(night.sleep, energy)
            answers: dict[str, Any] = {"energy": energy, "soreness": soreness,
                                       "sleep_quality": quality, "mood": mood}
            if i == 5:
                answers["note"] = "Trail camp, day two. Hills both days."
            if i == 0:
                answers["note"] = "Legs heavy on the stairs this morning."
            life.checkins[i] = answers

    life.vo2 = {85: 51.8, 71: 52.0, 57: 52.3, 43: 52.5, 29: 52.9, 15: 53.1, 2: 53.2}
    life.hrr = {87: 37.0, 73: 38.0, 59: 38.0, 45: 39.0, 31: 40.0, 17: 40.0, 10: 39.0, 3: 36.0}
    return life


# --- Theo: forty days after an ACL reconstruction ---------------------------------------------

THEO_POSTOP_DAY = 40
# Rehab minutes and effort by post-op week, as he logs them.
THEO_REHAB = ((35, 38, 4), (28, 36, 4), (21, 32, 4), (14, 26, 3), (6, 20, 3))


def _theo(z: Noise) -> Life:
    life = Life(peaks=(9.0, 13.0, 17.5), kcal_per_step=0.036)
    acl = ProcedureType.ACL
    for i in range(DAYS):
        day = THEO_POSTOP_DAY - i          # post-op day; negative before the operation
        quiet = 0.3 if i < 2 else 1.0
        night = Night(
            hrv=46.0 * (1 + 0.06 * quiet * z("hrv", i)),
            rhr=57.0 + 1.1 * quiet * z("rhr", i),
            sleep=7.3 + 0.28 * z("sleep", i),
            bed=23.0 + 0.28 * z("bed", i),
            efficiency=0.905 + 0.015 * z("eff", i),
            deep=0.20, rem=0.22,
            rr=14.4 + 0.3 * z("rr", i),
            temp=0.07 * z("temp", i),
            spo2=97.3 + 0.3 * z("spo2", i),
        )
        steps = 8300.0 * (1 + 0.10 * z("steps", i))
        speed, asymmetry, double_support = 1.34, 4.2, 25.5
        if day >= 0:
            progress = recovery_progress(acl, day)
            night.hrv *= 1 - 0.30 * math.exp(-day / 9)
            night.rhr += 7.0 * math.exp(-day / 8)
            night.sleep -= 1.3 * math.exp(-day / 7)
            night.efficiency -= 0.09 * math.exp(-day / 7)
            night.bed += 0.5 * math.exp(-day / 7)
            night.rr += 1.0 * math.exp(-day / 3)
            night.temp += 0.45 * math.exp(-day / 3)
            night.spo2 -= 0.5 * math.exp(-day / 2)
            steps = 8300.0 * float(curve_mid(acl, day)) * 1.04 * (1 + 0.06 * z("steps", i))
            speed *= 0.52 + 0.48 * progress
            asymmetry += 12.0 * (1 - progress) ** 1.5
            double_support += 7.0 * (1 - progress)
        if i == 0:      # a rest day behind him and a long night: above his recent normal
            night.hrv *= 1.10
            night.rhr -= 2.2
            night.sleep = 8.0
        elif i == 1:
            night.hrv *= 1.05
            night.rhr -= 1.2
            night.sleep = 7.7
        life.nights[i] = night
        life.steps[i] = steps
        life.gait[i] = {
            M.WALKING_SPEED: speed * (1 + 0.03 * z("speed", i)),
            M.WALKING_ASYMMETRY_PCT: max(1.0, asymmetry + 0.6 * z("asym", i)),
            M.DOUBLE_SUPPORT_PCT: double_support + 0.7 * z("dsup", i),
        }

        cycle = i % 7
        if day < -2:
            # Before the operation: the bike and the gym, as far as the knee let him.
            if cycle in (1, 4):
                life.workouts[i] = [Workout("indoor cycling", 32.0 + 2 * z("bike", i), 18.0, 121, 7.5)]
            elif cycle == 6:
                life.workouts[i] = [Workout("strength training", 41.0 + 2 * z("gym", i), 18.0, 108, 5.5)]
        elif day >= 6 and i > 0 and cycle not in (0, 3):
            minutes, rpe = next((m, r) for since, m, r in THEO_REHAB if day >= since)
            sessions = [Workout("functional strength training", float(minutes), 17.0, 96 + 2 * rpe, 4.2)]
            if day >= 21 and cycle in (2, 5):
                sessions.append(Workout("indoor cycling", 18.0, 17.75, 112, 6.5))
            life.workouts[i] = sessions
            life.logged[i] = (float(minutes), float(rpe))

        if i < CHECKIN_DAYS:
            pain = 1 + 3.2 * math.exp(-(day - 10) / 12) + 0.35 * z("pain", i)
            if day in (21, 22):          # the week the bike came in
                pain += 1
            energy = int(min(10, max(1, round(5 + 2.2 * (1 - math.exp(-(day - 10) / 14))
                                              + 0.5 * z("energy", i)))))
            if i < 2:
                energy = (8, 7)[i]
            quality, mood = _felt(night.sleep, energy)
            answers: dict[str, Any] = {"energy": energy, "pain": int(min(10, max(0, round(pain)))),
                                       "sleep_quality": quality, "mood": mood}
            if day == 21:
                answers["note"] = "Physio added the stationary bike this week."
            if i == 3:
                answers["note"] = "Stairs felt normal going up today."
            life.checkins[i] = answers

    # Outdoor walks came back in the fifth week; the estimate fell with the layoff.
    life.vo2 = {86: 45.2, 72: 45.0, 58: 44.8, 46: 44.6, 10: 42.1, 3: 42.4}
    life.hrr = {80: 31.0, 66: 30.0, 52: 31.0, 18: 22.0, 11: 24.0, 4: 26.0}
    return life


# --- Nora: nine days in ---------------------------------------------------------------------

NORA_DAYS = 9
NORA_WATCH_NIGHTS = 4


def _nora(z: Noise) -> Life:
    life = Life(span=NORA_DAYS, peaks=(8.0, 12.5, 18.0), kcal_per_step=0.04)
    for i in range(NORA_DAYS):
        life.steps[i] = 6900.0 * (1 + 0.2 * z("steps", i))
        life.gait[i] = {
            M.WALKING_SPEED: 1.27 * (1 + 0.03 * z("speed", i)),
            M.WALKING_ASYMMETRY_PCT: max(1.0, 3.4 + 0.5 * z("asym", i)),
            M.DOUBLE_SUPPORT_PCT: 26.0 + 0.6 * z("dsup", i),
        }
        if i < NORA_WATCH_NIGHTS:
            # The watch is on her wrist, but sleep tracking is not switched
            # on: heart signals arrive, the night itself does not.
            life.nights[i] = Night(hrv=39.0 * (1 + 0.06 * z("hrv", i)), rhr=63.0 + 1.0 * z("rhr", i))
        if i in (2, 1):
            life.workouts[i] = [Workout("walking", (35.0, 28.0)[2 - i], 18.0, 104, 4.4, 108.0,
                                        (2.9, 2.3)[2 - i])]
        if i < 8 and i != 5:
            energy = int(min(10, max(1, 6 + round(0.8 * z("energy", i)))))
            answers: dict[str, Any] = {
                "energy": energy, "soreness": int(max(0, 1 + round(0.6 * z("sore", i)))),
                "sleep_quality": "great" if z("slept", i) > 0.4 else "ok",
                "mood": "good" if energy >= 6 else "flat",
            }
            if i == 3:
                answers["note"] = "New watch arrived. Wearing it to bed from tonight."
            life.checkins[i] = answers
    return life


OURA = Gear("oura", SP.OURA, "Oura Ring 4", 88, time(6, 42))
MEMBERS: tuple[Member, ...] = (
    Member(
        id="jordan-me", first="Jordan", name="Jordan Avery", sex="M", born=date(1992, 4, 18),
        goal="sleep", sleep_target_hours=7.75, hero=True,
        tagline="Sleep and recover better · Oura and Apple Watch",
        detail="Two short weeks behind them, sleep debt coming down",
        joined=62,
        gear=(OURA, Gear("apple_watch", SP.APPLE, "Apple Watch Series 10", 88, time(7, 5))),
        nights_from=0, days_from=1, workouts_from=1, life=_jordan,
    ),
    Member(
        id="samira-me", first="Samira", name="Samira Haddad", sex="F", born=date(1993, 2, 9),
        goal="performance", sport="running", weekly_target_minutes=300,
        tagline="Train and perform · running · Garmin",
        detail="A camp week on an easy one: load well above her norm",
        joined=110,
        gear=(Gear("garmin", SP.GARMIN, "Garmin Forerunner 265", 110, time(6, 31)),),
        nights_from=0, days_from=0, workouts_from=0, life=_samira,
    ),
    Member(
        id="theo-me", first="Theo", name="Theo Okafor", sex="M", born=date(1997, 8, 23),
        goal="recovery", injury="ACL reconstruction, left knee", procedure="ACL",
        postop_day=THEO_POSTOP_DAY,
        tagline=f"Recover from surgery · ACL reconstruction, day {THEO_POSTOP_DAY} · Apple Watch",
        detail="Signals above his recent normal, rehab progressing",
        joined=THEO_POSTOP_DAY - 5,
        gear=(Gear("apple_watch", SP.APPLE, "Apple Watch Series 10", 89, time(7, 12)),
              Gear("apple_health", SP.APPLE, "iPhone 16", 89, time(7, 12))),
        nights_from=0, days_from=0, workouts_from=0, gait_from=1, hrv=M.HRV_SDNN, life=_theo,
    ),
    Member(
        id="nora-me", first="Nora", name="Nora Lindgren", sex="F", born=date(1985, 11, 2),
        goal="everyday",
        tagline=f"Everyday health · day {NORA_DAYS}",
        detail="Still learning her baseline: no sleep from her watch yet",
        joined=NORA_DAYS - 1,
        gear=(Gear("apple_health", SP.APPLE, "iPhone 15", NORA_DAYS - 1, time(7, 20)),
              Gear("apple_watch", SP.APPLE, "Apple Watch SE", NORA_WATCH_NIGHTS - 1, time(7, 20))),
        nights_from=1, days_from=0, workouts_from=1, gait_from=0, hrv=M.HRV_SDNN, life=_nora,
    ),
)


# --- the mark ---------------------------------------------------------------------------------


def _mark(profile: PersonalProfile | None) -> dict[str, Any] | None:
    mark = (profile.settings or {}).get(MARK) if profile is not None else None
    return mark if isinstance(mark, dict) else None


def is_showcase(db: Session, patient: Patient | None) -> bool:
    """Whether ``patient`` is a generated demo member (a personal row whose
    profile carries the mark). A real subscriber is never one."""
    if not is_personal(patient):
        return False
    return _mark(db.get(PersonalProfile, patient.id)) is not None


def mark_of(db: Session, patient: Patient) -> dict[str, Any]:
    """What the mark says about a member: ``hero``, ``order``, ``tagline``,
    ``detail``, ``seeded_for``. Empty for a row without it."""
    return _mark(db.get(PersonalProfile, patient.id)) or {}


def _marked(db: Session) -> list[Patient]:
    rows = db.execute(
        select(Patient, PersonalProfile)
        .join(PersonalProfile, PersonalProfile.patient_id == Patient.id)
        .where(Patient.account_kind == PERSONAL)
    ).all()
    found = [(patient, _mark(profile)) for patient, profile in rows]
    found = [(patient, mark) for patient, mark in found if mark is not None]
    found.sort(key=lambda pair: (not pair[1].get("hero"), pair[1].get("order", 99), pair[0].name))
    return [patient for patient, _ in found]


def members(db: Session) -> list[Patient]:
    """Every generated demo member, hero first. Empty off the demo stack."""
    if not settings.demo_mode:
        return []
    return _marked(db)


# --- the account -------------------------------------------------------------------------------


def _anchor(member: Member, today: date) -> date:
    """The engine's day zero: the operation for a recovery goal, else the
    day the space was opened."""
    return today - timedelta(days=member.postop_day if member.postop_day is not None
                             else member.joined)


def _account(db: Session, member: Member, order: int, today: date) -> tuple[Patient, PersonalProfile] | None:
    """The member's own rows, created on the first run and brought back to
    the script on every later one. None when the id belongs to somebody
    else: a row without the mark is never touched."""
    from app.api.mobile import PROCEDURE_DISPLAY

    patient = db.get(Patient, member.id)
    if patient is not None and not is_showcase(db, patient):
        logger.warning("Demo member %s not written: that id is another account's", member.id)
        return None
    anchor = _anchor(member, today)
    if patient is None:
        patient, profile = identity.create_personal_account(
            db, name=member.first, phone=None, goal=member.goal, sms_briefs=False,
        )
        # The mark goes on before anything else is written, so a run that
        # stops half way is picked up by the next one instead of orphaned.
        profile.settings = {MARK: {"order": order}}
        db.commit()
    else:
        profile = db.get(PersonalProfile, patient.id)
    age = today.year - member.born.year - ((today.month, today.day) < (member.born.month, member.born.day))
    procedure = member.procedure or "NONE"
    patient.name = member.name
    patient.initials = "".join(part[0] for part in member.name.split()[:2]).upper()
    patient.sex, patient.date_of_birth, patient.age = member.sex, member.born, age
    patient.procedure_type = procedure
    patient.procedure_display = PROCEDURE_DISPLAY[procedure]
    patient.surgery_date = patient.discharge_date = anchor
    patient.care_pathway = None if member.procedure else "general_recovery"
    patient.timezone = TZ
    opened = datetime.combine(today - timedelta(days=member.joined), time(20, 14))
    patient.created_at = opened
    profile.goal = member.goal
    profile.sport = member.sport
    profile.weekly_target_minutes = member.weekly_target_minutes
    profile.sleep_target_hours = member.sleep_target_hours
    profile.injury = member.injury
    profile.anchor_date = anchor if member.procedure else None
    profile.units = "metric"
    profile.sms_briefs = False
    profile.brief_hour = 7
    profile.created_at = opened
    profile.settings = {MARK: {
        "order": order, "hero": member.hero, "tagline": member.tagline, "detail": member.detail,
        # Set once the whole member is written (``_write``): a mark without
        # it is a run that did not finish.
        "seeded_for": None,
    }}
    if db.get(PersonalCredential, patient.id) is None and auth.credential_for_email(db, member.email) is None:
        auth.create_credential(db, patient, member.email, PASSWORD)
    db.commit()
    return patient, profile


# --- clearing what a run wrote -------------------------------------------------------------------


def _sweep_files(db: Session, patient_id: str) -> None:
    """The member's files and lake copies. Never fatal: the rows are what a
    refresh has to get right, and a function without the personal bucket's
    grant must still be able to run it."""
    from app.models.attachment import Attachment
    from app.storage import blobs

    try:
        blobs.delete_keys(list(db.scalars(
            select(Attachment.storage_key).where(Attachment.patient_id == patient_id)).all()))
        blobs.delete_patient_blobs(patient_id)
    except Exception:  # noqa: BLE001 — see the docstring
        logger.exception("could not sweep the files of demo member %s", patient_id)


def _wipe(db: Session, patient_id: str) -> None:
    """Everything a run writes for a member, and everything a demo added on
    top (coach turns, completed plan items, a logged session). The account
    stays: the patient row with any phone bound to it, the profile and its
    mark, the login, app sessions, and links texts already carry."""
    from app.models.attachment import Attachment
    from app.models.checkin import CheckinInvite
    from app.models.insight import EstablishedBaseline, Insight, RiskAssessment
    from app.models.library import CareAction, TaskVerification
    from app.models.notification import Notification
    from app.models.observation import Observation

    _sweep_files(db, patient_id)
    checkin_ids = db.scalars(select(Checkin.id).where(Checkin.patient_id == patient_id)).all()
    if checkin_ids:
        db.execute(delete(CheckinMessage).where(CheckinMessage.checkin_id.in_(checkin_ids)))
    for model in (PersonalLog, Entitlement, Consent, Attachment, Message, Notification, CareAction,
                  Checkin, CheckinInvite, TaskVerification, AdherenceRecord, AdherenceTask,
                  Insight, RiskAssessment, EstablishedBaseline, Observation, Device):
        db.execute(delete(model).where(model.patient_id == patient_id))
    db.commit()


def remove_personal(db: Session) -> list[str]:
    """Delete every demo member outright, account and all: the same steps
    as a subscriber deleting their own space. Only rows with the mark."""
    from app.identity import delete_patient

    removed: list[str] = []
    for patient in _marked(db):
        pid = patient.id
        _wipe(db, pid)
        for session in db.scalars(select(PatientSession).where(PatientSession.patient_id == pid)).all():
            session.revoked_at = session.revoked_at or datetime.now()
        for model in (PersonalCredential, PersonalProfile):
            db.execute(delete(model).where(model.patient_id == pid))
        db.commit()
        delete_patient(db, patient)
        removed.append(pid)
    return removed


# --- the streams ------------------------------------------------------------------------------------

UNITS: dict[M, str] = {
    M.HRV_RMSSD: "ms", M.HRV_SDNN: "ms", M.RESTING_HR: "bpm", M.SLEEP_DURATION: "h",
    M.SLEEP_STAGES: "h", M.RESPIRATORY_RATE: "breaths/min", M.SKIN_TEMP_DELTA: "degC",
    M.SPO2: "%", M.STEPS: "count", M.ACTIVE_ENERGY: "kcal", M.EXERCISE_SESSION: "min",
    M.VO2_MAX: "mL/kg/min", M.HR_RECOVERY_1MIN: "bpm", M.WALKING_SPEED: "m/s",
    M.WALKING_ASYMMETRY_PCT: "%", M.DOUBLE_SUPPORT_PCT: "%",
}


def _hourly_steps(member: Member, life: Life, i: int) -> np.ndarray:
    """One day's steps by the hour: the day's own total spread around the
    hours this person moves at, plus each workout's steps in its own hour."""
    hours = np.arange(24)
    profile = sum(np.exp(-((hours - peak) ** 2) / 5.0) for peak in life.peaks)
    profile = np.where((hours >= 6) & (hours <= 22), profile, 0.0)
    r = _rng(member.id, f"hourly:{i}")
    weights = profile * np.clip(1.0 + 0.25 * r.standard_normal(24), 0.05, None)
    buckets = np.round(weights / weights.sum() * life.steps[i])
    for workout in life.workouts.get(i, []):
        buckets[int(workout.hour)] += round(workout.minutes * workout.steps_per_min)
    return buckets


def _observations(member: Member, life: Life, today: date) -> list[CanonicalObservation]:
    rows: list[CanonicalObservation] = []

    def add(gear: Gear, metric: M, start: datetime, end: datetime, value: float,
            granularity: Granularity = Granularity.DAILY_SUMMARY,
            detail: dict[str, Any] | None = None) -> None:
        rows.append(CanonicalObservation(
            patient_id=member.id, source_provider=gear.provider, metric_type=metric,
            unit=UNITS[metric], value_num=round(float(value), 3), value_json=detail,
            start_time=start, end_time=end, granularity=granularity,
            source_device_id=f"{gear.slug}:{member.id}", timezone=TZ,
        ))

    def daily(gear: Gear, metric: M, d: date, value: float, detail: dict[str, Any] | None = None) -> None:
        add(gear, metric, datetime.combine(d, time(0, 0)), datetime.combine(d, time(23, 59, 59)),
            value, detail=detail)

    ring, wrist, band = (member.gear[member.nights_from], member.gear[member.days_from],
                         member.gear[member.workouts_from])
    for i in range(life.span - 1, -1, -1):
        d = today - timedelta(days=i)
        night = life.nights.get(i)
        if night is not None:
            if night.hrv is not None:
                daily(ring, member.hrv, d, night.hrv)
            if night.rhr is not None:
                daily(ring, M.RESTING_HR, d, night.rhr)
            if night.rr is not None:
                daily(ring, M.RESPIRATORY_RATE, d, night.rr)
            if night.temp is not None:
                daily(ring, M.SKIN_TEMP_DELTA, d, night.temp)
            if night.spo2 is not None:
                daily(ring, M.SPO2, d, min(99.5, night.spo2))
            if night.sleep is not None:
                efficiency = float(min(0.98, max(0.70, night.efficiency)))
                in_bed = night.sleep / efficiency
                began = datetime.combine(d - timedelta(days=1), time(0, 0)) + timedelta(hours=night.bed)
                stages = {
                    "deep": round(night.sleep * night.deep, 2),
                    "rem": round(night.sleep * night.rem, 2),
                    "light": round(night.sleep * (1 - night.deep - night.rem), 2),
                    "awake": round(in_bed - night.sleep, 2),
                    "bedtime_start": began.isoformat(timespec="minutes"),
                    "bedtime_stop": (began + timedelta(hours=in_bed)).isoformat(timespec="minutes"),
                    "efficiency": round(efficiency, 3),
                }
                daily(ring, M.SLEEP_DURATION, d, night.sleep)
                daily(ring, M.SLEEP_STAGES, d, night.sleep, stages)

        # Steps and active energy. Today stops in the early afternoon; a day
        # inside the last fortnight also carries its hourly buckets.
        workouts = life.workouts.get(i, [])
        buckets = _hourly_steps(member, life, i)
        so_far = 1.0
        if i == 0:
            whole = float(buckets.sum()) or 1.0
            buckets = buckets[: SO_FAR_HOUR + 1]
            so_far = float(buckets.sum()) / whole
        if i < HOURLY_DAYS:
            for hour, count in enumerate(buckets):
                start = datetime.combine(d, time(hour, 0))
                add(wrist, M.STEPS, start, start + timedelta(minutes=59, seconds=59), count,
                    Granularity.INTERVAL)
        daily(wrist, M.STEPS, d, float(buckets.sum()))
        r = _rng(member.id, f"energy:{i}")
        energy = (life.steps[i] * life.kcal_per_step + 40 * float(r.standard_normal())) * so_far
        energy += sum(w.minutes * w.kcal_per_min for w in workouts)
        daily(wrist, M.ACTIVE_ENERGY, d, max(20.0, energy))

        for workout in workouts:
            start = datetime.combine(d, time(0, 0)) + timedelta(hours=workout.hour)
            minutes = round(workout.minutes)
            detail: dict[str, Any] = {
                "kind": workout.kind, "average_hr": workout.average_hr,
                "max_hr": workout.average_hr + 21,
                "calories": round(minutes * workout.kcal_per_min),
            }
            if workout.km is not None:
                detail["distance_m"] = round(workout.km * 1000)
            add(band, M.EXERCISE_SESSION, start, start + timedelta(minutes=minutes), minutes,
                Granularity.SESSION, detail)

        if member.gait_from is not None and i in life.gait:
            for metric, value in life.gait[i].items():
                daily(member.gear[member.gait_from], metric, d, value)
        if i in life.vo2:
            daily(band, M.VO2_MAX, d, life.vo2[i])
        if i in life.hrr:
            daily(band, M.HR_RECOVERY_1MIN, d, life.hrr[i])
    return rows


# --- what the member did: check-ins, logged sessions, the plan -----------------------------------


def _complete(db: Session, task: AdherenceTask, answers: dict[str, Any], at: datetime) -> None:
    """One completion, written the way ``tasks.complete_task`` writes it but
    on the day it belongs to: the transcript, the day's adherence record,
    the task's result, and the subjective log for a question set that feeds
    it."""
    qset = tasks.question_set_key(task)
    pairs = tasks.transcript(qset, answers)
    checkin: Checkin | None = None
    if pairs:
        checkin = Checkin(patient_id=task.patient_id, occurred_at=at, channel="app")
        db.add(checkin)
        db.flush()
        for n, (prompt, said) in enumerate(pairs):
            db.add(CheckinMessage(checkin_id=checkin.id, seq=2 * n, who="copilot", text=prompt))
            db.add(CheckinMessage(checkin_id=checkin.id, seq=2 * n + 1, who="patient", text=said))
    task.status = "done"
    task.completed_at = at
    task.completed_via = "app"
    task.result = {"answers": answers, "checkin_id": checkin.id if checkin else None}
    task.payload = {**(task.payload or {}), "last_done": at.date().isoformat()}
    db.add(AdherenceRecord(patient_id=task.patient_id, task_id=task.id, date=at.date(),
                           status=AdherenceStatus.SELF_ATTESTED))
    if qset in PERSONAL_QSETS:
        record_task_answers(db, task, answers, at.date())


def _plan_answers(task: AdherenceTask, life: Life, i: int) -> tuple[dict[str, Any], time] | None:
    """How the member answered one of a past day's plan items, and when.
    None for a session the plan asked for on a day they did not train."""
    if task.kind == "workout":
        if i not in life.logged:
            return None
        minutes, rpe = life.logged[i]
        return {"minutes": int(minutes), "rpe": int(rpe)}, time(19, 5)
    if task.kind == "exercise":
        return {"exercises": "all", "pain": life.checkins.get(i, {}).get("pain", 1)}, time(17, 50)
    if task.kind == "walk":
        return {"minutes": 25}, time(12, 40)
    return {"done": "yes"}, time(22, 5)


def _board(db: Session, patient: Patient, profile: PersonalProfile, day: date) -> dict[str, Any]:
    data = load_personal_data(db, patient, day)
    board = compute_dashboard(data, patient, profile)
    board["notes"] = data.notes
    return board


def _said(db: Session, patient_id: str, at: datetime, text: str, *, coach: bool,
          checkin_task_id: int | None = None) -> None:
    """One thread line at a given moment: the member's, or the coach's. A
    coach line with ``checkin_task_id`` is that morning's brief."""
    line = Message(patient_id=patient_id, sender="copilot" if coach else "patient", channel="app",
                   text=text, created_at=at, authored_by="ai" if coach else None)
    if coach:
        line.read_by_patient_at = at + timedelta(minutes=3)
    if checkin_task_id is not None:
        line.action_kind = daily.BRIEF_TAG
        line.action_task_id = checkin_task_id
        line.action_label = "Start check-in"
    db.add(line)


def _extra(board: dict[str, Any], panel: str, key: str) -> Any:
    return (((board.get("panels") or {}).get(panel) or {}).get("extra") or {}).get(key)


def _week(board: dict[str, Any], metric: str, which: str) -> float:
    return float((((board.get("week") or {}).get("metrics") or {}).get(metric) or {}).get(which) or 0.0)


# What each member asked their coach on the two evenings before today, and
# what it said. Written as rows, never through a model; every number in a
# reply is read from that morning's own readouts, so the thread agrees with
# the screens beside it. (days ago, clock time, their line, the coach's.)
Exchange = tuple[int, time, str, str]


def _jordan_thread(boards: dict[int, dict[str, Any]]) -> list[Exchange]:
    two, one = boards[2], boards[1]
    return [
        (2, time(21, 20), "Slept seven and a half hours and I still feel flat. Is that normal?",
         f"Yes. One full night pays back part of two short weeks, not all of it. You were carrying "
         f"{_extra(two, 'sleep', 'debt_hours'):.1f} h of sleep debt this morning and readiness was "
         f"{_extra(two, 'readiness', 'score'):.0f}. Keep the same bedtime tonight and give it two "
         f"or three more nights."),
        (1, time(12, 45), "Save a note: the launch shipped, no more late nights.",
         "Saved that to your journal."),
        (1, time(21, 35), "Is my resting heart rate back to normal?",
         f"Nearly. Last night was {_extra(one, 'resting_hr', 'latest'):.0f} bpm against a usual "
         f"{_extra(one, 'resting_hr', 'baseline_mean'):.0f}, and it has come down every night since "
         f"you went back to an earlier bedtime. Sleep debt is {_extra(one, 'sleep', 'debt_hours'):.1f} h "
         f"and falling."),
    ]


def _samira_thread(boards: dict[int, dict[str, Any]]) -> list[Exchange]:
    two, one = boards[2], boards[1]
    return [
        (2, time(18, 5), "Hill repeats done, an hour at about a 6. Legs are heavy.",
         f"That fits the week. Your last seven days add up to {_week(two, 'load', 'this'):,.0f} AU "
         f"of session load against {_week(two, 'load', 'last'):,.0f} the week before. Keep the "
         f"first half of tomorrow's long run easy."),
        (1, time(19, 40), "Long run done, just over two hours. How is my load looking?",
         f"Heavy. The last seven days come to {_week(one, 'load', 'this'):,.0f} AU against "
         f"{_week(one, 'load', 'last'):,.0f} the week before, and last night's HRV was "
         f"{_extra(one, 'hrv', 'latest'):.0f} ms against a usual "
         f"{_extra(one, 'hrv', 'baseline_mean'):.0f}. Take tomorrow easy or off and let the base "
         f"catch up."),
    ]


def _theo_thread(boards: dict[int, dict[str, Any]]) -> list[Exchange]:
    two, one = boards[2], boards[1]
    return [
        (2, time(18, 10), "Knee was a 2 after the bike, back to a 1 by evening.",
         f"Noted. Put the same two numbers in tomorrow's check-in so the trend shows. Readiness "
         f"was {_extra(two, 'readiness', 'score'):.0f} this morning, close to your recent normal: "
         f"keep the set as your physio wrote it."),
        (1, time(20, 15), "Can I add the single-leg work my physio showed me?",
         f"That is your physio's call, and they know the knee. What I can tell you is where your "
         f"signals are: readiness {_extra(one, 'readiness', 'score'):.0f} this morning, resting "
         f"heart rate {_extra(one, 'resting_hr', 'latest'):.0f} against a usual "
         f"{_extra(one, 'resting_hr', 'baseline_mean'):.0f}. If they say yes, add only that and "
         f"note the next morning's pain."),
    ]


def _nora_thread(boards: dict[int, dict[str, Any]]) -> list[Exchange]:
    return [
        (1, time(20, 5), "When do I get a readiness score?",
         f"After five nights of resting heart rate and HRV, and one night of sleep. You have "
         f"{NORA_WATCH_NIGHTS - 1} nights of heart data so far and no sleep is arriving from "
         f"your watch yet. Check that sleep tracking is switched on, wear it overnight, and the "
         f"score should appear within the week."),
    ]


THREADS: dict[str, Callable[[dict[int, dict[str, Any]]], list[Exchange]]] = {
    "jordan-me": _jordan_thread, "samira-me": _samira_thread,
    "theo-me": _theo_thread, "nora-me": _nora_thread,
}
# The one line a coach turn above saved to the journal: (member, days ago, text).
JOURNAL = (("jordan-me", 1, "The launch shipped, no more late nights."),)


def _write(db: Session, member: Member, patient: Patient, profile: PersonalProfile, today: date) -> None:
    life = member.life(_noise(member.id))

    # Access: the trial every account starts on, long run out for the older
    # members, and a complimentary grant so nothing answers 402 if the
    # paywall is ever switched on. The beta consent, as the app records it.
    opened = datetime.combine(today - timedelta(days=member.joined), time(20, 14))
    subscription.start_trial(db, patient, now=opened)
    subscription.grant_comp(db, patient, COMP_DAYS, note="MedPull showcase member")
    auth.record_consent(
        db, patient, version=auth.CONSENT_VERSION,
        scopes={"beta_ack": True, "data_storage": True, "ai_processing": True, "research_use": True},
        signature=member.name, device_name="iPhone (demo)", app_version="1.0",
    )
    for gear in member.gear:
        db.add(Device(
            id=f"dev_{member.id}_{gear.slug}", patient_id=member.id, source_provider=gear.provider,
            device_model=gear.model,
            connected_at=datetime.combine(today - timedelta(days=gear.since), time(20, 30)),
            last_sync_at=datetime.combine(today, gear.synced),
        ))
    db.commit()

    ingest_observations(db, _observations(member, life, today))

    # The morning check-in, answered most mornings through today, and the
    # sessions logged from the app.
    checkin = plan.ensure_checkin(db, patient, profile)
    checkin.created_at = opened
    for i in sorted(life.checkins, reverse=True):
        at = datetime.combine(today - timedelta(days=i), time(7, 2)) + timedelta(minutes=(i * 7) % 23)
        _complete(db, checkin, life.checkins[i], at)
    for i, (minutes, rpe) in life.logged.items():
        day = today - timedelta(days=i)
        record(db, member.id, day, "session_minutes", value=minutes, source="app")
        record(db, member.id, day, "rpe", value=rpe, source="app")
    for member_id, i, text in JOURNAL:
        if member_id == member.id:
            record(db, member.id, today - timedelta(days=i), "note", text=text, source="coach")
    db.commit()

    # The two mornings before today, replayed through the plan writer and
    # the deterministic brief as they stood on those days, then closed the
    # way the member closed them; and the evenings' words with the coach.
    boards: dict[int, dict[str, Any]] = {}
    for i in REPLAYED_MORNINGS:
        day = today - timedelta(days=i)
        boards[i] = _board(db, patient, profile, day)
        written = plan.ensure_daily_plan(db, patient, profile, boards[i], day)
        _said(db, member.id, datetime.combine(day, time(7, 0)),
              insights.fallback_brief(boards[i]["digest"])["brief"], coach=True,
              checkin_task_id=checkin.id)
        for task_id in written["created"]:
            task = db.get(AdherenceTask, task_id)
            task.created_at = datetime.combine(day, time(7, 0))
            answered = _plan_answers(task, life, i)
            if answered is None:
                task.status, task.completed_at, task.completed_via = "skipped", datetime.combine(day, time(21, 0)), "app"
                task.payload = {**(task.payload or {}), "last_done": day.isoformat()}
                db.add(AdherenceRecord(patient_id=member.id, task_id=task.id, date=day,
                                       status=AdherenceStatus.MISSED))
            else:
                _complete(db, task, answered[0], datetime.combine(day, answered[1]))
        db.commit()
    for i, at, asked, answered in THREADS[member.id](boards):
        moment = datetime.combine(today - timedelta(days=i), at)
        _said(db, member.id, moment, asked, coach=False)
        _said(db, member.id, moment + timedelta(seconds=40), answered, coach=True)
    db.commit()

    # This morning, through the product's own morning run: today's plan,
    # the brief on the thread, and the brief and the four deep dives stored
    # with the deterministic renderer so the first read finds them.
    morning = daily.start_day(db, patient, profile, today=today, allow_llm=False, text=False)
    for domain in insights.DOMAINS:
        insights.get_deep_dive(db, patient, profile, morning["dashboard"], domain, allow_llm=False)

    # The clinic engine's read of the same stream: the care section a
    # recovery goal shows, and what the app's first screen asks for.
    from app.engine.pipeline import ensure_current

    ensure_current(db, member.id)

    profile.settings = {MARK: {**(_mark(profile) or {}), "seeded_for": today.isoformat(),
                               "at": datetime.now().isoformat(timespec="seconds")}}
    db.commit()


def seed_personal(db: Session, today: date | None = None) -> list[str]:
    """Create or refresh the demo members, anchored to ``today``; returns
    their patient ids. Idempotent, and never touches a row without the mark."""
    today = today or date.today()
    written: list[str] = []
    for order, member in enumerate(MEMBERS):
        account = _account(db, member, order, today)
        if account is None:
            continue
        patient, profile = account
        _wipe(db, member.id)
        _write(db, member, patient, profile, today)
        written.append(member.id)
    return written


__all__ = ["GOAL_LABELS", "MARK", "MEMBERS", "PASSWORD", "is_showcase", "mark_of", "members",
           "remove_personal", "seed_personal"]
