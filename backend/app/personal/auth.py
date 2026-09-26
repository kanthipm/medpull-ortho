"""Logins and consent for the personal tier.

A subscriber signs in with an email and a password. The phone number stays
for texts and for pairing with a hospital record; it is no longer the
identity. Passwords are hashed with scrypt from the standard library, with
the parameters written into the hash so they can be raised without a
migration. Eight failed attempts lock the account for fifteen minutes.

Consent is a versioned document. The person reads it in the app, ticks the
scopes, types their name, and the acceptance is stored by version and text
hash and archived in full to the personal bucket, so what they agreed to is
recoverable word for word later.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.personal import Consent, PersonalCredential

logger = logging.getLogger(__name__)

# scrypt: n=2^14, r=8, p=1 is the interactive-login setting the RFC suggests.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
_KEYLEN = 32
MIN_PASSWORD = 8
MAX_ATTEMPTS = 8
LOCKOUT = timedelta(minutes=15)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(ValueError):
    def __init__(self, detail: str, status: int = 401) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


def normalize_email(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    if not value:
        return None
    if len(value) > 254 or not _EMAIL.match(value):
        raise AuthError("Enter a valid email address", 422)
    return value


def check_password(password: str | None) -> str:
    if not password or len(password) < MIN_PASSWORD:
        raise AuthError(f"Use a password of at least {MIN_PASSWORD} characters", 422)
    if len(password) > 200:
        raise AuthError("That password is too long", 422)
    return password


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R,
                            p=_SCRYPT_P, dklen=_KEYLEN)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n),
                                   r=int(r), p=int(p), dklen=len(digest) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)


# --- credentials ----------------------------------------------------------------------


def credential_for_email(db: Session, email: str) -> PersonalCredential | None:
    return db.scalar(select(PersonalCredential).where(PersonalCredential.email == email))


def create_credential(db: Session, patient: Patient, email: str, password: str) -> PersonalCredential:
    if credential_for_email(db, email) is not None:
        raise AuthError("That email already has an account — sign in instead", 409)
    row = PersonalCredential(patient_id=patient.id, email=email,
                             password_hash=hash_password(check_password(password)),
                             password_changed_at=datetime.now())
    db.add(row)
    db.flush()
    return row


def authenticate(db: Session, email: str, password: str) -> Patient:
    """The account behind a login, or AuthError. Failures count toward the
    lockout; a locked account answers 423 whatever the password."""
    generic = AuthError("That email and password don't match")
    row = credential_for_email(db, email)
    if row is None:
        # Cost the same as a real check so an attacker cannot tell an unknown
        # email from a wrong password by timing.
        verify_password(password, hash_password("x" * MIN_PASSWORD))
        raise generic
    now = datetime.now()
    if row.locked_until and row.locked_until > now:
        minutes = max(1, int((row.locked_until - now).total_seconds() // 60) + 1)
        raise AuthError(f"Too many tries. Try again in {minutes} minute{'s' if minutes != 1 else ''}", 423)
    if not verify_password(password, row.password_hash):
        row.failed_attempts = (row.failed_attempts or 0) + 1
        if row.failed_attempts >= MAX_ATTEMPTS:
            row.locked_until = now + LOCKOUT
            row.failed_attempts = 0
        db.commit()
        raise generic
    row.failed_attempts = 0
    row.locked_until = None
    row.last_login_at = now
    patient = db.get(Patient, row.patient_id)
    if patient is None:
        raise generic
    db.commit()
    return patient


def set_password(db: Session, patient: Patient, password: str) -> None:
    row = db.get(PersonalCredential, patient.id)
    if row is None:
        raise AuthError("This account has no login yet", 404)
    row.password_hash = hash_password(check_password(password))
    row.password_changed_at = datetime.now()
    row.failed_attempts = 0
    row.locked_until = None
    db.flush()


# --- consent ---------------------------------------------------------------------------

CONSENT_VERSION = "2026-09-26.1"
CONSENT_KIND = "beta"
# The scopes the form asks for. Required ones cannot be unticked; the
# research scope can, and the app records the answer either way.
CONSENT_SCOPES: dict[str, dict[str, Any]] = {
    "beta_ack": {
        "label": "I understand MedPull Personal is a beta",
        "detail": "Features, readouts and wording will change while we learn from early users. "
                  "Some things will be wrong. Tell us when they are.",
        "required": True,
    },
    "data_storage": {
        "label": "Store my health data on MedPull’s servers",
        "detail": "Steps, sleep, heart rate and HRV, workouts and the other signals your watch "
                  "shares, your check-in answers and notes, kept in encrypted storage on Amazon "
                  "Web Services in the United States, in storage separate from any hospital’s "
                  "patient records.",
        "required": True,
    },
    "ai_processing": {
        "label": "Let MedPull’s AI read my data to write my readouts",
        "detail": "Your morning brief, deep dives and coach replies are written by an AI model "
                  "from your numbers. The numbers it needs are sent to the model provider for "
                  "that purpose and the results are stored with your account.",
        "required": True,
    },
    "research_use": {
        "label": "Use my data to improve MedPull",
        "detail": "We may analyse your data, and the AI results made from it, in de-identified "
                  "or aggregate form to improve the readouts, the models and the product. Never "
                  "sold, never used for advertising.",
        "required": False,
    },
}

CONSENT_TEXT = """MedPull Personal — beta consent

