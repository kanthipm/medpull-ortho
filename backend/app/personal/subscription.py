"""What lets a subscriber in: a trial, then an Apple subscription.

The app sells auto-renewing subscriptions through StoreKit 2 and reports
each signed transaction (a JWS) here. The server never talks to the App
Store: the transaction carries everything it needs — product, original
transaction id, expiry, environment — signed with a certificate chain that
ends at Apple's root.

Two modes, chosen by ``APPLE_SUBSCRIPTION_VERIFY``:

* **strict** checks the chain (each certificate signed by the next, the
  root's fingerprint pinned), the ES256 signature over the JWS, and that
  the transaction is for this app in the configured environment. Needs the
  ``cryptography`` package.
* **lenient** decodes the payload and checks bundle id, product and expiry.
  It exists because Xcode's local StoreKit testing signs with a certificate
  no Apple chain vouches for, and because a deployment without App Store
  Connect still has to demo the purchase flow. Grants made this way are
  recorded ``verified=False`` and shown as such.

Access is the best live row: a trial or an Apple grant whose expiry is in
the future (Apple grants get a three-day grace after expiry, matching the
store's own billing retry window).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.patient import Patient
from app.models.personal import Entitlement

logger = logging.getLogger(__name__)

GRACE_DAYS = 3


class SubscriptionError(ValueError):
    def __init__(self, detail: str, status: int = 422) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


def product_ids() -> set[str]:
    return {p.strip() for p in settings.personal_product_ids.split(",") if p.strip()}


# --- the trial -------------------------------------------------------------------------


def start_trial(db: Session, patient: Patient, now: datetime | None = None) -> Entitlement:
    now = now or datetime.now()
    existing = db.scalar(
        select(Entitlement).where(Entitlement.patient_id == patient.id,
                                  Entitlement.source == "trial")
    )
    if existing is not None:
        return existing
    row = Entitlement(
        patient_id=patient.id, source="trial", product_id="trial", status="active",
        started_at=now, expires_at=now + timedelta(days=settings.personal_trial_days),
        verified=True,
    )
    db.add(row)
    db.flush()
    return row


def grant_comp(db: Session, patient: Patient, days: int, note: str = "") -> Entitlement:
    """An operator's complimentary grant (a demo account, a friend)."""
    now = datetime.now()
    row = Entitlement(
        patient_id=patient.id, source="comp", product_id="comp", status="active",
        started_at=now, expires_at=now + timedelta(days=days), verified=True,
        raw={"note": note} if note else None,
    )
    db.add(row)
    db.flush()
    return row


# --- reading ----------------------------------------------------------------------------


def _live_until(row: Entitlement) -> datetime | None:
    if row.status == "revoked" or row.expires_at is None:
        return None if row.status == "revoked" else datetime.max
    grace = timedelta(days=GRACE_DAYS) if row.source == "apple" else timedelta(0)
    return row.expires_at + grace


def status(db: Session, patient: Patient, now: datetime | None = None) -> dict[str, Any]:
    """The account's access, as the app shows it on the paywall and in Profile."""
    now = now or datetime.now()
    rows = db.scalars(
        select(Entitlement).where(Entitlement.patient_id == patient.id)
        .order_by(Entitlement.id)
    ).all()
    best: Entitlement | None = None
    best_until: datetime | None = None
    for row in rows:
        until = _live_until(row)
        if until is None or until < now:
            continue
        # An Apple subscription outranks a trial that happens to run longer.
        rank = (row.source == "apple", until)
        if best is None or rank > (best.source == "apple", best_until or datetime.min):
            best, best_until = row, until
    if best is None:
        latest = rows[-1] if rows else None
        return {
            "state": "expired" if latest is not None else "none",
            "source": latest.source if latest else None,
            "product_id": latest.product_id if latest else None,
            "expires_at": latest.expires_at.isoformat() if latest and latest.expires_at else None,
            "days_left": 0, "verified": bool(latest.verified) if latest else False,
            "auto_renew": False, "entitled": False,
            "trial_used": any(r.source == "trial" for r in rows),
            "products": sorted(product_ids()),
        }
    in_grace = best.source == "apple" and best.expires_at is not None and best.expires_at < now
    state = "trial" if best.source == "trial" else "grace" if in_grace else "active"
    days_left = max(0, (best.expires_at - now).days) if best.expires_at else None
    return {
        "state": state, "source": best.source, "product_id": best.product_id,
        "expires_at": best.expires_at.isoformat() if best.expires_at else None,
        "days_left": days_left, "verified": bool(best.verified),
        "auto_renew": bool(best.auto_renew), "entitled": True,
        "trial_used": any(r.source == "trial" for r in rows),
        "products": sorted(product_ids()),
    }


def entitled(db: Session, patient: Patient, now: datetime | None = None) -> bool:
    return bool(status(db, patient, now)["entitled"])


# --- Apple's signed transactions ----------------------------------------------------------


def _b64url_decode(part: str) -> bytes:
    part += "=" * (-len(part) % 4)
    return base64.urlsafe_b64decode(part)


