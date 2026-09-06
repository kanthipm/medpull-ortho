"""Delivery channels. In-app and SMS (Sendblue) are real; email is a stub that
records intent so the preference UI and the eventual SES integration share one
path. SMS degrades to the same stub behavior when the Sendblue keys are unset."""

import logging
from typing import Protocol

from app.models.enums import NotificationChannel, NotificationStatus
from app.models.notification import Notification
from app.notifications.sendblue import SendblueChannel

logger = logging.getLogger(__name__)


class Channel(Protocol):
    def send(self, notification: Notification) -> NotificationStatus: ...


class InAppChannel:
    def send(self, notification: Notification) -> NotificationStatus:
        return NotificationStatus.UNREAD  # shows in the bell until read


class EmailChannel:
    def send(self, notification: Notification) -> NotificationStatus:
        logger.info("Email stub -> %s: %s", notification.recipient_id, notification.title)
        return NotificationStatus.SENT_STUB


CHANNELS: dict[NotificationChannel, Channel] = {
    NotificationChannel.IN_APP: InAppChannel(),
    NotificationChannel.SMS: SendblueChannel(),
    NotificationChannel.EMAIL: EmailChannel(),
}
