"""Metrics with less data: the two-day baseline, the per-metric countdown
("x days left"), the patient-facing view, the explanation glossary, and the
non-blocking narrative reads."""

from __future__ import annotations

import pandas as pd
import pytest

from app.engine.baseline import FIRM_BASELINE_DAYS, MIN_BASELINE_DAYS, compute_baseline
from app.engine.care import REGISTRY
from app.engine.confidence import coverage
from app.engine.curves import curve_mid
from app.engine.explain import METRICS, SECTIONS, SIGNALS, glossary
from app.engine.metrics_cards import build_cards
from app.engine.patient_view import metrics_view
from app.engine.readiness import days_left_text, readiness
from app.engine.trajectory import MIN_DAYS, compare
from app.models.enums import ConfidenceLevel, MetricStatus
from app.models.enums import MetricType as M
from app.models.enums import ProcedureType, TrajectoryState
from tests.test_care_metrics import ALL_IDS, _steps_on_curve, make_ctx
from tests.test_engine import SURGERY_DATE, _analyze, _healthy_series

# --- the readiness object -----------------------------------------------------


def test_readiness_counts_down_and_stages():
    r = readiness(0, 2, 3, note="days of steps")
    assert (r.ready, r.stage, r.left, r.firm_left) == (False, "collecting", 2, 3)
    assert days_left_text(r) == "2 more days"
    r = readiness(1, 2, 3)
    assert days_left_text(r) == "1 more day"
    r = readiness(2, 2, 3)
    assert (r.ready, r.stage, r.left, r.firm_left) == (True, "provisional", 0, 1)
    assert days_left_text(r) == "early read · firms up in 1 day"
    r = readiness(5, 2, 3)
    assert (r.ready, r.stage) == (True, "established")
    assert days_left_text(r) is None


def test_readiness_waits_for_post_op_day_two():
    # a patient on day 0: two days before the first countable day, then two days
    r = readiness(0, 2, 3, extra_wait=2)
    assert r.left == 4
    # held back by something a count cannot express: no countdown, just "waiting"
    r = readiness(5, 2, 3, ready=False)
    assert r.left == 0 and days_left_text(r) == "waiting on new data"


# --- the engine with two days -----------------------------------------------


def test_two_days_make_a_provisional_baseline():
    assert MIN_BASELINE_DAYS == 2 and FIRM_BASELINE_DAYS == 3
    two = pd.Series([62.0, 63.0], index=[2, 3])
    baseline = compute_baseline(str(M.RESTING_HR), two)
    assert baseline is not None and baseline.provisional and not baseline.is_preop
    three = pd.Series([62.0, 63.0, 62.5], index=[2, 3, 4])
    assert not compute_baseline(str(M.RESTING_HR), three).provisional
    pre = pd.Series([62.0, 63.0, 70.0], index=[-2, -1, 0])
    baseline = compute_baseline(str(M.RESTING_HR), pre)
    assert baseline.is_preop and baseline.provisional and baseline.n_days == 2
    assert compute_baseline(str(M.RESTING_HR), pd.Series([62.0], index=[2])) is None


def test_a_provisional_baseline_is_never_frozen(db):
    from app.engine import baseline_store
    from app.engine.types import Baseline

    two = Baseline(metric_type=str(M.RESTING_HR), mean=62.0, sd=1.5, n_days=2,
                   window="pre-op days -2..-1", is_preop=True, window_days=[-2, -1],
                   provisional=True)
    before = set(baseline_store.load_established(db, "grace"))
    baseline_store.establish(db, "grace", {str(M.RESTING_HR): two})
    db.rollback()
    assert set(baseline_store.load_established(db, "grace")) == before


