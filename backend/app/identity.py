"""One person, one chart: the console's view of a patient's phone and app
enrollment, and the two writes that keep the console and the patient app on
the same record.

Why this exists. Every task, message and text is keyed by ``patients.id``.
The console works on the chart a clinician opened; the app works on whatever
record the person enrolled against. When those differ — the clinician's
chart has no phone and the person signed up from the app as a new general
patient — the two halves of the product go quiet on each other: a message
sent from the chart never reaches the phone, a task never appears in the
app. ``set_phone`` fixes the first half (a chart with the right number gets
texts); ``link_app_account`` fixes both, by folding the app sign-up into the
chart so the session the phone already holds becomes a session on the chart.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.checkin import Checkin, CheckinInvite
from app.models.connection import WearableConnection
from app.models.insight import EstablishedBaseline, Insight, RiskAssessment
from app.models.library import CareAction, TaskVerification
from app.models.mobile import Message, PatientSession, PhoneVerification
from app.models.notification import Notification
from app.models.observation import Observation
from app.models.patient import Device, Patient
from app.notifications import sendblue

logger = logging.getLogger(__name__)


class IdentityError(ValueError):
    """A write the caller has to confirm or correct (the API answers 409/422)."""

    def __init__(self, detail: str, status: int = 409, **extra: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.extra = extra


# --- reading -------------------------------------------------------------------------


def app_status(db: Session, patient: Patient) -> dict[str, Any]:
    """Whether this chart is signed in on the patient app, and from where."""
    session = db.scalar(
        select(PatientSession)
        .where(PatientSession.patient_id == patient.id, PatientSession.revoked_at.is_(None))
        .order_by(PatientSession.last_seen_at.desc())
        .limit(1)
    )
    ever = session is not None or db.scalar(
        select(PatientSession.id).where(PatientSession.patient_id == patient.id).limit(1)
    ) is not None
    return {
        "enrolled": session is not None,
        "ever_enrolled": ever,
        "device_name": session.device_name if session else None,
        "app_version": session.app_version if session else None,
        "last_seen_at": session.last_seen_at.isoformat() if session else None,
    }


def _mask(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    return f"•••• {digits[-4:]}" if len(digits) >= 4 else "••••"


def link_candidates(db: Session, patient: Patient) -> list[dict[str, Any]]:
    """Other records that could be this person's app sign-up: anything with
    an app session or a phone, the ones sharing a name word first, then the
    most recently seen. Never the chart itself."""
    tokens = {t for t in patient.name.lower().replace(",", " ").split() if len(t) > 1}
    rows = db.scalars(select(Patient).where(Patient.id != patient.id)).all()
    out: list[dict[str, Any]] = []
    for p in rows:
        status = app_status(db, p)
        if not status["ever_enrolled"] and not p.phone:
            continue
        shared = bool(tokens & {t for t in p.name.lower().replace(",", " ").split()})
        out.append({
            "patient_id": p.id,
            "name": p.name,
            "hospital_id": p.hospital_id,
            "mode": "general" if str(p.procedure_type) == "NONE" else "recovery",
            "procedure_display": p.procedure_display,
            "phone_masked": _mask(p.phone),
            "phone_match": bool(patient.phone and p.phone and patient.phone == p.phone),
            "app": status,
            "name_match": shared,
        })
    out.sort(key=lambda c: (
        not c["phone_match"], not c["name_match"], not c["app"]["enrolled"],
        c["app"]["last_seen_at"] or "", c["name"],
    ))
    return out


# --- the phone -----------------------------------------------------------------------


def set_phone(db: Session, patient: Patient, phone: str | None, *, force: bool = False) -> dict:
    """Put a number on a chart (or clear it). A number already on another
    chart is refused unless ``force``, in which case it moves: one number,
    one patient, or inbound texts could land on the wrong chart."""
    if phone is None or not str(phone).strip():
        previous = patient.phone
        patient.phone = None
        db.commit()
        return {"phone": None, "previous": previous, "moved_from": []}
    normalized = sendblue.normalize_phone(str(phone))
    if normalized is None:
        raise IdentityError("Enter a valid mobile number (10 digits, or +country code)", 422)
    holders = db.scalars(
        select(Patient).where(Patient.phone == normalized, Patient.id != patient.id)
    ).all()
    if holders and not force:
        names = ", ".join(f"{h.name} ({h.id})" for h in holders)
        raise IdentityError(
            f"That number is already on {names}. Link that record instead, or move the "
            "number here.",
            409, holders=[h.id for h in holders],
        )
    moved = []
    for h in holders:
        h.phone = None
        moved.append(h.id)
        logger.info("Phone moved from %s to %s by the console", h.id, patient.id)
    patient.phone = normalized
    db.commit()
    return {"phone": normalized, "previous": None, "moved_from": moved}


# --- folding an app sign-up into a chart ---------------------------------------------


# Rows that simply change owner. Order matters for nothing here — no table
# references another by patient id — but Message/Session first reads well.
_MOVED = (
    PatientSession, PhoneVerification, Message, AdherenceTask, AdherenceRecord,
    TaskVerification, Checkin, CheckinInvite, Notification, Device, CareAction, Observation,
)
# Derived rows: dropped on both sides and recomputed for the chart.
_DERIVED = (RiskAssessment, EstablishedBaseline)


def link_app_account(db: Session, target: Patient, source: Patient) -> dict[str, Any]:
    """Merge ``source`` (the record the app enrolled against) into ``target``
    (the chart the clinician works on) and delete ``source``.

    Everything the person did in the app — sessions, thread, tasks, check-ins,
    Apple Health observations, the Junction connection — moves to the chart,
    so the phone's existing session keeps working and now acts as the chart.
    Blanks on the chart (phone, date of birth) fill from the sign-up; the
    chart's own values win otherwise. Derived rows are recomputed.
    """
    if target.id == source.id:
        raise IdentityError("A record cannot be linked to itself", 422)
    counts: dict[str, int] = {}
    for model in _MOVED:
        result = db.execute(
            update(model).where(model.patient_id == source.id).values(patient_id=target.id)
        )
        counts[model.__tablename__] = result.rowcount

    # One aggregator account per chart: keep the chart's own if it has one
    # (its history is already here), otherwise the sign-up's comes across.
    for conn in db.scalars(
        select(WearableConnection).where(WearableConnection.patient_id == source.id)
    ).all():
        existing = db.scalar(
            select(WearableConnection).where(
                WearableConnection.patient_id == target.id,
                WearableConnection.aggregator == conn.aggregator,
            )
        )
        if existing is None:
            conn.patient_id = target.id
            counts["wearable_connections"] = counts.get("wearable_connections", 0) + 1
        else:
            logger.warning(
                "Link %s -> %s: both hold a %s connection; keeping the chart's (%s), "
                "dropping %s", source.id, target.id, conn.aggregator,
                existing.external_user_id, conn.external_user_id,
            )
            db.delete(conn)

    for model in _DERIVED:
        db.execute(delete(model).where(model.patient_id.in_([source.id, target.id])))
    db.execute(delete(Insight).where(Insight.patient_id.in_([source.id, target.id])))

    filled: list[str] = []
    if not target.phone and source.phone:
        target.phone = source.phone
        filled.append("phone")
    elif target.phone and source.phone and target.phone != source.phone:
        # Two different numbers: the one the app verified by use is the one
        # texts should go to. The chart's old number is kept in the log.
        logger.info("Link %s -> %s: replacing chart phone with the app's", source.id, target.id)
        target.phone = source.phone
        filled.append("phone")
    if not target.date_of_birth and source.date_of_birth:
        target.date_of_birth = source.date_of_birth
        filled.append("date_of_birth")
    if not target.hospital_id and source.hospital_id:
        target.hospital_id = source.hospital_id
        filled.append("hospital_id")
    source_phone = source.phone
    source.phone = None  # the unique-number rule, before the row goes
    db.flush()
    db.delete(source)
    db.commit()

    from app.engine.pipeline import run_patient

    run_patient(db, target.id, force=True)
    logger.info("Linked app record %s into chart %s: %s", source.id, target.id, counts)
    return {
        "linked_from": source.id,
        "patient_id": target.id,
        "phone": target.phone,
        "source_phone": source_phone,
        "filled": filled,
        "moved": counts,
        "linked_at": datetime.now().isoformat(),
    }
