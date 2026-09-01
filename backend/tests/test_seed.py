from datetime import date

from sqlalchemy import func, select

from app.models import Observation, Patient
from app.models.enums import MetricType, SourceProvider
from app.seed.generators import generate_patient_observations
from app.seed.patients import PATIENTS, get_spec
from app.seed.scenarios import get_scenario

GAIT = {MetricType.WALKING_SPEED, MetricType.WALKING_ASYMMETRY_PCT, MetricType.DOUBLE_SUPPORT_PCT}


def test_generator_is_deterministic():
    spec = get_spec("marcus")
    today = date.today()
    a = generate_patient_observations(spec, get_scenario("marcus"), today)
    b = generate_patient_observations(spec, get_scenario("marcus"), today)
    assert len(a) == len(b)
    assert [(o.dedupe_key, o.value_num) for o in a] == [(o.dedupe_key, o.value_num) for o in b]


def test_all_patients_seeded(db):
    assert db.scalar(select(func.count(Patient.id))) == len(PATIENTS)


def test_gait_metrics_only_for_apple_patients(db):
    rows = db.execute(
        select(Observation.patient_id, Observation.metric_type).where(
            Observation.metric_type.in_([str(m) for m in GAIT])
        )
    ).all()
    apple_ids = {p.id for p in PATIENTS if p.provider == SourceProvider.APPLE}
    assert rows, "expected gait observations for apple patients"
    assert {pid for pid, _ in rows} <= apple_ids


def test_priya_has_sparse_coverage(db):
    spec = get_spec("priya")
    days = db.scalar(
        select(func.count(func.distinct(func.date(Observation.start_time)))).where(
            Observation.patient_id == "priya"
        )
    )
    total_days = 10 + spec.postop_day + 1  # pre-op window + post-op days
    assert days / total_days < 0.6


def test_marcus_resting_hr_elevated_on_latest_day(db):
    rows = db.execute(
        select(Observation.start_time, Observation.value_num)
        .where(
            Observation.patient_id == "marcus",
            Observation.metric_type == MetricType.RESTING_HR,
        )
        .order_by(Observation.start_time)
    ).all()
    pre_op = [v for t, v in rows[:10]]
    latest = rows[-1][1]
    baseline = sum(pre_op) / len(pre_op)
    # nominal ramp is +8 bpm; allow for day-level noise in both the baseline
    # window and the latest reading
    assert latest >= baseline + 4.5
