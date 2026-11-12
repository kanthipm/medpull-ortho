"""The acting clinic and the workspace list.

A staff console (the staff token, or the open demo) can look at one clinic
at a time: the workspace menu sends ``X-MedPull-Clinic: <hospital id>`` and
every roster read narrows to that hospital, with the same briefing and Ask
answers its own credential gets. It narrows lists only: staff still open any
clinic chart by id, and an org credential ignores the header.

``GET /api/console/workspaces`` is what the menu lists. Also here: a console
route that opens a chart by id never opens a subscriber's or an athlete's row.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import delete, event

from app.console_credentials import mint
from app.database import SessionLocal
from app.models.enums import NotificationChannel, ProcedureType
from app.models.notification import Notification
from app.models.patient import Patient
from app.models.personal import PersonalProfile
from tests.test_mobile import _forget_patient

METHODIST = {"linda", "aisha", "elena"}
HERMANN = {"robert", "grace"}
HIRT = {"hirt-cole", "hirt-tessa", "hirt-devon", "hirt-june", "hirt-rafael"}

ACTING = "X-MedPull-Clinic"
MEMBER_ID = "showcase-member-test"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _acting(hospital_id: str, token: str | None = None) -> dict:
    return {ACTING: hospital_id, **(_auth(token) if token else {})}


@pytest.fixture(scope="module", autouse=True)
def sports(seeded_db):
    """Athletes on the team boards, so the workspace list has teams with a
    roster and there is an athlete's row to refuse."""
    from app.sports.seed import ROSTER, _reset, seed_sports

    seed_sports(seeded_db, date.today())
    yield
    for spec in ROSTER:
        _reset(seeded_db, spec.id)


@pytest.fixture(scope="module")
def tokens(seeded_db):
    minted = {
        "methodist": mint(seeded_db, "hospital", "hosp_methodist", "Methodist console"),
        "hermann": mint(seeded_db, "hospital", "hosp_hermann", "Hermann console"),
        "mbb": mint(seeded_db, "team", "rice-mbb", "Rice MBB staff"),
        "rice": mint(seeded_db, "sports_org", "rice", "Rice athletics"),
        "staff": mint(seeded_db, "all", None, "Ops laptop"),
    }
    yield {name: token for name, (_row, token) in minted.items()}
    for row, _token in minted.values():
        seeded_db.delete(row)
    seeded_db.commit()


@pytest.fixture()
def member(db):
    """A throwaway Personal profile: a subscriber's row, never a chart."""
    today = date.today()
    db.add(Patient(
        id=MEMBER_ID, name="Jordan Avery", initials="JA", age=34, sex="F",
        procedure_type=ProcedureType.NONE, procedure_display="Train and perform",
        surgery_date=today - timedelta(days=30), discharge_date=today - timedelta(days=30),
        surgeon_id="ct_alvarez", assigned_provider_id="ct_alvarez", account_kind="personal",
    ))
    db.add(PersonalProfile(patient_id=MEMBER_ID, goal="performance", sport="running"))
    db.commit()
    yield db.get(Patient, MEMBER_ID)
    db.execute(delete(PersonalProfile).where(PersonalProfile.patient_id == MEMBER_ID))
    _forget_patient(db, MEMBER_ID)


@pytest.fixture()
def commits():
    """Counts commits made through the app's sessionmaker, the same hook the
    AWS storage layer uses to decide a request changed the database."""
    seen: list[int] = []

    def note(_session) -> None:
        seen.append(1)

    event.listen(SessionLocal, "after_commit", note)
    yield seen
    event.remove(SessionLocal, "after_commit", note)


def _worklist(client, headers=None) -> dict:
    resp = client.get("/api/worklist", headers=headers or {})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(body: dict) -> set[str]:
    return {p["id"] for p in body["patients"]}


# --- the header ---------------------------------------------------------------------------


def test_a_staff_console_acting_for_a_clinic_lists_that_clinic_only(client, tokens):
    everyone = _ids(_worklist(client))
    assert METHODIST <= everyone and HERMANN <= everyone and HIRT <= everyone
    # The open console, the staff token's twin and an 'all' credential alike.
    assert _ids(_worklist(client, _acting("hosp_methodist"))) == METHODIST
    assert _ids(_worklist(client, _acting("hirt", tokens["staff"]))) == HIRT
    body = _worklist(client, _acting("hosp_hermann"))
    assert _ids(body) == HERMANN and body["stats"]["total"] == len(HERMANN)


