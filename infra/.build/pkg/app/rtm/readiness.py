"""RTM compliance engine: CMS requirements in, readiness + next action out.

Deterministic by design — billing eligibility must be explainable, so this
never touches the LLM. Rules follow the P1 spec (SPEC.md §8):

  98975  enrollment: education + consent + baseline complete (one-time)
  98985  musculoskeletal monitoring, 2–15 days in the rolling 30-day window
  98977  musculoskeletal monitoring, ≥16 days in the rolling 30-day window
  98979  first 10 min of treatment management + one live interaction
  98980  first 20 min of treatment management + one live interaction
  98981  each additional 20 min beyond the first 20

A patient is Ready to Bill when enrollment is complete, the 16-day monitoring
threshold is met, ≥20 provider minutes with a live interaction are logged this
month, and documentation is approved.
"""

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import DocumentStatus
from app.models.patient import Patient
from app.models.rtm import EnrollmentStatus, ProviderTimeLog, RtmDocument
from app.rtm.coverage import QUALIFY_DAYS, get_current

# Demo estimates of national-average reimbursement (2026 dollars) — practice
# overview only, never a billing claim.
CPT_RATES = {
    "98975": 20.0,
    "98985": 44.0,
    "98977": 44.0,
    "98979": 25.0,
    "98980": 50.0,
    "98981": 40.0,
}

MONITORING_MIN_DAYS = 2  # 98985 floor


def _month_key(today: date) -> str:
    return f"{today.year:04d}-{today.month:02d}"


