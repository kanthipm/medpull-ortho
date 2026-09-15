"""The care-metrics engine: every metric on a synthetic context (computable
and NODATA paths), the guardrails, headline selection, the seeded roster,
and the API shapes."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.engine.care import REGISTRY, compute_care_metrics, unavailable_bundle
from app.engine.care._common import STATUS_RANK
from app.engine.care.catalog import CATALOG, CATALOG_ORDER, FAMILIES
from app.engine.care.headline import select_headline
from app.engine.care.pathways import PATHWAYS, pathway_for
from app.engine.care.types import CareContext, CareMetric
from app.engine.curves import curve_mid
from app.engine.types import (
    AdherenceResult,
    Baseline,
    CompositeResult,
    ConfidenceResult,
    DeviationResult,
    TrajectoryResult,
)
from app.llm.insights import BANNED
from app.models.enums import ConfidenceLevel, MetricStatus
from app.models.enums import MetricType as M
from app.models.enums import ProcedureType, TrajectoryState

SURGERY = date(2026, 3, 1)
ALL_IDS = [f"M{i}" for i in range(1, 19)] + [f"C{i}" for i in range(1, 7)]


# --- synthetic context helpers -------------------------------------------------


def _series(values, start: int = 0) -> pd.Series:
    return pd.Series(list(values), index=list(range(start, start + len(values))), dtype=float)


def _dev(metric: M, raw_z: float, series_z: list[float] | None = None, last_day: int = 20,
         flagged: bool = False, drifting: bool = False) -> DeviationResult:
    z = series_z if series_z is not None else [raw_z] * 14
    return DeviationResult(
        metric_type=str(metric), flagged=flagged, direction="up" if raw_z > 0 else "down",
        latest_z=z[-1], raw_z=raw_z, consecutive_out=0, drifting=drifting, last_day=last_day,
        series_z=z,
    )


def _baseline(metric: M, mean: float, sd: float = 1.0) -> Baseline:
    return Baseline(metric_type=str(metric), mean=mean, sd=sd, n_days=10,
                    window="pre-op days -10..-1", is_preop=True,
                    window_days=list(range(-10, 0)))


def make_ctx(postop_day: int = 20, procedure: ProcedureType = ProcedureType.THA,
             pathway: str = "ortho_tha", series: dict | None = None, **overrides) -> CareContext:
    fields = dict(
        patient_id="test", first_name="Test", procedure=procedure, pathway=PATHWAYS[pathway],
        postop_day=postop_day, surgery_date=SURGERY, today=SURGERY + timedelta(days=postop_day),
        series=series or {}, baselines={}, deviations={},
        confidence=ConfidenceResult(score=1.0, level=ConfidenceLevel.HIGH, days_with_data=7,
                                    window_days=7),
        trajectory=TrajectoryResult(state=TrajectoryState.ON_TRACK, pct=0.0,
                                    change_point_day=None),
        composite=CompositeResult(index=0.0, level="normal"),
        adherence=AdherenceResult(rate=0.0, verified=0, assigned=0, self_attested=0),
        now=datetime.combine(SURGERY + timedelta(days=postop_day), datetime.min.time())
        + timedelta(hours=12),
    )
    fields.update(overrides)
    return CareContext(**fields)


def _symptom_frame(values: dict[int, float], slot: str = "pm") -> pd.DataFrame:
    rows = []
    for day, v in values.items():
        rows.append({"day": day, "am": v if slot == "am" else np.nan,
                     "pm": v if slot == "pm" else np.nan, "mean": v})
    return pd.DataFrame(rows, columns=["day", "am", "pm", "mean"])


def _steps_on_curve(procedure: ProcedureType, postop_day: int, base: float = 6000.0,
                    pre: int = 10) -> pd.Series:
    days = list(range(-pre, postop_day + 1))
    return pd.Series([base if d < 0 else base * float(curve_mid(procedure, d)) for d in days],
                     index=days, dtype=float)


def _healthy_ctx(postop_day: int = 20) -> CareContext:
    steps = _steps_on_curve(ProcedureType.THA, postop_day)
    return make_ctx(postop_day, series={str(M.STEPS): steps})


def _assert_clean(metric: CareMetric | dict) -> None:
    payload = metric.to_dict() if isinstance(metric, CareMetric) else metric
    for key in ("status_text", "finding", "next_step", "method", "unlock", "delta_text", "name"):
        text = payload.get(key) or ""
        assert not BANNED.search(text), f"{payload['id']}.{key}: {text!r}"


# --- catalog / registry / guardrails ------------------------------------------------


def test_catalog_covers_every_metric_and_family():
    assert CATALOG_ORDER == ALL_IDS
    family_ids = [i for _, _, ids in FAMILIES for i in ids]
    assert sorted(family_ids) == sorted(ALL_IDS)
    assert set(REGISTRY) == set(ALL_IDS)
    for definition in CATALOG.values():
        assert definition.unlock and definition.method_short and definition.domains
    assert {d.id for d in CATALOG.values() if d.guarded} == {"M12", "M13", "C1", "C2", "C4"}


def test_empty_context_yields_nodata_for_everything_with_unlock_text():
    ctx = make_ctx(series={})
    bundle = compute_care_metrics(ctx)
    assert bundle["version"] == "care-1" and bundle["pathway"] == "ortho_tha"
    assert len(bundle["metrics"]) == 24
    for metric in bundle["metrics"]:
        if metric["id"] == "M16":
            continue  # data confidence always reads the engine's coverage result
        assert metric["status"] == "nodata", metric["id"]
        assert metric["unlock"], metric["id"]
        assert isinstance(metric["applicable"], bool)
        _assert_clean(metric)
    assert len(bundle["headline"]) == 3


def test_compute_never_raises_and_replaces_a_failing_metric(monkeypatch):
    def boom(ctx):
        raise RuntimeError("synthetic failure")

    monkeypatch.setitem(REGISTRY, "M1", boom)
    bundle = compute_care_metrics(_healthy_ctx())
    m1 = bundle["metrics"][0]
    assert m1["id"] == "M1" and m1["status"] == "nodata"
    assert m1["status_text"] == "Unavailable"
    assert m1["finding"] == "This metric could not be computed from the current data."


def test_unavailable_bundle_has_the_full_shape():
    bundle = unavailable_bundle(PATHWAYS["copd"])
    assert bundle["pathway"] == "copd" and len(bundle["metrics"]) == 24
    assert bundle["headline"] == ["C2", "M2", "M1"]


def test_applicable_follows_the_pathway_domain():
    ortho = compute_care_metrics(make_ctx())
    by_id = {m["id"]: m for m in ortho["metrics"]}
    assert by_id["M1"]["applicable"] is True
    assert by_id["C3"]["applicable"] is False
    assert by_id["C3"]["status_text"] == "Not used on this pathway"
    cardiac = compute_care_metrics(make_ctx(pathway="heart_failure"))
    by_id = {m["id"]: m for m in cardiac["metrics"]}
    assert by_id["C1"]["applicable"] is True
    assert by_id["M3"]["applicable"] is False


def test_pathway_for_derives_from_procedure_and_honours_an_explicit_key():
    class P:
        procedure_type = ProcedureType.ROTATOR_CUFF

    assert pathway_for(P()).key == "ortho_shoulder"

    class Q:
        procedure_type = ProcedureType.TKA
        care_pathway = "heart_failure"

    assert pathway_for(Q()).key == "heart_failure"

    class R:
        procedure_type = "nope"

    assert pathway_for(R()).key == "general_recovery"


def test_headline_prefers_live_metrics_in_pathway_order_and_gates_on_m16():
    def stub(mid: str, status: MetricStatus) -> dict:
        return {"id": mid, "status": str(status)}

    metrics = [stub(i, MetricStatus.NODATA) for i in ALL_IDS]
    assert select_headline(PATHWAYS["ortho_tka"], metrics) == ["M1", "M2", "M12"]
    live = {"M12": MetricStatus.OK, "M9": MetricStatus.WATCH}
    metrics = [stub(i, live.get(i, MetricStatus.NODATA)) for i in ALL_IDS]
    assert select_headline(PATHWAYS["ortho_tka"], metrics) == ["M12", "M9", "M1"]
    assert select_headline(PATHWAYS["ortho_shoulder"], metrics) == ["M9", "M12", "M2"]
    live["M16"] = MetricStatus.FLAG
    metrics = [stub(i, live.get(i, MetricStatus.NODATA)) for i in ALL_IDS]
    assert select_headline(PATHWAYS["ortho_tka"], metrics) == ["M12", "M9", "M16"]


# --- per-metric computable cases -----------------------------------------------------


def test_m1_flags_overreaching_and_collapsing_load():
    postop_day = 30
    steps = _steps_on_curve(ProcedureType.THA, postop_day)
    spiked = steps.copy()
    spiked.loc[24:30] = spiked.loc[24:30] * 2.5
    m = REGISTRY["M1"](make_ctx(postop_day, series={str(M.STEPS): spiked}))
    assert m.status is MetricStatus.FLAG and "Overreaching" in m.status_text
    assert m.chart is not None and m.chart.kind == "band" and m.chart.band
    collapsed = steps.copy()
    collapsed.loc[24:30] = collapsed.loc[24:30] * 0.25
    m = REGISTRY["M1"](make_ctx(postop_day, series={str(M.STEPS): collapsed}))
    assert m.status is MetricStatus.FLAG and "collapsing" in m.status_text
    assert REGISTRY["M1"](make_ctx(postop_day, series={str(M.STEPS): steps})).status is MetricStatus.OK
    # a chronic pathway uses the raw ratio
    chronic = make_ctx(postop_day, pathway="heart_failure", series={str(M.STEPS): spiked})
    assert REGISTRY["M1"](chronic).status is MetricStatus.FLAG


def test_m1_falls_back_to_energy_and_goes_stale():
    postop_day = 30
    energy = _steps_on_curve(ProcedureType.THA, postop_day, base=300.0)
    m = REGISTRY["M1"](make_ctx(postop_day, series={str(M.ACTIVE_ENERGY): energy}))
    assert m.status is MetricStatus.OK and "energy load" in m.finding
    stale = energy[energy.index <= 20]
    m = REGISTRY["M1"](make_ctx(postop_day, series={str(M.ACTIVE_ENERGY): stale}))
    assert m.status is MetricStatus.NODATA and m.status_text == "No recent data"


def test_m2_flags_a_steep_dose_response_and_names_the_symptom():
    postop_day = 25
    rng = np.random.default_rng(0)
    days = list(range(0, postop_day + 1))
    steps = pd.Series(3000 + rng.uniform(-1500, 1500, len(days)), index=days)
    pain = {d + 1: min(10.0, 2.0 + 1.5 * float(steps.loc[d]) / 1000.0) for d in days[:-1]}
    ctx = make_ctx(postop_day, series={str(M.STEPS): steps}, pain=_symptom_frame(pain, "am"))
    m = REGISTRY["M2"](ctx)
    assert m.status is MetricStatus.FLAG and m.status_text == "Irritability rising"
    assert m.name == "Pain–load sensitivity" and m.unit == "pts / 1k steps"
    assert m.chart is not None and m.chart.kind == "scatter" and m.chart.fit
    _assert_clean(m)
    # COPD pairs breathlessness with load
    breath = {d + 1: min(4.0, 0.5 + 0.8 * float(steps.loc[d]) / 1000.0) for d in days[:-1]}
    copd = make_ctx(postop_day, pathway="copd", series={str(M.STEPS): steps},
                    symptoms={"breathlessness": _symptom_frame(breath, "am")})
    m = REGISTRY["M2"](copd)
    assert m.name == "Breathlessness–load sensitivity"
    assert m.status in (MetricStatus.FLAG, MetricStatus.WATCH)


def test_m2_nodata_says_what_unlocks_it():
    m = REGISTRY["M2"](_healthy_ctx())
    assert m.status is MetricStatus.NODATA
    assert "Log pain AM & PM" in (m.unlock or "")


def test_m3_flags_an_elevated_plateau_and_falls_back_to_double_support():
    postop_day = 20
    days = list(range(-10, postop_day + 1))
    asym = pd.Series([4.0 if d < 0 else 12.0 for d in days], index=days)
    m = REGISTRY["M3"](make_ctx(postop_day, series={str(M.WALKING_ASYMMETRY_PCT): asym}))
    assert m.status is MetricStatus.FLAG and "plateaued" in m.status_text
    improving = pd.Series([4.0 if d < 0 else 4.0 + 12.0 * np.exp(-0.2 * d) for d in days],
                          index=days)
    m = REGISTRY["M3"](make_ctx(postop_day, series={str(M.WALKING_ASYMMETRY_PCT): improving}))
    assert m.status is MetricStatus.OK and m.status_text == "Near symmetric"
    ds = pd.Series([25.0 if d < 0 else 31.0 for d in days], index=days)
    m = REGISTRY["M3"](make_ctx(postop_day, series={str(M.DOUBLE_SUPPORT_PCT): ds}))
    assert "double support" in m.name and m.status is MetricStatus.FLAG


def _walk(day: int, minutes: int, c0: float, fade: float, hr_reserve: float, rhr: float = 60.0):
    cadence = [c0 * (1 - fade * m) for m in range(minutes)]
    return {"day": day, "kind": "guided_walk", "minutes": float(minutes), "cadence_spm": cadence,
            "hr_bpm": [rhr + hr_reserve] * minutes, "speed_mps": [c * 0.6 / 60 for c in cadence],
            "steps": sum(cadence)}


def test_m4_and_m5_read_walk_detail():
    walks = [_walk(d, 8, 100.0, 0.005, 30.0 + 2.0 * d) for d in range(4, 20, 3)]
    ctx = make_ctx(20, sessions=walks, baselines={str(M.RESTING_HR): _baseline(M.RESTING_HR, 60.0)})
    m4 = REGISTRY["M4"](ctx)
    assert m4.status is MetricStatus.FLAG and m4.status_text == "Effort cost rising"
    assert m4.unit == "bpm / spm"
    m5 = REGISTRY["M5"](ctx)
    assert m5.status is MetricStatus.OK and m5.status_text == "Sustaining cadence"
    fading = [_walk(d, 8, 100.0, 0.04, 30.0) for d in range(4, 20, 3)]
    m5 = REGISTRY["M5"](make_ctx(20, sessions=fading))
    assert m5.status is MetricStatus.FLAG and "time to fatigue" in (m5.delta_text or "")
    assert m5.chart is not None and m5.chart.x_label == "Minute"
    nodata = REGISTRY["M4"](make_ctx(20))
    assert nodata.status is MetricStatus.NODATA and "guided walk" in nodata.unlock


def test_m6_sit_to_stand_up_and_down():
    days = list(range(6, 21))
    up = pd.Series([6.0 if d < 14 else 9.0 for d in days], index=days)
    assert REGISTRY["M6"](make_ctx(20, series={str(M.SIT_TO_STAND): up})).status_text == "Chair rises up"
    down = pd.Series([8.0 if d < 14 else 4.0 for d in days], index=days)
    m = REGISTRY["M6"](make_ctx(20, series={str(M.SIT_TO_STAND): down}))
    assert m.status is MetricStatus.WATCH and m.status_text == "Chair rises down"
    assert m.chart is not None and m.chart.kind == "bars"


def test_m7_uses_the_engine_deviation_and_cadence_when_step_length_exists():
    postop_day = 20
    days = list(range(-10, postop_day + 1))
    speed = pd.Series([1.2 if d < 0 else 1.2 * float(curve_mid(ProcedureType.THA, d)) for d in days],
                      index=days)
    ctx = make_ctx(postop_day, series={str(M.WALKING_SPEED): speed},
                   baselines={str(M.WALKING_SPEED): _baseline(M.WALKING_SPEED, 1.2, 0.06)},
                   deviations={str(M.WALKING_SPEED): _dev(M.WALKING_SPEED, -3.0, flagged=True)})
    m = REGISTRY["M7"](ctx)
    assert m.status is MetricStatus.FLAG and m.status_text == "Below expected pace"
    assert m.name == "Walking pace recovery" and m.chart.reference is not None
    step_len = pd.Series([0.6] * len(days), index=days)
    m = REGISTRY["M7"](make_ctx(postop_day, series={str(M.WALKING_SPEED): speed,
                                                     str(M.STEP_LENGTH): step_len}))
    assert m.name == "Cadence recovery curve" and m.unit == "spm"
    chronic = make_ctx(postop_day, pathway="copd", series={str(M.WALKING_SPEED): speed})
    assert REGISTRY["M7"](chronic).status_text in ("Holding own baseline", "Dip vs own baseline")


def test_m8_stairs_plateau_progressing_and_not_resumed():
    days = list(range(0, 21))
    flat = pd.Series([0.0 if d < 5 else 2.0 for d in days], index=days)
    m = REGISTRY["M8"](make_ctx(20, series={str(M.FLIGHTS_CLIMBED): flat}))
    assert m.status is MetricStatus.WATCH and "plateaued" in m.status_text
    assert m.delta_text.startswith("since day 5")
    rising = pd.Series([0.0 if d < 5 else 1.0 + 0.4 * (d - 5) for d in days], index=days)
    m = REGISTRY["M8"](make_ctx(20, series={str(M.FLIGHTS_CLIMBED): rising}))
    assert m.status is MetricStatus.OK and m.status_text == "Progressing"
    none = pd.Series([0.0] * 25, index=list(range(0, 25)))
    m = REGISTRY["M8"](make_ctx(24, series={str(M.FLIGHTS_CLIMBED): none}))
    assert m.status is MetricStatus.WATCH and m.status_text == "Stairs not yet resumed"
    high = pd.Series([0.0 if d < 3 else 6.0 for d in days], index=days)
    assert REGISTRY["M8"](make_ctx(20, series={str(M.FLIGHTS_CLIMBED): high})).status is MetricStatus.OK
    assert REGISTRY["M8"](make_ctx(20)).status is MetricStatus.NODATA


def test_m9_flags_fragmentation_that_tracks_evening_pain():
    postop_day = 20
    days = list(range(-10, postop_day + 1))
    rows = []
    pain = {}
    for d in days:
        frag = 0.08 if d < 8 else 0.20 + 0.01 * ((d - 8) % 3)
        rows.append({"day": d, "total_h": 7.0, "awake_h": 7.0 * frag, "deep_h": 1.4,
                     "rem_h": 1.5, "light_h": 7.0 - 2.9 - 7.0 * frag})
        pain[d] = 3.0 + 30.0 * (frag - 0.08)
    ctx = make_ctx(postop_day, sleep_stages=pd.DataFrame(rows), pain=_symptom_frame(pain, "pm"))
    m = REGISTRY["M9"](ctx)
    assert m.status is MetricStatus.FLAG and "tracks pain" in m.status_text
    assert "for review" in m.finding and m.chart.kind == "dual"
    _assert_clean(m)
    # duration-only fallback
    sleep = pd.Series([7.0] * len(days), index=days)
    ctx = make_ctx(postop_day, series={str(M.SLEEP_DURATION): sleep},
                   deviations={str(M.SLEEP_DURATION): _dev(M.SLEEP_DURATION, -3.0, flagged=True)})
    m = REGISTRY["M9"](ctx)
    assert m.status is MetricStatus.WATCH and m.unit == "sleep duration only"


def test_m10_sustained_stress_flags_and_variant_hrv_is_accepted():
    hrv = _dev(M.HRV_RMSSD, -2.0, [-2.0] * 14)
    rhr = _dev(M.RESTING_HR, 2.0, [2.0] * 14)
    m = REGISTRY["M10"](make_ctx(deviations={str(M.HRV_RMSSD): hrv, str(M.RESTING_HR): rhr}))
    assert m.status is MetricStatus.FLAG and "Sustained" in m.status_text
    assert "monitoring context" in m.finding
    _assert_clean(m)
    sdnn = _dev(M.HRV_SDNN, -0.2, [-0.2] * 14)
    m = REGISTRY["M10"](make_ctx(deviations={str(M.RESTING_HR): _dev(M.RESTING_HR, 0.1, [0.1] * 14)},
                                 local_deviations={str(M.HRV_SDNN): sdnn}))
    assert m.status is MetricStatus.OK and str(M.HRV_SDNN) in m.inputs
    assert REGISTRY["M10"](make_ctx()).status is MetricStatus.NODATA


def _hourly(days: list[int], amplitude: float) -> pd.DataFrame:
    rows = []
    for d in days:
        for h in range(24):
            rows.append({"day": d, "hour": h,
                         "value": max(0.0, 200 + amplitude * np.cos(2 * np.pi * (h - 14) / 24))})
    return pd.DataFrame(rows)


def test_m11_sees_a_flattening_rhythm():
    days = list(range(7, 21))
    flat = pd.concat([_hourly(days[:7], 180.0), _hourly(days[7:], 60.0)])
    m = REGISTRY["M11"](make_ctx(20, intraday={str(M.STEPS): flat}))
    assert m.status is MetricStatus.WATCH and m.status_text == "Rhythm flattening"
    assert "peak 14:00" in m.delta_text and m.chart.x_label == "Hour"
    stable = _hourly(days, 180.0)
    assert REGISTRY["M11"](make_ctx(20, intraday={str(M.STEPS): stable})).status_text == "Rhythm stable"
    assert REGISTRY["M11"](make_ctx(20)).status is MetricStatus.NODATA


def test_m12_is_guarded_and_agrees_with_the_composite():
    quiet = [0.0] * 14
    deviations = {
        str(M.RESTING_HR): _dev(M.RESTING_HR, 3.5, quiet),
        str(M.SKIN_TEMP): _dev(M.SKIN_TEMP, 3.5, quiet),
        str(M.HRV_RMSSD): _dev(M.HRV_RMSSD, -3.0, quiet),
        str(M.RESPIRATORY_RATE): _dev(M.RESPIRATORY_RATE, 2.0, quiet),
    }
    ctx = make_ctx(20, deviations=deviations, composite=CompositeResult(index=2.4, level="high"))
    m = REGISTRY["M12"](ctx)
    assert m.status is MetricStatus.FLAG and m.guarded
    assert "recommend clinician review" in m.finding
    assert m.drivers and m.drivers[0]["contribution"] >= m.drivers[-1]["contribution"]
    assert "infection" not in m.finding.lower() and "sepsis" not in m.finding.lower()
    _assert_clean(m)
    calm = {k: _dev(M(k), 0.2, quiet) for k in deviations}
    m = REGISTRY["M12"](make_ctx(20, deviations=calm))
    assert m.status is MetricStatus.OK
    early = REGISTRY["M12"](make_ctx(5, deviations=calm))
    assert "Early post-op" in early.finding
    chronic = REGISTRY["M12"](make_ctx(5, pathway="heart_failure", deviations=calm))
    assert "Early post-op" not in chronic.finding and "program" in chronic.delta_text
    two = {k: v for k, v in list(calm.items())[:2]}
    assert REGISTRY["M12"](make_ctx(20, deviations=two)).status is MetricStatus.NODATA


def test_m13_coupling_flags_only_with_temperature_involved():
    rising = [0.0] * 7 + [1.5, 1.8, 2.0]
    deviations = {
        str(M.SKIN_TEMP): _dev(M.SKIN_TEMP, 2.0, rising),
        str(M.RESTING_HR): _dev(M.RESTING_HR, 2.0, rising),
        str(M.HRV_RMSSD): _dev(M.HRV_RMSSD, -2.0, [-z for z in rising]),
    }
    m = REGISTRY["M13"](make_ctx(20, deviations=deviations))
    assert m.status is MetricStatus.FLAG and m.guarded and "recommend review" in m.finding
    _assert_clean(m)
    cardiac_only = dict(deviations)
    cardiac_only[str(M.SKIN_TEMP)] = _dev(M.SKIN_TEMP, 0.0, [0.0] * 10)
    assert REGISTRY["M13"](make_ctx(20, deviations=cardiac_only)).status is MetricStatus.OK
    assert REGISTRY["M13"](make_ctx(20)).status is MetricStatus.NODATA


def _tasks(today: date, pattern: list[str]) -> list[dict]:
    records = {today - timedelta(days=i): (status, "seed") for i, status in enumerate(pattern)}
    return [{"id": 1, "title": "Walk twice daily", "kind": "walk", "status": "pending",
             "records": records}]


def test_m14_rates_match_the_adherence_result_and_flag_low():
    postop_day = 20
    today = SURGERY + timedelta(days=postop_day)
    tasks = _tasks(today, ["missed"] * 10 + ["verified"] * 4)
    ctx = make_ctx(postop_day, tasks=tasks,
                   adherence=AdherenceResult(rate=0.29, verified=4, assigned=14, self_attested=0))
    m = REGISTRY["M14"](ctx)
    assert m.status is MetricStatus.FLAG and m.status_text == "Adherence low"
    assert "29% incl. self-reported" in m.delta_text and m.chart.kind == "heat"
    good = _tasks(today, ["verified"] * 14)
    ctx = make_ctx(postop_day, tasks=good,
                   adherence=AdherenceResult(rate=1.0, verified=14, assigned=14, self_attested=0))
    assert REGISTRY["M14"](ctx).status is MetricStatus.OK
    assert REGISTRY["M14"](make_ctx(postop_day)).status is MetricStatus.NODATA


def test_m15_disengagement_from_silence_and_missed_tasks():
    postop_day = 20
    today = SURGERY + timedelta(days=postop_day)
    checkins = [{"occurred_at": datetime.combine(today - timedelta(days=9), datetime.min.time()),
                 "channel": "app", "patient_chars": 200, "n_patient_msgs": 3, "flags": 0}]
    ctx = make_ctx(postop_day, checkins=checkins,
                   adherence=AdherenceResult(rate=0.3, verified=3, assigned=10, self_attested=0))
    m = REGISTRY["M15"](ctx)
    assert m.status is MetricStatus.WATCH and m.chart.kind == "gauge"
    assert {d["key"] for d in m.drivers} == {"latency", "length_decay", "movement", "adherence"}
    silent = make_ctx(postop_day, adherence=AdherenceResult(rate=0.0, verified=0, assigned=10,
                                                              self_attested=0))
    m = REGISTRY["M15"](silent)
    assert m.status is MetricStatus.FLAG and m.status_text == "Disengaging"
    assert REGISTRY["M15"](make_ctx(postop_day)).status is MetricStatus.NODATA


def test_m16_follows_the_confidence_level():
    low = make_ctx(confidence=ConfidenceResult(score=0.2, level=ConfidenceLevel.LOW,
                                               days_with_data=1, window_days=7,
                                               dark_metrics=[str(M.SPO2)]))
    m = REGISTRY["M16"](low)
    assert m.status is MetricStatus.FLAG and m.status_text == "Cannot see this patient"
    assert "no device" in m.delta_text
    assert REGISTRY["M16"](_healthy_ctx()).status is MetricStatus.OK


def test_m17_reads_the_engine_verdict_and_fits_a_pace():
    postop_day = 25
    actual = [{"day": d, "v": 0.85 * float(curve_mid(ProcedureType.THA, d))} for d in range(0, 26)]
    traj = TrajectoryResult(state=TrajectoryState.BEHIND, pct=-15.0, change_point_day=None,
                            actual=actual, expected=[{"day": d, "lo": 0.3, "mid": 0.4, "hi": 0.5}
                                                     for d in range(0, 26)])
    m = REGISTRY["M17"](make_ctx(postop_day, trajectory=traj))
    assert m.status is MetricStatus.FLAG and m.status_text == "Behind expected curve"
    assert m.value == "−15%" and m.chart.kind == "band" and m.chart.fit
    thin = TrajectoryResult(state=TrajectoryState.UNKNOWN, pct=None, change_point_day=None,
                            actual=actual[:3])
    assert REGISTRY["M17"](make_ctx(postop_day, trajectory=thin)).status is MetricStatus.NODATA
    steps = _steps_on_curve(ProcedureType.THA, postop_day)
    chronic = REGISTRY["M17"](make_ctx(postop_day, pathway="hypertension",
                                       series={str(M.STEPS): steps}))
    assert chronic.name == "Trend vs own baseline"
    assert "curve" not in chronic.status_text


def test_m18_finds_a_plateau_and_a_regression():
    postop_day = 20
    days = list(range(0, postop_day + 1))
    plateau = pd.Series([6000 * float(curve_mid(ProcedureType.THA, min(d, 8))) for d in days],
                        index=days)
    m = REGISTRY["M18"](make_ctx(postop_day, series={str(M.STEPS): plateau}))
    assert m.status is MetricStatus.WATCH and m.status_text.startswith("Plateau since day")
    assert m.drivers[0]["metric_type"] == "trajectory"
    dropped = pd.Series([4000.0 if d < 14 else 2000.0 for d in days], index=days)
    m = REGISTRY["M18"](make_ctx(postop_day, series={str(M.STEPS): dropped}))
    assert m.status is MetricStatus.FLAG and m.status_text == "Regression since day 14"
    on_curve = _steps_on_curve(ProcedureType.THA, postop_day)
    assert REGISTRY["M18"](make_ctx(postop_day, series={str(M.STEPS): on_curve})).status is MetricStatus.OK


def test_c1_weight_gain_is_guarded():
    days = list(range(0, 21))
    weight = pd.Series([70.0] * 19 + [70.4, 72.5], index=days)
    m = REGISTRY["C1"](make_ctx(20, pathway="heart_failure", series={str(M.BODY_WEIGHT): weight}))
    assert m.status is MetricStatus.FLAG and "fluid retention" in m.finding
    assert "decompensation" not in m.finding.lower()
    _assert_clean(m)
    stable = pd.Series([70.0] * 21, index=days)
    assert REGISTRY["C1"](make_ctx(20, series={str(M.BODY_WEIGHT): stable})).status is MetricStatus.OK


def test_c2_desaturation_burden():
    days = list(range(-10, 21))
    spo2 = pd.Series([97.0] * 29 + [89.0, 88.5], index=days)
    m = REGISTRY["C2"](make_ctx(20, pathway="copd", series={str(M.SPO2): spo2}))
    assert m.status is MetricStatus.FLAG and m.guarded
    fine = pd.Series([97.0] * 31, index=days)
    assert REGISTRY["C2"](make_ctx(20, series={str(M.SPO2): fine})).status is MetricStatus.OK


def test_c3_time_in_range_from_readings_and_summaries():
    rows = [{"day": 20 - i // 12, "value": 120.0 if i % 3 else 220.0, "granularity": "instant",
             "json": None} for i in range(120)]
    m = REGISTRY["C3"](make_ctx(20, pathway="diabetes", glucose=pd.DataFrame(rows)))
    assert m.status is MetricStatus.WATCH and m.value == "67"
    summaries = [{"day": d, "value": 150.0, "granularity": "daily_summary",
                  "json": {"tir_pct": 40.0, "mean": 190.0, "hypo_count": 1}} for d in range(14, 21)]
    m = REGISTRY["C3"](make_ctx(20, pathway="diabetes", glucose=pd.DataFrame(summaries)))
    assert m.status is MetricStatus.FLAG and m.drivers[0]["count"] == 7


def test_c4_blood_pressure_above_target():
    days = list(range(0, 21))
    sys = pd.Series([152.0] * 21, index=days)
    dia = pd.Series([94.0] * 21, index=days)
    m = REGISTRY["C4"](make_ctx(20, pathway="hypertension",
                                series={str(M.BLOOD_PRESSURE_SYSTOLIC): sys,
                                        str(M.BLOOD_PRESSURE_DIASTOLIC): dia}))
    assert m.status is MetricStatus.FLAG and m.status_text == "Above target — for review"
    assert m.value == "152/94" and m.chart.kind == "dual"
    ok = pd.Series([124.0] * 21, index=days)
    assert REGISTRY["C4"](make_ctx(20, series={str(M.BLOOD_PRESSURE_SYSTOLIC): ok})).status is MetricStatus.OK


def test_c5_symptom_burden_rising():
    pain = {d: 2.0 + 0.5 * (d - 7) for d in range(7, 21)}
    m = REGISTRY["C5"](make_ctx(20, pain=_symptom_frame(pain)))
    assert m.status is MetricStatus.FLAG and m.status_text == "Symptom burden rising"
    easing = {d: 8.0 - 0.3 * (d - 7) for d in range(7, 21)}
    assert REGISTRY["C5"](make_ctx(20, pain=_symptom_frame(easing))).status_text == "Symptom burden easing"
    assert REGISTRY["C5"](make_ctx(20)).status is MetricStatus.NODATA


def test_c6_sedentary_burden_from_hourly_buckets_and_from_daily_steps():
    rows = [{"day": d, "hour": h, "value": 300.0 if h in (9, 18) else 0.0}
            for d in range(14, 21) for h in range(24)]
    m = REGISTRY["C6"](make_ctx(20, intraday={str(M.STEPS): pd.DataFrame(rows)}))
    assert m.status is MetricStatus.FLAG and m.unit == "sedentary h/day"
    steps = pd.Series([400.0] * 21, index=list(range(0, 21)))
    m = REGISTRY["C6"](make_ctx(20, pathway="general_recovery", series={str(M.STEPS): steps}))
    assert m.status is MetricStatus.FLAG and m.status_text == "Mostly inactive days"


def test_every_payload_is_plain_json():
    import json

    bundle = compute_care_metrics(_healthy_ctx())
    json.dumps(bundle)  # numpy scalars / NaN would raise
    for metric in bundle["metrics"]:
        assert set(metric) >= {"id", "key", "name", "family", "status", "status_text", "value",
                               "value_num", "unit", "finding", "confidence", "chart", "method",
                               "inputs", "unlock", "feeds_from_tasks", "drivers", "applicable",
                               "domains"}
        if metric["chart"]:
            assert len(metric["chart"]["series"]) <= 60


# --- the seeded roster ------------------------------------------------------------------


def _care(db, patient_id: str) -> dict:
    from app.engine.pipeline import latest_assessment

    return latest_assessment(db, patient_id).analytics["care_metrics"]


def _by_id(care: dict) -> dict[str, dict]:
    return {m["id"]: m for m in care["metrics"]}


@pytest.mark.parametrize("patient_id", ["linda", "robert", "sofia", "aisha", "priya", "grace",
                                        "david", "james", "elena", "steve"])
def test_seeded_roster_bundle_shape_and_guardrails(db, patient_id):
    care = _care(db, patient_id)
    assert care["version"] == "care-1"
    assert len(care["headline"]) == 3 and len(set(care["headline"])) == 3
    assert [m["id"] for m in care["metrics"]] == ALL_IDS
    for metric in care["metrics"]:
        _assert_clean(metric)


def test_linda_night_disruption_is_a_finding(db):
    m = _by_id(_care(db, "linda"))["M9"]
    assert m["status"] in ("flag", "watch")
    assert _care(db, "linda")["headline"][0] == "M9"


def test_aisha_pain_cost_climbs_and_stairs_plateau(db):
    by_id = _by_id(_care(db, "aisha"))
    assert STATUS_RANK[MetricStatus(by_id["M2"]["status"])] >= STATUS_RANK[MetricStatus.WATCH]
    assert by_id["M8"]["status"] == "watch" and "plateau" in by_id["M8"]["status_text"].lower()
    assert by_id["M3"]["status"] == "flag"  # the same limp the risk tier flags
    assert by_id["M18"]["status"] == "watch" and "Plateau" in by_id["M18"]["status_text"]


def test_robert_walk_metrics_say_what_would_unlock_them(db):
    by_id = _by_id(_care(db, "robert"))
    for mid in ("M4", "M5"):
        assert by_id[mid]["status"] == "nodata"
        assert "guided walk" in by_id[mid]["unlock"]


def test_priya_cannot_be_seen_but_her_scale_and_cuff_report(db):
    by_id = _by_id(_care(db, "priya"))
    assert by_id["M16"]["status"] == "flag"
    assert by_id["C1"]["status"] == "ok" and by_id["C4"]["status"] == "ok"
    assert by_id["C1"]["applicable"] is False  # computed, but not this pathway's metric
    assert "M16" in _care(db, "priya")["headline"]


def test_input_hash_moves_with_checkins_and_tasks(db):
    from app.engine.pipeline import compute_input_hash
    from app.models.checkin import Checkin

    before = compute_input_hash(db, "grace")
    checkin = Checkin(patient_id="grace", occurred_at=datetime.now(), channel="app")
    db.add(checkin)
    db.commit()
    try:
        assert compute_input_hash(db, "grace") != before
    finally:
        db.delete(checkin)
        db.commit()
    assert compute_input_hash(db, "grace") == before


# --- API -----------------------------------------------------------------------------------


def test_care_metrics_endpoint_shape(client):
    body = client.get("/api/patients/aisha/care-metrics").json()
    assert set(body) == {"version", "pathway", "headline", "metrics", "families", "computed_at"}
    assert body["pathway"] == {"key": "ortho_tha", "name": "Total hip replacement recovery",
                               "domain": "ortho"}
    assert len(body["metrics"]) == 24 and len(body["headline"]) == 3
    assert [f["key"] for f in body["families"]] == [key for key, _, _ in FAMILIES]
    assert client.get("/api/patients/ghost/care-metrics").status_code == 404


def test_raw_data_endpoint_groups_by_metric_type(client):
    body = client.get("/api/patients/aisha/raw-data?days=7").json()
    assert body["days"] == 7 and body["checkins_count"] >= 1 and body["tasks_count"] >= 1
    types = {m["metric_type"]: m for m in body["metric_types"]}
    assert "steps" in types and "hr_sample" in types and "pain_nrs" in types
    steps = body["rows"]["steps"]
    assert len(steps) <= 400 and steps[0]["date"] >= steps[-1]["date"]
    assert {"date", "start_time", "value", "unit", "source", "granularity", "patient_reported",
            "json"} <= set(steps[0])
    assert types["steps"]["count"] == len(steps) or types["steps"]["truncated"]
    assert client.get("/api/patients/aisha/raw-data?days=0").status_code == 422
