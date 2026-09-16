import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.worklist import ensure_fresh_assessment
from app.config import settings
from app.database import get_db
from app.models.adherence import AdherenceTask
from app.models.checkin import Checkin
from app.models.enums import InsightKind, MetricType, NotificationChannel
from app.models.hospital import Hospital
from app.models.notification import Notification
from app.models.observation import Observation
from app.models.patient import CareTeamMember, Patient
from app.notifications import sendblue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients", tags=["patients"])


def _get_patient(db: Session, patient_id: str) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_id}")
    return patient


@router.get("/{patient_id}")
def patient_detail(patient_id: str, db: Session = Depends(get_db)) -> dict:
    from app.llm.insights import get_patient_insight

    patient = _get_patient(db, patient_id)
    assessment = ensure_fresh_assessment(db, patient_id)
    analytics = assessment.analytics

    summary = get_patient_insight(db, InsightKind.PATIENT_SUMMARY, patient_id)
    actions = get_patient_insight(db, InsightKind.SUGGESTED_ACTIONS, patient_id)

    last_checkin = db.scalar(
        select(Checkin.occurred_at)
        .where(Checkin.patient_id == patient_id)
        .order_by(Checkin.occurred_at.desc())
        .limit(1)
    )
    # Patient.devices is ordered newest-connected-first, so an upgraded watch
    # wins over the row that happened to be written first. Retired rows are
    # skipped: an unpaired watch, or the account a record merge retired, must
    # not be shown as the live source.
    device = next((d for d in patient.devices if d.status != "revoked"), None)
    from app.identity import app_status

    return {
        "id": patient.id,
        "name": patient.name,
        "initials": patient.initials,
        "age": patient.age,
        "sex": patient.sex,
        "mode": "general" if str(patient.procedure_type) == "NONE" else "recovery",
        "hospital_id": patient.hospital_id,
        "hospital": patient.hospital.name if patient.hospital else None,
        # The console's contact with the person: where texts go, and whether
        # the patient app is signed in on this chart.
        "phone": patient.phone or None,
        "sms_configured": sendblue.configured(),
        "app": app_status(db, patient),
        "procedure_display": patient.procedure_display,
        "postop_day": analytics.get("postop_day"),
        "surgery_date": patient.surgery_date.isoformat(),
        "discharge_date": patient.discharge_date.isoformat(),
        "surgeon": patient.surgeon.name,
        "assigned_provider": patient.assigned_provider.name,
        "device": {
            "provider": str(device.source_provider),
            "model": device.device_model,
            "last_sync_at": device.last_sync_at.isoformat() if device.last_sync_at else None,
        }
        if device
        else None,
        "risk": {
            "level": assessment.risk_level,
            "score": assessment.risk_score,
            "reasons": assessment.reasons,
            "computed_at": assessment.computed_at.isoformat(),
        },
        "data_confidence": {
            "score": analytics["confidence"]["score"],
            "level": analytics["confidence"]["level"],
            "days_with_data": analytics["confidence"]["days_with_data"],
        },
        "trajectory": {
            "state": analytics["trajectory"]["state"],
            "pct": analytics["trajectory"]["pct"],
        },
        "summary": {
            "text": summary.content.get("summary", ""),
            "generated_at": summary.generated_at.isoformat(),
            "provider": summary.llm_provider,
        },
        "actions": actions.content.get("actions", []),
        "last_checkin_at": last_checkin.isoformat() if last_checkin else None,
    }


@router.get("/{patient_id}/metrics")
def patient_metrics(patient_id: str, db: Session = Depends(get_db)) -> dict:
    _get_patient(db, patient_id)
    assessment = ensure_fresh_assessment(db, patient_id)
    analytics = assessment.analytics
    return {
        "data_confidence": analytics["confidence"],
        "trajectory": analytics["trajectory"],
        "composite": analytics["composite"],
        "metrics": analytics["metrics"],
        "adherence": analytics["adherence"],
    }


