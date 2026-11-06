"""MedPull Sports routes.

Two routers. ``router`` is the athlete's app under ``/api/mobile/sports``:
joining, the home board, performance, recovery, rehab, logging, devices.
``team_router`` is the staff dashboard under ``/api/sports`` and follows
the console's posture (no authentication in this build, like every console
route): the roster board, an athlete's detail, a message to an athlete,
the calendar.
"""

from __future__ import annotations

import datetime as dt
import logging
import secrets
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api import mobile
from app.api.mobile import current_patient
from app.database import get_db
from app.models.mobile import Message
from app.models.patient import Device, Patient
from app.models.sports import (
    LEVEL_LABELS,
    SPORT_LABELS,
    SPORTS,
    STATUS_LABELS,
    STATUSES,
    SportsEvent,
    SportsInjury,
    SportsOrg,
    SportsProfile,
    SportsRehabMeasure,
    SportsSession,
    SportsStaff,
    SportsTeam,
    SportsTest,
)
from app.personal import auth
from app.personal.auth import AuthError
from app.personal.scope import is_sports
from app.sports import identity, insights, jump, plan, wellness
from app.sports.catalog import (
    CATEGORIES,
    DEVICES,
    INJURIES,
    MEASURES,
    TESTS,
    WELLNESS,
    device_view,
    devices_for,
    injuries_for,
    injury_view,
    measure_view,
    test_view,
    tests_for,
    wellness_view,
)
from app.sports.catalog.devices import CATEGORY_LABELS, PATH_LABELS
from app.sports.data import load_sports_data
from app.sports.identity import SportsIdentityError
from app.sports.performance import compute_performance
from app.sports.recovery import compute_recovery
from app.sports.rehab import availability_for, compute_rehab
from app.tasks import service as tasks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mobile/sports", tags=["sports"])
team_router = APIRouter(prefix="/sports", tags=["sports-team"])

POSITIONS = {
    "basketball": ["Point guard", "Guard", "Wing", "Forward", "Center"],
    "tennis": ["Singles", "Doubles", "Singles and doubles"],
    "soccer": ["Goalkeeper", "Center back", "Full back", "Defensive midfielder", "Central midfielder",
               "Attacking midfielder", "Winger", "Forward"],
}
CLASS_YEARS = ["Fr", "So", "Jr", "Sr", "Gr"]


# --- helpers -----------------------------------------------------------------------------------


def athlete(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)) -> Patient:
    if not is_sports(patient):
        raise HTTPException(status_code=403, detail="This is not a MedPull Sports account")
    if identity.profile_of(db, patient) is None:
        raise HTTPException(status_code=404, detail="No athlete profile on this account")
    return patient


def _profile(db: Session, patient: Patient) -> SportsProfile:
    profile = identity.profile_of(db, patient)
    if profile is None:
        raise HTTPException(status_code=404, detail="No athlete profile on this account")
    return profile


def compute_home(db: Session, patient: Patient, profile: SportsProfile, today: date | None = None) -> dict[str, Any]:
    """Every board at once: the data is loaded once and the three engines
    read it. The home, recovery, performance and rehab routes return slices."""
    data = load_sports_data(db, patient, profile, today)
    performance = compute_performance(data, patient.sex)
    rehab = compute_rehab(data)
    availability = availability_for(rehab["active"], profile.status)
    recovery = compute_recovery(data, patient, performance, availability)
    return {"data": data, "performance": performance, "rehab": rehab, "recovery": recovery,
            "availability": availability}


def _when(raw: Any) -> str:
    """An ISO timestamp as "today 6:40 am" / "Oct 19, 6:40 am"; anything else as "recently"."""
    if not raw:
        return "recently"
    try:
        stamp = datetime.fromisoformat(str(raw))
    except ValueError:
        return "recently"
    clock = stamp.strftime("%-I:%M %p").lower()
    if stamp.date() == date.today():
        return f"today {clock}"
    if stamp.date() == date.today() - timedelta(days=1):
        return f"yesterday {clock}"
    return f"{stamp.strftime('%b %-d')}, {clock}"


def _devices_view(db: Session, patient: Patient, profile: SportsProfile) -> dict[str, Any]:
    settings = profile.settings or {}
    connected: dict[str, Any] = settings.get("devices") or {}
    summary = mobile._wearable_summary(db, patient)
    linked = {d["provider"].lower(): d for d in summary.get("devices", [])}
    apple = summary.get("apple_health", {}).get("connected", False)
    out = []
    for spec in devices_for(profile.sport):
        state = "available"
        detail = None
        if spec.path == "healthkit":
            if spec.key == "apple_watch":
                state = "connected" if apple else "available"
                detail = "Reading through Apple Health" if apple else "Connect Apple Health and this flows in"
            elif connected.get(spec.key):
                state = "connected" if apple else "available"
                detail = "Reads through Apple Health" if apple else "Connect Apple Health and this flows in"
            else:
                detail = "Writes to Apple Health; add it here and it reads through"
        elif spec.path == "junction":
            slug = (spec.junction_slug or spec.key).split("_")[0]
            hit = linked.get(slug) or linked.get(spec.key)
            if hit:
                state = "connected"
                detail = f"Synced {_when(hit.get('last_sync_at'))}"
            elif connected.get(spec.key):
                state = "connected"
                detail = "Linked"
        elif spec.path in ("partner", "import", "ble"):
            if connected.get(spec.key):
                state = "sample" if spec.path == "partner" and connected[spec.key].get("mode") == "sample" else "connected"
                detail = connected[spec.key].get("detail")
        elif spec.path == "none":
            state = "unavailable"
        out.append({**device_view(spec), "state": state, "detail": detail})
    groups = []
    for cat, label in CATEGORY_LABELS.items():
        items = [d for d in out if d["category"] == cat]
        if items:
            groups.append({"key": cat, "label": label, "devices": items})
    return {"apple_health": summary.get("apple_health"), "aggregator_configured": summary.get("aggregator_configured"),
            "connected": sum(1 for d in out if d["state"] in ("connected", "sample")),
            "groups": groups, "paths": PATH_LABELS}


