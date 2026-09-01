from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import NotificationChannel, NotificationStatus
from app.models.notification import Notification, NotificationPreference
from app.models.patient import CareTeamMember, Patient

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
def list_notifications(status: str = "all", db: Session = Depends(get_db)) -> dict:
    query = (
        select(Notification, Patient.name)
        .join(Patient, Patient.id == Notification.patient_id)
        .where(Notification.channel == NotificationChannel.IN_APP)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    if status == "unread":
        query = query.where(Notification.status == NotificationStatus.UNREAD)
    rows = db.execute(query).all()
    return {
        "notifications": [
            {
                "id": n.id,
                "patient_id": n.patient_id,
                "patient_name": name,
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "channel": str(n.channel),
                "status": str(n.status),
                "created_at": n.created_at.isoformat(),
            }
            for n, name in rows
        ]
    }


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db)) -> dict:
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Unknown notification")
    notification.status = NotificationStatus.READ
    notification.read_at = datetime.now()
    db.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db)) -> dict:
    """Clears the bell, so it clears exactly what the bell lists: an out-of-band
    row marked read here would retire an alert nobody was ever shown."""
    unread = db.scalars(
        select(Notification).where(
            Notification.channel == NotificationChannel.IN_APP,
            Notification.status == NotificationStatus.UNREAD,
        )
    ).all()
    for n in unread:
        n.status = NotificationStatus.READ
        n.read_at = datetime.now()
    db.commit()
    return {"ok": True, "count": len(unread)}


class PreferenceUpdate(BaseModel):
    channel: NotificationChannel
    enabled: bool
    min_priority: str = "high"


# Channels with a real delivery path. SmsChannel/EmailChannel only log a line
# and persist a `sent_stub` row that list_notifications never returns, so
# enabling one would promise an alert that is delivered nowhere and readable
# nowhere.
AVAILABLE_CHANNELS = {NotificationChannel.IN_APP}


def _recipients(db: Session, recipient_id: str | None) -> list[str]:
    """Preferences are stored per care-team member, and there is no signed-in
    user to infer one from. An explicit `recipient_id` addresses that member;
    omitting it addresses the whole care team, which is what the practice-wide
    settings screen means — but it says so instead of fanning out by accident."""
    if recipient_id is not None:
        if db.get(CareTeamMember, recipient_id) is None:
            raise HTTPException(status_code=404, detail=f"Unknown recipient: {recipient_id}")
        return [recipient_id]
    return list(db.scalars(select(CareTeamMember.id).order_by(CareTeamMember.id)).all())


def _preferences_response(db: Session, recipients: list[str]) -> list[dict]:
    prefs = db.scalars(
        select(NotificationPreference)
        .where(NotificationPreference.recipient_id.in_(recipients))
        .order_by(NotificationPreference.recipient_id, NotificationPreference.id)
    ).all()
    by_channel: dict[NotificationChannel, list[NotificationPreference]] = {}
    for p in prefs:
        by_channel.setdefault(NotificationChannel(p.channel), []).append(p)
    out = []
    for channel in NotificationChannel:
        rows = by_channel.get(channel, [])
        out.append(
            {
                "channel": str(channel),
                "enabled": any(p.enabled for p in rows),
                "min_priority": rows[0].min_priority if rows else "high",
                "available": channel in AVAILABLE_CHANNELS,
            }
        )
    return out


@router.get("/notification-preferences")
def get_preferences(recipient_id: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    return _preferences_response(db, _recipients(db, recipient_id))


@router.put("/notification-preferences")
def update_preferences(
    updates: list[PreferenceUpdate],
    recipient_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Upsert, scoped to the addressed recipients. A care-team member added
    after the seed has no stored row, so updating in place alone is a silent
    no-op; and the whole batch is validated before anything is written."""
    recipients = _recipients(db, recipient_id)
    for update in updates:
        if update.enabled and update.channel not in AVAILABLE_CHANNELS:
            raise HTTPException(
                status_code=422,
                detail=f"{update.channel} delivery is not connected yet",
            )
    for update in updates:
        rows = {
            row.recipient_id: row
            for row in db.scalars(
                select(NotificationPreference).where(
                    NotificationPreference.channel == update.channel,
                    NotificationPreference.recipient_id.in_(recipients),
                )
            ).all()
        }
        for member_id in recipients:
            row = rows.get(member_id)
            if row is None:
                row = NotificationPreference(recipient_id=member_id, channel=update.channel)
                db.add(row)
            row.enabled = update.enabled
            row.min_priority = update.min_priority
    db.commit()
    return _preferences_response(db, recipients)
