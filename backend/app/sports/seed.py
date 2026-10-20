"""The MedPull Sports demo: Rice University Athletics with a men's
basketball roster, a handful of other programs for the picker, and two
athletes on their own.

Every athlete here is fictional. Names are invented, emails sit on a demo
domain, and the staff are invented too: nothing in this file imitates a
real person. The organisation names are real places a program could pick
from the list; their rosters are not.

Deterministic: every stream is drawn from numpy generators seeded by the
athlete id, anchored to ``today``, so a reseed reproduces the same numbers
for the same day. Observations go through the same ingest path a wearable
delivery takes.

Log in to any athlete with their email and the password ``owls-2026``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import CanonicalObservation
from app.connectors.ingest import ingest_observations
from app.models.enums import Granularity
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider as SP
from app.models.patient import Device, Patient
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
from app.sports import identity
from app.sports.catalog.tests import TESTS

PASSWORD = "owls-2026"
EMAIL_DOMAIN = "athletes.medpull.demo"
TZ = "America/Chicago"
DAYS = 60

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
    scenario: str                # healthy | star | sleep_debt | load_spike | acl | ankle | tendon | unwell | fresh | freshman | taper
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


def _wearable_rows(spec: AthleteSpec, pid: str, today: date, events: list[dict[str, Any]]) -> list[CanonicalObservation]:
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
        if s == "ankle" and i <= 9:
            steps *= 0.6
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


def _sessions(spec: AthleteSpec, pid: str, today: date, events: list[dict[str, Any]]) -> list[SportsSession]:
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
            if kind in ("practice", "game", "shootaround"):
                out.append(SportsSession(patient_id=pid, date=d, kind="rehab", minutes=float(r.uniform(55, 75)),
                                         rpe=float(r.integers(4, 6)), source="manual"))
            else:
                out.append(SportsSession(patient_id=pid, date=d, kind="lift", minutes=45.0, rpe=5.0, source="manual"))
            continue
        if s == "ankle" and (today - d).days <= 9:
            if (today - d).days <= 4 and kind in ("practice", "lift"):
                out.append(SportsSession(patient_id=pid, date=d, kind="rehab", minutes=40.0, rpe=3.0, source="manual"))
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


def _wellness(spec: AthleteSpec, pid: str, today: date, sessions: list[SportsSession]) -> list[SportsWellness]:
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
        if sc == "ankle" and i <= 9:
            pain = float(np.clip(6.5 - 0.4 * (9 - i) + r.normal(0, 0.4), 1, 10))
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
        out.append(SportsWellness(patient_id=pid, date=today, key="note", text="Midterms this week. Two all-nighters.", source="app"))
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
        # Weekly countermovement jumps on the force plate, Mondays, eight weeks.
        cmj_base = val("cmj_height", -0.05 if big else 0.05)
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
    else:  # soccer
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


def _injuries(spec: AthleteSpec, pid: str, today: date) -> tuple[list[SportsInjury], list[SportsRehabMeasure]]:
    r = _rng(spec.id, "injury")
    injuries: list[SportsInjury] = []
    measures: list[SportsRehabMeasure] = []

    def m(inj: SportsInjury, key: str, value: float, d: date, side: str | None = None, source: str = "staff") -> None:
        from app.sports.catalog.injuries import MEASURES
        spec_m = MEASURES[key]
        measures.append(SportsRehabMeasure(injury_id=0, patient_id=pid, date=d, measure_key=key, value=round(float(value), spec_m.decimals),
                                           unit=spec_m.unit, side=side, source=source))

    if spec.scenario == "acl":
        surgery = today - timedelta(days=167)
        inj = SportsInjury(patient_id=pid, injury_key="acl_reconstruction", label="ACL reconstruction", side="left",
                           body_region="knee", date_of_injury=surgery - timedelta(days=16), date_of_surgery=surgery,
                           graft="Bone–patellar tendon–bone", mechanism="Non-contact, landing from a rebound",
                           clinician="Dr. Evan Ruiz-Castillo", status="active",
                           target_return_date=surgery + timedelta(days=285),
                           note="Isolated ACL, no meniscal work. Cleared for straight-line running at 14 weeks.")
        injuries.append(inj)
        # Weekly measures from week 1: range, effusion, pain; strength from week 6 every two weeks; hops from week 16.
        for wk in range(1, 25):
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
        day0 = today - timedelta(days=9)
        inj = SportsInjury(patient_id=pid, injury_key="ankle_sprain_lateral", label="Lateral ankle sprain", side="right",
                           body_region="ankle", date_of_injury=day0, grade="Grade 2", mechanism="Landed on a foot under the rim",
                           clinician="Marisol Deng, ATC", status="active", note="Anterior drawer 1+, no syndesmosis signs. Boot 48 h.")
        injuries.append(inj)
        for k in range(0, 10):
            d = day0 + timedelta(days=k)
            if d > today:
                break
            m(inj, "pain_nrs", max(0.0, round(7 - k * 0.55 + r.normal(0, 0.3))), d, source="app")
            m(inj, "ankle_girth_figure8", 56.0 + max(0.0, 3.2 - k * 0.3), d, side="right")
            m(inj, "ankle_girth_figure8", 55.9 + r.normal(0, 0.1), d, side="left")
            m(inj, "swelling_grade", max(0, round(2.4 - k * 0.3)), d)
            if k >= 3 and k % 2 == 1:
                m(inj, "ankle_dorsiflexion", 7.0 + k * 0.5 + r.normal(0, 0.2), d, side="right", source="phone")
                m(inj, "ankle_dorsiflexion", 11.8 + r.normal(0, 0.2), d, side="left", source="phone")
                m(inj, "single_leg_balance_s", min(30, 3 + k * 2.2), d, side="right", source="phone")
                m(inj, "single_leg_balance_s", 32 + r.normal(0, 3), d, side="left", source="phone")
        m(inj, "calf_raise_reps", 18, today - timedelta(days=1), side="right")
        m(inj, "calf_raise_reps", 27, today - timedelta(days=1), side="left")
        m(inj, "cait", 19, today - timedelta(days=1), source="app")
        m(inj, "faam_sport", 56, today - timedelta(days=1), source="app")
    elif spec.scenario == "tendon":
        day0 = today - timedelta(days=24)
        inj = SportsInjury(patient_id=pid, injury_key="patellar_tendinopathy", label="Patellar tendinopathy (jumper's knee)",
                           side="left", body_region="knee", date_of_injury=day0, mechanism="Gradual, inferior pole, worse in the morning",
                           clinician="Tyrese Calloway", status="active", note="Managing in training: isometrics pre-practice, HSR three times a week.")
        injuries.append(inj)
        for k in range(0, 25, 2):
            d = day0 + timedelta(days=k)
            if d > today:
                break
            m(inj, "decline_squat_pain", max(1.0, round(6.5 - k * 0.12 + r.normal(0, 0.4))), d, source="app")
            m(inj, "pain_next_morning", max(1.0, round(5.5 - k * 0.1 + r.normal(0, 0.4))), d, source="app")
            m(inj, "pain_nrs", max(1.0, round(4.5 - k * 0.08 + r.normal(0, 0.4))), d, source="app")
        m(inj, "visa_p", 58, day0, source="app")
        m(inj, "visa_p", 66, day0 + timedelta(days=14), source="app")
        m(inj, "quad_strength", 590, today - timedelta(days=3), side="left", source="dynamometer")
        m(inj, "quad_strength", 660, today - timedelta(days=3), side="right", source="dynamometer")
    elif spec.scenario == "tennis_solo":
        day0 = today - timedelta(days=20)
        inj = SportsInjury(patient_id=pid, injury_key="shoulder_overuse", label="Serving shoulder (rotator cuff / impingement)",
                           side="right", body_region="shoulder", date_of_injury=day0, mechanism="Built over two tournament weeks",
                           status="active", note="Seen by a physio; no serving for two weeks, groundstrokes fine.")
        injuries.append(inj)
        for k in range(0, 21, 3):
            d = day0 + timedelta(days=k)
            if d > today:
                break
            m(inj, "pain_nrs", max(1.0, round(6 - k * 0.2 + r.normal(0, 0.3))), d, source="app")
            m(inj, "shoulder_ir", 38 + k * 0.6, d, side="right", source="phone")
            m(inj, "shoulder_ir", 56, d, side="left", source="phone")
        m(inj, "shoulder_er_ir_ratio", 0.63, today - timedelta(days=2), side="right")
        m(inj, "kjoc", 71, today - timedelta(days=2), source="app")
        m(inj, "serve_pct_max", 60, today - timedelta(days=1), source="app")
    elif spec.scenario == "soccer_solo":
        day0 = today - timedelta(days=17)
        inj = SportsInjury(patient_id=pid, injury_key="hamstring_strain", label="Hamstring strain", side="left",
                           body_region="hamstring", date_of_injury=day0, grade="Grade 2", mechanism="Sprinting, late in a match",
                           status="active")
        injuries.append(inj)
        for k in range(0, 18, 2):
            d = day0 + timedelta(days=k)
            if d > today:
                break
            m(inj, "pain_nrs", max(0.0, round(6 - k * 0.4 + r.normal(0, 0.3))), d, source="app")
            if k >= 4:
                m(inj, "hamstring_ake", max(5.0, 28 - k * 1.1), d, side="left", source="phone")
                m(inj, "hamstring_ake", 12.0, d, side="right", source="phone")
            if k >= 8 and k % 4 == 0:
                m(inj, "nordic_force", 395 + r.normal(0, 8), d, side="right")
                m(inj, "nordic_force", (395 + r.normal(0, 8)) * min(0.93, 0.7 + 0.025 * (k - 8)), d, side="left")
        m(inj, "askling_h_pain", 1, today - timedelta(days=1), source="app")
        m(inj, "sprint_pct_max", 88, today - timedelta(days=2), source="app")
    return injuries, measures


def _reset(db: Session, pid: str) -> None:
    """Remove a demo athlete so a reseed starts clean."""
    from sqlalchemy import delete

    from app.models.adherence import AdherenceRecord, AdherenceTask
    from app.models.checkin import Checkin, CheckinMessage
    from app.models.insight import EstablishedBaseline, Insight, RiskAssessment
    from app.models.mobile import Message, PatientSession, PhoneVerification
    from app.models.notification import Notification
    from app.models.observation import Observation
    from app.models.personal import Consent, PersonalCredential, PersonalLog

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


def seed_sports(db: Session, today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    counts: dict[str, int] = {"orgs": 0, "teams": 0, "staff": 0, "events": 0, "athletes": 0, "observations": 0,
                              "sessions": 0, "wellness": 0, "tests": 0, "injuries": 0, "measures": 0}
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
    from sqlalchemy import delete

    db.execute(delete(SportsEvent).where(SportsEvent.team_id == "rice-mbb"))
    events = rice_schedule(today)
    for e in events:
        db.add(SportsEvent(team_id="rice-mbb", **e))
        counts["events"] += 1
    db.commit()

    for spec in ROSTER:
        _reset(db, spec.id)
        dob = date(today.year - spec.age, 3, 14)
        patient, profile = identity.create_sports_account(
            db, name=spec.name, sport=spec.sport, sex=spec.sex, date_of_birth=dob, org_id=spec.org_id,
            team_id=spec.team_id, position=spec.position, jersey=spec.jersey, class_year=spec.class_year,
            level=spec.level, height_cm=spec.height_in * 2.54, weight_kg=spec.weight_lb * 0.4536,
            wingspan_cm=spec.wingspan_in * 2.54 if spec.wingspan_in else None,
            standing_reach_cm=spec.reach_in * 2.54 if spec.reach_in else None, dominant_side=spec.dominant,
            units="imperial", cycle_tracking=(spec.sex == "F"), join_code="OWLS26" if spec.org_id == "rice" else None,
            patient_id=spec.id,
        )
        patient.timezone = TZ
        auth.create_credential(db, patient, _email(spec), PASSWORD)
        auth.record_consent(db, patient, version=auth.CONSENT_VERSION,
                            scopes={"beta_ack": True, "data_storage": True, "ai_processing": True, "research_use": True},
                            signature=spec.name, device_name="iPhone (demo)", app_version="1.0")
        device_model = {"apple": "Apple Watch Series 11", "whoop": "WHOOP 5.0", "oura": "Oura Ring 4", "garmin": "Garmin Venu 4"}[spec.device]
        db.add(Device(id=f"dev_{spec.id}", patient_id=spec.id, source_provider=SP(spec.device), device_model=device_model,
                      connected_at=datetime.combine(today - timedelta(days=DAYS), time(10, 0)),
                      last_sync_at=datetime.combine(today, time(6, 40))))
        if spec.device != "apple":
            db.add(Device(id=f"dev_{spec.id}_apple", patient_id=spec.id, source_provider=SP.APPLE, device_model="iPhone 17",
                          connected_at=datetime.combine(today - timedelta(days=DAYS), time(10, 0)),
                          last_sync_at=datetime.combine(today, time(7, 5))))
        # Team devices the program connected: sample data until a credential is keyed.
        if spec.team_id == "rice-mbb":
            profile.settings = {"devices": {
                "catapult": {"mode": "sample", "detail": "Connected by Rice Athletics — sample data", "at": datetime.now().isoformat()},
                "hawkin": {"mode": "sample", "detail": "Connected by Rice Athletics — sample data", "at": datetime.now().isoformat()},
                "vald": {"mode": "sample", "detail": "Connected by Rice Athletics — sample data", "at": datetime.now().isoformat()},
                "noah": {"mode": "sample", "detail": "Connected by Rice Athletics — sample data", "at": datetime.now().isoformat()},
                "vert": {"mode": "import", "detail": "Import ready", "at": datetime.now().isoformat()},
            }}
        athlete_events = events if spec.team_id == "rice-mbb" else _solo_schedule(spec, today)
        rows = _wearable_rows(spec, spec.id, today, athlete_events)
        ingested, _, _ = ingest_observations(db, rows)
        counts["observations"] += ingested
        sessions = _sessions(spec, spec.id, today, athlete_events)
        for s in sessions:
            db.add(s)
        counts["sessions"] += len(sessions)
        for w in _wellness(spec, spec.id, today, sessions):
            db.add(w)
            counts["wellness"] += 1
        for t in _tests(spec, spec.id, today):
            db.add(t)
            counts["tests"] += 1
        injuries, measures = _injuries(spec, spec.id, today)
        from app.sports.catalog.injuries import MEASURES

        by_test = {m.test_key: m for m in MEASURES.values() if m.test_key}
        for inj in injuries:
            db.add(inj)
            db.flush()
            for mrow in measures:
                mrow.injury_id = inj.id
                db.add(mrow)
            counts["injuries"] += 1
            counts["measures"] += len(measures)
            # A performance test that is also a rehab measure (single-leg
            # jump, quad strength, hop…) counts on the injury too, as the
            # app does when a test is logged.
            for t in db.scalars(select(SportsTest).where(SportsTest.patient_id == spec.id,
                                                         SportsTest.date >= inj.date_of_injury)).all():
                mspec = by_test.get(t.test_key)
                if mspec is None:
                    continue
                db.add(SportsRehabMeasure(injury_id=inj.id, patient_id=spec.id, date=t.date, measure_key=mspec.key,
                                          value=t.value, unit=mspec.unit, side=t.side if mspec.sided else None,
                                          source=t.source))
                counts["measures"] += 1
            if inj.date_of_surgery:
                from app.sports.catalog.injuries import INJURIES

                spec_i = INJURIES[inj.injury_key]
                if spec_i.procedure_type:
                    patient.procedure_type = spec_i.procedure_type
                    patient.procedure_display = spec_i.label
                    patient.surgery_date = inj.date_of_surgery
                    patient.discharge_date = inj.date_of_surgery
                    patient.care_pathway = None
        if spec.scenario == "acl":
            profile.status = "out"
            profile.status_note = "ACL, month 5½: running and plyometrics, no cutting or contact."
        elif spec.scenario == "ankle":
            profile.status = "modified"
            profile.status_note = "Right ankle, day 9: bike, balance, no practice until hops are symmetric."
        elif spec.scenario == "tendon":
            profile.status = "modified"
            profile.status_note = "Left patellar tendon: jump load managed, isometrics before practice."
        db.commit()
        counts["athletes"] += 1
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