def _home_view(db: Session, patient: Patient, profile: SportsProfile, home: dict[str, Any], brief: dict[str, Any] | None,
               plan_written: dict[str, Any] | None) -> dict[str, Any]:
    rec = home["recovery"]
    perf = home["performance"]
    rehab = home["rehab"]
    open_tasks = tasks.open_tasks(db, patient.id)
    return {
        "as_of": rec["as_of"],
        "profile": identity.profile_view(db, patient, profile),
        "availability": home["availability"],
        "availability_label": STATUS_LABELS.get(home["availability"], home["availability"]),
        "verdict": rec["verdict"],
        "brief": brief,
        "readiness": rec["readiness"],
        "days_with_data": rec["days_with_data"],
        "wellness": {k: v for k, v in rec["wellness"].items() if k != "items"} | {"items": rec["wellness"]["items"]},
        "schedule": rec["schedule"],
        "suggestions": rec["suggestions"][:3],
        "suggestion_count": len(rec["suggestions"]),
        "neuromuscular": perf["neuromuscular"],
        "jumps": perf.get("jumps"),
        "load": rec["load"],
        "sleep": rec["panels"].get("sleep"),
        "hrv": rec["panels"].get("hrv"),
        "resting_hr": rec["panels"].get("resting_hr"),
        "performance_headline": perf["headline"][:6],
        "performance_logged": perf["logged"],
        "overall_percentile": perf.get("overall_percentile"),
        "asymmetries": perf["asymmetries"],
        "injuries": [{k: b[k] for k in ("id", "label", "side", "status", "days", "weeks", "symbol", "body_region")}
                     | {"phase": b.get("phase"), "rts": {kk: (b.get("rts") or {}).get(kk) for kk in ("met", "total", "pct", "projected")}
                        if b.get("rts") else None, "focus": (b.get("focus") or [])[:2]}
                     for b in rehab["active"]],
        "tasks": [mobile._task_view(t) for t in open_tasks],
        "plan": plan_written,
        "devices_connected": _devices_view(db, patient, profile)["connected"],
        "guardrail": "Performance and recovery guidance — return-to-play is your medical staff's call.",
    }


def _session_answer(db: Session, patient: Patient, body: Any) -> dict:
    first = mobile._first_enrollment(db, patient)
    token = mobile._issue_session(db, patient, body.device_name, body.app_version)
    if first:
        db.add(Message(patient_id=patient.id, sender="copilot", channel="app", authored_by="ai",
                       text="Welcome to MedPull Sports. Connect your watch, answer the morning questions, and "
                            "your readiness, load and performance picture builds from tonight."))
        db.commit()
    return {"status": "enrolled", "verified": False, "session_token": token, "me": mobile.me_view(db, patient)}


# --- catalog and organisations (public) --------------------------------------------------------------


@router.get("/orgs")
def orgs(q: str = "", db: Session = Depends(get_db)) -> dict:
    return {"orgs": identity.orgs_view(db, q)}


@router.get("/catalog")
def catalog(sport: str = "basketball") -> dict:
    if sport not in SPORTS:
        raise HTTPException(status_code=404, detail="Unknown sport")
    return {
        "sport": sport, "sport_label": SPORT_LABELS[sport],
        "sports": [{"key": s, "label": SPORT_LABELS[s]} for s in SPORTS],
        "positions": POSITIONS[sport], "class_years": CLASS_YEARS,
        "levels": [{"key": k, "label": v} for k, v in LEVEL_LABELS.items()],
        "statuses": [{"key": k, "label": STATUS_LABELS[k]} for k in STATUSES],
        "categories": CATEGORIES,
        "tests": [test_view(t) for t in tests_for(sport)],
        "injuries": [injury_view(i, full=False) for i in injuries_for(sport)],
        "measures": {k: measure_view(m) for k, m in MEASURES.items()},
        "wellness": [wellness_view(w) for w in WELLNESS.values()],
        "devices": [device_view(d) for d in devices_for(sport)],
        "device_categories": CATEGORY_LABELS, "device_paths": PATH_LABELS,
    }


@router.get("/catalog/injuries/{injury_key}")
def catalog_injury(injury_key: str) -> dict:
    spec = INJURIES.get(injury_key)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown injury")
    return injury_view(spec, full=True)


# --- joining -----------------------------------------------------------------------------------------


class JoinBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str
    password: str
    consent: mobile.ConsentAcceptance | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    sport: str
    org_id: str | None = None
    team_id: str | None = None
    join_code: str | None = None
    position: str | None = None
    jersey: str | None = None
    class_year: str | None = None
    level: str | None = None
    height_cm: float | None = Field(default=None, ge=100, le=250)
    weight_kg: float | None = Field(default=None, ge=30, le=200)
    wingspan_cm: float | None = Field(default=None, ge=100, le=270)
    standing_reach_cm: float | None = Field(default=None, ge=150, le=320)
    dominant_side: str | None = None
    units: str = "imperial"
    cycle_tracking: bool = False
    device_name: str | None = None
    app_version: str | None = None


@router.post("/join")
def join(body: JoinBody, db: Session = Depends(get_db)) -> dict:
    try:
        email = auth.normalize_email(body.email)
        auth.check_password(body.password)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    if email is None:
        raise HTTPException(status_code=422, detail="Enter your email address")
    if auth.credential_for_email(db, email) is not None:
        raise HTTPException(status_code=409, detail="That email already has an account — sign in instead")
    if body.sport not in SPORTS:
        raise HTTPException(status_code=422, detail="Pick your sport")
    if body.consent is None:
        raise HTTPException(status_code=422, detail="Read and agree to the beta consent first")
    try:
        auth.validate_scopes(body.consent.scopes)
        if body.consent.version != auth.CONSENT_VERSION:
            raise AuthError("The consent form has changed — read the new version and agree again", 409)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    phone = None
    if body.phone and body.phone.strip():
        from app.notifications import sendblue

        phone = sendblue.normalize_phone(body.phone)
        if phone is None:
            raise HTTPException(status_code=422, detail="Enter a valid mobile number, or leave it out")
    try:
        patient, _profile_row = identity.create_sports_account(
            db, name=body.name, sport=body.sport, phone=phone, sex=body.sex, date_of_birth=body.date_of_birth,
            org_id=body.org_id, team_id=body.team_id, position=body.position, jersey=body.jersey,
            class_year=body.class_year, level=body.level, height_cm=body.height_cm, weight_kg=body.weight_kg,
            wingspan_cm=body.wingspan_cm, standing_reach_cm=body.standing_reach_cm,
            dominant_side=body.dominant_side, units=body.units, cycle_tracking=body.cycle_tracking,
            join_code=body.join_code,
        )
        auth.create_credential(db, patient, email, body.password)
        auth.record_consent(db, patient, version=body.consent.version, scopes=body.consent.scopes,
                            signature=body.consent.signature, device_name=body.device_name,
                            app_version=body.app_version)
    except SportsIdentityError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    db.commit()
    return _session_answer(db, patient, body)