def test_cards_show_on_the_third_day_of_wear_and_never_flag_on_two():
    # a device connected the day of surgery: readings on days 0..3
    postop_day = 3
    series = {}
    for metric, value in ((M.RESTING_HR, 62.0), (M.HRV_RMSSD, 45.0), (M.SLEEP_DURATION, 7.2),
                          (M.SKIN_TEMP, 36.5), (M.SPO2, 97.5)):
        series[str(metric)] = pd.Series([value] * 4, index=[0, 1, 2, 3], dtype=float)
    # resting HR jumps on day 3 — a one-day spike against a two-day reference
    series[str(M.RESTING_HR)] = pd.Series([62.0, 62.0, 62.0, 80.0], index=[0, 1, 2, 3])
    baselines, deviations = _analyze(series, ProcedureType.TKA)
    confidence = coverage(series, postop_day)
    cards = build_cards(series, baselines, deviations, confidence, ProcedureType.TKA,
                        postop_day, SURGERY_DATE)
    by_key = {c.metric_key: c for c in cards}
    rhr = by_key[str(M.RESTING_HR)]
    assert rhr.status is not MetricStatus.NODATA, "two days of readings is a reading"
    assert rhr.status is not MetricStatus.FLAG, "a two-day reference may not flag"
    assert rhr.readiness["stage"] == "provisional"
    assert "Early read" in rhr.finding
    assert by_key[str(M.SLEEP_DURATION)].readiness["ready"] is True


def test_cards_count_down_to_their_first_reading():
    postop_day = 0
    series = {str(M.RESTING_HR): pd.Series([70.0], index=[0], dtype=float)}
    baselines, deviations = _analyze(series, ProcedureType.TKA)
    cards = build_cards(series, baselines, deviations, coverage(series, postop_day),
                        ProcedureType.TKA, postop_day, SURGERY_DATE)
    rhr = next(c for c in cards if c.metric_key == str(M.RESTING_HR))
    assert rhr.status is MetricStatus.NODATA
    # nothing counts before day 2, then two days: four more
    assert rhr.readiness == {**rhr.readiness, "ready": False, "left": 4}
    never = next(c for c in cards if c.metric_key == str(M.STEPS))
    assert never.status_text == "Not measured yet" and never.readiness["left"] == 0


def test_trajectory_compares_from_three_days():
    assert MIN_DAYS == 3
    days = [0, 1, 2]
    index = pd.Series([float(curve_mid(ProcedureType.THA, d)) for d in days], index=days)
    result = compare(index, ProcedureType.THA, 2)
    assert result.state == TrajectoryState.ON_TRACK
    assert result.readiness["ready"] and result.readiness["stage"] == "provisional"
    thin = compare(pd.Series([0.3], index=[0]), ProcedureType.THA, 0)
    assert thin.state == TrajectoryState.UNKNOWN and thin.readiness["left"] == 2


def test_confidence_judges_the_panel_the_patient_has():
    postop_day = 14
    full = coverage(_healthy_series(postop_day, ProcedureType.TKA), postop_day)
    assert full.level == ConfidenceLevel.HIGH and len(full.panel) == 6
    # a watch with no temperature sensor: five signals, all reporting -> still high
    no_temp = _healthy_series(postop_day, ProcedureType.TKA)
    del no_temp[str(M.SKIN_TEMP)]
    five = coverage(no_temp, postop_day)
    assert five.level == ConfidenceLevel.HIGH and five.dark_metrics == []
    # a phone alone: steps only -> never more than low
    only_steps = {str(M.STEPS): no_temp[str(M.STEPS)]}
    assert coverage(only_steps, postop_day).level == ConfidenceLevel.LOW
    # two signals, every day: moderate at best
    two = {k: no_temp[k] for k in (str(M.STEPS), str(M.RESTING_HR))}
    assert coverage(two, postop_day).level == ConfidenceLevel.MEDIUM


# --- the care metrics ----------------------------------------------------------


