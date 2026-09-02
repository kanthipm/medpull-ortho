"""Which metric types each provider can supply.

The UI uses this to degrade gracefully per patient device — e.g. gait-quality
metrics (walking speed/asymmetry/double-support/steadiness) are measured by
iPhone/Apple Watch only; no other platform exposes them. Sources: Apple
mobility-metrics whitepaper; Health Connect data-type list; vendor API docs.
"""

from app.models.enums import MetricType as M
from app.models.enums import SourceProvider as P

CORE = [M.STEPS, M.RESTING_HR, M.HR_SAMPLE, M.SLEEP_DURATION, M.ACTIVE_ENERGY, M.CALORIES]
GAIT = [
    M.WALKING_SPEED,
    M.STEP_LENGTH,
    M.DOUBLE_SUPPORT_PCT,
    M.WALKING_ASYMMETRY_PCT,
    M.WALKING_STEADINESS,
    M.STAIR_SPEED_UP,
    M.STAIR_SPEED_DOWN,
    M.SIX_MIN_WALK,
]

CAPABILITIES: dict[P, list[M]] = {
    # Apple ships SDNN only (heartRateVariabilitySDNN) — there is no RMSSD
    # identifier, and writing SDNN into hrv_rmssd corrupts the EWMA baseline
    # the moment a patient switches platforms. Apple skin temp is a DELTA.
    P.APPLE: CORE + GAIT + [M.HRV_SDNN, M.SLEEP_STAGES, M.SPO2, M.RESPIRATORY_RATE,
                            M.SKIN_TEMP_DELTA, M.EXERCISE_SESSION],
    P.FITBIT: CORE + [M.HRV_RMSSD, M.SLEEP_STAGES, M.SPO2, M.RESPIRATORY_RATE,
                      M.SKIN_TEMP, M.EXERCISE_SESSION],
    P.GARMIN: CORE + [M.HRV_RMSSD, M.SLEEP_STAGES, M.SPO2, M.RESPIRATORY_RATE,
                      M.EXERCISE_SESSION],
    P.OURA: [M.STEPS, M.RESTING_HR, M.HRV_RMSSD, M.SLEEP_DURATION, M.SLEEP_STAGES,
             M.SPO2, M.RESPIRATORY_RATE, M.SKIN_TEMP_DELTA, M.CALORIES],
    # WHOOP exposes NO continuous-HR endpoint in the developer API (verified
    # against two OpenAPI snapshots) — cycle/workout aggregates only. Its
    # skin temperature is absolute Celsius.
    P.WHOOP: [M.RESTING_HR, M.HRV_RMSSD, M.SLEEP_DURATION, M.SLEEP_STAGES,
              M.SPO2, M.RESPIRATORY_RATE, M.SKIN_TEMP, M.CALORIES],
    P.DEXCOM: [],  # CGM — glucose metrics arrive in a later metric_type expansion
    P.WITHINGS: [M.STEPS, M.RESTING_HR, M.SLEEP_DURATION, M.SLEEP_STAGES, M.SPO2,
                 M.CALORIES],
    P.POLAR: CORE + [M.HRV_RMSSD, M.SLEEP_STAGES, M.EXERCISE_SESSION],
    P.SAMSUNG: CORE + [M.HRV_RMSSD, M.SLEEP_STAGES, M.SPO2, M.SKIN_TEMP,
                       M.EXERCISE_SESSION],
    P.MOCK: CORE + GAIT + [M.HRV_RMSSD, M.SLEEP_STAGES, M.SPO2, M.RESPIRATORY_RATE,
                           M.SKIN_TEMP, M.EXERCISE_SESSION],
    # The aggregator: the union of what connectors/junction.py actually emits
    # from Junction's activity/sleep/workout summaries and its SpO₂,
    # respiratory-rate, HRV and temperature timeseries. Which of these a given
    # patient really gets depends on the device behind the Junction account
    # (an Oura ring has no workouts, a Withings watch no HRV), which the
    # patient chart reports card by card. HR_SAMPLE is opt-in
    # (JUNCTION_INGEST_HEART_RATE_SAMPLES); gait metrics are not passed
    # through by Junction at all.
    P.JUNCTION: [M.STEPS, M.RESTING_HR, M.HRV_RMSSD, M.HRV_SDNN, M.SLEEP_DURATION,
                 M.SLEEP_STAGES, M.SPO2, M.RESPIRATORY_RATE, M.SKIN_TEMP,
                 M.SKIN_TEMP_DELTA, M.ACTIVE_ENERGY, M.CALORIES, M.EXERCISE_SESSION],
}


def provider_supports(provider: P, metric: M) -> bool:
    return metric in CAPABILITIES.get(provider, [])
