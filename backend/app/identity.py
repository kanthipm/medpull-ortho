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
    from sqlalchemy import func

    tokens = {t for t in patient.name.lower().replace(",", " ").split() if len(t) > 1}
    rows = db.scalars(select(Patient).where(Patient.id != patient.id)).all()
    out: list[dict[str, Any]] = []
    for p in rows:
        status = app_status(db, p)
        if not status["ever_enrolled"] and not p.phone:
            continue
        shared = bool(tokens & {t for t in p.name.lower().replace(",", " ").split()})
        # What linking would move, and whether it is allowed at all. A
        # candidate with its own readings and check-ins is somebody's chart,
        # not a stray sign-up, and the console needs to say so before a
        # click that cannot be undone.
        readings = db.scalar(select(func.count(Observation.id)).where(
            Observation.patient_id == p.id, Observation.deleted_at.is_(None))) or 0
        checkins = db.scalar(select(func.count(Checkin.id)).where(
            Checkin.patient_id == p.id)) or 0
        out.append({
            "observations": readings,
            "checkins": checkins,
            "refusal": link_refusal(db, patient, p),
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
# Observations are handled separately: their dedupe key names the patient.
_MOVED = (
    PatientSession, PhoneVerification, Message, AdherenceTask, AdherenceRecord,
    TaskVerification, Checkin, CheckinInvite, Notification, Device, CareAction,
)
# Derived rows: dropped on both sides and recomputed for the chart.
_DERIVED = (RiskAssessment, EstablishedBaseline)


def _last_seen(db: Session, patient_id: str) -> datetime:
    seen = db.scalar(
        select(PatientSession.last_seen_at)
        .where(PatientSession.patient_id == patient_id, PatientSession.revoked_at.is_(None))
        .order_by(PatientSession.last_seen_at.desc())
        .limit(1)
    )
    return seen or datetime.min


def _merge_observations(
    db: Session, target: Patient, source: Patient, keep_user: str | None = None
) -> dict[str, int]:
    """Move the sign-up's readings onto the chart without double counting.

    A dedupe key names the patient it was ingested for, so a moved row must
    be re-keyed to the chart or the next delivery of the same measurement
    (a restated daily step total) would land beside it as a second row.
    Re-keying also exposes the real overlap: the same Apple Health day
    delivered for both records — one phone, two Junction users. For those
    the more recently ingested row wins, whichever record it came from.
    """
    from app.models.enums import Granularity

    def day_key(row: Observation) -> tuple | None:
        # Junction gives every daily summary its own record id per user, so
        # the same day from two users never shares a dedupe key. The day is
        # the identity of a daily summary (connectors/base.py says as much
        # for rows without a record id), so daily rows also collide by day.
        #
        # The SOURCE DEVICE is part of that identity. Without it, merging two
        # records fed by different hardware deleted one side's day as a
        # duplicate of the other's — a Fitbit day and an Apple day for the
        # same date are two measurements, not one, and roughly fifty of each
        # were destroyed that way before this was fixed. The case the merge
        # exists for is unaffected: one phone delivering under two Junction
        # users carries the same device id on both sides.
        if str(row.granularity) != str(Granularity.DAILY_SUMMARY):
            return None
        return (str(row.metric_type), row.local_date, row.source_device_id or "na",
                row.side or "na", row.body_site or "na")

    by_key: dict[str, Observation] = {}
    by_day: dict[tuple, Observation] = {}
    for row in db.scalars(select(Observation).where(Observation.patient_id == target.id)):
        by_key[row.dedupe_key] = row
        if (k := day_key(row)) is not None:
            by_day[k] = row
    def from_kept_account(row: Observation) -> bool:
        # A Junction device id is "junction:<user>:<provider slug>".
        return bool(keep_user and keep_user in (row.source_device_id or ""))

    def wins(candidate: Observation, holder: Observation) -> bool:
        """Which of two readings for the same day survives.

        The one delivered by the Junction account that is being KEPT wins,
        whatever its ingest time: a future restatement of that day arrives
        with that account's record id, and if the surviving row carried the
        retired account's id the restatement would land beside it as a second
        reading for the day and double the total. Ingest time only breaks a
        tie between rows from the same account.
        """
        kept_candidate, kept_holder = from_kept_account(candidate), from_kept_account(holder)
        if kept_candidate != kept_holder:
            return kept_candidate
        return (candidate.ingested_at or datetime.min) > (holder.ingested_at or datetime.min)

    counts = {"moved": 0, "dropped_duplicate": 0, "replaced_older": 0}
    for row in db.scalars(select(Observation).where(Observation.patient_id == source.id)).all():
        new_key = row.dedupe_key.replace(f":{source.id}:", f":{target.id}:", 1)
        dk = day_key(row)
        existing = by_key.get(new_key) or (by_day.get(dk) if dk is not None else None)
        if existing is not None:
            if wins(row, existing):
                by_key.pop(existing.dedupe_key, None)
                if (ek := day_key(existing)) is not None:
                    by_day.pop(ek, None)
                db.delete(existing)
                db.flush()  # free the unique key before the moved row takes it
                counts["replaced_older"] += 1
            else:
                db.delete(row)
                counts["dropped_duplicate"] += 1
                continue
        row.patient_id = target.id
        row.dedupe_key = new_key
        by_key[new_key] = row
        if dk is not None:
            by_day[dk] = row
        counts["moved"] += 1
    db.flush()
    return counts


def _merge_connections(db: Session, target: Patient, source: Patient) -> dict[str, Any]:
    """One aggregator account per chart. When both records have one, keep
    the account the phone is actually delivering to — the record with the
    live app session, then the one with the newest data — and retire the
    other: its Device rows are marked revoked and its Junction user id is
    returned so an operator can delete it at Junction. Webhooks for a
    retired user are ignored by the connector (no connection row)."""
    out: dict[str, Any] = {"kept": None, "retired_junction_user": None}
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
            out["kept"] = conn.external_user_id
            continue
        source_rank = (_last_seen(db, source.id), conn.last_data_at or datetime.min)
        target_rank = (_last_seen(db, target.id), existing.last_data_at or datetime.min)
        keep, retire = (conn, existing) if source_rank > target_rank else (existing, conn)
        logger.warning(
            "Link %s -> %s: both hold a %s connection; keeping %s, retiring %s",
            source.id, target.id, conn.aggregator, keep.external_user_id, retire.external_user_id,
        )
        for device in db.scalars(select(Device).where(
            Device.id.like(f"{retire.aggregator}:{retire.external_user_id}:%")
        )).all():
            device.status = "revoked"
        db.delete(retire)
        db.flush()
        keep.patient_id = target.id
        out["kept"] = keep.external_user_id
        out["retired_junction_user"] = retire.external_user_id
    db.flush()
    return out


def _device_sources(db: Session, patient_id: str) -> set[str]:
    """The distinct hardware feeding a record's readings.

    Only the device itself, never the aggregator account it arrived under: a
    Junction device id is "junction:<user>:<slug>", and one phone delivering
    under two users would otherwise look like two different devices — which
    is precisely the case a merge is for.
    """
    return {
        (device or "na").rsplit(":", 1)[-1]
        for (device,) in db.execute(
            select(Observation.source_device_id)
            .where(Observation.patient_id == patient_id, Observation.deleted_at.is_(None))
            .distinct()
        ).all()
    }


def link_refusal(db: Session, target: Patient, source: Patient) -> str | None:
    """Why these two records must not be merged, or None when it is safe.

    The merge answers one question — "this person has two records, make them
    one" — and the evidence for that is a shared device: the same phone
    delivering under two aggregator users. Two records fed by entirely
    different hardware are two people, and folding them together deletes one
    of them. That happened: a chart with its own phone, two app sessions, a
    Junction account and three hundred Apple Health readings was folded into
    a demo patient whose data came from a Fitbit, and undoing it took a
    backup and a provenance-by-provenance split.
    """
    if target.id == source.id:
        return "A record cannot be linked to itself"
    target_sources = _device_sources(db, target.id)
    source_sources = _device_sources(db, source.id)
    if not target_sources or not source_sources:
        return None  # one side has no readings: nothing to disagree about
    if target_sources & source_sources:
        return None  # same hardware on both sides: one person, two records
    return (
        "These records are fed by different devices "
        f"({', '.join(sorted(source_sources))} vs {', '.join(sorted(target_sources))}), "
        "so they look like two different patients rather than one person's two "
        "records. Linking would delete one of them. Check the phone number and "
        "the device on each chart first."
    )


def link_app_account(
    db: Session, target: Patient, source: Patient, *, force: bool = False
) -> dict[str, Any]:
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
    refusal = link_refusal(db, target, source)
    if refusal is not None and not force:
        raise IdentityError(refusal, 409, source=source.id, target=target.id)
    counts: dict[str, int] = {}
    # The connection decision reads sessions, so it runs before they move.
    connections = _merge_connections(db, target, source)
    for model in _MOVED:
        result = db.execute(
            update(model).where(model.patient_id == source.id).values(patient_id=target.id)
        )
        counts[model.__tablename__] = result.rowcount
    observations = _merge_observations(db, target, source, connections.get("kept"))
    counts["observations"] = observations["moved"]

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

    # The merge is committed by this point. A failure to re-score must not be
    # reported as a failed link: the caller would retry and get a 404 for a
    # source record that no longer exists, and the next read recomputes anyway.
    try:
        from app.engine.pipeline import run_patient

        run_patient(db, target.id, force=True)
    except Exception:  # noqa: BLE001
        logger.exception("Link %s -> %s: recompute failed; the merge stands",
                         source.id, target.id)
    logger.info("Linked app record %s into chart %s: %s", source.id, target.id, counts)
    return {
        "linked_from": source.id,
        "patient_id": target.id,
        "phone": target.phone,
        "source_phone": source_phone,
        "filled": filled,
        "moved": counts,
        "observations": observations,
        "wearable": connections,
        "linked_at": datetime.now().isoformat(),
    }


def delete_patient(db: Session, patient: Patient) -> dict[str, Any]:
    """Remove a record and every row that points at it (a junk sign-up, a
    test row). Not a merge: nothing is kept. Refuses a record with a live
    app session — link it instead, or sign the phone out first."""
    if db.scalar(
        select(PatientSession.id).where(
            PatientSession.patient_id == patient.id, PatientSession.revoked_at.is_(None)
        ).limit(1)
    ) is not None:
        raise IdentityError(
            f"{patient.id} is signed in on the app; link it into a chart instead of deleting it"
        )
    from app.models.checkin import CheckinMessage

    counts: dict[str, int] = {}
    checkin_ids = db.scalars(select(Checkin.id).where(Checkin.patient_id == patient.id)).all()
    if checkin_ids:
        counts["checkin_messages"] = db.execute(
            delete(CheckinMessage).where(CheckinMessage.checkin_id.in_(checkin_ids))
        ).rowcount
    for model in (*_MOVED, Observation, WearableConnection, *_DERIVED):
        counts[model.__tablename__] = db.execute(
            delete(model).where(model.patient_id == patient.id)
        ).rowcount
    counts["insights"] = db.execute(delete(Insight).where(Insight.patient_id == patient.id)).rowcount
    pid = patient.id
    db.delete(patient)
    db.commit()
    logger.info("Deleted patient %s: %s", pid, counts)
    return {"deleted": pid, "rows": counts}
