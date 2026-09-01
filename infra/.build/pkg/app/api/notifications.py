from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import NotificationChannel, NotificationStatus
from app.models.notification import Notification, NotificationPreference
from app.models.patient import Patient

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
    unread = db.scalars(
        select(Notification).where(Notification.status == NotificationStatus.UNREAD)
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


AVAILABLE_CHANNELS = {NotificationChannel.IN_APP}


def _preferences_response(db: Session) -> list[dict]:
    prefs = db.scalars(select(NotificationPreference)).all()
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
def get_preferences(db: Session = Depends(get_db)) -> list[dict]:
    return _preferences_response(db)


@router.put("/notification-preferences")
def update_preferences(
    updates: list[PreferenceUpdate], db: Session = Depends(get_db)
) -> list[dict]:
    for update in updates:
        rows = db.scalars(
            select(NotificationPreference).where(
                NotificationPreference.channel == update.channel
            )
        ).all()
        for row in rows:
            row.enabled = update.enabled
            row.min_priority = update.min_priority
    db.commit()
    return _preferences_response(db)
