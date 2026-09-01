"""Import every model so Base.metadata knows the full schema."""

from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.checkin import Checkin, CheckinMessage
from app.models.insight import Insight, RiskAssessment
from app.models.notification import Notification, NotificationPreference
from app.models.observation import Observation, WebhookEvent
from app.models.patient import CareTeamMember, Device, Patient
from app.models.rtm import (
    EnrollmentStatus,
    MonitoringWindow,
    ProviderTimeLog,
    RtmDocument,
    RtmInteraction,
)

__all__ = [
    "AdherenceRecord",
    "AdherenceTask",
    "Checkin",
    "CheckinMessage",
    "Insight",
    "RiskAssessment",
    "Notification",
    "NotificationPreference",
    "Observation",
    "WebhookEvent",
    "CareTeamMember",
    "Device",
    "Patient",
    "MonitoringWindow",
    "EnrollmentStatus",
    "ProviderTimeLog",
    "RtmDocument",
    "RtmInteraction",
]
