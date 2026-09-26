"""The personal tier's API, under ``/api/mobile``.

Joining and signing in are pre-authentication like the clinic flows and
follow the same phone rules (one number per space, a texted code when the
deployment can send one). Everything else carries the app session, and
the readouts additionally require an entitlement: a trial, an Apple
subscription, or a grace period after one lapses. Without it the routes
answer 402 with what the paywall needs to show.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import mobile
from app.api.mobile import current_patient
from app.api.worklist import ensure_fresh_assessment
from app.database import get_db
from app.models.hospital import Hospital
from app.models.mobile import PhoneVerification
from app.models.patient import Patient
from app.models.personal import GOAL_LABELS, GOALS, PersonalProfile
from app.notifications import sendblue
from app.personal import archive, auth, daily, identity, insights, subscription
from app.personal.auth import AuthError
from app.personal.data import load_personal_data
from app.personal.identity import PersonalIdentityError
from app.personal.logs import LOG_KEYS, record
from app.personal.metrics import compute_dashboard
from app.personal.scope import CLINIC, is_personal
from app.personal.subscription import SubscriptionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mobile", tags=["personal"])


# --- helpers ------------------------------------------------------------------------------


def _profile(db: Session, patient: Patient) -> PersonalProfile:
    if not is_personal(patient):
        raise HTTPException(status_code=403, detail="This is a hospital record, not a personal space")
    profile = identity.profile_of(db, patient)
    if profile is None:
        raise HTTPException(status_code=404, detail="No personal profile on this account")
    return profile


def personal_patient(
    patient: Patient = Depends(current_patient), db: Session = Depends(get_db)
) -> Patient:
    _profile(db, patient)
    return patient


def entitled_patient(
    patient: Patient = Depends(personal_patient), db: Session = Depends(get_db)
) -> Patient:
    state = subscription.status(db, patient)
    if not state["entitled"]:
        raise HTTPException(
            status_code=402,
            detail="Your MedPull Personal access has ended. Subscribe to keep your readouts.",
            headers={"X-MedPull-Paywall": json.dumps(state)},
        )
    return patient


def _profile_view(profile: PersonalProfile) -> dict[str, Any]:
    return {
        "goal": profile.goal, "goal_label": GOAL_LABELS.get(profile.goal, profile.goal),
        "sport": profile.sport, "weekly_target_minutes": profile.weekly_target_minutes,
        "sleep_target_hours": profile.sleep_target_hours, "injury": profile.injury,
        "anchor_date": profile.anchor_date.isoformat() if profile.anchor_date else None,
        "units": profile.units, "sms_briefs": profile.sms_briefs, "brief_hour": profile.brief_hour,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }


def _session_answer(db: Session, patient: Patient, body: Any, *, verified: bool) -> dict:
    first = mobile._first_enrollment(db, patient)
    token = mobile._issue_session(db, patient, body.device_name, body.app_version)
    if first:
        mobile._welcome(db, patient)
    return {"status": "enrolled", "verified": verified, "session_token": token,
            "me": mobile.me_view(db, patient)}


class ConsentBody(BaseModel):
    version: str
    scopes: dict[str, bool] = Field(default_factory=dict)
    signature: str | None = Field(default=None, max_length=120)


def _record_consent(db: Session, patient: Patient, consent: ConsentBody | None,
                    device_name: str | None, app_version: str | None) -> None:
    if consent is None:
        raise HTTPException(status_code=422, detail="Read and agree to the beta consent first")
    try:
        auth.record_consent(db, patient, version=consent.version, scopes=consent.scopes,
                            signature=consent.signature, device_name=device_name,
                            app_version=app_version)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


def _holders(db: Session, phone: str) -> list[Patient]:
    return list(db.scalars(select(Patient).where(Patient.phone == phone)).all())


# --- joining -----------------------------------------------------------------------------


class PersonalJoinBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    # The login. Email and password are the identity; the phone is optional
    # and only for texts and pairing with a hospital record.
    email: str
    password: str
    consent: ConsentBody | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    goal: str = "everyday"
    sport: str | None = None
    weekly_target_minutes: int | None = Field(default=None, ge=0, le=3000)
    sleep_target_hours: float | None = Field(default=None, ge=4, le=12)
    injury: str | None = None
    anchor_date: date | None = None
    procedure_type: str | None = None
    units: str = "metric"
    sms_briefs: bool = True
    device_name: str | None = None
    app_version: str | None = None


@router.post("/personal/join")
def personal_join(body: PersonalJoinBody, db: Session = Depends(get_db)) -> dict:
    """Create a personal space with an email and password login.

    Consent to the beta is required and recorded (and archived) with the
    account. A phone number is optional; when given it decides a second
    path: free, it is claimed; on a hospital record, the person is asked to
    prove it (a texted code) and the new space is paired with that record;
    on another personal space, they are sent to sign in instead."""
    try:
        email = auth.normalize_email(body.email)
        auth.check_password(body.password)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    if email is None:
        raise HTTPException(status_code=422, detail="Enter your email address")
    if auth.credential_for_email(db, email) is not None:
        raise HTTPException(status_code=409,
                            detail="That email already has an account — sign in instead")
    if body.goal not in GOALS:
        raise HTTPException(status_code=422, detail="Pick what you want out of MedPull")
    if body.consent is None:
        raise HTTPException(status_code=422, detail="Read and agree to the beta consent first")
    try:
        auth.validate_scopes(body.consent.scopes)
        if body.consent.version != auth.CONSENT_VERSION:
            raise AuthError("The consent form has changed — read the new version and agree again", 409)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    phone = None
    clinic = None
    needs_code = False
    if body.phone and body.phone.strip():
        phone = sendblue.normalize_phone(body.phone)
        if phone is None:
            raise HTTPException(status_code=422, detail="Enter a valid mobile number, or leave it out")
        holders = _holders(db, phone)
        personal_holders = [h for h in holders if is_personal(h)]
        clinic_holders = [h for h in holders if not is_personal(h)]
        if personal_holders:
            raise HTTPException(
                status_code=409,
                detail="That number already has a personal space — sign in to it instead",
            )
        clinic = clinic_holders[0] if len(clinic_holders) == 1 else None
        if clinic_holders and (clinic is None or clinic.linked_patient_id):
            raise HTTPException(
                status_code=409,
                detail="That number is on a hospital record that already has a personal space",
            )
        needs_code = mobile._verification_needed() or clinic is not None
        if needs_code and not sendblue.configured():
            # A chart with this number exists and nothing can carry a code
            # to prove the claim. The safe door: sign in to the record, then
            # add the personal space from Profile (that path is authenticated).
            raise HTTPException(
                status_code=409,
                detail="That number is on a hospital record. Sign in to that record first, then "
                "add your personal space from Profile — or leave the number out for now.",
            )
    try:
        patient, _profile_row = identity.create_personal_account(
            db, name=body.name, phone=None if needs_code else phone, goal=body.goal,
            sport=body.sport, weekly_target_minutes=body.weekly_target_minutes,
            sleep_target_hours=body.sleep_target_hours, injury=body.injury,
            anchor_date=body.anchor_date, procedure_type=body.procedure_type, sex=body.sex,
            date_of_birth=body.date_of_birth, units=body.units,
            sms_briefs=body.sms_briefs and phone is not None,
        )
        auth.create_credential(db, patient, email, body.password)
    except PersonalIdentityError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    _record_consent(db, patient, body.consent, body.device_name, body.app_version)
    db.commit()
    archive.archive_event(patient, "account_created", {"goal": body.goal, "phone": phone is not None})
    if needs_code:
        started = mobile._start_verification(db, patient, phone)
        started["intent"] = "join"
        started["links_to"] = clinic.id if clinic else None
        db.commit()
        return started
    return _session_answer(db, patient, body, verified=False)


class LoginBody(BaseModel):
    email: str
    password: str
    device_name: str | None = None
    app_version: str | None = None


@router.post("/personal/login")
def personal_login(body: LoginBody, db: Session = Depends(get_db)) -> dict:
    """Back in, on any phone: the email and password."""
    try:
        email = auth.normalize_email(body.email)
        if email is None:
            raise AuthError("Enter your email address", 422)
        patient = auth.authenticate(db, email, body.password)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    return _session_answer(db, patient, body, verified=True)


class ForgotBody(BaseModel):
    email: str


@router.post("/personal/password/forgot")
def password_forgot(body: ForgotBody, db: Session = Depends(get_db)) -> dict:
    """A reset code, texted to the phone on the account. The answer never
    says whether the email exists; only whether a text went out."""
    try:
        email = auth.normalize_email(body.email)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    row = auth.credential_for_email(db, email) if email else None
    patient = db.get(Patient, row.patient_id) if row else None
    if patient is None or not patient.phone or not sendblue.configured():
        return {"sent": False, "phone_masked": None, "verification_id": None,
                "detail": "If that account has a phone number on file and texts are on, a code "
                          "is on its way. Otherwise write to hello@medpull.org and we’ll help."}
    started = mobile._start_verification(db, patient, patient.phone)
    db.commit()
    return {"sent": True, "phone_masked": started["phone_masked"],
            "verification_id": started["verification_id"], "detail": None}


class ResetBody(BaseModel):
    verification_id: int
    code: str = Field(min_length=4, max_length=8)
    password: str
    device_name: str | None = None
    app_version: str | None = None


@router.post("/personal/password/reset")
def password_reset(body: ResetBody, db: Session = Depends(get_db)) -> dict:
    verification = db.get(PhoneVerification, body.verification_id)
    if verification is None or verification.verified_at is not None:
        raise HTTPException(status_code=404, detail="Start over — that code is no longer valid")
    if verification.expires_at < datetime.now():
        raise HTTPException(status_code=410, detail="That code expired — request a new one")
    if verification.attempts >= mobile.VERIFICATION_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many tries — request a new code")
    verification.attempts += 1
    import secrets

    if not secrets.compare_digest(verification.code_hash, mobile._hash(body.code.strip())):
        db.commit()
        raise HTTPException(status_code=401, detail="That code isn't right")
    verification.verified_at = datetime.now()
    patient = db.get(Patient, verification.patient_id)
    if patient is None or not is_personal(patient):
        raise HTTPException(status_code=404, detail="Unknown account")
    try:
        auth.set_password(db, patient, body.password)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    db.commit()
    return _session_answer(db, patient, body, verified=True)


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/personal/password/change")
def password_change(body: ChangePasswordBody, patient: Patient = Depends(personal_patient),
                    db: Session = Depends(get_db)) -> dict:
    from app.models.personal import PersonalCredential

    row = db.get(PersonalCredential, patient.id)
    if row is None or not auth.verify_password(body.current_password, row.password_hash):
        raise HTTPException(status_code=401, detail="That isn't your current password")
    try:
        auth.set_password(db, patient, body.new_password)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    db.commit()
    return {"ok": True}


# --- consent -------------------------------------------------------------------------------


@router.get("/consent")
def consent_document() -> dict:
    """The beta consent, as the app shows it before an account exists."""
    return auth.consent_document()


class ConsentAcceptBody(ConsentBody):
    device_name: str | None = None
    app_version: str | None = None


@router.post("/consent")
def accept_consent(body: ConsentAcceptBody, patient: Patient = Depends(current_patient),
                   db: Session = Depends(get_db)) -> dict:
    """Record acceptance for a signed-in account of either kind (an
    existing account meeting a new version, or a hospital patient)."""
    _record_consent(db, patient, body, body.device_name, body.app_version)
    db.commit()
    return {"ok": True, "consent": auth.consent_view(db, patient)}


class ResearchBody(BaseModel):
    allowed: bool


@router.patch("/personal/consent/research")
def set_research(body: ResearchBody, patient: Patient = Depends(personal_patient),
                 db: Session = Depends(get_db)) -> dict:
    if auth.set_research_use(db, patient, body.allowed) is None:
        raise HTTPException(status_code=404, detail="No consent on file yet")
    db.commit()
    return {"ok": True, "consent": auth.consent_view(db, patient)}


@router.delete("/personal/account")
def delete_account(patient: Patient = Depends(personal_patient), db: Session = Depends(get_db)) -> dict:
    """Delete the personal space and everything under it: rows, files, the
    lake. A paired hospital record is unpaired and left alone — it is the
    clinic's — and its wearable stream stays with it."""
    from sqlalchemy import delete as sql_delete

    from app.models.mobile import PatientSession
    from app.models.personal import Consent, Entitlement, PersonalCredential, PersonalLog

    pid = patient.id
    other = identity.linked(db, patient)
    if other is not None:
        other.linked_patient_id = None
    patient.linked_patient_id = None
    patient.observations_from = None
    for session in db.scalars(select(PatientSession).where(PatientSession.patient_id == pid)).all():
        session.revoked_at = datetime.now()
    for model in (PersonalLog, Entitlement, Consent, PersonalCredential, PersonalProfile):
        db.execute(sql_delete(model).where(model.patient_id == pid))
    db.commit()
    from app.identity import IdentityError, delete_patient

    try:
        result = delete_patient(db, patient)
    except IdentityError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    return {"ok": True, "deleted": pid, "rows": result["rows"]}


