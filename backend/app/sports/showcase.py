"""Fill a real athlete's account with a showcase: what MedPull Sports looks
like after a week of use as a professional basketball player.

The account stays the person's own (their login, their consent, their
name); this writes the data around it. Two months of wearable nights
(the ring or band backfills history when it links), six weeks of practice
and game load from the team's tracking system, a preseason battery on
the force plates and gates, weekly jump tests, the week of morning
check-ins and phone tests the athlete did themselves, a lateral ankle
sprain a month ago that is nearly back to full symmetry, and a note from
the performance staff. Deterministic per athlete id, anchored to today.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.connectors.ingest import ingest_observations
from app.models.enums import SourceProvider as SP
from app.models.mobile import Message
from app.models.patient import Device, Patient
from app.models.sports import (
    SportsEvent,
    SportsInjury,
    SportsOrg,
    SportsProfile,
    SportsRehabMeasure,
    SportsSession,
    SportsTeam,
    SportsTest,
    SportsWellness,
)
from app.sports.catalog.injuries import MEASURES
from app.sports.catalog.tests import TESTS
from app.sports.seed import (
    TZ,
    AthleteSpec,
    _rng,
    _sessions,
    _tests,
    _wearable_rows,
    _wellness,
)

OPPONENTS = ["San Antonio", "Dallas", "Memphis", "New Orleans", "Denver", "Utah", "Phoenix", "Golden State",
             "Minnesota", "Oklahoma City", "Portland", "Sacramento", "LA Clippers", "LA Lakers"]
ARENA = "Toyota Center"
# Days before today with a game; two of them are a back-to-back.
PAST_GAMES = [40, 37, 35, 32, 30, 27, 25, 23, 20, 18, 16, 13, 11, 10, 8, 6, 3, 1]
NEXT_GAMES = [1, 3, 6, 8, 10, 13, 15, 18, 20]


def pro_schedule(today: date) -> list[dict[str, Any]]:
    """An NBA-shaped calendar: a game every two or three days, home and away
    in blocks with a travel day before a road trip, shootaround on home game
    days, practice otherwise, two lifts a week, Sundays off when free."""
    out: list[dict[str, Any]] = []
    games: dict[date, dict[str, Any]] = {}
    for n, back in enumerate(PAST_GAMES):
        games[today - timedelta(days=back)] = dict(opponent=OPPONENTS[n % len(OPPONENTS)], home=(n // 2) % 2 == 0)
    for n, ahead in enumerate(NEXT_GAMES):
        games[today + timedelta(days=ahead)] = dict(opponent=OPPONENTS[(n + 7) % len(OPPONENTS)], home=(n // 2) % 2 == 1)
    for i in range(42, -22, -1):
        d = today - timedelta(days=i)
        g = games.get(d)
        if g is not None:
            if g["home"]:
                out.append(dict(date=d, kind="shootaround", title="Shootaround", start_time="10:00", location=ARENA))
            out.append(dict(date=d, kind="game", title="Game", opponent=g["opponent"], home=g["home"], start_time="19:00",
                            location=ARENA if g["home"] else "Away"))
            continue
        nxt = games.get(d + timedelta(days=1))
        if nxt is not None and not nxt["home"] and games.get(d - timedelta(days=1), {}).get("home", True):
            out.append(dict(date=d, kind="travel", title=f"Travel to {nxt['opponent']}", home=False, start_time="14:00"))
            out.append(dict(date=d, kind="practice", title="Practice", start_time="10:00", location="Training center"))
            continue
        if d.weekday() == 6 and games.get(d - timedelta(days=1)) is not None:
            out.append(dict(date=d, kind="off", title="Day off"))
            continue
        if d.weekday() in (1, 4):
            out.append(dict(date=d, kind="lift", title="Lift", start_time="09:00", location="Training center"))
        out.append(dict(date=d, kind="practice", title="Practice", start_time="11:00", location="Training center"))
    return out


def _spec(patient: Patient, profile: SportsProfile, org_id: str | None, team_id: str | None) -> AthleteSpec:
    age = 24
    if patient.date_of_birth:
        born = patient.date_of_birth
        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return AthleteSpec(
        patient.id, patient.name, "basketball", profile.position or "Guard", profile.jersey, None, age,
        patient.sex or "M", (profile.height_cm or 193.0) / 2.54, (profile.weight_kg or 88.0) / 0.4536,
        (profile.wingspan_cm / 2.54) if profile.wingspan_cm else None,
        (profile.standing_reach_cm / 2.54) if profile.standing_reach_cm else None,
        profile.dominant_side or "right", "whoop", "star", org_id=org_id, team_id=team_id, starter=True,
        athleticism=0.7, level="pro",
    )


INJURY_DAYS_AGO = 38


def _ankle_sprain(pid: str, today: date, clinician: str) -> tuple[SportsInjury, list[SportsRehabMeasure]]:
    """A grade 2 lateral sprain five weeks ago, right ankle: every gate met
    as of this week, the last one (single-hop symmetry) on Friday, so the
    plan sits in its final phase, the prevention block."""
    r = _rng(pid, "showcase-injury")
    day0 = today - timedelta(days=INJURY_DAYS_AGO)
    inj = SportsInjury(patient_id=pid, injury_key="ankle_sprain_lateral", label="Lateral ankle sprain", side="right",
                       body_region="ankle", date_of_injury=day0, grade="Grade 2",
                       mechanism="Landed on a defender's foot closing out on a shooter", clinician=clinician,
                       status="active", note="Anterior drawer 1+, no syndesmosis signs. Taped for practice from day 7, "
                                             "playing from day 12. Hop symmetry cleared the 90% line this week; "
                                             "balance block stays in warm-ups for the season.")
    rows: list[SportsRehabMeasure] = []

    def m(key: str, value: float, k: int, side: str | None = None, source: str = "staff") -> None:
        spec = MEASURES[key]
        rows.append(SportsRehabMeasure(injury_id=0, patient_id=pid, date=day0 + timedelta(days=k), measure_key=key,
                                       value=round(float(value), spec.decimals), unit=spec.unit, side=side, source=source))

    pain = {0: 7, 1: 6, 2: 5, 3: 4, 5: 3, 7: 3, 10: 2, 14: 2, 17: 2, 21: 1, 24: 1, 28: 1, 31: 1, 35: 0}
    for k, p in pain.items():
        m("pain_nrs", p, k, source="app")
    for k in (0, 1, 2, 3, 5, 7, 10, 14, 21, 28, 35):
        m("ankle_girth_figure8", 59.6 - min(3.4, k * 0.33) + r.normal(0, 0.08), k, side="right")
        m("ankle_girth_figure8", 55.9 + r.normal(0, 0.08), k, side="left")
        m("swelling_grade", 2 if k < 3 else 1 if k < 10 else 0, k)
    for k in (3, 5, 7, 10, 14, 21, 28, 35):
        m("ankle_dorsiflexion", min(11.8, 6.3 + k * 0.28) + r.normal(0, 0.15), k, side="right", source="phone")
        m("ankle_dorsiflexion", 12.0 + r.normal(0, 0.15), k, side="left", source="phone")
    for k in (5, 7, 10, 14, 21, 24, 28, 35):
        m("single_leg_balance_s", min(29.0, 3.5 + k * 1.0), k, side="right", source="phone")
        m("single_leg_balance_s", 31.0 + r.normal(0, 1.5), k, side="left", source="phone")
    for k in (7, 14, 21, 28, 35):
        m("calf_raise_reps", min(27, 13 + k * 0.5), k, side="right")
        m("calf_raise_reps", 28, k, side="left")
    for k, right in ((14, 180.0), (21, 190.0), (28, 197.0), (35, 205.0)):
        m("hop_single", right + r.normal(0, 1.0), k, side="right")
        m("hop_single", 222.0 + r.normal(0, 1.0), k, side="left")
    for k, right in ((17, 10.8), (24, 9.8), (30, 9.3), (35, 9.2)):
        m("hop_lateral", right + r.normal(0, 0.05), k, side="right", source="phone")
        m("hop_lateral", 9.0 + r.normal(0, 0.05), k, side="left", source="phone")
    for k, v in ((7, 16), (14, 21), (21, 24), (28, 26), (35, 27)):
        m("cait", v, k, source="app")
    for k, v in ((7, 48), (14, 70), (21, 84), (28, 89), (35, 92)):
        m("faam_sport", v, k, source="app")
    m("sebt_composite", 91.5, 24, side="right")
    m("sebt_composite", 95.8, 24, side="left")
    m("sebt_composite", 94.6, 35, side="right")
    m("sebt_composite", 96.1, 35, side="left")
    return inj, rows


def fill_pro_athlete(db: Session, patient_id: str, today: date | None = None, *, org_id: str | None = "rockets",
                     team_id: str | None = "rockets-nba") -> dict[str, Any]:
    today = today or date.today()
    patient = db.get(Patient, patient_id)
    profile = db.scalar(select(SportsProfile).where(SportsProfile.patient_id == patient_id))
    if patient is None or profile is None:
        raise ValueError(f"No athlete account with id {patient_id!r}")
    if org_id and db.get(SportsOrg, org_id) is None:
        raise ValueError(f"No organisation {org_id!r}: seed the sports demo first")
    if team_id and db.get(SportsTeam, team_id) is None:
        raise ValueError(f"No team {team_id!r}: seed the sports demo first")

    counts: dict[str, int] = {"events": 0, "observations": 0, "sessions": 0, "wellness": 0, "tests": 0,
                              "measures": 0, "messages": 0}

    # The athlete: a professional, on the team, with the team's systems.
    profile.level = "pro"
    profile.position = profile.position or "Guard"
    profile.org_id = org_id
    profile.team_id = team_id
    profile.coach_linked = bool(org_id)
    profile.status = "available"
    profile.status_note = None
    stamp = datetime.now().isoformat()
    org_name = db.get(SportsOrg, org_id).name if org_id else "your program"
    profile.settings = {**(profile.settings or {}), "devices": {
        "catapult": {"mode": "sample", "detail": f"Connected by {org_name} — sample data", "at": stamp},
        "hawkin": {"mode": "sample", "detail": f"Connected by {org_name} — sample data", "at": stamp},
        "vald": {"mode": "sample", "detail": f"Connected by {org_name} — sample data", "at": stamp},
        "noah": {"mode": "sample", "detail": f"Connected by {org_name} — sample data", "at": stamp},
        "whoop": {"mode": "live", "detail": "Connected", "at": stamp},
        "vert": {"mode": "import", "detail": "Import ready", "at": stamp},
    }}
    patient.timezone = patient.timezone or TZ

    # Devices: the band that backfilled two months of nights, and the phone.
    have = {d.source_provider for d in db.scalars(select(Device).where(Device.patient_id == patient_id)).all()}
    if SP.WHOOP not in have:
        db.add(Device(id=f"dev_{patient_id}_whoop", patient_id=patient_id, source_provider=SP.WHOOP, device_model="WHOOP 5.0",
                      connected_at=datetime.combine(today - timedelta(days=60), time(10, 0)),
                      last_sync_at=datetime.combine(today, time(6, 40))))
    if SP.APPLE not in have:
        db.add(Device(id=f"dev_{patient_id}_apple", patient_id=patient_id, source_provider=SP.APPLE, device_model="Apple Watch Series 11",
                      connected_at=datetime.combine(today - timedelta(days=8), time(19, 30)),
                      last_sync_at=datetime.combine(today, time(7, 5))))

    # The team calendar.
    events: list[dict[str, Any]] = []
    if team_id:
        db.execute(delete(SportsEvent).where(SportsEvent.team_id == team_id))
        events = pro_schedule(today)
        for e in events:
            db.add(SportsEvent(team_id=team_id, **e))
        counts["events"] = len(events)
    db.commit()

    # A clean slate for the generated streams; the account itself stays.
    for model in (SportsSession, SportsWellness, SportsTest, SportsRehabMeasure):
        db.execute(delete(model).where(model.patient_id == patient_id))
    db.execute(delete(SportsInjury).where(SportsInjury.patient_id == patient_id))
    db.commit()

    spec = _spec(patient, profile, org_id, team_id)
    injury_day = today - timedelta(days=INJURY_DAYS_AGO)

    rows = _wearable_rows(spec, patient_id, today, events)
    ingested, _, _ = ingest_observations(db, rows)
    counts["observations"] = ingested

    # Sessions from the tracking system; the sprain's first week is rehab,
    # the games of its second week were missed.
    sessions: list[SportsSession] = []
    for s in _sessions(spec, patient_id, today, events):
        since = (s.date - injury_day).days
        if 0 <= since <= 6:
            if s.kind in ("practice", "game", "shootaround"):
                sessions.append(SportsSession(patient_id=patient_id, date=s.date, kind="rehab", minutes=65.0, rpe=5.0,
                                              load_au=325.0, jumps=0, source="manual",
                                              note="Bike, pool and band work; ankle rehab block"))
            continue
        if 7 <= since <= 11 and s.kind == "game":
            continue
        if s.kind == "practice":
            # In-season pro practices run shorter and lighter than a college
            # preseason block; the games carry the week.
            s.minutes = round(s.minutes * 0.7, 1)
            s.rpe = max(3.0, (s.rpe or 6.0) - 1.0)
            s.load_au = round(s.minutes * s.rpe, 1)
            s.jumps = int((s.jumps or 0) * 0.8)
            if s.player_load:
                s.player_load = round(s.player_load * 0.75, 1)
        elif s.kind == "game":
            # Session RPE covers the whole game night, warm-up and bench
            # time included, not just the minutes on the floor.
            s.minutes = round(s.minutes + 28.0, 1)
            s.load_au = round(s.minutes * (s.rpe or 8.0), 1)
        sessions.append(s)
    for s in sessions:
        db.add(s)
    counts["sessions"] = len(sessions)

    # The week of mornings the athlete answered themselves.
    week = [w for w in _wellness(spec, patient_id, today, sessions) if (today - w.date).days <= 8 and w.key != "note"]
    for w in week:
        if w.key == "pain":
            w.value = 1.0 if (today - w.date).days >= 2 else 0.0
        db.add(w)
    db.add(SportsWellness(patient_id=patient_id, date=today - timedelta(days=1), key="note",
                          text="Ankle felt solid in the cut drills. Taped for practice.", source="app"))
    counts["wellness"] = len(week) + 1

    # The preseason battery and the weekly jumps, then the phone tests from this week.
    tests = _tests(spec, patient_id, today)
    cmj = max((t for t in tests if t.test_key == "cmj_height"), key=lambda t: t.date, default=None)
    jump_cm = (cmj.value if cmj else 52.0) + 1.8
    r = _rng(patient_id, "showcase-phone")

    def phone(key: str, value: float, back: int, side: str | None = None) -> None:
        t = TESTS[key]
        tests.append(SportsTest(patient_id=patient_id, date=today - timedelta(days=back), test_key=key,
                                value=round(value, t.decimals), unit=t.unit, side=side, source="phone", device="iPhone",
                                detail={"method": "flight time, h = g·t²/8"} if key == "phone_jump_height" else None))

    phone("phone_jump_height", jump_cm - 0.9 + r.normal(0, 0.3), 6)
    phone("phone_jump_height", jump_cm + 0.4 + r.normal(0, 0.3), 3)
    phone("phone_jump_height", jump_cm + 0.9 + r.normal(0, 0.3), 1)
    phone("reaction_time", 221 + r.normal(0, 4), 6)
    phone("reaction_time", 208 + r.normal(0, 4), 2)
    phone("single_leg_balance", 26.0 + r.normal(0, 1), 5, side="right")
    phone("single_leg_balance", 31.0 + r.normal(0, 1), 5, side="left")
    phone("hip_internal_rotation", 38 + r.normal(0, 1), 4, side="right")
    phone("hip_internal_rotation", 36 + r.normal(0, 1), 4, side="left")
    phone("hamstring_ake", 168 + r.normal(0, 1.5), 4, side="right")
    phone("hamstring_ake", 165 + r.normal(0, 1.5), 4, side="left")
    phone("single_leg_cmj", (jump_cm * 0.46) + r.normal(0, 0.3), 3, side="left")
    phone("single_leg_cmj", (jump_cm * 0.46) * 0.91 + r.normal(0, 0.3), 3, side="right")
    for t in tests:
        db.add(t)
    counts["tests"] = len(tests)

    # The ankle, a month on.
    clinician = "Team athletic trainer"
    inj, measures = _ankle_sprain(patient_id, today, clinician)
    db.add(inj)
    db.flush()
    for mrow in measures:
        mrow.injury_id = inj.id
        db.add(mrow)
    counts["measures"] = len(measures)

    # A line from the staff on the thread, two days ago.
    if org_id:
        note = Message(patient_id=patient_id, sender="care_team", channel="console",
                       text="Performance staff (Sports scientist): Hop symmetry cleared 90% on Friday, 92% both "
                            "ways. Full minutes from here. Keep the balance block in warm-ups three times a week "
                            "for the season, and the tape stays on for practice through November.",
                       authored_by="care_team", sender_id=patient.assigned_provider_id)
        note.created_at = datetime.combine(today - timedelta(days=2), time(16, 20))
        db.add(note)
        counts["messages"] = 1
    db.commit()
    return counts
