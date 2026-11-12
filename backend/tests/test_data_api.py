"""The console's Data tab (app/api/data.py, app/dataviews).

Every route is a read: none commits, each respects the console's scope, and
a chart it opens is always a clinic chart. The numbers are checked against
what the engine itself builds, not against themselves.
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

import pytest
from sqlalchemy import event, func, select

from app.console_credentials import mint
from app.database import SessionLocal
from app.dataviews.reported import answers_from_pairs
from app.engine.dataload import load_daily_series, source_rank
from app.models.enums import MetricType as M
from app.models.observation import Observation
from app.models.patient import Patient
from app.tasks.service import QUESTION_SETS, transcript

ACTING = "X-MedPull-Clinic"
METHODIST = {"linda", "aisha", "elena"}
HIRT = {"hirt-cole", "hirt-tessa", "hirt-devon", "hirt-june", "hirt-rafael"}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def tokens(seeded_db):
    """A credential for each of two clinics, and one for a team: a console
    that has no clinic roster at all. The team is a throwaway row."""
    from app.models.sports import SportsOrg, SportsTeam

    org = SportsOrg(id="data-test-org", name="Data Test Athletics", short_name="Data Test",
                    kind="college", city="Houston", state="TX")
    team = SportsTeam(id="data-test-team", org_id=org.id, name="Track", sport="track")
    seeded_db.add(org)
    seeded_db.flush()
    seeded_db.add(team)
    seeded_db.commit()
    minted = {
        "methodist": mint(seeded_db, "hospital", "hosp_methodist", "Methodist console"),
        "hirt": mint(seeded_db, "hospital", "hirt", "HIRT console"),
        "mbb": mint(seeded_db, "team", team.id, "Track staff"),
    }
    yield {name: token for name, (_row, token) in minted.items()}
    for row, _token in minted.values():
        seeded_db.delete(row)
    seeded_db.delete(team)
    seeded_db.flush()
    seeded_db.delete(org)
    seeded_db.commit()


@pytest.fixture()
def commits():
    """Counts commits made through the app's sessionmaker, the hook the AWS
    storage layer uses to decide a request changed the database."""
    seen: list[int] = []

    def note(_session) -> None:
        seen.append(1)

    event.listen(SessionLocal, "after_commit", note)
    yield seen
    event.remove(SessionLocal, "after_commit", note)


# --- the dictionary -----------------------------------------------------------------


def test_the_catalog_names_every_metric_with_its_family_unit_and_tier(client, commits):
    res = client.get("/api/data/catalog")
    assert res.status_code == 200 and "max-age" in res.headers["cache-control"]
    body = res.json()
    keys = {m["key"] for m in body["metrics"]}
    assert keys == {str(m) for m in M}  # the whole vocabulary, nothing invented
    tiers = {t["key"] for t in body["tiers"]}
    families = {f["key"] for f in body["families"]}
    for metric in body["metrics"]:
        assert metric["label"] and metric["tier"] in tiers and metric["family"] in families
        assert metric["aggregation"] in ("mean", "additive")
    # what MedPull computes itself says how
    by_key = {m["key"]: m for m in body["metrics"]}
    assert by_key["step_length"]["tier"] == "display" and by_key["step_length"]["method"]
    assert by_key["resting_hr"]["tier"] == "scored"
    assert by_key["stress_index"]["computed"] is True
    # sources in precedence order, MedPull's own measurement first
    ranks = [s["rank"] for s in body["sources"]]
    assert ranks == sorted(ranks) and body["sources"][0]["key"] == "medpull"
    assert {m["id"] for m in body["care_metrics"]} >= {"M1", "M9", "M18", "C1", "C6"}
    assert commits == []


# --- the roster ---------------------------------------------------------------------


def test_coverage_lists_the_clinic_roster_by_family(client, db, commits):
    res = client.get("/api/data/coverage?days=30")
    assert res.status_code == 200
    body = res.json()
    ids = {p["id"] for p in body["patients"]}
    assert METHODIST <= ids and HIRT <= ids
    assert body["days"] == 30 and body["as_of"] == date.today().isoformat()
    families = [f["key"] for f in body["families"]]
    assert families[:3] == ["sleep", "cardiac", "activity"] and "exercise_sessions" in families

    linda = next(p for p in body["patients"] if p["id"] == "linda")
    assert set(linda["cells"]) == set(families)
    since = date.today() - timedelta(days=29)
    stored_days = db.scalar(
        select(func.count(func.distinct(Observation.local_date))).where(
            Observation.patient_id == "linda", Observation.deleted_at.is_(None),
            Observation.metric_type == str(M.SLEEP_DURATION), Observation.local_date >= since,
            Observation.local_date <= date.today(),
        )
    )
    assert linda["cells"]["sleep"]["days"] == stored_days > 0
    assert linda["device"] and linda["risk_level"] and linda["confidence"]["level"]

    # a lifter is followed by check-in: no device, training load and sessions instead
    cole = next(p for p in body["patients"] if p["id"] == "hirt-cole")
    assert cole["device"] is None and cole["cells"]["sleep"]["days"] == 0
    assert cole["cells"]["training_load"]["days"] > 0
    assert cole["cells"]["exercise_sessions"]["days"] > 0
    assert cole["checkins"]["count"] > 0 and cole["exercises"]["done"] > 0
    assert commits == []


def test_coverage_follows_the_scope_and_the_acting_clinic(client, tokens):
    own = client.get("/api/data/coverage", headers=_auth(tokens["methodist"])).json()
    assert {p["id"] for p in own["patients"]} == METHODIST
    acting = client.get("/api/data/coverage", headers={ACTING: "hirt"}).json()
    assert {p["id"] for p in acting["patients"]} == HIRT
    # a team credential has no clinic roster
    assert client.get("/api/data/coverage", headers=_auth(tokens["mbb"])).json()["patients"] == []
    assert client.get("/api/data/coverage?days=0").status_code == 422


# --- one chart ----------------------------------------------------------------------


def test_summary_reads_the_stored_assessment_without_recomputing(client, commits):
    res = client.get("/api/patients/linda/data/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["patient"]["id"] == "linda" and body["devices"]
    sleep = next(m for m in body["metrics"] if m["metric_type"] == "sleep_duration")
    assert sleep["count"] > 0 and sleep["sources"] and sleep["first"] <= sleep["last"]
    assert len(body["calendar"]["by_day"]) == body["calendar"]["days"] == 60
    assessment = body["assessment"]
    assert assessment["risk"]["level"] in ("high", "medium", "low", "missing_data")
    assert isinstance(assessment["risk"]["reasons"], list)
    assert commits == []

    # a lifter's chart carries the reported block instead of device signals
    lifter = client.get("/api/patients/hirt-cole/data/summary").json()
    assert lifter["devices"] == [] and lifter["reported"] is not None
    assert lifter["assessment"]["risk"]["level"] == "high"


def test_readings_page_newest_first_without_skips_or_repeats(client, db, commits):
    total = db.scalar(select(func.count(Observation.id)).where(
        Observation.patient_id == "aisha", Observation.deleted_at.is_(None)))
    seen: list[int] = []
    cursor = None
    pages = 0
    while True:
        url = "/api/patients/aisha/observations/browse?limit=200"
        if cursor:
            url += f"&cursor={cursor}"
        body = client.get(url).json()
        assert body["total"] == total
        stamps = [(r["start_time"], r["id"]) for r in body["rows"]]
        assert stamps == sorted(stamps, reverse=True)
        seen += [r["id"] for r in body["rows"]]
        cursor = body["next_cursor"]
        pages += 1
        if not cursor:
            break
    # many readings share a start time (the hourly samples): every row once
    assert len(seen) == len(set(seen)) == total and pages > 1
    assert "raw_payload" not in body["rows"][0]
    assert commits == []


def test_readings_filter_and_mark_the_rows_the_series_uses(client, db):
    body = client.get(
        "/api/patients/aisha/observations/browse?family=mobility&limit=200").json()
    assert body["rows"] and {r["metric_type"] for r in body["rows"]} <= {
        "walking_speed", "step_length", "cadence", "double_support_pct", "walking_asymmetry_pct",
        "walking_steadiness", "stair_speed_up", "stair_speed_down", "six_min_walk",
        "rom_flexion", "rom_extension", "rom_abduction", "range_of_motion"}
    assert {f["key"] for f in body["facets"]["source"]} >= {"medpull"}
    # a row is "used" exactly when its source is the best-ranked for that metric and day
    best: dict[tuple[str, str], int] = {}
    for metric_type, day, provider in db.execute(
        select(Observation.metric_type, Observation.local_date, Observation.source_provider)
        .where(Observation.patient_id == "aisha", Observation.deleted_at.is_(None),
               Observation.value_num.is_not(None))
    ).all():
        key = (str(metric_type), day.isoformat())
        best[key] = min(best.get(key, 99), source_rank(str(provider)))
    for row in body["rows"]:
        wins = source_rank(row["source"]) == best[(row["metric_type"], row["local_date"])]
        if row["value"] is None:
            assert row["used_in_series"] is False
        elif row["granularity"] != "daily_summary" and row["metric_type"] in ("steps",):
            continue  # an additive metric's parts yield to a summary: covered below
        else:
            assert row["used_in_series"] is wins, row

    one = client.get(
        "/api/patients/aisha/observations/browse?metric_type=resting_hr&source=apple").json()
    assert one["rows"] and {r["metric_type"] for r in one["rows"]} == {"resting_hr"}
    assert client.get("/api/patients/aisha/observations/browse?metric_type=nope").status_code == 422
    assert client.get("/api/patients/aisha/observations/browse?cursor=zzz").status_code == 422
    assert client.get(
        "/api/patients/aisha/observations/browse?from=2026-02-01&to=2026-01-01").status_code == 422


def test_the_daily_series_is_the_engines_own(client, db, commits):
    patient = db.get(Patient, "linda")
    engine_series = load_daily_series(db, patient.id, patient.surgery_date)["resting_hr"]
    body = client.get("/api/patients/linda/series?metric=resting_hr,stress_index&days=365").json()
    rhr, stress = body["series"]
    assert rhr["metric"] == "resting_hr" and rhr["judged"] is True and rhr["baseline"]["n_days"] > 0
    got = {p["day"]: p["value"] for p in rhr["points"]}
    want = {int(day): round(float(value), 3) for day, value in engine_series.dropna().items()}
    assert got == want
    assert all(p["source"] for p in rhr["points"])
    # the stress index is computed, never a stored reading
    assert stress["computed"] is True and stress["points"]
    assert {p["source"] for p in stress["points"]} == {"medpull"}
    assert db.scalar(select(func.count(Observation.id)).where(
        Observation.metric_type == str(M.STRESS_INDEX))) == 0
    assert commits == []
    assert client.get("/api/patients/linda/series?metric=nope").status_code == 422
    assert client.get("/api/patients/linda/series?metric=").status_code == 422


def test_sleep_lists_the_nights_with_their_stages(client, commits):
    body = client.get("/api/patients/aisha/sleep?days=14").json()
    assert body["nights"] and body["nights"] == sorted(
        body["nights"], key=lambda n: n["date"], reverse=True)
    night = body["nights"][0]
    assert night["duration_h"] > 0 and set(night["stages"]) == {"deep", "rem", "light", "awake"}
    assert body["averages"]["nights"] == len(body["nights"])
    assert body["baseline"] and "nocturnal_disruption" in body["derived"]
    assert commits == []
    # nobody wears anything at the lifting clinic: no nights, and no error
    none = client.get("/api/patients/hirt-cole/sleep").json()
    assert none["nights"] == [] and none["averages"]["nights"] == 0


def test_the_reported_grid_is_a_row_per_day_with_checkins_and_exercises(client, commits):
    body = client.get("/api/patients/hirt-cole/reported?days=14").json()
    assert len(body["rows"]) == 14 and body["rows"][0]["date"] == date.today().isoformat()
    assert body["load_unit"] in ("kg", "lb")
    asked = {q["id"]: q for q in body["questions"]}
    assert list(asked)[:1] == ["pain"] and list(asked)[-1] == "note"
    # the question as this clinic's lifters are asked it
    assert asked["pain"]["prompt"] == "How's the pain today, 0 to 10?"
    assert {"swelling", "new_pain", "sleep", "program", "rpe", "minutes"} <= set(asked)

    last_night = body["rows"][1]
    answers = last_night["answers"]
    assert answers["pain"] == 6 and answers["swelling"] == "yes" and answers["program"] == "all"
    assert answers["rpe"] == 8 and answers["minutes"] == 80
    assert last_night["load"] == 640.0 and last_night["program"] == 1.0  # effort x minutes
    # the same evening on the exercise calendar: prescribed against done
    ex = last_night["exercises"]
    assert ex["assigned"] == ex["done"] == 5 and ex["over"] >= 1
    step_ups = next(i for i in ex["items"] if i["title"] == "Step-Ups")
    assert step_ups["load_kg"] == 10 and step_ups["load_done_kg"] == 16 and step_ups["over"]
    assert step_ups["line"].startswith("16 kg done, 10 kg prescribed")
    assert body["summary"]["pain"]["latest"]["value"] == 6
    assert body["summary"]["checkin_days"] == 14 - 1  # every evening but today's
    assert commits == []

    # a day nobody checked in is still a row
    quiet = client.get("/api/patients/hirt-rafael/reported?days=5").json()
    assert [bool(r["checkins"]) for r in quiet["rows"][:3]] == [False, False, False]


def test_a_transcript_reads_back_into_the_answers_that_wrote_it():
    """The grid recovers answers from the stored transcript; whatever the
    question sets can write, it must read back unchanged."""
    samples = {
        "scale": [0, 4, 10], "number": [0, 45], "yes_no": ["yes", "no"], "text": ["Knee is fine."],
    }
    for name, questions in QUESTION_SETS.items():
        for question in questions:
            values = samples.get(question["kind"]) or question["options"]
            for value in values:
                if question["kind"] == "number":
                    lo, hi = question.get("min", 0), question.get("max", 10_000)
                    if not lo <= value <= hi:
                        continue
                answers = {question["id"]: value}
                assert answers_from_pairs(transcript(name, answers)) == answers, (name, question)
    # a free conversation with the assistant is not a questionnaire
    assert answers_from_pairs([("How are you feeling?", "Pretty good, about a 3 today")]) == {}


def test_exports_are_plain_csv_files(client, commits):
    res = client.get("/api/patients/aisha/data/export?kind=observations&metric_type=resting_hr")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    assert 'filename="aisha-readings.csv"' in res.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert rows and {r["metric_type"] for r in rows} == {"resting_hr"}
    assert {"date", "value", "unit", "source", "used_in_series"} <= set(rows[0])

    grid = client.get("/api/patients/hirt-cole/data/export?kind=reported&days=14")
    lines = list(csv.DictReader(io.StringIO(grid.text)))
    assert len(lines) == 14 and lines[1]["pain"] == "6" and lines[1]["training_load_au"] == "640.0"
    assert "Step-Ups: 16 kg done, 10 kg prescribed" in lines[1]["done_against_prescribed"]

    series = client.get("/api/patients/linda/data/export?kind=series&metric=steps,resting_hr")
    daily = list(csv.DictReader(io.StringIO(series.text)))
    assert {r["metric"] for r in daily} == {"steps", "resting_hr"}
    assert client.get("/api/patients/linda/data/export?kind=series").status_code == 422
    assert client.get("/api/patients/linda/data/export?kind=nope").status_code == 422
    assert commits == []


# --- who may read ---------------------------------------------------------------------

CHART_READS = (
    "/api/patients/{id}/data/summary",
    "/api/patients/{id}/observations/browse",
    "/api/patients/{id}/series?metric=steps",
    "/api/patients/{id}/sleep",
    "/api/patients/{id}/reported",
    "/api/patients/{id}/data/export",
)


@pytest.mark.parametrize("path", CHART_READS)
def test_a_chart_read_stays_inside_the_credentials_clinic(client, tokens, path):
    own = client.get(path.format(id="linda"), headers=_auth(tokens["methodist"]))
    assert own.status_code == 200
    other = client.get(path.format(id="hirt-cole"), headers=_auth(tokens["methodist"]))
    assert other.status_code == 404
    assert client.get(path.format(id="linda"), headers=_auth(tokens["mbb"])).status_code == 404
    assert client.get(path.format(id="nobody")).status_code == 404
    # acting for a clinic narrows lists, not a chart opened by id
    assert client.get(path.format(id="linda"), headers={ACTING: "hirt"}).status_code == 200


@pytest.mark.parametrize("path", CHART_READS)
def test_a_chart_read_never_opens_a_subscriber_or_an_athlete(client, db, path):
    from app.models.enums import ProcedureType

    today = date.today()
    rows = [
        Patient(id="data-test-member", name="Member Row", initials="MR", age=30, sex="F",
                procedure_type=ProcedureType.NONE, procedure_display="Personal",
                surgery_date=today, discharge_date=today, surgeon_id="ct_alvarez",
                assigned_provider_id="ct_alvarez", account_kind="personal"),
        Patient(id="data-test-athlete", name="Athlete Row", initials="AR", age=20, sex="M",
                procedure_type=ProcedureType.NONE, procedure_display="Sports",
                surgery_date=today, discharge_date=today, surgeon_id="ct_alvarez",
                assigned_provider_id="ct_alvarez", account_kind="sports"),
    ]
    for row in rows:
        db.add(row)
    db.commit()
    try:
        for row in rows:
            assert client.get(path.format(id=row.id)).status_code == 404
        listed = {p["id"] for p in client.get("/api/data/coverage").json()["patients"]}
        assert not listed & {"data-test-member", "data-test-athlete"}
    finally:
        for row in rows:
            db.delete(row)
        db.commit()
