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
    """
    rows = db.execute(
        select(Observation.metric_type, Observation.start_time, Observation.value_num)
        .where(Observation.patient_id == patient_id, Observation.value_num.is_not(None))
        .order_by(Observation.start_time)
    ).all()
    if not rows:
        return {}

    df = pd.DataFrame(rows, columns=["metric_type", "start_time", "value"])
    df["day"] = df["start_time"].map(lambda t: (t.date() - surgery_date).days)

    out: dict[str, pd.Series] = {}
    for metric, group in df.groupby("metric_type"):
        series = group.groupby("day")["value"].mean().sort_index()
        out[str(MetricType(metric))] = series
    return out
