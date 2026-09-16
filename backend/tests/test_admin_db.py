"""The operator tool that edits a deployed database.

It runs as its own process against its own engine, so it is exercised the
way an operator runs it: a subprocess over a real SQLite file. These are
the destructive paths — a deleted line, a revoked session, a deleted chart
— and they are worth a test precisely because nothing else catches a
mistake in them before it has already happened to production.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "admin_db.py"

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture()
def deployed(tmp_path, monkeypatch):
    """A standalone database file, seeded, with one photo on one thread."""
    from app.database import Base
    from app.models.attachment import Attachment
    from app.models.mobile import Message, PatientSession
    from app.seed.patients import full_roster
    from app.seed.seed import seed_core
    from app.storage import blobs

    monkeypatch.setenv("ATTACHMENT_DIR", str(tmp_path / "blobs"))
    db_path = tmp_path / "recovery.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        hospitals, patients = full_roster()
        seed_core(db, date.today(), roster=(hospitals, patients))
        pid = patients[0].id
        stored = blobs.put(blobs.new_key(pid, "image/jpeg"), JPEG, "image/jpeg")
        message = Message(patient_id=pid, sender="patient", channel="app", text="look at this")
        db.add(message)
        db.flush()
        db.add(Attachment(
            patient_id=pid, message_id=message.id, uploaded_by="patient", source="app",
            content_type="image/jpeg", byte_size=stored.byte_size, sha256=stored.sha256,
            storage_key=stored.key, confirmed_at=message.created_at,
        ))
        db.add(PatientSession(patient_id=pid, token_hash="x" * 64, device_name="iPhone"))
        db.commit()
        ids = (pid, message.id, stored.key)
    engine.dispose()
    return db_path, ids, Session, tmp_path


def _run(db_path, tmp_path, *flags) -> dict:
    env = {**os.environ, "ATTACHMENT_DIR": str(tmp_path / "blobs")}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--local", str(db_path), *flags],
        capture_output=True, text=True, env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout[proc.stdout.index("{") :])


def test_deleting_a_line_takes_its_files_and_their_bytes(deployed):
    from app.models.attachment import Attachment
    from app.models.mobile import Message
    from app.storage import blobs

    db_path, (pid, message_id, key), Session, tmp_path = deployed
    report = _run(db_path, tmp_path, "--delete-message", str(message_id))
    assert report["deleted_messages"] == [
        {"id": message_id, "patient": pid, "attachments": 1, "blobs": 1}
    ]
    with Session() as db:
        assert db.get(Message, message_id) is None
        assert db.scalars(db.query(Attachment).statement).all() == []
    # An object nothing points at any more is a patient's photograph nobody
    # accounts for, so the bytes go with the row.
    os.environ["ATTACHMENT_DIR"] = str(tmp_path / "blobs")
    assert blobs.stat(key) is None


def test_a_chart_the_app_is_signed_in_on_is_not_deleted_by_accident(deployed):
    db_path, (pid, _message_id, _key), Session, tmp_path = deployed
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--local", str(db_path), "--delete-patient", pid],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode != 0
    assert "signed in on the app" in proc.stderr

    # Signing the app out is the deliberate step that unlocks it — and on
    # its own, what a lost phone needs.
    report = _run(db_path, tmp_path, "--revoke-sessions", pid, "--delete-patient", pid)
    assert report["revoked_sessions"] == [{"patient": pid, "sessions": 1}]
    assert report["deleted"][0]["deleted"] == pid
    assert pid not in [row["id"] for row in report["roster"]]


def test_a_report_changes_nothing(deployed):
    db_path, (pid, message_id, _key), Session, tmp_path = deployed
    from app.models.mobile import Message

    before = _run(db_path, tmp_path, "--report")
    assert any(row["id"] == pid for row in before["roster"])
    assert "deleted" not in before and "revoked_sessions" not in before
    with Session() as db:
        assert db.get(Message, message_id) is not None
