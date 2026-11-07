"""The home exercise program: the standard catalog seed, the library routes,
custom exercises and their clinic privacy, and the feature flag."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.hep.catalog import CATALOG, FIRST_ANIMATIONS, ensure_catalog
from app.hep.models import BODY_REGIONS, CATEGORIES, AuditEvent, Exercise
from app.llm.insights import BANNED

_LEDGER_MODELS = (AuditEvent, Exercise)


@pytest.fixture(scope="module")
def catalog(seeded_db):
    ensure_catalog(seeded_db)
    return seeded_db


@pytest.fixture()
def ledger(db):
    marks = {model: (db.scalar(select(func.max(model.id))) or 0) for model in _LEDGER_MODELS}
    yield
    db.expire_all()
    for model, mark in marks.items():
        for row in db.scalars(select(model).where(model.id > mark)).all():
            db.delete(row)
    db.commit()


def _standard(db):
    return db.scalars(select(Exercise).where(Exercise.key.is_not(None))).all()


# --- the catalog -----------------------------------------------------------------------


def test_catalog_is_seeded_complete_and_patient_safe(catalog):
    rows = _standard(catalog)
    keys = [e.key for e in rows]
    assert len(rows) == 30 and len(set(keys)) == 30
    assert {e.key for e in CATALOG} == set(keys)
    assert len(FIRST_ANIMATIONS) == 10 and FIRST_ANIMATIONS[0] == "knee_heel_slides"
    for e in rows:
        assert e.origin == "standard" and e.hospital_id is None
        assert e.status == "draft" and e.media_id is None  # nothing ships approved
        assert e.body_region in BODY_REGIONS and e.category in CATEGORIES
        assert e.instructions and len(e.instructions.splitlines()) >= 2, e.key
        assert e.synonyms, e.key
        for text in (e.title, e.instructions, e.precautions):
            assert not BANNED.search(text), e.key
        # no dose anywhere in the library: sets, reps and holds are the clinician's
        assert not re.search(r"\b\d+\s*(reps?|sets?|seconds?|times)\b", e.instructions, re.I), e.key
    regions = {e.body_region for e in rows}
    assert {"knee", "hip", "ankle", "shoulder", "back_core", "full_body"} == regions
    assert {e.category for e in rows} == set(CATEGORIES)


def test_ensure_catalog_is_idempotent_and_keeps_the_clinics_state(catalog):
    assert ensure_catalog(catalog) == 0
    e = catalog.scalar(select(Exercise).where(Exercise.key == "knee_quad_sets"))
    original = (e.status, e.usage_count, e.title, e.version)
    e.status, e.usage_count, e.title = "approved", 4, "changed by hand"
    catalog.commit()
    assert ensure_catalog(catalog) == 0
    catalog.expire_all()
    e = catalog.scalar(select(Exercise).where(Exercise.key == "knee_quad_sets"))
    assert (e.status, e.usage_count) == ("approved", 4)
    assert e.title == original[2]  # wording follows the code
    assert e.version == original[3] + 1  # and the version records that it moved
    e.status, e.usage_count = original[0], original[1]
    catalog.commit()


# --- the library routes --------------------------------------------------------------


def test_library_lists_searches_and_filters(client, catalog):
    body = client.get("/api/hep/exercises").json()
    assert body["clinic"]["id"] == "hosp_demo"
    assert len(body["exercises"]) == 30
    assert {r["key"] for r in body["regions"]} == set(BODY_REGIONS)
    assert {c["key"] for c in body["categories"]} == set(CATEGORIES)
    first = body["exercises"][0]
    assert {"id", "key", "origin", "title", "synonyms", "body_region", "body_region_label",
            "category", "steps", "instructions", "equipment", "precautions", "status",
            "version", "media"} <= set(first)
    assert first["media"] is None

    by_synonym = client.get("/api/hep/exercises?q=slr").json()["exercises"]
    assert [e["key"] for e in by_synonym] == ["knee_straight_leg_raises"]
    bridges = client.get("/api/hep/exercises?q=bridge").json()["exercises"]
    assert "hip_glute_bridges" in {e["key"] for e in bridges}
    knee = client.get("/api/hep/exercises?region=knee").json()["exercises"]
    assert len(knee) == 6 and all(e["body_region"] == "knee" for e in knee)
    balance = client.get("/api/hep/exercises?category=balance").json()["exercises"]
    assert len(balance) == 3 and all(e["category"] == "balance" for e in balance)
    both = client.get("/api/hep/exercises?region=hip&category=strengthening").json()["exercises"]
    assert len(both) == 5
    assert client.get("/api/hep/exercises?q=zzzz").json()["exercises"] == []
    assert client.get("/api/hep/exercises?region=elbow").status_code == 400
    assert client.get("/api/hep/exercises?category=cardio").status_code == 400
    assert client.get("/api/hep/exercises?origin=ai").status_code == 400
    assert client.get("/api/hep/exercises/999999").status_code == 404
    one = client.get(f"/api/hep/exercises/{first['id']}").json()
    assert one["id"] == first["id"]


def test_custom_exercise_crud_and_archive(client, catalog, ledger):
    created = client.post("/api/hep/exercises/custom", json={
        "title": "  Seated   marching ", "body_region": "hip", "category": "functional",
        "instructions": "Sit tall.\n\n  Lift one knee, then the other.  \n",
        "synonyms": ["seated march", "Seated March", "high knees seated"],
        "equipment": "A chair", "precautions": "Hold the seat if needed.", "actor": "ct_pt",
    })
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["origin"] == "custom" and body["key"] is None and body["clinic_id"] == "hosp_demo"
    assert body["title"] == "Seated marching"
    assert body["steps"] == ["Sit tall.", "Lift one knee, then the other."]
    assert body["synonyms"] == ["seated march", "high knees seated"]
    assert body["status"] == "draft" and body["version"] == 1 and body["created_by"] == "ct_pt"
    eid = body["id"]

    listed = client.get("/api/hep/exercises?origin=custom").json()["exercises"]
    assert [e["id"] for e in listed] == [eid]
    assert eid in {e["id"] for e in client.get("/api/hep/exercises?q=march").json()["exercises"]}
    assert eid in {e["id"] for e in client.get("/api/hep/exercises").json()["exercises"]}

    patched = client.patch(f"/api/hep/exercises/{eid}", json={
        "title": "Seated marching, slow", "status": "approved"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "Seated marching, slow"
    assert patched.json()["status"] == "approved" and patched.json()["version"] == 2
    # a status-only patch does not bump the version
    assert client.patch(f"/api/hep/exercises/{eid}", json={"status": "review"}).json()["version"] == 2

    archived = client.patch(f"/api/hep/exercises/{eid}", json={"status": "archived"}).json()
    assert archived["status"] == "archived"
    assert eid not in {e["id"] for e in client.get("/api/hep/exercises").json()["exercises"]}
    assert eid in {e["id"] for e in client.get(
        "/api/hep/exercises?include_archived=true").json()["exercises"]}
    restored = client.patch(f"/api/hep/exercises/{eid}", json={"status": "draft"}).json()
    assert restored["status"] == "draft"

    events = catalog.scalars(select(AuditEvent).where(
        AuditEvent.subject_type == "exercise", AuditEvent.subject_id == str(eid))).all()
    assert [a.action for a in events][:2] == ["exercise.create", "exercise.update"]
    assert events[0].actor == "ct_pt" and events[0].hospital_id == "hosp_demo"


def test_library_rejects_bad_custom_exercises(client, catalog, ledger):
    post = lambda **kw: client.post("/api/hep/exercises/custom", json={  # noqa: E731
        "title": "Seated marching", "body_region": "hip", "category": "functional", **kw})
    assert post(title="ab").status_code == 422
    assert post(body_region="elbow").status_code == 422
    assert post(category="cardio").status_code == 422
    assert post(instructions="We detected weakness").status_code == 422
    assert post(precautions="Stop if we diagnose pain").status_code == 422
    assert client.patch("/api/hep/exercises/999999", json={"status": "draft"}).status_code == 404


def test_standard_exercises_are_read_only_and_never_archived(client, catalog):
    e = catalog.scalar(select(Exercise).where(Exercise.key == "knee_heel_slides"))
    assert client.patch(f"/api/hep/exercises/{e.id}", json={"title": "Mine now"}).status_code == 422
    assert client.patch(f"/api/hep/exercises/{e.id}",
                        json={"instructions": "x"}).status_code == 422
    assert client.patch(f"/api/hep/exercises/{e.id}", json={"status": "archived"}).status_code == 422
    # review state does move: that is how a PT signs the wording off
    ok = client.patch(f"/api/hep/exercises/{e.id}", json={"status": "approved"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    client.patch(f"/api/hep/exercises/{e.id}", json={"status": "draft"})
    catalog.expire_all()
    assert catalog.get(Exercise, e.id).status == "draft"


def test_custom_exercises_stay_inside_their_clinic(client, catalog, ledger, monkeypatch):
    mine = client.post("/api/hep/exercises/custom", json={
        "title": "Towel scrunches", "body_region": "ankle", "category": "strengthening"}).json()
    assert mine["clinic_id"] == "hosp_demo"
    monkeypatch.setattr(settings, "hep_clinic_id", "hosp_medpull")
    theirs = client.get("/api/hep/exercises").json()
    assert theirs["clinic"]["id"] == "hosp_medpull"
    assert len(theirs["exercises"]) == 30  # the standard set, nothing of hosp_demo's
    assert mine["id"] not in {e["id"] for e in theirs["exercises"]}
    assert client.get(f"/api/hep/exercises/{mine['id']}").status_code == 404
    assert client.patch(f"/api/hep/exercises/{mine['id']}",
                        json={"status": "archived"}).status_code == 404
    monkeypatch.setattr(settings, "hep_clinic_id", "hosp_nowhere")
    assert client.get("/api/hep/exercises").status_code == 503


def test_a_hospital_credential_has_its_own_library_and_plans(client, catalog, ledger, db, monkeypatch):
    """Behind a locked console a hospital credential acts for its own hospital
    whatever HEP_CLINIC_ID says, the staff token for the configured clinic,
    and a team credential has no clinic to act for (app/api/scope.py's lines)."""
    from app.console_credentials import mint
    from app.models.sports import SportsOrg

    monkeypatch.setattr(settings, "console_access_token", "open-sesame")
    # the suite seeds no sports program; one bare org is enough for a credential
    org = SportsOrg(id="hep-test-org", name="HEP Test Athletics", short_name="HEP", kind="club",
                    city="Tomball", state="TX", timezone="America/Chicago")
    db.add(org)
    db.commit()
    minted = [mint(db, "hospital", "hosp_medpull", "Medpull clinic"),
              mint(db, "sports_org", "hep-test-org", "Athletics")]
    hosp = {"Authorization": f"Bearer {minted[0][1]}"}
    team = {"Authorization": f"Bearer {minted[1][1]}"}
    staff = {"Authorization": "Bearer open-sesame"}
    try:
        assert client.get("/api/hep/exercises").status_code == 401
        mine = client.post("/api/hep/exercises/custom", headers=hosp, json={
            "title": "Towel scrunches", "body_region": "ankle", "category": "strengthening"})
        assert mine.status_code == 200, mine.text
        assert mine.json()["clinic_id"] == "hosp_medpull"
        assert client.get("/api/hep/exercises", headers=hosp).json()["clinic"]["id"] == "hosp_medpull"
        # the staff console acts for the configured clinic and never sees the other's custom rows
        monkeypatch.setattr(settings, "hep_clinic_id", "hosp_demo")
        theirs = client.get("/api/hep/exercises", headers=staff).json()
        assert theirs["clinic"]["id"] == "hosp_demo"
        assert mine.json()["id"] not in {e["id"] for e in theirs["exercises"]}
        assert client.get(f"/api/hep/exercises/{mine.json()['id']}", headers=staff).status_code == 404
        # HEP_CLINIC_ID does not redirect a hospital credential
        assert client.get("/api/hep/exercises", headers=hosp).json()["clinic"]["id"] == "hosp_medpull"
        # a sports credential has no clinic
        assert client.get("/api/hep/exercises", headers=team).status_code == 403
        assert client.get("/api/hep/plans", headers=team).status_code == 403
    finally:
        for row, _token in minted:
            db.delete(row)
        db.delete(org)
        db.commit()


def test_feature_flag_hides_the_routes(client, catalog, monkeypatch):
    assert client.get("/api/health").json()["hep"] is True
    monkeypatch.setattr(settings, "hep_enabled", False)
    assert client.get("/api/health").json()["hep"] is False
    assert client.get("/api/hep/exercises").status_code == 404
    assert client.post("/api/hep/exercises/custom", json={
        "title": "Anything", "body_region": "hip", "category": "mobility"}).status_code == 404


# --- plans ------------------------------------------------------------------------------


@pytest.fixture()
def plan_ledger(db):
    from app.hep.models import ExercisePlan, PlanExercise

    models = (PlanExercise, ExercisePlan, AuditEvent, Exercise)
    marks = {m: (db.scalar(select(func.max(m.id))) or 0) for m in models}
    yield
    db.expire_all()
    for m, mark in marks.items():
        for row in db.scalars(select(m).where(m.id > mark)).all():
            db.delete(row)
    db.commit()


def _ex(client, key):
    return next(e for e in client.get("/api/hep/exercises").json()["exercises"] if e["key"] == key)


def test_plan_draft_update_publish_and_snapshot(client, catalog, plan_ledger):
    heel, quads = _ex(client, "knee_heel_slides"), _ex(client, "knee_quad_sets")
    used_before = quads["usage_count"]
    created = client.post("/api/hep/plans", json={
        "patient_id": "steve", "title": "  Week one  knee ", "notes": "Go gently.",
        "assigned_by": "ct_alvarez", "actor": "ct_alvarez",
        "items": [
            {"exercise_id": heel["id"], "sets": 3, "reps": 10, "frequency": "twice_daily",
             "side": "left", "clinician_instructions": "Slow on the way down."},
            {"exercise_id": quads["id"], "sets": 2, "hold_seconds": 5},
        ],
    })
    assert created.status_code == 200, created.text
    plan = created.json()
    assert plan["status"] == "draft" and plan["version"] == 1 and plan["title"] == "Week one knee"
    assert plan["patient"] == {"id": "steve", "name": "Steve"}
    assert [i["title"] for i in plan["items"]] == ["Heel Slides", "Quad Sets"]
    assert plan["items"][0]["dose"] == "3 sets × 10 reps · Twice a day · Left"
    assert plan["items"][1]["dose"] == "2 sets · hold 5 s · Once a day"
    assert all(i["snapshotted"] is False for i in plan["items"])
    pid = plan["id"]

    stale = client.put(f"/api/hep/plans/{pid}", json={"version": 99, "title": "x"})
    assert stale.status_code == 409
    reordered = client.put(f"/api/hep/plans/{pid}", json={
        "version": 1,
        "items": [{"exercise_id": quads["id"], "reps": 12},
                  {"exercise_id": heel["id"], "sets": 3, "reps": 10, "frequency": "daily"}],
    })
    assert reordered.status_code == 200, reordered.text
    assert reordered.json()["version"] == 2
    assert [i["title"] for i in reordered.json()["items"]] == ["Quad Sets", "Heel Slides"]
    assert reordered.json()["items"][0]["dose"] == "12 reps · Once a day"

    listed = client.get("/api/hep/plans?status=draft").json()["plans"]
    assert pid in {p["id"] for p in listed}
    assert listed[0]["items"] is None and listed[0]["exercise_count"] == 2

    assert client.post(f"/api/hep/plans/{pid}/publish", json={"version": 1}).status_code == 409
    published = client.post(f"/api/hep/plans/{pid}/publish",
                            json={"version": 2, "actor": "ct_alvarez"})
    assert published.status_code == 200, published.text
    body = published.json()
    assert body["plan"]["status"] == "active" and body["plan"]["published_at"]
    assert body["invitation"]["status"] == "not_needed"
    assert body["delivery"]["channel"] == "app" and "patient_has_app" in body["delivery"]
    assert all(i["snapshotted"] for i in body["plan"]["items"])
    quads_now = client.get(f"/api/hep/exercises/{quads['id']}").json()
    assert quads_now["usage_count"] == used_before + 1
    assert client.post(f"/api/hep/plans/{pid}/publish", json={"version": 3}).status_code == 422

    # a library edit never rewrites a published prescription
    catalog.expire_all()
    row = catalog.get(Exercise, quads["id"])
    row.title, row.version = "Quad Sets (renamed)", row.version + 1
    catalog.commit()
    live = client.get(f"/api/hep/plans/{pid}").json()
    item = next(i for i in live["items"] if i["exercise_id"] == quads["id"])
    assert item["title"] == "Quad Sets" and item["library_changed"] is True
    assert item["library_current"]["title"] == "Quad Sets (renamed)"
    row.title, row.version = "Quad Sets", row.version - 1
    catalog.commit()

    mine = client.get("/api/hep/patients/steve/plans").json()
    assert mine["active"]["id"] == pid and mine["drafts"] == []

    # a second publish for the same patient supersedes the first
    second = client.post("/api/hep/plans", json={
        "patient_id": "steve", "items": [{"exercise_id": heel["id"], "reps": 8}]}).json()
    out = client.post(f"/api/hep/plans/{second['id']}/publish", json={"version": 1}).json()
    assert out["superseded"] == [pid]
    assert client.get(f"/api/hep/plans/{pid}").json()["status"] == "superseded"
    mine = client.get("/api/hep/patients/steve/plans").json()
    assert mine["active"]["id"] == second["id"]
    assert [p["id"] for p in mine["history"]] == [pid]

    # a published plan can be revised (re-snapshotted) but not moved or emptied
    revised = client.put(f"/api/hep/plans/{second['id']}", json={
        "version": 2, "items": [{"exercise_id": heel["id"], "reps": 8},
                                {"exercise_id": quads["id"], "sets": 1}]})
    assert revised.status_code == 200 and len(revised.json()["items"]) == 2
    assert all(i["snapshotted"] for i in revised.json()["items"])
    assert client.put(f"/api/hep/plans/{second['id']}", json={
        "version": 3, "patient_id": "guest"}).status_code == 422
    assert client.put(f"/api/hep/plans/{second['id']}", json={
        "version": 3, "items": []}).status_code == 422

    archived = client.post(f"/api/hep/plans/{second['id']}/archive").json()
    assert archived["status"] == "archived"
    assert client.get("/api/hep/patients/steve/plans").json()["active"] is None
    closed = client.put(f"/api/hep/plans/{second['id']}", json={"version": 5, "title": "x"})
    assert closed.status_code == 422

    events = catalog.scalars(select(AuditEvent).where(
        AuditEvent.subject_type == "plan", AuditEvent.subject_id == str(pid))).all()
    assert [a.action for a in events] == ["plan.create", "plan.update", "plan.publish"]
    assert events[2].actor == "ct_alvarez"


def test_plan_rejects_bad_input(client, catalog, plan_ledger):
    heel = _ex(client, "knee_heel_slides")

    def post(**kw):
        return client.post("/api/hep/plans", json={"patient_id": "steve", **kw})

    assert post(items=[{"exercise_id": heel["id"]}, {"exercise_id": heel["id"]}]).status_code == 422
    assert post(items=[{"exercise_id": 999999}]).status_code == 422
    assert post(items=[{"exercise_id": heel["id"], "frequency": "hourly"}]).status_code == 422
    assert post(items=[{"exercise_id": heel["id"], "side": "up"}]).status_code == 422
    assert post(items=[{"exercise_id": heel["id"], "sets": 1000}]).status_code == 422
    assert post(items=[{"exercise_id": heel["id"],
                        "clinician_instructions": "We detected weakness"}]).status_code == 422
    # a patient of another hospital is unknown to this clinic
    assert client.post("/api/hep/plans", json={"patient_id": "linda", "items": []}).status_code == 422
    # an archived custom exercise cannot be added
    custom = client.post("/api/hep/exercises/custom", json={
        "title": "Towel scrunches", "body_region": "ankle", "category": "strengthening"}).json()
    client.patch(f"/api/hep/exercises/{custom['id']}", json={"status": "archived"})
    assert post(items=[{"exercise_id": custom["id"]}]).status_code == 422
    # publishing needs a patient and at least one exercise
    empty = post(items=[]).json()
    assert client.post(f"/api/hep/plans/{empty['id']}/publish", json={"version": 1}).status_code == 422
    nobody = client.post("/api/hep/plans", json={"items": [{"exercise_id": heel["id"]}]}).json()
    assert nobody["patient"] is None
    assert client.post(f"/api/hep/plans/{nobody['id']}/publish", json={"version": 1}).status_code == 422
    assert client.get("/api/hep/plans/999999").status_code == 404
    assert client.get("/api/hep/plans?status=nope").status_code == 400
    assert client.get("/api/hep/patients/linda/plans").status_code == 404


def test_plan_options_list_the_clinics_patients(client, catalog):
    body = client.get("/api/hep/options").json()
    assert {f["key"] for f in body["frequencies"]} >= {"daily", "twice_daily", "weekly"}
    assert {s["key"] for s in body["sides"]} == {"left", "right", "both", "not_applicable"}
    ids = {p["id"] for p in body["patients"]}
    assert "steve" in ids and "linda" not in ids
    assert body["care_team"] and body["max_items"] == 20
    assert {r["key"] for r in body["regions"]} == set(BODY_REGIONS)
