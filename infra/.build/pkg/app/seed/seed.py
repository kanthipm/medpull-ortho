"""Seed the database with the deterministic demo roster.

    uv run python -m app.seed.seed --reset

--reset drops and recreates the schema first. After seeding raw data the
engine pipeline and insight caches are warmed so the first page load is
instant.
"""

import argparse
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

import app.models  # noqa: F401 — register all tables on Base.metadata
from app.config import settings
from app.connectors.ingest import ingest_observations
from app.database import Base, SessionLocal, engine
from app.models import (
    AdherenceRecord,
    AdherenceTask,
    CareTeamMember,
    Checkin,
    CheckinMessage,
    Device,
    NotificationPreference,
    Patient,
)
from app.models.enums import NotificationChannel
from app.seed import adherence as adh
from app.seed.conversations import CONVERSATIONS
from app.seed.generators import generate_patient_observations
from app.seed.patients import CARE_TEAM, PATIENTS
from app.seed.scenarios import get_scenario


def seed_core(db: Session, today: date) -> dict[str, int]:
    counts: dict[str, int] = {}

    for ct in CARE_TEAM:
        db.add(CareTeamMember(id=ct.id, name=ct.name, role=ct.role))
    counts["care_team"] = len(CARE_TEAM)

    for spec in PATIENTS:
        surgery = today - timedelta(days=spec.postop_day)
        db.add(
            Patient(
                id=spec.id,
                name=spec.name,
                initials=spec.initials,
                age=spec.age,
                sex=spec.sex,
                procedure_type=spec.procedure,
                procedure_display=spec.procedure_display,
                surgery_date=surgery,
                discharge_date=surgery + timedelta(days=spec.discharge_offset),
                surgeon_id=spec.surgeon_id,
                assigned_provider_id=spec.surgeon_id,
            )
        )
        db.add(
            Device(
                id=f"dev_{spec.id}",
                patient_id=spec.id,
                source_provider=spec.provider,
                device_model=spec.device_model,
                connected_at=datetime.combine(surgery - timedelta(days=14), time(10, 0)),
                last_sync_at=datetime.combine(today, time(7, 30)),
            )
        )
    counts["patients"] = len(PATIENTS)
    db.commit()

    # observations via the same path real integrations will use
    total_obs = 0
    for spec in PATIENTS:
        obs = generate_patient_observations(spec, get_scenario(spec.id), today)
        ingested, _ = ingest_observations(db, obs)
        total_obs += ingested
    counts["observations"] = total_obs

    # check-ins
    n_checkins = 0
    for spec in PATIENTS:
        for days_ago, hour, messages in CONVERSATIONS.get(spec.id, []):
            checkin = Checkin(
                patient_id=spec.id,
                occurred_at=datetime.combine(today - timedelta(days=days_ago), time(hour, 12)),
                channel="app",
            )
            db.add(checkin)
            db.flush()
            for seq, (who, text) in enumerate(messages):
                db.add(CheckinMessage(checkin_id=checkin.id, seq=seq, who=who, text=text))
            n_checkins += 1
    counts["checkins"] = n_checkins

    # adherence tasks + last-14-day records
    n_records = 0
    for spec in PATIENTS:
        specs = adh.TASKS.get(spec.id, [])
        task_rows = []
        for t in specs:
            row = AdherenceTask(
                patient_id=spec.id, title=t.title, why=t.why, verified_by=t.verified_by
            )
            db.add(row)
            task_rows.append(row)
        db.flush()
        statuses = adh.daily_statuses(spec.id, len(task_rows))
        for day_offset, day_statuses in enumerate(statuses):
            record_date = today - timedelta(days=len(statuses) - 1 - day_offset)
            # no adherence expectations before surgery
            if record_date < today - timedelta(days=spec.postop_day):
                continue
            for task_row, status in zip(task_rows, day_statuses):
                db.add(
                    AdherenceRecord(
                        patient_id=spec.id, task_id=task_row.id, date=record_date, status=status
                    )
                )
                n_records += 1
    counts["adherence_records"] = n_records

    # default notification preferences: in-app on, SMS/email present but off
    for ct in CARE_TEAM:
        db.add(NotificationPreference(recipient_id=ct.id, channel=NotificationChannel.IN_APP, enabled=True))
        db.add(NotificationPreference(recipient_id=ct.id, channel=NotificationChannel.SMS, enabled=False))
        db.add(NotificationPreference(recipient_id=ct.id, channel=NotificationChannel.EMAIL, enabled=False))
    db.commit()

    # RTM state (new tables only — never observations; golden tiers depend on them)
    from app.seed.rtm import seed_rtm

    counts.update(seed_rtm(db, today))
    return counts


def warm_engine_and_insights(db: Session) -> None:
    from app.engine.pipeline import run_all

    assessments = run_all(db)
    print(f"  engine: {len(assessments)} risk assessments")

    from app.llm.insights import get_daily_briefing, get_patient_insight
    from app.models.enums import InsightKind

    for spec in PATIENTS:
        for kind in (
            InsightKind.WORKLIST_REASON,
            InsightKind.PATIENT_SUMMARY,
            InsightKind.SUGGESTED_ACTIONS,
        ):
            get_patient_insight(db, kind, spec.id)
    get_daily_briefing(db)
    print("  insights: caches warmed")


def run_seed(reset: bool = False) -> dict[str, int]:
    """Seed the configured database and warm its caches. Returns the row counts.

    Split out of main() so the Lambda seed action can drive it directly instead
    of faking command-line arguments.
    """
    if settings.database_url.startswith("sqlite:///"):
        from pathlib import Path

        Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )

    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    today = date.today()
    db = SessionLocal()
    try:
        counts = seed_core(db, today)
        for k, v in counts.items():
            print(f"  {k}: {v}")
        try:
            warm_engine_and_insights(db)
        except ImportError as e:
            print(f"  (engine/insights not available yet: {e})")
        print("Seed complete.")
        return counts
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop and recreate the schema first")
    args = parser.parse_args()
    run_seed(reset=args.reset)


if __name__ == "__main__":
    main()