@router.get("/{patient_id}/timeline")
def patient_timeline(patient_id: str, db: Session = Depends(get_db)) -> dict:
    patient = _get_patient(db, patient_id)
    assessment = ensure_fresh_assessment(db, patient_id)
    analytics = assessment.analytics

    # surgery_date doubles as the enrollment anchor for a general patient, who
    # was never operated on and never discharged: labelling their join date
    # "Surgery" put an operation on the chart of someone who never had one.
    if str(patient.procedure_type) == "NONE":
        events: list[dict] = [
            {"date": patient.surgery_date.isoformat(), "kind": "enrolled",
             "label": "Monitoring started"},
        ]
    else:
        events = [
            {"date": patient.surgery_date.isoformat(), "kind": "surgery", "label": "Surgery"},
            {"date": patient.discharge_date.isoformat(), "kind": "discharge",
             "label": "Discharged"},
        ]

    checkin_dates = db.scalars(
        select(Checkin.occurred_at).where(Checkin.patient_id == patient_id)
    ).all()
    for occurred in checkin_dates:
        events.append(
            {"date": occurred.date().isoformat(), "kind": "checkin", "label": "Daily check-in"}
        )

    change_day = analytics["trajectory"].get("change_point_day")
    if change_day is not None:
        change_date = patient.surgery_date + timedelta(days=int(change_day))
        events.append(
            {
                "date": change_date.isoformat(),
                "kind": "change_point",
                "label": "Trajectory shift",
            }
        )

    severe = [r for r in assessment.reasons if r.get("severity", 0) >= 3][:2]
    for reason in severe:
        events.append(
            {
                "date": assessment.computed_at.date().isoformat(),
                "kind": "flag",
                "label": reason["text"],
            }
        )

    events.append({"date": datetime.now().date().isoformat(), "kind": "today", "label": "Today"})
    events.sort(key=lambda e: (e["date"], e["kind"] == "today"))
    return {"events": events}


@router.get("/{patient_id}/checkins")
def patient_checkins(patient_id: str, db: Session = Depends(get_db)) -> dict:
    from app.engine.checkin_digest import digest

    _get_patient(db, patient_id)
    checkins = db.scalars(
        select(Checkin)
        .where(Checkin.patient_id == patient_id)
        .order_by(Checkin.occurred_at.desc())
    ).all()
    return {
        "checkins": [
            {
                "id": c.id,
                "occurred_at": c.occurred_at.isoformat(),
                "channel": c.channel,
                "messages": [{"who": m.who, "text": m.text} for m in c.messages],
                "digest": digest([{"who": m.who, "text": m.text} for m in c.messages]),
            }
            for c in checkins
        ]
    }


