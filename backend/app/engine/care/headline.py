"""Headline selection: the six fixed tiles above Full stats, and the
metrics brought to attention beside them.

The pathway carries the six (see pathways.py). They are the same six, in
the same order, for every patient on that pathway whatever their data looks
like: a clinician who reads two knee patients finds the load ratio in the
same rectangle on both pages, and a tile with no data yet says what it
needs and how many days are left rather than giving its slot to something
else. The engine's judgement goes in a separate list: ``select_attention``
returns the metrics OUTSIDE the six that are flagged or worth watching,
flags first, a Flag on data confidence (M16) always first, capped so the
strip stays a strip.
"""

from __future__ import annotations

from typing import Any

from app.engine.care.pathways import HEADLINE_SIZE, Pathway
from app.engine.care.types import CareMetric
from app.models.enums import MetricStatus

ATTENTION_SIZE = 3


def _status(metric: CareMetric | dict[str, Any]) -> str:
    if isinstance(metric, dict):
        return str(metric.get("status", ""))
    return str(metric.status)


def _id(metric: CareMetric | dict[str, Any]) -> str:
    return metric["id"] if isinstance(metric, dict) else metric.id


def select_headline(pathway: Pathway, metrics: list[CareMetric] | list[dict[str, Any]]) -> list[str]:
    """The pathway's six, in its order — the same for every patient on it."""
    by_id = {_id(m): m for m in metrics}
    return [i for i in pathway.headline if i in by_id][:HEADLINE_SIZE]


def select_attention(
    pathway: Pathway, metrics: list[CareMetric] | list[dict[str, Any]]
) -> list[str]:
    """Metrics outside the six that earned a look: flags first, a data-
    confidence flag ahead of everything (it qualifies every other reading on
    the page), then watches, capped at ATTENTION_SIZE."""
    headline = set(select_headline(pathway, metrics))
    flags = [_id(m) for m in metrics
             if _id(m) not in headline and _status(m) == str(MetricStatus.FLAG)]
    watches = [_id(m) for m in metrics
               if _id(m) not in headline and _status(m) == str(MetricStatus.WATCH)]
    if "M16" in flags:
        flags = ["M16"] + [i for i in flags if i != "M16"]
    return (flags + watches)[:ATTENTION_SIZE]
