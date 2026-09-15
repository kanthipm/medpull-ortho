"""The care plan: task library, AI task builder, plan assignment and
verification read-back, message templates and drafts, next steps.

Every route is a plain ``def`` (the engine and SQLAlchemy are synchronous).
The library is upserted once per process by the ``_library_ready``
dependency rather than at startup, because ``app/main.py`` and the seed
belong to the patient-app session.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.worklist import ensure_fresh_assessment
from app.config import settings
from app.database import get_db
from app.engine.care.pathways import PATHWAYS, pathway_by_key
from app.llm.insights import BANNED
from app.models.library import MessageTemplate, TaskTemplate
from app.models.patient import Patient
from app.plan import ensure_ready
from app.plan.library import applies_to, pathways_payload, template_payload
from app.plan.messages import TONES, draft_patient_message, message_payload
from app.plan.service import PlanError, PlanItem
from app.plan.verify_kinds import PHASES, SCHEDULES, TASK_KINDS, VerifyKind, kinds_payload

router = APIRouter(tags=["plan"])


def _library_ready(db: Session = Depends(get_db)) -> Session:
    ensure_ready(db)
    return db


def _get_patient(db: Session, patient_id: str) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_id}")
    return patient


def _base_url(request: Request) -> str:
    return settings.checkin_base_url or str(request.base_url).rstrip("/")


def _no_diagnostic(*texts: str | None) -> None:
    for text in texts:
        if text and BANNED.search(text):
            raise HTTPException(
                status_code=422, detail="Patient-facing text must not use diagnostic language"
            )


# --- task templates ---------------------------------------------------------------------


class TemplateCreate(BaseModel):
    title: str = Field(min_length=3, max_length=90)
    why: str = Field(default="", max_length=160)
    clinical_target: str = Field(default="", max_length=160)
    verify_kind: str = "custom"
    task_kind: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    schedule: str = "daily"
    phase: str = "ongoing"
    feeds: list[str] = Field(default_factory=list)
    pathways: list[str] = Field(default_factory=list)
    pinned: bool = False


class TemplatePatch(BaseModel):
    pinned: bool | None = None
    archived: bool | None = None
    title: str | None = Field(default=None, min_length=3, max_length=90)
    why: str | None = Field(default=None, max_length=160)
    clinical_target: str | None = Field(default=None, max_length=160)
    params: dict[str, Any] | None = None
    schedule: str | None = None
    phase: str | None = None
    pathways: list[str] | None = None


@router.get("/task-templates")
def list_task_templates(
    pathway: str | None = None,
    q: str | None = None,
    include_archived: bool = False,
    db: Session = Depends(_library_ready),
) -> dict:
    from app.plan.verify_kinds import verified_by_label

    if pathway is not None and pathway not in PATHWAYS:
        raise HTTPException(status_code=400, detail=f"Unknown pathway: {pathway}")
    resolved = pathway_by_key(pathway) if pathway else None
    needle = (q or "").strip().lower()
    rows = db.scalars(select(TaskTemplate).order_by(TaskTemplate.id)).all()
    templates = []
    for t in rows:
        if t.archived and not include_archived:
            continue
        if resolved is not None and not applies_to(t.pathways, resolved):
            continue
        if needle and needle not in " ".join(
            [t.title, t.why, t.clinical_target, t.key or "", t.use_case,
             verified_by_label(t.verify_kind)]
        ).lower():
            continue
        templates.append(template_payload(t))
    return {"templates": templates, "kinds": kinds_payload(), "pathways": pathways_payload()}


@router.post("/task-templates")
def create_task_template(body: TemplateCreate, db: Session = Depends(_library_ready)) -> dict:
    from app.plan.verify_kinds import as_kind, default_task_kind, params_for

    _no_diagnostic(body.title, body.why)
    try:
        kind = VerifyKind(body.verify_kind)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown verify_kind: {body.verify_kind}")
    task_kind = body.task_kind if body.task_kind in TASK_KINDS else default_task_kind(kind)
    template = TaskTemplate(
        key=None, title=body.title.strip(), why=body.why.strip(),
        clinical_target=body.clinical_target.strip(), task_kind=task_kind,
        verify_kind=str(as_kind(kind)), params=params_for(kind, body.params),
        schedule=body.schedule if body.schedule in SCHEDULES else "daily",
        phase=body.phase if body.phase in PHASES else "ongoing",
        feeds=[f[:8] for f in body.feeds][:8],
        pathways=[p for p in body.pathways if p in PATHWAYS or p in
                  {pw.domain for pw in PATHWAYS.values()} or p == "all"],
        use_case="custom", source="custom", pinned=body.pinned, created_by="provider",
    )
    db.add(template)
    db.commit()
    return template_payload(template)


@router.patch("/task-templates/{template_id}")
def patch_task_template(
    template_id: int, body: TemplatePatch, db: Session = Depends(_library_ready)
) -> dict:
    from app.plan.verify_kinds import params_for

    template = db.get(TaskTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Unknown template")
    _no_diagnostic(body.title, body.why)
    if body.pinned is not None:
        template.pinned = body.pinned
    if body.archived is not None:
        template.archived = body.archived
    if body.title is not None:
        template.title = body.title.strip()
    if body.why is not None:
        template.why = body.why.strip()
    if body.clinical_target is not None:
        template.clinical_target = body.clinical_target.strip()
    if body.params is not None:
        template.params = params_for(template.verify_kind, body.params)
    if body.schedule in SCHEDULES:
        template.schedule = body.schedule
    if body.phase in PHASES:
        template.phase = body.phase
    if body.pathways is not None:
        template.pathways = list(body.pathways)
    db.commit()
    return template_payload(template)


# --- the builder ------------------------------------------------------------------------


class DraftBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    patient_id: str | None = None
    pathway: str | None = None


@router.post("/task-builder/draft")
def task_builder_draft(body: DraftBody, db: Session = Depends(_library_ready)) -> dict:
    from app.plan.builder import draft_tasks

    patient = _get_patient(db, body.patient_id) if body.patient_id else None
    if body.pathway is not None and body.pathway not in PATHWAYS:
        raise HTTPException(status_code=400, detail=f"Unknown pathway: {body.pathway}")
    return draft_tasks(db, body.text, patient, body.pathway)


@router.post("/patients/{patient_id}/plan/suggest")
def suggest_plan(patient_id: str, db: Session = Depends(_library_ready)) -> dict:
    from app.plan.builder import suggest_tasks

    return suggest_tasks(db, _get_patient(db, patient_id))


# --- the plan -----------------------------------------------------------------------------


class PlanItemBody(BaseModel):
    template_id: int | None = None
    template_key: str | None = None
    title: str = ""
    why: str = ""
    clinical_target: str = ""
    task_kind: str | None = None
    verify_kind: str = "custom"
    params: dict[str, Any] = Field(default_factory=dict)
    schedule: str = "daily"
    phase: str = "ongoing"
    feeds: list[str] = Field(default_factory=list)
    due_at: datetime | None = None
    save_as_template: bool = False
    pin: bool = False
    assigned_by: str = "provider"

    def to_item(self) -> PlanItem:
        return PlanItem(
            template_id=self.template_id, template_key=self.template_key, title=self.title,
            why=self.why, clinical_target=self.clinical_target, task_kind=self.task_kind,
            verify_kind=self.verify_kind, params=self.params, schedule=self.schedule,
            phase=self.phase, feeds=self.feeds, due_at=self.due_at,
            save_as_template=self.save_as_template, pin=self.pin, assigned_by=self.assigned_by,
        )


class AssignBody(BaseModel):
    items: list[PlanItemBody] = Field(min_length=1, max_length=12)
    notify: bool = True


class RecordBody(BaseModel):
    date: date
    status: str  # verified | self_attested | missed
    count: float | None = None


@router.get("/patients/{patient_id}/plan")
def get_plan(patient_id: str, db: Session = Depends(_library_ready)) -> dict:
    from app.plan.service import patient_plan

    _get_patient(db, patient_id)
    # A fresh assessment runs verification, so the records below are current.
    ensure_fresh_assessment(db, patient_id)
    return patient_plan(db, patient_id)


@router.post("/patients/{patient_id}/plan")
def assign(
    patient_id: str, body: AssignBody, request: Request, db: Session = Depends(_library_ready)
) -> dict:
    from app.plan.service import assign_plan

    patient = _get_patient(db, patient_id)
    try:
        return assign_plan(
            db, patient, [i.to_item() for i in body.items], notify=body.notify,
            base_url=_base_url(request), created_by=patient.assigned_provider_id or "provider",
        )
    except PlanError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/patients/{patient_id}/plan/{task_id}/end")
def end_plan_task(patient_id: str, task_id: int, db: Session = Depends(_library_ready)) -> dict:
    from app.models.adherence import AdherenceTask
    from app.plan.service import end_task, patient_plan

    _get_patient(db, patient_id)
    task = db.get(AdherenceTask, task_id)
    if task is None or task.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="Unknown task")
    end_task(db, task_id)
    return {"ok": True, "task_id": task_id, "summary": patient_plan(db, patient_id)["summary"]}


@router.post("/patients/{patient_id}/plan/{task_id}/record")
def record_plan_status(
    patient_id: str, task_id: int, body: RecordBody, db: Session = Depends(_library_ready)
) -> dict:
    from app.models.adherence import AdherenceTask
    from app.plan.service import record_provider_status

    _get_patient(db, patient_id)
    task = db.get(AdherenceTask, task_id)
    if task is None or task.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="Unknown task")
    if body.date > date.today():
        raise HTTPException(status_code=422, detail="Cannot record a future day")
    try:
        record = record_provider_status(db, task_id, body.date, body.status, body.count)
    except PlanError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True, "record": {"task_id": task_id, "date": record.date.isoformat(),
                                   "status": str(record.status), "source": "provider",
                                   "count": body.count}}


# --- message templates + drafts ---------------------------------------------------------


class MessageTemplateCreate(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    body: str = Field(min_length=10, max_length=600)
    tone: str = "warm"
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False


class MessageTemplatePatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=80)
    body: str | None = Field(default=None, min_length=10, max_length=600)
    tone: str | None = None
    tags: list[str] | None = None
    pinned: bool | None = None
    archived: bool | None = None


class DraftMessageBody(BaseModel):
    intent: str | None = Field(default=None, max_length=400)
    tone: str = "warm"
    template_id: int | None = None


@router.get("/message-templates")
def list_message_templates(
    include_archived: bool = False, db: Session = Depends(_library_ready)
) -> dict:
    rows = db.scalars(select(MessageTemplate).order_by(MessageTemplate.id)).all()
    return {
        "templates": [message_payload(t) for t in rows if include_archived or not t.archived],
        "tones": list(TONES),
    }


@router.post("/message-templates")
def create_message_template(
    body: MessageTemplateCreate, db: Session = Depends(_library_ready)
) -> dict:
    _no_diagnostic(body.title, body.body)
    template = MessageTemplate(
        key=None, title=body.title.strip(), body=body.body.strip(),
        tone=body.tone if body.tone in TONES else "warm", tags=[t[:24] for t in body.tags][:8],
        source="custom", pinned=body.pinned, created_by="provider",
    )
    db.add(template)
    db.commit()
    return message_payload(template)


@router.patch("/message-templates/{template_id}")
def patch_message_template(
    template_id: int, body: MessageTemplatePatch, db: Session = Depends(_library_ready)
) -> dict:
    template = db.get(MessageTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Unknown template")
    _no_diagnostic(body.title, body.body)
    if body.title is not None:
        template.title = body.title.strip()
    if body.body is not None:
        template.body = body.body.strip()
    if body.tone in TONES:
        template.tone = body.tone
    if body.tags is not None:
        template.tags = [t[:24] for t in body.tags][:8]
    if body.pinned is not None:
        template.pinned = body.pinned
    if body.archived is not None:
        template.archived = body.archived
    db.commit()
    return message_payload(template)


@router.post("/patients/{patient_id}/messages/draft")
def draft_message(
    patient_id: str, body: DraftMessageBody, db: Session = Depends(_library_ready)
) -> dict:
    patient = _get_patient(db, patient_id)
    ensure_fresh_assessment(db, patient_id)
    try:
        return draft_patient_message(
            db, patient, intent=body.intent, tone=body.tone, template_id=body.template_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- next steps ----------------------------------------------------------------------------


class ExecuteBody(BaseModel):
    payload_override: dict[str, Any] | None = None


class CompleteBody(BaseModel):
    result: dict[str, Any] = Field(default_factory=dict)


@router.get("/patients/{patient_id}/next-steps")
def next_steps(patient_id: str, db: Session = Depends(_library_ready)) -> dict:
    from app.plan.next_steps import plan_next_steps

    patient = _get_patient(db, patient_id)
    assessment = ensure_fresh_assessment(db, patient_id)
    now = datetime.now()
    return {"steps": plan_next_steps(db, patient, assessment, now=now),
            "generated_at": now.isoformat()}


@router.post("/patients/{patient_id}/next-steps/{key}/execute")
def execute_next_step(
    patient_id: str, key: str, body: ExecuteBody | None = None, request: Request = None,
    db: Session = Depends(_library_ready),
) -> dict:
    from app.plan.next_steps import execute_step

    patient = _get_patient(db, patient_id)
    try:
        return execute_step(
            db, patient, key, override=(body.payload_override if body else None),
            base_url=_base_url(request) if request is not None else "",
            executed_by=patient.assigned_provider_id or "provider",
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValueError, PlanError) as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/patients/{patient_id}/next-steps/{key}/complete")
def complete_next_step(
    patient_id: str, key: str, body: CompleteBody | None = None,
    db: Session = Depends(_library_ready),
) -> dict:
    from app.plan.next_steps import complete_step

    patient = _get_patient(db, patient_id)
    return complete_step(db, patient, key, body.result if body else None,
                         executed_by=patient.assigned_provider_id or "provider")


@router.post("/patients/{patient_id}/next-steps/{key}/dismiss")
def dismiss_next_step(patient_id: str, key: str, db: Session = Depends(_library_ready)) -> dict:
    from app.plan.next_steps import dismiss_step

    patient = _get_patient(db, patient_id)
    return dismiss_step(db, patient, key, executed_by=patient.assigned_provider_id or "provider")