def _minutes_in_window(db: Session, patient_id: str, today: date) -> tuple[int, bool]:
    """Provider time over the rolling 30-day window (mirrors coverage.py —
    calendar-month aggregation is flaky near month boundaries)."""
    from datetime import datetime, time, timedelta

    since = datetime.combine(today - timedelta(days=29), time.min)
    seconds = db.scalar(
        select(func.coalesce(func.sum(ProviderTimeLog.seconds), 0)).where(
            ProviderTimeLog.patient_id == patient_id,
            ProviderTimeLog.occurred_at >= since,
        )
    ) or 0
    interactive = db.scalar(
        select(func.count(ProviderTimeLog.id)).where(
            ProviderTimeLog.patient_id == patient_id,
            ProviderTimeLog.occurred_at >= since,
            ProviderTimeLog.interactive.is_(True),
        )
    ) or 0
    return int(seconds // 60), interactive > 0


def _documentation_ready(db: Session, patient_id: str, month: str) -> bool:
    approved = db.scalar(
        select(func.count(RtmDocument.id)).where(
            RtmDocument.patient_id == patient_id,
            RtmDocument.month == month,
            RtmDocument.status == DocumentStatus.APPROVED,
        )
    ) or 0
    return approved > 0


def compute_readiness(db: Session, patient: Patient, today: date | None = None) -> dict[str, Any]:
    """The RTM Readiness Card, as data."""
    today = today or date.today()
    month = _month_key(today)

    enrollment = db.get(EnrollmentStatus, patient.id)
    window = get_current(db, patient.id)
    monitoring_days = window.days_with_data if window else 0
    minutes, interactive = _minutes_in_window(db, patient.id, today)
    documentation_ready = _documentation_ready(db, patient.id, month)

    enrollment_state = {
        "education_complete": bool(enrollment and enrollment.education_complete),
        "consent_complete": bool(enrollment and enrollment.consent_complete),
        "baseline_complete": bool(enrollment and enrollment.baseline_complete),
        "complete": bool(enrollment and enrollment.complete),
        "pathway": enrollment.pathway if enrollment else None,
    }

    eligibility: list[dict[str, Any]] = []

    def code(cpt: str, eligible: bool, note: str = "", units: int = 1) -> None:
        eligibility.append({"cpt": cpt, "eligible": eligible, "note": note, "units": units})

    code(
        "98975",
        enrollment_state["complete"],
        "" if enrollment_state["complete"] else "Enrollment incomplete",
    )
    if not enrollment_state["complete"]:
        code("98985", False, "Monitoring starts after enrollment")
    elif monitoring_days >= QUALIFY_DAYS:
        code("98977", True, f"{monitoring_days} monitoring days")
    elif monitoring_days >= MONITORING_MIN_DAYS:
        code(
            "98985",
            True,
            f"{monitoring_days} monitoring days ({QUALIFY_DAYS - monitoring_days} to 98977)",
        )
    else:
        code("98985", False, f"{monitoring_days} monitoring days — needs {MONITORING_MIN_DAYS}")

    if minutes >= 20 and interactive:
        code("98980", True, f"{minutes} min logged")
        extra_units = (minutes - 20) // 20
        if extra_units > 0:
            code("98981", True, f"{extra_units} × additional 20 min", units=extra_units)
    elif minutes >= 10 and interactive:
        code("98979", True, f"{minutes} min logged")
        code("98980", False, f"{20 - minutes} minutes remaining")
    else:
        missing = []
        if minutes < 20:
            missing.append(f"{20 - minutes} minutes remaining")
        if not interactive:
            missing.append("live interaction required")
        code("98980", False, ", ".join(missing))

    ready_to_bill = (
        enrollment_state["complete"]
        and monitoring_days >= QUALIFY_DAYS
        and minutes >= 20
        and interactive
        and documentation_ready
    )

    return {
        "month": month,
        "enrollment": enrollment_state,
        "monitoring": {
            "days": monitoring_days,
            "target": QUALIFY_DAYS,
            "window_days": 30,
            "eligible": monitoring_days >= QUALIFY_DAYS,
            "enrolled": enrollment_state["complete"],
        },
        "treatment_management": {
            "minutes": minutes,
            "interactive_communication": interactive,
        },
        "documentation_ready": documentation_ready,
        "billing": eligibility,
        "ready_to_bill": ready_to_bill,
        "suggested_action": _suggested_action(
            enrollment_state, monitoring_days, minutes, interactive, documentation_ready
        ),
        "estimated_value": round(
            sum(
                CPT_RATES.get(e["cpt"], 0.0) * e["units"]
                for e in eligibility
                if e["eligible"]
            ),
            2,
        ),
    }


def _suggested_action(
    enrollment: dict[str, Any],
    monitoring_days: int,
    minutes: int,
    interactive: bool,
    documentation_ready: bool,
) -> str:
    """Provider-actionable steps first; passive accrual (monitoring days
    arrive on their own as the patient wears the device) is only suggested
    when nothing else is left to do."""
    if not enrollment["consent_complete"]:
        return "Complete consent during the next check-in."
    if not enrollment["baseline_complete"]:
        return "Capture the pain and mobility baseline."
    if not enrollment["complete"]:
        return "Finish RTM education to complete enrollment."
    if not interactive:
        return "Call the patient to complete RTM requirements."
    if minutes < 20:
        return f"Log {20 - minutes} more review minutes to reach 98980."
    if not documentation_ready:
        return "Review and approve this month's documentation."
    if monitoring_days < QUALIFY_DAYS:
        return (
            f"On track — {QUALIFY_DAYS - monitoring_days} more monitoring days "
            "accrue this window."
        )
    return "All RTM requirements met — ready to bill."


def practice_overview(db: Session, today: date | None = None) -> dict[str, Any]:
    """The lightweight practice strip (SPEC.md §9) — five numbers, no dashboard."""
    from app.engine.pipeline import latest_assessment

    today = today or date.today()
    patients = db.scalars(select(Patient).order_by(Patient.id)).all()

    needs_review = 0
    ready = 0
    revenue = 0.0
    adherence_rates: list[float] = []
    for patient in patients:
        assessment = latest_assessment(db, patient.id)
        # matches the worklist's "needs review" language, which counts the
        # high tier only — the strip and the headline must agree
        if assessment is not None and assessment.risk_level == "high":
            needs_review += 1
        if assessment is not None:
            rate = assessment.analytics.get("adherence", {}).get("rate")
            if rate is not None:
                adherence_rates.append(float(rate))
        readiness = compute_readiness(db, patient, today)
        if readiness["ready_to_bill"]:
            ready += 1
        revenue += readiness["estimated_value"]

    return {
        "rtm_patients": len(patients),
        "needs_review": needs_review,
        "ready_to_bill": ready,
        "therapy_adherence_pct": round(100 * sum(adherence_rates) / len(adherence_rates))
        if adherence_rates
        else None,
        "estimated_revenue": round(revenue, 2),
    }
