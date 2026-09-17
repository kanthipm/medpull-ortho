"""A care metric's `value` is the number alone; its `unit` travels separately.

The console and the app print `value` and then `unit`, so a value that
already ends in its unit reads twice ("12.3% %", "0.32 m/s m/s")."""

from __future__ import annotations

import pytest

ROSTER = ["linda", "robert", "sofia", "aisha", "priya", "grace", "david", "james", "elena", "steve"]


def _metrics(db, patient_id: str) -> list[dict]:
    from app.engine.pipeline import latest_assessment

    return latest_assessment(db, patient_id).analytics["care_metrics"]["metrics"]


@pytest.mark.parametrize("patient_id", ROSTER)
def test_no_value_repeats_its_unit(db, patient_id):
    for metric in _metrics(db, patient_id):
        value, unit = metric.get("value"), (metric.get("unit") or "").strip()
        if value is None or not unit:
            continue
        assert not str(value).strip().endswith(unit), (metric["id"], value, unit)


def test_walking_metrics_carry_a_bare_number(db):
    seen = 0
    for patient_id in ROSTER:
        for metric in _metrics(db, patient_id):
            if metric["id"] in ("M3", "M7") and metric.get("value") is not None:
                float(metric["value"])  # a plain number, no unit glued on
                seen += 1
    assert seen, "no seeded patient computed M3 or M7"
