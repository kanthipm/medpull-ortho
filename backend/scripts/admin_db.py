#!/usr/bin/env python
"""Operate on the deployed database the way the API does: under the S3
write lock, on a fresh hydrate, with an unconditional persist at the end.

    uv run python scripts/admin_db.py --bucket <s3 bucket> --dry-run --link steve steve-test-8de9
    uv run python scripts/admin_db.py --bucket <s3 bucket> --link steve steve-test-8de9 \\
        --prune-assessments --purge-phone-verifications
    uv run python scripts/admin_db.py --local /path/to/copy.db --link steve steve-test-8de9
    uv run python scripts/admin_db.py --bucket <s3 bucket> --mint-token hospital:hirt "HIRT console"
    uv run python scripts/admin_db.py --bucket <s3 bucket> --revoke-token 3

``--dry-run`` hydrates and applies the operations locally, prints the
report and uploads nothing. ``--local`` works on a SQLite file in place
(no S3 at all) — the way to rehearse on a downloaded copy first.

``--mint-token KIND:ORG_ID LABEL`` creates an org-scoped console credential
(``hospital:<id>``, ``sports_org:<id>``, ``team:<id>``, or ``all`` for a staff
one) and prints the token exactly once, in the report; the database keeps
only its hash. Hand it over as ``https://<console>/login#token=<token>``.
``--report`` lists every credential with its id, and ``--revoke-token ID``
retires one. The staff token stays ``CONSOLE_ACCESS_TOKEN``.

Every provider is switched off in this process (no Groq, Junction,
Sendblue or Ollama call can happen), so the only side effect is the file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--bucket", help="S3 bucket holding db/recovery.db (the deployed database)")
    where.add_argument("--local", help="operate on this SQLite file in place, no S3")
    ap.add_argument("--db-key", default="db/recovery.db")
    ap.add_argument("--dry-run", action="store_true", help="apply locally, report, upload nothing")
    ap.add_argument("--link", nargs=2, metavar=("TARGET", "SOURCE"), action="append", default=[],
                    help="fold SOURCE (an app sign-up) into TARGET (the chart); repeatable")
    ap.add_argument("--set-phone", nargs=2, metavar=("PATIENT", "PHONE"), action="append", default=[])
    ap.add_argument("--rename-hospital", nargs=2, metavar=("ID", "NAME"), action="append", default=[],
                    help="give a hospital row its real name (the seed calls it MedPull Demo Hospital)")
    ap.add_argument("--prune-assessments", action="store_true",
                    help="keep only the newest risk_assessments row per patient")
    ap.add_argument("--purge-phone-verifications", action="store_true",
                    help="delete every one-time code row (they expire in 10 minutes anyway)")
    ap.add_argument("--restore-demo-phones", action="store_true",
                    help="put each demo persona's intended number back on its chart "
                         "(app/seed/demo_fill.py is the source of the numbers)")
    ap.add_argument("--dedupe-daily", action="store_true",
                    help="collapse duplicate daily summaries (one per patient/metric/day/device), "
                         "keeping the most recently ingested")
    ap.add_argument("--revoke-sessions", action="append", default=[], metavar="PATIENT",
                    help="sign the patient app out of this chart (a lost phone, or "
                         "before deleting a chart that is signed in)")
    ap.add_argument("--delete-message", action="append", default=[], type=int, metavar="ID",
                    help="remove one thread line and any files on it, bytes included")
    ap.add_argument("--delete-sports-org", action="append", default=[], metavar="ORG_ID",
                    help="remove a sports program with its teams, staff, events and console "
                         "credentials; refuses one that still has athletes on it")
    ap.add_argument("--delete-patient", action="append", default=[], metavar="ID",
                    help="delete a patient and every row that points at them (no merge)")
    ap.add_argument("--mint-token", nargs=2, metavar=("KIND:ORG_ID", "LABEL"), action="append",
                    default=[],
                    help="mint an org-scoped console credential (hospital:<id>, sports_org:<id>, "
                         "team:<id>, or all); the token is printed once, only its hash is kept")
    ap.add_argument("--revoke-token", action="append", default=[], type=int, metavar="ID",
                    help="retire a console credential by id (--report lists them)")
    ap.add_argument("--report", action="store_true",
                    help="print the roster, row counts and console credentials")
    args = ap.parse_args()

    # Environment before any app import: app.database binds the engine at import.
    for key in ("GROQ_API_KEY", "JUNCTION_API_KEY", "JUNCTION_WEBHOOK_SECRET", "SENDBLUE_API_KEY",
                "SENDBLUE_API_SECRET", "SENDBLUE_WEBHOOK_SECRET", "OLLAMA_URL", "CARE_TEAM_PHONES"):
        os.environ[key] = ""
    os.environ["WARM_CACHES_ON_STARTUP"] = "false"
    workdir = None
    if args.bucket:
        workdir = tempfile.mkdtemp(prefix="medpull-admin-")
        os.environ["S3_BUCKET"] = args.bucket
        os.environ["S3_DB_KEY"] = args.db_key
        os.environ["DATABASE_URL"] = f"sqlite:///{workdir}/recovery.db"
        # A merge with a forced recompute takes longer than the API's 25 s.
        os.environ["LOCK_TTL_SECONDS"] = "300"
        os.environ["LOCK_ACQUIRE_TIMEOUT_SECONDS"] = "60"
    else:
        path = Path(args.local).resolve()
        if not path.exists():
            print(f"no such file: {path}", file=sys.stderr)
            return 2
        os.environ["S3_BUCKET"] = ""
        os.environ["DATABASE_URL"] = f"sqlite:///{path}"

    import app.models  # noqa: F401  (register every table)
    from app.aws import storage
    from app.database import SessionLocal, ensure_schema

    def apply(db) -> dict:
        from sqlalchemy import delete, select

        from app.identity import IdentityError, link_app_account, set_phone
        from app.models.insight import RiskAssessment
        from app.models.mobile import PhoneVerification
        from app.models.patient import Patient

        report: dict = {}
        for hospital_id, name in args.rename_hospital:
            from app.models.hospital import Hospital

            hospital = db.get(Hospital, hospital_id)
            if hospital is None:
                raise SystemExit(f"unknown hospital {hospital_id}")
            hospital.name = name
            hospital.system = None
            db.commit()
            report.setdefault("renamed_hospitals", []).append({"id": hospital_id, "name": name})
        for patient_id, phone in args.set_phone:
            patient = db.get(Patient, patient_id)
            if patient is None:
                raise SystemExit(f"unknown patient {patient_id}")
            report.setdefault("set_phone", []).append(set_phone(db, patient, phone, force=True))
        for target_id, source_id in args.link:
            target, source = db.get(Patient, target_id), db.get(Patient, source_id)
            if target is None or source is None:
                raise SystemExit(f"unknown patient in --link {target_id} {source_id}")
            try:
                # An operator running this named both records explicitly, so
                # the cross-patient guard is theirs to override; the console's
                # one-click path is not.
                report.setdefault("linked", []).append(
                    link_app_account(db, target, source, force=True))
            except IdentityError as e:
                raise SystemExit(f"link refused: {e.detail}")
        if args.revoke_sessions:
            # delete_patient refuses a chart the app is signed in on, because
            # that is how a patient's own history gets destroyed by an
            # operator tidying up. Signing out is the deliberate step that
            # unlocks it — and on its own, what a lost phone needs.
            from app.models.mobile import PatientSession

            for patient_id in args.revoke_sessions:
                if db.get(Patient, patient_id) is None:
                    raise SystemExit(f"unknown patient {patient_id}")
                rows = db.scalars(
                    select(PatientSession).where(
                        PatientSession.patient_id == patient_id,
                        PatientSession.revoked_at.is_(None),
                    )
                ).all()
                for row in rows:
                    row.revoked_at = datetime.now()
                db.commit()
                report.setdefault("revoked_sessions", []).append(
                    {"patient": patient_id, "sessions": len(rows)}
                )
        if args.delete_message:
            # A line sent by mistake, or a probe left by a deploy check. The
            # bytes go with the row: an orphaned object in storage is a
            # patient's photograph nothing accounts for any more.
            from app.models.attachment import Attachment
            from app.models.mobile import Message
            from app.storage import blobs

            for message_id in args.delete_message:
                message = db.get(Message, message_id)
                if message is None:
                    raise SystemExit(f"unknown message {message_id}")
                rows = db.scalars(
                    select(Attachment).where(Attachment.message_id == message_id)
                ).all()
                keys = [r.storage_key for r in rows if not r.storage_key.startswith("pending:")]
                gone = blobs.delete_keys(keys) if keys else 0
                for row in rows:
                    db.delete(row)
                db.delete(message)
                db.commit()
                report.setdefault("deleted_messages", []).append(
                    {"id": message_id, "patient": message.patient_id,
                     "attachments": len(rows), "blobs": gone}
                )
        if args.delete_patient:
            from app.identity import delete_patient

            for patient_id in args.delete_patient:
                patient = db.get(Patient, patient_id)
                if patient is None:
                    raise SystemExit(f"unknown patient {patient_id}")
                report.setdefault("deleted", []).append(delete_patient(db, patient))
        if args.delete_sports_org:
            from app.sports.identity import delete_sports_org

            for org_id in args.delete_sports_org:
                try:
                    report.setdefault("deleted_sports_orgs", []).append(delete_sports_org(db, org_id))
                except ValueError as e:
                    raise SystemExit(str(e)) from None
        if args.prune_assessments:
            keep: list[int] = []
            for pid in db.scalars(select(Patient.id)).all():
                newest = db.scalar(
                    select(RiskAssessment.id).where(RiskAssessment.patient_id == pid)
                    .order_by(RiskAssessment.computed_at.desc(), RiskAssessment.id.desc()).limit(1)
                )
                if newest is not None:
                    keep.append(newest)
            gone = db.execute(delete(RiskAssessment).where(RiskAssessment.id.not_in(keep))).rowcount
            db.commit()
            report["pruned_assessments"] = gone
        if args.restore_demo_phones:
            # The demo personas carry invented 555 numbers, which Sendblue can
            # never accept as verified contacts — so a send to one is always a
            # recorded failure. They are on the charts because a chart with no
            # number on file reads as incomplete; the operator drives SMS
            # through their own verified number instead.
            from app.seed.demo_fill import _build_roster

            legacy, new_personas = _build_roster(date.today())
            intended = {p.spec.id: p.phone for p in (*legacy, *new_personas)}
            applied, skipped = [], []
            for patient_id, phone in sorted(intended.items()):
                patient = db.get(Patient, patient_id)
                if patient is None:
                    skipped.append({"patient": patient_id, "why": "no such record"})
                    continue
                if patient.phone == phone:
                    continue
                holder = db.scalar(select(Patient).where(
                    Patient.phone == phone, Patient.id != patient_id))
                if holder is not None:
                    # One number, one chart: never point two records at one
                    # phone, or an inbound text lands on the wrong one.
                    skipped.append({"patient": patient_id, "why": f"held by {holder.id}"})
                    continue
                previous, patient.phone = patient.phone, phone
                applied.append({"patient": patient_id, "phone": phone, "was": previous})
            db.commit()
            report["restored_demo_phones"] = {"applied": applied, "skipped": skipped}

        if args.dedupe_daily:
            # A provider that re-issued its record id for a day it had already
            # sent left one row per delivery. connectors/ingest.py now treats
            # the day as the identity; this clears what the old keying left.
            from app.models.enums import Granularity
            from app.models.observation import Observation

            rows = db.scalars(
                select(Observation).where(
                    Observation.granularity == Granularity.DAILY_SUMMARY,
                    Observation.deleted_at.is_(None),
                )
            ).all()
            groups: dict[tuple, list] = {}
            for row in rows:
                groups.setdefault((
                    row.patient_id, str(row.source_provider), str(row.metric_type),
                    row.local_date, row.source_device_id or "na", row.side or "na",
                ), []).append(row)
            removed = []
            for key, group in groups.items():
                if len(group) < 2:
                    continue
                group.sort(key=lambda r: (r.ingested_at or datetime.min, r.id), reverse=True)
                for loser in group[1:]:
                    removed.append({"patient": loser.patient_id, "metric": str(loser.metric_type),
                                    "date": str(loser.local_date), "value": loser.value_num})
                    db.delete(loser)
            db.commit()
            report["deduped_daily"] = {"removed": len(removed), "rows": removed[:20]}

        if args.purge_phone_verifications:
            report["purged_phone_verifications"] = db.execute(delete(PhoneVerification)).rowcount
            db.commit()
        if args.mint_token or args.revoke_token:
            # Console credentials (app/console_credentials.py). The mint is the
            # one time the token exists in the clear: it goes into this report
            # and nowhere else, and the row keeps its hash.
            from app.console_credentials import CredentialError, credential_view, mint, revoke

            for spec, label in args.mint_token:
                kind, _, org_id = spec.partition(":")
                try:
                    row, token = mint(db, kind, org_id or None, label)
                except CredentialError as e:
                    raise SystemExit(f"mint refused: {e}")
                entry = {**credential_view(row, db), "token": token}
                if args.dry_run:
                    entry["note"] = "dry run — this token was not stored and will not work"
                report.setdefault("minted_tokens", []).append(entry)
            for credential_id in args.revoke_token:
                try:
                    row = revoke(db, credential_id)
                except CredentialError as e:
                    raise SystemExit(str(e))
                report.setdefault("revoked_tokens", []).append(credential_view(row, db))
        if args.report or True:
            from sqlalchemy import func

            from app.console_credentials import credential_view, list_credentials
            from app.models.mobile import PatientSession
            from app.models.observation import Observation

            report["credentials"] = [credential_view(c, db) for c in list_credentials(db)]

            rows = []
            for p in db.scalars(select(Patient).order_by(Patient.created_at)).all():
                rows.append({
                    "id": p.id, "name": p.name, "hospital": p.hospital_id, "phone": p.phone,
                    "procedure": str(p.procedure_type),
                    "observations": db.scalar(select(func.count(Observation.id)).where(Observation.patient_id == p.id)),
                    "sessions": db.scalar(select(func.count(PatientSession.id)).where(
                        PatientSession.patient_id == p.id, PatientSession.revoked_at.is_(None))),
                    "assessments": db.scalar(select(func.count(RiskAssessment.id)).where(RiskAssessment.patient_id == p.id)),
                })
            report["roster"] = rows
        return report

    if args.bucket and not args.dry_run:
        with storage.write_lock():
            storage.hydrate(force=True)
            ensure_schema()
            with SessionLocal() as db:
                report = apply(db)
            try:
                uploaded = storage.persist(conditional=False)
            except storage.LockLost:
                # Another writer broke this lock while we worked, so our base
                # is stale. Uploading would undo whatever they committed.
                print(
                    "ABORTED: the S3 write lock was taken over while this ran, so nothing "
                    "was uploaded and the database is unchanged. Re-run it.",
                    file=sys.stderr,
                )
                return 3
        report["uploaded"] = uploaded
        report["etag"] = storage._state.get("etag")
    elif args.bucket:
        storage.hydrate(force=True)
        ensure_schema()
        with SessionLocal() as db:
            report = apply(db)
        report["uploaded"] = False
        report["note"] = f"dry run — nothing uploaded; local copy at {workdir}/recovery.db"
    else:
        ensure_schema()
        with SessionLocal() as db:
            report = apply(db)
        report["uploaded"] = False
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
