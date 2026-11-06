"""What this patient's setup can measure, and how.

Every card on the panel is one of four things for a given patient:

* ``passive``      a connected wearable or the phone's health store reports it
                   on its own;
* ``active``       only MedPull's own algorithm produces it, so the patient has
                   to run a test on the Measure tab (the guided walk, the
                   six-minute walk, the range-of-motion holds);
* ``unavailable``  nothing connected to this patient can report it, and the
                   card says what would;
* ``unknown``      nothing is connected yet, so no claim is made either way.

Declared from the capability map and the patient's connections rather than
learned from what has arrived, so a card can say "not available on this
setup" on day one instead of "not measured yet" forever. The confidence gate
(engine/confidence.py) deliberately keeps judging a patient on what their
sources have actually reported, because a capability list over-claims for
some brands and a patient must not be marked down for a signal that was
never going to come.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.capabilities import provider_supports
from app.engine.metrics_cards import CARD_ORDER
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider as P
from app.models.mobile import PatientSession, live_session_clause
from app.models.patient import Patient

PASSIVE, ACTIVE, UNAVAILABLE, UNKNOWN = "passive", "active", "unavailable", "unknown"

# The Measure-tab test that produces each of MedPull's own metrics.
MEASURE_TEST: dict[M, str] = {
    M.WALKING_SPEED: "the guided walk",
    M.STEP_LENGTH: "the guided walk",
    M.CADENCE: "the guided walk",
    M.WALKING_ASYMMETRY_PCT: "the guided walk",
    M.DOUBLE_SUPPORT_PCT: "the guided walk",
    M.WALKING_STEADINESS: "the guided walk",
    M.STAIR_SPEED_UP: "the guided walk, on a phone with a barometer",
    M.STAIR_SPEED_DOWN: "the guided walk, on a phone with a barometer",
    M.SIX_MIN_WALK: "the six-minute walk test",
    M.ROM_FLEXION: "the range-of-motion test",
    M.ROM_EXTENSION: "the range-of-motion test",
    M.ROM_ABDUCTION: "the range-of-motion test",
    M.EXERCISE_SESSION: "the guided walk",
}
# The stress index is derived inside the engine from whichever of these a
# wearable supplies.
STRESS_INPUTS = (M.HRV_RMSSD, M.HRV_SDNN, M.RESTING_HR, M.RESPIRATORY_RATE)

PROVIDER_NAME: dict[P, str] = {
    P.APPLE: "Apple Health", P.FITBIT: "Fitbit", P.GARMIN: "Garmin", P.OURA: "Oura",
    P.WHOOP: "WHOOP", P.WITHINGS: "Withings", P.POLAR: "Polar", P.DEXCOM: "Dexcom",
    P.SAMSUNG: "Samsung Health", P.HEALTH_CONNECT: "Health Connect",
}


def connected_providers(patient: Patient) -> set[str]:
    return {str(d.source_provider) for d in patient.devices if d.status != "revoked"}


def has_app(db: Session, patient: Patient) -> bool:
    """A live patient-app session on this chart or its paired space: the
    Measure tab is reachable, so MedPull's own metrics can be produced."""
    ids = [patient.id] + ([patient.linked_patient_id] if patient.linked_patient_id else [])
    return db.scalar(
        select(PatientSession.id)
        .where(PatientSession.patient_id.in_(ids), live_session_clause())
        .limit(1)
    ) is not None


def _would_supply(metric: M) -> list[str]:
    names = [PROVIDER_NAME[p] for p in PROVIDER_NAME if provider_supports(p, metric)]
    return names[:4]


def profile_for(metric: M, providers: set[str], app: bool) -> dict[str, Any]:
    if metric is M.STRESS_INDEX:
        feeds = [p for p in providers if any(_supports(p, m) for m in STRESS_INPUTS)]
        if feeds:
            return {"availability": PASSIVE, "sources": sorted(feeds), "note": None}
        return {"availability": UNAVAILABLE, "sources": [],
                "note": "Derived from a wearable's overnight heart rate, HRV and breathing rate; "
                        "nothing connected to this patient reports them."}
    passive = sorted(p for p in providers if _supports(p, metric))
    if passive:
        return {"availability": PASSIVE, "sources": passive, "note": None}
    if app and provider_supports(P.MEDPULL, metric) and metric in MEASURE_TEST:
        return {"availability": ACTIVE, "sources": [str(P.MEDPULL)],
                "note": f"Measured by {MEASURE_TEST[metric]} in the MedPull app."}
    would = _would_supply(metric)
    by_app = (f"{MEASURE_TEST[metric]} in the MedPull app" if metric in MEASURE_TEST else None)
    options = ([", ".join(would)] if would else []) + ([by_app] if by_app else [])
    note = "Nothing connected to this patient reports it."
    if options:
        note += " It would come from " + " or ".join(options) + "."
    return {"availability": UNAVAILABLE, "sources": [], "note": note}


def _supports(provider: str, metric: M) -> bool:
    try:
        return provider_supports(P(provider), metric)
    except ValueError:
        return False


def source_profile(db: Session, patient: Patient) -> dict[str, dict[str, Any]]:
    """metric_key -> {availability, sources, note} for every card on the panel."""
    providers = connected_providers(patient)
    app = has_app(db, patient)
    if not providers and not app:
        return {str(m): {"availability": UNKNOWN, "sources": [], "note": None}
                for m, *_ in CARD_ORDER}
    return {str(m): profile_for(m, providers, app) for m, *_ in CARD_ORDER}


__all__ = ["source_profile", "profile_for", "connected_providers", "has_app"]
