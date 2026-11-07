"""Org-scoped console credentials.

One console, several doors. The staff token (or an open console) sees every
hospital and every team; a hospital credential sees its own roster and
nothing else; a team credential one board, a sports-org credential one
program's boards. An id outside the scope is a 404, so nothing leaks; the
staff-only screens are a 403 that says so. The suite's console is open, so
these tests are also the proof that an org token narrows an open demo.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.console_credentials import mint, resolve, revoke
from app.models.credential import ConsoleCredential
from app.models.enums import NotificationChannel
from app.models.notification import Notification
from app.models.patient import Patient
from tests.test_mobile import _forget_patient

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "admin_db.py"

# The ortho demo roster the suite seeds (app/seed/patients.py), by hospital.
METHODIST = {"linda", "aisha", "elena"}
HERMANN = {"robert", "grace"}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
def sports(seeded_db):
    """The team boards need athletes; the clinic tests do not mind them."""
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


def _worklist_ids(client, headers=None) -> set[str]:
    resp = client.get("/api/worklist", headers=headers or {})
    assert resp.status_code == 200, resp.text
    return {p["id"] for p in resp.json()["patients"]}


# --- who sees what -------------------------------------------------------------------------


def test_an_open_console_with_no_token_sees_every_hospital(client):
    from app.config import settings

    assert settings.console_access_token == ""
    assert client.get("/api/health").json()["console_auth"] is False
    ids = _worklist_ids(client)
    assert METHODIST <= ids and HERMANN <= ids
    session = client.get("/api/console/session").json()
    assert session == {"scope": {"kind": "all", "org_id": None, "label": "MedPull",
                                 "name": "MedPull"}}


def test_the_staff_token_sees_every_hospital_and_locks_the_door(client, monkeypatch, tokens):
    from app.config import settings

    monkeypatch.setattr(settings, "console_access_token", "open-sesame")
    assert client.get("/api/worklist").status_code == 401
    assert client.get("/api/console/session").status_code == 401
    wrong = client.get("/api/console/session", headers=_auth("not-it"))
    assert wrong.status_code == 401 and wrong.json()["detail"] == "That access token is not right"
    ids = _worklist_ids(client, _auth("open-sesame"))
    assert METHODIST <= ids and HERMANN <= ids
    assert client.get("/api/console/session", headers=_auth("open-sesame")).json()["scope"] == {
        "kind": "all", "org_id": None, "label": "MedPull", "name": "MedPull",
    }
    # A minted credential opens the locked door too, as its own scope.
    assert _worklist_ids(client, _auth(tokens["methodist"])) == METHODIST
    # The team board is behind the same door now.
    assert client.get("/api/sports/teams").status_code == 401
    assert client.get("/api/sports/teams", headers=_auth(tokens["mbb"])).status_code == 200
    # An 'all' credential is staff without being the global token.
    assert HERMANN <= _worklist_ids(client, _auth(tokens["staff"]))


def test_a_hospital_token_narrows_an_open_console_to_its_roster(client, tokens):
    headers = _auth(tokens["methodist"])
    assert _worklist_ids(client, headers) == METHODIST
    body = client.get("/api/worklist", headers=headers).json()
    assert body["stats"]["total"] == len(METHODIST)
    # The briefing is about this roster, not the demo hospital's high-risk case.
    assert body["briefing"]["text"]
    assert "Marcus" not in body["briefing"]["text"] and "Reyes" not in body["briefing"]["text"]
    assert _worklist_ids(client, _auth(tokens["hermann"])) == HERMANN
    assert client.get("/api/console/session", headers=headers).json()["scope"] == {
        "kind": "hospital", "org_id": "hosp_methodist", "label": "Methodist console",
        "name": "Houston Methodist Hospital",
    }


PATIENT_READS = [
    "", "/overview", "/metrics", "/timeline", "/checkins", "/tasks", "/messages", "/plan",
    "/next-steps", "/care-metrics", "/raw-data", "/wearables", "/app-link/candidates",
    "/observations?metric_type=steps",
    "/attachments/upload-ticket?content_type=image/jpeg&byte_size=100",
]


@pytest.mark.parametrize("suffix", PATIENT_READS)
def test_a_hospital_token_reads_its_own_patient_and_404s_on_another(client, tokens, suffix):
    headers = _auth(tokens["methodist"])
    assert client.get(f"/api/patients/linda{suffix}", headers=headers).status_code == 200
    other = client.get(f"/api/patients/robert{suffix}", headers=headers)
    assert other.status_code == 404, other.text
    assert other.json()["detail"] == "Unknown patient"


def test_a_hospital_token_cannot_act_on_another_hospitals_patient(client, tokens):
    headers = _auth(tokens["methodist"])
    posts = [
        ("/api/patients/robert/actions/escalate", None),
        ("/api/patients/robert/actions/daily-checkin", None),
        ("/api/patients/robert/recompute", None),
        ("/api/patients/robert/actions/draft-message", None),
        ("/api/patients/robert/messages/read", None),
        ("/api/patients/robert/checkin-invite", {"phone": "+15125550100"}),
        ("/api/patients/robert/actions/message", {"text": "hello"}),
        ("/api/patients/robert/actions/assign-task", {"title": "Walk", "notify": False}),
        ("/api/patients/robert/plan/suggest", None),
        ("/api/patients/robert/messages/draft", {"intent": "check in"}),
        ("/api/patients/robert/next-steps/checkin/execute", None),
        ("/api/patients/robert/app-link", {"from_patient_id": "linda"}),
        ("/api/patients/robert/wearables/junction/link", None),
        ("/api/narratives/warm", {"patient_id": "robert", "worklist": False}),
        ("/api/task-builder/draft", {"text": "walk daily", "patient_id": "robert"}),
    ]
    for path, body in posts:
        resp = client.post(path, headers=headers, json=body) if body is not None else \
            client.post(path, headers=headers)
        assert resp.status_code == 404, f"{path}: {resp.status_code} {resp.text}"
    assert client.patch("/api/patients/robert/contact", headers=headers,
                        json={"phone": None}).status_code == 404
    assert client.delete("/api/patients/robert/wearables/junction", headers=headers).status_code == 404
    # The other side of the merge must be in scope too.
    assert client.post("/api/patients/linda/app-link", headers=headers,
                       json={"from_patient_id": "robert"}).status_code == 404
    # The warm call for the roster is answered, and names nobody else's patient.
    warm = client.post("/api/narratives/warm", headers=headers, json={"worklist": True})
    assert warm.status_code == 200
    assert {g["patient_id"] for g in warm.json()["generated"] if g["patient_id"]} <= METHODIST


def test_link_candidates_stay_inside_the_hospital(client, db, tokens):
    headers = _auth(tokens["methodist"])
    # Robert has a number on file, which makes him a candidate for everyone
    # on an unscoped console.
    db.get(Patient, "robert").phone = "+15125550777"
    db.commit()
    try:
        everyone = client.get("/api/patients/linda/app-link/candidates").json()["candidates"]
        assert "robert" in {c["patient_id"] for c in everyone}
        scoped = client.get("/api/patients/linda/app-link/candidates",
                            headers=headers).json()["candidates"]
        assert "robert" not in {c["patient_id"] for c in scoped}
        assert all(c["hospital_id"] == "hosp_methodist" for c in scoped)
    finally:
        db.get(Patient, "robert").phone = None
        db.commit()


def test_notifications_are_only_about_patients_in_scope(client, db, tokens):
    headers = _auth(tokens["methodist"])
    mine = Notification(patient_id="linda", recipient_id="ct_alvarez", kind="test",
                        title="Linda", body="in scope", channel=NotificationChannel.IN_APP)
    theirs = Notification(patient_id="robert", recipient_id="ct_alvarez", kind="test",
                          title="Robert", body="out of scope", channel=NotificationChannel.IN_APP)
    db.add_all([mine, theirs])
    db.commit()
    try:
        listed = client.get("/api/notifications", headers=headers).json()["notifications"]
        ids = {n["id"] for n in listed}
        assert mine.id in ids and theirs.id not in ids
        assert {n["patient_id"] for n in listed} <= METHODIST
        assert client.post(f"/api/notifications/{theirs.id}/read", headers=headers).status_code == 404
        assert client.post(f"/api/notifications/{mine.id}/read", headers=headers).status_code == 200
        # read-all retires this console's alerts only
        client.post("/api/notifications/read-all", headers=headers)
        db.expire_all()
        assert db.get(Notification, theirs.id).status == "unread"
        assert db.get(Notification, mine.id).status == "read"
    finally:
        db.execute(delete(Notification).where(Notification.id.in_([mine.id, theirs.id])))
        db.commit()


def test_ask_answers_over_the_scoped_roster_only(client, tokens):
    question = {"question": "Who needs urgent attention today?"}
    everyone = client.post("/api/ask", json=question).json()
    assert "reyes" in everyone["patient_ids"]  # the demo hospital's high-risk case
    scoped = client.post("/api/ask", headers=_auth(tokens["methodist"]), json=question).json()
    assert set(scoped["patient_ids"]) <= METHODIST
    assert "Marcus" not in scoped["answer"]


# --- the team boards --------------------------------------------------------------------------


def test_sports_routes_are_a_404_for_a_hospital_token(client, tokens):
    headers = _auth(tokens["methodist"])
    assert client.get("/api/sports/teams", headers=headers).status_code == 404
    assert client.get("/api/sports/teams/rice-mbb/dashboard", headers=headers).status_code == 404
    assert client.get("/api/sports/teams/rice-mbb/events", headers=headers).status_code == 404
    assert client.get("/api/sports/teams/rice-mbb/athletes/kwame-asante",
                      headers=headers).status_code == 404
    assert client.post("/api/sports/teams/rice-mbb/events", headers=headers, json={
        "date": date.today().isoformat(), "kind": "practice", "title": "Shootaround",
    }).status_code == 404
    assert client.patch("/api/sports/teams/rice-mbb/athletes/jalen-okoro/status", headers=headers,
                        json={"status": "out"}).status_code == 404
    assert client.post("/api/sports/teams/rice-mbb/athletes/kwame-asante/message", headers=headers,
                       json={"text": "hi"}).status_code == 404
    assert client.delete("/api/sports/teams/rice-mbb/events/1", headers=headers).status_code == 404


def test_a_team_token_sees_its_own_board_and_no_clinic_chart(client, tokens):
    headers = _auth(tokens["mbb"])
    orgs = client.get("/api/sports/teams", headers=headers).json()["orgs"]
    assert [o["id"] for o in orgs] == ["rice"]
    assert [t["id"] for t in orgs[0]["teams"]] == ["rice-mbb"]
    board = client.get("/api/sports/teams/rice-mbb/dashboard", headers=headers)
    assert board.status_code == 200 and board.json()["team"]["id"] == "rice-mbb"
    assert client.get("/api/sports/teams/rice-wbb/dashboard", headers=headers).status_code == 404
    assert client.get("/api/sports/teams/rockets-nba/events", headers=headers).status_code == 404
    assert client.post("/api/sports/teams/rice-wbb/events", headers=headers, json={
        "date": date.today().isoformat(), "kind": "practice", "title": "Not ours",
    }).status_code == 404
    # No clinic chart is a team's business.
    assert _worklist_ids(client, headers) == set()
    assert client.get("/api/patients/linda", headers=headers).status_code == 404
    assert client.get("/api/notifications", headers=headers).json()["notifications"] == []
    assert client.get("/api/console/session", headers=headers).json()["scope"] == {
        "kind": "team", "org_id": "rice-mbb", "label": "Rice MBB staff",
        "name": "Rice Men's Basketball",
    }


def test_a_sports_org_token_sees_every_board_in_its_program(client, tokens):
    headers = _auth(tokens["rice"])
    orgs = client.get("/api/sports/teams", headers=headers).json()["orgs"]
    assert [o["id"] for o in orgs] == ["rice"]
    assert {"rice-mbb", "rice-wbb"} <= {t["id"] for t in orgs[0]["teams"]}
    assert client.get("/api/sports/teams/rice-wbb/dashboard", headers=headers).status_code == 200
    assert client.get("/api/sports/teams/rockets-nba/dashboard", headers=headers).status_code == 404
    assert client.get("/api/console/session", headers=headers).json()["scope"]["name"] == \
        "Rice University Athletics"
    # Staff (the open console here) still see every program.
    assert len(client.get("/api/sports/teams").json()["orgs"]) > 1


# --- staff-only surfaces ------------------------------------------------------------------------


@pytest.mark.parametrize("token_name", ["methodist", "mbb"])
def test_staff_only_routes_are_a_403_for_org_tokens(client, tokens, token_name):
    headers = _auth(tokens[token_name])
    for method, path, body in [
        ("GET", "/api/integrations", None),
        ("GET", "/api/integrations/junction/status", None),
        ("POST", "/api/integrations/junction/connect", None),
        ("GET", "/api/notification-preferences", None),
        ("PUT", "/api/notification-preferences", []),
        ("POST", "/api/task-templates", {"title": "Walk twice a day"}),
        ("PATCH", "/api/task-templates/1", {"pinned": True}),
        ("POST", "/api/message-templates", {"title": "Hello", "body": "How are you feeling today?"}),
        ("PATCH", "/api/message-templates/1", {"pinned": True}),
    ]:
        resp = client.request(method, path, headers=headers, json=body)
        assert resp.status_code == 403, f"{method} {path}: {resp.status_code} {resp.text}"
        assert "MedPull staff" in resp.json()["detail"]
    # What the patient page needs stays readable: the shared library and the glossary.
    assert client.get("/api/task-templates", headers=headers).status_code == 200
    assert client.get("/api/message-templates", headers=headers).status_code == 200
    assert client.get("/api/explain", headers=headers).status_code == 200
    # And staff keep them.
    assert client.get("/api/integrations").status_code == 200
    assert client.get("/api/notification-preferences").status_code == 200


# --- creating patients ----------------------------------------------------------------------------


def test_a_hospital_token_creates_patients_on_its_own_roster_only(client, db, tokens):
    headers = _auth(tokens["methodist"])
    assert client.post("/api/patients/", headers=headers, json={
        "hospital_id": "hosp_hermann", "name": "Wrong Roster"}).status_code == 403
    assert client.post("/api/patients/", headers=_auth(tokens["mbb"]), json={
        "hospital_id": "hosp_methodist", "name": "Not A Clinic"}).status_code == 403
    assert client.post("/api/patients/", headers=headers, json={
        "hospital_id": "hosp_nowhere", "name": "No Such Hospital"}).status_code == 403
    created = client.post("/api/patients/", headers=headers, json={
        "hospital_id": "hosp_methodist", "name": "Scoped Create"})
    assert created.status_code == 200, created.text
    pid = created.json()["patient"]["id"]
    try:
        assert pid in _worklist_ids(client, headers)
        assert pid not in _worklist_ids(client, _auth(tokens["hermann"]))
    finally:
        _forget_patient(db, pid)
    # Staff (an open console here) may add to any roster, but not to a hospital
    # that does not exist.
    assert client.post("/api/patients/", json={
        "hospital_id": "hosp_nowhere", "name": "No Such Hospital"}).status_code == 422
    staff = client.post("/api/patients/", json={"hospital_id": "hosp_hermann", "name": "Any Roster"})
    assert staff.status_code == 200, staff.text
    _forget_patient(db, staff.json()["patient"]["id"])


# --- the credential itself ----------------------------------------------------------------------


def test_a_revoked_token_is_refused_at_once(client, db):
    row, token = mint(db, "hospital", "hosp_methodist", "short-lived")
    try:
        assert client.get("/api/console/session", headers=_auth(token)).status_code == 200
        revoke(db, row.id)
        refused = client.get("/api/worklist", headers=_auth(token))
        assert refused.status_code == 401
        assert refused.json()["detail"] == "That access token is not right"
        assert client.get("/api/console/session", headers=_auth(token)).status_code == 401
        # revoking again keeps the first stamp
        stamp = row.revoked_at
        assert revoke(db, row.id).revoked_at == stamp
    finally:
        db.delete(row)
        db.commit()


def test_minting_checks_the_org_and_stores_only_a_hash(db):
    from app.console_credentials import CredentialError, hash_token

    with pytest.raises(CredentialError):
        mint(db, "clinic", "hosp_demo", "bad kind")
    with pytest.raises(CredentialError):
        mint(db, "hospital", "hosp_nowhere", "no such hospital")
    with pytest.raises(CredentialError):
        mint(db, "team", None, "no team id")
    with pytest.raises(CredentialError):
        mint(db, "all", "hosp_demo", "all takes no org")
    with pytest.raises(CredentialError):
        mint(db, "hospital", "hosp_demo", "   ")
    row, token = mint(db, "team", "rice-wten", "  Tennis   staff ")
    try:
        assert token.startswith("mp_") and len(token) > 30
        assert row.label == "Tennis staff" and row.token_hash == hash_token(token)
        assert token not in {row.token_hash, row.label}
        assert resolve(db, token) is row
        assert resolve(db, token + "x") is None
        assert resolve(db, "") is None
    finally:
        db.delete(row)
        db.commit()


def test_last_used_moves_at_most_once_an_hour(db):
    row, token = mint(db, "hospital", "hosp_demo", "stamp test")
    try:
        assert row.last_used_at is None
        assert resolve(db, token) is row
        first = row.last_used_at
        assert first is not None
        assert resolve(db, token) is row and row.last_used_at == first
        row.last_used_at = datetime.now() - timedelta(hours=2)
        db.commit()
        assert resolve(db, token) is row and row.last_used_at > first
    finally:
        db.delete(row)
        db.commit()


# --- the operator script --------------------------------------------------------------------------


@pytest.fixture()
def standalone_db(tmp_path):
    """A database file of its own, seeded, for the script to edit in place."""
    from app.database import Base
    from app.seed.patients import full_roster
    from app.seed.seed import seed_core

    db_path = tmp_path / "recovery.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        hospitals, patients = full_roster()
        seed_core(db, date.today(), roster=(hospitals, patients))
        db.commit()
    engine.dispose()
    return db_path, Session


def _run(db_path, *flags) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--local", str(db_path), *flags],
        capture_output=True, text=True, env={**os.environ},
        cwd=str(Path(__file__).resolve().parents[1]),
    )


def test_admin_db_mints_lists_and_revokes_tokens(standalone_db):
    db_path, Session = standalone_db
    proc = _run(db_path, "--mint-token", "hospital:hosp_demo", "HIRT console")
    assert proc.returncode == 0, proc.stderr[-2000:]
    report = json.loads(proc.stdout[proc.stdout.index("{"):])
    minted = report["minted_tokens"]
    assert len(minted) == 1
    token = minted[0]["token"]
    assert token.startswith("mp_")
    assert minted[0]["kind"] == "hospital" and minted[0]["org_id"] == "hosp_demo"
    assert minted[0]["name"] == "MedPull Demo Hospital" and minted[0]["label"] == "HIRT console"
    assert "token_hash" not in minted[0]
    credential_id = minted[0]["id"]

    # The token is in the output once; the file holds only its hash.
    with Session() as db:
        row = resolve(db, token)
        assert row is not None and row.id == credential_id and row.kind == "hospital"
        assert token not in (row.token_hash, row.label)
        assert db.scalar(select(ConsoleCredential.token_hash)) != token

    listed = _run(db_path, "--report")
    assert listed.returncode == 0, listed.stderr[-2000:]
    report = json.loads(listed.stdout[listed.stdout.index("{"):])
    assert [c["id"] for c in report["credentials"]] == [credential_id]
    assert token not in listed.stdout and "token_hash" not in listed.stdout
    assert report["credentials"][0]["revoked_at"] is None

    revoked = _run(db_path, "--revoke-token", str(credential_id))
    assert revoked.returncode == 0, revoked.stderr[-2000:]
    report = json.loads(revoked.stdout[revoked.stdout.index("{"):])
    assert report["revoked_tokens"][0]["id"] == credential_id
    assert report["revoked_tokens"][0]["revoked_at"] is not None
    with Session() as db:
        assert resolve(db, token) is None

    # Refusals are loud and change nothing.
    bad = _run(db_path, "--mint-token", "clinic:hosp_demo", "bad kind")
    assert bad.returncode != 0 and "Unknown credential kind" in bad.stderr
    missing = _run(db_path, "--mint-token", "team:no-such-team", "no team")
    assert missing.returncode != 0 and "Unknown team" in missing.stderr
    unknown = _run(db_path, "--revoke-token", "999")
    assert unknown.returncode != 0 and "Unknown credential id" in unknown.stderr
    with Session() as db:
        assert db.scalar(select(ConsoleCredential.id).where(ConsoleCredential.id != credential_id)) is None
