"""The demo members of MedPull Personal (app/personal/showcase.py) and the
console's read-only view of their spaces (app/api/console_personal.py).

Runs against a database of its own, like tests/test_showcase.py: the suite's
shared roster never gains a subscriber. The routes are pointed at it through
FastAPI's ``get_db`` override for the length of the module.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — register every table
from app.config import settings
from app.console_credentials import mint
from app.database import Base, get_db
from app.models.hospital import Hospital
from app.models.mobile import Message
from app.models.observation import Observation
from app.models.patient import Patient
from app.models.personal import PersonalProfile
from app.personal import showcase
from app.personal.data import load_personal_data
from app.personal.identity import create_personal_account
from app.personal.metrics import compute_dashboard

TODAY = date.today()
MEMBER_IDS = ["jordan-me", "samira-me", "theo-me", "nora-me"]
GETS = (
    "/api/console/personal/members",
    "/api/console/personal/jordan-me/overview",
    "/api/console/personal/jordan-me/week",
    "/api/console/personal/jordan-me/signals",
    "/api/console/personal/jordan-me/insights/sleep",
    "/api/console/personal/jordan-me/export",
)


@pytest.fixture(scope="module")
def seeded():
    """A database holding the demo members and nothing else, seeded once."""
    directory = tempfile.mkdtemp(prefix="personal-showcase-tests-")
    engine = create_engine(f"sqlite:///{directory}/personal.db",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        written = showcase.seed_personal(db, TODAY)
    yield Session, written
    engine.dispose()
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture()
def db(seeded):
    Session, _ = seeded
    with Session() as session:
        yield session


@pytest.fixture(scope="module")
def api(seeded):
    from app.main import app

    Session, _ = seeded

    def _get_db():
        with Session() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def demo(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)


@pytest.fixture()
def commits(seeded):
    """Commits made through this module's sessionmaker while a test runs."""
    Session, _ = seeded
    seen: list[int] = []

    def note(_session) -> None:
        seen.append(1)

    event.listen(Session, "after_commit", note)
    yield seen
    event.remove(Session, "after_commit", note)


def _counts(db) -> dict[str, int]:
    return {
        table.name: db.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }


def _board(db, member_id: str) -> dict:
    patient = db.get(Patient, member_id)
    return compute_dashboard(load_personal_data(db, patient), patient,
                             db.get(PersonalProfile, member_id))


# --- the seed -------------------------------------------------------------------------


def test_the_seed_writes_four_marked_members_each_a_real_personal_account(seeded, db, demo):
    _, written = seeded
    assert written == MEMBER_IDS
    rows = showcase.members(db)
    assert [p.id for p in rows] == MEMBER_IDS  # the hero first
    for patient in rows:
        assert patient.account_kind == "personal" and patient.hospital_id is None
        assert showcase.is_showcase(db, patient)
        assert patient.phone is None  # nobody is ever texted for a generated member
        profile = db.get(PersonalProfile, patient.id)
        assert profile.sms_briefs is False
    assert {db.get(PersonalProfile, i).goal for i in MEMBER_IDS} == {
        "sleep", "performance", "recovery", "everyday"}


def test_members_are_listed_on_the_demo_stack_only(db):
    assert settings.demo_mode is False
    assert showcase.members(db) == []


def test_every_member_has_a_reading_dated_today_and_reads_as_designed(db):
    for member_id in MEMBER_IDS:
        newest = db.scalar(select(func.max(Observation.local_date)).where(
            Observation.patient_id == member_id))
        assert newest == TODAY, member_id
    boards = {i: _board(db, i) for i in MEMBER_IDS}
    # three members with a full history have a verdict; the newest is still being learned
    for member_id in ("jordan-me", "samira-me", "theo-me"):
        assert boards[member_id]["verdict"]["kind"] != "unknown", member_id
        assert boards[member_id]["days_with_data"] >= 60
    assert boards["nora-me"]["verdict"]["kind"] == "unknown"
    assert boards["nora-me"]["days_with_data"] < 14

    def extra(member_id: str, panel: str, key: str):
        return boards[member_id]["panels"][panel]["extra"].get(key)

    # Jordan: two short weeks behind them, the debt still showing
    assert extra("jordan-me", "sleep", "debt_hours") > 1.0
    # Samira logs her runs, so her load reads from session RPE, and this week is the big one
    assert extra("samira-me", "load", "source") == "session RPE"
    week = boards["samira-me"]["week"]["metrics"]["load"]
    assert week["this"] > week["last"] * 2
    # Theo's goal adds the care section in his sections
    assert "care" in boards["theo-me"]["sections"]


def test_a_second_run_the_same_day_leaves_the_same_rows(db):
    before = _counts(db)
    again = showcase.seed_personal(db, TODAY)
    assert again == MEMBER_IDS
    assert _counts(db) == before


def test_the_seed_never_touches_a_subscriber_without_the_mark(db, demo):
    real, _profile = create_personal_account(db, name="Riley Stone", phone=None, goal="sleep",
                                             sport=None, sms_briefs=False)
    try:
        showcase.seed_personal(db, TODAY)
        assert db.get(Patient, real.id) is not None
        assert not showcase.is_showcase(db, db.get(Patient, real.id))
        assert real.id not in [p.id for p in showcase.members(db)]
    finally:
        from sqlalchemy import delete

        from app.models.personal import Consent, Entitlement

        for model in (Consent, Entitlement, PersonalProfile):
            db.execute(delete(model).where(model.patient_id == real.id))
        db.execute(delete(Patient).where(Patient.id == real.id))
        db.commit()