@pytest.mark.parametrize("value", ["", "all", "ALL", "hosp_nowhere", "  "])
def test_an_unknown_or_cleared_clinic_is_all_clinics(client, value):
    ids = _ids(_worklist(client, {ACTING: value}))
    assert METHODIST <= ids and HERMANN <= ids and HIRT <= ids
    session = client.get("/api/console/session", headers={ACTING: value}).json()
    assert session["acting_clinic"] is None


def test_an_org_credential_ignores_the_header(client, tokens):
    headers = _acting("hosp_methodist", tokens["hermann"])
    assert _ids(_worklist(client, headers)) == HERMANN
    session = client.get("/api/console/session", headers=headers).json()
    assert session["scope"]["org_id"] == "hosp_hermann" and session["acting_clinic"] is None
    # A team credential stays a team credential: no clinic chart at all.
    assert _ids(_worklist(client, _acting("hosp_methodist", tokens["mbb"]))) == set()


def test_the_session_names_the_acting_clinic(client, tokens):
    session = client.get("/api/console/session", headers=_acting("hirt")).json()
    assert session == {
        "scope": {"kind": "all", "org_id": None, "label": "MedPull", "name": "MedPull"},
        "acting_clinic": {"id": "hirt", "name": "H.I.R.T. Physical Therapy"},
    }
    assert client.get("/api/console/session").json()["acting_clinic"] is None
    staff = client.get("/api/console/session", headers=_acting("hosp_methodist", tokens["staff"]))
    assert staff.json()["acting_clinic"] == {"id": "hosp_methodist",
                                             "name": "Houston Methodist Hospital"}


# --- what is keyed by roster ----------------------------------------------------------------


def test_the_acting_clinic_reads_the_briefing_its_own_credential_reads(client, tokens):
    own = _worklist(client, _auth(tokens["methodist"]))["briefing"]
    acting = _worklist(client, _acting("hosp_methodist"))["briefing"]
    # The same cached row, not a second briefing about the same people.
    assert acting == own and acting["text"]
    # And never the all-clinics briefing, which leads with the demo
    # hospital's high-risk case.
    everyone = _worklist(client)["briefing"]
    assert "Marcus" in everyone["text"] or "Reyes" in everyone["text"]
    assert "Marcus" not in acting["text"] and "Reyes" not in acting["text"]
    assert acting["text"] != everyone["text"]


def test_ask_answers_over_the_acting_clinic(client, tokens):
    question = {"question": "Who needs urgent attention today?"}
    everyone = client.post("/api/ask", json=question).json()
    assert "reyes" in everyone["patient_ids"]
    own = client.post("/api/ask", headers=_auth(tokens["methodist"]), json=question).json()
    acting = client.post("/api/ask", headers=_acting("hosp_methodist"), json=question).json()
    assert set(acting["patient_ids"]) <= METHODIST
    assert acting["answer"] == own["answer"] and acting["patient_ids"] == own["patient_ids"]
    assert "Marcus" not in acting["answer"]


def test_the_warm_pass_stays_inside_the_acting_clinic(client):
    warm = client.post("/api/narratives/warm", headers=_acting("hosp_methodist"),
                       json={"worklist": True})
    assert warm.status_code == 200, warm.text
    assert {g["patient_id"] for g in warm.json()["generated"] if g["patient_id"]} <= METHODIST


def test_the_bell_lists_the_acting_clinics_alerts(client, db):
    mine = Notification(patient_id="linda", recipient_id="ct_alvarez", kind="test",
                        title="Linda", body="methodist", channel=NotificationChannel.IN_APP)
    theirs = Notification(patient_id="robert", recipient_id="ct_alvarez", kind="test",
                          title="Robert", body="hermann", channel=NotificationChannel.IN_APP)
    db.add_all([mine, theirs])
    db.commit()
    try:
        listed = client.get("/api/notifications", headers=_acting("hosp_methodist")).json()
        ids = {n["id"] for n in listed["notifications"]}
        assert mine.id in ids and theirs.id not in ids
        assert {n["patient_id"] for n in listed["notifications"]} <= METHODIST
        everything = {n["id"] for n in client.get("/api/notifications").json()["notifications"]}
        assert {mine.id, theirs.id} <= everything
    finally:
        db.execute(delete(Notification).where(Notification.id.in_([mine.id, theirs.id])))
        db.commit()


