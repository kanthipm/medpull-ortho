"""The seed only runs on the demo stack unless an operator forces it."""

from app.config import settings
from app.seed import seed as seed_module


def test_the_seed_refuses_a_deployment_that_is_not_the_demo(monkeypatch):
    # nobody live, so the only thing standing in the way is the mode
    monkeypatch.setattr(seed_module, "unrebuildable_patient_ids", lambda db: [])

    monkeypatch.setattr(settings, "demo_mode", False)
    refusal = seed_module.refuse_destructive_reseed()
    assert refusal is not None and "not in demo mode" in refusal["error"]
    assert seed_module.refuse_destructive_reseed(force=True) is None

    monkeypatch.setattr(settings, "demo_mode", True)
    assert seed_module.refuse_destructive_reseed() is None


def test_live_patients_are_named_before_the_mode_is(monkeypatch):
    monkeypatch.setattr(seed_module, "unrebuildable_patient_ids", lambda db: ["someone"])
    monkeypatch.setattr(settings, "demo_mode", False)
    refusal = seed_module.refuse_destructive_reseed()
    assert refusal["live_patients"] == ["someone"]
    assert "cannot be rebuilt" in refusal["error"]
