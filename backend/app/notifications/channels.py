"""Delivery channels. In-app is real; SMS/email are stubs that record intent
so the preference UI and the eventual Twilio/SES integrations share one path."""

import logging
from typing import Protocol

from app.models.enums import NotificationChannel, NotificationStatus
from app.models.notification import Notification

logger = logging.getLogger(__name__)


class Channel(Protocol):
    def send(self, notification: Notification) -> NotificationStatus: ...


class InAppChannel:
    def send(self, notification: Notification) -> NotificationStatus:
        return NotificationStatus.UNREAD  # shows in the bell until read


class SmsChannel:
    def send(self, notification: Notification) -> NotificationStatus:
        logger.info("SMS stub -> %s: %s", notification.recipient_id, notification.title)
        return NotificationStatus.SENT_STUB


class EmailChannel:
    def send(self, notification: Notification) -> NotificationStatus:
        logger.info("Email stub -> %s: %s", notification.recipient_id, notification.title)
        return NotificationStatus.SENT_STUB


CHANNELS: dict[NotificationChannel, Channel] = {
    NotificationChannel.IN_APP: InAppChannel(),
    NotificationChannel.SMS: SmsChannel(),
    NotificationChannel.EMAIL: EmailChannel(),
}
