from datetime import date

from sqlalchemy import func, select

from app.models import Observation, Patient
from app.models.enums import MetricType, SourceProvider
from app.seed.generators import generate_patient_observations
from app.seed.patients import full_roster, get_spec
from app.seed.scenarios import get_scenario

GAIT = {MetricType.WALKING_SPEED, MetricType.WALKING_ASYMMETRY_PCT, MetricType.DOUBLE_SUPPORT_PCT}


def test_generator_is_deterministic():
    spec = get_spec("linda")
    today = date.today()
    a = generate_patient_observations(spec, get_scenario("linda"), today)
    b = generate_patient_observations(spec, get_scenario("linda"), today)
    assert len(a) == len(b)
    assert [(o.dedupe_key, o.value_num) for o in a] == [(o.dedupe_key, o.value_num) for o in b]


def test_all_patients_seeded(db):
    # conftest seeds patients.full_roster(): the shipped demo hospital plus
    # the ortho demo roster these fixtures are calibrated against.
    _, seeded = full_roster()
    assert db.scalar(select(func.count(Patient.id))) == len(seeded)


def test_gait_metrics_only_for_apple_patients(db):
    rows = db.execute(
        select(Observation.patient_id, Observation.metric_type).where(
            Observation.metric_type.in_([str(m) for m in GAIT])
        )
    ).all()
    _, seeded = full_roster()
    apple_ids = {p.id for p in seeded if p.provider == SourceProvider.APPLE}
    assert rows, "expected gait observations for apple patients"
    assert {pid for pid, _ in rows} <= apple_ids


def test_priya_has_sparse_coverage(db):
    # The watch is what she forgets to wear; her Withings scale and cuff
    # report on their own schedule, so coverage is judged on the watch's steps.
    spec = get_spec("priya")
    days = db.scalar(
        select(func.count(func.distinct(func.date(Observation.start_time)))).where(
            Observation.patient_id == "priya",
            Observation.metric_type == MetricType.STEPS,
        )
    )
    total_days = 10 + spec.postop_day + 1  # pre-op window + post-op days
    assert days / total_days < 0.6


def test_linda_sleep_depressed_on_latest_day(db):
    rows = db.execute(
        select(Observation.start_time, Observation.value_num)
        .where(
            Observation.patient_id == "linda",
            Observation.metric_type == MetricType.SLEEP_DURATION,
        )
        .order_by(Observation.start_time)
    ).all()
    pre_op = [v for t, v in rows[:10]]
    latest = rows[-1][1]
    baseline = sum(pre_op) / len(pre_op)
    # nominal ramp multiplies sleep to 0.75x; allow for day-level noise in
    # both the baseline window and the latest reading
    assert latest <= baseline * 0.88


def _stage_rows(db, patient_id: str):
    return db.execute(
        select(Observation.value_num, Observation.value_json)
        .where(
            Observation.patient_id == patient_id,
            Observation.metric_type == MetricType.SLEEP_STAGES,
        )
        .order_by(Observation.start_time)
    ).all()


def test_linda_nights_fragment_as_her_sleep_shortens(db):
    """The awake fraction answers the sleep ramp: linda's latest nights carry
    a larger awake share than her early (pre-op) nights, while the stage
    hours still add up to the night's total."""
    rows = _stage_rows(db, "linda")
    fractions = [j["awake"] / total for total, j in rows]
    early = sum(fractions[:10]) / 10
    assert fractions[-1] > early * 1.2
    for total, stages in rows:
        assert abs(sum(stages.values()) - total) < 0.05  # stage hours still add up


def test_aisha_flights_plateau_with_her_recovery(db):
    """aisha's scenario freezes progress at day 8, so her flights climbed
    stop growing: the last week's mean is no higher than the week before."""
    spec = get_spec("aisha")
    rows = db.execute(
        select(Observation.local_date, Observation.value_num)
        .where(
            Observation.patient_id == "aisha",
            Observation.metric_type == MetricType.FLIGHTS_CLIMBED,
        )
        .order_by(Observation.local_date)
    ).all()
    assert rows, "aisha (Apple) should report flights climbed"
    surgery = date.today() - __import__("datetime").timedelta(days=spec.postop_day)
    by_day = {(d - surgery).days: v for d, v in rows}
    last7 = [by_day[d] for d in range(spec.postop_day - 6, spec.postop_day + 1) if d in by_day]
    prior = [by_day[d] for d in range(spec.postop_day - 13, spec.postop_day - 6) if d in by_day]
    assert len(last7) >= 5 and len(prior) >= 3
    assert sum(last7) / len(last7) <= sum(prior) / len(prior) * 1.1
    assert max(by_day.values()) >= 1


def test_seed_extensions_are_additive_and_deterministic():
    """The care-metric rows (pain logs, flights, guided walks, hourly buckets,
    the Withings scale) are appended without changing a single daily-summary
    value the risk tier scores."""
    spec = get_spec("aisha")
    today = date.today()
    obs = generate_patient_observations(spec, get_scenario("aisha"), today)
    kinds = {str(o.metric_type) for o in obs}
    assert {"pain_nrs", "flights_climbed", "exercise_session", "sit_to_stand", "hr_sample"} <= kinds
    hourly = [o for o in obs if str(o.metric_type) == "steps" and o.external_id]
    summaries = {o.local_date: o.value_num for o in obs
                 if str(o.metric_type) == "steps" and not o.external_id}
    by_date: dict = {}
    for o in hourly:
        by_date[o.local_date] = by_date.get(o.local_date, 0) + o.value_num
    for day, total in by_date.items():
        assert abs(total - summaries[day]) < 1.0  # buckets add up to the summary
    again = generate_patient_observations(spec, get_scenario("aisha"), today)
    assert [(o.dedupe_key, o.value_num, o.value_json) for o in obs] == [
        (o.dedupe_key, o.value_num, o.value_json) for o in again
    ]