def test_m1_reads_provisionally_from_five_days():
    steps = _steps_on_curve(ProcedureType.THA, 6, pre=0)
    ctx = make_ctx(6, series={str(M.STEPS): steps})
    m = REGISTRY["M1"](ctx)
    assert m.status is not MetricStatus.NODATA
    assert m.readiness["stage"] == "provisional" and m.readiness["firm_left"] > 0
    assert "Early read" in m.finding
    short = make_ctx(4, series={str(M.STEPS): _steps_on_curve(ProcedureType.THA, 4, pre=0)})
    m = REGISTRY["M1"](short)
    assert m.status is MetricStatus.NODATA
    assert m.readiness["left"] >= 1 and m.readiness["unit"] == "days"


def test_m2_reads_from_four_pairs_but_never_flags_on_them():
    from tests.test_care_metrics import _symptom_frame

    steps = pd.Series({d: 2000.0 + 500.0 * (d % 3) for d in range(10, 20)}, dtype=float)
    pain = _symptom_frame({d: 2.0 + 2.0 * ((d - 1) % 3) for d in range(11, 21)}, slot="am")
    ctx = make_ctx(20, series={str(M.STEPS): steps}, pain=pain)
    m = REGISTRY["M2"](ctx)
    assert m.status is not MetricStatus.NODATA
    assert m.readiness["ready"]
    # three pairs: a countdown, in paired days
    few = pd.Series({d: 2000.0 + 500.0 * (d % 3) for d in range(17, 20)}, dtype=float)
    m = REGISTRY["M2"](make_ctx(20, series={str(M.STEPS): few}, pain=pain))
    assert m.status is MetricStatus.NODATA and m.status_text == "Needs more pairs"
    assert m.readiness["unit"] == "paired days" and m.readiness["left"] == 1


@pytest.mark.parametrize("patient_id", ["reyes", "grace", "linda", "priya"])
def test_every_computed_metric_carries_readiness_or_an_unlock(db, patient_id):
    from app.engine.pipeline import latest_assessment

    bundle = latest_assessment(db, patient_id).analytics
    for m in bundle["care_metrics"]["metrics"]:
        if m["status"] != "nodata":
            assert m["readiness"] is None or set(m["readiness"]) >= {"ready", "left", "stage"}, m["id"]
        else:
            assert m["readiness"] or m["unlock"], m["id"]
    for card in bundle["metrics"]:
        assert card["readiness"] is not None, card["metric_key"]
    assert bundle["trajectory"]["readiness"] is not None


# --- the glossary --------------------------------------------------------------


def test_glossary_covers_every_metric_signal_and_section():
    from app.engine.metrics_cards import CARD_ORDER

    assert set(METRICS) == set(ALL_IDS)
    for metric, *_ in CARD_ORDER:
        assert str(metric) in SIGNALS, str(metric)
    assert {"trajectory", "composite", "adherence", "confidence", "risk_tier"} <= set(SECTIONS)
    for table in (METRICS, SIGNALS, SECTIONS):
        for key, entry in table.items():
            for field in ("title", "what", "inputs", "how", "reading", "shows_after",
                          "patient_what", "patient_why", "patient_help"):
                assert entry.get(field), f"{key}.{field}"
    payload = glossary()
    assert set(payload) == {"metrics", "signals", "sections"}


def test_glossary_never_uses_diagnostic_verbs():
    from app.llm.insights import BANNED

    for table in (METRICS, SIGNALS, SECTIONS):
        for key, entry in table.items():
            for field in ("patient_what", "patient_why", "patient_help"):
                assert not BANNED.search(entry[field]), f"{key}.{field}"


def test_explain_endpoint(client):
    body = client.get("/api/explain").json()
    assert body["metrics"]["M1"]["title"] and body["signals"]["steps"]["shows_after"]
    one = client.get("/api/explain/metrics/M12").json()
    assert one["kind"] == "metrics" and "Mahalanobis" in one["how"]
    assert client.get("/api/explain/metrics/M99").status_code == 404


# --- the patient view ----------------------------------------------------------