class LoginBody(BaseModel):
    email: str
    password: str
    device_name: str | None = None
    app_version: str | None = None


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)) -> dict:
    """Any account with an email login (sports or personal): the app reads
    ``me.patient.account_kind`` and shows the right home."""
    try:
        email = auth.normalize_email(body.email)
        if email is None:
            raise AuthError("Enter your email address", 422)
        patient = auth.authenticate(db, email, body.password)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    token = mobile._issue_session(db, patient, body.device_name, body.app_version)
    return {"status": "enrolled", "verified": True, "session_token": token, "me": mobile.me_view(db, patient)}


# --- the boards --------------------------------------------------------------------------------------


@router.get("/home")
def home(patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    profile = _profile(db, patient)
    h = compute_home(db, patient, profile)
    brief = insights.get_brief(db, patient, profile, h["recovery"], h["performance"], h["rehab"], allow_llm=False)
    return _home_view(db, patient, profile, h, brief, None)


class DayBody(BaseModel):
    pass


@router.post("/day")
def start_day(patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    """Open the day: write today's plan, generate the brief, return the home."""
    profile = _profile(db, patient)
    h = compute_home(db, patient, profile)
    written = plan.ensure_daily_plan(db, patient, h["recovery"], h["rehab"])
    brief = insights.get_brief(db, patient, profile, h["recovery"], h["performance"], h["rehab"])
    return _home_view(db, patient, profile, h, brief, written)


@router.get("/recovery")
def recovery(patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    profile = _profile(db, patient)
    h = compute_home(db, patient, profile)
    rec = h["recovery"]
    return {k: v for k, v in rec.items() if k not in ("digest",)} | {"availability": h["availability"]}


@router.get("/performance")
def performance(patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    profile = _profile(db, patient)
    h = compute_home(db, patient, profile)
    perf = h["performance"]
    brief = insights.get_performance_brief(db, patient, profile, perf, patient.sex)
    return perf | {"brief": brief}


def _with_reads(db: Session, patient: Patient, profile: SportsProfile, rehab: dict[str, Any]) -> dict[str, Any]:
    active = [b | {"read": insights.get_injury_read(db, patient, profile, b)} for b in rehab.get("active") or []]
    return rehab | {"active": active}


@router.get("/rehab")
def rehab(patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    profile = _profile(db, patient)
    h = compute_home(db, patient, profile)
    return _with_reads(db, patient, profile, h["rehab"]) | {
        "availability": h["availability"],
        "catalog": [injury_view(i, full=False) for i in injuries_for(profile.sport)]}


# --- logging -----------------------------------------------------------------------------------------


class WellnessBody(BaseModel):
    answers: dict[str, Any]
    date: dt.date | None = None


@router.post("/wellness")
def log_wellness(body: WellnessBody, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    when = body.date or date.today()
    if when > date.today() or when < date.today() - timedelta(days=30):
        raise HTTPException(status_code=422, detail="Log within the last month")
    written = wellness.record_many(db, patient.id, when, body.answers, source="app")
    if written == 0:
        raise HTTPException(status_code=422, detail="Nothing to log")
    # Completing the day's check-in task closes the loop on the plan.
    for task in tasks.open_tasks(db, patient.id):
        if tasks.question_set_key(task) == "checkin_sports" and when == date.today():
            try:
                tasks.complete_task(db, task, {k: v for k, v in body.answers.items() if k in
                                               ("sleep_quality", "fatigue", "soreness", "stress", "mood", "pain", "note")},
                                    via="app")
            except ValueError:
                pass
            break
    db.commit()
    profile = _profile(db, patient)
    h = compute_home(db, patient, profile)
    return {"ok": True, "written": written, "wellness": h["recovery"]["wellness"], "verdict": h["recovery"]["verdict"],
            "suggestions": h["recovery"]["suggestions"][:3]}


class SessionBody(BaseModel):
    date: dt.date | None = None
    kind: str = "practice"
    minutes: float = Field(ge=1, le=600)
    rpe: float | None = Field(default=None, ge=0, le=10)
    jumps: int | None = Field(default=None, ge=0, le=2000)
    player_load: float | None = None
    distance_m: float | None = None
    high_speed_m: float | None = None
    max_speed_kmh: float | None = None
    average_hr: float | None = None
    note: str | None = Field(default=None, max_length=400)
    source: str = "manual"


@router.post("/sessions")
def log_session(body: SessionBody, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    when = body.date or date.today()
    if when > date.today() or when < date.today() - timedelta(days=60):
        raise HTTPException(status_code=422, detail="Log within the last two months")
    row = SportsSession(patient_id=patient.id, date=when, kind=body.kind[:24], minutes=body.minutes, rpe=body.rpe,
                        load_au=(body.minutes * body.rpe) if body.rpe is not None else None, jumps=body.jumps,
                        player_load=body.player_load, distance_m=body.distance_m, high_speed_m=body.high_speed_m,
                        max_speed_kmh=body.max_speed_kmh, average_hr=body.average_hr, note=body.note,
                        source=body.source[:24])
    db.add(row)
    # A matching plan item is done.
    for task in tasks.open_tasks(db, patient.id):
        tag = (task.payload or {}).get("sports") or {}
        if str(tag.get("key", "")).startswith("log_") and when == date.today():
            try:
                tasks.complete_task(db, task, {"minutes": int(body.minutes), "rpe": int(body.rpe or 0)}, via="app")
            except ValueError:
                pass
            break
    db.commit()
    return {"ok": True, "id": row.id, "load_au": row.load_au}


@router.get("/sessions")
def list_sessions(days: int = 28, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    since = date.today() - timedelta(days=max(1, min(days, 180)))
    rows = db.scalars(select(SportsSession).where(SportsSession.patient_id == patient.id, SportsSession.date >= since)
                      .order_by(SportsSession.date.desc(), SportsSession.id.desc())).all()
    return {"sessions": [_session_view(s) for s in rows]}


def _session_view(s: SportsSession) -> dict[str, Any]:
    return {"id": s.id, "date": s.date.isoformat(), "kind": s.kind, "minutes": s.minutes, "rpe": s.rpe,
            "load_au": s.load_au, "jumps": s.jumps, "player_load": s.player_load, "distance_m": s.distance_m,
            "high_speed_m": s.high_speed_m, "max_speed_kmh": s.max_speed_kmh, "average_hr": s.average_hr,
            "source": s.source, "note": s.note}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    row = db.get(SportsSession, session_id)
    if row is None or row.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Unknown session")
    db.delete(row)
    db.commit()
    return {"ok": True}


class TestEntry(BaseModel):
    test_key: str
    value: float
    side: str | None = None
    date: dt.date | None = None
    source: str = "manual"
    device: str | None = None
    note: str | None = Field(default=None, max_length=300)


class TestsBody(BaseModel):
    entries: list[TestEntry] = Field(min_length=1, max_length=40)


@router.post("/tests")
def log_tests(body: TestsBody, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    ids = []
    for e in body.entries:
        spec = TESTS.get(e.test_key)
        if spec is None:
            raise HTTPException(status_code=422, detail=f"Unknown test {e.test_key}")
        if spec.sided and e.side not in ("left", "right"):
            raise HTTPException(status_code=422, detail=f"{spec.label} is logged per side")
        when = e.date or date.today()
        if when > date.today():
            raise HTTPException(status_code=422, detail="A test cannot be in the future")
        row = SportsTest(patient_id=patient.id, date=when, test_key=e.test_key, value=float(e.value), unit=spec.unit,
                         side=e.side if spec.sided else None, source=e.source[:24], device=(e.device or "")[:60] or None,
                         note=e.note)
        db.add(row)
        db.flush()
        ids.append(row.id)
        # A rehab measure with the same meaning (quad strength, single-leg jump…) is written too,
        # against every active injury on the matching side.
        for mkey, mspec in MEASURES.items():
            if mspec.test_key == e.test_key:
                for inj in db.scalars(select(SportsInjury).where(SportsInjury.patient_id == patient.id,
                                                                 SportsInjury.status == "active")).all():
                    db.add(SportsRehabMeasure(injury_id=inj.id, patient_id=patient.id, date=when, measure_key=mkey,
                                              value=float(e.value), unit=mspec.unit,
                                              side=e.side if mspec.sided else None, source=e.source[:24]))
    db.commit()
    profile = _profile(db, patient)
    h = compute_home(db, patient, profile)
    return {"ok": True, "ids": ids, "performance": h["performance"]}


@router.delete("/tests/{test_id}")
def delete_test(test_id: int, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    row = db.get(SportsTest, test_id)
    if row is None or row.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Unknown test")
    db.delete(row)
    db.commit()
    return {"ok": True}


class JumpBody(BaseModel):
    accel: list[list[float]] = Field(min_length=10, max_length=20000)
    sample_rate_hz: float = Field(gt=10, le=400)
    test_key: str = "phone_jump_height"
    side: str | None = None
    recorded_at: datetime | None = None
    device_model: str | None = None
    save: bool = True


@router.post("/tests/jump")
def phone_jump(body: JumpBody, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    spec = TESTS.get(body.test_key)
    if spec is None or not spec.phone or spec.unit != "cm":
        raise HTTPException(status_code=422, detail="That test is not a phone jump test")
    try:
        result = jump.estimate_jump(body.accel, body.sample_rate_hz)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not jump.is_plausible_jump(result["height_cm"]):
        raise HTTPException(status_code=422, detail="That reading isn't plausible. Try again with the phone against your chest.")
    saved_id = None
    if body.save:
        if spec.sided and body.side not in ("left", "right"):
            raise HTTPException(status_code=422, detail="Say which leg")
        row = SportsTest(patient_id=patient.id, date=(body.recorded_at or datetime.now()).date(), test_key=body.test_key,
                         value=result["height_cm"], unit="cm", side=body.side if spec.sided else None, source="phone",
                         device=(body.device_model or "iPhone")[:60], detail=result)
        db.add(row)
        db.flush()
        saved_id = row.id
        for mkey, mspec in MEASURES.items():
            if mspec.test_key == body.test_key:
                for inj in db.scalars(select(SportsInjury).where(SportsInjury.patient_id == patient.id,
                                                                 SportsInjury.status == "active")).all():
                    db.add(SportsRehabMeasure(injury_id=inj.id, patient_id=patient.id, date=row.date, measure_key=mkey,
                                              value=result["height_cm"], unit="cm",
                                              side=body.side if mspec.sided else None, source="phone"))
        db.commit()
    return {"ok": True, "id": saved_id, **result, "height_in": jump.height_in(result["height_cm"])}


class BalanceBody(BaseModel):
    gravity: list[list[float]] = Field(min_length=10, max_length=20000)
    sample_rate_hz: float = Field(gt=10, le=400)
    side: str
    seconds_held: float | None = None
    save: bool = True


@router.post("/tests/balance")
def phone_balance(body: BalanceBody, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    if body.side not in ("left", "right"):
        raise HTTPException(status_code=422, detail="Say which leg")
    try:
        result = jump.estimate_balance(body.gravity, body.sample_rate_hz)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    seconds = body.seconds_held if body.seconds_held is not None else result["seconds"]
    saved_id = None
    if body.save:
        row = SportsTest(patient_id=patient.id, date=date.today(), test_key="single_leg_balance", value=float(seconds),
                         unit="s", side=body.side, source="phone", detail=result)
        db.add(row)
        db.flush()
        saved_id = row.id
        for inj in db.scalars(select(SportsInjury).where(SportsInjury.patient_id == patient.id,
                                                         SportsInjury.status == "active")).all():
            db.add(SportsRehabMeasure(injury_id=inj.id, patient_id=patient.id, date=date.today(),
                                      measure_key="single_leg_balance_s", value=float(seconds), unit="s",
                                      side=body.side, source="phone"))
        db.commit()
    return {"ok": True, "id": saved_id, "seconds": seconds, **result}


# --- injuries ----------------------------------------------------------------------------------------


class InjuryBody(BaseModel):
    injury_key: str
    side: str | None = None
    date_of_injury: dt.date
    date_of_surgery: dt.date | None = None
    graft: str | None = None
    grade: str | None = None
    mechanism: str | None = Field(default=None, max_length=200)
    clinician: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=600)
    target_return_date: dt.date | None = None


@router.post("/injuries")
def report_injury(body: InjuryBody, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    spec = INJURIES.get(body.injury_key)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown injury")
    if body.date_of_injury > date.today():
        raise HTTPException(status_code=422, detail="The injury date cannot be in the future")
    if body.date_of_surgery and body.date_of_surgery < body.date_of_injury:
        raise HTTPException(status_code=422, detail="Surgery comes after the injury")
    row = SportsInjury(patient_id=patient.id, injury_key=spec.key, label=spec.label,
                       side=body.side if body.side in ("left", "right") else None, body_region=spec.body_region,
                       date_of_injury=body.date_of_injury, date_of_surgery=body.date_of_surgery, graft=body.graft,
                       grade=body.grade, mechanism=body.mechanism, clinician=body.clinician, note=body.note,
                       target_return_date=body.target_return_date, status="active")
    db.add(row)
    # A surgical injury anchors the clinic engine's recovery curve and care
    # metrics on the operation.
    if body.date_of_surgery and spec.procedure_type:
        patient.procedure_type = spec.procedure_type
        patient.procedure_display = spec.label
        patient.surgery_date = body.date_of_surgery
        patient.discharge_date = body.date_of_surgery
        patient.care_pathway = None
    profile = _profile(db, patient)
    db.commit()
    h = compute_home(db, patient, profile)
    profile.status = h["availability"]
    db.commit()
    return {"ok": True, "id": row.id, "rehab": h["rehab"]}


class InjuryPatch(BaseModel):
    status: str | None = None          # active | cleared | resolved
    phase_override: int | None = Field(default=None, ge=0, le=8)
    target_return_date: dt.date | None = None
    note: str | None = Field(default=None, max_length=600)
    clinician: str | None = None


@router.patch("/injuries/{injury_id}")
def update_injury(injury_id: int, body: InjuryPatch, patient: Patient = Depends(athlete),
                  db: Session = Depends(get_db)) -> dict:
    row = db.get(SportsInjury, injury_id)
    if row is None or row.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Unknown injury")
    if body.status is not None:
        if body.status not in ("active", "cleared", "resolved"):
            raise HTTPException(status_code=422, detail="Unknown status")
        row.status = body.status
        if body.status != "active":
            row.cleared_at = date.today()
    if body.phase_override is not None:
        row.phase_override = body.phase_override or None
    if body.target_return_date is not None:
        row.target_return_date = body.target_return_date
    if body.note is not None:
        row.note = body.note
    if body.clinician is not None:
        row.clinician = body.clinician[:120]
    profile = _profile(db, patient)
    if body.status is not None and body.status != "active":
        # Clearing the injury hands the roster status back to the engine:
        # the "out" it set when the injury was reported must not outlive it.
        profile.status = "available"
    db.commit()
    h = compute_home(db, patient, profile)
    if profile.status in ("available", "modified", "out"):
        profile.status = h["availability"] if row.status != "active" or profile.status != "out" else profile.status
        db.commit()
    return {"ok": True, "rehab": h["rehab"]}


class MeasureEntry(BaseModel):
    measure_key: str
    value: float
    side: str | None = None   # involved | uninvolved | left | right
    date: dt.date | None = None
    source: str = "manual"
    note: str | None = Field(default=None, max_length=300)


class MeasuresBody(BaseModel):
    entries: list[MeasureEntry] = Field(min_length=1, max_length=40)


@router.post("/injuries/{injury_id}/measures")
def log_measures(injury_id: int, body: MeasuresBody, patient: Patient = Depends(athlete),
                 db: Session = Depends(get_db)) -> dict:
    inj = db.get(SportsInjury, injury_id)
    if inj is None or inj.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Unknown injury")
    for e in body.entries:
        spec = MEASURES.get(e.measure_key)
        if spec is None:
            raise HTTPException(status_code=422, detail=f"Unknown measure {e.measure_key}")
        if spec.sided and e.side not in ("involved", "uninvolved", "left", "right"):
            raise HTTPException(status_code=422, detail=f"{spec.label} is logged per side")
        when = e.date or date.today()
        if when > date.today():
            raise HTTPException(status_code=422, detail="A measure cannot be in the future")
        db.add(SportsRehabMeasure(injury_id=inj.id, patient_id=patient.id, date=when, measure_key=e.measure_key,
                                  value=float(e.value), unit=spec.unit, side=e.side if spec.sided else None,
                                  source=e.source[:24], note=e.note))
        if spec.test_key and TESTS.get(spec.test_key):
            tspec = TESTS[spec.test_key]
            side = e.side
            if side in ("involved", "uninvolved") and inj.side:
                side = inj.side if side == "involved" else ("left" if inj.side == "right" else "right")
            if not tspec.sided or side in ("left", "right"):
                db.add(SportsTest(patient_id=patient.id, date=when, test_key=spec.test_key, value=float(e.value),
                                  unit=tspec.unit, side=side if tspec.sided else None, source=e.source[:24]))
    db.commit()
    profile = _profile(db, patient)
    h = compute_home(db, patient, profile)
    board = next((b for b in h["rehab"]["active"] + h["rehab"]["past"] if b["id"] == inj.id), None)
    if profile.status != "out" or h["availability"] != "out":
        profile.status = h["availability"]
        db.commit()
    return {"ok": True, "injury": board}


# --- profile, organisation, devices ------------------------------------------------------------------------


@router.get("/profile")
def get_profile(patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    return {"profile": identity.profile_view(db, patient, _profile(db, patient))}


class ProfilePatch(BaseModel):
    position: str | None = None
    jersey: str | None = None
    class_year: str | None = None
    level: str | None = None
    height_cm: float | None = Field(default=None, ge=100, le=250)
    weight_kg: float | None = Field(default=None, ge=30, le=200)
    wingspan_cm: float | None = Field(default=None, ge=100, le=270)
    standing_reach_cm: float | None = Field(default=None, ge=150, le=320)
    dominant_side: str | None = None
    units: str | None = None
    cycle_tracking: bool | None = None
    status: str | None = None
    status_note: str | None = None


@router.patch("/profile")
def patch_profile(body: ProfilePatch, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    profile = _profile(db, patient)
    for field in ("position", "jersey", "class_year", "height_cm", "weight_kg", "wingspan_cm", "standing_reach_cm",
                  "cycle_tracking", "status_note"):
        value = getattr(body, field)
        if value is not None:
            setattr(profile, field, value.strip()[:60] if isinstance(value, str) else value)
    if body.level in LEVEL_LABELS:
        profile.level = body.level
    if body.dominant_side in ("left", "right"):
        profile.dominant_side = body.dominant_side
    if body.units in ("metric", "imperial"):
        profile.units = body.units
    if body.status in STATUSES:
        profile.status = body.status
    if body.weight_kg is not None:
        wellness.record(db, patient.id, date.today(), "body_mass_kg", value=body.weight_kg, source="app")
    db.commit()
    return {"profile": identity.profile_view(db, patient, profile)}


class OrgJoinBody(BaseModel):
    org_id: str
    team_id: str | None = None
    join_code: str | None = None
    position: str | None = None


@router.post("/org/join")
def org_join(body: OrgJoinBody, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    profile = _profile(db, patient)
    try:
        identity.join_org(db, profile, org_id=body.org_id, team_id=body.team_id, join_code=body.join_code,
                          position=body.position)
    except SportsIdentityError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    return {"profile": identity.profile_view(db, patient, profile), "me": mobile.me_view(db, patient)}


@router.post("/org/leave")
def org_leave(patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    profile = _profile(db, patient)
    identity.leave_org(db, profile)
    return {"profile": identity.profile_view(db, patient, profile), "me": mobile.me_view(db, patient)}


@router.get("/devices")
def devices(patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    return _devices_view(db, patient, _profile(db, patient))


class DeviceConnectBody(BaseModel):
    mode: str = "sample"   # sample | import | live


@router.post("/devices/{key}/connect")
def connect_device(key: str, body: DeviceConnectBody | None = None, patient: Patient = Depends(athlete),
                   db: Session = Depends(get_db)) -> dict:
    spec = DEVICES.get(key)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown device")
    profile = _profile(db, patient)
    if spec.path == "junction":
        # The real thing: Junction's hosted link page, when the server has a key.
        try:
            link = mobile.wearable_link(patient, db)
            return {"ok": True, "link_url": link.get("link_url"), "state": "linking"}
        except HTTPException as e:
            # No aggregator on this server: record the intent so the screen shows it.
            settings = dict(profile.settings or {})
            devs = dict(settings.get("devices") or {})
            devs[key] = {"mode": "sample", "detail": "Marked as connected; this server has no wearable aggregator key",
                         "at": datetime.now().isoformat()}
            settings["devices"] = devs
            profile.settings = settings
            db.commit()
            return {"ok": True, "state": "sample", "detail": e.detail}
    if spec.path == "none":
        raise HTTPException(status_code=409, detail=spec.note or "Not available on iPhone")
    if spec.path == "healthkit":
        return {"ok": True, "state": "healthkit", "detail": "Connect Apple Health; this device writes to it."}
    settings = dict(profile.settings or {})
    devs = dict(settings.get("devices") or {})
    mode = (body.mode if body else "sample")
    detail = {"sample": "Connected by your program — sample data until the credential is keyed",
              "import": "Import ready: drop the export file and the results land on your Stats tab",
              "live": "Connected"}.get(mode, "Connected")
    devs[key] = {"mode": mode, "detail": detail, "at": datetime.now().isoformat()}
    settings["devices"] = devs
    profile.settings = settings
    db.commit()
    return {"ok": True, "state": "sample" if mode == "sample" else "connected", "detail": detail}


@router.delete("/devices/{key}")
def disconnect_device(key: str, patient: Patient = Depends(athlete), db: Session = Depends(get_db)) -> dict:
    profile = _profile(db, patient)
    settings = dict(profile.settings or {})
    devs = dict(settings.get("devices") or {})
    devs.pop(key, None)
    settings["devices"] = devs
    profile.settings = settings
    db.commit()
    return {"ok": True}


# =====================================================================================================
# The team dashboard
# =====================================================================================================


def _team_or_404(db: Session, team_id: str) -> SportsTeam:
    team = db.get(SportsTeam, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Unknown team")
    return team


def _roster(db: Session, team: SportsTeam) -> list[tuple[Patient, SportsProfile]]:
    rows = db.execute(
        select(Patient, SportsProfile).join(SportsProfile, SportsProfile.patient_id == Patient.id)
        .where(SportsProfile.team_id == team.id, SportsProfile.coach_linked.is_(True))
        .order_by(Patient.name)
    ).all()
    return [(p, pr) for p, pr in rows]


def _athlete_row(db: Session, patient: Patient, profile: SportsProfile, h: dict[str, Any]) -> dict[str, Any]:
    rec = h["recovery"]
    perf = h["performance"]
    rehab = h["rehab"]
    panels = rec["panels"]
    readiness = panels.get("readiness") or {}
    rx = readiness.get("extra") or {}
    sleep = panels.get("sleep") or {}
    sx = sleep.get("extra") or {}
    hrv = panels.get("hrv") or {}
    hx = hrv.get("extra") or {}
    rhr = panels.get("resting_hr") or {}
    rhx = rhr.get("extra") or {}
    wellness_p = rec["wellness"]
    flags = []
    if readiness.get("status") == "flag":
        flags.append({"key": "readiness", "status": "flag", "text": readiness.get("status_text")})
    for key, p in (("sleep", sleep), ("hrv", hrv), ("resting_hr", rhr), ("body", panels.get("body") or {})):
        if p.get("status") in ("watch", "flag"):
            flags.append({"key": key, "status": p["status"], "text": p.get("status_text")})
    if wellness_p["status"] in ("watch", "flag"):
        flags.append({"key": "wellness", "status": wellness_p["status"], "text": wellness_p["status_text"]})
    if rec["load"]["status"] in ("watch", "flag"):
        flags.append({"key": "load", "status": rec["load"]["status"], "text": rec["load"]["status_text"]})
    neuro = perf["neuromuscular"]
    if neuro["status"] in ("watch", "flag"):
        flags.append({"key": "neuromuscular", "status": neuro["status"], "text": neuro["status_text"]})
    if rec["illness"]["status"] in ("watch", "flag"):
        flags.append({"key": "illness", "status": rec["illness"]["status"], "text": "Illness watch"})
    for a in perf["asymmetries"]:
        flags.append({"key": "asymmetry", "status": a["status"], "text": f"{a['label']} {a['asymmetry']['pct']:.0f}% asym"})
    severity = max([{"ok": 0, "watch": 1, "flag": 2}[f["status"]] for f in flags] + [0])
    staff_action = None
    tips = rec["suggestions"]
    if h["availability"] == "out":
        board = rehab["active"][0] if rehab["active"] else None
        staff_action = (f"Rehab: {board['phase']['name'].lower()}, {board['rts']['met']}/{board['rts']['total']} RTS criteria"
                        if board and board.get("phase") else "Rehab")
    elif tips and tips[0]["key"] not in ("green",):
        staff_action = tips[0]["title"]
    cmj = perf["cards"].get("cmj_height")
    return {
        "id": patient.id, "name": patient.name, "first_name": patient.name.split()[0], "initials": patient.initials,
        "position": profile.position, "jersey": profile.jersey, "class_year": profile.class_year,
        "availability": h["availability"], "availability_label": STATUS_LABELS.get(h["availability"], h["availability"]),
        "status_note": profile.status_note,
        "verdict": rec["verdict"],
        "readiness": rx.get("score"), "readiness_band": rx.get("band"), "readiness_status": readiness.get("status"),
        "readiness_series": [p["value"] for p in (readiness.get("series") or [])[-14:]],
        "sleep_hours": sx.get("last_night_hours"), "sleep_need": sx.get("need_hours"), "sleep_debt": sx.get("debt_hours"),
        "hrv_z": hx.get("z_latest"), "hrv_latest": hx.get("latest"), "hrv_baseline": hx.get("baseline_mean"),
        "rhr_delta": rhx.get("delta_7d"), "rhr_latest": rhx.get("latest"),
        "wellness_z": wellness_p.get("composite_z"), "hooper": wellness_p.get("hooper"),
        "wellness_answered_today": wellness_p.get("answered_today", 0) > 0,
        "soreness": next((i["value"] for i in wellness_p["items"] if i["key"] == "soreness"), None),
        "load_week": rec["load"].get("week_load"), "load_change_pct": rec["load"].get("change_pct"),
        "monotony": rec["load"].get("monotony"), "acwr": rec["load"].get("acwr"),
        "jumps_week": (perf.get("jumps") or {}).get("week"),
        "cmj": cmj["latest"] if cmj else None, "cmj_change_pct": (cmj.get("baseline") or {}).get("pct") if cmj else None,
        "neuromuscular": neuro["status"],
        "flags": flags, "severity": severity, "staff_action": staff_action,
        "injuries": [{"id": b["id"], "label": b["label"], "side": b["side"], "weeks": b["weeks"],
                      "phase": b.get("phase"), "rts": {k: (b.get("rts") or {}).get(k) for k in ("met", "total", "pct", "projected")}}
                     for b in rehab["active"]],
        "days_with_data": rec["days_with_data"],
    }


@team_router.get("/teams")
def teams(db: Session = Depends(get_db)) -> dict:
    orgs = identity.orgs_view(db)
    counts = dict(db.execute(select(SportsProfile.team_id, func.count()).where(SportsProfile.team_id.is_not(None),
                                                                                 SportsProfile.coach_linked.is_(True))
                             .group_by(SportsProfile.team_id)).all())
    for o in orgs:
        for t in o["teams"]:
            t["roster"] = counts.get(t["id"], 0)
    return {"orgs": orgs}


@team_router.get("/teams/{team_id}/dashboard")
def team_dashboard(team_id: str, db: Session = Depends(get_db)) -> dict:
    team = _team_or_404(db, team_id)
    org = db.get(SportsOrg, team.org_id)
    today = date.today()
    rows = []
    boards: dict[str, dict[str, Any]] = {}
    for patient, profile in _roster(db, team):
        try:
            h = compute_home(db, patient, profile)
        except Exception:  # noqa: BLE001 — one athlete must not blank the board
            logger.exception("team board failed for %s", patient.id)
            continue
        boards[patient.id] = h
        rows.append(_athlete_row(db, patient, profile, h))
    rows.sort(key=lambda r: (-(r["severity"]), r["availability"] != "out", r["name"]))
    available = sum(1 for r in rows if r["availability"] == "available")
    modified = sum(1 for r in rows if r["availability"] == "modified")
    out = sum(1 for r in rows if r["availability"] == "out")
    scores = [r["readiness"] for r in rows if r["readiness"] is not None]
    answered = sum(1 for r in rows if r["wellness_answered_today"])
    events = db.scalars(select(SportsEvent).where(SportsEvent.team_id == team.id, SportsEvent.date >= today - timedelta(days=7),
                                                  SportsEvent.date <= today + timedelta(days=14))
                        .order_by(SportsEvent.date, SportsEvent.start_time)).all()
    # Team load: the sum of session load by day over four weeks.
    since = today - timedelta(days=27)
    load_rows = db.execute(select(SportsSession.date, func.sum(SportsSession.load_au), func.sum(SportsSession.jumps))
                           .join(SportsProfile, SportsProfile.patient_id == SportsSession.patient_id)
                           .where(SportsProfile.team_id == team.id, SportsSession.date >= since)
                           .group_by(SportsSession.date).order_by(SportsSession.date)).all()
    n = max(len(rows), 1)
    load_series = [{"date": d.isoformat(), "load_per_athlete": round(float(load or 0) / n),
                    "jumps_per_athlete": round(float(jumps or 0) / n)}
                   for d, load, jumps in load_rows]
    staff = db.scalars(select(SportsStaff).where(SportsStaff.org_id == team.org_id,
                                                 (SportsStaff.team_id == team.id) | (SportsStaff.team_id.is_(None)))
                       .order_by(SportsStaff.name)).all()
    injuries = [{"athlete_id": r["id"], "name": r["name"], "position": r["position"], **inj}
                for r in rows for inj in r["injuries"]]
    attention = [r for r in rows if r["severity"] >= 1 or r["availability"] != "available"][:8]
    briefing = _team_briefing(rows, events, today)
    return {
        "team": identity.team_view(team), "org": identity.org_view(org) if org else None,
        "as_of": today.isoformat(),
        "summary": {"roster": len(rows), "available": available, "modified": modified, "out": out,
                    "mean_readiness": round(sum(scores) / len(scores)) if scores else None,
                    "answered_today": answered, "flags": sum(len(r["flags"]) for r in rows)},
        "briefing": briefing,
        "attention": attention,
        "roster": rows,
        "injuries": injuries,
        "events": [_event_view(e) for e in events],
        "load": load_series,
        "staff": [identity.staff_view(s) for s in staff],
        "guardrail": "Monitoring for staff review — return-to-play decisions belong to the medical staff.",
    }


def _team_briefing(rows: list[dict[str, Any]], events: list[SportsEvent], today: date) -> dict[str, Any]:
    game = next((e for e in events if e.date == today and e.kind in ("game", "match")), None)
    next_game = next((e for e in sorted(events, key=lambda e: e.date) if e.date > today and e.kind in ("game", "match")), None)
    low = [r for r in rows if r["readiness"] is not None and r["readiness"] < 34]
    watch = [r for r in rows if r["severity"] >= 1 and r["availability"] == "available"]
    out = [r for r in rows if r["availability"] == "out"]
    parts = []
    if game:
        parts.append(f"Game day vs {game.opponent or game.title}.")
    elif next_game:
        d = (next_game.date - today).days
        parts.append(f"Next game in {d} day{'s' if d != 1 else ''}" + (f" vs {next_game.opponent}" if next_game.opponent else "") + ".")
    if out:
        parts.append(f"{len(out)} out: " + ", ".join(r["first_name"] for r in out) + ".")
    if low:
        parts.append(f"{len(low)} under a readiness of 34: " + ", ".join(r["first_name"] for r in low[:4]) + ".")
    elif watch:
        parts.append(f"{len(watch)} worth a look: " + ", ".join(f"{r['first_name']} ({r['flags'][0]['text'].lower()})" for r in watch[:4]) + ".")
    else:
        parts.append("Nobody is flagged this morning.")
    answered = sum(1 for r in rows if r["wellness_answered_today"])
    parts.append(f"{answered} of {len(rows)} have answered the morning questions.")
    headline = ("Game day" if game else f"{len(out)} out, {len(watch)} to watch" if (out or watch) else "A quiet morning")
    return {"headline": headline, "text": " ".join(parts)}


def _event_view(e: SportsEvent) -> dict[str, Any]:
    return {"id": e.id, "date": e.date.isoformat(), "start_time": e.start_time, "kind": e.kind, "title": e.title,
            "opponent": e.opponent, "home": e.home, "location": e.location, "note": e.note}


@team_router.get("/teams/{team_id}/athletes/{patient_id}")
def team_athlete(team_id: str, patient_id: str, db: Session = Depends(get_db)) -> dict:
    team = _team_or_404(db, team_id)
    patient = db.get(Patient, patient_id)
    profile = identity.profile_of(db, patient) if patient else None
    if patient is None or profile is None or profile.team_id != team.id:
        raise HTTPException(status_code=404, detail="Unknown athlete on this team")
    h = compute_home(db, patient, profile)
    row = _athlete_row(db, patient, profile, h)
    brief = insights.get_brief(db, patient, profile, h["recovery"], h["performance"], h["rehab"], allow_llm=False)
    thread = db.scalars(select(Message).where(Message.patient_id == patient.id).order_by(Message.created_at.desc()).limit(30)).all()
    sessions = db.scalars(select(SportsSession).where(SportsSession.patient_id == patient.id,
                                                      SportsSession.date >= date.today() - timedelta(days=28))
                          .order_by(SportsSession.date.desc())).all()
    rec = h["recovery"]
    return {
        "team": identity.team_view(team), "athlete": row,
        "profile": identity.profile_view(db, patient, profile),
        "brief": brief,
        "recovery": {k: v for k, v in rec.items() if k not in ("digest",)},
        "performance": h["performance"],
        "rehab": h["rehab"],
        "sessions": [_session_view(s) for s in sessions],
        "tasks": [mobile._task_view(t) for t in tasks.open_tasks(db, patient.id)],
        "thread": [mobile._message_view(m, {}) for m in reversed(thread)],
    }


class StaffMessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    staff_id: str | None = None


@team_router.post("/teams/{team_id}/athletes/{patient_id}/message")
def staff_message(team_id: str, patient_id: str, body: StaffMessageBody, db: Session = Depends(get_db)) -> dict:
    team = _team_or_404(db, team_id)
    patient = db.get(Patient, patient_id)
    profile = identity.profile_of(db, patient) if patient else None
    if patient is None or profile is None or profile.team_id != team.id:
        raise HTTPException(status_code=404, detail="Unknown athlete on this team")
    staff = db.get(SportsStaff, body.staff_id) if body.staff_id else None
    text = body.text.strip()
    if staff is not None:
        text = f"{staff.name} ({identity.STAFF_ROLE_LABELS.get(staff.role, staff.role)}): {text}"
    m = Message(patient_id=patient.id, sender="care_team", channel="console", text=text[:2000], authored_by="care_team",
                sender_id=patient.assigned_provider_id)
    db.add(m)
    db.commit()
    return {"ok": True, "id": m.id}


class StatusBody(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=300)


@team_router.patch("/teams/{team_id}/athletes/{patient_id}/status")
def staff_status(team_id: str, patient_id: str, body: StatusBody, db: Session = Depends(get_db)) -> dict:
    team = _team_or_404(db, team_id)
    patient = db.get(Patient, patient_id)
    profile = identity.profile_of(db, patient) if patient else None
    if patient is None or profile is None or profile.team_id != team.id:
        raise HTTPException(status_code=404, detail="Unknown athlete on this team")
    if body.status not in STATUSES:
        raise HTTPException(status_code=422, detail="Unknown status")
    profile.status = body.status
    profile.status_note = body.note
    db.commit()
    return {"ok": True, "status": profile.status, "status_label": STATUS_LABELS[profile.status]}


class EventBody(BaseModel):
    date: dt.date
    kind: str
    title: str = Field(min_length=1, max_length=120)
    start_time: str | None = None
    opponent: str | None = None
    home: bool | None = None
    location: str | None = None
    note: str | None = None


@team_router.get("/teams/{team_id}/events")
def team_events(team_id: str, days: int = 21, db: Session = Depends(get_db)) -> dict:
    team = _team_or_404(db, team_id)
    today = date.today()
    rows = db.scalars(select(SportsEvent).where(SportsEvent.team_id == team.id, SportsEvent.date >= today - timedelta(days=7),
                                                SportsEvent.date <= today + timedelta(days=days))
                      .order_by(SportsEvent.date, SportsEvent.start_time)).all()
    return {"events": [_event_view(e) for e in rows]}


@team_router.post("/teams/{team_id}/events")
def add_event(team_id: str, body: EventBody, db: Session = Depends(get_db)) -> dict:
    team = _team_or_404(db, team_id)
    e = SportsEvent(team_id=team.id, date=body.date, kind=body.kind[:24], title=body.title, start_time=body.start_time,
                    opponent=body.opponent, home=body.home, location=body.location, note=body.note)
    db.add(e)
    db.commit()
    return {"ok": True, "event": _event_view(e)}


@team_router.delete("/teams/{team_id}/events/{event_id}")
def delete_event(team_id: str, event_id: int, db: Session = Depends(get_db)) -> dict:
    _team_or_404(db, team_id)
    db.execute(delete(SportsEvent).where(SportsEvent.id == event_id, SportsEvent.team_id == team_id))
    db.commit()
    return {"ok": True}


# Unused imports kept honest.
_ = (Device, secrets)