def decode_jws(jws: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    """(header, payload, signature, signing input) or SubscriptionError."""
    try:
        head, body, sig = jws.strip().split(".")
        header = json.loads(_b64url_decode(head))
        payload = json.loads(_b64url_decode(body))
        signature = _b64url_decode(sig)
    except (ValueError, json.JSONDecodeError) as e:
        raise SubscriptionError("That is not a signed transaction") from e
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise SubscriptionError("That is not a signed transaction")
    return header, payload, signature, f"{head}.{body}".encode()


def verify_strict(jws: str) -> dict[str, Any]:
    """Chain, root pin, signature. Returns the payload or raises."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        from cryptography.hazmat.primitives.serialization import Encoding
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise SubscriptionError(
            "Strict verification needs the cryptography package on this server", 503
        ) from e

    header, payload, signature, signing_input = decode_jws(jws)
    if header.get("alg") != "ES256":
        raise SubscriptionError("Unexpected signature algorithm")
    chain_b64 = header.get("x5c")
    if not isinstance(chain_b64, list) or len(chain_b64) < 2:
        raise SubscriptionError("The transaction carries no certificate chain")
    try:
        certs = [x509.load_der_x509_certificate(base64.b64decode(c)) for c in chain_b64]
    except Exception as e:  # noqa: BLE001
        raise SubscriptionError("The certificate chain could not be read") from e

    root = certs[-1]
    fingerprint = hashlib.sha256(root.public_bytes(Encoding.DER)).hexdigest()
    if fingerprint.lower() != settings.apple_root_ca_g3_sha256.lower():
        raise SubscriptionError("The certificate chain does not end at Apple's root")

    def check_signed_by(child, parent) -> None:
        key = parent.public_key()
        if isinstance(key, ec.EllipticCurvePublicKey):
            key.verify(child.signature, child.tbs_certificate_bytes,
                       ec.ECDSA(child.signature_hash_algorithm))
        elif isinstance(key, rsa.RSAPublicKey):
            key.verify(child.signature, child.tbs_certificate_bytes, padding.PKCS1v15(),
                       child.signature_hash_algorithm)
        else:
            raise SubscriptionError("Unsupported certificate key")

    try:
        for child, parent in zip(certs, certs[1:]):
            check_signed_by(child, parent)
        check_signed_by(root, root)
    except SubscriptionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SubscriptionError("The certificate chain does not verify") from e

    signed_at = payload.get("signedDate")
    when = (datetime.fromtimestamp(signed_at / 1000, tz=timezone.utc)
            if isinstance(signed_at, (int, float)) else datetime.now(timezone.utc))
    leaf = certs[0]
    if not (leaf.not_valid_before_utc <= when <= leaf.not_valid_after_utc):
        raise SubscriptionError("The signing certificate was not valid when this was signed")

    leaf_key = leaf.public_key()
    if not isinstance(leaf_key, ec.EllipticCurvePublicKey) or len(signature) != 64:
        raise SubscriptionError("Unexpected signing key")
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    try:
        leaf_key.verify(encode_dss_signature(r, s), signing_input, ec.ECDSA(hashes.SHA256()))
    except Exception as e:  # noqa: BLE001
        raise SubscriptionError("The transaction signature does not verify") from e
    return payload


def _ms(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value / 1000)
    return None


def apply_apple_transaction(
    db: Session, patient: Patient, jws: str, *, environment_hint: str | None = None
) -> Entitlement:
    """Record a signed transaction as this account's entitlement."""
    strict = settings.apple_subscription_verify.lower() == "strict"
    if strict:
        payload = verify_strict(jws)
        verified = True
    else:
        _header, payload, _sig, _input = decode_jws(jws)
        verified = False

    bundle = payload.get("bundleId")
    if bundle != settings.ios_bundle_id:
        raise SubscriptionError("That transaction is for a different app")
    product = payload.get("productId")
    if product not in product_ids():
        raise SubscriptionError(f"Unknown product {product!r}")
    environment = payload.get("environment") or environment_hint or "Unknown"
    if strict and environment != settings.apple_environment:
        raise SubscriptionError(
            f"A {environment} transaction cannot unlock a {settings.apple_environment} server"
        )
    original = str(payload.get("originalTransactionId") or payload.get("transactionId") or "")
    if not original:
        raise SubscriptionError("The transaction carries no id")
    expires = _ms(payload.get("expiresDate"))
    purchased = _ms(payload.get("purchaseDate")) or datetime.now()
    revoked = _ms(payload.get("revocationDate")) is not None

    row = db.scalar(select(Entitlement).where(Entitlement.original_transaction_id == original))
    if row is not None and row.patient_id != patient.id:
        # One Apple subscription, one account. A second account claiming it
        # (a shared Apple ID, a phone passed on) is refused rather than moved.
        raise SubscriptionError("That subscription is already linked to another account", 409)
    if row is None:
        row = Entitlement(patient_id=patient.id, source="apple", original_transaction_id=original)
        db.add(row)
    row.product_id = product
    row.transaction_id = str(payload.get("transactionId") or "") or None
    row.environment = environment
    row.started_at = purchased
    row.expires_at = expires
    row.status = "revoked" if revoked else "active"
    row.auto_renew = True
    row.verified = verified
    row.raw = {k: payload.get(k) for k in (
        "type", "inAppOwnershipType", "offerType", "signedDate", "expiresDate",
        "purchaseDate", "revocationReason", "webOrderLineItemId",
    )}
    db.flush()
    logger.info("Apple subscription %s for %s: %s until %s (%s)", product, patient.id,
                row.status, expires, "verified" if verified else "unverified")
    return row
