"""Idempotent persistence of canonical observations.

Wearable providers re-deliver webhooks, revise already-delivered rows
(restatement — Apple resting HR, Garmin sleep staging, WHOOP edits are all
routine) and back-fill late data. First-write-wins is therefore wrong in a way
that biases the engine toward under-reporting: a provisional partial value
would win forever over the provider's corrected one. Ingestion is a genuine
upsert:

* a byte-identical redelivery (same payload_hash) counts as a duplicate;
* a changed payload updates the row and bumps ``revision`` — unless the
  provider's own ``source_updated_at`` says the incoming copy is older than
  what we hold, which counts as a duplicate (out-of-order redelivery);
* a provider tombstone (``deleted=True``) soft-deletes: the row keeps its
  identity so the deletion survives re-delivery, and the readers that drive
  analytics and billing — ``engine/dataload.py`` and ``rtm/coverage.py`` —
  filter ``deleted_at``.

This is also the choke point where an observation's date is bounded. Every
connector's output reaches the table through here, so it is the only place a
window guard cannot be bypassed by a new connector.
"""

import hashlib
import json
from datetime import date, datetime, timedelta, timezone as dt_timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import CanonicalObservation
from app.engine import baseline_store
from app.models.enums import MetricType as M
from app.models.observation import Observation
from app.models.patient import Patient

# Batch ceiling. The whole ten-patient seed is 2,825 rows delivered in ten
# calls, the largest of them 585; a real connect-time back-fill is the same
# order. A payload past this is a provider fault or a hostile body, not data.
MAX_BATCH_OBSERVATIONS = 5_000

# How far before surgery an observation may be dated. compute_baseline() takes
# *every* day with a negative post-op index as pre-op, so an old back-fill does
# not extend the history — it rewrites the reference the z-scores are measured
# against, widening the SD until real deterioration reads as ordinary. Sixty
# days absorbs any connect-time historical pull (aggregators default to 30-90)
# while keeping the personal baseline anchored to the weeks around surgery.
MAX_PREOP_BACKFILL_DAYS = 60

# Outer bounds of what a human body (or a device measuring one) can report.
# These are not clinical thresholds — they are the edge of the physically
# possible, deliberately wide enough that no real reading is ever refused. A
# value outside them is an integration fault (unit mismatch, a sentinel like
# -1 or 999, a hostile body), and letting one in is not a small error: a
# baseline is a mean over ten days, so a single "resting HR" of 200 moves a
# patient's reference by twelve beats and blinds the channel that decides
# their tier.
PLAUSIBLE_RANGE: dict[str, tuple[float, float]] = {
    str(M.STEPS): (0.0, 100_000.0),
    str(M.RESTING_HR): (25.0, 150.0),
    str(M.HR_SAMPLE): (20.0, 250.0),
    str(M.HRV_RMSSD): (1.0, 300.0),
    str(M.SLEEP_DURATION): (0.0, 24.0),
    str(M.SLEEP_STAGES): (0.0, 24.0),
    str(M.SPO2): (50.0, 100.0),
    str(M.RESPIRATORY_RATE): (4.0, 60.0),
    str(M.SKIN_TEMP): (30.0, 45.0),
    str(M.SKIN_TEMP_DELTA): (-10.0, 10.0),
    str(M.WALKING_SPEED): (0.0, 4.0),
    str(M.STEP_LENGTH): (0.0, 2.0),
    str(M.DOUBLE_SUPPORT_PCT): (0.0, 100.0),
    str(M.WALKING_ASYMMETRY_PCT): (0.0, 100.0),
    str(M.WALKING_STEADINESS): (0.0, 100.0),
    str(M.STAIR_SPEED_UP): (0.0, 3.0),
    str(M.STAIR_SPEED_DOWN): (0.0, 3.0),
    str(M.SIX_MIN_WALK): (0.0, 1_200.0),
    str(M.ACTIVE_ENERGY): (0.0, 20_000.0),
    str(M.CALORIES): (0.0, 20_000.0),
    str(M.EXERCISE_SESSION): (0.0, 1_440.0),
    str(M.WEAR_TIME_MINUTES): (0.0, 1_440.0),
    str(M.PAIN_NRS): (0.0, 10.0),
    str(M.RANGE_OF_MOTION): (0.0, 360.0),
    str(M.EXERCISE_REPS): (0.0, 10_000.0),
}

