"""Import every model so Base.metadata knows the full schema."""

from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.attachment import Attachment
from app.models.checkin import Checkin, CheckinMessage
from app.models.connection import WearableConnection
from app.models.hospital import Hospital
from app.models.insight import EstablishedBaseline, Insight, RiskAssessment
from app.models.library import CareAction, MessageTemplate, TaskTemplate, TaskVerification
from app.models.mobile import Message, PatientSession, PhoneVerification
from app.models.notification import Notification, NotificationPreference
from app.models.observation import Observation, WebhookEvent
from app.models.patient import CareTeamMember, Device, Patient
from app.models.personal import (
    Consent,
    Entitlement,
    PersonalCredential,
    PersonalLog,
    PersonalProfile,
)

__all__ = [
    "AdherenceRecord",
    "AdherenceTask",
    "Attachment",
    "CareAction",
    "MessageTemplate",
    "TaskTemplate",
    "TaskVerification",
    "Checkin",
    "CheckinMessage",
    "EstablishedBaseline",
    "Hospital",
    "Message",
    "PatientSession",
    "PhoneVerification",
    "Insight",
    "RiskAssessment",
    "Notification",
    "NotificationPreference",
    "Observation",
    "WebhookEvent",
    "CareTeamMember",
    "Device",
    "Patient",
    "WearableConnection",
    "Consent",
    "Entitlement",
    "PersonalCredential",
    "PersonalLog",
    "PersonalProfile",
]