# --- the console ----------------------------------------------------------------------


@pytest.mark.parametrize("path", GETS)
def test_the_personal_pages_do_not_exist_off_the_demo_stack(api, path):
    assert settings.demo_mode is False
    assert api.get(path).status_code == 404


@pytest.mark.parametrize("path", GETS)
def test_every_read_answers_on_the_demo_stack_without_committing(api, demo, commits, path):
    res = api.get(path)
    assert res.status_code == 200, res.text
    assert commits == []


def test_the_members_list_has_the_line_a_list_needs(api, demo):
    body = api.get("/api/console/personal/members").json()
    assert [m["id"] for m in body["members"]] == MEMBER_IDS
    jordan = body["members"][0]
    assert jordan["hero"] is True and jordan["goal"] == "sleep" and jordan["devices"]
    assert jordan["verdict"]["kind"] != "unknown" and 0 < jordan["readiness"]["score"] <= 100
    assert jordan["sleep"]["last_night_h"] > 0 and jordan["sleep"]["debt_h"] > 0
    nora = body["members"][-1]
    assert nora["verdict"]["kind"] == "unknown" and nora["readiness"]["score"] is None


def test_the_overview_is_the_members_own_dashboard(api, db, demo):
    body = api.get("/api/console/personal/samira-me/overview").json()
    assert set(body) == {"member", "profile", "subscription", "dashboard", "brief", "care", "plan",
                         "thread", "logs", "notes"}
    # the very numbers the phone reads: sign in as the member and compare
    session = api.post("/api/demo/session", json={"persona_id": "samira-me"}).json()
    phone = api.get("/api/mobile/personal/dashboard",
                    headers={"Authorization": f"Bearer {session['session_token']}"}).json()
    assert body["dashboard"]["verdict"] == phone["dashboard"]["verdict"]
    assert body["dashboard"]["panels"]["readiness"] == phone["dashboard"]["panels"]["readiness"]
    assert body["dashboard"]["sections"] == phone["dashboard"]["sections"]
    assert "digest" not in body["dashboard"] and "notes" not in body["dashboard"]
    assert body["brief"]["brief"] and body["brief"]["provider"] == "fallback"
    assert body["plan"]["open"] and body["thread"] and body["logs"]
    assert body["thread"] == sorted(body["thread"], key=lambda m: m["created_at"])
    assert body["care"] is None  # a performance goal has no care section

    theo = api.get("/api/console/personal/theo-me/overview").json()
    assert theo["care"] and theo["care"]["metrics"]


def test_a_brief_headline_prints_sleep_as_a_percentage_of_need():
    from app.personal.insights import fallback_brief

    digest = {"verdict": {"kind": "easy", "title": "Take it easy", "reason": "", "detail": ""},
              "sleep": {"status": "watch", "performance": 0.74}}
    assert "74% of need" in fallback_brief(digest)["headline"]


def test_no_id_opens_anything_but_a_generated_member(api, db, demo):
    real, _profile = create_personal_account(db, name="Casey Lund", phone=None, goal="everyday",
                                             sport=None, sms_briefs=False)
    db.add(Hospital(id="hosp_ps", name="PS Clinic", system="PS", city="Houston", state="TX"))
    db.commit()
    try:
        for member_id in (real.id, "nobody", "hirt-cole"):
            for tail in ("overview", "week", "signals", "insights/sleep", "export"):
                res = api.get(f"/api/console/personal/{member_id}/{tail}")
                assert res.status_code == 404, (member_id, tail)
            assert api.post(f"/api/console/personal/{member_id}/coach",
                            json={"text": "hello"}).status_code == 404
        listed = [m["id"] for m in api.get("/api/console/personal/members").json()["members"]]
        assert real.id not in listed
        # an org credential has no Personal version at all
        _row, token = mint(db, "hospital", "hosp_ps", "PS console")
        headers = {"Authorization": f"Bearer {token}"}
        assert api.get("/api/console/personal/members", headers=headers).status_code == 404
        assert api.get("/api/console/personal/jordan-me/overview", headers=headers).status_code == 404
        assert api.get("/api/console/personal/jordan-me/insights/nope").status_code == 404
    finally:
        from sqlalchemy import delete

        from app.models.credential import ConsoleCredential
        from app.models.personal import Consent, Entitlement

        db.execute(delete(ConsoleCredential))
        for model in (Consent, Entitlement, PersonalProfile):
            db.execute(delete(model).where(model.patient_id == real.id))
        db.execute(delete(Patient).where(Patient.id == real.id))
        db.execute(delete(Hospital).where(Hospital.id == "hosp_ps"))
        db.commit()


def test_a_coach_turn_lands_on_the_members_thread(api, db, demo):
    before = db.scalar(select(func.count(Message.id)).where(Message.patient_id == "nora-me"))
    res = api.post("/api/console/personal/nora-me/coach", json={"text": "How am I doing?"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["reply"] and body["provider"] == "fallback" and body["flagged"] is False
    db.expire_all()
    after = db.scalar(select(func.count(Message.id)).where(Message.patient_id == "nora-me"))
    assert after == before + 2  # the member's line and the coach's
    assert [m["sender"] for m in body["thread"][-2:]] == ["patient", "copilot"]
    assert api.post("/api/console/personal/nora-me/coach", json={"text": ""}).status_code == 422
