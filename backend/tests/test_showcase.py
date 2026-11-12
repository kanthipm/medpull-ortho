"""The showcase (docs/dev/showcase.md, docs/dev/showcase/fill.md): the
persona registry, the demo routes the iPhone app calls with no credential,
the fill that keeps all three versions current, and the day reset.

Everything here runs against a database of its own, built by the fill on
an empty schema. The suite's shared database is never read or written: the
routes are pointed at this one through FastAPI's ``get_db`` override, which
is taken off again when the module ends.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — register every table
from app.config import settings
from app.database import Base, get_db
from app.hep.models import Exercise, ExerciseAssignment
from app.models.attachment import Attachment
from app.models.enums import ProcedureType
from app.models.hospital import Hospital
from app.models.insight import RiskAssessment
from app.models.mobile import Message, PatientSession
from app.models.notification import Notification
from app.models.patient import Device, Patient
from app.models.personal import PersonalProfile
from app.personal import auth
from app.personal import showcase as personal_showcase
from app.seed import demo_fill, hirt, showcase
from app.sports import seed as sports_seed

TODAY = date.today()
PERSONA_KEYS = {"id", "name", "hero", "tagline", "detail", "account_kind", "tier", "has"}
REAL_PHONE = "+15042345678"
OTHER_REAL_PHONE = "+15043456789"


def _engine(directory: str, name: str):
    engine = create_engine(f"sqlite:///{directory}/{name}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def filled():
    """A database of this module's own, holding a complete showcase: the
    fill run once on an empty schema. Yields its sessionmaker and engine."""
    directory = tempfile.mkdtemp(prefix="showcase-tests-")
    engine = _engine(directory, "showcase.db")
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        report = showcase.fill_showcase(db, TODAY, force=True)
    yield Session, engine, report
    engine.dispose()
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture()
def db(filled):
    Session, _engine_, _report = filled
    with Session() as session:
        yield session


@pytest.fixture(scope="module")
def api(filled):
    """The app, with every route reading this module's database."""
    from app.main import app

    Session, _engine_, _report = filled

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
def member(db, monkeypatch):
    """One demo member of MedPull Personal, standing in for whatever
    ``app.personal.showcase`` holds: the showcase only ever asks that module
    who the members are, so the answer is supplied here and the row is
    removed afterwards."""
    from sqlalchemy import delete

    from app.models.personal import Consent, Entitlement
    from app.personal.identity import create_personal_account

    patient, _profile = create_personal_account(
        db, name="Jordan Avery", phone=None, goal="sleep", sport="running", sms_briefs=False)
    monkeypatch.setattr(personal_showcase, "members", lambda db: [db.get(Patient, patient.id)])
    monkeypatch.setattr(personal_showcase, "is_showcase",
                        lambda db, row: row is not None and row.id == patient.id)
    yield patient
    for model in (PatientSession, Consent, Entitlement, RiskAssessment, PersonalProfile):
        db.execute(delete(model).where(model.patient_id == patient.id))
    db.execute(delete(Patient).where(Patient.id == patient.id))
    db.commit()


