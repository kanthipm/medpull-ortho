#!/usr/bin/env python
"""Placeholder demonstration clips for the HIRT demo.

    uv run python scripts/seed_hirt_media.py --local /path/to/copy.db
    uv run python scripts/seed_hirt_media.py --bucket <demo data bucket> --dry-run
    uv run python scripts/seed_hirt_media.py --bucket <demo data bucket>

The seed writes the lifters' schedule (app/seed/hirt.py) but no clips: bytes
need an object store. This makes a short silent MP4 title card for every
exercise HIRT's schedule uses — 720×1280, six seconds, the sage #3f6b5a
background, "Dr. Ashley Gregg · <exercise> · demonstration" in white when
this ffmpeg can draw text, a plain sage card when it cannot — stores each
under a clinic key with ``blobs.put`` and writes the approved ``ExerciseMedia``
row for ``hirt``; then three patient return clips ("Cole Whitaker · Step-Ups ·
day 12") as attachments linked to a done assignment and to a line on the
lifter's thread, the way the app's completion writes them. Idempotent: an
exercise that already has a clinic clip is skipped, so is an assignment that
already carries one, and a return clip the script made before is relinked
rather than rendered again. Real footage replaces these through the
console's upload button.

``--bucket`` works the way scripts/admin_db.py does: under the S3 write
lock, on a fresh hydrate, with an unconditional persist at the end; the
bytes go to the same bucket, under ``attachments/``. ``--dry-run`` hydrates
and renders, writes rows into the local copy and uploads nothing — bytes
included — so it only shows what a real run would do. ``--local`` works on
a SQLite file in place, writing the bytes to ``ATTACHMENT_DIR`` (or
``--attachment-dir``, or backend/data/attachments, where a laptop API
serves them from). Never point ``--local`` at backend/data/recovery.db.

Every provider is switched off in this process, so the only side effects
are the database file and the objects beside it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

CLINIC = "hirt"
THERAPIST = "ct_gregg"
THERAPIST_NAME = "Dr. Ashley Gregg"
SAGE = "0x3f6b5a"
WIDTH, HEIGHT, SECONDS = 720, 1280, 6
# The lifters who sent a clip back, and of which exercise: the latest done
# day of each gets it.
RETURN_CLIPS = (
    ("hirt-cole", "functional_step_ups"),
    ("hirt-tessa", "ankle_calf_raises"),
    ("hirt-june", "functional_sit_to_stand"),
)


def find_ffmpeg(explicit: str | None) -> str:
    for candidate in (explicit, "/opt/homebrew/bin/ffmpeg", shutil.which("ffmpeg")):
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("ffmpeg not found; pass --ffmpeg /path/to/ffmpeg")


def has_drawtext(ffmpeg: str) -> bool:
    """Homebrew's ffmpeg is built without libfreetype, so the title text is
    drawn only where the filter exists; the card is plain sage otherwise."""
    out = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True)
    return " drawtext " in out.stdout


def render_clip(ffmpeg: str, text: str, *, drawtext: bool) -> bytes:
    """A silent H.264 title card as MP4 bytes, faststart so a phone can play
    it as it loads."""
    with tempfile.TemporaryDirectory(prefix="hirt-clip-") as tmp:
        out = Path(tmp) / "clip.mp4"
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={SAGE}:s={WIDTH}x{HEIGHT}:d={SECONDS}:r=24",
        ]
        if drawtext:
            safe = text.replace("\\", "").replace("'", "\\'").replace(":", "\\:")
            cmd += ["-vf", (f"drawtext=text='{safe}':fontcolor=white:fontsize=44:"
                            "x=(w-text_w)/2:y=(h-text_h)/2")]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
                str(out)]
        subprocess.run(cmd, check=True)
        return out.read_bytes()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--bucket", help="S3 bucket holding db/recovery.db (the demo database)")
    where.add_argument("--local", help="operate on this SQLite file in place, no S3")
    ap.add_argument("--db-key", default="db/recovery.db")
    ap.add_argument("--dry-run", action="store_true",
                    help="hydrate, render and apply locally; upload nothing, bytes included")
    ap.add_argument("--attachment-dir",
                    help="with --local: where the bytes go (default ATTACHMENT_DIR, else "
                         "backend/data/attachments)")
    ap.add_argument("--ffmpeg", help="path to ffmpeg (default /opt/homebrew/bin/ffmpeg or PATH)")
    args = ap.parse_args()

    # Environment before any app import: app.database binds the engine at import.
    for key in ("GROQ_API_KEY", "JUNCTION_API_KEY", "JUNCTION_WEBHOOK_SECRET", "SENDBLUE_API_KEY",
                "SENDBLUE_API_SECRET", "SENDBLUE_WEBHOOK_SECRET", "OLLAMA_URL", "CARE_TEAM_PHONES"):
        os.environ[key] = ""
    os.environ["WARM_CACHES_ON_STARTUP"] = "false"
    workdir = None
    if args.bucket:
        workdir = tempfile.mkdtemp(prefix="medpull-hirt-media-")
        os.environ["S3_BUCKET"] = args.bucket
        os.environ["S3_DB_KEY"] = args.db_key
        os.environ["DATABASE_URL"] = f"sqlite:///{workdir}/recovery.db"
        os.environ["LOCK_TTL_SECONDS"] = "300"
        os.environ["LOCK_ACQUIRE_TIMEOUT_SECONDS"] = "60"
    else:
        path = Path(args.local).resolve()
        if not path.exists():
            print(f"no such file: {path}", file=sys.stderr)
            return 2
        if path == (BACKEND / "data" / "recovery.db").resolve():
            print("refusing to touch backend/data/recovery.db; copy it first", file=sys.stderr)
            return 2
        os.environ["S3_BUCKET"] = ""
        os.environ["DATABASE_URL"] = f"sqlite:///{path}"
        if args.attachment_dir:
            os.environ["ATTACHMENT_DIR"] = str(Path(args.attachment_dir).resolve())

    ffmpeg = find_ffmpeg(args.ffmpeg)
    drawtext = has_drawtext(ffmpeg)

    import app.models  # noqa: F401  (register every table)
    from app.aws import storage
    from app.database import SessionLocal, ensure_schema

    def apply(db, *, write_bytes: bool) -> dict:
        from sqlalchemy import select

        from app.hep.catalog import ensure_catalog
        from app.hep.models import Exercise, ExerciseAssignment, ExerciseMedia
        from app.hep.schedule import completion_line
        from app.hep.service import clinic_clips
        from app.models.attachment import Attachment
        from app.models.mobile import Message
        from app.models.patient import Patient
        from app.seed import hirt
        from app.storage import blobs

        ensure_catalog(db)
        now = datetime.now()
        report: dict = {
            "ffmpeg": ffmpeg, "drawtext": drawtext, "bytes_written": write_bytes,
            "clinic_clips": [], "skipped_exercises": [], "return_clips": [], "skipped_lifters": [],
        }

        def store(key: str, data: bytes) -> tuple[int, str]:
            blobs.sniff(data[:1024], "video/mp4")
            if write_bytes:
                stored = blobs.put(key, data, "video/mp4")
                return stored.byte_size, stored.sha256
            return len(data), hashlib.sha256(data).hexdigest()

        keys = sorted({item.key for items in hirt.SCHEDULE.values() for item in items})
        exercises = {e.key: e for e in db.scalars(select(Exercise).where(Exercise.key.in_(keys)))}
        missing = sorted(set(keys) - set(exercises))
        if missing:
            raise SystemExit(f"catalog is missing {', '.join(missing)}")
        own = clinic_clips(db, CLINIC)
        for key in keys:
            exercise = exercises[key]
            if exercise.id in own:
                report["skipped_exercises"].append(key)
                continue
            data = render_clip(ffmpeg, f"{THERAPIST_NAME} · {exercise.title} · demonstration",
                               drawtext=drawtext)
            storage_key = blobs.new_clinic_key(CLINIC, "video/mp4")
            size, _sha = store(storage_key, data)
            row = ExerciseMedia(
                hospital_id=CLINIC, exercise_id=exercise.id, kind="video", storage_key=storage_key,
                content_type="video/mp4", size_bytes=size, width=WIDTH, height=HEIGHT,
                duration_ms=SECONDS * 1000, approval_status="approved", reviewed_by=THERAPIST,
                reviewed_at=now, uploaded_by=THERAPIST,
            )
            db.add(row)
            db.flush()
            report["clinic_clips"].append(
                {"exercise": key, "media_id": row.id, "key": storage_key, "bytes": size})
        db.commit()

        for patient_id, key in RETURN_CLIPS:
            patient = db.get(Patient, patient_id)
            exercise = exercises[key]
            if patient is None:
                report["skipped_lifters"].append({"patient": patient_id, "why": "not on this roster"})
                continue
            row = db.scalar(
                select(ExerciseAssignment).where(
                    ExerciseAssignment.patient_id == patient_id,
                    ExerciseAssignment.exercise_id == exercise.id,
                    ExerciseAssignment.status == "done",
                ).order_by(ExerciseAssignment.scheduled_for.desc(), ExerciseAssignment.id.desc())
            )
            if row is None:
                report["skipped_lifters"].append({"patient": patient_id, "why": f"no done {key}"})
                continue
            if row.video_attachment_id:
                report["skipped_lifters"].append(
                    {"patient": patient_id, "why": "that day already has a clip"})
                continue
            first = db.scalar(
                select(ExerciseAssignment.scheduled_for)
                .where(ExerciseAssignment.patient_id == patient_id)
                .order_by(ExerciseAssignment.scheduled_for).limit(1)
            )
            program_day = (row.scheduled_for - first).days if first else 0
            filename = f"{patient_id}-{key.replace('_', '-')}-day-{program_day}.mp4"
            at = row.completed_at or now
            # A clip this script made on an earlier run survives a refill as
            # an attachment row with nothing pointing at it; relink it rather
            # than leaving a second object behind.
            attachment = db.scalar(
                select(Attachment).where(
                    Attachment.patient_id == patient_id, Attachment.filename == filename,
                    Attachment.deleted_at.is_(None), Attachment.confirmed_at.is_not(None),
                ).order_by(Attachment.id.desc())
            )
            rendered = attachment is None
            if attachment is None:
                data = render_clip(
                    ffmpeg, f"{patient.name} · {exercise.title} · day {program_day}",
                    drawtext=drawtext,
                )
                storage_key = blobs.new_key(patient_id, "video/mp4")
                size, sha = store(storage_key, data)
                attachment = Attachment(
                    patient_id=patient_id, uploaded_by="patient", uploaded_by_id=None, source="app",
                    content_type="video/mp4", byte_size=size, sha256=sha, storage_key=storage_key,
                    filename=filename, created_at=at, confirmed_at=at,
                )
                db.add(attachment)
                db.flush()
            message = db.get(Message, attachment.message_id) if attachment.message_id else None
            if message is None:
                message = Message(
                    patient_id=patient_id, sender="patient", channel="app",
                    text=completion_line(exercise.title, row.pain_after, row.note,
                                         effort=row.effort),
                    created_at=at,
                    read_by_care_team_at=at + timedelta(hours=1),
                )
                db.add(message)
                db.flush()
                attachment.message_id = message.id
            row.video_attachment_id = attachment.id
            row.updated_at = max(row.updated_at or at, at)
            db.commit()
            report["return_clips"].append({
                "patient": patient_id, "exercise": key, "day": row.scheduled_for.isoformat(),
                "assignment_id": row.id, "attachment_id": attachment.id, "message_id": message.id,
                "rendered": rendered,
            })
        return report

    if args.bucket and not args.dry_run:
        with storage.write_lock():
            storage.hydrate(force=True)
            ensure_schema()
            with SessionLocal() as db:
                report = apply(db, write_bytes=True)
            try:
                uploaded = storage.persist(conditional=False)
            except storage.LockLost:
                print(
                    "ABORTED: the S3 write lock was taken over while this ran, so the database "
                    "was not uploaded. The clips already stored have rows only in the discarded "
                    "copy; re-run it.",
                    file=sys.stderr,
                )
                return 3
        report["uploaded"] = uploaded
        report["etag"] = storage._state.get("etag")
    elif args.bucket:
        storage.hydrate(force=True)
        ensure_schema()
        with SessionLocal() as db:
            report = apply(db, write_bytes=False)
        report["uploaded"] = False
        report["note"] = f"dry run — nothing uploaded; local copy at {workdir}/recovery.db"
    else:
        ensure_schema()
        with SessionLocal() as db:
            report = apply(db, write_bytes=True)
        from app.storage import blobs

        report["uploaded"] = False
        report["attachment_dir"] = str(blobs.local_root())
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
