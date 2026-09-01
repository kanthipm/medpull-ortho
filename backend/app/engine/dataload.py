"""Load a patient's observations into per-metric daily series."""

from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import MetricType
from app.models.observation import Observation


def load_daily_series(db: Session, patient_id: str, surgery_date: date) -> dict[str, pd.Series]:
    """metric_type -> Series of daily values indexed by post-op day (int).

    Negative index = pre-op. Multiple rows per day are averaged (steps arrive
    as one daily summary per provider, so mean is safe across the board).

    The day axis is the materialized ``local_date`` — the same column the RTM
    day counter reads (``rtm/coverage.py``). Deriving a second day from
    ``start_time`` would put a West Coast patient's evening on the next day for
    the engine and on the correct one for billing, so a patient's post-op day 7
    and their 7th monitored day would silently be different days.

    Tombstoned rows are excluded: a provider deletion must not keep driving
    baselines, z-scores, trajectory or the charts read off this series.
    """
    rows = db.execute(
        select(Observation.metric_type, Observation.local_date, Observation.value_num)
        .where(
            Observation.patient_id == patient_id,
            Observation.value_num.is_not(None),
            Observation.deleted_at.is_(None),
        )
        .order_by(Observation.local_date)
    ).all()
    if not rows:
        return {}

    df = pd.DataFrame(rows, columns=["metric_type", "local_date", "value"])
    df["day"] = df["local_date"].map(lambda d: (d - surgery_date).days)

    out: dict[str, pd.Series] = {}
    for metric, group in df.groupby("metric_type"):
        series = group.groupby("day")["value"].mean().sort_index()
        out[str(MetricType(metric))] = series
    return out
