"""RTM compliance engine: CMS requirements in, readiness + next action out.

Deterministic by design — billing eligibility must be explainable, so this
never touches the LLM. Rules follow the P1 spec (SPEC.md §8):

  98975  enrollment: education + consent + baseline complete, billed once
  98985  musculoskeletal monitoring, 2–15 days in the rolling 30-day window
  98977  musculoskeletal monitoring, ≥16 days in the rolling 30-day window
  98979  first 10 min of treatment management + one live interaction
  98980  first 20 min of treatment management + one live interaction
  98981  each additional 20 min beyond the first 20

Every gate on this card measures the SAME rolling 30-day window that
coverage.py counts monitoring days over. Calendar months are only ever a
label here: a month-scoped gate next to a rolling one makes a patient lose
their documentation credit at midnight on the 1st while keeping their
minutes, and Ready to Bill flips false for no clinical reason.

98977 needs no upper bound: coverage.update_window counts distinct dates
inside a 30-day window that ends today, so monitoring days can never exceed
30 and ">= 16" is exactly the spec's "16–30".

Every gate is also floored at the patient's ENROLLMENT (see billing_floor):
minutes and documentation that predate it are real work, but not work done
under an RTM plan that existed at the time.

Known limitation, stated so it is not mistaken for an oversight: 98980/98981
are defined by CPT per calendar month, and a rolling 30-day window is not the
same thing. One 25-minute session can satisfy the window on the 31st and again
four weeks later, so a practice that bills off this card at each month end
could claim the same minutes in two consecutive months. Closing that needs a
record of what has actually been claimed — a claim ledger — because a card
computed from scratch on every request has no way to know. Neither a
calendar-month gate nor a 30-day episode anchored on enrollment is a
substitute: both reintroduce the cliff this window exists to remove, where a
patient loses Ready to Bill at midnight while their minutes carry over. Until
a claim is something the product records, the card reports the window it
measured (`treatment_management.counted_from` / `counted_to`) so the same
accrual can be recognised as the same accrual.

A patient is Ready to Bill when enrollment is complete, the 16-day monitoring
threshold is met, ≥20 provider minutes with a live interaction are logged in
the window, and documentation is approved.
"""

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import DocumentStatus
from app.models.patient import Patient
from app.models.rtm import EnrollmentStatus, ProviderTimeLog, RtmDocument
from app.rtm.coverage import QUALIFY_DAYS, WINDOW_DAYS, get_current

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
    """Label for the documentation period. Never a billing gate — see the
    module docstring; every gate measures `window_floor` instead."""
    return f"{today.year:04d}-{today.month:02d}"


def window_floor(today: date) -> date:
    """First day of the rolling billing window, identical to the one
    coverage.monitoring_start clamps to. Every gate on the card moves
    together because they all start here — and llm/documentation.py measures
    the note's activity window with this same function, so a note can never
    describe a period the CPT ladder did not score."""
    return today - timedelta(days=WINDOW_DAYS - 1)


def billing_floor(today: date, enrolled_at: datetime | None) -> datetime:
    """Earliest instant that can carry billable credit for this patient.

    Two bounds, and the later one wins. The rolling window is the period being
    scored; the enrollment instant is when RTM services began. Work done
    before enrollment completed is real work, but it is not treatment
    management under an RTM plan that did not exist yet — readiness.py's own
    docstring said so while `_minutes_in_window` measured from the window
    alone, so the moment a patient enrolled, everything logged beforehand
    turned billable at once.

    That is the product's ordinary path, not a contrived state: the suggested
    action for an unenrolled patient is "Call the patient to complete RTM
    requirements", and POST /actions/call writes an interactive time log — so
    the very call that completes enrollment left 25 pre-enrollment interactive
    minutes that became $50 of 98980 one moment later.

    The instant is used rather than the date because it is known exactly and
    the enrolling call itself belongs to setup (98975), not to treatment
    management. Monitoring DAYS are clamped to the enrollment date instead
    (rtm/coverage.py) — a monitoring day is a calendar day, and that is the
    granularity that count is kept in.
    """
    floor = datetime.combine(window_floor(today), time.min)
    if enrolled_at is None:
        return floor
    return max(floor, enrolled_at)


def _minutes_in_window(
    db: Session, patient_id: str, since: datetime
) -> tuple[int, bool]:
    """Provider time over the billing window, summed from `occurred_at`.
    `ProviderTimeLog.month` is deliberately not read: a calendar-month rollup
    drops half a patient's minutes on the 1st."""
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


def _documentation_ready(db: Session, patient_id: str, since: datetime) -> bool:
    """Approved documentation inside the billing window. Scoped by the
    approval timestamp rather than `RtmDocument.month`, so the credit a
    provider earned on the 31st is still credit on the 1st — and by the same
    enrollment floor as the minutes, so a note approved before the patient was
    enrolled cannot document a period of RTM service that had not started."""
    approved = db.scalar(
        select(func.count(RtmDocument.id)).where(
            RtmDocument.patient_id == patient_id,
            RtmDocument.status == DocumentStatus.APPROVED,
            RtmDocument.approved_at >= since,
        )
    ) or 0
    return approved > 0


