"""delete_patient leaves nothing behind in any table that names the patient,
whichever facet the row belongs to, and unhooks a paired row."""

from datetime import date

from sqlalchemy import select, text

from app.identity import delete_patient
from app.models import Patient
from app.models.personal import Consent, Entitlement, PersonalCredential
from app.models.sports import SportsProfile, SportsSession, SportsWellness


def _clone(db, source_id: str, **overrides) -> Patient:
    src = db.get(Patient, source_id)
    cols = {c.name: getattr(src, c.name) for c in Patient.__table__.columns}
    cols.update(overrides)
    row = Patient(**cols)
    db.add(row)
    db.flush()
    return row


def _rows(db, table: str, pid: str) -> int:
    return db.execute(
        text(f"select count(*) from {table} where patient_id = :pid"), {"pid": pid}
    ).scalar()


def test_delete_patient_sweeps_sports_and_personal_tables_and_unlinks_the_pair(db):
    athlete = _clone(
        db, "reyes", id="sweep-athlete", name="Sweep Athlete", account_kind="sports",
        hospital_id=None, phone=None, linked_patient_id=None,
    )
    space = _clone(
        db, "reyes", id="sweep-space", name="Sweep Space", account_kind="personal",
        hospital_id=None, phone=None, linked_patient_id="sweep-athlete",
    )
    db.add_all([
        SportsProfile(patient_id=athlete.id, sport="basketball"),
        SportsSession(patient_id=athlete.id, date=date.today(), minutes=60, rpe=7),
        SportsWellness(patient_id=athlete.id, date=date.today(), key="sleep_quality", value=7),
        PersonalCredential(patient_id=athlete.id, email="sweep@example.com", password_hash="x"),
        Consent(patient_id=athlete.id, version="2026-09-26.1", text_sha256="abc"),
        Entitlement(patient_id=athlete.id, source="trial"),
    ])
    db.commit()
    for table in ("sports_profiles", "sports_sessions", "sports_wellness",
                  "personal_credentials", "consents", "entitlements"):
        assert _rows(db, table, athlete.id) == 1, table

    result = delete_patient(db, db.get(Patient, athlete.id))

    assert result["deleted"] == athlete.id
    rows = result["rows"]
    for table in ("sports_profiles", "sports_sessions", "sports_wellness",
                  "personal_credentials", "consents", "entitlements"):
        assert rows[table] == 1, table
        assert _rows(db, table, athlete.id) == 0, table
    assert rows["unlinked"] == 1
    assert db.get(Patient, athlete.id) is None
    db.expire_all()
    assert db.get(Patient, space.id).linked_patient_id is None

    # Nothing anywhere still names the row.
    for (table,) in db.execute(text("select name from sqlite_master where type = 'table'")):
        columns = {r[1] for r in db.execute(text(f'pragma table_info("{table}")'))}
        if "patient_id" in columns:
            assert _rows(db, table, athlete.id) == 0, table

    db.delete(db.get(Patient, space.id))
    db.commit()
    assert db.scalars(select(Patient.id).where(Patient.id.like("sweep-%"))).all() == []
