"""App Store Server Notifications (V2): Apple tells this server when a
personal subscription renews, lapses, is refunded or revoked, so access does
not depend on the phone reporting its next transaction.

Always strict. The app's own route may run lenient for Xcode and sandbox
demos because a signed-in patient is behind it; this route is anonymous, so
a payload whose certificate chain does not reach Apple's root is rejected
whatever APPLE_SUBSCRIPTION_VERIFY says. Register
``https://<host>/api/webhooks/apple/subscriptions`` in App Store Connect.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.observation import WebhookEvent
from app.personal import subscription
from app.personal.subscription import SubscriptionError

router = APIRouter(tags=["webhooks"])


class NotificationBody(BaseModel):
    signedPayload: str


@router.post("/webhooks/apple/subscriptions", response_model=None)
def apple_subscription_notification(
    body: NotificationBody, db: Session = Depends(get_db)
) -> dict | JSONResponse:
    try:
        payload = subscription.verify_strict(body.signedPayload)
    except SubscriptionError as e:
        # Recorded without content, like any other unverified delivery.
        db.add(WebhookEvent(
            provider="apple", signature_valid=False, status="rejected", error=e.detail,
            payload={"rejected": True, "bytes": len(body.signedPayload)},
        ))
        db.commit()
        raise HTTPException(status_code=401, detail="Signature verification failed")

    event = WebhookEvent(provider="apple", signature_valid=True, payload={
        k: payload.get(k)
        for k in ("notificationType", "subtype", "notificationUUID", "version", "signedDate")
    })
    db.add(event)
    db.commit()
    try:
        outcome, row = subscription.apply_notification(
            db, payload, verify=subscription.verify_strict
        )
    except SubscriptionError as e:
        event.status, event.error = "failed", e.detail
        db.commit()
        raise HTTPException(status_code=e.status, detail=e.detail)
    event.status, event.processed_at = outcome, datetime.now()
    db.commit()
    if row is None:
        return JSONResponse(status_code=202, content={"status": "ignored"})
    return {"status": "processed", "patient_id": row.patient_id, "entitlement": row.status}