def compute_readiness(db: Session, patient: Patient, today: date | None = None) -> dict[str, Any]:
    """The RTM Readiness Card, as data."""
    today = today or date.today()
    month = _month_key(today)

    enrollment = db.get(EnrollmentStatus, patient.id)
    enrolled_at = enrollment.enrolled_at if enrollment else None
    enrolled_on = enrolled_at.date() if enrolled_at else None
    # A "complete" enrollment with no date is not a datable enrollment, and
    # every gate below measures from that date. Treating it as complete
    # dereferenced a None and turned GET /rtm — and, through
    # practice_overview, the whole practice strip — into a 500.
    enrolled = bool(enrollment and enrollment.complete and enrolled_at is not None)
    floor = billing_floor(today, enrolled_at if enrolled else None)

    window = get_current(db, patient.id)
    monitoring_days = window.days_with_data if window else 0
    minutes, interactive = _minutes_in_window(db, patient.id, floor)
    documentation_ready = _documentation_ready(db, patient.id, floor)

    enrollment_state = {
        "education_complete": bool(enrollment and enrollment.education_complete),
        "consent_complete": bool(enrollment and enrollment.consent_complete),
        "baseline_complete": bool(enrollment and enrollment.baseline_complete),
        "complete": enrolled,
        "pathway": enrollment.pathway if enrollment else None,
    }

    eligibility: list[dict[str, Any]] = []

    def code(cpt: str, eligible: bool, note: str = "", units: int = 1) -> None:
        eligibility.append({"cpt": cpt, "eligible": eligible, "note": note, "units": units})

    # 98975 is a one-time setup charge, and nothing persists "already billed",
    # so the window is the proxy: the code is offered for the 30 days that
    # follow enrollment and never again. Re-offering it every computation adds
    # $20 per patient per month to estimated_value forever.
    setup_in_window = enrolled_on is not None and enrolled_on >= window_floor(today)
    if not enrolled:
        code("98975", False, "Enrollment incomplete")
    elif setup_in_window:
        code("98975", True)
    else:
        code("98975", False, f"One-time setup — enrolled {enrolled_on.isoformat()}")

    if not enrolled:
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

    if not enrolled:
        # Treatment management is a service rendered under an active RTM
        # enrollment. Minutes logged before 98975 completes are real work but
        # not billable work, and without this gate they reach the practice
        # strip's estimated revenue.
        code("98980", False, "Treatment management starts after enrollment")
    elif minutes >= 20 and interactive:
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
        enrolled
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
            "window_days": WINDOW_DAYS,
            "eligible": monitoring_days >= QUALIFY_DAYS,
            "enrolled": enrolled,
        },
        "treatment_management": {
            "minutes": minutes,
            "interactive_communication": interactive,
            # The period these minutes were counted over, so the card is
            # self-describing: two readings taken days apart can be told apart
            # as the same accrual rather than a second one.
            "counted_from": floor.date().isoformat(),
            "counted_to": today.isoformat(),
            "billable_from": enrolled_on.isoformat() if enrolled else None,
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
    """The lightweight practice strip (SPEC.md §9) — five numbers, no dashboard.

    Recomputes each patient the way GET /api/worklist does. Reading the stored
    assessment instead would report yesterday's tier and yesterday's monitoring
    window on the first request of a new day, and the strip sits directly above
    the worklist it would then contradict.
    """
    from app.engine.pipeline import ensure_current

    today = today or date.today()
    patients = db.scalars(select(Patient).order_by(Patient.id)).all()

    needs_review = 0
    ready = 0
    revenue = 0.0
    adherence_rates: list[float] = []
    for patient in patients:
        assessment = ensure_current(db, patient.id)
        # the HIGH tier, which is exactly what GET /api/worklist reports as
        # stats["high"] — the two endpoints must not disagree about how many
        # patients need review
        if assessment.risk_level == "high":
            needs_review += 1
        rate = assessment.analytics.get("adherence", {}).get("rate")
        if rate is not None:
            adherence_rates.append(float(rate))
        readiness = compute_readiness(db, patient, today)
        if readiness["ready_to_bill"]:
            ready += 1
        revenue += readiness["estimated_value"]

    return {
        # the monitored roster, matching the worklist's stats["total"]
        "rtm_patients": len(patients),
        "needs_review": needs_review,
        "ready_to_bill": ready,
        "therapy_adherence_pct": round(100 * sum(adherence_rates) / len(adherence_rates))
        if adherence_rates
        else None,
        "estimated_revenue": round(revenue, 2),
    }
