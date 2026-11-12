"""The MedPull Sports demo: Rice University Athletics with a men's
basketball roster and a women's soccer squad, a handful of other programs
for the picker, and two athletes on their own.

Every athlete here is fictional. Names are invented, emails sit on a demo
domain, and the staff are invented too: nothing in this file imitates a
real person. The organisation names are real places a program could pick
from the list; their rosters are not.

Deterministic: every stream is drawn from numpy generators seeded by the
athlete id, anchored to ``today``, so a reseed reproduces the same numbers
for the same day. Observations go through the same ingest path a wearable
delivery takes.

``seed_sports`` is a refresh, not a rebuild. Run every morning, it rewrites
what a device or a test day would have produced (wearable nights, sessions,
wellness answers, the battery, the rehab measures, the calendar it wrote
itself) around the new day, and leaves what a person did: the athlete's
account and app sign-ins, the thread, an availability the staff set, an
event the staff added. An injury keeps its date for ``STORY_DAYS`` mornings,
so "day 9" reads "day 10" tomorrow, then the story starts over so the board
never runs out of it. ``fresh=True`` is the rebuild.

Log in to any athlete with their email and the password ``owls-2026``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

import numpy as np
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.connectors.base import CanonicalObservation
from app.connectors.ingest import ingest_observations
from app.models.enums import Granularity
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider as SP
from app.models.insight import EstablishedBaseline, Insight, RiskAssessment
from app.models.mobile import Message
from app.models.observation import Observation
from app.models.patient import Device, Patient
from app.models.personal import Consent, PersonalCredential
from app.models.sports import (
    SportsEvent,
    SportsInjury,
    SportsOrg,
    SportsProfile,
    SportsRehabMeasure,
    SportsSession,
    SportsStaff,
    SportsTeam,
    SportsTest,
    SportsWellness,
)
from app.personal import auth
from app.personal.scope import is_sports
from app.sports import identity
from app.sports.catalog.tests import TESTS

PASSWORD = "owls-2026"
EMAIL_DOMAIN = "athletes.medpull.demo"
TZ = "America/Chicago"
DAYS = 60

# ``SportsEvent.source`` for a row this module (or the showcase fill) wrote.
# A refresh replaces those and the rows older than the column; an event the
# staff added carries "staff" and is never touched.
SEEDED = "seed"

# How many mornings an injury keeps its date before the story starts over.
STORY_DAYS = 14
# Days since the injury (the operation, for the ACL) on the story's first day.
STORY_BASE = {"acl": 167, "ankle": 9, "tendon": 24, "hamstring": 17, "tennis_solo": 20, "soccer_solo": 17}

# --- organisations -------------------------------------------------------------------------------------

ORGS = [
    dict(id="rice", name="Rice University Athletics", short_name="Rice", kind="college", city="Houston", state="TX",
         conference="American Conference", level="ncaa_d1", join_code="OWLS26",
         colors={"primary": "#00205B", "secondary": "#C1C6C8"}),
    dict(id="rockets", name="Houston Rockets", short_name="Rockets", kind="pro", city="Houston", state="TX",
         conference="NBA", level="pro", join_code="CLUTCH", colors={"primary": "#CE1141", "secondary": "#000000"}),
    dict(id="dynamo", name="Houston Dynamo FC", short_name="Dynamo", kind="pro", city="Houston", state="TX",
         conference="MLS", level="pro", join_code="FOREVER", colors={"primary": "#F68712", "secondary": "#101820"}),
    dict(id="uh", name="University of Houston Athletics", short_name="Houston", kind="college", city="Houston", state="TX",
         conference="Big 12", level="ncaa_d1", join_code="COOGS", colors={"primary": "#C8102E", "secondary": "#FFFFFF"}),
    dict(id="hcta", name="Houston Court Tennis Academy", short_name="HCTA", kind="academy", city="Houston", state="TX",
         conference=None, level="club", join_code=None, colors={"primary": "#2F6B3A", "secondary": "#F2F2F0"}),
]

TEAMS = [
    dict(id="rice-mbb", org_id="rice", name="Men's Basketball", sport="basketball", sex="M", season="2026-27", phase="preseason"),
    dict(id="rice-wbb", org_id="rice", name="Women's Basketball", sport="basketball", sex="F", season="2026-27", phase="preseason"),
    dict(id="rice-wten", org_id="rice", name="Women's Tennis", sport="tennis", sex="F", season="2026-27", phase="offseason"),
    dict(id="rice-wsoc", org_id="rice", name="Women's Soccer", sport="soccer", sex="F", season="2026", phase="in_season"),
    dict(id="rockets-nba", org_id="rockets", name="Rockets", sport="basketball", sex="M", season="2026-27", phase="preseason"),
    dict(id="dynamo-mls", org_id="dynamo", name="First Team", sport="soccer", sex="M", season="2026", phase="in_season"),
    dict(id="uh-mbb", org_id="uh", name="Men's Basketball", sport="basketball", sex="M", season="2026-27", phase="preseason"),
    dict(id="hcta-elite", org_id="hcta", name="Elite Squad", sport="tennis", sex="mixed", season="2026", phase="in_season"),
]

STAFF = [
    dict(id="st_rice_hc", org_id="rice", team_id="rice-mbb", name="Coach Darnell Whitmore", role="head_coach", athlete_facing=False),
    dict(id="st_rice_sc", org_id="rice", team_id="rice-mbb", name="Tyrese Calloway", role="strength", athlete_facing=True),
    dict(id="st_rice_at", org_id="rice", team_id="rice-mbb", name="Marisol Deng, ATC", role="athletic_trainer", athlete_facing=True),
    dict(id="st_rice_ss", org_id="rice", team_id=None, name="Dr. Hana Okafor", role="sports_scientist", athlete_facing=True),
    dict(id="st_rice_md", org_id="rice", team_id=None, name="Dr. Evan Ruiz-Castillo", role="physician", athlete_facing=True),
    dict(id="st_rice_wsoc_hc", org_id="rice", team_id="rice-wsoc", name="Coach Renata Vasquez", role="head_coach", athlete_facing=False),
    dict(id="st_rice_wsoc_sc", org_id="rice", team_id="rice-wsoc", name="Kiera Malone", role="strength", athlete_facing=True),
    dict(id="st_rice_wsoc_at", org_id="rice", team_id="rice-wsoc", name="Jonah Feldt, ATC", role="athletic_trainer", athlete_facing=True),
    dict(id="st_rockets_ss", org_id="rockets", team_id=None, name="Performance staff", role="sports_scientist", athlete_facing=True),
]


# --- the roster -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AthleteSpec:
    id: str
    name: str
    sport: str
    position: str
    jersey: str | None
    class_year: str | None
    age: int
    sex: str
    height_in: float
    weight_lb: float
    wingspan_in: float | None
    reach_in: float | None
    dominant: str
    device: str                  # apple | whoop | oura | garmin
    # healthy | star | sleep_debt | load_spike | acl | ankle | tendon | hamstring | unwell | fresh | freshman | taper
    scenario: str
    org_id: str | None = "rice"
    team_id: str | None = "rice-mbb"
    starter: bool = False
    athleticism: float = 0.0     # -1..1, shifts the whole battery
    level: str = "ncaa_d1"
    notes: dict[str, Any] = field(default_factory=dict)


ROSTER: list[AthleteSpec] = [
    AthleteSpec("jalen-okoro", "Jalen Okoro", "basketball", "Point guard", "1", "Jr", 21, "M", 74.0, 186, 77.5, 98.0, "right", "whoop", "star", starter=True, athleticism=0.8),
    AthleteSpec("mateo-reyes-vega", "Mateo Reyes-Vega", "basketball", "Guard", "3", "So", 20, "M", 75.5, 192, 79.0, 100.0, "right", "apple", "sleep_debt", starter=True, athleticism=0.4),
    AthleteSpec("devin-marsh", "Devin Marsh", "basketball", "Wing", "11", "Sr", 22, "M", 78.0, 208, 82.0, 104.5, "left", "oura", "load_spike", starter=True, athleticism=0.6),
    AthleteSpec("kwame-asante", "Kwame Asante", "basketball", "Forward", "24", "Jr", 21, "M", 80.0, 224, 85.0, 107.0, "right", "apple", "acl", starter=False, athleticism=0.5),
    AthleteSpec("luka-petrovic", "Luka Petrović", "basketball", "Center", "32", "Sr", 23, "M", 83.0, 246, 88.5, 112.0, "right", "garmin", "healthy", starter=True, athleticism=0.1),
    AthleteSpec("tobias-lindqvist", "Tobias Lindqvist", "basketball", "Forward", "15", "So", 19, "M", 80.5, 216, 84.0, 106.0, "right", "whoop", "ankle", starter=True, athleticism=0.3),
    AthleteSpec("andre-beaumont", "André Beaumont", "basketball", "Wing", "7", "Jr", 21, "M", 77.0, 201, 81.0, 102.5, "right", "apple", "tendon", starter=False, athleticism=0.5),
    AthleteSpec("isaiah-cole", "Isaiah Cole", "basketball", "Guard", "5", "Fr", 18, "M", 73.5, 178, 76.0, 96.5, "left", "apple", "freshman", starter=False, athleticism=-0.2),
    AthleteSpec("ethan-nakamura", "Ethan Nakamura", "basketball", "Guard", "10", "So", 20, "M", 74.5, 184, 77.0, 98.5, "right", "oura", "healthy", starter=False, athleticism=0.2),
    AthleteSpec("samuel-adeyemi", "Samuel Adeyemi", "basketball", "Center", "40", "Jr", 21, "M", 82.0, 238, 87.0, 110.5, "right", "whoop", "unwell", starter=False, athleticism=0.0),
    AthleteSpec("rafael-dossantos", "Rafael dos Santos", "basketball", "Forward", "21", "Fr", 19, "M", 79.0, 212, 83.5, 105.0, "right", "apple", "fresh", starter=False, athleticism=0.3),
    AthleteSpec("caleb-whitfield", "Caleb Whitfield", "basketball", "Wing", "2", "Gr", 24, "M", 77.5, 205, 80.5, 103.0, "right", "garmin", "taper", starter=False, athleticism=0.4),
    AthleteSpec("noah-brennan", "Noah Brennan", "basketball", "Point guard", "0", "Fr", 18, "M", 72.5, 172, 74.5, 95.0, "right", "apple", "healthy", starter=False, athleticism=-0.4),
    # Women's soccer, in season: a hamstring coming back, a week of short
    # nights, a week of too much running, an illness, and four who are fine.
    AthleteSpec("camila-ortega", "Camila Ortega", "soccer", "Forward", "9", "Sr", 21, "F", 66.0, 134, None, None, "right", "whoop", "star",
                team_id="rice-wsoc", starter=True, athleticism=0.7),
    AthleteSpec("brooke-halvorsen", "Brooke Halvorsen", "soccer", "Winger", "11", "Jr", 20, "F", 65.0, 128, None, None, "left", "garmin", "hamstring",
                team_id="rice-wsoc", starter=True, athleticism=0.6),
    AthleteSpec("naomi-adebayo", "Naomi Adebayo", "soccer", "Central midfielder", "8", "So", 19, "F", 64.5, 126, None, None, "right", "apple", "sleep_debt",
                team_id="rice-wsoc", starter=True, athleticism=0.3),
    AthleteSpec("sienna-park", "Sienna Park", "soccer", "Full back", "3", "Jr", 20, "F", 63.5, 122, None, None, "right", "oura", "load_spike",
                team_id="rice-wsoc", starter=True, athleticism=0.4),
    AthleteSpec("freya-lindholm", "Freya Lindholm", "soccer", "Goalkeeper", "1", "Sr", 22, "F", 70.0, 152, None, None, "right", "apple", "healthy",
                team_id="rice-wsoc", starter=True, athleticism=0.2),
    AthleteSpec("imani-brooks", "Imani Brooks", "soccer", "Center back", "5", "Gr", 23, "F", 68.5, 146, None, None, "right", "whoop", "unwell",
                team_id="rice-wsoc", starter=True, athleticism=0.1),
    AthleteSpec("valentina-cruz", "Valentina Cruz", "soccer", "Attacking midfielder", "10", "So", 19, "F", 63.0, 118, None, None, "left", "apple", "healthy",
                team_id="rice-wsoc", starter=True, athleticism=0.5),
    AthleteSpec("harper-nguyen", "Harper Nguyen", "soccer", "Defensive midfielder", "6", "Fr", 18, "F", 65.5, 130, None, None, "right", "garmin", "freshman",
                team_id="rice-wsoc", starter=False, athleticism=-0.2),
    # On their own: no program, a club level, their own devices.
    AthleteSpec("sloane-whitaker", "Sloane Whitaker", "tennis", "Singles", None, None, 26, "F", 68.0, 141, None, None, "right", "apple", "tennis_solo",
                org_id=None, team_id=None, level="club", athleticism=0.3),
    AthleteSpec("kofi-mensah", "Kofi Mensah", "soccer", "Winger", None, None, 24, "M", 70.0, 163, None, None, "right", "garmin", "soccer_solo",
                org_id=None, team_id=None, level="club", athleticism=0.5),
]


def _rng(athlete_id: str, salt: str) -> np.random.Generator:
    digest = hashlib.sha256(f"{athlete_id}:{salt}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def _email(spec: AthleteSpec) -> str:
    local = spec.id.replace("-", ".")
    return f"{local}@{EMAIL_DOMAIN}"


# --- calendar --------------------------------------------------------------------------------------------


def rice_schedule(today: date) -> list[dict[str, Any]]:
    """Six weeks back and three forward: practices Monday to Friday with a
    lift on Monday and Thursday, scrimmages on two Saturdays, an exhibition
    next Saturday and the opener a fortnight after it, Sunday off."""
    out: list[dict[str, Any]] = []
    start = today - timedelta(days=42)
    opponents = ["Gulf Coast", "Bayou State", "Hill Country", "Prairie View A&M", "Lone Star Tech"]
    scrim_days = {today - timedelta(days=9), today - timedelta(days=2)}
    exhibition = today + timedelta(days=5)
    opener = today + timedelta(days=16)
    k = 0
    for i in range(42 + 22):
        d = start + timedelta(days=i)
        wd = d.weekday()
        if d in scrim_days:
            out.append(dict(date=d, kind="game", title="Scrimmage", opponent=opponents[k % len(opponents)], home=(k % 2 == 0),
                            start_time="14:00", location="Tudor Fieldhouse" if k % 2 == 0 else "Away"))
            k += 1
            continue
        if d == exhibition:
            out.append(dict(date=d, kind="game", title="Exhibition", opponent=opponents[3], home=True, start_time="19:00",
                            location="Tudor Fieldhouse"))
            continue
        if d == opener:
            out.append(dict(date=d, kind="game", title="Season opener", opponent=opponents[4], home=True, start_time="19:30",
                            location="Tudor Fieldhouse"))
            continue
        if d == opener + timedelta(days=3):
            out.append(dict(date=d - timedelta(days=1), kind="travel", title="Travel to Denver", home=False, start_time="15:00"))
            out.append(dict(date=d, kind="game", title="Road game", opponent="Front Range", home=False, start_time="20:00", location="Away"))
            continue
        if wd == 6:
            continue
        if wd in (0, 3):
            out.append(dict(date=d, kind="lift", title="Lift", start_time="07:00", location="Patterson Center"))
        if wd == 5:
            out.append(dict(date=d, kind="shootaround", title="Shootaround", start_time="10:00", location="Tudor Fieldhouse"))
        else:
            out.append(dict(date=d, kind="practice", title="Practice", start_time="15:30", location="Tudor Fieldhouse"))
    return out


def wsoc_schedule(today: date) -> list[dict[str, Any]]:
    """Six weeks back and three forward, in season: a match on Thursday and
    on Sunday, training on Tuesday (with a lift), Wednesday and Saturday,
    a recovery session the morning after Thursday's match, Monday off. The
    squad travels the day before an away Sunday."""
    out: list[dict[str, Any]] = []
    opponents = ["Gulf Coast", "Bayou State", "Hill Country", "Lone Star Tech", "Piney Woods", "Red River State",
                 "Coastal Bend", "Trinity Valley"]
    # Weeks are counted from a fixed Monday so an opponent keeps its date as
    # the days go by.
    epoch = date(2026, 1, 5)
    for i in range(-42, 22):
        d = today + timedelta(days=i)
        wd = d.weekday()
        week = (d - epoch).days // 7
        if wd == 3:
            out.append(dict(date=d, kind="game", title="Match", opponent=opponents[(2 * week) % len(opponents)], home=True,
                            start_time="19:00", location="Holloway Field"))
        elif wd == 6:
            home = week % 2 == 0
            out.append(dict(date=d, kind="game", title="Match", opponent=opponents[(2 * week + 1) % len(opponents)], home=home,
                            start_time="13:00", location="Holloway Field" if home else "Away"))
        elif wd == 1:
            out.append(dict(date=d, kind="lift", title="Lift", start_time="07:30", location="Patterson Center"))
            out.append(dict(date=d, kind="practice", title="Training", start_time="15:00", location="Holloway Field"))
        elif wd == 2:
            out.append(dict(date=d, kind="practice", title="Training", start_time="15:00", location="Holloway Field"))
        elif wd == 4:
            out.append(dict(date=d, kind="recovery", title="Recovery session", start_time="10:00", location="Patterson Center"))
        elif wd == 5:
            away = week % 2 == 1
            out.append(dict(date=d, kind="practice", title="Training", start_time="09:30", location="Holloway Field"))
            if away and d > today:
                out.append(dict(date=d, kind="travel", title=f"Travel to {opponents[(2 * week + 1) % len(opponents)]}",
                                home=False, start_time="14:00"))
    return out


# --- streams ------------------------------------------------------------------------------------------------


def _baseline(spec: AthleteSpec) -> dict[str, float]:
    r = _rng(spec.id, "baseline")
    big = spec.height_in >= 80
    return {
        "hrv": float(r.uniform(58, 92) - (8 if big else 0)),
        "rhr": float(r.uniform(46, 56) + (3 if big else 0)),
        "sleep": float(r.uniform(7.2, 8.1)),
        "rr": float(r.uniform(13.0, 15.5)),
        "temp": float(r.uniform(36.3, 36.6)),
        "spo2": float(r.uniform(96.5, 98.3)),
        "steps": float(r.uniform(8500, 12500)),
        "bed_h": float(r.uniform(22.8, 23.9)),  # bedtime hour, local
    }


def _wearable_rows(spec: AthleteSpec, pid: str, today: date, events: list[dict[str, Any]],
                   story_day: int = 0) -> list[CanonicalObservation]:
    r = _rng(spec.id, "stream")
    base = _baseline(spec)
    provider = {"apple": SP.APPLE, "whoop": SP.WHOOP, "oura": SP.OURA, "garmin": SP.GARMIN}[spec.device]
    device_id = f"{spec.device}:{pid}"
    game_days = {e["date"] for e in events if e["kind"] == "game"}
    rows: list[CanonicalObservation] = []
    for i in range(DAYS, -1, -1):
        d = today - timedelta(days=i)
        hrv = base["hrv"] * (1 + r.normal(0, 0.07))
        rhr = base["rhr"] + r.normal(0, 1.4)
        sleep = base["sleep"] + r.normal(0, 0.45)
        rr = base["rr"] + r.normal(0, 0.45)
        temp = base["temp"] + r.normal(0, 0.09)
        spo2 = base["spo2"] + r.normal(0, 0.35)
        steps = base["steps"] * (1 + r.normal(0, 0.15))
        bed = base["bed_h"] + r.normal(0, 0.35)
        # A game the night before: later bedtime, a touch less sleep, HRV a little down next morning.
        if (d - timedelta(days=1)) in game_days:
            bed += 0.9
            sleep -= 0.6
            hrv *= 0.94
            rhr += 1.5
        # Weekends run later.
        if d.weekday() in (4, 5):
            bed += 0.5
        s = spec.scenario
        if s == "sleep_debt" and i <= 10:
            sleep = 5.4 + r.normal(0, 0.35)
            bed += 1.6
            hrv *= 0.84 - 0.01 * (10 - i)
            rhr += 3.5 + 0.2 * (10 - i)
        if s == "load_spike" and i <= 6:
            hrv *= 0.9
            rhr += 2.5
        if s == "unwell" and i <= 2:
            temp += 0.65
            rr += 2.2
            rhr += 6.5
            hrv *= 0.78
        if s in ("fresh", "taper") and i <= 5:
            hrv *= 1.08
            rhr -= 1.5
            sleep += 0.4
        if s == "star":
            sleep += 0.3
            hrv *= 1.03
        if s == "acl":
            steps *= 0.55
        if s == "ankle" and i <= STORY_BASE["ankle"] + story_day:
            steps *= 0.6
        if s == "hamstring" and 0 <= STORY_BASE["hamstring"] + story_day - i <= 10:
            steps *= 0.7
        bed_start = datetime.combine(d - timedelta(days=1), time(0, 0)) + timedelta(hours=bed)
        wake = bed_start + timedelta(hours=sleep + 0.55)
        stages = {"deep": round(sleep * 0.21, 2), "rem": round(sleep * 0.23, 2), "light": round(sleep * 0.49, 2),
                  "awake": round(sleep * 0.07, 2), "bedtime_start": bed_start.isoformat(), "bedtime_stop": wake.isoformat(),
                  "efficiency": round(float(np.clip(0.9 + r.normal(0, 0.03), 0.72, 0.98)), 3)}
        energy = steps * 0.045 + (420 if d in game_days else 280 if d.weekday() < 5 else 120) + r.normal(0, 60)
        for metric, value, unit, vjson in (
            (M.HRV_RMSSD, hrv, "ms", None), (M.RESTING_HR, rhr, "bpm", None), (M.SLEEP_DURATION, sleep, "h", None),
            (M.SLEEP_STAGES, sleep, "h", stages), (M.STEPS, steps, "count", None),
            (M.ACTIVE_ENERGY, energy, "kcal", None), (M.RESPIRATORY_RATE, rr, "breaths/min", None),
            (M.SKIN_TEMP, temp, "degC", None), (M.SPO2, spo2, "%", None),
        ):
            rows.append(CanonicalObservation(
                patient_id=pid, source_provider=provider, metric_type=metric, unit=unit,
                value_num=round(float(value), 3), value_json=vjson,
                start_time=datetime.combine(d, time(0, 0)), end_time=datetime.combine(d, time(23, 59, 59)),
                granularity=Granularity.DAILY_SUMMARY, source_device_id=device_id, timezone=TZ,
            ))
    return rows


def _sessions(spec: AthleteSpec, pid: str, today: date, events: list[dict[str, Any]],
              story_day: int = 0) -> list[SportsSession]:
    if spec.sport == "soccer" and spec.team_id:
        return _soccer_sessions(spec, pid, today, events, story_day)
    r = _rng(spec.id, "sessions")
    out = []
    s = spec.scenario
    for e in events:
        d = e["date"]
        if d > today:
            continue
        kind = e["kind"]
        if kind not in ("practice", "game", "lift", "shootaround"):
            continue
        if s == "acl":
            # Rehab and lifts carry their load like any session (minutes × RPE),
            # so the team's load figure counts them the way the athlete's card does.
            if kind in ("practice", "game", "shootaround"):
                minutes = float(r.uniform(55, 75))
                rpe = float(r.integers(4, 6))
                out.append(SportsSession(patient_id=pid, date=d, kind="rehab", minutes=minutes, rpe=rpe,
                                         load_au=round(minutes * rpe, 1), source="manual"))
            else:
                out.append(SportsSession(patient_id=pid, date=d, kind="lift", minutes=45.0, rpe=5.0, load_au=225.0,
                                         source="manual"))
            continue
        if s == "ankle":
            # Days since the sprain: nothing for the first five, the rehab
            # block after that, no practice until the staff say so.
            since = STORY_BASE["ankle"] + story_day - (today - d).days
            if since >= 0:
                if since >= 5 and kind in ("practice", "lift"):
                    out.append(SportsSession(patient_id=pid, date=d, kind="rehab", minutes=40.0, rpe=3.0, load_au=120.0,
                                             source="manual"))
                continue
        if kind == "practice":
            minutes = float(r.normal(112, 6))
            rpe = float(np.clip(round(r.normal(6.8, 0.5)), 3, 10))
            jumps = int(r.normal(88, 18))
            pl = float(r.normal(520, 55))
        elif kind == "game":
            minutes = float(r.normal(34, 5)) if spec.starter else float(r.normal(16, 6))
            minutes = max(6.0, minutes)
            rpe = float(np.clip(round(r.normal(8.4, 0.6)), 5, 10))
            jumps = int(minutes * r.normal(1.9, 0.3))
            pl = float(minutes * r.normal(11.0, 1.2))
        elif kind == "lift":
            minutes = float(r.normal(52, 6))
            rpe = float(np.clip(round(r.normal(5.5, 0.8)), 3, 9))
            jumps = 0
            pl = None
        else:  # shootaround
            minutes = float(r.normal(48, 6))
            rpe = float(np.clip(round(r.normal(3.2, 0.6)), 1, 6))
            jumps = int(r.normal(28, 8))
            pl = float(r.normal(140, 25))
        if s == "load_spike" and (today - d).days <= 7:
            minutes *= 1.18
            rpe = min(10.0, rpe + 0.5)
            jumps = int(jumps * 1.35)
            if pl:
                pl *= 1.2
        if s == "tendon":
            jumps = int(jumps * 0.7)
        if s == "taper" and (today - d).days <= 7:
            minutes *= 0.7
            jumps = int(jumps * 0.6)
        if s == "unwell" and (today - d).days <= 1:
            continue
        for _ in range(1):
            out.append(SportsSession(patient_id=pid, date=d, kind=kind, minutes=round(minutes, 1), rpe=rpe,
                                     load_au=round(minutes * rpe, 1), jumps=max(0, jumps),
                                     player_load=round(pl, 1) if pl else None,
                                     source="catapult" if kind != "lift" else "manual"))
        if s == "load_spike" and (today - d).days <= 7 and kind == "practice":
            out.append(SportsSession(patient_id=pid, date=d, kind="conditioning", minutes=25.0, rpe=7.0, load_au=175.0,
                                     jumps=0, source="manual", note="Extra conditioning after practice"))
    return out


def _soccer_sessions(spec: AthleteSpec, pid: str, today: date, events: list[dict[str, Any]],
                     story_day: int = 0) -> list[SportsSession]:
    """A soccer squad's sessions as the GPS units report them: distance,
    high-speed running and top speed beside minutes and RPE. The day before
    a match is short and light; a goalkeeper covers half the ground."""
    r = _rng(spec.id, "sessions")
    out: list[SportsSession] = []
    s = spec.scenario
    keeper = spec.position == "Goalkeeper"
    peak_kmh = 28.0 + 2.0 * spec.athleticism
    match_days = {e["date"] for e in events if e["kind"] == "game"}
    strained_on = today - timedelta(days=STORY_BASE["hamstring"] + story_day) if s == "hamstring" else None
    for e in events:
        d, kind = e["date"], e["kind"]
        if d > today or kind not in ("practice", "game", "lift", "recovery"):
            continue
        ago = (today - d).days
        if strained_on is not None and d >= strained_on:
            # The strain: five quiet days, a rehab block, then running on her
            # own beside the squad with the top speed stepping up.
            since = (d - strained_on).days
            if since < 5:
                continue
            if kind == "lift":
                out.append(SportsSession(patient_id=pid, date=d, kind="lift", minutes=40.0, rpe=5.0, load_au=200.0,
                                         source="manual", note="Upper body and trunk"))
            elif kind in ("practice", "game") and since < 11:
                out.append(SportsSession(patient_id=pid, date=d, kind="rehab", minutes=45.0, rpe=4.0, load_au=180.0,
                                         source="manual", note="Hamstring block: Nordics, extenders, bike"))
            elif kind in ("practice", "game"):
                share = min(0.93, 0.84 + 0.01 * (since - 11))
                out.append(SportsSession(patient_id=pid, date=d, kind="individual", minutes=50.0, rpe=5.0, load_au=250.0,
                                         distance_m=4200.0, high_speed_m=round(180.0 + 12.0 * (since - 11), 0),
                                         max_speed_kmh=round(peak_kmh * share, 1), source="statsports",
                                         note="Return to running beside the squad"))
            continue
        if s == "unwell" and ago <= 1:
            continue
        light = (d + timedelta(days=1)) in match_days
        metres_per_min = sprint_per_min = top_share = None
        if kind == "practice":
            minutes = float(r.normal(58, 5)) if light else float(r.normal(84, 6))
            rpe = float(np.clip(round(r.normal(4.2, 0.5) if light else r.normal(6.4, 0.6)), 2, 10))
            metres_per_min = float(r.normal(68, 5)) if light else float(r.normal(78, 6))
            sprint_per_min = float(r.normal(3.2, 0.8)) if light else float(r.normal(6.0, 1.2))
            top_share = float(np.clip(r.normal(0.90, 0.03), 0.8, 1.0))
        elif kind == "game":
            minutes = float(np.clip(r.normal(86, 6), 45, 96)) if spec.starter else float(np.clip(r.normal(26, 10), 8, 60))
            rpe = float(np.clip(round(r.normal(8.6, 0.5)), 6, 10))
            metres_per_min = float(r.normal(112, 6))
            sprint_per_min = float(r.normal(8.8, 1.4))
            top_share = float(np.clip(r.normal(0.98, 0.015), 0.9, 1.0))
        elif kind == "lift":
            minutes = float(r.normal(46, 5))
            rpe = float(np.clip(round(r.normal(5.2, 0.8)), 3, 9))
        else:  # recovery
            minutes = float(r.normal(34, 4))
            rpe = float(np.clip(round(r.normal(2.2, 0.5)), 1, 4))
            metres_per_min = float(r.normal(48, 5))
            sprint_per_min = 0.0
        if s == "load_spike" and ago <= 7:
            minutes *= 1.15
            rpe = min(10.0, rpe + 0.5)
            if sprint_per_min:
                sprint_per_min *= 1.45
            if metres_per_min:
                metres_per_min *= 1.08
        if keeper and metres_per_min is not None:
            metres_per_min *= 0.5
            sprint_per_min = (sprint_per_min or 0.0) * 0.12
        distance = round(minutes * metres_per_min, 0) if metres_per_min is not None else None
        out.append(SportsSession(
            patient_id=pid, date=d, kind=kind, minutes=round(minutes, 1), rpe=rpe, load_au=round(minutes * rpe, 1),
            distance_m=distance,
            high_speed_m=round(minutes * max(sprint_per_min, 0.0), 0) if sprint_per_min is not None else None,
            max_speed_kmh=round(peak_kmh * top_share, 1) if top_share is not None else None,
            player_load=round(distance * 0.068, 1) if distance is not None else None,
            source="statsports" if metres_per_min is not None else "manual"))
        if s == "load_spike" and ago <= 7 and kind == "practice":
            out.append(SportsSession(patient_id=pid, date=d, kind="conditioning", minutes=25.0, rpe=7.0, load_au=175.0,
                                     distance_m=3400.0, high_speed_m=420.0, source="statsports",
                                     note="Extra running after training"))
    return out


def _wellness(spec: AthleteSpec, pid: str, today: date, sessions: list[SportsSession],
              story_day: int = 0) -> list[SportsWellness]:
    r = _rng(spec.id, "wellness")
    load_by_day: dict[date, float] = {}
    for s in sessions:
        load_by_day[s.date] = load_by_day.get(s.date, 0.0) + (s.load_au or 0.0)
    out = []
    sc = spec.scenario
    for i in range(45, -1, -1):
        d = today - timedelta(days=i)
        # Two days a fortnight go unanswered, like a real roster.
        if r.random() < 0.08 and i != 0:
            continue
        yest = load_by_day.get(d - timedelta(days=1), 0.0)
        heavy = yest > 700
        sleep_q = float(np.clip(r.normal(7.2, 1.1) - (0.8 if heavy else 0), 0, 10))
        fatigue = float(np.clip(r.normal(3.4, 1.2) + (1.6 if heavy else 0), 0, 10))
        soreness = float(np.clip(r.normal(3.2, 1.2) + (2.0 if heavy else 0), 0, 10))
        stress = float(np.clip(r.normal(3.0, 1.3), 0, 10))
        mood = float(np.clip(r.normal(7.3, 1.0), 0, 10))
        pain = 0.0
        hydration = float(np.clip(round(r.normal(2.6, 0.9)), 1, 8))
        if sc == "sleep_debt" and i <= 10:
            sleep_q = float(np.clip(r.normal(3.6, 0.9), 0, 10))
            fatigue = float(np.clip(r.normal(7.2, 0.8), 0, 10))
            stress = float(np.clip(r.normal(6.8, 1.0), 0, 10))
            mood = float(np.clip(r.normal(4.6, 0.9), 0, 10))
        if sc == "load_spike" and i <= 6:
            soreness = float(np.clip(r.normal(7.0, 0.8), 0, 10))
            fatigue = float(np.clip(r.normal(6.4, 0.8), 0, 10))
        if sc == "unwell" and i <= 2:
            fatigue = float(np.clip(r.normal(7.5, 0.6), 0, 10))
            mood = 4.0
            out.append(SportsWellness(patient_id=pid, date=d, key="illness", value=1.0, source="app"))
        if sc == "acl":
            pain = float(np.clip(r.normal(1.4, 0.8), 0, 10))
        if sc in ("ankle", "hamstring"):
            # Days since the injury on this morning: the pain she or he
            # reports eases as they add up.
            since = STORY_BASE[sc] + story_day - i
            if since >= 0 and sc == "ankle":
                pain = float(np.clip(6.5 - 0.4 * since + r.normal(0, 0.4), 1, 10))
            elif since >= 0:
                pain = float(np.clip(5.5 - 0.3 * since + r.normal(0, 0.4), 0, 10))
        if sc == "tendon":
            pain = float(np.clip(r.normal(3.0, 0.8), 0, 10))
        if sc in ("fresh", "taper", "star") and i <= 5:
            fatigue = float(np.clip(r.normal(2.0, 0.8), 0, 10))
            sleep_q = float(np.clip(r.normal(8.2, 0.7), 0, 10))
        for key, value in (("sleep_quality", sleep_q), ("fatigue", fatigue), ("soreness", soreness), ("stress", stress),
                           ("mood", mood), ("pain", pain), ("hydration", hydration)):
            out.append(SportsWellness(patient_id=pid, date=d, key=key, value=round(value, 1), source="app"))
        if d.weekday() == 0 or (sc == "unwell" and i <= 2):
            kg = spec.weight_lb * 0.4536 * (1 + r.normal(0, 0.004)) * (0.975 if sc == "unwell" and i <= 1 else 1.0)
            out.append(SportsWellness(patient_id=pid, date=d, key="body_mass_kg", value=round(kg, 1), source="app"))
    if sc == "sleep_debt":
        text = ("Two exams and a paper due this week. About five hours a night." if spec.sport == "soccer"
                else "Midterms this week. Two all-nighters.")
        out.append(SportsWellness(patient_id=pid, date=today, key="note", text=text, source="app"))
    if sc == "hamstring":
        out.append(SportsWellness(patient_id=pid, date=today - timedelta(days=1), key="note",
                                  text="Hamstring was fine on the runs. A little tight this morning, gone after the warm-up.",
                                  source="app"))
    if sc == "tendon":
        out.append(SportsWellness(patient_id=pid, date=today - timedelta(days=1), key="note",
                                  text="Left knee stiff on the stairs this morning, settled by lunch.", source="app"))
    return out


def _tests(spec: AthleteSpec, pid: str, today: date) -> list[SportsTest]:
    r = _rng(spec.id, "tests")
    a = spec.athleticism
    out: list[SportsTest] = []
    big = spec.height_in >= 80
    lvl = spec.level
    sex = spec.sex

    def val(key: str, shift: float = 0.0) -> float:
        """A value for this athlete, placed on the benchmark by athleticism."""
        spec_t = TESTS[key]
        from app.sports.catalog.tests import benchmark_for
        row, _ = benchmark_for(spec_t, lvl, sex)
        if row is None:
            return 0.0
        p25, p50, p75, p90 = row
        pos = 0.5 + 0.45 * (a + shift) + r.normal(0, 0.08)
        pos = float(np.clip(pos, 0.0, 1.0))
        # Interpolate across the row as if the percentiles were evenly spaced.
        pts = [p25, p50, p75, p90]
        idx = pos * 3
        lo = int(np.floor(idx))
        hi = min(lo + 1, 3)
        frac = idx - lo
        return float(pts[lo] + (pts[hi] - pts[lo]) * frac)

    battery_day = today - timedelta(days=35)

    def add(key: str, value: float, side: str | None = None, d: date | None = None, source: str = "staff", device: str | None = None) -> None:
        t = TESTS[key]
        out.append(SportsTest(patient_id=pid, date=d or battery_day, test_key=key, value=round(value, t.decimals),
                              unit=t.unit, side=side, source=source, device=device))

    def weekly_jumps(shift: float) -> None:
        """Countermovement jumps on the force plate, Mondays, nine weeks."""
        cmj_base = val("cmj_height", shift)
        rsi_base = val("cmj_rsi_mod")
        tto_base = val("cmj_time_to_takeoff")
        power_base = val("cmj_peak_power_rel")
        for w in range(8, -1, -1):
            d = today - timedelta(days=w * 7 + (today.weekday() - 0) % 7)
            if d > today:
                continue
            f = 1 + r.normal(0, 0.025)
            tf = 1 + r.normal(0, 0.03)
            if spec.scenario == "load_spike" and w <= 1:
                f *= 0.90 - 0.02 * (1 - w)
                tf *= 1.12
            if spec.scenario in ("fresh", "taper") and w == 0:
                f *= 1.06
                tf *= 0.95
            if spec.scenario == "star" and w == 0:
                # The star is peaking: the latest jump sits above the baseline
                # whatever the noise draws, so the read is "Fresh".
                f *= 1.03
                tf *= 0.96
            if spec.scenario == "sleep_debt" and w == 0:
                f *= 0.95
                tf *= 1.06
            if spec.scenario == "acl":
                continue
            add("cmj_height", cmj_base * f, d=d, source="force_plate", device="Hawkin Dynamics")
            add("cmj_rsi_mod", rsi_base * f * (1 / tf), d=d, source="force_plate", device="Hawkin Dynamics")
            add("cmj_time_to_takeoff", tto_base * tf, d=d, source="force_plate", device="Hawkin Dynamics")
            add("cmj_peak_power_rel", power_base * f, d=d, source="force_plate", device="Hawkin Dynamics")
            add("cmj_asymmetry", abs(r.normal(4.5 if spec.scenario != "tendon" else 9.0, 1.8)), d=d, source="force_plate", device="Hawkin Dynamics")

    def pair(key: str, device: str | None = None, source: str = "staff") -> None:
        """A sided test with the small everyday edge a dominant leg has."""
        v = val(key)
        t = TESTS[key]
        other = "left" if spec.dominant == "right" else "right"
        gap = 1 - abs(r.normal(0.025, 0.012))
        add(key, v, side=spec.dominant, device=device, source=source)
        add(key, v * gap if t.higher_is_better else v / gap, side=other, device=device, source=source)

    if spec.sport == "basketball":
        # Anthropometrics
        add("height", spec.height_in * 2.54)
        add("body_mass", spec.weight_lb * 0.4536)
        if spec.wingspan_in:
            add("wingspan", spec.wingspan_in * 2.54)
        if spec.reach_in:
            add("standing_reach", spec.reach_in * 2.54)
        add("hand_length", 21.5 + (1.2 if big else 0) + r.normal(0, 0.4))
        add("hand_width", 23.0 + (1.5 if big else 0) + r.normal(0, 0.5))
        add("body_fat_pct", val("body_fat_pct", -0.1 if big else 0.1), source="staff", device="InBody 770")
        # Combine battery
        add("vertical_jump_standing", val("vertical_jump_standing", -0.1 if big else 0.1), device="Vertec")
        add("vertical_jump_max", val("vertical_jump_max", -0.1 if big else 0.1), device="Vertec")
        add("lane_agility", val("lane_agility", -0.15 if big else 0.05), device="Timing gates")
        add("shuttle_run_combine", val("shuttle_run_combine", -0.1 if big else 0.05), device="Timing gates")
        add("sprint_3q_court", val("sprint_3q_court", -0.15 if big else 0.05), device="Timing gates")
        add("sprint_10m", val("sprint_10m"), device="Timing gates")
        add("sprint_20m", val("sprint_20m"), device="Timing gates")
        base_pa = val("pro_agility_5_10_5")
        add("pro_agility_5_10_5", base_pa, side="left", device="Timing gates")
        add("pro_agility_5_10_5", base_pa * (1 + r.normal(0.02, 0.015)), side="right", device="Timing gates")
        base_505 = val("cod_505")
        add("cod_505", base_505, side="left", device="Timing gates")
        add("cod_505", base_505 * (1 + r.normal(0.02, 0.015)), side="right", device="Timing gates")
        add("broad_jump", val("broad_jump"))
        add("bench_press_185_reps", max(0.0, val("bench_press_185_reps", 0.2 if big else -0.1)))
        add("trap_bar_deadlift_rel", val("trap_bar_deadlift_rel"))
        add("squat_1rm_rel", val("squat_1rm_rel", -0.15 if big else 0.0))
        add("imtp_peak_force_rel", val("imtp_peak_force_rel"), device="Hawkin Dynamics")
        add("drop_jump_rsi", val("drop_jump_rsi"), device="Hawkin Dynamics")
        add("yoyo_ir1", val("yoyo_ir1", -0.3 if big else 0.1))
        add("ift_30_15", val("ift_30_15", -0.25 if big else 0.1))
        add("suicides_17s", val("suicides_17s", -0.3 if big else 0.1))
        add("reaction_time", val("reaction_time"), source="phone", device="iPhone")
        add("free_throw_pct", val("free_throw_pct"), source="staff", device="Noah")
        add("shooting_pct_3pt", val("shooting_pct_3pt", -0.2 if big else 0.0), source="staff", device="Noah")
        # Sided strength and mobility: a dominant-side edge, and a scenario asymmetry.
        def sided(key: str, asym: float = 0.0, device: str | None = None, shift: float = 0.0,
                  source: str = "staff") -> None:
            v = val(key, shift)
            t = TESTS[key]
            weak = "left" if spec.dominant == "right" else "right"
            dom_edge = 1 + r.normal(0.03, 0.015)
            edge = dom_edge * (1 + asym)
            for side in ("left", "right"):
                if t.higher_is_better:
                    value = v * (edge if side == spec.dominant else 1.0 / (1 + asym) if side == weak else 1.0)
                else:
                    value = v * (1.0 / edge if side == spec.dominant else (1 + asym) if side == weak else 1.0)
                if side == weak and asym == 0:
                    value = value * (1 + r.normal(0, 0.02))
                add(key, value, side=side, device=device, source=source)
        sided("nordic_hamstring_force", device="VALD NordBord")
        sided("hip_adduction_force", device="VALD ForceFrame")
        sided("hip_abduction_force", device="VALD ForceFrame")
        sided("knee_extension_iso", asym=(0.22 if spec.scenario == "acl" else 0.0), device="VALD DynaMo")
        sided("knee_flexion_iso", asym=(0.12 if spec.scenario == "acl" else 0.0), device="VALD DynaMo")
        sided("ankle_dorsiflexion_ktw", asym=(0.25 if spec.scenario == "ankle" else 0.0), source="phone", device="iPhone")
        sided("y_balance_composite", asym=(0.06 if spec.scenario in ("ankle", "acl") else 0.0))
        sided("single_leg_balance", asym=(0.4 if spec.scenario == "ankle" else 0.0), source="phone", device="iPhone")
        sided("hop_single_distance", asym=(0.18 if spec.scenario == "acl" else 0.0))
        sided("calf_raise_reps", asym=(0.1 if spec.scenario == "ankle" else 0.0))
        sided("grip_strength")
        weekly_jumps(-0.05 if big else 0.05)
        if spec.scenario == "acl":
            # The single-leg jump on the phone, both legs, fortnightly: the symmetry climbing.
            for k in range(5, -1, -1):
                d = today - timedelta(days=k * 14)
                good = 17.5 + r.normal(0, 0.6)
                lsi = 0.62 + 0.05 * (5 - k)
                side_inv = "left"
                add("single_leg_cmj", good, side="right", d=d, source="phone", device="iPhone")
                add("single_leg_cmj", good * lsi, side=side_inv, d=d, source="phone", device="iPhone")
    elif spec.sport == "tennis":
        add("height", spec.height_in * 2.54)
        add("body_mass", spec.weight_lb * 0.4536)
        add("serve_speed", val("serve_speed"), device="Radar")
        add("spider_test", val("spider_test"))
        add("hexagon", val("hexagon"))
        add("sprint_20m", val("sprint_20m"))
        add("cmj_height", val("cmj_height"), source="phone", device="iPhone")
        add("medball_overhead_throw", val("medball_overhead_throw"))
        v = val("medball_rotational_throw")
        add("medball_rotational_throw", v, side="right")
        add("medball_rotational_throw", v * 0.9, side="left")
        g = val("grip_strength")
        add("grip_strength", g, side="right")
        add("grip_strength", g * 0.88, side="left")
        ir = val("shoulder_ir_rom")
        add("shoulder_ir_rom", ir * 0.72, side="right", source="phone", device="iPhone")
        add("shoulder_ir_rom", ir, side="left", source="phone", device="iPhone")
        add("shoulder_er_ir_ratio", 0.62, side="right")
        add("shoulder_er_ir_ratio", 0.74, side="left")
        add("yoyo_ir1", val("yoyo_ir1"))
        add("reaction_time", val("reaction_time"), source="phone", device="iPhone")
    elif spec.team_id:
        # A soccer squad's preseason battery: gates, GPS, the NordBord and the
        # force frame, the phone for range and balance, then the weekly jump.
        keeper = spec.position == "Goalkeeper"
        add("height", spec.height_in * 2.54)
        add("body_mass", spec.weight_lb * 0.4536)
        add("body_fat_pct", val("body_fat_pct"), device="InBody 770")
        add("sprint_10m", val("sprint_10m"), device="Timing gates")
        add("sprint_30m", val("sprint_30m"), device="Timing gates")
        add("max_speed", val("max_speed"), device="STATSports Apex")
        add("yoyo_ir1", val("yoyo_ir1", -0.3 if keeper else 0.1))
        add("yoyo_ir2", val("yoyo_ir2", -0.3 if keeper else 0.0))
        add("ift_30_15", val("ift_30_15", -0.2 if keeper else 0.1))
        add("broad_jump", val("broad_jump"))
        add("squat_1rm_rel", val("squat_1rm_rel"))
        add("trap_bar_deadlift_rel", val("trap_bar_deadlift_rel"))
        add("imtp_peak_force_rel", val("imtp_peak_force_rel"), device="Hawkin Dynamics")
        add("reaction_time", val("reaction_time", 0.2 if keeper else 0.0), source="phone", device="iPhone")
        pair("pro_agility_5_10_5", device="Timing gates")
        pair("arrowhead", device="Timing gates")
        pair("nordic_hamstring_force", device="VALD NordBord")
        pair("hip_adduction_force", device="VALD ForceFrame")
        pair("hip_abduction_force", device="VALD ForceFrame")
        pair("knee_extension_iso", device="VALD DynaMo")
        pair("hamstring_ake", source="phone", device="iPhone")
        pair("ankle_dorsiflexion_ktw", source="phone", device="iPhone")
        pair("single_leg_balance", source="phone", device="iPhone")
        pair("y_balance_composite")
        weekly_jumps(0.0)
    else:  # soccer, on their own
        add("height", spec.height_in * 2.54)
        add("body_mass", spec.weight_lb * 0.4536)
        add("sprint_10m", val("sprint_10m"), device="Timing gates")
        add("sprint_30m", val("sprint_30m"), device="Timing gates")
        add("max_speed", val("max_speed"), device="GPS")
        add("yoyo_ir1", val("yoyo_ir1"))
        add("yoyo_ir2", val("yoyo_ir2"))
        add("ift_30_15", val("ift_30_15"))
        add("cmj_height", val("cmj_height"), source="phone", device="iPhone")
        n = val("nordic_hamstring_force")
        add("nordic_hamstring_force", n, side="right", device="NordBord")
        add("nordic_hamstring_force", n * 0.8, side="left", device="NordBord")
        h = val("hip_adduction_force")
        add("hip_adduction_force", h, side="right")
        add("hip_adduction_force", h * 0.95, side="left")
        a5 = val("arrowhead")
        add("arrowhead", a5, side="left", device="Timing gates")
        add("arrowhead", a5 * 1.02, side="right", device="Timing gates")
        add("body_fat_pct", val("body_fat_pct"))
    return out


def _injuries(spec: AthleteSpec, pid: str, today: date,
              story_day: int = 0) -> tuple[list[SportsInjury], list[SportsRehabMeasure]]:
    """The injury a scenario carries and its rehab measures up to today.
    ``story_day`` is how many mornings the story has run: the injury sits
    that much further back, and the measures have that many more days."""
    r = _rng(spec.id, "injury")
    injuries: list[SportsInjury] = []
    measures: list[SportsRehabMeasure] = []
    # Days since the injury (the operation, for the ACL) as of today.
    n = STORY_BASE.get(spec.scenario, 0) + story_day

    def m(inj: SportsInjury, key: str, value: float, d: date, side: str | None = None, source: str = "staff") -> None:
        from app.sports.catalog.injuries import MEASURES
        spec_m = MEASURES[key]
        measures.append(SportsRehabMeasure(injury_id=0, patient_id=pid, date=d, measure_key=key, value=round(float(value), spec_m.decimals),
                                           unit=spec_m.unit, side=side, source=source))

    if spec.scenario == "acl":
        surgery = today - timedelta(days=n)
        inj = SportsInjury(patient_id=pid, injury_key="acl_reconstruction", label="ACL reconstruction", side="left",
                           body_region="knee", date_of_injury=surgery - timedelta(days=16), date_of_surgery=surgery,
                           graft="Bone–patellar tendon–bone", mechanism="Non-contact, landing from a rebound",
                           clinician="Dr. Evan Ruiz-Castillo", status="active",
                           target_return_date=surgery + timedelta(days=285),
                           note="Isolated ACL, no meniscal work. Straight-line running since week 14.")
        injuries.append(inj)
        # Weekly measures from week 1: range, effusion, pain; strength from week 6 every two weeks; hops from week 16.
        for wk in range(1, 27):
            d = surgery + timedelta(days=wk * 7)
            if d > today:
                break
            ext = max(0.0, 8 - wk * 1.2 + r.normal(0, 0.5))
            flex = min(140.0, 70 + wk * 5.5 + r.normal(0, 2))
            eff = max(0.0, 2.2 - wk * 0.2 + r.normal(0, 0.15))
            m(inj, "knee_extension_deficit", round(ext), d, source="phone")
            m(inj, "knee_flexion", flex, d, side="left", source="phone")
            m(inj, "knee_flexion", 142 + r.normal(0, 1), d, side="right", source="phone")
            m(inj, "effusion_grade", round(min(3, eff)), d)
            m(inj, "pain_nrs", max(0.0, round(5 - wk * 0.25 + r.normal(0, 0.4))), d, source="app")
            if wk <= 4:
                m(inj, "slr_lag", max(0.0, round(6 - wk * 1.8)), d)
            if wk >= 6 and wk % 2 == 0:
                good = 640 + r.normal(0, 15)
                lsi = min(0.86, 0.48 + 0.022 * (wk - 6))
                m(inj, "quad_strength", good, d, side="right", source="dynamometer")
                m(inj, "quad_strength", good * lsi, d, side="left", source="dynamometer")
                hg = 380 + r.normal(0, 10)
                hl = min(0.92, 0.6 + 0.02 * (wk - 6))
                m(inj, "hamstring_strength", hg, d, side="right", source="dynamometer")
                m(inj, "hamstring_strength", hg * hl, d, side="left", source="dynamometer")
            if wk >= 8 and wk % 4 == 0:
                m(inj, "calf_raise_reps", 28, d, side="right")
                m(inj, "calf_raise_reps", min(28, 14 + wk), d, side="left")
                m(inj, "single_leg_balance_s", 40, d, side="right", source="phone")
                m(inj, "single_leg_balance_s", min(40, 10 + wk * 1.5), d, side="left", source="phone")
            if wk >= 16 and wk % 2 == 0:
                good = 196 + r.normal(0, 4)
                lsi = min(0.88, 0.66 + 0.03 * (wk - 16))
                m(inj, "hop_single", good, d, side="right")
                m(inj, "hop_single", good * lsi, d, side="left")
                m(inj, "hop_triple", good * 2.9, d, side="right")
                m(inj, "hop_triple", good * 2.9 * (lsi - 0.02), d, side="left")
                m(inj, "hop_crossover", good * 2.7, d, side="right")
                m(inj, "hop_crossover", good * 2.7 * (lsi - 0.04), d, side="left")
                tg = 1.95 + r.normal(0, 0.04)
                m(inj, "hop_timed_6m", tg, d, side="right", source="phone")
                m(inj, "hop_timed_6m", tg / (lsi - 0.02), d, side="left", source="phone")
            if wk in (12, 16, 20, 24):
                m(inj, "acl_rsi", {12: 44, 16: 51, 20: 57, 24: 61}[wk], d, source="app")
                m(inj, "ikdc", {12: 58, 16: 66, 20: 72, 24: 77}[wk], d, source="app")
                m(inj, "tampa_tsk", {12: 26, 16: 23, 20: 21, 24: 20}[wk], d, source="app")
                m(inj, "koos_sport", {12: 40, 16: 50, 20: 60, 24: 65}[wk], d, source="app")
        m(inj, "knee_valgus_dvj", 1, today - timedelta(days=5), source="staff")
        m(inj, "y_balance_anterior_diff", 3.2, today - timedelta(days=5))
    elif spec.scenario == "ankle":
        day0 = today - timedelta(days=n)
        inj = SportsInjury(patient_id=pid, injury_key="ankle_sprain_lateral", label="Lateral ankle sprain", side="right",
                           body_region="ankle", date_of_injury=day0, grade="Grade 2", mechanism="Landed on a foot under the rim",
                           clinician="Marisol Deng, ATC", status="active", note="Anterior drawer 1+, no syndesmosis signs. Boot 48 h.")
        injuries.append(inj)
        for k in range(0, n + 1):
            d = day0 + timedelta(days=k)
            m(inj, "pain_nrs", max(0.0, round(7 - k * 0.55 + r.normal(0, 0.3))), d, source="app")
            m(inj, "ankle_girth_figure8", 56.0 + max(0.0, 3.2 - k * 0.3), d, side="right")
            m(inj, "ankle_girth_figure8", 55.9 + r.normal(0, 0.1), d, side="left")
            m(inj, "swelling_grade", max(0, round(2.4 - k * 0.3)), d)
            if k >= 3 and k % 2 == 1:
                m(inj, "ankle_dorsiflexion", min(11.6, 7.0 + k * 0.5) + r.normal(0, 0.2), d, side="right", source="phone")
                m(inj, "ankle_dorsiflexion", 11.8 + r.normal(0, 0.2), d, side="left", source="phone")
                m(inj, "single_leg_balance_s", min(30, 3 + k * 2.2), d, side="right", source="phone")
                m(inj, "single_leg_balance_s", 32 + r.normal(0, 3), d, side="left", source="phone")
            if k >= 16 and k % 3 == 1:
                # Hopping from the third week: close, not yet symmetric.
                m(inj, "hop_single", 222.0 * min(0.88, 0.80 + 0.01 * (k - 16)), d, side="right")
                m(inj, "hop_single", 222.0, d, side="left")
        # Yesterday's strength and questionnaires, a little better each day.
        m(inj, "calf_raise_reps", min(26, 18 + story_day), today - timedelta(days=1), side="right")
        m(inj, "calf_raise_reps", 27, today - timedelta(days=1), side="left")
        m(inj, "cait", min(25, 19 + story_day // 2), today - timedelta(days=1), source="app")
        m(inj, "faam_sport", min(84, 56 + 2 * story_day), today - timedelta(days=1), source="app")
    elif spec.scenario == "tendon":
        day0 = today - timedelta(days=n)
        inj = SportsInjury(patient_id=pid, injury_key="patellar_tendinopathy", label="Patellar tendinopathy (jumper's knee)",
                           side="left", body_region="knee", date_of_injury=day0, mechanism="Gradual, inferior pole, worse in the morning",
                           clinician="Tyrese Calloway", status="active", note="Managing in training: isometrics pre-practice, HSR three times a week.")
        injuries.append(inj)
        for k in range(0, n + 1, 2):
            d = day0 + timedelta(days=k)
            m(inj, "decline_squat_pain", max(1.0, round(6.5 - k * 0.12 + r.normal(0, 0.4))), d, source="app")
            m(inj, "pain_next_morning", max(1.0, round(5.5 - k * 0.1 + r.normal(0, 0.4))), d, source="app")
            m(inj, "pain_nrs", max(1.0, round(4.5 - k * 0.08 + r.normal(0, 0.4))), d, source="app")
        m(inj, "visa_p", 58, day0, source="app")
        m(inj, "visa_p", 66, day0 + timedelta(days=14), source="app")
        m(inj, "quad_strength", 590, today - timedelta(days=3), side="left", source="dynamometer")
        m(inj, "quad_strength", 660, today - timedelta(days=3), side="right", source="dynamometer")
    elif spec.scenario == "tennis_solo":
        day0 = today - timedelta(days=n)
        inj = SportsInjury(patient_id=pid, injury_key="shoulder_overuse", label="Serving shoulder (rotator cuff / impingement)",
                           side="right", body_region="shoulder", date_of_injury=day0, mechanism="Built over two tournament weeks",
                           status="active", note="Seen by a physio; no serving for two weeks, groundstrokes fine.")
        injuries.append(inj)
        for k in range(0, n + 1, 3):
            d = day0 + timedelta(days=k)
            m(inj, "pain_nrs", max(1.0, round(6 - k * 0.2 + r.normal(0, 0.3))), d, source="app")
            m(inj, "shoulder_ir", min(54.0, 38 + k * 0.6), d, side="right", source="phone")
            m(inj, "shoulder_ir", 56, d, side="left", source="phone")
        m(inj, "shoulder_er_ir_ratio", 0.63, today - timedelta(days=2), side="right")
        m(inj, "kjoc", 71, today - timedelta(days=2), source="app")
        m(inj, "serve_pct_max", 60, today - timedelta(days=1), source="app")
    elif spec.scenario in ("hamstring", "soccer_solo"):
        day0 = today - timedelta(days=n)
        squad = spec.scenario == "hamstring"
        inj = SportsInjury(patient_id=pid, injury_key="hamstring_strain", label="Hamstring strain", side="left",
                           body_region="hamstring", date_of_injury=day0, grade="Grade 2", mechanism="Sprinting, late in a match",
                           clinician="Jonah Feldt, ATC" if squad else None, status="active",
                           note="Biceps femoris, no tendon involvement on the scan. Running from day 11." if squad else None)
        injuries.append(inj)
        for k in range(0, n + 1, 2):
            d = day0 + timedelta(days=k)
            m(inj, "pain_nrs", max(0.0, round(6 - k * 0.4 + r.normal(0, 0.3))), d, source="app")
            if k >= 4:
                m(inj, "hamstring_ake", max(5.0, 28 - k * 1.1), d, side="left", source="phone")
                m(inj, "hamstring_ake", 12.0, d, side="right", source="phone")
            if k >= 8 and k % 4 == 0:
                m(inj, "nordic_force", 395 + r.normal(0, 8), d, side="right")
                m(inj, "nordic_force", (395 + r.normal(0, 8)) * min(0.93, 0.7 + 0.025 * (k - 8)), d, side="left")
        # The two gates still open: the H-test and a sprint near full speed.
        m(inj, "askling_h_pain", 1, today - timedelta(days=1), source="app")
        m(inj, "sprint_pct_max", min(93, 88 + story_day // 2), today - timedelta(days=2), source="app")
    return injuries, measures


def _months(days: int) -> str:
    """Days as months to the nearest half, the way staff say it: 5½, 6."""
    halves = round(days / 30.44 * 2)
    return f"{halves // 2}½" if halves % 2 else str(halves // 2)


def status_for(spec: AthleteSpec, story_day: int = 0) -> tuple[str, str | None]:
    """The availability and the staff's one-line note a scenario starts
    with. The day, week and month in the note come from the injury's date,
    so they read one further each morning the story runs."""
    n = STORY_BASE.get(spec.scenario, 0) + story_day
    if spec.scenario == "acl":
        return "out", f"ACL, month {_months(n)}: running and plyometrics, no cutting or contact."
    if spec.scenario == "ankle":
        return "modified", f"Right ankle, day {n}: bike, balance, no practice until hops are symmetric."
    if spec.scenario == "tendon":
        return "modified", f"Left patellar tendon, week {n // 7 + 1}: jump load managed, isometrics before practice."
    if spec.scenario == "hamstring":
        return "modified", f"Left hamstring, day {n}: running on her own, no match minutes until the H-test is 0."
    return "available", None


def _reset(db: Session, pid: str) -> None:
    """Remove a demo athlete entirely: the account, the sign-ins, the thread
    and every stream. What ``fresh=True`` and the tests' clean-up use; the
    morning refresh never calls it."""
    from app.models.adherence import AdherenceRecord, AdherenceTask
    from app.models.checkin import Checkin, CheckinMessage
    from app.models.mobile import PatientSession, PhoneVerification
    from app.models.notification import Notification
    from app.models.personal import PersonalLog

    checkin_ids = db.scalars(select(Checkin.id).where(Checkin.patient_id == pid)).all()
    if checkin_ids:
        db.execute(delete(CheckinMessage).where(CheckinMessage.checkin_id.in_(checkin_ids)))
    for model in (SportsRehabMeasure, SportsInjury, SportsTest, SportsSession, SportsWellness, SportsProfile,
                  Consent, PersonalCredential, PersonalLog, Checkin, RiskAssessment, Insight, EstablishedBaseline,
                  PatientSession, PhoneVerification, Message, Notification, AdherenceRecord, AdherenceTask,
                  Observation, Device):
        db.execute(delete(model).where(model.patient_id == pid))
    db.execute(delete(Patient).where(Patient.id == pid))
    db.commit()


# --- the refresh ---------------------------------------------------------------------------------------

# The calendar each seeded team gets. A team without an entry keeps no
# generated calendar and its board says so.
TEAM_SCHEDULES = {"rice-mbb": rice_schedule, "rice-wsoc": wsoc_schedule}

_SAMPLE = "Connected by Rice Athletics — sample data"
# Team systems the program connected for the squad: sample data until a
# credential is keyed (app/sports/catalog/devices.py says which is which).
TEAM_DEVICES: dict[str, dict[str, tuple[str, str]]] = {
    "rice-mbb": {"catapult": ("sample", _SAMPLE), "hawkin": ("sample", _SAMPLE), "vald": ("sample", _SAMPLE),
                 "noah": ("sample", _SAMPLE), "vert": ("import", "Import ready")},
    "rice-wsoc": {"statsports": ("sample", _SAMPLE), "hawkin": ("sample", _SAMPLE), "vald": ("sample", _SAMPLE)},
}

# A line or two from the staff on a thread: (staff id, days before the story
# started, time of day, text). Written when an athlete's story starts and left
# alone while it runs, so a note ages like any other message.
NOTES: dict[str, list[tuple[str, int, str, str]]] = {
    "kwame-asante": [("st_rice_at", 2, "11:30",
                      "Quad strength is at 83% of the right side on the last dynamometer test. Single-leg press stays "
                      "heavy this block, and no cutting until that number passes 90.")],
    "tobias-lindqvist": [("st_rice_at", 1, "16:10",
                          "Calf raises were 18 on the right against 27 on the left today. Bike and the balance block "
                          "every day; we start hopping when the raises are within three of each other.")],
    "mateo-reyes-vega": [("st_rice_sc", 1, "17:45",
                          "No lift for you tomorrow. Midterms come first: lights out by 11 the next three nights and "
                          "we look at your mornings again after the weekend.")],
    "brooke-halvorsen": [("st_rice_wsoc_at", 2, "15:45",
                          "Top speed reached 88% of your best on the runs today. The H-test is still 1 out of 10, so "
                          "no match minutes yet: flying 20s at 90% next, then we retest the Nordics.")],
    "naomi-adebayo": [("st_rice_wsoc_sc", 1, "17:20",
                       "The lift is optional for you this week. Exams first: lights out by 11, and we pick the block "
                       "back up once they are done.")],
    "imani-brooks": [("st_rice_wsoc_at", 1, "08:10",
                      "Stay home today and keep the fluids going. Send me your temperature tonight and we decide "
                      "about tomorrow then.")],
}


def write_schedule(db: Session, team_id: str, events: list[dict[str, Any]]) -> int:
    """Replace the calendar the seed wrote for a team with this one. Rows
    older than the ``source`` column were all the seed's, so they go too;
    an event the staff added stays where it is."""
    db.execute(delete(SportsEvent).where(SportsEvent.team_id == team_id,
                                         or_(SportsEvent.source == SEEDED, SportsEvent.source.is_(None))))
    for e in events:
        db.add(SportsEvent(team_id=team_id, source=SEEDED, **e))
    return len(events)


def story_of(settings: dict[str, Any] | None, key: str, today: date) -> tuple[date, int]:
    """The day the running story started and how many mornings it has run.
    ``key`` is where the profile's settings keep it ("seed" for this roster,
    "showcase" for a filled account). A story that is missing, past
    ``STORY_DAYS`` or dated after ``today`` starts today."""
    raw = ((settings or {}).get(key) or {}).get("story_started")
    try:
        started = date.fromisoformat(raw) if raw else None
    except (TypeError, ValueError):
        started = None
    if started is None or not 0 <= (today - started).days <= STORY_DAYS:
        return today, 0
    return started, (today - started).days


def clear_streams(db: Session, pid: str) -> None:
    """Drop what a device or a test day produced for an athlete, and what the
    engines derived from it. The account, its sign-ins, the thread, tasks and
    the injury row itself are not here: they are not streams."""
    for model in (SportsRehabMeasure, SportsTest, SportsSession, SportsWellness, Observation, RiskAssessment, Insight,
                  EstablishedBaseline):
        db.execute(delete(model).where(model.patient_id == pid))


def upsert_injury(db: Session, pid: str, new: SportsInjury | None) -> SportsInjury | None:
    """Write the generated injury over the row an earlier run left, so its id
    (the athlete's plan and the console both link to it) survives a refresh.
    Any other injury on the athlete goes: on a demo account they are all
    generated."""
    rows = list(db.scalars(select(SportsInjury).where(SportsInjury.patient_id == pid).order_by(SportsInjury.id)).all())
    keep = next((row for row in rows if new is not None and row.injury_key == new.injury_key), None)
    for row in rows:
        if row is not keep:
            db.delete(row)
    if new is None:
        return None
    if keep is None:
        db.add(new)
        db.flush()
        return new
    for name in ("label", "side", "body_region", "date_of_injury", "date_of_surgery", "graft", "mechanism", "grade",
                 "status", "target_return_date", "clinician", "note"):
        setattr(keep, name, getattr(new, name))
    keep.phase_override = None
    keep.cleared_at = None
    return keep


def write_notes(db: Session, patient: Patient, lines: list[tuple[str, datetime]], *, restart: bool) -> int:
    """Put the generated staff lines on an athlete's thread. They are found
    again by their exact text, so nothing anyone typed is ever touched. While
    a story runs the lines already there are left to age; a new story swaps
    them for fresh ones."""
    if not lines:
        return 0
    have = db.scalars(select(Message).where(Message.patient_id == patient.id, Message.sender == "care_team",
                                            Message.channel == "console",
                                            Message.text.in_([text for text, _ in lines]))).all()
    if not restart and len(have) == len(lines):
        return len(have)
    for row in have:
        db.delete(row)
    for text, when in lines:
        db.add(Message(patient_id=patient.id, sender="care_team", channel="console", text=text, authored_by="care_team",
                       sender_id=patient.assigned_provider_id, created_at=when))
    return len(lines)


def _note_lines(spec: AthleteSpec, started: date) -> list[tuple[str, datetime]]:
    staff = {s["id"]: s for s in STAFF}
    out = []
    for staff_id, back, clock, text in NOTES.get(spec.id, []):
        who = staff[staff_id]
        signed = f"{who['name']} ({identity.STAFF_ROLE_LABELS.get(who['role'], who['role'])}): {text}"
        out.append((signed, datetime.combine(started - timedelta(days=back), time.fromisoformat(clock))))
    return out


def _account(db: Session, spec: AthleteSpec, today: date) -> tuple[Patient, SportsProfile]:
    """The athlete's account: created the first time, brought back to the
    spec every time after. Never deleted here, so the app stays signed in
    and a bound phone number stays bound."""
    patient = db.get(Patient, spec.id)
    profile = db.get(SportsProfile, spec.id) if patient is not None else None
    # A birthday in mid-March, in the year that makes the spec's age true today.
    dob = date(today.year - spec.age - (1 if (today.month, today.day) < (3, 14) else 0), 3, 14)
    if patient is None:
        patient, profile = identity.create_sports_account(
            db, name=spec.name, sport=spec.sport, sex=spec.sex, date_of_birth=dob, org_id=spec.org_id,
            team_id=spec.team_id, position=spec.position, jersey=spec.jersey, class_year=spec.class_year,
            level=spec.level, height_cm=spec.height_in * 2.54, weight_kg=spec.weight_lb * 0.4536,
            wingspan_cm=spec.wingspan_in * 2.54 if spec.wingspan_in else None,
            standing_reach_cm=spec.reach_in * 2.54 if spec.reach_in else None, dominant_side=spec.dominant,
            units="imperial", cycle_tracking=(spec.sex == "F"), join_code="OWLS26" if spec.org_id == "rice" else None,
            patient_id=spec.id,
        )
    elif profile is None or not is_sports(patient):
        raise ValueError(f"{spec.id} exists and is not a demo athlete; the sports seed will not write over it")
    else:
        parts = spec.name.split()
        patient.name = spec.name
        patient.initials = "".join(part[0] for part in parts[:2]).upper()
        patient.sex = spec.sex
        patient.date_of_birth = dob
        profile.sport = spec.sport
        profile.org_id = spec.org_id
        profile.team_id = spec.team_id
        profile.coach_linked = bool(spec.org_id and spec.team_id)
        profile.position = spec.position
        profile.jersey = spec.jersey
        profile.class_year = spec.class_year
        profile.level = spec.level
        profile.height_cm = spec.height_in * 2.54
        profile.weight_kg = spec.weight_lb * 0.4536
        profile.wingspan_cm = spec.wingspan_in * 2.54 if spec.wingspan_in else None
        profile.standing_reach_cm = spec.reach_in * 2.54 if spec.reach_in else None
        profile.dominant_side = spec.dominant
    patient.age = spec.age
    patient.timezone = TZ
    # The clinical anchor a new account has: no operation, the general
    # pathway, dated today. A surgical injury below moves it to the operation.
    patient.procedure_type = "NONE"
    patient.procedure_display = "No surgery"
    patient.surgery_date = today
    patient.discharge_date = today
    patient.care_pathway = "general_recovery"
    if db.get(PersonalCredential, spec.id) is None:
        auth.create_credential(db, patient, _email(spec), PASSWORD)
    auth.record_consent(db, patient, version=auth.CONSENT_VERSION,
                        scopes={"beta_ack": True, "data_storage": True, "ai_processing": True, "research_use": True},
                        signature=spec.name, device_name="iPhone (demo)", app_version="1.0")
    # Flushed so the ingest window, which reads the anchor from the table,
    # sees today's.
    db.flush()
    return patient, profile


def _devices(db: Session, spec: AthleteSpec, today: date) -> None:
    """The watch or band the athlete wears, and the phone: synced this morning."""
    model = {"apple": "Apple Watch Series 11", "whoop": "WHOOP 5.0", "oura": "Oura Ring 4", "garmin": "Garmin Venu 4"}[spec.device]
    wanted = [(f"dev_{spec.id}", SP(spec.device), model, time(6, 40))]
    if spec.device != "apple":
        wanted.append((f"dev_{spec.id}_apple", SP.APPLE, "iPhone 17", time(7, 5)))
    for device_id, provider, device_model, synced in wanted:
        row = db.get(Device, device_id)
        if row is None:
            row = Device(id=device_id, patient_id=spec.id, source_provider=provider, device_model=device_model)
            db.add(row)
        row.connected_at = datetime.combine(today - timedelta(days=DAYS), time(10, 0))
        row.last_sync_at = datetime.combine(today, synced)


def _refresh(db: Session, spec: AthleteSpec, today: date, events: list[dict[str, Any]], counts: dict[str, int]) -> None:
    patient, profile = _account(db, spec, today)
    settings = dict(profile.settings or {})
    started, story_day = story_of(settings, "seed", today)
    restart = (settings.get("seed") or {}).get("story_started") != started.isoformat()
    _devices(db, spec, today)
    connected = dict(settings.get("devices") or {})
    stamp = datetime.combine(today - timedelta(days=DAYS), time(10, 0)).isoformat()
    for key, (mode, detail) in TEAM_DEVICES.get(spec.team_id or "", {}).items():
        connected[key] = {"mode": mode, "detail": detail, "at": stamp}
    settings["devices"] = connected
    settings["seed"] = {"story_started": started.isoformat()}
    profile.settings = settings

    clear_streams(db, spec.id)
    rows = _wearable_rows(spec, spec.id, today, events, story_day)
    ingested, _, _ = ingest_observations(db, rows)
    counts["observations"] += ingested
    sessions = _sessions(spec, spec.id, today, events, story_day)
    db.add_all(sessions)
    counts["sessions"] += len(sessions)
    wellness = _wellness(spec, spec.id, today, sessions, story_day)
    db.add_all(wellness)
    counts["wellness"] += len(wellness)
    tests = _tests(spec, spec.id, today)
    db.add_all(tests)
    counts["tests"] += len(tests)

    injuries, measures = _injuries(spec, spec.id, today, story_day)
    inj = upsert_injury(db, spec.id, injuries[0] if injuries else None)
    if inj is not None:
        from app.sports.catalog.injuries import INJURIES, MEASURES

        for mrow in measures:
            mrow.injury_id = inj.id
        db.add_all(measures)
        counts["injuries"] += 1
        counts["measures"] += len(measures)
        # A performance test that is also a rehab measure (single-leg jump,
        # quad strength, hop…) counts on the injury too, as the app does when
        # a test is logged.
        by_test = {m.test_key: m for m in MEASURES.values() if m.test_key}
        for t in tests:
            mspec = by_test.get(t.test_key)
            if mspec is None or t.date < inj.date_of_injury:
                continue
            db.add(SportsRehabMeasure(injury_id=inj.id, patient_id=spec.id, date=t.date, measure_key=mspec.key,
                                      value=t.value, unit=mspec.unit, side=t.side if mspec.sided else None,
                                      source=t.source))
            counts["measures"] += 1
        spec_i = INJURIES[inj.injury_key]
        if inj.date_of_surgery and spec_i.procedure_type:
            patient.procedure_type = spec_i.procedure_type
            patient.procedure_display = spec_i.label
            patient.surgery_date = inj.date_of_surgery
            patient.discharge_date = inj.date_of_surgery
            patient.care_pathway = None

    # An availability the staff set from the console stays theirs; anything
    # else is the scenario's, with its day count brought up to this morning.
    if not identity.staff_set_status(profile):
        profile.status, profile.status_note = status_for(spec, story_day)
    counts["messages"] += write_notes(db, patient, _note_lines(spec, started), restart=restart)
    db.commit()
    counts["athletes"] += 1


def seed_sports(db: Session, today: date | None = None, *, fresh: bool = False) -> dict[str, int]:
    """Bring the sports demo up to ``today``. Safe to run every morning: see
    the module docstring for what is rewritten and what is kept. ``fresh``
    removes every demo athlete and the seeded teams' whole calendars first."""
    today = today or date.today()
    counts: dict[str, int] = {"orgs": 0, "teams": 0, "staff": 0, "events": 0, "athletes": 0, "observations": 0,
                              "sessions": 0, "wellness": 0, "tests": 0, "injuries": 0, "measures": 0, "messages": 0}
    for o in ORGS:
        if db.get(SportsOrg, o["id"]) is None:
            db.add(SportsOrg(**o, timezone=TZ))
            counts["orgs"] += 1
    db.flush()
    for t in TEAMS:
        if db.get(SportsTeam, t["id"]) is None:
            db.add(SportsTeam(**t))
            counts["teams"] += 1
    db.flush()
    for s in STAFF:
        if db.get(SportsStaff, s["id"]) is None:
            db.add(SportsStaff(**s))
            counts["staff"] += 1
    db.commit()

    if fresh:
        db.execute(delete(SportsEvent).where(SportsEvent.team_id.in_(list(TEAM_SCHEDULES))))
        db.commit()
        for spec in ROSTER:
            _reset(db, spec.id)
    schedules: dict[str, list[dict[str, Any]]] = {}
    for team_id, schedule in TEAM_SCHEDULES.items():
        schedules[team_id] = schedule(today)
        counts["events"] += write_schedule(db, team_id, schedules[team_id])
    db.commit()

    for spec in ROSTER:
        events = schedules[spec.team_id] if spec.team_id in schedules else _solo_schedule(spec, today)
        _refresh(db, spec, today, events, counts)
    return counts


def _solo_schedule(spec: AthleteSpec, today: date) -> list[dict[str, Any]]:
    """An individual athlete's own week: training most days, a match or
    tournament at weekends."""
    out: list[dict[str, Any]] = []
    for i in range(42, -8, -1):
        d = today - timedelta(days=i)
        wd = d.weekday()
        if spec.sport == "tennis":
            if wd in (0, 2, 4):
                out.append(dict(date=d, kind="practice", title="Hitting session", start_time="08:00"))
            if wd in (1, 3):
                out.append(dict(date=d, kind="lift", title="Gym", start_time="07:00"))
            if wd == 5 and i > 20:
                out.append(dict(date=d, kind="game", title="Match", opponent="Club ladder", home=True, start_time="10:00"))
        else:
            if wd in (0, 1, 3):
                out.append(dict(date=d, kind="practice", title="Training", start_time="18:30"))
            if wd == 2:
                out.append(dict(date=d, kind="lift", title="Gym", start_time="07:00"))
            if wd == 5 and i > 17:
                out.append(dict(date=d, kind="game", title="Match", opponent="League", home=(i % 2 == 0), start_time="15:00"))
    return out