class PersonalSigninBody(BaseModel):
    phone: str
    device_name: str | None = None
    app_version: str | None = None


@router.post("/personal/signin")
def personal_signin(body: PersonalSigninBody, db: Session = Depends(get_db)) -> dict:
    """Back into an existing personal space by phone: only with a texted
    code. With a password login in place, a number alone must never open an
    account, so a deployment that cannot text points at the email login."""
    phone = sendblue.normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(status_code=422, detail="Enter a valid mobile number")
    holders = [h for h in _holders(db, phone) if is_personal(h)]
    if not holders:
        raise HTTPException(status_code=404, detail="No personal space uses that number yet")
    if not sendblue.configured():
        raise HTTPException(status_code=409,
                            detail="Sign in with your email and password on this server")
    patient = holders[0]
    started = mobile._start_verification(db, patient, phone)
    started["intent"] = "signin"
    db.commit()
    return started


class PersonalVerifyBody(BaseModel):
    verification_id: int
    code: str = Field(min_length=4, max_length=8)
    device_name: str | None = None
    app_version: str | None = None


@router.post("/personal/verify")
def personal_verify(body: PersonalVerifyBody, db: Session = Depends(get_db)) -> dict:
    """Finish a personal join or sign-in that needed a code. Proving the
    number also pairs the new space with the hospital record that carries
    it, if there is one — the two rows then share the phone on purpose."""
    verification = db.get(PhoneVerification, body.verification_id)
    if verification is None or verification.verified_at is not None:
        raise HTTPException(status_code=404, detail="Start over — that code is no longer valid")
    if verification.expires_at < datetime.now():
        raise HTTPException(status_code=410, detail="That code expired — request a new one")
    if verification.attempts >= mobile.VERIFICATION_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many tries — request a new code")
    verification.attempts += 1
    import secrets

    if not secrets.compare_digest(verification.code_hash, mobile._hash(body.code.strip())):
        db.commit()
        raise HTTPException(status_code=401, detail="That code isn't right")
    verification.verified_at = datetime.now()
    patient = db.get(Patient, verification.patient_id)
    if patient is None or not is_personal(patient):
        raise HTTPException(status_code=404, detail="Unknown account")
    phone = verification.phone
    clinic = next((h for h in _holders(db, phone) if not is_personal(h)), None)
    for other in _holders(db, phone):
        if is_personal(other) and other.id != patient.id:
            other.phone = None  # a stale personal row; the proven phone wins
    patient.phone = phone
    db.commit()
    if clinic is not None and not clinic.linked_patient_id and not patient.linked_patient_id:
        try:
            identity.link(db, clinic, patient)
        except PersonalIdentityError as e:
            logger.info("Verified join did not pair with %s: %s", clinic.id, e.detail)
    return _session_answer(db, patient, body, verified=True)