def test_the_exercise_calendar_acts_for_the_acting_clinic(client, tokens):
    def roster(headers) -> set[str]:
        resp = client.get("/api/hep/schedule", headers=headers)
        assert resp.status_code == 200, resp.text
        return {p["id"] for p in resp.json()["patients"]}

    assert roster(_acting("hirt")) == HIRT
    assert roster(_acting("hosp_methodist")) == METHODIST
    # Ahead of HEP_CLINIC_ID and the biggest-roster default; a hospital
    # credential still acts for its own clinic whatever the header says.
    assert roster(_acting("hirt", tokens["methodist"])) == METHODIST
    assert client.get("/api/hep/schedule", headers=_acting("hirt", tokens["mbb"])).status_code == 403


# --- it narrows lists and nothing else ------------------------------------------------------


def test_staff_acting_for_a_clinic_still_open_any_chart_and_keep_their_pages(client):
    headers = _acting("hosp_methodist")
    for path in ("/api/patients/robert", "/api/patients/robert/overview",
                 "/api/patients/hirt-cole/raw-data"):
        assert client.get(path, headers=headers).status_code == 200, path
    assert client.get("/api/integrations", headers=headers).status_code == 200
    assert client.get("/api/notification-preferences", headers=headers).status_code == 200
    assert client.get("/api/sports/teams", headers=headers).status_code == 200


# --- a chart opened by id is a clinic chart ---------------------------------------------------

CHART_READS = [
    "", "/overview", "/metrics", "/timeline", "/checkins", "/tasks", "/messages", "/plan",
    "/next-steps", "/care-metrics", "/raw-data", "/wearables", "/observations?metric_type=steps",
]


@pytest.mark.parametrize("suffix", CHART_READS)
def test_a_console_never_opens_a_subscriber_or_an_athlete_by_id(client, member, tokens, suffix):
    # The open console and a staff credential see every hospital, and still
    # a member's profile and an athlete's row are not charts.
    for headers in ({}, _auth(tokens["staff"]), _acting("hosp_methodist")):
        for row_id in (MEMBER_ID, "kwame-asante"):
            resp = client.get(f"/api/patients/{row_id}{suffix}", headers=headers)
            assert resp.status_code == 404, f"{row_id}{suffix}: {resp.status_code}"
            assert resp.json()["detail"] == "Unknown patient"
    assert client.get(f"/api/patients/linda{suffix}").status_code == 200


def test_a_console_cannot_act_on_a_subscriber_or_an_athlete(client, member):
    for row_id in (MEMBER_ID, "kwame-asante"):
        assert client.post(f"/api/patients/{row_id}/recompute").status_code == 404
        assert client.post(f"/api/patients/{row_id}/actions/message",
                           json={"text": "hello"}).status_code == 404
        assert client.patch(f"/api/patients/{row_id}/contact",
                            json={"phone": None}).status_code == 404
        # The sign-up folded into a chart must be a chart too.
        assert client.post("/api/patients/linda/app-link",
                           json={"from_patient_id": row_id}).status_code == 404


# --- the workspace list --------------------------------------------------------------------


