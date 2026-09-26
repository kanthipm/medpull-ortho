import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.llm.prose import humanize_codes
from app.models.checkin import Checkin
from app.models.enums import InsightKind, RiskLevel
from app.models.library import TaskTemplate
from app.models.patient import Patient
from app.notifications import sendblue
from app.plan import ensure_ready

logger = logging.getLogger(__name__)
router = APIRouter(tags=["worklist"])

TIER_ORDER = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.MISSING_DATA: 2, RiskLevel.LOW: 3}

# How many patients on one worklist request may reach the model for their
# one-line reason. A cold cache misses for every patient at once (an engine or
# prompt version bump does that), and a dozen sequential Groq calls behind a
# 30 s edge timeout is a worklist that times out rather than one that is slow.
# The rest are served the deterministic line, keyed as such, so a later read
# fills the real key. Highest tier first: that is where the words matter.
LLM_BUDGET = 4


def ensure_fresh_assessment(db: Session, patient_id: str):
    """Lazy staleness check: recompute only when observations changed.

    One definition, in the engine, so the practice strip cannot drift from the
    worklist it sits above."""
    from app.engine.pipeline import ensure_current

    return ensure_current(db, patient_id)


@router.get("/worklist")
def worklist(db: Session = Depends(get_db)) -> dict:
    from app.llm.insights import get_daily_briefing, get_patient_insight
    from app.plan.next_steps import next_step_summary

    from app.personal.scope import clinic_patients

    # Clinic charts only: a personal subscriber is never on a worklist.
    patients = clinic_patients(db)
    # The next-step planner names the library tasks a step would assign, so
    # the library is read once here rather than once per row.
    ensure_ready(db)
    templates = db.scalars(select(TaskTemplate).order_by(TaskTemplate.id)).all()

    last_checkins = dict(
        db.execute(
            select(Checkin.patient_id, func.max(Checkin.occurred_at)).group_by(Checkin.patient_id)
        ).all()
    )

    # Assessments first, so the tier is known before any narrative is asked
    # for: the model budget below goes to the rows a clinician reads first.
    # One patient's failure must not empty the roster — the whole point of
    # this screen is the other eleven — so a broken patient is reported as a
    # row that says so and the rest of the worklist is served.
    scored: list[tuple[Patient, object | None]] = []
    broken: list[Patient] = []
    for patient in patients:
        try:
            scored.append((patient, ensure_fresh_assessment(db, patient.id)))
        except Exception:  # noqa: BLE001 — one patient, not the roster
            logger.exception("worklist: assessment failed for %s", patient.id)
            broken.append(patient)
    scored.sort(key=lambda pair: TIER_ORDER.get(RiskLevel(pair[1].risk_level), 9))

    rows = []
    stats = {"total": len(patients), "high": 0, "medium": 0, "missing": 0, "low": 0}
    llm_spent = 0
    for patient, assessment in scored:
        analytics = assessment.analytics
        level = RiskLevel(assessment.risk_level)
        stats_key = "missing" if level == RiskLevel.MISSING_DATA else str(level)
        stats[stats_key] += 1
        try:
            reason = get_patient_insight(
                db, InsightKind.WORKLIST_REASON, patient.id, allow_llm=llm_spent < LLM_BUDGET,
            )
            if reason.llm_provider != "fallback":
                llm_spent += 1
            # The model sometimes echoes a tier code ("risk missing_data").
            reason_text = humanize_codes(reason.content.get("reason", ""))
        except Exception:  # noqa: BLE001 — a narrative is not worth a 500
            logger.exception("worklist: reason failed for %s", patient.id)
            reason_text = ""
        # Rules over the stored assessment plus a few counts — no LLM, no
        # recompute — so the row can carry its top recommended step.
        try:
            next_step, next_steps_open = next_step_summary(
                db, patient, assessment, last_checkin_at=last_checkins.get(patient.id),
                templates=templates,
            )
        except Exception:  # noqa: BLE001
            logger.exception("worklist: next step failed for %s", patient.id)
            next_step, next_steps_open = None, 0
        rows.append(
            {
                "id": patient.id,
                "name": patient.name,
                "initials": patient.initials,
                "priority": level,
                "risk_score": assessment.risk_score,
                "reason": reason_text,
                "procedure_display": patient.procedure_display,
                "mode": "general" if str(patient.procedure_type) == "NONE" else "recovery",
                "postop_day": analytics.get("postop_day"),
                # Whether a text can actually reach them. The row's step used
                # to be the only hint, so a check-in step for a patient with a
                # phone was labelled "Open check-in link" purely because that
                # step carries no tel of its own.
                "can_text": bool(patient.phone) and sendblue.configured(),
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
                "next_step": next_step,
                "next_steps_open": next_steps_open,
            }
        )

    # A patient the engine could not score still belongs on the screen: a
    # silently missing row reads as "nothing to do here".
    for patient in broken:
        stats["missing"] += 1
        rows.append(
            {
                "id": patient.id,
                "name": patient.name,
                "initials": patient.initials,
                "priority": RiskLevel.MISSING_DATA,
                "risk_score": -1,
                "reason": "Analysis unavailable — open the patient to retry",
                "procedure_display": patient.procedure_display,
                "mode": "general" if str(patient.procedure_type) == "NONE" else "recovery",
                "postop_day": None,
                "can_text": bool(patient.phone) and sendblue.configured(),
                "days_since_discharge": (datetime.now().date() - patient.discharge_date).days,
                "last_checkin_at": last_checkins.get(patient.id),
                "assigned_provider": {
                    "name": patient.assigned_provider.name,
                    "role": str(patient.assigned_provider.role),
                },
                "data_confidence": {"score": 0.0, "level": "low"},
                "trajectory": {"state": "unknown", "pct": None},
                "next_step": None,
                "next_steps_open": 0,
            }
        )

    rows.sort(key=lambda r: (TIER_ORDER[r["priority"]], -r["risk_score"]))
    for row in rows:
        row.pop("risk_score")

    try:
        briefing_text = ""
        briefing = get_daily_briefing(db)
        briefing_text = briefing.content.get("briefing", "")
        briefing_view = {
            "text": briefing_text,
            "generated_at": briefing.generated_at.isoformat(),
            "provider": briefing.llm_provider,
        }
    except Exception:  # noqa: BLE001 — the roster matters, the paragraph does not
        logger.exception("worklist: briefing failed")
        briefing_view = {"text": "", "generated_at": datetime.now().isoformat(),
                         "provider": "unavailable"}
    return {
        "as_of": datetime.now().isoformat(),
        "stats": stats,
        "briefing": briefing_view,
        "patients": rows,
    }
