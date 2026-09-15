"""Headline selection: the three tiles shown above Full stats.

The pathway carries the priority order (see pathways.py for the rationale
per pathway). The first three metrics in that order that actually computed
lead; when fewer than three did, the list is completed with the highest-
priority NODATA ones so the tiles still say what would unlock them. A
FLAG on data confidence (M16) always takes a slot — it gates the rest.
"""

from __future__ import annotations

from typing import Any

from app.engine.care.pathways import Pathway
from app.engine.care.types import CareMetric
from app.models.enums import MetricStatus

HEADLINE_SIZE = 3


def _status(metric: CareMetric | dict[str, Any]) -> str:
    if isinstance(metric, dict):
        return str(metric.get("status", ""))
    return str(metric.status)


def _id(metric: CareMetric | dict[str, Any]) -> str:
    return metric["id"] if isinstance(metric, dict) else metric.id


def select_headline(pathway: Pathway, metrics: list[CareMetric] | list[dict[str, Any]]) -> list[str]:
    by_id = {_id(m): m for m in metrics}
    order = [i for i in pathway.headline if i in by_id]
    live = [i for i in order if _status(by_id[i]) != str(MetricStatus.NODATA)]
    dark = [i for i in order if _status(by_id[i]) == str(MetricStatus.NODATA)]
    chosen = (live + dark)[:HEADLINE_SIZE]
    # Data confidence gates every other tile: when it says the patient cannot
    # be seen, that is the headline whatever the pathway's order says.
    gate = by_id.get("M16")
    if gate is not None and _status(gate) == str(MetricStatus.FLAG) and "M16" not in chosen:
        chosen = chosen[: HEADLINE_SIZE - 1] + ["M16"]
    return chosen
