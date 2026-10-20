"""MedPull Sports: joining, the boards, logging, the rehab engine, the team
dashboard, and the console's blindness to athletes. The Rice demo roster is
seeded once for the module; accounts created by tests are removed."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.patient import Patient
from app.models.sports import SportsProfile
from app.sports import jump
from app.sports.catalog import INJURIES, MEASURES, TESTS, band_for
from app.sports.catalog import tests_for as sport_tests_for
from app.sports.seed import PASSWORD, ROSTER, seed_sports

EMAIL = "demo.athlete@athletes.medpull.demo"
PWD = "owls-2026-test"


def _consent() -> dict:
    from app.personal.auth import CONSENT_VERSION

    return {"version": CONSENT_VERSION, "signature": "Demo Athlete",
            "scopes": {"beta_ack": True, "data_storage": True, "ai_processing": True, "research_use": False}}


@pytest.fixture(scope="module", autouse=True)
def roster(seeded_db):
    seed_sports(seeded_db, date.today())
    yield
    from app.sports.seed import _reset

    for spec in ROSTER:
        _reset(seeded_db, spec.id)


def _login(client, email: str, password: str = PASSWORD) -> dict:
    resp = client.post("/api/mobile/sports/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['session_token']}"}


# --- catalog -------------------------------------------------------------------------------------


def test_catalog_is_consistent():
    for inj in INJURIES.values():
        for phase in inj.phases:
            for c in phase.exit_criteria:
                assert c.measure_key == "__days" or c.measure_key in MEASURES, (inj.key, c.measure_key)
        for m in inj.measures:
            assert m in MEASURES
    for m in MEASURES.values():
        if m.test_key:
            assert m.test_key in TESTS, m.test_key
    assert len(sport_tests_for("basketball")) > 60
    assert band_for(TESTS["cmj_height"], 44.0, "ncaa_d1", "M")["word"] in ("Solid", "Strong")
    assert band_for(TESTS["lane_agility"], 10.6, "ncaa_d1", "M")["percentile"] >= 90


def test_catalog_route(client):
    resp = client.get("/api/mobile/sports/catalog?sport=basketball")
    assert resp.status_code == 200
    body = resp.json()
    assert any(t["key"] == "vertical_jump_max" for t in body["tests"])
    assert any(i["key"] == "acl_reconstruction" for i in body["injuries"])
    assert body["measures"]["quad_strength"]["sided"] is True
    assert any(d["key"] == "catapult" and d["team"] for d in body["devices"])


# --- joining -------------------------------------------------------------------------------------


def test_join_as_individual_then_join_rice(client, db):
    body = {"name": "Demo Athlete", "email": EMAIL, "password": PWD, "consent": _consent(), "sport": "basketball",
            "position": "Guard", "height_cm": 190.0, "weight_kg": 86.0, "dominant_side": "right", "sex": "M",
            "level": "club", "device_name": "iPhone (test)"}
    resp = client.post("/api/mobile/sports/join", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['session_token']}"}
    pid = data["me"]["patient"]["id"]
    try:
        me = data["me"]
        assert me["patient"]["mode"] == "sports"
        assert me["patient"]["account_kind"] == "sports"
        assert me["sports"]["sport"] == "basketball"
        assert me["sports"]["org"] is None
        assert me["patient"]["hospital"] is None
        # Not on any clinician's roster.
        ids = [p["id"] for p in client.get("/api/worklist").json()["patients"]]
        assert pid not in ids
        # The wrong join code is refused; the right one links the athlete.
        resp = client.post("/api/mobile/sports/org/join", headers=headers,
                           json={"org_id": "rice", "team_id": "rice-mbb", "join_code": "nope"})
        assert resp.status_code == 403
        resp = client.post("/api/mobile/sports/org/join", headers=headers,
                           json={"org_id": "rice", "team_id": "rice-mbb", "join_code": "owls26"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["profile"]["coach_linked"] is True
        assert any(s["role"] == "athletic_trainer" for s in resp.json()["profile"]["staff"])
        # A tennis team is the wrong sport.
        resp = client.post("/api/mobile/sports/org/join", headers=headers,
                           json={"org_id": "rice", "team_id": "rice-wten", "join_code": "owls26"})
        assert resp.status_code == 422
        # The home works with no data: still learning.
        home = client.post("/api/mobile/sports/day", headers=headers).json()
        assert home["verdict"]["kind"] == "learning"
        assert any(t["title"] == "Morning wellness" for t in home["tasks"])
        # Logging wellness and a session.
        resp = client.post("/api/mobile/sports/wellness", headers=headers,
                           json={"answers": {"sleep_quality": 7, "fatigue": 3, "soreness": 2, "stress": 3, "mood": 8}})
        assert resp.status_code == 200
        assert resp.json()["wellness"]["answered_today"] == 5
        resp = client.post("/api/mobile/sports/sessions", headers=headers, json={"kind": "practice", "minutes": 90, "rpe": 7})
        assert resp.status_code == 200 and resp.json()["load_au"] == 630
        # A sided test needs a side; a pair gives an asymmetry.
        resp = client.post("/api/mobile/sports/tests", headers=headers, json={"entries": [{"test_key": "hop_single_distance", "value": 200}]})
        assert resp.status_code == 422
        resp = client.post("/api/mobile/sports/tests", headers=headers, json={"entries": [
            {"test_key": "hop_single_distance", "value": 200, "side": "left"},
            {"test_key": "hop_single_distance", "value": 160, "side": "right"},
            {"test_key": "vertical_jump_max", "value": 33.0}]})
        assert resp.status_code == 200
        perf = resp.json()["performance"]
        card = perf["cards"]["hop_single_distance"]
        assert card["asymmetry"]["weaker"] == "right" and card["asymmetry"]["pct"] == 20.0
        assert card["asymmetry_status"] == "flag"
        assert perf["cards"]["vertical_jump_max"]["band"]["reference"].startswith("ncaa_d1") or \
            perf["cards"]["vertical_jump_max"]["band"]["reference"] == "all"
        # The team now lists the athlete.
        board = client.get("/api/sports/teams/rice-mbb/dashboard").json()
        assert any(r["id"] == pid for r in board["roster"])
        resp = client.post("/api/mobile/sports/org/leave", headers=headers)
        assert resp.status_code == 200 and resp.json()["profile"]["org"] is None
    finally:
        from app.sports.seed import _reset

        _reset(db, pid)


def test_join_rejects_bad_input(client):
    resp = client.post("/api/mobile/sports/join", json={"name": "X", "email": "nope", "password": "short", "sport": "golf"})
    assert resp.status_code == 422


# --- the demo roster -------------------------------------------------------------------------------


def test_roster_boards_read_as_designed(client):
    h = _login(client, "mateo.reyes.vega@athletes.medpull.demo")
    home = client.get("/api/mobile/sports/home", headers=h).json()
    assert home["verdict"]["kind"] in ("rest", "modify")
    assert home["readiness"]["extra"]["score"] < 40
    assert any(s["category"] == "sleep" for s in client.get("/api/mobile/sports/recovery", headers=h).json()["suggestions"])
    h = _login(client, "devin.marsh@athletes.medpull.demo")
    rec = client.get("/api/mobile/sports/recovery", headers=h).json()
    assert rec["load"]["status"] in ("watch", "flag")
    assert rec["neuromuscular"]["status"] in ("watch", "flag")
    h = _login(client, "jalen.okoro@athletes.medpull.demo")
    perf = client.get("/api/mobile/sports/performance", headers=h).json()
    assert perf["logged"] > 30
    assert perf["overall_percentile"] >= 60
    assert perf["neuromuscular"]["status"] == "ok"


def test_stats_read_and_category_summaries(client):
    h = _login(client, "jalen.okoro@athletes.medpull.demo")
    perf = client.get("/api/mobile/sports/performance", headers=h).json()
    jump = next(c for c in perf["categories"] if c["key"] == "jump")
    assert jump["percentile"] is not None and jump["word"] and jump["best"]["key"]
    assert perf["strengths"] and all(x["percentile"] >= 50 for x in perf["strengths"])
    brief = perf["brief"]
    assert brief["provider"] == "fallback"
    assert brief["headline"] and brief["strengths"] and brief["improve"] and len(brief["brief"].split()) >= 10
    h = _login(client, "kwame.asante@athletes.medpull.demo")
    board = client.get("/api/mobile/sports/rehab", headers=h.copy()).json()["active"][0]
    assert board["read"]["headline"] and "phase 4 of 6" in board["read"]["read"].lower()
    assert all(isinstance(g, str) and len(g) > 3 for g in board["phase"]["goals"])


def test_acl_athlete_is_in_phase_four_and_out(client):
    h = _login(client, "kwame.asante@athletes.medpull.demo")
    rehab = client.get("/api/mobile/sports/rehab", headers=h).json()
    assert rehab["availability"] == "out"
    board = rehab["active"][0]
    assert board["injury_key"] == "acl_reconstruction"
    assert board["phase"]["number"] == 4
    assert 20 <= board["weeks"] <= 26
    quad = next(c for c in board["phase"]["criteria"] if c["measure_key"] == "quad_strength")
    assert quad["use"] == "lsi" and quad["met"] is False and 70 <= quad["value"] <= 90
    rts = board["rts"]
    assert rts["total"] >= 10 and rts["met"] < rts["total"]
    assert any(f["kind"] == "measure" for f in board["focus"])
    assert any(m["key"] == "acl_rsi" and m["logged"] for m in board["measures"])
    # The verdict is the plan, not a training call.
    home = client.get("/api/mobile/sports/home", headers=h).json()
    assert home["verdict"]["kind"] == "rehab"
    # Logging a symmetric quad test moves the criterion.
    resp = client.post(f"/api/mobile/sports/injuries/{board['id']}/measures", headers=h, json={"entries": [
        {"measure_key": "quad_strength", "value": 700, "side": "uninvolved", "source": "dynamometer"},
        {"measure_key": "quad_strength", "value": 640, "side": "involved", "source": "dynamometer"}]})
    assert resp.status_code == 200
    quad = next(c for c in resp.json()["injury"]["phase"]["criteria"] if c["measure_key"] == "quad_strength")
    assert quad["met"] is True and quad["value"] == pytest.approx(91.4, abs=0.1)


def test_ankle_athlete_is_modified_in_phase_two(client):
    h = _login(client, "tobias.lindqvist@athletes.medpull.demo")
    rehab = client.get("/api/mobile/sports/rehab", headers=h).json()
    assert rehab["availability"] == "modified"
    board = rehab["active"][0]
    assert board["injury_key"] == "ankle_sprain_lateral" and board["phase"]["number"] == 2
    df = next(c for c in board["phase"]["criteria"] if c["measure_key"] == "ankle_dorsiflexion")
    assert df["use"] == "diff"


def test_report_and_clear_an_injury(client, db):
    h = _login(client, "noah.brennan@athletes.medpull.demo")
    resp = client.post("/api/mobile/sports/injuries", headers=h, json={
        "injury_key": "hamstring_strain", "side": "left", "date_of_injury": (date.today() - timedelta(days=3)).isoformat(),
        "grade": "Grade 1"})
    assert resp.status_code == 200, resp.text
    board = resp.json()["rehab"]["active"][0]
    assert board["phase"]["number"] == 1
    assert resp.json()["rehab"]["availability"] == "out"
    resp = client.patch(f"/api/mobile/sports/injuries/{board['id']}", headers=h, json={"status": "cleared"})
    assert resp.status_code == 200
    assert resp.json()["rehab"]["active"] == []
    db.expire_all()
    profile = db.get(SportsProfile, "noah-brennan")
    assert profile.status == "available"


def test_phone_jump_estimate():
    acc = [[0, 0, 9.81]] * 50 + [[0, 0, 22.0]] * 5 + [[0, 0, 0.4]] * 45 + [[0, 0, 25.0]] * 5 + [[0, 0, 9.81]] * 50
    r = jump.estimate_jump(acc, 100.0)
    assert r["flight_time_ms"] == 450 and r["height_cm"] == pytest.approx(24.8, abs=0.1) and r["confidence"] == "high"
    with pytest.raises(ValueError):
        jump.estimate_jump([[0, 0, 9.81]] * 100, 100.0)


def test_phone_jump_route_logs_the_phone_test(client):
    h = _login(client, "ethan.nakamura@athletes.medpull.demo")
    acc = [[0, 0, 9.81]] * 50 + [[0, 0, 22.0]] * 5 + [[0, 0, 0.4]] * 60 + [[0, 0, 25.0]] * 5 + [[0, 0, 9.81]] * 50
    resp = client.post("/api/mobile/sports/tests/jump", headers=h, json={"accel": acc, "sample_rate_hz": 100})
    assert resp.status_code == 200
    assert resp.json()["height_cm"] > 40
    perf = client.get("/api/mobile/sports/performance", headers=h).json()
    assert "phone_jump_height" in perf["cards"]
    # The force-plate baseline is untouched by the phone reading.
    assert perf["cards"]["cmj_height"]["source"] == "force_plate"


def test_coach_answers_from_the_board_without_a_model(client):
    h = _login(client, "mateo.reyes.vega@athletes.medpull.demo")
    resp = client.post("/api/mobile/agent", headers=h, json={"text": "why is my readiness low today?"})
    assert resp.status_code == 200
    assert "Readiness" in resp.json()["reply"]
    resp = client.post("/api/mobile/agent", headers=h, json={"text": "how is my sleep"})
    assert "Sleep" in resp.json()["reply"]
    h = _login(client, "kwame.asante@athletes.medpull.demo")
    resp = client.post("/api/mobile/agent", headers=h, json={"text": "when can I return from my ACL?"})
    assert "phase 4" in resp.json()["reply"]


# --- the team dashboard ------------------------------------------------------------------------------


def test_team_dashboard(client):
    teams = client.get("/api/sports/teams").json()["orgs"]
    rice = next(o for o in teams if o["id"] == "rice")
    assert teams[0]["kind"] == "college"
    mbb = next(t for t in rice["teams"] if t["id"] == "rice-mbb")
    assert mbb["roster"] == 13
    board = client.get("/api/sports/teams/rice-mbb/dashboard").json()
    s = board["summary"]
    assert s["roster"] == 13 and s["out"] == 1 and s["modified"] == 2
    assert s["answered_today"] >= 10
    names = {r["id"]: r for r in board["roster"]}
    assert names["kwame-asante"]["availability"] == "out"
    assert names["tobias-lindqvist"]["availability"] == "modified"
    assert names["andre-beaumont"]["availability"] == "modified"
    assert names["mateo-reyes-vega"]["readiness"] < 40
    assert names["devin-marsh"]["load_change_pct"] > 15
    assert any(f["key"] == "illness" for f in names["samuel-adeyemi"]["flags"])
    assert board["roster"][0]["severity"] >= board["roster"][-1]["severity"]
    assert any(e["kind"] == "game" for e in board["events"])
    assert len(board["load"]) >= 20
    assert any(i["athlete_id"] == "kwame-asante" for i in board["injuries"])
    detail = client.get("/api/sports/teams/rice-mbb/athletes/kwame-asante").json()
    assert detail["rehab"]["active"][0]["phase"]["number"] == 4
    assert detail["brief"]["brief"]
    resp = client.post("/api/sports/teams/rice-mbb/athletes/kwame-asante/message",
                       json={"text": "Nice hop numbers this week.", "staff_id": "st_rice_at"})
    assert resp.status_code == 200
    h = _login(client, "kwame.asante@athletes.medpull.demo")
    thread = client.get("/api/mobile/messages", headers=h).json()["messages"]
    assert any("Nice hop numbers" in m["text"] and m["authored_by"] == "care_team" for m in thread)
    resp = client.patch("/api/sports/teams/rice-mbb/athletes/jalen-okoro/status", json={"status": "modified", "note": "Rest day"})
    assert resp.status_code == 200
    board = client.get("/api/sports/teams/rice-mbb/dashboard").json()
    assert {r["id"]: r for r in board["roster"]}["jalen-okoro"]["availability"] == "modified"
    client.patch("/api/sports/teams/rice-mbb/athletes/jalen-okoro/status", json={"status": "available"})


def test_console_never_sees_athletes(client, db):
    ids = [p["id"] for p in client.get("/api/worklist").json()["patients"]]
    assert not any(spec.id in ids for spec in ROSTER)
    athletes = db.scalars(select(Patient.id).where(Patient.account_kind == "sports")).all()
    assert len(athletes) >= 15