What this is. MedPull Personal is an early version (a beta) of a subscription service that reads the signals from your watch or phone and turns them into readiness, training load, sleep and recovery readouts, a daily plan and a coach. It is a tool for training and recovery. It is not a medical device and it does not give medical advice. If you feel unwell, see a clinician.

What we collect. With your permission the app reads activity, sleep, heart rate, heart rate variability, blood oxygen, breathing rate, skin temperature, workouts, walking metrics and fitness estimates from Apple Health or a connected wearable. You also give us your name, email, phone number if you add one, your goal, your check-in answers, notes and anything you tell the coach.

Where it goes. Your data is stored in encrypted storage on Amazon Web Services in the United States, in a store that is separate from any hospital’s patient records. Your files and data exports live in their own storage bucket. The AI readouts written for you are stored with your account so you can read them again and so we can improve them.

Who sees it. Nobody at a hospital sees your personal space unless you choose to pair it with a hospital record, and then only that record. Service providers that operate the app receive what they need to do their job: Amazon Web Services (hosting), Junction (wearable data), the AI model provider (the numbers behind your readouts), and Sendblue (texts, if you turn them on). We do not sell your data and we do not use it for advertising.

How we use it. To run the app for you. If you agree below, also to improve MedPull: analysing data and AI results in de-identified or aggregate form to make the readouts, the models and the product better.

Your rights. You can export everything from Profile at any time. You can delete your account and its data from Profile at any time; deletion removes your account rows and files. You can withdraw the research permission from Profile without losing the app. Questions: hello@medpull.org.

By typing your name and tapping Agree you confirm you are at least 18, or 13 or older with a parent or guardian’s permission, and that you have read and agree to this."""


def consent_hash() -> str:
    return hashlib.sha256(CONSENT_TEXT.encode()).hexdigest()


def consent_document() -> dict[str, Any]:
    """What the app shows: the words, the scopes, the version."""
    return {
        "kind": CONSENT_KIND,
        "version": CONSENT_VERSION,
        "text": CONSENT_TEXT,
        "text_sha256": consent_hash(),
        "scopes": [{"key": k, **v} for k, v in CONSENT_SCOPES.items()],
        "beta": True,
    }


def validate_scopes(scopes: dict[str, Any] | None) -> dict[str, bool]:
    given = {k: bool(v) for k, v in (scopes or {}).items() if k in CONSENT_SCOPES}
    for key, spec in CONSENT_SCOPES.items():
        if spec["required"] and not given.get(key):
            raise AuthError(f"“{spec['label']}” is needed to use MedPull Personal", 422)
    return {k: given.get(k, False) for k in CONSENT_SCOPES}


def record_consent(db: Session, patient: Patient, *, version: str, scopes: dict[str, Any] | None,
                   signature: str | None, device_name: str | None, app_version: str | None) -> Consent:
    if version != CONSENT_VERSION:
        raise AuthError("The consent form has changed — read the new version and agree again", 409)
    row = Consent(
        patient_id=patient.id, kind=CONSENT_KIND, version=version, text_sha256=consent_hash(),
        scopes=validate_scopes(scopes), signature=(signature or "").strip()[:120] or None,
        device_name=(device_name or "")[:80] or None, app_version=(app_version or "")[:40] or None,
    )
    db.add(row)
    db.flush()
    try:
        from app.personal import archive

        row.archived_key = archive.archive_consent(patient, row)
    except Exception:  # noqa: BLE001 — the row is the record; the archive is a copy
        logger.exception("consent archive failed for %s", patient.id)
    db.flush()
    return row


def current_consent(db: Session, patient: Patient) -> Consent | None:
    return db.scalar(
        select(Consent)
        .where(Consent.patient_id == patient.id, Consent.kind == CONSENT_KIND,
               Consent.withdrawn_at.is_(None))
        .order_by(Consent.id.desc())
        .limit(1)
    )


def consent_view(db: Session, patient: Patient) -> dict[str, Any]:
    row = current_consent(db, patient)
    return {
        "version": row.version if row else None,
        "accepted_at": row.accepted_at.isoformat() if row else None,
        "scopes": row.scopes if row else None,
        "current_version": CONSENT_VERSION,
        "needs_consent": row is None or row.version != CONSENT_VERSION,
    }


def set_research_use(db: Session, patient: Patient, allowed: bool) -> Consent | None:
    """Flip the one optional scope without a new signature."""
    row = current_consent(db, patient)
    if row is None:
        return None
    scopes = dict(row.scopes or {})
    scopes["research_use"] = bool(allowed)
    row.scopes = scopes
    db.flush()
    try:
        from app.personal import archive

        row.archived_key = archive.archive_consent(patient, row)
    except Exception:  # noqa: BLE001
        logger.exception("consent archive failed for %s", patient.id)
    return row
