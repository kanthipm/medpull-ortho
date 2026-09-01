"""Deterministic RTM demo state (SPEC.md §1/§6/§8) — enrollment, provider
time, interactions, documentation. New tables only: nothing here may touch
observations, adherence, or anything else that feeds the pinned golden tiers.

Every timestamp derives from `today`, so readiness is stable regardless of
seed date. The roster deliberately covers every compliance stage:

  grace   education only — consent is the next action
  robert  baseline pending — enrollment incomplete
  marcus  enrolled, 14 min, no call yet — the spec's "98980 (6 min remaining)"
  linda   enrolled, minimal time — early monitoring
  priya   enrolled but barely-worn device — monitoring-days gap drives action
  elena   enrolled, 12 min incl. call — 98979 tier
  sofia   enrolled, 22 min incl. call — 98980 met, documentation pending
  aisha   enrolled, 25 min incl. call — 98980 met, documentation pending
  james   enrolled, 21 min incl. call, docs approved — Ready to Bill
  david   enrolled, 45 min incl. call, docs approved — Ready to Bill + 98981
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models.enums import (
    DocumentKind,
    DocumentStatus,
    GUARDRAIL_SENTENCE,
    InteractionKind,
    TimeLogActivity,
)
from app.models.rtm import EnrollmentStatus, ProviderTimeLog, RtmDocument, RtmInteraction
from app.seed.patients import get_spec


@dataclass(frozen=True)
class TimeEntry:
    days_ago: int
    activity: TimeLogActivity
    minutes: int
    interactive: bool = False
    note: str = ""


@dataclass(frozen=True)
class RtmSpec:
    education_days_ago: int | None
    consent_days_ago: int | None
    baseline_days_ago: int | None
    pathway: str
    time_logs: list[TimeEntry] = field(default_factory=list)
    approve_docs: bool = False


RTM_STATES: dict[str, RtmSpec] = {
    "marcus": RtmSpec(
        9, 9, 8, "TKA standard recovery",
        [
            TimeEntry(6, TimeLogActivity.CHART_REVIEW, 5, note="Reviewed vitals deviation"),
            TimeEntry(3, TimeLogActivity.CHART_REVIEW, 6, note="Reviewed pain trend + PT adherence"),
            TimeEntry(1, TimeLogActivity.MESSAGING, 3, note="Message re: swelling protocol"),
        ],
    ),
    "linda": RtmSpec(
        11, 11, 10, "Rotator cuff standard recovery",
        [
            TimeEntry(4, TimeLogActivity.CHART_REVIEW, 5, note="Sleep disruption review"),
            TimeEntry(2, TimeLogActivity.MESSAGING, 3, note="Message re: sling positioning"),
        ],
    ),
    "robert": RtmSpec(
        7, 6, None, "Lumbar decompression recovery",
        [TimeEntry(2, TimeLogActivity.CHART_REVIEW, 4, note="Initial monitoring review")],
    ),
    "sofia": RtmSpec(
        22, 22, 21, "Ankle ORIF recovery",
        [
            TimeEntry(15, TimeLogActivity.CHART_REVIEW, 6, note="Weight-bearing progression review"),
            TimeEntry(9, TimeLogActivity.CALL, 6, interactive=True, note="Progress call — pain controlled"),
            TimeEntry(4, TimeLogActivity.CHART_REVIEW, 6, note="Gait metrics review"),
            TimeEntry(1, TimeLogActivity.DOCUMENTATION, 4, note="Monthly documentation prep"),
        ],
    ),
    "aisha": RtmSpec(
        16, 16, 15, "THA standard recovery",
        [
            TimeEntry(11, TimeLogActivity.CHART_REVIEW, 7, note="Postop signals review"),
            TimeEntry(7, TimeLogActivity.CALL, 8, interactive=True, note="Symptom review call"),
            TimeEntry(3, TimeLogActivity.CHART_REVIEW, 6, note="Deviation follow-up"),
            TimeEntry(1, TimeLogActivity.CARE_COORDINATION, 4, note="PT coordination"),
        ],
    ),
    "priya": RtmSpec(
        10, 10, 9, "THA standard recovery",
        [TimeEntry(5, TimeLogActivity.CHART_REVIEW, 5, note="Missing-data outreach review")],
    ),
    "grace": RtmSpec(
        3, None, None, "THA standard recovery",
        [],
    ),
    "david": RtmSpec(
        33, 33, 32, "ACL accelerated return-to-sport",
        [
            TimeEntry(24, TimeLogActivity.CHART_REVIEW, 8, note="Return-to-sport metrics review"),
            TimeEntry(18, TimeLogActivity.CALL, 10, interactive=True, note="Progression call"),
            TimeEntry(12, TimeLogActivity.CHART_REVIEW, 9, note="Asymmetry trend review"),
            TimeEntry(6, TimeLogActivity.CARE_COORDINATION, 8, note="PT plan progression"),
            TimeEntry(2, TimeLogActivity.DOCUMENTATION, 10, note="Monthly summary review"),
        ],
        approve_docs=True,
    ),
    "james": RtmSpec(
        29, 29, 28, "TKA standard recovery",
        [
            TimeEntry(16, TimeLogActivity.CHART_REVIEW, 6, note="Plateau review"),
            TimeEntry(10, TimeLogActivity.CALL, 7, interactive=True, note="Motivation + plan call"),
            TimeEntry(4, TimeLogActivity.CHART_REVIEW, 8, note="Trend review"),
        ],
        approve_docs=True,
    ),
    "elena": RtmSpec(
        20, 20, 19, "Meniscus repair recovery",
        [
            TimeEntry(8, TimeLogActivity.CHART_REVIEW, 4, note="Early mobility review"),
            TimeEntry(3, TimeLogActivity.CALL, 8, interactive=True, note="Check-in call — progressing"),
        ],
    ),
}

_INTERACTION_FOR = {
    TimeLogActivity.CALL: InteractionKind.CALL,
    TimeLogActivity.MESSAGING: InteractionKind.MESSAGE,
    TimeLogActivity.CARE_COORDINATION: InteractionKind.UPDATE_PLAN,
}


def seed_rtm(db: Session, today: date) -> dict[str, int]:
    counts = {"rtm_enrollment": 0, "rtm_time_logs": 0, "rtm_interactions": 0, "rtm_documents": 0}
    month = f"{today.year:04d}-{today.month:02d}"

    for patient_id, spec in RTM_STATES.items():
        patient_spec = get_spec(patient_id)
        if patient_spec is None:
            continue

        def at(days_ago: int | None, hour: int = 9) -> datetime | None:
            if days_ago is None:
                return None
            return datetime.combine(today - timedelta(days=days_ago), time(hour, 15))

        education_at = at(spec.education_days_ago)
        consent_at = at(spec.consent_days_ago, 10)
        baseline_at = at(spec.baseline_days_ago, 11)
        complete = all(t is not None for t in (education_at, consent_at, baseline_at))
        db.add(
            EnrollmentStatus(
                patient_id=patient_id,
                education_complete=education_at is not None,
                education_at=education_at,
                consent_complete=consent_at is not None,
                consent_at=consent_at,
                baseline_complete=baseline_at is not None,
                baseline_at=baseline_at,
                complete=complete,
                enrolled_at=baseline_at if complete else None,
                pathway=spec.pathway,
            )
        )
        counts["rtm_enrollment"] += 1

        surgeon_id = get_spec(patient_id).surgeon_id
        for entry in spec.time_logs:
            occurred = at(entry.days_ago, 14)
            db.add(
                ProviderTimeLog(
                    patient_id=patient_id,
                    provider_id=surgeon_id,
                    activity=entry.activity,
                    seconds=entry.minutes * 60,
                    interactive=entry.interactive,
                    note=entry.note or None,
                    occurred_at=occurred,
                    month=f"{occurred.year:04d}-{occurred.month:02d}",
                )
            )
            counts["rtm_time_logs"] += 1
            interaction_kind = _INTERACTION_FOR.get(entry.activity)
            if interaction_kind is not None:
                db.add(
                    RtmInteraction(
                        patient_id=patient_id,
                        provider_id=surgeon_id,
                        kind=interaction_kind,
                        detail=entry.note,
                        occurred_at=occurred,
                    )
                )
                counts["rtm_interactions"] += 1

        if spec.approve_docs:
            name = patient_spec.name
            display = patient_spec.procedure_display
            for kind, title, body in (
                (
                    DocumentKind.ENCOUNTER_NOTE,
                    f"RTM encounter note — postop day {patient_spec.postop_day}",
                    f"{name}, {display}, postop day {patient_spec.postop_day}. Recovery "
                    "progressing per the assigned pathway with monitoring signals within "
                    "expected ranges. Treatment management this period included chart "
                    "review and a live patient call; plan continued unchanged. "
                    f"{GUARDRAIL_SENTENCE}",
                ),
                (
                    DocumentKind.MONTHLY_SUMMARY,
                    f"RTM monthly summary — {month}",
                    f"{name} ({display}) met the 16-of-30 monitoring-day threshold this "
                    "window with consistent therapy adherence. Provider review time and "
                    "a live interactive communication satisfy the treatment-management "
                    "requirements; documentation reviewed and approved. "
                    f"{GUARDRAIL_SENTENCE}",
                ),
            ):
                db.add(
                    RtmDocument(
                        patient_id=patient_id,
                        kind=kind,
                        content={"title": title, "body": body},
                        llm_provider="fallback",
                        model=None,
                        status=DocumentStatus.APPROVED,
                        month=month,
                        created_at=at(2, 16),
                        approved_at=at(1, 9),
                        approved_by=surgeon_id,
                    )
                )
                counts["rtm_documents"] += 1

    db.commit()
    return counts
