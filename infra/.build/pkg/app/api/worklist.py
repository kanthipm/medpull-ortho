from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.checkin import Checkin
from app.models.enums import InsightKind, RiskLevel
from app.models.patient import Patient

router = APIRouter(tags=["worklist"])

TIER_ORDER = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.MISSING_DATA: 2, RiskLevel.LOW: 3}


def ensure_fresh_assessment(db: Session, patient_id: str):
    """Lazy staleness check: recompute only when observations changed."""
    from app.engine.pipeline import compute_input_hash, latest_assessment, run_patient

    current = latest_assessment(db, patient_id)
    if current is None or current.input_hash != compute_input_hash(db, patient_id):
        return run_patient(db, patient_id)
    return current


@router.get("/worklist")
def worklist(db: Session = Depends(get_db)) -> dict:
    from app.llm.insights import get_daily_briefing, get_patient_insight
    from app.models.rtm import EnrollmentStatus, MonitoringWindow
    from app.rtm.coverage import QUALIFY_DAYS

    patients = db.scalars(select(Patient)).all()
    enrolled_ids = set(
        db.scalars(
            select(EnrollmentStatus.patient_id).where(EnrollmentStatus.complete.is_(True))
        )
    )

    last_checkins = dict(
        db.execute(
            select(Checkin.patient_id, func.max(Checkin.occurred_at)).group_by(Checkin.patient_id)
        ).all()
    )
    # latest monitoring window per patient, one query
    monitoring: dict[str, int] = {}
    for window in db.scalars(
        select(MonitoringWindow).order_by(MonitoringWindow.window_end, MonitoringWindow.id)
    ):
        monitoring[window.patient_id] = window.days_with_data

    rows = []
    stats = {"total": len(patients), "high": 0, "medium": 0, "missing": 0, "low": 0}
    for patient in patients:
        assessment = ensure_fresh_assessment(db, patient.id)
        reason = get_patient_insight(db, InsightKind.WORKLIST_REASON, patient.id)
        analytics = assessment.analytics
        level = RiskLevel(assessment.risk_level)
        stats_key = "missing" if level == RiskLevel.MISSING_DATA else str(level)
        stats[stats_key] += 1
        rows.append(
            {
                "id": patient.id,
                "name": patient.name,
                "initials": patient.initials,
                "priority": level,
                "risk_score": assessment.risk_score,
                "reason": reason.content.get("reason", ""),
                "procedure_display": patient.procedure_display,
                "postop_day": analytics.get("postop_day"),
                "days_since_discharge": (datetime.now().date() - patient.discharge_date).days,
                "last_checkin_at": last_checkins.get(patient.id),
                "assigned_provider": {
                    "name": patient.assigned_provider.name,
                    "role": str(patient.assigned_provider.role),
                },
                "data_confidence": {
                    "score": analytics["confidence"]["score"],
                    "level": analytics["confidence"]["level"],
                },
                "trajectory": {
                    "state": analytics["trajectory"]["state"],
                    "pct": analytics["trajectory"]["pct"],
                },
                "rtm": {
                    "days": monitoring.get(patient.id, 0),
                    "target": QUALIFY_DAYS,
                    "eligible": monitoring.get(patient.id, 0) >= QUALIFY_DAYS,
                    "enrolled": patient.id in enrolled_ids,
                },
            }
        )

    rows.sort(key=lambda r: (TIER_ORDER[r["priority"]], -r["risk_score"]))
    for row in rows:
        row.pop("risk_score")

    briefing = get_daily_briefing(db)
    return {
        "as_of": datetime.now().isoformat(),
        "stats": stats,
        "briefing": {
            "text": briefing.content.get("briefing", ""),
            "generated_at": briefing.generated_at.isoformat(),
            "provider": briefing.llm_provider,
        },
        "patients": rows,
    }