# Observations are dated in patient-local wall time, so a patient east of the
# server can legitimately carry tomorrow's server-local date. Nothing can
# legitimately be dated further ahead, and the deviation window has no upper
# bound of its own — a future row simply becomes "the latest reading".
MAX_FUTURE_DAYS = 1


def _source_stamp(value: datetime | None) -> datetime | None:
    """The provider's last-modified instant as naive UTC.

    SQLite hands DateTime columns back naive, and Python refuses to order a
    naive datetime against an aware one, so an aggregator's ISO-8601 stamp
    (always offset-qualified) has to be flattened before it is written or
    compared. Naive input is trusted as already UTC.
    """
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(dt_timezone.utc).replace(tzinfo=None)


def payload_hash_of(o: CanonicalObservation) -> str:
    """Content hash over the measurement itself — the fields a restatement
    exists to correct.

    granularity is one of them because dedupe branch 1 keys on the provider's
    external_id alone: without it here, an intraday bucket restated as a daily
    summary hashes identically to what we hold and never reaches _apply().
    """
    material = json.dumps(
        {
            "value_num": o.value_num,
            "value_json": o.value_json,
            "unit": o.unit,
            "granularity": str(o.granularity),
            "start": o.start_time.isoformat(),
            "end": o.end_time.isoformat(),
            "deleted": o.deleted,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(material.encode()).hexdigest()


def ingestible_window(surgery_date: date, today: date) -> tuple[date, date]:
    """The inclusive range of dates an observation for this patient may carry."""
    return (
        surgery_date - timedelta(days=MAX_PREOP_BACKFILL_DAYS),
        today + timedelta(days=MAX_FUTURE_DAYS),
    )


def _reject_out_of_window(db: Session, observations: list[CanonicalObservation]) -> None:
    """Raise if any observation is dated outside its patient's ingestible window.

    Both day definitions are bounded — ``start_time.date()`` and the
    materialized ``local_date`` — so no reader is handed a day outside the
    window whichever of the two it indexes on.

    Rejection is all-or-nothing and loud. A batch carrying implausible dates is
    an integration fault, and applying the rest of it would leave a half-written
    back-fill that no endpoint reports; the caller turns this into a recorded,
    failed WebhookEvent instead.
    """
    today = date.today()
    patient_ids = {o.patient_id for o in observations}
    surgery_dates: dict[str, date] = dict(
        db.execute(
            select(Patient.id, Patient.surgery_date).where(Patient.id.in_(patient_ids))
        ).all()
    )
    unknown = sorted(patient_ids - set(surgery_dates))
    if unknown:
        raise ValueError(
            f"Cannot date-bound observations for unknown patient(s): {', '.join(unknown)}"
        )

    for patient_id in sorted(patient_ids):
        floor, ceiling = ingestible_window(surgery_dates[patient_id], today)
        offenders = [
            o
            for o in observations
            if o.patient_id == patient_id
            and not (
                floor <= min(o.start_time.date(), o.local_date)
                and max(o.start_time.date(), o.local_date) <= ceiling
            )
        ]
        if offenders:
            dates = sorted({o.start_time.date() for o in offenders})
            raise ValueError(
                f"{len(offenders)} observation(s) for {patient_id} fall outside the "
                f"ingestible window {floor}..{ceiling} (surgery date "
                f"{surgery_dates[patient_id]}): {dates[0]}..{dates[-1]}"
            )


def _reject_implausible(observations: list[CanonicalObservation]) -> None:
    """Raise if any numeric value is outside the physically possible range for
    its metric. Rejection is all-or-nothing, like the window guard: a batch
    carrying impossible numbers is a broken integration, and half-applying it
    leaves a mixture nobody can tell apart from real data afterwards."""
    offenders: list[str] = []
    for o in observations:
        if o.value_num is None:
            continue
        bounds = PLAUSIBLE_RANGE.get(str(o.metric_type))
        if bounds is None:
            continue
        low, high = bounds
        if not (low <= o.value_num <= high):
            offenders.append(
                f"{o.patient_id}/{o.metric_type} {o.value_num} on "
                f"{o.local_date.isoformat()} (plausible {low}..{high})"
            )
    if offenders:
        raise ValueError(
            f"{len(offenders)} observation(s) carry physiologically impossible "
            f"values: {'; '.join(offenders[:5])}"
        )


def _apply(row: Observation, o: CanonicalObservation, content_hash: str) -> None:
    """Restate an existing row in place.

    granularity is written because dedupe branch 1 (the provider's external_id)
    does not carry it in the key: a measurement first delivered as an intraday
    bucket and restated as a daily summary lands on this same row, and keeping
    the old value would misfile it for every granularity-aware reader. Branches
    2 and 3 both pin granularity in the key, so there the write is a no-op.

    external_id is deliberately not written: branch 1 keys on it, so it cannot
    differ, and on branches 2 and 3 it is absent by construction.

    qualifies_for_rtm and is_patient_reported are deliberately not written.
    They are provenance, decided once at normalize()/insert; making them
    restatement-mutable would let an unsigned or mock redelivery promote a row
    into the billable set rtm/coverage.py counts.
    """
    row.value_num = o.value_num
    row.value_json = o.value_json
    row.unit = o.unit
    row.granularity = o.granularity
    row.start_time = o.start_time
    row.end_time = o.end_time
    row.timezone = o.timezone
    row.local_date = o.local_date
    row.source_device_id = o.source_device_id
    row.body_site = o.body_site
    row.side = o.side
    row.source_updated_at = _source_stamp(o.source_updated_at)
    row.payload_hash = content_hash
    row.raw_payload = o.raw_payload
    row.deleted_at = datetime.now() if o.deleted else None
    row.ingested_at = datetime.now()


def partition_by_window(
    db: Session, observations: list[CanonicalObservation]
) -> tuple[list[CanonicalObservation], list[CanonicalObservation]]:
    """Split a batch into (inside, outside) the patients' ingestible windows.

    For an aggregator this is the polite form of ``_reject_out_of_window``:
    Junction back-fills and restates months of history as a matter of course,
    so a row dated before the pre-op window is routine, not a fault, and the
    right response is to drop it and say so rather than refuse the delivery
    (which the provider would only retry). The demo path keeps the loud
    all-or-nothing rejection, where an odd date really is a caller bug.

    Unknown patients are left in ``inside`` so the ingest guard still raises
    for them: silently dropping a row for a patient that does not exist would
    hide exactly the misrouting this exists to surface.
    """
    if not observations:
        return [], []
    today = date.today()
    patient_ids = {o.patient_id for o in observations}
    surgery_dates: dict[str, date] = dict(
        db.execute(
            select(Patient.id, Patient.surgery_date).where(Patient.id.in_(patient_ids))
        ).all()
    )
    inside: list[CanonicalObservation] = []
    outside: list[CanonicalObservation] = []
    for o in observations:
        surgery = surgery_dates.get(o.patient_id)
        if surgery is None:
            inside.append(o)
            continue
        floor, ceiling = ingestible_window(surgery, today)
        earliest = min(o.start_time.date(), o.local_date)
        latest = max(o.start_time.date(), o.local_date)
        (inside if floor <= earliest and latest <= ceiling else outside).append(o)
    return inside, outside


def ingest_in_batches(
    db: Session, observations: list[CanonicalObservation]
) -> tuple[int, int, int]:
    """``ingest_observations`` over a batch that may exceed the ceiling.

    The ceiling exists so an unbounded *body* cannot be materialized; a signed
    aggregator back-fill of a nightly SpO₂ series over the whole ingestible
    window is not that, but it can legitimately run past 5,000 rows. Feeding
    it through in ceiling-sized slices keeps every guard inside
    ``ingest_observations`` in force per slice while letting the whole
    delivery land. Note what changes: rejection becomes per slice rather than
    per delivery, which is why callers on this path pre-filter dates and
    values instead of relying on the guards to refuse.

    The baseline pin is taken once, for the whole delivery, before the first
    slice. Taken per slice it would let the second slice establish a
    patient's pre-op reference from whatever prefix of the back-fill the
    first slice happened to hold — a reference the delivery itself defined,
    which is exactly what the pin exists to prevent.
    """
    if not observations:
        return (0, 0, 0)
    for patient_id in sorted({o.patient_id for o in observations}):
        baseline_store.ensure_established(db, patient_id)
    db.commit()
    ingested = updated = duplicates = 0
    for offset in range(0, len(observations), MAX_BATCH_OBSERVATIONS):
        chunk = observations[offset : offset + MAX_BATCH_OBSERVATIONS]
        i, u, d = ingest_observations(db, chunk, pin_baseline=False)
        ingested += i
        updated += u
        duplicates += d
    return ingested, updated, duplicates


def ingest_observations(
    db: Session, observations: list[CanonicalObservation], *, pin_baseline: bool = True
) -> tuple[int, int, int]:
    """Returns (ingested, updated, duplicates).

    Raises ValueError if the batch is oversized, carries dates outside a
    patient's ingestible window, or carries values no body could produce —
    nothing is written in any of those cases.

    ``pin_baseline=False`` is for ``ingest_in_batches``, which has already
    pinned the reference for the delivery as a whole.
    """
    if not observations:
        return (0, 0, 0)

    if len(observations) > MAX_BATCH_OBSERVATIONS:
        raise ValueError(
            f"Batch of {len(observations)} observations exceeds the "
            f"{MAX_BATCH_OBSERVATIONS}-row ingest ceiling"
        )
    _reject_out_of_window(db, observations)
    _reject_implausible(observations)

    # Pin each patient's pre-op baseline to the record as it stands BEFORE this
    # delivery is applied. compute_baseline() reads every negative post-op day
    # as pre-op, so a back-fill dated inside the pre-op window does not extend
    # the reference — it replaces it, and every finding measured against the
    # old one silently becomes a different finding. Establishing here, at the
    # one choke point every connector passes through, is what stops a delivery
    # from defining the baseline it is about to be judged against.
    if pin_baseline:
        for patient_id in sorted({o.patient_id for o in observations}):
            baseline_store.ensure_established(db, patient_id)
        db.commit()

    keys = [o.dedupe_key for o in observations]
    existing: dict[str, Observation] = {
        row.dedupe_key: row
        for row in db.scalars(
            select(Observation).where(Observation.dedupe_key.in_(keys))
        )
    }

    ingested = 0
    updated = 0
    duplicates = 0
    for o in observations:
        key = o.dedupe_key
        content_hash = payload_hash_of(o)
        row = existing.get(key)

        if row is None:
            row = Observation(
                patient_id=o.patient_id,
                source_provider=o.source_provider,
                source_device_id=o.source_device_id,
                metric_type=o.metric_type,
                unit=o.unit,
                value_num=o.value_num,
                value_json=o.value_json,
                start_time=o.start_time,
                end_time=o.end_time,
                timezone=o.timezone,
                local_date=o.local_date,
                granularity=o.granularity,
                body_site=o.body_site,
                side=o.side,
                external_id=o.external_id,
                source_updated_at=_source_stamp(o.source_updated_at),
                payload_hash=content_hash,
                deleted_at=datetime.now() if o.deleted else None,
                qualifies_for_rtm=o.qualifies_for_rtm,
                is_patient_reported=o.is_patient_reported,
                dedupe_key=key,
                raw_payload=o.raw_payload,
            )
            db.add(row)
            existing[key] = row  # an intra-batch repeat is a restatement, not an insert
            ingested += 1
            continue

        if row.payload_hash == content_hash and bool(row.deleted_at) == o.deleted:
            duplicates += 1
            continue

        # Out-of-order redelivery: the provider's own clock says our copy is
        # newer. payload_hash alone can't catch this — the stale copy differs.
        incoming_stamp = _source_stamp(o.source_updated_at)
        held_stamp = _source_stamp(row.source_updated_at)
        if (
            incoming_stamp is not None
            and held_stamp is not None
            and incoming_stamp <= held_stamp
        ):
            duplicates += 1
            continue

        _apply(row, o, content_hash)
        row.revision = (row.revision or 0) + 1
        updated += 1

    db.commit()
    return (ingested, updated, duplicates)
