"""Load a patient's observations into per-metric daily series."""

from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Granularity, MetricType, SourceProvider
from app.models.observation import Observation

# Metrics whose intraday rows are parts of a daily total rather than repeated
# measurements of one quantity. A day's value is the mean of its DAILY_SUMMARY
# rows when any exist (a Junction summary, the seed) and otherwise the SUM of
# its INTERVAL/INSTANT/SESSION rows (hourly step buckets from the patient app,
# workouts). Averaging an hourly bucket into a daily summary would have read a
# 6,000-step day as ~250 steps the moment the first bucket arrived.
ADDITIVE = {
    str(MetricType.STEPS),
    str(MetricType.ACTIVE_ENERGY),
    str(MetricType.CALORIES),
    str(MetricType.FLIGHTS_CLIMBED),
    str(MetricType.SIT_TO_STAND),
    str(MetricType.EXERCISE_SESSION),
}

_SUMMARY = str(Granularity.DAILY_SUMMARY)

# One source per metric and day. A patient can be reached more than one way
# for the same measurement: MedPull's own gait algorithm and Apple's walking
# metrics on an iPhone, or a Fitbit's sleep through Junction's cloud and again
# through Health Connect on an Android phone. The day's value comes from the
# best-ranked source that reported that day; the other rows stay in the raw
# data for comparison and never enter the series. Days the preferred source
# did not cover fall back down the list.
#
# The rank, lowest wins:
#   0  MedPull's own rows (engine/mobility): one algorithm for every phone.
#   1  A brand's cloud connector: the device maker's own numbers, delivered
#      whether or not the phone is on.
#   2  The phone's health store (Apple Health, Health Connect): the same
#      numbers relayed by the phone, or the phone's own sensors. Samsung
#      wearables have no cloud path, so for them this tier is the only one.
#   3  What a person or clinician typed.
# Unknown providers rank with the cloud brands.
_RANK: dict[str, int] = {
    str(SourceProvider.MEDPULL): 0,
    str(SourceProvider.APPLE): 2,
    str(SourceProvider.HEALTH_CONNECT): 2,
    str(SourceProvider.SAMSUNG): 2,
    str(SourceProvider.PATIENT_REPORTED): 3,
    str(SourceProvider.CLINICIAN_ENTERED): 3,
}
_DEFAULT_RANK = 1


def source_rank(provider: str) -> int:
    return _RANK.get(str(provider), _DEFAULT_RANK)


def load_daily_series(db: Session, patient_id: str, surgery_date: date) -> dict[str, pd.Series]:
    """metric_type -> Series of daily values indexed by post-op day (int).

    Negative index = pre-op. Multiple rows per day are averaged, except for the
    ADDITIVE metrics above, where intraday rows are summed unless the day also
    carries a daily summary (which then stands alone: the summary and the
    buckets describe the same steps, and a Junction summary is the provider's
    own total).

    The day axis is the materialized ``local_date``. Deriving a second day
    from ``start_time`` would put a West Coast patient's evening on the next
    day, so a patient's post-op day 7
    and their 7th monitored day would silently be different days.

    Tombstoned rows are excluded: a provider deletion must not keep driving
    baselines, z-scores, trajectory or the charts read off this series.
    """
    rows = db.execute(
        select(
            Observation.metric_type,
            Observation.local_date,
            Observation.value_num,
            Observation.granularity,
            Observation.source_provider,
        )
        .where(
            Observation.patient_id == patient_id,
            Observation.value_num.is_not(None),
            Observation.deleted_at.is_(None),
        )
        .order_by(Observation.local_date)
    ).all()
    if not rows:
        return {}

    df = pd.DataFrame(
        rows, columns=["metric_type", "local_date", "value", "granularity", "source_provider"]
    )
    df["day"] = df["local_date"].map(lambda d: (d - surgery_date).days)
    df["metric_type"] = df["metric_type"].map(str)
    df["granularity"] = df["granularity"].map(str)
    # Pick the source before anything is averaged or summed: two sources'
    # step rows added together would walk the patient twice as far.
    df["rank"] = df["source_provider"].map(source_rank)
    best = df.groupby(["metric_type", "day"])["rank"].transform("min")
    df = df[df["rank"] == best]

    out: dict[str, pd.Series] = {}
    for metric, group in df.groupby("metric_type"):
        if metric in ADDITIVE:
            series = _additive_daily(group)
        else:
            series = group.groupby("day")["value"].mean().sort_index()
        out[str(MetricType(metric))] = series.astype(float)
    return out


def _additive_daily(group: pd.DataFrame) -> pd.Series:
    summaries = group[group["granularity"] == _SUMMARY]
    parts = group[group["granularity"] != _SUMMARY]
    by_summary = summaries.groupby("day")["value"].mean()
    by_parts = parts.groupby("day")["value"].sum()
    # A day with a summary keeps the summary alone — the buckets are the same
    # steps counted again, not more of them.
    by_parts = by_parts[~by_parts.index.isin(by_summary.index)]
    return pd.concat([by_summary, by_parts]).sort_index()