def _session(api, persona_id: str, device: str | None = None) -> dict:
    body = {"persona_id": persona_id} | ({"device_name": device} if device else {})
    resp = api.post("/api/demo/session", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _table_counts(db) -> dict[str, int]:
    return {
        table.name: db.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }


# --- the registry ---------------------------------------------------------------------------


def test_the_registry_lists_every_clinic_persona_and_every_seeded_athlete():
    by_id = {p.id: p for p in showcase.REGISTRY}
    assert len(by_id) == len(showcase.REGISTRY), "an id is on the registry twice"
    assert set(demo_fill.roster_ids()) | {a.id for a in sports_seed.ROSTER} == set(by_id)
    assert not set(by_id) & demo_fill.PROTECTED

    cole = showcase.persona("hirt-cole")
    assert cole.version == "clinic" and cole.org_id == "hirt" and cole.hero
    assert cole.org_name == "H.I.R.T. Physical Therapy"
    assert cole.tagline == hirt.PATHWAYS["hirt-cole"] and cole.detail == "Load spike, pain rising"
    assert [p.id for p in showcase.REGISTRY if p.org_id == "hirt" and p.hero] == ["hirt-cole"]

    dana = showcase.persona("dana")
    assert dana.org_id == "hosp_demo" and dana.tagline == "Total Knee Replacement (TKA) · day 9"

    jalen = showcase.persona("jalen-okoro")
    assert jalen.version == "sports" and jalen.org_id == "rice-mbb" and jalen.hero
    assert jalen.org_name == "Rice · Men's Basketball" and jalen.tagline == "Point guard · #1 · Jr"
    assert showcase.persona("sloane-whitaker").org_id == "independent"

    assert showcase.persona("steve") is None and showcase.persona("nobody") is None
    assert all(p.detail for p in showcase.REGISTRY), "a persona has no story line"


# --- GET /api/demo/personas -----------------------------------------------------------------


def test_personas_lists_each_version_with_its_orgs(api, db, demo):
    before = db.scalar(select(func.count(RiskAssessment.id)))
    body = api.get("/api/demo/personas").json()
    assert set(body) == {"as_of", "sms", "versions"}
    assert body["as_of"] == TODAY.isoformat()
    assert body["sms"] == {"number": None, "text_body": "Hi MedPull", "configured": False}

    versions = {v["key"]: v for v in body["versions"]}
    assert [v["key"] for v in body["versions"]] == [k for k in showcase.VERSIONS if k in versions]
    assert {"clinic", "sports"} <= set(versions)
    # Personal is listed exactly when the database holds demo members.
    assert ("personal" in versions) == bool(personal_showcase.members(db))
    for version in body["versions"]:
        assert set(version) == {"key", "label", "blurb", "orgs"} and version["orgs"]
        for org in version["orgs"]:
            assert set(org) == {"id", "name", "personas"} and org["personas"]
            assert [p["hero"] for p in org["personas"]] == [True] + [False] * (len(org["personas"]) - 1)
            for p in org["personas"]:
                assert set(p) == PERSONA_KEYS
                assert set(p["has"]) == {"wearable", "exercises", "thread"}
                assert p["account_kind"] == version["key"]

    clinic = {o["id"]: o for o in versions["clinic"]["orgs"]}
    assert list(clinic)[:2] == ["hirt", "hosp_demo"]
    assert set(clinic) == {"hirt", "hosp_demo", "hosp_methodist", "hosp_hermann", "hosp_stlukes",
                           "hosp_utsw"}
    assert clinic["hirt"]["name"] == "H.I.R.T. Physical Therapy"
    lifters = {p["id"]: p for p in clinic["hirt"]["personas"]}
    assert {pid: p["tier"] for pid, p in lifters.items()} == hirt.EXPECTED_TIERS
    assert clinic["hirt"]["personas"][0] == {
        "id": "hirt-cole", "name": "Cole Whitaker", "hero": True,
        "tagline": "Patellar tendinopathy · progressive loading",
        "detail": "Load spike, pain rising", "account_kind": "clinic", "tier": "high",
        "has": {"wearable": False, "exercises": True, "thread": True},
    }
    demo_hospital = {p["id"]: p for p in clinic["hosp_demo"]["personas"]}
    assert clinic["hosp_demo"]["personas"][0]["id"] == "dana"
    assert demo_hospital["dana"]["has"] == {"wearable": True, "exercises": False, "thread": True}
    assert demo_hospital["medha"]["has"] == {"wearable": False, "exercises": False, "thread": False}
    assert demo_hospital["reyes"]["tier"] == "high"

    sports = {o["id"]: o for o in versions["sports"]["orgs"]}
    assert sports["rice-mbb"]["name"] == "Rice · Men's Basketball"
    jalen = sports["rice-mbb"]["personas"][0]
    assert jalen["id"] == "jalen-okoro" and jalen["tier"] is None and jalen["has"]["wearable"]
    assert {p["id"] for o in sports.values() for p in o["personas"]} == {a.id for a in sports_seed.ROSTER}

    # A GET: nothing was scored or stored to answer it.
    db.expire_all()
    assert db.scalar(select(func.count(RiskAssessment.id))) == before


def test_personas_lists_only_rows_that_exist_and_drops_an_empty_version(filled, monkeypatch):
    """The registry is intersected with the database: an empty one lists
    nobody, and one holding a single lifter lists that org alone."""
    directory = tempfile.mkdtemp(prefix="showcase-tests-empty-")
    engine = _engine(directory, "empty.db")
    try:
        with sessionmaker(bind=engine)() as empty:
            assert showcase.personas(empty)["versions"] == []
            assert showcase.resolve(empty, "hirt-cole") is None
            demo_fill.ensure_orgs(empty, [])
            cole = next(p for p in demo_fill.build_roster()[2] if p.spec.id == "hirt-cole")
            demo_fill.write_persona(empty, cole, TODAY)
            versions = showcase.personas(empty)["versions"]
            assert [v["key"] for v in versions] == ["clinic"]
            assert [o["id"] for o in versions[0]["orgs"]] == ["hirt"]
            only = versions[0]["orgs"][0]["personas"]
            assert [p["id"] for p in only] == ["hirt-cole"]
            # Never scored: the tier is read as stored, and nothing is stored.
            assert only[0]["tier"] is None and only[0]["hero"] is True
    finally:
        engine.dispose()
        shutil.rmtree(directory, ignore_errors=True)


def test_a_demo_member_is_listed_under_personal(api, db, demo, member):
    body = api.get("/api/demo/personas").json()
    assert [v["key"] for v in body["versions"]] == ["clinic", "personal", "sports"]
    personal = body["versions"][1]
    assert personal["label"] == "Personal" and [o["id"] for o in personal["orgs"]] == ["personal"]
    assert personal["orgs"][0]["name"] == "MedPull Personal"
    assert personal["orgs"][0]["personas"] == [{
        "id": member.id, "name": "Jordan Avery", "hero": True,
        "tagline": "Sleep and recover better · running", "detail": "",
        "account_kind": "personal", "tier": None,
        "has": {"wearable": False, "exercises": False, "thread": False},
    }]


# --- POST /api/demo/session -----------------------------------------------------------------


@pytest.mark.parametrize("persona_id, version, mode", [
    ("hirt-cole", "clinic", "general"),
    ("dana", "clinic", "recovery"),
    ("jalen-okoro", "sports", "sports"),
])
def test_a_session_as_a_persona_carries_the_me_the_app_reads(api, demo, persona_id, version, mode):
    body = _session(api, persona_id, f"pytest {persona_id}")
    assert set(body) == {"session_token", "me", "persona"}
    assert body["persona"] == {"id": persona_id, "name": body["me"]["patient"]["name"],
                               "version": version}
    me = api.get("/api/mobile/me", headers=_bearer(body["session_token"]))
    assert me.status_code == 200 and me.json() == body["me"]
    assert body["me"]["patient"]["id"] == persona_id and body["me"]["patient"]["mode"] == mode
    assert body["me"]["patient"]["account_kind"] == version
    # Consent is on file, so the app does not stop at the consent screen.
    assert body["me"]["consent"]["needs_consent"] is False


def test_a_session_as_a_demo_member(api, demo, member):
    body = _session(api, member.id)
    assert body["persona"] == {"id": member.id, "name": "Jordan Avery", "version": "personal"}
    me = api.get("/api/mobile/me", headers=_bearer(body["session_token"])).json()
    assert me == body["me"] and me["patient"]["mode"] == "personal"
    # The fill is what files a member's consent; it has not run since this
    # one was made, so file it the way the fill does.


def test_only_people_the_showcase_knows_can_be_signed_into(api, db, demo):
    """Not an unknown id, and not a chart that exists but is nobody's persona."""
    walk_in = Patient(
        id="walk-in-test", name="Wren Calloway", initials="WC", age=40, sex="F",
        procedure_type="NONE", procedure_display="General care", surgery_date=TODAY,
        discharge_date=TODAY, surgeon_id="ct_chen", assigned_provider_id="ct_chen",
        hospital_id="hosp_demo",
    )
    db.add(walk_in)
    db.commit()
    try:
        for persona_id in ("nobody", "walk-in-test"):
            resp = api.post("/api/demo/session", json={"persona_id": persona_id})
            assert resp.status_code == 404 and resp.json() == {"detail": "Unknown persona"}
            assert api.post("/api/demo/reset-day", json={"persona_id": persona_id}).status_code == 404
        assert api.post("/api/demo/session", json={}).status_code == 422
        assert db.scalar(select(func.count(PatientSession.id)).where(
            PatientSession.patient_id == "walk-in-test")) == 0
    finally:
        db.delete(walk_in)
        db.commit()


def test_a_subscriber_without_the_mark_cannot_be_signed_into(api, db, demo, member, monkeypatch):
    monkeypatch.setattr(personal_showcase, "is_showcase", lambda db, row: False)
    assert api.post("/api/demo/session", json={"persona_id": member.id}).status_code == 404


def test_every_persona_route_is_absent_off_the_demo_stack(api, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    assert api.get("/api/demo/personas").status_code == 404
    assert api.post("/api/demo/session", json={"persona_id": "hirt-cole"}).status_code == 404
    assert api.post("/api/demo/reset-day", json={"persona_id": "hirt-cole"}).status_code == 404


def test_one_session_per_persona_and_device(api, db, demo):
    def rows(device):
        db.expire_all()
        return db.scalars(select(PatientSession).where(
            PatientSession.patient_id == "hirt-tessa", PatientSession.device_name == device)).all()

    first = _session(api, "hirt-tessa", "iPhone A")["session_token"]
    second = _session(api, "hirt-tessa", "iPhone A")["session_token"]
    assert first != second and len(rows("iPhone A")) == 1
    # The earlier token is spent; the new one is the session.
    assert api.get("/api/mobile/me", headers=_bearer(first)).status_code == 401
    assert api.get("/api/mobile/me", headers=_bearer(second)).status_code == 200

    # Another device is another session, and so is another persona on the same device.
    other = _session(api, "hirt-tessa", "iPhone B")["session_token"]
    june = _session(api, "hirt-june", "iPhone A")["session_token"]
    assert len(rows("iPhone B")) == 1 and len(rows("iPhone A")) == 1
    for token in (second, other, june):
        assert api.get("/api/mobile/me", headers=_bearer(token)).status_code == 200

    # No name given: filed under the default, still one row however often it is asked.
    _session(api, "hirt-tessa")
    _session(api, "hirt-tessa")
    assert len(rows("demo phone")) == 1


def test_the_console_demo_session_route_is_unchanged(api, db, demo):
    resp = api.post("/api/demo/patient-session", json={"patient_id": "hirt-june"})
    assert resp.status_code == 200
    assert set(resp.json()) == {"token", "patient"}
    assert resp.json()["patient"] == {"id": "hirt-june", "name": "June Halvorsen"}
    assert api.get("/api/mobile/me", headers=_bearer(resp.json()["token"])).status_code == 200


# --- POST /api/demo/reset-day ---------------------------------------------------------------


def _pristine(row: ExerciseAssignment) -> bool:
    return row.status == "assigned" and all(
        getattr(row, name) is None
        for name in (*showcase._OUTCOME_FIELDS, *showcase._REVIEW_FIELDS)
    )


def test_reset_day_puts_todays_exercises_and_thread_back(api, db, demo):
    from app.hep import schedule

    pid = "hirt-june"  # four exercises every day, no clip or wearable asked for
    headers = _bearer(_session(api, pid, "reset-day")["session_token"])
    today = api.get("/api/mobile/exercises", headers=headers).json()["items"]
    assert len(today) == 4 and {i["status"] for i in today} == {"assigned"}
    done_before = db.scalar(select(func.count(ExerciseAssignment.id)).where(
        ExerciseAssignment.patient_id == pid, ExerciseAssignment.status == "done"))
    assert done_before == hirt.EXPECTED_SCHEDULE[pid]["done"]
    thread_before = db.scalar(select(func.count(Message.id)).where(Message.patient_id == pid))
    bell_before = db.scalar(select(func.count(Notification.id)).where(Notification.patient_id == pid))

    # A clip the lifter filmed, as the direct upload leaves it: confirmed, on no line yet.
    clip = Attachment(patient_id=pid, content_type="video/mp4", byte_size=64,
                      storage_key="test/showcase/reset-day.mp4", filename="attempt.mp4",
                      confirmed_at=datetime.now())
    db.add(clip)
    db.commit()

    first, second, third, fourth = (i["id"] for i in today)
    assert api.post(f"/api/mobile/exercises/{first}/start", json={"pain_before": 2},
                    headers=headers).status_code == 200
    assert api.post(f"/api/mobile/exercises/{first}/complete", headers=headers, json={
        "pain_after": 3, "effort": 5, "note": "Fine today.", "sets_done": 2, "reps_done": 10,
        "video": {"attachment_id": clip.id}}).status_code == 200
    assert api.post(f"/api/mobile/exercises/{second}/complete", headers=headers,
                    json={"pain_after": 1}).status_code == 200
    assert api.post(f"/api/mobile/exercises/{third}/skip", headers=headers,
                    json={"reason": "Out of time"}).status_code == 200
    assert api.post(f"/api/mobile/exercises/{fourth}/start", json={"pain_before": 1},
                    headers=headers).status_code == 200
    # Her therapist looks at the first and writes back; and, today, at a day
    # June did last week, which stays done.
    db.expire_all()
    schedule.review_assignment(db, db.get(ExerciseAssignment, first),
                               note="Good depth. Same again tomorrow.", actor="ct_harris")
    earlier = db.scalar(
        select(ExerciseAssignment).where(
            ExerciseAssignment.patient_id == pid, ExerciseAssignment.status == "done",
            ExerciseAssignment.scheduled_for < TODAY, ExerciseAssignment.reviewed_at.is_(None),
        ).order_by(ExerciseAssignment.scheduled_for.desc()).limit(1)
    )
    schedule.review_assignment(db, earlier, note="Nice and level.", actor="ct_harris")
    assert db.scalar(select(func.count(Message.id)).where(Message.patient_id == pid)) == thread_before + 4

    resp = api.post("/api/demo/reset-day", json={"persona_id": pid})
    assert resp.status_code == 200 and resp.json() == {"reopened": 4, "removed": 4}

    db.expire_all()
    for assignment_id in (first, second, third, fourth):
        assert _pristine(db.get(ExerciseAssignment, assignment_id))
    earlier = db.get(ExerciseAssignment, earlier.id)
    assert earlier.status == "done" and earlier.completed_at is not None
    assert earlier.reviewed_at is None and earlier.review_note is None
    assert db.scalar(select(func.count(Message.id)).where(Message.patient_id == pid)) == thread_before
    assert db.scalar(select(func.count(Notification.id)).where(
        Notification.patient_id == pid)) == bell_before
    # The clip is still a stored file, on no line and no day.
    clip = db.get(Attachment, clip.id)
    assert clip.message_id is None and clip.deleted_at is None
    # What the fill wrote is as it was, and the app shows the day open again.
    assert db.scalar(select(func.count(ExerciseAssignment.id)).where(
        ExerciseAssignment.patient_id == pid, ExerciseAssignment.status == "done")) == done_before
    assert db.scalar(select(func.count(ExerciseAssignment.id)).where(
        ExerciseAssignment.patient_id == pid, ExerciseAssignment.reviewed_at.is_not(None),
    )) == hirt.EXPECTED_REVIEWS[pid]
    again = api.get("/api/mobile/exercises", headers=headers).json()["items"]
    assert {i["status"] for i in again} == {"assigned"}
    assert api.post(f"/api/mobile/exercises/{first}/complete", headers=headers,
                    json={"pain_after": 2}).status_code == 200

    # The walkthrough can be run again, and reset again.
    assert api.post("/api/demo/reset-day", json={"persona_id": pid}).json() == {
        "reopened": 1, "removed": 1}
    assert api.post("/api/demo/reset-day", json={"persona_id": pid}).json() == {
        "reopened": 0, "removed": 0}
    db.delete(db.get(Attachment, clip.id))
    db.commit()


def test_reset_day_reports_nothing_for_a_persona_with_no_calendar(api, demo, member):
    for persona_id in ("jalen-okoro", member.id, "dana"):
        resp = api.post("/api/demo/reset-day", json={"persona_id": persona_id})
        assert resp.status_code == 200 and resp.json() == {"reopened": 0, "removed": 0}


# --- the fill -------------------------------------------------------------------------------


def test_the_fill_refuses_off_the_demo_stack(db, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    before = _table_counts(db)
    with pytest.raises(showcase.ShowcaseRefused, match="not in demo mode"):
        showcase.fill_showcase(db, TODAY)
    assert _table_counts(db) == before
    monkeypatch.setattr(settings, "demo_mode", True)
    assert showcase.refusal() is None


def test_the_fill_builds_all_of_it_on_an_empty_database(filled, db):
    _Session, _engine_, report = filled
    assert report["filled_on"] == TODAY.isoformat() == showcase.filled_on(db)
    assert report["clinic"]["personas"] == demo_fill.roster_ids()
    assert report["clinic"]["skipped"] == {}
    assert report["sports"]["athletes"] == len(sports_seed.ROSTER)
    assert report["personas"] >= len(showcase.REGISTRY)

    # Every chart points at a hospital that exists, the ortho roster's four included.
    hospitals = set(db.scalars(select(Hospital.id)))
    assert {"hirt", "hosp_demo", "hosp_methodist", "hosp_hermann", "hosp_stlukes", "hosp_utsw"} <= hospitals
    for row in db.scalars(select(Patient).where(Patient.id.in_(demo_fill.roster_ids()))):
        assert row.hospital_id in hospitals, row.id
    # The lifters read as the demo is pitched, and the calendar is theirs.
    for pid, tier in hirt.EXPECTED_TIERS.items():
        assert report["clinic"]["tiers"][pid] == tier
    # The two charts the shipped seed starts the demo hospital with are part
    # of the fill: Reyes current and high, Medha a chart with nothing on it yet.
    reyes = db.get(Patient, "reyes")
    assert reyes.surgery_date == TODAY - timedelta(days=8) and reyes.hospital_id == "hosp_demo"
    assert db.get(Device, "dev_reyes").last_sync_at.date() == TODAY
    assert report["clinic"]["tiers"]["reyes"] == "high"
    medha = db.get(Patient, "medha")
    assert medha is not None and db.scalar(
        select(func.count(Device.id)).where(Device.patient_id == "medha")) == 0
    assert report["clinic"]["tiers"]["medha"] == "missing_data"


def test_a_lifters_chart_leads_with_six_tiles_that_have_data(api, db):
    """The H.I.R.T. roster has a calendar and check-ins and no watch: the six
    tiles its charts lead with are the ones those fill, adherence from the
    calendar among them, and each lifter reads as their story is told."""
    from app.engine.care.pathways import ORTHO_SIX, TRAINING_SIX

    def bundle(pid: str) -> dict:
        row = db.scalars(
            select(RiskAssessment).where(RiskAssessment.patient_id == pid)
            .order_by(RiskAssessment.computed_at.desc(), RiskAssessment.id.desc())
        ).first()
        return row.analytics["care_metrics"]

    adherence = {}
    for pid in hirt.PATHWAYS:
        care = bundle(pid)
        by_id = {m["id"]: m for m in care["metrics"]}
        assert care["pathway"] == "training_program" and care["headline"] == list(TRAINING_SIX)
        assert [i for i in TRAINING_SIX if by_id[i]["status"] == "nodata"] == [], pid
        assert by_id["M14"]["value_label"] == "verified exercise-days"
        assert by_id["M2"]["name"].startswith("Pain")
        adherence[pid] = by_id["M14"]["status"]
    assert adherence == {
        "hirt-cole": "ok", "hirt-tessa": "ok", "hirt-june": "ok",
        "hirt-devon": "flag", "hirt-rafael": "watch",
    }
    # The chart says which pathway it was read on; a surgical persona is untouched.
    body = api.get("/api/patients/hirt-devon/care-metrics").json()
    assert body["pathway"] == {"key": "training_program", "name": "Training program",
                               "domain": "general"}
    assert body["headline"] == list(TRAINING_SIX)
    assert bundle("reyes")["headline"] == list(ORTHO_SIX)
    # One nudge for the program that slipped, as before.
    steps = api.get("/api/patients/hirt-devon/next-steps").json()["steps"]
    assert [s["key"] for s in steps].count("msg_program_nudge") == 1
    assert not {"msg_exercise_nudge", "open_plan"} & {s["key"] for s in steps}


def test_a_lifters_worklist_line_is_the_engines_own_sentence(db, monkeypatch):
    """With a model configured, the three lifters who need a look still read
    as the engine flagged them: no model call, the reason text itself."""
    from app.llm import insights
    from app.models.enums import InsightKind

    monkeypatch.setattr(insights, "provider_name", lambda: "groq")
    monkeypatch.setattr(insights, "complete_json",
                        lambda *a, **kw: pytest.fail("a lifter's reason must not call the model"))
    lines = {
        pid: insights.get_patient_insight(db, InsightKind.WORKLIST_REASON, pid).content["reason"]
        for pid in ("hirt-cole", "hirt-rafael", "hirt-devon")
    }
    assert lines["hirt-cole"].startswith("Training load 1.6× its recent average")
    assert lines["hirt-rafael"] == "Went quiet — no check-in for 3 days"
    assert lines["hirt-devon"].startswith("Program slipping")
    assert all("device" not in line.lower() for line in lines.values())


def test_every_clinic_personas_thread_reads_in_time_order(db):
    """The phone lists a thread by row id, so the fill leaves each persona's
    rows numbered in the order they are dated."""
    checked = 0
    for pid in demo_fill.roster_ids():
        dates = list(db.scalars(
            select(Message.created_at).where(Message.patient_id == pid).order_by(Message.id)
        ))
        assert dates == sorted(dates), pid
        checked += len(dates) > 1
    assert checked >= len(hirt.PATHWAYS)


def test_putting_a_thread_in_order_takes_its_files_and_links_along():
    from app.models.links import AppLink

    directory = tempfile.mkdtemp(prefix="showcase-thread-")
    engine = _engine(directory, "thread.db")
    try:
        with sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)() as db:
            db.add(Hospital(id="clinic", name="A clinic", system="A", city="Houston", state="TX"))
            start = TODAY - timedelta(days=14)
            for pid, name in (("pat", "Pat Example"), ("other", "Other Example")):
                db.add(Patient(
                    id=pid, name=name, initials="PE", age=30, sex="F",
                    procedure_type=ProcedureType.NONE, procedure_display="A program",
                    surgery_date=start, discharge_date=start, surgeon_id="ct_harris",
                    assigned_provider_id="ct_gregg", hospital_id="clinic",
                ))
            db.flush()
            noon = datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=12)
            # Written newest first, the way a fill in passes leaves them.
            note = Message(patient_id="pat", sender="care_team", text="About your Step-Ups",
                           channel="app", authored_by="care_team",
                           created_at=noon - timedelta(days=2))
            clip_line = Message(patient_id="pat", sender="patient", text="Did Step-Ups",
                                channel="app", created_at=noon - timedelta(days=3))
            welcome = Message(patient_id="pat", sender="care_team", text="Welcome",
                              channel="sms", created_at=noon - timedelta(days=7))
            theirs = Message(patient_id="other", sender="patient", text="Not mine",
                             channel="app", created_at=noon - timedelta(days=9))
            db.add_all([note, clip_line, welcome, theirs])
            db.flush()
            ids = [note.id, clip_line.id, welcome.id]
            clip = Attachment(patient_id="pat", message_id=clip_line.id, content_type="video/mp4",
                              storage_key="k/clip", filename="clip.mp4", confirmed_at=noon)
            link = AppLink(token_hash="h1", patient_id="pat", kind="thread", message_id=note.id)
            elsewhere = AppLink(token_hash="h2", patient_id="other", kind="thread",
                                message_id=theirs.id)
            db.add_all([clip, link, elsewhere])
            db.commit()

            assert demo_fill.thread_in_order(db, "pat") == 2
            db.commit()
            rows = db.scalars(
                select(Message).where(Message.patient_id == "pat").order_by(Message.id)).all()
            assert [r.id for r in rows] == ids
            assert [r.text for r in rows] == ["Welcome", "Did Step-Ups", "About your Step-Ups"]
            assert [(r.sender, r.channel) for r in rows] == [
                ("care_team", "sms"), ("patient", "app"), ("care_team", "app")]
            assert rows[2].authored_by == "care_team" and rows[0].authored_by is None
            # The clip is still on its own line and the link on the note it carried.
            assert db.get(Message, db.get(Attachment, clip.id).message_id).text == "Did Step-Ups"
            assert db.get(Message, db.get(AppLink, link.id).message_id).text == "About your Step-Ups"
            # Another person's thread and link are not part of it.
            assert db.get(AppLink, elsewhere.id).message_id == theirs.id
            assert db.get(Message, theirs.id).text == "Not mine"
            # In order already: nothing to do.
            assert demo_fill.thread_in_order(db, "pat") == 0
    finally:
        engine.dispose()
        shutil.rmtree(directory, ignore_errors=True)


def test_every_persona_has_consent_on_file(db):
    listed = showcase._listed(db)
    assert len(listed) >= len(showcase.REGISTRY)
    for _entry, row in listed:
        assert auth.consent_view(db, row)["needs_consent"] is False, row.id
    # A consent from before the form changed counts as none, and is renewed once.
    from app.models.personal import Consent

    old = db.scalar(select(Consent).where(Consent.patient_id == "rosa"))
    current, old.version = old.version, "2025-01-01.0"
    db.commit()
    assert hirt.ensure_consent(db, "rosa") == 1
    assert hirt.ensure_consent(db, "rosa") == 0
    assert auth.consent_view(db, db.get(Patient, "rosa"))["needs_consent"] is False
    assert auth.current_consent(db, db.get(Patient, "rosa")).version == current
    db.delete(old)
    db.commit()


def test_a_refill_is_idempotent_and_keeps_what_a_presenter_left(api, db, demo):
    """Run twice in a row: the same rows. Across it a phone stays signed in
    as its persona, a clinic one and an athlete alike, and a real number a
    presenter bound stays on the chart; a placeholder is just rewritten."""
    cole = _session(api, "hirt-cole", "presenter")["session_token"]
    jalen = _session(api, "jalen-okoro", "presenter")["session_token"]
    db.get(Patient, "hirt-cole").phone = REAL_PHONE
    db.get(Patient, "jalen-okoro").phone = OTHER_REAL_PHONE
    # A chart nobody authored, with nothing on it: the kind of row a sweep
    # for "junk" used to delete.
    db.add(Patient(
        id="abandoned-signup", name="Test Test", initials="TT", age=30, sex="U",
        procedure_type="NONE", procedure_display="General care", surgery_date=TODAY,
        discharge_date=TODAY, surgeon_id="ct_chen", assigned_provider_id="ct_chen",
        hospital_id="hosp_demo",
    ))
    # A return clip, as scripts/seed_hirt_media.py leaves one behind a refill.
    db.add(Attachment(patient_id="hirt-cole", content_type="video/mp4", byte_size=64,
                      storage_key="test/showcase/cole-step-ups.mp4", confirmed_at=datetime.now(),
                      filename="hirt-cole-functional-step-ups-day-12.mp4"))
    db.commit()

    first = showcase.fill_showcase(db, TODAY)
    db.expire_all()
    counts = _table_counts(db)
    second = showcase.fill_showcase(db, TODAY)
    db.expire_all()
    assert _table_counts(db) == counts
    assert second["clinic"]["tiers"] == first["clinic"]["tiers"]
    assert second["clinic"]["counts"] == first["clinic"]["counts"]
    assert second["consents"] == 0 and second["kept"]["phones"] <= 1

    # Still signed in, on both sides of the product.
    for token, pid in ((cole, "hirt-cole"), (jalen, "jalen-okoro")):
        me = api.get("/api/mobile/me", headers=_bearer(token))
        assert me.status_code == 200 and me.json()["patient"]["id"] == pid
    assert db.get(Patient, "hirt-cole").phone == REAL_PHONE
    assert db.get(Patient, "jalen-okoro").phone == OTHER_REAL_PHONE
    assert db.get(Patient, "hirt-tessa").phone == hirt.PHONES["hirt-tessa"]
    assert demo_fill.is_placeholder_phone(hirt.PHONES["hirt-tessa"])
    assert not demo_fill.is_placeholder_phone(REAL_PHONE) and not demo_fill.is_placeholder_phone(None)
    # The abandoned sign-up is not the showcase's to remove.
    assert db.get(Patient, "abandoned-signup") is not None

    # The clip is back on the latest done day of that exercise, with the
    # line a completion writes, once — and that day still waits for review.
    step_ups = db.scalar(select(Exercise).where(Exercise.key == "functional_step_ups"))
    latest = db.scalar(
        select(ExerciseAssignment).where(
            ExerciseAssignment.patient_id == "hirt-cole", ExerciseAssignment.status == "done",
            ExerciseAssignment.exercise_id == step_ups.id,
        ).order_by(ExerciseAssignment.scheduled_for.desc()).limit(1)
    )
    clip = db.scalar(select(Attachment).where(
        Attachment.storage_key == "test/showcase/cole-step-ups.mp4"))
    assert latest.video_attachment_id == clip.id and latest.reviewed_at is None
    line = db.get(Message, clip.message_id)
    assert line.patient_id == "hirt-cole" and line.text.startswith(f"Did {step_ups.title}")
    assert db.scalar(select(func.count(Message.id)).where(
        Message.patient_id == "hirt-cole", Message.text.startswith("Did "))) == 1
    assert db.scalar(select(func.count(ExerciseAssignment.id)).where(
        ExerciseAssignment.patient_id == "hirt-cole",
        ExerciseAssignment.video_attachment_id.is_not(None))) == 1

    db.delete(db.get(Patient, "abandoned-signup"))
    db.get(Patient, "hirt-cole").phone = hirt.PHONES["hirt-cole"]
    db.get(Patient, "jalen-okoro").phone = None
    db.commit()


def test_the_clinic_fill_leaves_a_row_of_another_kind_alone(db):
    """An id on the roster that belongs to a subscriber's space is skipped
    and reported, never overwritten."""
    from app.personal.scope import PERSONAL

    lucia = db.get(Patient, "lucia")
    was = lucia.account_kind
    lucia.account_kind = PERSONAL
    db.commit()
    try:
        report = demo_fill.fill(db, TODAY)
        assert report["skipped"] == {"lucia": "the row with this id is a personal account"}
        assert "lucia" not in report["personas"] and "lucia" not in report["tiers"]
    finally:
        db.get(Patient, "lucia").account_kind = was
        db.commit()
    assert "lucia" in demo_fill.fill(db, TODAY)["personas"]


def test_health_reports_the_day_the_showcase_was_filled(api, filled, monkeypatch):
    import app.api.system as system

    _Session, engine, _report = filled
    monkeypatch.setattr(system, "engine", engine)
    assert api.get("/api/health").json()["showcase"] == {"filled_on": TODAY.isoformat()}

    # Never filled, and a database from before the table existed: both null.
    directory = tempfile.mkdtemp(prefix="showcase-tests-health-")
    try:
        never = _engine(directory, "never.db")
        monkeypatch.setattr(system, "engine", never)
        assert api.get("/api/health").json()["showcase"] == {"filled_on": None}
        older = create_engine(f"sqlite:///{directory}/older.db")
        monkeypatch.setattr(system, "engine", older)
        body = api.get("/api/health").json()
        assert body["showcase"] == {"filled_on": None} and body["db_ok"] is True
        never.dispose()
        older.dispose()
    finally:
        shutil.rmtree(directory, ignore_errors=True)
