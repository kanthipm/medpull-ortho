"""The AI task builder: deterministic parsing for ortho and chronic
sentences, coercing validation, suggestions, PHI stripping, and the LLM path
with a faked provider."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.engine.care.pathways import PATHWAYS
from app.llm.insights import BANNED
from app.models.library import TaskTemplate
from app.models.patient import Patient
from app.plan import builder
from app.plan.builder import (
    coerce_draft,
    draft_tasks,
    draft_tasks_fallback,
    pick_template,
    strip_phi,
    suggest_tasks,
)
from app.plan.library import ensure_library, templates_for_pathway
from app.plan.verify_kinds import VerifyKind

SMOKE_TEXT = ("three short walks a day, log hip pain morning and evening, one flight of stairs "
              "by next week, no bending past 90 degrees")


def _by_kind(tasks):
    return {t["verify_kind"]: t for t in tasks}


def test_fallback_parses_ortho_sentences(db):
    ensure_library(db)
    result = draft_tasks(db, SMOKE_TEXT, db.get(Patient, "aisha"))
    assert result["provider"] == "fallback" and result["pathway"] == "ortho_tha"
    kinds = _by_kind(result["tasks"])
    assert set(kinds) == {"walk_bouts", "pain_log", "stairs", "precaution"}
    walks = kinds["walk_bouts"]
    assert walks["params"]["bouts"] == 3 and walks["source_template_key"] == "uc2_early_three_walks"
    pain = kinds["pain_log"]
    assert pain["params"]["times"] == 2 and pain["schedule"] == "am_pm"
    stairs = kinds["stairs"]
    assert stairs["params"]["flights"] == 1 and stairs["schedule"] == "once"
    assert stairs["due_at"] is not None and stairs["source_template_key"] is not None
    precaution = kinds["precaution"]
    assert precaution["title"] == "No bending past 90 degrees"
    assert precaution["task_kind"] == "custom" and precaution["template_key"] is None
    for t in result["tasks"]:
        assert t["rationale"] and t["task_kind"] in ("walk", "checkin", "exercise", "custom")
        assert not BANNED.search(t["title"] + t["why"] + t["rationale"])


def test_fallback_parses_chronic_sentences(db):
    ensure_library(db)
    text = ("weigh yourself every morning; check your oxygen each morning; log blood pressure "
            "twice a day; use the inhaler as prescribed; note fluids and salt; check your feet")
    result = draft_tasks(db, text, None, "copd")
    kinds = _by_kind(result["tasks"])
    assert set(kinds) == {"weight_log", "spo2_check", "bp_log", "inhaler_log", "fluid_note",
                          "foot_check"}
    assert kinds["bp_log"]["params"]["times"] == 2
    assert kinds["spo2_check"]["source_template_key"] == "uc9_morning_spo2"
    assert kinds["inhaler_log"]["task_kind"] == "medication"
    glucose = draft_tasks(db, "log your sugar before breakfast and dinner", None, "diabetes")
    assert glucose["tasks"][0]["verify_kind"] == "glucose_log"
    breath = draft_tasks(db, "rate your breathlessness am and pm", None, "copd")["tasks"][0]
    assert breath["verify_kind"] == "breathlessness_log" and breath["params"]["times"] == 2


def test_fallback_handles_counts_bands_and_unknown_sentences(db):
    ensure_library(db)
    templates = templates_for_pathway(db, None)
    tasks = draft_tasks_fallback(
        "5 walks a day. stay between 3,000 and 5,000 steps. 10 minute walk without stopping. "
        "call the office if the dressing leaks. move every hour",
        templates, PATHWAYS["ortho_tka"], 20, today=date(2026, 9, 14),
    )
    kinds = _by_kind(tasks)
    assert kinds["walk_bouts"]["params"]["bouts"] == 5
    assert kinds["steps_band"]["params"] == {"band_low": 3000, "band_high": 5000, "auto": False}
    assert kinds["continuous_walk"]["params"]["minutes"] == 10
    assert kinds["move_hourly"]["source_template_key"] == "uc2_early_move_hourly"
    custom = kinds["custom"]
    assert custom["title"] == "Call the office if the dressing leaks"
    assert custom["why"] == "Your care team asked for this."


def test_coerce_draft_repairs_rather_than_rejects(db):
    ensure_library(db)
    templates = templates_for_pathway(db, PATHWAYS["ortho_tka"])
    raw = {"tasks": [
        {"template_key": "uc1_early_three_walks", "params": {"bouts": "4", "bogus": 1},
         "schedule": "sometimes", "phase": "never", "title": "x" * 400, "rationale": "r" * 500},
        {"title": "Log pain", "why": "so we can see", "verify_kind": "not_a_kind",
         "task_kind": "nope", "params": {"times": 2.7}},
        {"title": "We detected a clot", "verify_kind": "custom"},
        "not a dict",
    ]}
    tasks = coerce_draft(raw, templates, PATHWAYS["ortho_tka"], 10)
    assert len(tasks) == 2
    first = tasks[0]
    assert first["template_key"] == "uc1_early_three_walks"
    assert first["params"] == {"bouts": 4, "min_minutes": 5}
    assert first["schedule"] == "daily" and first["phase"] == "early"
    assert len(first["title"]) == 90 and len(first["rationale"]) == 200
    second = tasks[1]
    assert second["verify_kind"] == "custom" and second["task_kind"] == "custom"
    assert second["params"] == {} and second["phase"] == "early"
    assert coerce_draft({"nope": []}, templates, PATHWAYS["ortho_tka"], 10) is None
    assert coerce_draft({"tasks": "x"}, templates, PATHWAYS["ortho_tka"], 10) is None
    assert coerce_draft([], templates, PATHWAYS["ortho_tka"], 10) is None


def test_strip_phi_removes_phones_and_emails():
    text = "call me at 512-555-0142 or +1 (512) 555 0199, email aisha.bello@example.com"
    clean = strip_phi(text)
    assert "555" not in clean and "@" not in clean
    assert clean.count("[phone]") == 2 and "[email]" in clean
    assert strip_phi("three walks a day, 5 sit-to-stands") == "three walks a day, 5 sit-to-stands"


def test_llm_path_reports_provider_and_strikes_only_on_contract_failure(db, monkeypatch):
    ensure_library(db)
    strikes: list[str] = []
    valid: list[str] = []
    monkeypatch.setattr(builder, "provider_name", lambda: "groq")
    monkeypatch.setattr(builder, "note_invalid_output", lambda p: strikes.append(p))
    monkeypatch.setattr(builder, "note_valid_output", lambda p: valid.append(p))
    seen: dict = {}

    def fake_complete(system, user, **kwargs):
        seen["user"] = user
        return {"tasks": [{"template_key": "uc2_mid_step_band", "rationale": "keeps load even"}]}

    monkeypatch.setattr(builder, "complete_json", fake_complete)
    result = draft_tasks(db, "keep her steps even; phone 512-555-0142", db.get(Patient, "aisha"))
    assert result["provider"] == "groq" and valid == ["groq"] and strikes == []
    assert result["tasks"][0]["template_key"] == "uc2_mid_step_band"
    assert "555-0142" not in seen["user"] and "Aisha Bello" not in seen["user"]
    assert '"patient_first_name": "Aisha"' in seen["user"]

    monkeypatch.setattr(builder, "complete_json", lambda *a, **k: {"garbage": True})
    result = draft_tasks(db, "three walks a day", db.get(Patient, "aisha"))
    assert result["provider"] == "fallback" and strikes == ["groq"]
    assert result["tasks"][0]["verify_kind"] == "walk_bouts"

    monkeypatch.setattr(builder, "complete_json", lambda *a, **k: {"tasks": [
        {"title": "We detected trouble", "verify_kind": "custom"}]})
    result = draft_tasks(db, "three walks a day", db.get(Patient, "aisha"))
    assert result["provider"] == "fallback" and strikes == ["groq"]  # no second strike


def test_pick_template_prefers_the_pathway_then_schedule(db):
    ensure_library(db)
    templates = templates_for_pathway(db, None)
    tha = PATHWAYS["ortho_tha"]
    assert pick_template(templates, tha, VerifyKind.PAIN_LOG).key == "uc2_pain_precaution"
    assert pick_template(templates, tha, VerifyKind.PAIN_LOG, schedule="am_pm").key == \
        "uc7_pain_am_pm"
    assert pick_template(templates, tha, VerifyKind.STAIRS) is None
    assert pick_template(templates, tha, VerifyKind.STAIRS, any_pathway=True).key == \
        "uc1_mid_one_flight"
    hf = PATHWAYS["heart_failure"]
    assert pick_template(templates, hf, VerifyKind.STEPS_BAND).key == "uc8_activity_band"


def test_suggest_returns_three_to_five_library_keys(db):
    ensure_library(db)
    from app.plan.service import active_template_keys

    for patient_id in ("aisha", "robert", "grace", "priya"):
        result = suggest_tasks(db, db.get(Patient, patient_id))
        tasks = result["tasks"]
        assert 3 <= len(tasks) <= 5, patient_id
        keys = [t["template_key"] for t in tasks]
        assert len(set(keys)) == len(keys)
        library_keys = set(db.scalars(select(TaskTemplate.key)).all())
        assert set(keys) <= library_keys
        assert not set(keys) & active_template_keys(db, patient_id)
        assert all(t["rationale"] for t in tasks)
        assert result["provider"] == "fallback"


def test_builder_api(client):
    assert client.post("/api/task-builder/draft",
                       json={"text": "walk", "pathway": "nope"}).status_code == 400
    assert client.post("/api/task-builder/draft",
                       json={"text": "walk", "patient_id": "nobody"}).status_code == 404
    body = client.post("/api/task-builder/draft", json={"text": SMOKE_TEXT, "patient_id": "aisha"})
    assert body.status_code == 200
    assert len(body.json()["tasks"]) == 4 and body.json()["provider"] == "fallback"
    suggested = client.post("/api/patients/aisha/plan/suggest").json()
    assert 3 <= len(suggested["tasks"]) <= 5
    assert client.post("/api/patients/nobody/plan/suggest").status_code == 404
