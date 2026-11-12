#!/usr/bin/env python
"""Run the showcase fill against the DEPLOYED demo database, safely.

    uv run python scripts/push_demo_fill.py --bucket <s3 bucket> --dry-run
    uv run python scripts/push_demo_fill.py --bucket <s3 bucket>
    uv run python scripts/push_demo_fill.py --local /path/to/copy.db

``app.seed.showcase.fill_showcase`` anchors every demo org to today: the
clinic personas and the H.I.R.T. lifters, the sports rosters and the
Personal members. Surgery dates, observations, check-ins, the exercise
calendar and the athletes' streams all run up to the current date instead
of stopping on the day the database was last filled, so the tiers and the
readiness scores come back to life instead of every chart ageing into
MISSING_DATA. On the demo stack the same fill runs each morning as the
Lambda action ``showcase_fill``; this script is the same thing by hand.

It takes the same S3 write lock the API takes, hydrates a fresh copy,
fills it, and persists unconditionally — the pattern scripts/admin_db.py
uses, for the same reason: an out-of-band upload that skips the lock will
either lose to a concurrent request or silently undo one.

Before a real run it copies the current object to
``db/backups/recovery-<utc timestamp>.db`` server-side and prints the key.

What it never touches: any chart the showcase does not author. The fill
writes its own personas by id and nothing else, so a real person who
enrolled, the protected charts (``app.seed.demo_fill.PROTECTED``) and an
onboarding attempt somebody abandoned are all left exactly as they are. On
the personas themselves it keeps app sessions and any phone number that is
not a 555 placeholder (a presenter's own, bound through ``/api/demo/phone``).

The fill is for the demo stack, and this laptop cannot ask a bucket which
stack it belongs to. So a bucket whose name does not say ``demo`` is
refused unless ``--force`` is given; ``--local`` fills whatever file it is
handed.

``--dry-run`` hydrates, fills a local copy and uploads nothing, printing
where the filled copy landed so the tiers can be checked before committing.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def _backup(bucket: str, key: str) -> str:
    """Server-side copy of the live object, before anything is rewritten."""
    from app.aws.storage import client

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_key = f"db/backups/recovery-{stamp}.db"
    client().copy_object(
        Bucket=bucket, Key=backup_key, CopySource={"Bucket": bucket, "Key": key}
    )
    return backup_key


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--bucket", help="S3 bucket holding db/recovery.db (the deployed database)")
    where.add_argument("--local", help="fill this SQLite file in place, no S3")
    ap.add_argument("--db-key", default="db/recovery.db")
    ap.add_argument("--dry-run", action="store_true",
                    help="hydrate and fill a local copy; upload nothing")
    ap.add_argument("--force", action="store_true",
                    help="fill a bucket whose name does not say it is the demo stack's")
    ap.add_argument("--warm", action="store_true",
                    help="fill the Groq insight caches after the fill (slow, rate-limited)")
    ap.add_argument("--pause", type=float, default=12.0,
                    help="seconds between Groq calls while warming (default 12: the free "
                         "tier's tokens-per-minute limit trips after ~9 calls)")
    ap.add_argument("--no-persona-phones", action="store_true",
                    help="leave the demo patients without a phone number")
    args = ap.parse_args()

    if args.bucket and "demo" not in args.bucket.lower() and not args.force:
        print(
            f"refusing: {args.bucket} does not look like the demo stack's bucket (no 'demo' in "
            "its name), and the showcase fill rewrites every persona's chart. Pass --force if "
            "this really is a demo database.",
            file=sys.stderr,
        )
        return 2

    # Environment before any app import: app.database binds its engine at
    # import time, and the fill must write to the file we are holding.
    os.environ["WARM_CACHES_ON_STARTUP"] = "false"
    for key in ("JUNCTION_API_KEY", "JUNCTION_WEBHOOK_SECRET", "SENDBLUE_API_KEY",
                "SENDBLUE_API_SECRET", "SENDBLUE_WEBHOOK_SECRET", "CARE_TEAM_PHONES"):
        os.environ[key] = ""
    if not args.warm:
        # Nothing may reach a model on a plain fill: the engine re-runs for
        # every patient it touches, and a Groq call per patient is how the
        # free tier's rate limit gets tripped.
        os.environ["GROQ_API_KEY"] = ""
        os.environ["OLLAMA_URL"] = ""

    if args.local:
        db_path = Path(args.local).expanduser().resolve()
        if not db_path.exists():
            print(f"no such file: {db_path}", file=sys.stderr)
            return 2
        # No S3 in this process: the file on disk is the database.
        os.environ["S3_BUCKET"] = ""
    else:
        workdir = tempfile.mkdtemp(prefix="medpull-demofill-")
        db_path = Path(workdir) / "recovery.db"
        os.environ["S3_BUCKET"] = args.bucket
        os.environ["S3_DB_KEY"] = args.db_key
        # A full fill regenerates every persona and re-runs the engine for
        # each: minutes, not the API's seconds.
        os.environ["LOCK_TTL_SECONDS"] = "900"
        os.environ["LOCK_ACQUIRE_TIMEOUT_SECONDS"] = "60"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    def fill() -> dict:
        """The showcase fill on the file we are holding. Forced: which stack
        this is was settled above, and this process's own DEMO_MODE says
        nothing about the bucket's."""
        import app.models  # noqa: F401 — register every table
        from app.database import SessionLocal, ensure_schema
        from app.seed.showcase import fill_showcase

        ensure_schema()
        with SessionLocal() as db:
            report = fill_showcase(
                db, force=True, suppress_phones=args.no_persona_phones, warm=args.warm,
                pause=args.pause, say=print,
            )
        print(
            f"\n{len(report['clinic']['personas'])} clinic personas, "
            f"{report['sports'].get('athletes', 0)} athletes, {len(report['personal'])} members; "
            f"put back {report['kept']['sessions']} session(s) and {report['kept']['phones']} "
            f"bound phone(s) the refill would have dropped; {report['consents']} consent "
            "row(s) added"
        )
        if report["clinic"]["skipped"]:
            print(f"skipped: {report['clinic']['skipped']}")
        return report

    if args.local:
        fill()
        print(f"\nfilled in place: {db_path}")
        return 0

    from app.aws import storage

    if args.dry_run:
        storage.hydrate(force=True)
        fill()
        print(f"\ndry run — nothing uploaded. Filled copy: {db_path}")
        return 0

    backup_key = _backup(args.bucket, args.db_key)
    print(f"backup: s3://{args.bucket}/{backup_key}")

    with storage.write_lock():
        storage.hydrate(force=True)
        fill()
        try:
            uploaded = storage.persist(conditional=False)
        except storage.LockLost:
            # Another writer broke this lock while the fill ran, so this copy
            # is built on a stale base and uploading it would undo their work.
            print(
                "ABORTED: the S3 write lock was taken over while this ran, so nothing "
                f"was uploaded. The database is unchanged; the backup at {backup_key} "
                "is the state from before this attempt. Re-run it.",
                file=sys.stderr,
            )
            return 3

    print(f"\nuploaded: {uploaded}  etag: {storage._state.get('etag')}")
    print(f"rollback: aws s3 cp s3://{args.bucket}/{backup_key} "
          f"s3://{args.bucket}/{args.db_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
