"""One read for the console's patient page.

The page used to open with eleven requests in two waves: the record, then
everything the cards under it read. On Lambda each of those is its own
invocation competing for the function's reserved concurrency with every phone
that is refreshing, so a clinician opening a chart could throttle the app in a
patient's hand. This answers the page's eight patient-scoped reads in one call
by calling the very handlers that serve them one by one, so each part is
byte-for-byte what its own route returns and the console can seed its
per-resource caches from it (frontend/src/api/queries.ts, ``usePatient``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import care, integrations, patients, plan
from app.api.auth import ConsoleScope, console_scope
from app.database import get_db
from app.plan import ensure_ready

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/{patient_id}/overview")
def patient_overview(
    patient_id: str,
    db: Session = Depends(get_db),
    scope: ConsoleScope = Depends(console_scope),
) -> dict:
    # The plan routes' own dependency: the task and message libraries must
    # exist before the plan and the next steps read them.
    ensure_ready(db)
    # The record first: an id this console cannot see is a 404 before any
    # other work is done. Every part below applies the same scope.
    detail = patients.patient_detail(patient_id, db, scope)
    return {
        "detail": detail,
        "care_metrics": care.care_metrics(patient_id, db, scope),
        "next_steps": plan.next_steps(patient_id, db, scope),
        "plan": plan.get_plan(patient_id, db, scope),
        "checkins": patients.patient_checkins(patient_id, db, scope),
        "timeline": patients.patient_timeline(patient_id, db, scope),
        "messages": patients.list_messages(patient_id, db, scope),
        "wearables": integrations.patient_wearables(patient_id, db, scope),
    }
