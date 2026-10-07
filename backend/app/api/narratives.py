"""Narrative warming: the one place a page is allowed to spend model calls.

The worklist and the patient page answer every read from the cache or the
deterministic renderer and never block on Groq. When their response says
``narratives_pending > 0`` the console calls ``POST /api/narratives/warm``
in the background; this endpoint spends a bounded number of model calls
(highest tier first, the asked-for patient first), persists what it wrote,
and reports what is still missing so the console can call again or stop.

On a laptop the same work also runs on a timer (app/main.py), so the warm
call usually finds nothing to do; on Lambda, where no timer runs, it is
what fills the caches after the day rolls over.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.llm.insights import (
    briefing_is_cached,
    get_daily_briefing,
    get_patient_insight,
    insight_is_cached,
)
from app.models.enums import InsightKind, RiskLevel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/narratives", tags=["narratives"])

# Model calls one warm request may make. Four is three worklist reasons and
# the briefing, or a patient's summary and actions with two reasons to spare
# — enough to turn one screen from rules-based to AI in a single call, and
# small enough to stay well inside the 30 s edge timeout at the model's
# 15 s deadline when the first call is slow.
LLM_BUDGET = 4
# Wall-clock cap per request, so a slow provider ends the pass early rather
# than the edge ending the request mid-write.
TIME_BUDGET_S = 20.0
TIER_ORDER = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.MISSING_DATA: 2, RiskLevel.LOW: 3}

PATIENT_KINDS = (InsightKind.PATIENT_SUMMARY, InsightKind.SUGGESTED_ACTIONS)


class WarmBody(BaseModel):
    # The patient whose page is open: their summary and actions go first.
    patient_id: str | None = None
    # Also fill worklist reasons and the briefing (the worklist is open).
    worklist: bool = True
    budget: int = Field(default=LLM_BUDGET, ge=1, le=LLM_BUDGET)


def _todo(db: Session, body: WarmBody) -> list[tuple[InsightKind, str | None]]:
    """Every narrative on the asked-for screens that the model has not
    written yet, most valuable first."""
    from app.engine.pipeline import latest_assessment
    from app.personal.scope import clinic_patients

    todo: list[tuple[InsightKind, str | None]] = []
    if body.patient_id:
        for kind in PATIENT_KINDS:
            if not insight_is_cached(db, kind, body.patient_id):
                todo.append((kind, body.patient_id))
    if body.worklist:
        ranked = []
        for patient in clinic_patients(db):
            assessment = latest_assessment(db, patient.id)
            if assessment is None:
                continue
            tier = TIER_ORDER.get(RiskLevel(assessment.risk_level), 9)
            if not insight_is_cached(db, InsightKind.WORKLIST_REASON, patient.id):
                ranked.append((tier, patient.id))
        ranked.sort()
        todo.extend((InsightKind.WORKLIST_REASON, pid) for _, pid in ranked)
        if not briefing_is_cached(db):
            todo.append((InsightKind.DAILY_BRIEFING, None))
    return todo


@router.post("/warm")
def warm(body: WarmBody, db: Session = Depends(get_db)) -> dict:
    started = time.monotonic()
    todo = _todo(db, body)
    generated: list[dict] = []
    spent = 0
    for kind, patient_id in todo:
        if spent >= body.budget or time.monotonic() - started > TIME_BUDGET_S:
            break
        try:
            if kind == InsightKind.DAILY_BRIEFING:
                row = get_daily_briefing(db)
            else:
                row = get_patient_insight(db, kind, patient_id)
        except Exception:  # noqa: BLE001 — one narrative, not the pass
            logger.exception("warm: %s for %s failed", kind, patient_id)
            continue
        # A call that fell back (provider outage, rate limit) still counts
        # against the budget: the next one would pay the same wait.
        spent += 1
        generated.append({"kind": str(kind), "patient_id": patient_id, "provider": row.llm_provider})
    remaining = len(_todo(db, body))
    return {
        "generated": generated,
        "spent": spent,
        "pending": remaining,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "as_of": datetime.now().isoformat(),
    }


def warm_everything() -> int:
    """The laptop warmer's pass: every assessment current, every narrative
    written. Returns how many model calls it made. Opens its own session."""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.engine.pipeline import run_all
    from app.models.patient import Patient

    calls = 0
    db = SessionLocal()
    try:
        run_all(db)
        for pid in db.scalars(select(Patient.id)).all():
            for kind in (InsightKind.WORKLIST_REASON, *PATIENT_KINDS):
                if not insight_is_cached(db, kind, pid):
                    get_patient_insight(db, kind, pid)
                    calls += 1
        if not briefing_is_cached(db):
            get_daily_briefing(db)
            calls += 1
    finally:
        db.close()
    return calls
