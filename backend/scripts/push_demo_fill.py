#!/usr/bin/env python
"""Run app.seed.demo_fill against the DEPLOYED database, safely.

    uv run python scripts/push_demo_fill.py --bucket <s3 bucket> --dry-run
    uv run python scripts/push_demo_fill.py --bucket <s3 bucket>
    uv run python scripts/push_demo_fill.py --local /path/to/copy.db

demo_fill rebuilds the demo roster anchored to today, which is what a
filmed demo needs the morning it is filmed: surgery dates, observations,
check-ins and adherence all run up to the current date instead of stopping
on the day the database was last filled, so the risk tiers come back to
life instead of every patient ageing into MISSING_DATA.

It takes the same S3 write lock the API takes, hydrates a fresh copy,
fills it, and persists unconditionally — the pattern scripts/admin_db.py
uses, for the same reason: an out-of-band upload that skips the lock will
either lose to a concurrent request or silently undo one.

Before a real run it copies the current object to
``db/backups/recovery-<utc timestamp>.db`` server-side and prints the key.

What it never touches: the protected charts (``app.seed.demo_fill.PROTECTED``
— Steve's record and the Guest slot) and any patient who has since enrolled
with a phone or an app session. demo_fill enforces that itself; this script
only carries it to S3.

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
    ap.add_argument("--warm", action="store_true",
                    help="fill the Groq insight caches after the fill (slow, rate-limited)")
    ap.add_argument("--pause", type=float, default=12.0,
                    help="seconds between Groq calls while warming (default 12: the free "
                         "tier's tokens-per-minute limit trips after ~9 calls)")
    ap.add_argument("--no-persona-phones", action="store_true",
                    help="leave the demo patients without a phone number")
    args = ap.parse_args()

    # Environment before any app import: app.database binds its engine at
    # import time, and demo_fill must write to the file we hydrated.
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
        db_path = Path(args.local).resolve()
        if not db_path.exists():
            print(f"no such file: {db_path}", file=sys.stderr)
            return 2
    else:
        workdir = tempfile.mkdtemp(prefix="medpull-demofill-")
        db_path = Path(workdir) / "recovery.db"
        os.environ["S3_BUCKET"] = args.bucket
        os.environ["S3_DB_KEY"] = args.db_key
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        # A full fill regenerates every demo patient and re-runs the engine
        # for each: minutes, not the API's seconds.
        os.environ["LOCK_TTL_SECONDS"] = "900"
        os.environ["LOCK_ACQUIRE_TIMEOUT_SECONDS"] = "60"

    def fill() -> None:
        """demo_fill's own CLI, pointed at the file we are holding."""
        from app.seed import demo_fill

        argv = ["demo_fill", "--db", str(db_path), "--pause", str(args.pause)]
        if args.warm:
            argv.append("--warm")
        if args.no_persona_phones:
            argv.append("--no-persona-phones")
        saved, sys.argv = sys.argv, argv
        try:
            demo_fill.main()
        finally:
            sys.argv = saved

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