def test_the_staff_workspace_list_has_clinics_and_teams(client, tokens, commits):
    body = client.get("/api/console/workspaces").json()
    assert set(body) == {"demo", "versions", "clinics", "acting_clinic", "members", "teams"}
    assert body["demo"] is False and body["acting_clinic"] is None
    # Personal is demo-stack only, and the suite is not the demo stack.
    assert body["versions"] == ["clinic", "sports"] and body["members"] == []

    clinics = body["clinics"]
    assert all(set(c) == {"id", "name", "patients", "hep"} for c in clinics)
    by_id = {c["id"]: c for c in clinics}
    assert by_id["hosp_methodist"]["patients"] == len(METHODIST)
    assert by_id["hosp_hermann"]["patients"] == len(HERMANN)
    assert by_id["hirt"] == {"id": "hirt", "name": "H.I.R.T. Physical Therapy",
                             "patients": len(HIRT), "hep": True}
    assert by_id["hosp_methodist"]["hep"] is False
    # Most charts first, and no hospital without a chart.
    counts = [c["patients"] for c in clinics]
    assert counts == sorted(counts, reverse=True) and min(counts) >= 1

    teams = body["teams"]
    assert all(set(t) == {"id", "name", "org_id", "org_name", "sport", "roster"} for t in teams)
    assert all(t["roster"] >= 1 for t in teams)
    mbb = next(t for t in teams if t["id"] == "rice-mbb")
    assert mbb["name"] == "Men's Basketball" and mbb["org_id"] == "rice"
    assert mbb["org_name"] == "Rice" and mbb["sport"] == "basketball"
    assert [t["roster"] for t in teams] == sorted((t["roster"] for t in teams), reverse=True)

    acting = client.get("/api/console/workspaces", headers=_acting("hirt")).json()
    assert acting["acting_clinic"] == {"id": "hirt", "name": "H.I.R.T. Physical Therapy"}
    # The menu still lists every clinic to switch to.
    assert acting["clinics"] == clinics
    # Neither read wrote anything.
    client.get("/api/console/session", headers=_acting("hirt"))
    assert commits == []


def test_a_hospital_credential_lists_its_one_clinic(client, tokens, commits):
    headers = _auth(tokens["methodist"])
    client.get("/api/console/session", headers=headers)  # the hourly last-used stamp
    commits.clear()
    body = client.get("/api/console/workspaces", headers=headers).json()
    assert body["versions"] == ["clinic"]
    assert body["clinics"] == [{"id": "hosp_methodist", "name": "Houston Methodist Hospital",
                                "patients": len(METHODIST), "hep": False}]
    assert body["teams"] == [] and body["members"] == [] and body["acting_clinic"] is None
    assert commits == []


def test_sports_credentials_list_their_teams(client, tokens):
    team = client.get("/api/console/workspaces", headers=_auth(tokens["mbb"])).json()
    assert team["versions"] == ["sports"] and team["clinics"] == [] and team["members"] == []
    assert [t["id"] for t in team["teams"]] == ["rice-mbb"]
    org = client.get("/api/console/workspaces", headers=_auth(tokens["rice"])).json()
    assert org["versions"] == ["sports"] and org["clinics"] == []
    assert org["teams"] and {t["org_id"] for t in org["teams"]} == {"rice"}
    assert "rice-mbb" in {t["id"] for t in org["teams"]}


def test_personal_is_listed_on_the_demo_stack_for_staff_only(client, member, tokens, monkeypatch):
    from app.config import settings
    from app.personal import showcase

    # Off the demo stack the members are never asked for, let alone listed.
    monkeypatch.setattr(showcase, "members", lambda db: [member])
    body = client.get("/api/console/workspaces").json()
    assert "personal" not in body["versions"] and body["members"] == []

    monkeypatch.setattr(settings, "demo_mode", True)
    body = client.get("/api/console/workspaces").json()
    assert body["demo"] is True
    assert body["versions"] == ["clinic", "personal", "sports"]
    assert body["members"] == [{"id": MEMBER_ID, "name": "Jordan Avery", "goal": "performance",
                                "tagline": "Train and perform"}]
    # A clinic's or a team's credential never sees a member.
    for name in ("methodist", "mbb"):
        scoped = client.get("/api/console/workspaces", headers=_auth(tokens[name])).json()
        assert scoped["members"] == [] and "personal" not in scoped["versions"]

    # A demo stack with no members yet lists no Personal version.
    monkeypatch.setattr(showcase, "members", lambda db: [])
    assert "personal" not in client.get("/api/console/workspaces").json()["versions"]


def test_a_member_in_the_registry_carries_its_tagline(client, member, monkeypatch):
    from app.config import settings
    from app.personal import showcase
    from app.seed import showcase as registry

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(showcase, "members", lambda db: [member])
    monkeypatch.setattr(registry, "REGISTRY", (registry.Persona(
        id=MEMBER_ID, name="Jordan Avery", version="personal", org_id="personal",
        org_name="MedPull Personal", tagline="Half-marathon build · week 9"),))
    members = client.get("/api/console/workspaces").json()["members"]
    assert members[0]["tagline"] == "Half-marathon build · week 9"
