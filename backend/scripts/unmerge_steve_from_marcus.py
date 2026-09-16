#!/usr/bin/env python
"""Undo the accidental link of the `steve` chart into `marcus`.

The console's "Link an app sign-up" was used on Marcus's chart with Steve's
record as the source, so ``identity.link_app_account`` folded Steve into
Marcus and deleted the Steve row: his phone, his two app sessions, his
Junction connection, his Apple Health history, his tasks and his message
thread all moved across.

Nothing about that merge is reversible in general — it is designed for one
person holding two records — but this instance is separable because the two
people's data carries different provenance:

* Steve's readings come from Apple Health, through Junction
  (``source_provider`` junction with ``source_device_id`` apple_health_kit)
  and from the phone's direct gait upload (apple / apple_health:gait).
* Marcus's are the demo generator's Fitbit and patient-reported rows.

Two things the merge destroyed rather than moved, because its day-collision
rule assumed both sides were the same person:

* ~50 of Steve's daily summaries, where his Apple day collided with
  Marcus's Fitbit day for the same metric. Those are restored from the S3
  backup taken before the merge (``--backup``).
* some of Marcus's Fitbit days, which lost the same coin toss. They are NOT
  recoverable here — that backup predates Marcus existing — so they have to
  come from a demo_fill re-run afterwards. The script reports the shortfall.

    uv run python scripts/unmerge_steve_from_marcus.py --local copy.db --backup backup.db
    uv run python scripts/unmerge_steve_from_marcus.py --bucket <bucket> --backup backup.db
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# Steve's chart, as the seed declares it (app/seed/patients.py).
STEVE = dict(
    id="steve", name="Steve", initials="S", age=19, sex="M",
    procedure_type="TKA", procedure_display="Total Knee Replacement (TKA)",
    surgeon_id="ct_alvarez", assigned_provider_id="ct_alvarez",
    hospital_id="hosp_medpull", phone="+18588666257", care_pathway=None,
)
MARCUS_PHONE = "+17135550122"

# Provenance that identifies a row as Steve's, not Marcus's.
STEVE_PROVIDERS = ("junction", "apple")
STEVE_DEVICES = ("apple_health_kit", "apple_health:gait")
# His Junction account, and the retired one from the earlier steve-test merge.
STEVE_JUNCTION_USERS = ("2857dd72-7e85-42a7-af22-5cd31c8d6984",
                        "7dae8c30-491a-4f50-a012-c3c11050bad3")
# Message rows: his voice/console history and the SMS loop we proved tonight.
STEVE_MESSAGE_IDS = (1, 2, 3, 4, 5, 6, 7, 42, 43, 44, 45, 46, 47, 48)
# His real tasks (a care-plan check-in and the weekly incision photo).
STEVE_TASK_IDS = (21, 60)
# Created on the wrong chart during the accident: two identical tasks from a
# double-click, and the two failed texts announcing them. Deleted, not moved.
ACCIDENT_TASK_IDS = (61, 62)
ACCIDENT_MESSAGE_IDS = (49, 50)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--bucket", help="S3 bucket holding db/recovery.db")
    where.add_argument("--local", help="operate on this SQLite file in place")
    ap.add_argument("--backup", required=True,
                    help="pre-merge database, for the daily summaries the merge deleted")
    ap.add_argument("--db-key", default="db/recovery.db")
    args = ap.parse_args()

    for key in ("GROQ_API_KEY", "JUNCTION_API_KEY", "JUNCTION_WEBHOOK_SECRET",
                "SENDBLUE_API_KEY", "SENDBLUE_API_SECRET", "SENDBLUE_WEBHOOK_SECRET",
                "OLLAMA_URL", "CARE_TEAM_PHONES"):
        os.environ[key] = ""
    os.environ["WARM_CACHES_ON_STARTUP"] = "false"
    workdir = None
    if args.bucket:
        workdir = tempfile.mkdtemp(prefix="medpull-unmerge-")
        os.environ["S3_BUCKET"] = args.bucket
        os.environ["S3_DB_KEY"] = args.db_key
        os.environ["DATABASE_URL"] = f"sqlite:///{workdir}/recovery.db"
        os.environ["LOCK_TTL_SECONDS"] = "300"
        os.environ["LOCK_ACQUIRE_TIMEOUT_SECONDS"] = "60"
    else:
        os.environ["S3_BUCKET"] = ""
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(args.local).resolve()}"

    import app.models  # noqa: F401
    from app.aws import storage
    from app.database import SessionLocal, ensure_schema

    def apply(db) -> dict:
        import sqlite3

        from sqlalchemy import delete, select, update

        from app.models.adherence import AdherenceRecord, AdherenceTask
        from app.models.connection import WearableConnection
        from app.models.insight import EstablishedBaseline, Insight, RiskAssessment
        from app.models.library import TaskVerification
        from app.models.mobile import Message, PatientSession
        from app.models.observation import Observation
        from app.models.patient import Device, Patient

        report: dict = {}
        if db.get(Patient, "steve") is not None:
            raise SystemExit("`steve` already exists — nothing to unmerge")
        marcus = db.get(Patient, "marcus")
        if marcus is None:
            raise SystemExit("`marcus` is missing — wrong database?")

        # 1. Steve's chart, as it was.
        today = date.today()
        steve = Patient(
            **STEVE,
            surgery_date=date(2026, 9, 2),
            discharge_date=date(2026, 9, 3),
            date_of_birth=None,
        )
        db.add(steve)
        db.flush()

        # 2. His readings, by provenance, re-keyed so the dedupe key names him.
        moved_obs = 0
        for row in db.scalars(select(Observation).where(
            Observation.patient_id == "marcus",
            Observation.source_provider.in_(STEVE_PROVIDERS),
        )).all():
            if (row.source_device_id or "") not in STEVE_DEVICES:
                continue
            row.patient_id = "steve"
            row.dedupe_key = row.dedupe_key.replace(":marcus:", ":steve:", 1)
            moved_obs += 1
        db.flush()
        report["observations_moved"] = moved_obs

        # 3. Sessions (Marcus never had one), his messages, his tasks.
        report["sessions_moved"] = db.execute(
            update(PatientSession).where(PatientSession.patient_id == "marcus")
            .values(patient_id="steve")
        ).rowcount
        report["messages_moved"] = db.execute(
            update(Message).where(Message.id.in_(STEVE_MESSAGE_IDS))
            .values(patient_id="steve")
        ).rowcount
        report["tasks_moved"] = db.execute(
            update(AdherenceTask).where(AdherenceTask.id.in_(STEVE_TASK_IDS))
            .values(patient_id="steve")
        ).rowcount
        for model in (AdherenceRecord, TaskVerification):
            db.execute(update(model).where(model.task_id.in_(STEVE_TASK_IDS))
                       .values(patient_id="steve"))

        # 4. The accident's own rows.
        report["accident_tasks_deleted"] = db.execute(
            delete(AdherenceTask).where(AdherenceTask.id.in_(ACCIDENT_TASK_IDS))
        ).rowcount
        for model in (AdherenceRecord, TaskVerification):
            db.execute(delete(model).where(model.task_id.in_(ACCIDENT_TASK_IDS)))
        report["accident_messages_deleted"] = db.execute(
            delete(Message).where(Message.id.in_(ACCIDENT_MESSAGE_IDS))
        ).rowcount

        # 5. The wearable account and its device rows are his.
        report["connections_moved"] = db.execute(
            update(WearableConnection)
            .where(WearableConnection.external_user_id.in_(STEVE_JUNCTION_USERS))
            .values(patient_id="steve")
        ).rowcount
        moved_devices = []
        for device in db.scalars(select(Device).where(Device.patient_id == "marcus")).all():
            if any(user in device.id for user in STEVE_JUNCTION_USERS):
                device.patient_id = "steve"
                moved_devices.append(device.id)
        report["devices_moved"] = moved_devices

        # 6. Marcus is a demo persona again.
        marcus.phone = MARCUS_PHONE
        db.flush()

        # 7. The daily summaries the merge deleted, from the pre-merge copy.
        #    Both of Steve's old records are sources: this database already
        #    holds the result of folding steve-test-8de9 into steve.
        held = {row.dedupe_key for row in db.scalars(
            select(Observation).where(Observation.patient_id == "steve"))}
        # The day identity of a daily summary. Both sides must be normalised
        # the same way: rows read through the ORM carry date/enum objects,
        # rows read straight from the backup carry strings, and comparing the
        # two forms silently matched nothing.
        def day_of(metric, local_date, granularity, device) -> tuple:
            if isinstance(local_date, str):
                local_date = date.fromisoformat(local_date[:10])
            return (str(metric), local_date, str(granularity), device or "na")

        by_day = {
            day_of(r.metric_type, r.local_date, r.granularity, r.source_device_id)
            for r in db.scalars(select(Observation).where(Observation.patient_id == "steve"))
            if str(r.granularity) == "daily_summary"
        }
        backup = sqlite3.connect(str(Path(args.backup).resolve()))
        backup.row_factory = sqlite3.Row
        writable = set(Observation.__table__.columns.keys())

        # sqlite3 hands back strings; the ORM's Date/DateTime columns want
        # real objects, and a JSON column wants the decoded value.
        import json as _json
        from datetime import datetime as _dt

        DATETIMES = ("start_time", "end_time", "source_updated_at", "deleted_at", "ingested_at")
        DATES = ("local_date",)
        JSONS = ("value_json", "raw_payload")

        def coerce(data: dict) -> dict:
            out = {}
            for key, value in data.items():
                if key not in writable:
                    continue
                if value is None:
                    out[key] = None
                elif key in DATETIMES and isinstance(value, str):
                    out[key] = _dt.fromisoformat(value)
                elif key in DATES and isinstance(value, str):
                    out[key] = date.fromisoformat(value[:10])
                elif key in JSONS and isinstance(value, str):
                    try:
                        out[key] = _json.loads(value)
                    except ValueError:
                        out[key] = None
                else:
                    out[key] = value
            return out
        restored = 0
        for row in backup.execute(
            "select * from observations where patient_id in ('steve','steve-test-8de9')"
        ).fetchall():
            data = dict(row)
            # Both old records become one chart, so the key names steve either way.
            key = data["dedupe_key"].replace("steve-test-8de9", "steve")
            if key in held:
                continue
            day = day_of(data["metric_type"], data["local_date"],
                         data["granularity"], data["source_device_id"])
            if str(data["granularity"]) == "daily_summary":
                if day in by_day:
                    continue
                by_day.add(day)
            data.pop("id", None)
            data["patient_id"] = "steve"
            data["dedupe_key"] = key
            db.add(Observation(**coerce(data)))
            held.add(key)
            restored += 1
        backup.close()
        db.flush()
        report["observations_restored_from_backup"] = restored

        # 8. Derived rows for both, then recompute from the real data.
        for model in (RiskAssessment, EstablishedBaseline):
            db.execute(delete(model).where(model.patient_id.in_(("steve", "marcus"))))
        db.execute(delete(Insight).where(Insight.patient_id.in_(("steve", "marcus"))))
        db.commit()

        from app.engine.pipeline import run_patient

        for patient_id in ("steve", "marcus"):
            assessment = run_patient(db, patient_id, force=True)
            report[f"{patient_id}_tier"] = str(assessment.risk_level)

        # 9. What Marcus is still missing, for a demo_fill top-up.
        from sqlalchemy import distinct, func

        since = today - timedelta(days=30)
        for patient_id in ("steve", "marcus"):
            report[f"{patient_id}_observations"] = db.scalar(
                select(func.count(Observation.id))
                .where(Observation.patient_id == patient_id))
            report[f"{patient_id}_days_with_data"] = db.scalar(
                select(func.count(distinct(Observation.local_date)))
                .where(Observation.patient_id == patient_id,
                       Observation.local_date >= since))
            report[f"{patient_id}_phone"] = db.get(Patient, patient_id).phone
        report["steve_sessions_live"] = db.scalar(
            select(func.count(PatientSession.id))
            .where(PatientSession.patient_id == "steve", PatientSession.revoked_at.is_(None)))
        db.commit()
        return report

    if args.bucket:
        with storage.write_lock():
            storage.hydrate(force=True)
            ensure_schema()
            with SessionLocal() as db:
                report = apply(db)
            report["uploaded"] = storage.persist(conditional=False)
        report["etag"] = storage._state.get("etag")
    else:
        ensure_schema()
        with SessionLocal() as db:
            report = apply(db)
        report["uploaded"] = False
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
