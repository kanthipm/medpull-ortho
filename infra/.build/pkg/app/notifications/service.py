"""Care-team notification on High recovery priority."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import NotificationChannel
from app.models.insight import RiskAssessment
from app.models.notification import Notification, NotificationPreference
from app.models.patient import Patient
from app.notifications.channels import CHANNELS


def notify_high_priority(db: Session, patient: Patient, assessment: RiskAssessment) -> None:
    top_reason = assessment.reasons[0]["text"] if assessment.reasons else "Multiple signals changed"
    title = f"{patient.name} — high recovery priority"
    # In-app notifications navigate on click; out-of-band channels need the link.
    linked_body = f"{top_reason}. Review at /patients/{patient.id}."

    prefs = db.scalars(
        select(NotificationPreference).where(
            NotificationPreference.recipient_id == patient.assigned_provider_id,
            NotificationPreference.enabled.is_(True),
        )
    ).all()
    channels = [p.channel for p in prefs] or [NotificationChannel.IN_APP]

    for channel in channels:
        notification = Notification(
            patient_id=patient.id,
            recipient_id=patient.assigned_provider_id,
            kind="priority_high",
            title=title,
            body=top_reason if channel == NotificationChannel.IN_APP else linked_body,
            channel=channel,
        )
        notification.status = CHANNELS[NotificationChannel(channel)].send(notification)
        db.add(notification)
    db.commit()