def test_patient_view_never_carries_clinical_verdicts(db):
    from app.engine.pipeline import latest_assessment
    from app.llm.insights import BANNED

    view = metrics_view(latest_assessment(db, "reyes").analytics, True, signal_days=8)
    assert view["metrics"], "the headline metrics are the first rows"
    states = {m["state"] for m in view["metrics"]}
    assert states <= {"good", "watch", "reviewing", "waiting"}
    for m in view["metrics"] + view["signals"]:
        assert not BANNED.search(m["headline"])
        for word in ("σ", "Mahalanobis", "z-score", "composite", "deterioration", "flag"):
            assert word not in m["headline"], (m, word)
        assert m["explain"] is None or set(m["explain"]) == {"title", "what", "why", "help"}
    reviewing = [m for m in view["metrics"] if m["state"] == "reviewing"]
    assert reviewing, "Marcus's flagged metrics read as 'your care team is taking a look'"
    assert "care team" in reviewing[0]["headline"]
    assert view["overall"]["blurb"]


def test_patient_view_counts_down_for_a_thin_record(db):
    from app.engine.pipeline import latest_assessment

    view = metrics_view(latest_assessment(db, "grace").analytics, True, signal_days=3)
    waiting = [m for m in view["metrics"] if m["state"] == "waiting" and m["days_left_text"]]
    assert waiting and all(m["days_left_text"].endswith("days") or m["days_left_text"].endswith("day")
                           or "more" in m["days_left_text"] for m in waiting)
    assert view["overall"]["days_until_full_picture"]
    assert view["trajectory"]["explain"]["what"]


def test_mobile_metrics_endpoint(client):
    from tests.test_mobile import _enroll

    headers, _ = _enroll(client, "grace", hospital_id="hosp_hermann", phone="+15125550199")
    body = client.get("/api/mobile/metrics", headers=headers).json()
    assert body["mode"] == "recovery"
    assert set(body) >= {"overall", "metrics", "signals", "trajectory"}
    me = client.get("/api/mobile/me", headers=headers).json()
    assert "days_until_full_picture" in me["recovery"]


# --- non-blocking narratives ---------------------------------------------------


def test_page_reads_never_call_the_model_and_the_warm_call_does(client, db, monkeypatch):
    from app.llm import insights

    calls: list[str] = []

    def fake_complete_json(system, user, **kwargs):
        calls.append(user)
        if '"reason"' in user:
            return {"reason": "RHR +8 vs baseline · temp up"}
        if '"briefing"' in user:
            return {"briefing": "Start with Marcus Reyes, whose heart rate and temperature are up. " * 2}
        if '"actions"' in user:
            return {"actions": [{"title": "Call Marcus about the chills", "detail": "d", "urgency": "today"}]}
        return {"summary": "Marcus needs a call today: his heart rate and temperature are both up. " * 2}

    monkeypatch.setattr(insights, "provider_name", lambda: "groq")
    monkeypatch.setattr(insights, "model_name", lambda: "fake-model")
    monkeypatch.setattr(insights, "complete_json", fake_complete_json)

    worklist = client.get("/api/worklist").json()
    assert calls == [], "the worklist read must not wait on the model"
    assert worklist["narratives_pending"] >= 1
    detail = client.get("/api/patients/reyes").json()
    assert calls == []
    assert detail["narratives_pending"] == 2 and detail["summary"]["provider"] == "fallback"

    warmed = client.post("/api/narratives/warm", json={"patient_id": "reyes", "worklist": False}).json()
    assert warmed["spent"] == 2 and len(calls) == 2
    after = client.get("/api/patients/reyes").json()
    assert after["narratives_pending"] == 0 and after["summary"]["provider"] == "groq"
    assert after["summary"]["text"].startswith("Marcus needs a call today")

    before = len(calls)
    warmed = client.post("/api/narratives/warm", json={"worklist": True, "budget": 2}).json()
    assert warmed["spent"] == 2 and len(calls) == before + 2