@router.get("/{patient_id}/observations")
def patient_observations(
    patient_id: str, metric_type: str, days: int = 30, db: Session = Depends(get_db)
) -> dict:
    _get_patient(db, patient_id)
    try:
        metric = MetricType(metric_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid metric_type: {metric_type}")

    since = datetime.now() - timedelta(days=days)
    rows = db.scalars(
        select(Observation)
        .where(
            Observation.patient_id == patient_id,
            Observation.metric_type == metric,
            Observation.start_time >= since,
            # A provider tombstone is a retraction: connectors/ingest soft-deletes
            # so the deletion survives redelivery, and every reader owes it the
            # filter or the chart keeps plotting a value the source withdrew.
            Observation.deleted_at.is_(None),
        )
        .order_by(Observation.start_time)
    ).all()
    unit = rows[0].unit if rows else ""
    return {
        "metric_type": metric_type,
        "unit": unit,
        "points": [
            {"t": r.start_time.isoformat(), "v": r.value_num}
            for r in rows
            if r.value_num is not None
        ],
    }


@router.post("/{patient_id}/recompute")
def recompute(patient_id: str, db: Session = Depends(get_db)) -> dict:
    """Full refresh: rerun the deterministic engine AND bust the narrative
    caches, so the next reads trigger fresh LLM generations — this patient's
    insights plus the roster briefing (which embeds this patient's reason).

    It runs to completion and returns the fresh assessment, so it answers 200
    rather than the 202 it used to declare for work it never deferred.

    Not every roster-level row is the briefing: `/api/ask` answers are stored
    with a NULL patient_id too, keyed on questions this patient's numbers need
    not appear in. Deleting by "patient_id IS NULL" emptied that cache as well,
    at one LLM call per cached question to refill."""
    from sqlalchemy import and_, delete, or_

    from app.engine.pipeline import run_patient
    from app.models.insight import Insight

    _get_patient(db, patient_id)
    db.execute(
        delete(Insight).where(
            or_(
                Insight.patient_id == patient_id,
                and_(
                    Insight.patient_id.is_(None),
                    Insight.kind == InsightKind.DAILY_BRIEFING,
                ),
            )
        )
    )
    db.commit()
    assessment = run_patient(db, patient_id, force=True)
    return {
        "risk_level": assessment.risk_level,
        "recomputed_at": assessment.computed_at.isoformat(),
    }


class AssignTaskBody(BaseModel):
    title: str
    why: str = ""
    # checkin | exercise | walk | medication | wound_check | custom
    kind: str = "custom"
    due_at: datetime | None = None
    # Text the patient about it through Sendblue (when configured and the
    # patient has a number on file). Off records the task for the app only.
    notify: bool = True


class MessageBody(BaseModel):
    # Empty is valid when a file is attached: a clinician sending a sheet of
    # exercises has nothing to add in words.
    text: str = ""
    attachment_ids: list[int] = Field(default_factory=list, max_length=8)
    # Which care-team member is writing; defaults to the assigned provider.
    sender_id: str | None = None


def _task_view(t: AdherenceTask) -> dict:
    from app.tasks.service import KIND_LABELS

    return {
        "id": t.id,
        "kind": t.kind or "custom",
        "kind_label": KIND_LABELS.get(t.kind or "custom", "Task"),
        "title": t.title,
        "why": t.why,
        "status": t.status or "pending",
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "sent_at": t.sent_at.isoformat() if t.sent_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "completed_via": t.completed_via,
        "answers": (t.result or {}).get("answers") if t.result else None,
    }


def _authorship(m, db: Session | None = None) -> dict:
    """Who stands behind this message, for the UI to label.

    ``kind`` is "care_team" only when a clinician wrote, approved or triggered
    it; everything else reads as "ai", including the rows written before the
    column existed. The copilot is the default and the UI shows no badge for
    it — a tag is a claim, and only a person's name is worth making one about.
    """
    kind = m.authored_by or ("care_team" if m.sender == "care_team" else "ai")
    name = None
    if kind == "care_team" and m.sender_id and db is not None:
        member = db.get(CareTeamMember, m.sender_id)
        name = member.name if member else None
    return {"kind": kind, "name": name}


def _message_view(m, db: Session | None = None,
                  attachments: dict[int, list] | None = None) -> dict:
    return {
        "id": m.id,
        "sender": m.sender,
        "sender_id": m.sender_id,
        "authored_by": _authorship(m, db),
        "channel": m.channel,
        "text": m.text,
        "created_at": m.created_at.isoformat(),
        "delivery_status": m.delivery_status,
        "delivery_detail": m.delivery_detail,
        "attachments": (attachments or {}).get(m.id, []),
        "read_by_care_team": m.read_by_care_team_at is not None,
    }


@router.post("/{patient_id}/actions/assign-task")
def assign_task(
    patient_id: str, body: AssignTaskBody, request: Request, db: Session = Depends(get_db)
) -> dict:
    """Create a task in the patient's plan and, by default, text them about
    it. Completion is tracked: the patient finishes it in the app, by
    replying to the text, by voice, or on the linked web page, and each
    completion writes the adherence record the engine scores."""
    from app.tasks.service import create_task

    patient = _get_patient(db, patient_id)
    base = settings.checkin_base_url or str(request.base_url).rstrip("/")
    try:
        task, sms = create_task(
            db, patient, title=body.title, why=body.why, kind=body.kind,
            due_at=body.due_at, notify=body.notify, base_url=base,
            created_by=patient.assigned_provider_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if sms is None:
        status = "assigned"
    elif sms.sent:
        status = "assigned_texted"
    else:
        status = "assigned_not_texted"
    return {
        "ok": True,
        "status": status,
        "sms": {"sent": sms.sent, "detail": sms.detail} if sms else None,
        "task": _task_view(task),
    }


@router.get("/{patient_id}/tasks")
def list_tasks(patient_id: str, db: Session = Depends(get_db)) -> dict:
    from app.tasks.service import recent_tasks

    _get_patient(db, patient_id)
    return {"tasks": [_task_view(t) for t in recent_tasks(db, patient_id, limit=50)]}


@router.post("/{patient_id}/actions/message")
def message_patient(patient_id: str, body: MessageBody, db: Session = Depends(get_db)) -> dict:
    """Write to the patient's thread (the app shows it) and text it through
    Sendblue when the patient has a number on file and the keys are set."""
    from app.models.mobile import Message
    from app.notifications import sendblue

    patient = _get_patient(db, patient_id)
    text = body.text.strip()
    if not text and not body.attachment_ids:
        raise HTTPException(status_code=422, detail="Write something, or attach a file")
    sender_id = body.sender_id or patient.assigned_provider_id
    member = db.get(CareTeamMember, sender_id)
    if member is None:
        raise HTTPException(status_code=404, detail=f"Unknown sender: {sender_id}")
    # A clinician typed or approved this, so it is theirs to stand behind and
    # it goes out under their name. The stored copy keeps the text as written;
    # only the outbound text carries the tag and loses the patient's name.
    message = Message(
        patient_id=patient.id, sender="care_team", sender_id=sender_id, channel="console",
        text=text, authored_by="care_team",
    )
    db.add(message)
    db.flush()
    from app.api.attachments import attachments_for, claim

    attached = claim(db, patient, body.attachment_ids, message)
    delivery = None
    if patient.phone:
        # The link is only worth sending when it goes somewhere the patient
        # can use. Someone already on the app has this message in their thread
        # and can simply reply to the text; someone who has never enrolled has
        # one useful destination, which is the app itself.
        from app.identity import app_status

        enrolled = app_status(db, patient)["ever_enrolled"]
        # A file is never sent as provider media: that publishes a patient's
        # photograph to an unauthenticated URL. The text says one arrived and
        # the app is where it can be seen, which is also why an enrolled
        # patient needs no link — it is already in their thread.
        body_text = text
        if attached and not text:
            body_text = "Your care team sent you a file." if attached == 1 else (
                f"Your care team sent you {attached} files.")
        elif attached:
            body_text = f"{text} ({attached} attached)"
        delivery = sendblue.send_care_team_message(
            patient.phone, body_text, member=member, patient_name=patient.name,
            link=None if enrolled else settings.app_download_url,
        )
        message.delivery_status = "sent" if delivery.sent else "failed"
        message.delivery_detail = None if delivery.sent else delivery.detail
        message.external_handle = delivery.message_handle
    db.commit()
    if delivery is not None and delivery.sent:
        status = "sent_sms"
    elif patient.phone:
        status = "stored_sms_failed"
    else:
        status = "stored_app_only"
    return {
        "status": status,
        "detail": delivery.detail if delivery else "patient has no phone number on file",
        "message": _message_view(message, db, attachments_for(db, [message])),
    }


@router.get("/{patient_id}/messages")
def list_messages(patient_id: str, db: Session = Depends(get_db)) -> dict:
    from app.models.mobile import Message

    _get_patient(db, patient_id)
    from app.api.attachments import attachments_for

    rows = db.scalars(
        select(Message).where(Message.patient_id == patient_id).order_by(Message.id).limit(300)
    ).all()
    # One query for three hundred lines, beside the clinician-name lookup.
    files = attachments_for(db, rows)
    return {"messages": [_message_view(m, db, files) for m in rows]}


@router.post("/{patient_id}/messages/read")
def mark_messages_read(patient_id: str, db: Session = Depends(get_db)) -> dict:
    from app.models.mobile import Message

    _get_patient(db, patient_id)
    rows = db.scalars(
        select(Message).where(
            Message.patient_id == patient_id,
            Message.sender == "patient",
            Message.read_by_care_team_at.is_(None),
        )
    ).all()
    now = datetime.now()
    for m in rows:
        m.read_by_care_team_at = now
    db.commit()
    return {"ok": True, "count": len(rows)}


@router.post("/{patient_id}/actions/draft-message")
def draft_message(patient_id: str, db: Session = Depends(get_db)) -> dict:
    """AI-drafted patient message — for the clinician to edit before queueing."""
    from app.engine.pipeline import latest_assessment
    from app.llm.draft import draft_message as draft

    patient = _get_patient(db, patient_id)
    assessment = latest_assessment(db, patient_id)
    if assessment is None:
        raise HTTPException(status_code=409, detail="No analysis available yet for this patient")
    return draft(db, patient, assessment)


@router.post("/{patient_id}/actions/escalate")
def escalate(patient_id: str, db: Session = Depends(get_db)) -> dict:
    from app.engine.pipeline import latest_assessment

    patient = _get_patient(db, patient_id)
    assessment = latest_assessment(db, patient_id)
    top_reason = (
        assessment.reasons[0]["text"]
        if assessment is not None and assessment.reasons
        else "Provider requested review"
    )
    notification = Notification(
        patient_id=patient_id,
        recipient_id=patient.assigned_provider_id,
        kind="escalation",
        title=f"{patient.name} — escalated by provider",
        body=top_reason,
        channel=NotificationChannel.IN_APP,
    )
    db.add(notification)
    db.commit()
    return {"ok": True}


class ContactBody(BaseModel):
    phone: str | None = None
    # Move the number here when another chart already holds it.
    force: bool = False


@router.patch("/{patient_id}/contact")
def update_contact(patient_id: str, body: ContactBody, db: Session = Depends(get_db)) -> dict:
    """Set (or clear) the number the console texts. Refuses a number that is
    on another chart unless ``force`` moves it, so one number maps to one
    patient and inbound texts cannot land on the wrong chart."""
    from app.identity import IdentityError, app_status, set_phone

    patient = _get_patient(db, patient_id)
    try:
        result = set_phone(db, patient, body.phone, force=body.force)
    except IdentityError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    return {**result, "app": app_status(db, patient)}


@router.get("/{patient_id}/app-link/candidates")
def app_link_candidates(patient_id: str, db: Session = Depends(get_db)) -> dict:
    """Records this chart could be linked to: other patients who signed in
    on the app or have a phone — the person's own sign-up, usually."""
    from app.identity import app_status, link_candidates

    patient = _get_patient(db, patient_id)
    return {"app": app_status(db, patient), "phone": patient.phone or None,
            "candidates": link_candidates(db, patient)}


class LinkBody(BaseModel):
    from_patient_id: str


@router.post("/{patient_id}/app-link")
def link_app(patient_id: str, body: LinkBody, db: Session = Depends(get_db)) -> dict:
    """Fold another record (the one the app enrolled against) into this
    chart. The app session, thread, tasks and data move here and the other
    record is deleted, so the phone acts as this chart from the next request."""
    from app.identity import IdentityError, app_status, link_app_account

    patient = _get_patient(db, patient_id)
    source = db.get(Patient, body.from_patient_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Unknown patient: {body.from_patient_id}")
    try:
        result = link_app_account(db, patient, source)
    except IdentityError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    return {**result, "app": app_status(db, patient)}


class CreatePatientBody(BaseModel):
    hospital_id: str
    name: str
    phone: str | None = None
    date_of_birth: str | None = None  # YYYY-MM-DD
    sex: str | None = None  # M, F, X
    procedure_type: str | None = None  # TKA, THA, etc. or NONE for general
    surgery_date: str | None = None  # YYYY-MM-DD


def require_hospital_auth(
    authorization: str | None = Header(default=None), 
    db: Session = Depends(get_db)
) -> Hospital:
    """Require valid hospital access token for dashboard operations."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Hospital access token required")
    token = authorization.split(" ", 1)[1].strip()
    
    hospital = db.scalar(select(Hospital).where(Hospital.access_token == token))
    if hospital is None:
        raise HTTPException(status_code=401, detail="Invalid hospital access token")
    if not hospital.active:
        raise HTTPException(status_code=403, detail="Hospital account inactive")
    return hospital


@router.post("/")
def create_patient(
    body: CreatePatientBody, 
    hospital: Hospital = Depends(require_hospital_auth),
    db: Session = Depends(get_db)
) -> dict:
    """Create a new patient record for the authenticated hospital."""
    # Ensure the request matches the authenticated hospital
    if body.hospital_id != hospital.id:
        raise HTTPException(status_code=403, detail="Cannot create patients for other hospitals")
    
    # Validate procedure type if provided
    from app.api.mobile import PROCEDURE_DISPLAY
    if body.procedure_type and body.procedure_type not in PROCEDURE_DISPLAY:
        raise HTTPException(status_code=422, detail="Invalid procedure type")
    
    # Parse dates if provided
    surgery_date = None
    date_of_birth = None
    if body.surgery_date:
        try:
            surgery_date = date.fromisoformat(body.surgery_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid surgery date format (use YYYY-MM-DD)")
        # A future date makes post-op day negative, which the coverage window
        # reads as "no days to assess": the patient would sit in Missing data
        # for ever while their watch streamed.
        if surgery_date > date.today():
            raise HTTPException(
                status_code=422,
                detail="Surgery date is in the future — create the record after the operation",
            )
    
    if body.date_of_birth:
        try:
            date_of_birth = date.fromisoformat(body.date_of_birth)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date of birth format (use YYYY-MM-DD)")
    
    # Determine procedure type and anchor date
    if body.procedure_type and body.procedure_type != "NONE":
        if not surgery_date:
            raise HTTPException(status_code=422, detail="Surgery date required for surgical patients")
        procedure = body.procedure_type
        anchor = surgery_date
        care_pathway = None
    else:
        procedure = "NONE"
        anchor = surgery_date or date.today()
        care_pathway = "general_recovery"
    
    # The number texts go to: valid or absent, never a raw string that every
    # send would then reject, and never one already on another chart.
    phone: str | None = None
    if body.phone and body.phone.strip():
        phone = sendblue.normalize_phone(body.phone)
        if phone is None:
            raise HTTPException(status_code=422, detail="Enter a valid mobile number")
        holder = db.scalar(select(Patient).where(Patient.phone == phone))
        if holder is not None:
            raise HTTPException(
                status_code=409,
                detail=f"That number is already on {holder.name} ({holder.id})",
            )
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Name is required")

    # Generate unique patient ID
    from app.api.mobile import _slug
    patient_id = _slug(body.name, db)
    
    # Get default care team
    from app.api.mobile import _default_provider
    surgeon_id, assigned_id = _default_provider(db, procedure != "NONE")
    
    # Create patient
    name_parts = body.name.split()
    patient = Patient(
        id=patient_id,
        name=body.name.strip(),
        initials="".join(part[0] for part in name_parts[:2]).upper(),
        age=0,  # Will be calculated from date_of_birth if provided
        sex=(body.sex or "U")[:1].upper() if body.sex else "U",
        procedure_type=procedure,
        procedure_display=PROCEDURE_DISPLAY[procedure],
        surgery_date=anchor,
        discharge_date=anchor,
        surgeon_id=surgeon_id,
        assigned_provider_id=assigned_id,
        hospital_id=body.hospital_id,
        date_of_birth=date_of_birth,
        care_pathway=care_pathway,
        phone=phone,
    )
    
    # Calculate age if date_of_birth provided
    if date_of_birth:
        today = date.today()
        patient.age = today.year - date_of_birth.year - (
            (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
        )
        if not 0 <= patient.age <= 120:
            raise HTTPException(status_code=422, detail="Invalid date of birth")
    
    db.add(patient)
    db.commit()

    # Tell the patient they have been set up, and keep a line in their thread
    # so the console can see the invite went out (or why it did not).
    invite: dict = {"sent": False, "detail": "no phone number on file"}
    if patient.phone:
        from app.models.mobile import Message

        delivery = sendblue.send_invite_message(patient.phone)
        db.add(Message(
            patient_id=patient.id, sender="care_team", sender_id=assigned_id, channel="sms",
            text=sendblue.INVITE_TEMPLATE.format(app_url=settings.app_download_url),
            delivery_status="sent" if delivery.sent else "failed",
            delivery_detail=None if delivery.sent else delivery.detail,
            external_handle=delivery.message_handle,
        ))
        db.commit()
        invite = {"sent": delivery.sent, "detail": delivery.detail}

    return {
        "ok": True,
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "hospital_id": patient.hospital_id,
            "procedure_type": patient.procedure_type,
            "surgery_date": patient.surgery_date.isoformat() if patient.surgery_date else None,
        },
        "invite": invite,
    }