# --- the two spaces -------------------------------------------------------------------------


@router.get("/profiles")
def profiles(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    return {"profiles": identity.profiles_view(db, patient), "current": patient.id}


class SwitchBody(BaseModel):
    patient_id: str
    device_name: str | None = None
    app_version: str | None = None


@router.post("/profiles/switch")
def switch(body: SwitchBody, patient: Patient = Depends(current_patient),
           db: Session = Depends(get_db)) -> dict:
    """A session for the other space. The current one stays valid, so the
    app keeps a token per space and switching back is instant."""
    try:
        target = identity.switch_target(db, patient, body.patient_id)
    except PersonalIdentityError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    token = mobile._issue_session(db, target, body.device_name, body.app_version)
    return {"session_token": token, "me": mobile.me_view(db, target)}


class AddPersonalBody(BaseModel):
    goal: str = "everyday"
    sport: str | None = None
    weekly_target_minutes: int | None = Field(default=None, ge=0, le=3000)
    sleep_target_hours: float | None = Field(default=None, ge=4, le=12)
    injury: str | None = None
    units: str = "metric"
    sms_briefs: bool = True
    device_name: str | None = None
    app_version: str | None = None


@router.post("/personal/add")
def add_personal_space(body: AddPersonalBody, patient: Patient = Depends(current_patient),
                       db: Session = Depends(get_db)) -> dict:
    """From a signed-in hospital record: open a personal space paired with
    it. The session proves the person, so no code is needed; the recovery
    goal inherits the chart's operation and date."""
    if is_personal(patient):
        raise HTTPException(status_code=409, detail="This already is your personal space")
    if patient.linked_patient_id:
        raise HTTPException(status_code=409, detail="This record already has a personal space")
    surgical = str(patient.procedure_type) != "NONE"
    try:
        personal, _ = identity.create_personal_account(
            db, name=patient.name, phone=patient.phone, goal=body.goal, sport=body.sport,
            weekly_target_minutes=body.weekly_target_minutes,
            sleep_target_hours=body.sleep_target_hours,
            injury=body.injury or (patient.procedure_display if surgical and body.goal == "recovery" else None),
            anchor_date=patient.surgery_date if surgical else None,
            procedure_type=str(patient.procedure_type) if surgical else None,
            sex=patient.sex, date_of_birth=patient.date_of_birth, units=body.units,
            sms_briefs=body.sms_briefs,
        )
        identity.link(db, patient, personal)
    except PersonalIdentityError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    token = mobile._issue_session(db, personal, body.device_name, body.app_version)
    return {"session_token": token, "me": mobile.me_view(db, personal),
            "profiles": identity.profiles_view(db, personal)}


class LinkHospitalBody(BaseModel):
    # "enroll": pair with an existing record found through /patients/search.
    # "join": create a new record at the hospital and pair with it.
    mode: str = "enroll"
    hospital_id: str
    patient_id: str | None = None
    had_surgery: bool = False
    procedure_type: str | None = None
    surgery_date: date | None = None
    device_name: str | None = None
    app_version: str | None = None


@router.post("/personal/link-hospital")
def link_hospital(body: LinkHospitalBody, patient: Patient = Depends(personal_patient),
                  db: Session = Depends(get_db)) -> dict:
    """From a personal space: join a hospital's programme, keeping this space.

    Pairing with an existing record follows the clinic enroll rule: open
    when the record has no number or carries this one; otherwise a code to
    the record's number proves the claim (verified through /enroll/verify,
    after which the app calls this again).
    """
    if patient.linked_patient_id:
        raise HTTPException(status_code=409, detail="This space is already paired with a record")
    if db.get(Hospital, body.hospital_id) is None:
        raise HTTPException(status_code=404, detail="Unknown hospital")
    if body.mode == "join":
        if body.had_surgery:
            if body.procedure_type not in mobile.PROCEDURE_DISPLAY or body.procedure_type == "NONE":
                raise HTTPException(status_code=422, detail="Pick the operation you had")
            if body.surgery_date is None or body.surgery_date > date.today():
                raise HTTPException(status_code=422, detail="Enter the date of your surgery")
            procedure, anchor = body.procedure_type, body.surgery_date
        else:
            procedure, anchor = "NONE", date.today()
        surgeon_id, assigned_id = mobile._default_provider(db, body.had_surgery)
        parts = patient.name.split()
        clinic = Patient(
            id=mobile._slug(patient.name, db), name=patient.name,
            initials="".join(p[0] for p in parts[:2]).upper(), age=patient.age, sex=patient.sex,
            procedure_type=procedure, procedure_display=mobile.PROCEDURE_DISPLAY[procedure],
            surgery_date=anchor, discharge_date=anchor, surgeon_id=surgeon_id,
            assigned_provider_id=assigned_id, hospital_id=body.hospital_id,
            date_of_birth=patient.date_of_birth, phone=None,
            care_pathway=None if body.had_surgery else "general_recovery", account_kind=CLINIC,
        )
        db.add(clinic)
        db.commit()
    else:
        if not body.patient_id:
            raise HTTPException(status_code=422, detail="Pick your record")
        clinic = db.get(Patient, body.patient_id)
        if clinic is None or is_personal(clinic) or clinic.hospital_id != body.hospital_id:
            raise HTTPException(status_code=404, detail="Unknown record")
        if clinic.linked_patient_id:
            raise HTTPException(status_code=409, detail="That record already has a personal space")
        open_record = not clinic.phone or clinic.phone == patient.phone
        if not open_record:
            if not sendblue.configured():
                raise HTTPException(
                    status_code=409,
                    detail="That record has a different number on file. Ask your care team to "
                    "update it, then try again.",
                )
            started = mobile._start_verification(db, clinic, patient.phone or clinic.phone,
                                                 send_to=clinic.phone)
            started["intent"] = "link"
            db.commit()
            return started
    try:
        result = identity.link(db, clinic, patient)
    except PersonalIdentityError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    if mobile._first_enrollment(db, clinic):
        mobile._welcome(db, clinic)
    token = mobile._issue_session(db, clinic, body.device_name, body.app_version)
    return {"status": "linked", "link": result, "session_token": token,
            "me": mobile.me_view(db, clinic), "profiles": identity.profiles_view(db, clinic)}


# --- the profile ------------------------------------------------------------------------------


@router.get("/personal/profile")
def get_profile(patient: Patient = Depends(personal_patient), db: Session = Depends(get_db)) -> dict:
    profile = _profile(db, patient)
    return {"profile": _profile_view(profile), "subscription": subscription.status(db, patient),
            "profiles": identity.profiles_view(db, patient)}


class ProfilePatch(BaseModel):
    goal: str | None = None
    sport: str | None = None
    weekly_target_minutes: int | None = Field(default=None, ge=0, le=3000)
    sleep_target_hours: float | None = Field(default=None, ge=4, le=12)
    injury: str | None = None
    units: str | None = None
    sms_briefs: bool | None = None
    brief_hour: int | None = Field(default=None, ge=0, le=23)


@router.patch("/personal/profile")
def patch_profile(body: ProfilePatch, patient: Patient = Depends(personal_patient),
                  db: Session = Depends(get_db)) -> dict:
    profile = _profile(db, patient)
    if body.goal is not None:
        if body.goal not in GOALS:
            raise HTTPException(status_code=422, detail="Unknown goal")
        profile.goal = body.goal
    for field in ("sport", "weekly_target_minutes", "sleep_target_hours", "injury",
                  "sms_briefs", "brief_hour"):
        value = getattr(body, field)
        if value is not None:
            setattr(profile, field, value.strip()[:120] if isinstance(value, str) else value)
    if body.units in ("metric", "imperial"):
        profile.units = body.units
    db.commit()
    return {"profile": _profile_view(profile)}


# --- subscription -------------------------------------------------------------------------------


@router.get("/personal/subscription")
def get_subscription(patient: Patient = Depends(personal_patient),
                     db: Session = Depends(get_db)) -> dict:
    return subscription.status(db, patient)


class AppleTransactionBody(BaseModel):
    jws: str = Field(min_length=20, max_length=20000)
    environment: str | None = None


@router.post("/personal/subscription/apple")
def apple_transaction(body: AppleTransactionBody, patient: Patient = Depends(personal_patient),
                      db: Session = Depends(get_db)) -> dict:
    try:
        row = subscription.apply_apple_transaction(db, patient, body.jws,
                                                   environment_hint=body.environment)
    except SubscriptionError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    db.commit()
    return {"ok": True, "entitlement": {
        "source": row.source, "product_id": row.product_id, "status": row.status,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "verified": row.verified, "environment": row.environment,
    }, "subscription": subscription.status(db, patient)}


# --- the readouts ---------------------------------------------------------------------------------


def _dashboard(db: Session, patient: Patient, profile: PersonalProfile) -> dict[str, Any]:
    data = load_personal_data(db, patient)
    dashboard = compute_dashboard(data, patient, profile)
    dashboard["notes"] = data.notes
    return dashboard


def _care_section(db: Session, patient: Patient, profile: PersonalProfile) -> dict[str, Any] | None:
    """The M1–M18 report for a recovery goal: the clinic engine's own
    metrics, computed over the same stream."""
    if profile.goal != "recovery":
        return None
    try:
        assessment = ensure_fresh_assessment(db, patient.id)
    except Exception:  # noqa: BLE001 — the readouts stand without this section
        logger.exception("care metrics failed for personal %s", patient.id)
        return None
    care = (assessment.analytics or {}).get("care_metrics") or {}
    metrics = [m for m in care.get("metrics", []) if m.get("applicable", True)]
    headline = care.get("headline", [])
    return {
        "pathway": care.get("pathway"), "headline": headline,
        "metrics": metrics,
        "risk": {"level": assessment.risk_level, "reasons": assessment.reasons},
        "trajectory": {"state": assessment.trajectory_state, "pct": assessment.trajectory_pct},
        "postop_day": (assessment.analytics or {}).get("postop_day"),
        "computed_at": assessment.computed_at.isoformat(),
    }


@router.get("/personal/dashboard")
def dashboard(patient: Patient = Depends(entitled_patient), db: Session = Depends(get_db)) -> dict:
    profile = _profile(db, patient)
    board = _dashboard(db, patient, profile)
    brief = insights.get_brief(db, patient, profile, board)
    care = _care_section(db, patient, profile)
    return {
        "dashboard": {k: v for k, v in board.items() if k not in ("digest", "notes")},
        "brief": brief,
        "care": care,
        "profile": _profile_view(profile),
        "subscription": subscription.status(db, patient),
        "profiles": identity.profiles_view(db, patient),
    }


class DayBody(BaseModel):
    text: bool = False


@router.post("/personal/day")
def start_day(body: DayBody | None = None, patient: Patient = Depends(entitled_patient),
              db: Session = Depends(get_db)) -> dict:
    """Start the day: write today's plan, generate the brief, put it on the
    thread. The app calls this on first open; the scheduler calls the same
    code for everyone each morning."""
    profile = _profile(db, patient)
    result = daily.start_day(db, patient, profile, text=bool(body and body.text))
    board = result["dashboard"]
    return {
        "dashboard": {k: v for k, v in board.items() if k not in ("digest", "notes")},
        "brief": result["brief"], "plan": result["plan"], "texted": result["texted"],
        "care": _care_section(db, patient, profile),
        "profile": _profile_view(profile),
        "subscription": subscription.status(db, patient),
        "profiles": identity.profiles_view(db, patient),
    }


@router.get("/personal/week")
def week(patient: Patient = Depends(entitled_patient), db: Session = Depends(get_db)) -> dict:
    """This week against last, with the coach's review of it."""
    profile = _profile(db, patient)
    board = _dashboard(db, patient, profile)
    review = insights.get_deep_dive(db, patient, profile, board, "weekly")
    return {"week": board.get("week"), "trends": board.get("trends"), "review": review}


@router.get("/personal/insights/{domain}")
def deep_dive(domain: str, patient: Patient = Depends(entitled_patient),
              db: Session = Depends(get_db)) -> dict:
    if domain not in insights.DOMAINS:
        raise HTTPException(status_code=404, detail="Unknown insight")
    profile = _profile(db, patient)
    board = _dashboard(db, patient, profile)
    return insights.get_deep_dive(db, patient, profile, board, domain)


class LogBody(BaseModel):
    key: str
    value: float | None = None
    text: str | None = Field(default=None, max_length=1000)
    # `dt.date`, not `date`: the field's own name would shadow the type
    # while pydantic evaluates the annotation.
    date: dt.date | None = None


@router.post("/personal/log")
def log_entry(body: LogBody, patient: Patient = Depends(personal_patient),
              db: Session = Depends(get_db)) -> dict:
    if body.key not in LOG_KEYS:
        raise HTTPException(status_code=422, detail="Unknown log key")
    if body.key != "note" and body.value is None:
        raise HTTPException(status_code=422, detail="A value is needed")
    if body.key == "note" and not (body.text or "").strip():
        raise HTTPException(status_code=422, detail="Write something")
    when = body.date or date.today()
    if when > date.today() or when < date.today() - timedelta(days=30):
        raise HTTPException(status_code=422, detail="Log within the last month")
    row = record(db, patient.id, when, body.key, value=body.value, text=body.text, source="app")
    db.commit()
    return {"ok": True, "id": row.id}


# --- export -------------------------------------------------------------------------------------


@router.post("/personal/export")
def export_data(request: Request, patient: Patient = Depends(personal_patient),
                db: Session = Depends(get_db)) -> dict:
    """Everything this account holds, as one JSON document. Written to the
    personal bucket with a short-lived link where there is one; returned
    inline otherwise."""
    from app.models.observation import Observation
    from app.storage import blobs

    profile = _profile(db, patient)
    data = load_personal_data(db, patient)
    board = compute_dashboard(data, patient, profile)
    since = date.today() - timedelta(days=365)
    observations = db.execute(
        select(Observation.local_date, Observation.metric_type, Observation.value_num,
               Observation.unit, Observation.source_provider)
        .where(Observation.patient_id == (patient.observations_from or patient.id),
               Observation.local_date >= since, Observation.deleted_at.is_(None))
        .order_by(Observation.local_date)
    ).all()
    bundle = {
        "exported_at": datetime.now().isoformat(),
        "account": {"id": patient.id, "name": patient.name, "created_at":
                    patient.created_at.isoformat() if patient.created_at else None},
        "profile": _profile_view(profile),
        "subscription": subscription.status(db, patient),
        "dashboard": {k: v for k, v in board.items() if k != "digest"},
        "logs": {key: [{"date": d.isoformat(), "value": v} for d, v in s.items()]
                 for key, s in data.logs.items()},
        "notes": data.notes,
        "observations": [
            {"date": d.isoformat(), "metric": str(m), "value": v, "unit": u, "source": str(p)}
            for d, m, v, u, p in observations
        ],
    }
    payload = json.dumps(bundle, default=str).encode()
    if blobs.enabled_s3():
        key = f"{blobs.PERSONAL_PREFIX}/{patient.id}/exports/{datetime.now():%Y%m%dT%H%M%S}.json"
        blobs.put_json(key, payload)
        url = blobs.download_url(key, "application/json", "medpull-export.json")
        return {"url": url, "bytes": len(payload), "expires_in": blobs.DOWNLOAD_TTL_S}
    return {"url": None, "bytes": len(payload), "data": bundle}
