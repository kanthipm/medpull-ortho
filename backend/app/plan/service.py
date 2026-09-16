"""Assigning a care plan and reading it back.

A plan item — a library template or an AI-drafted task — becomes one of the
patient-app session's ``AdherenceTask`` rows through THEIR ``create_task``
(so the app, the SMS conversation and the tokenized web page all see it),
with the care-plan semantics stored under ``payload["care"]``: which
template it came from, how data verifies it, what it feeds. One summary
text, not one per task, tells the patient what was added.

``patient_plan`` is the read side: every active task with its last fourteen
days of records, the provenance of each record (``TaskVerification``) and
the rates the adherence metrics use.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.care.pathways import pathway_for
from app.llm.insights import BANNED
from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.enums import AdherenceStatus
from app.models.library import TaskTemplate, TaskVerification
from app.models.mobile import Message
from app.models.patient import Patient
from app.notifications import sendblue
from app.plan.verify_kinds import (
    PHASES,
    SCHEDULES,
    TASK_KINDS,
    VerifyKind,
    as_kind,
    default_task_kind,
    params_for,
    verified_by_label,
)
from app.tasks.service import KIND_LABELS, create_task

logger = logging.getLogger(__name__)

WINDOW_DAYS = 14
PLAN_TEXT_MAX = 900
TITLE_MAX, WHY_MAX, TARGET_MAX = 90, 160, 160
RECORD_RANK = {
    str(AdherenceStatus.MISSED): 0,
    str(AdherenceStatus.SELF_ATTESTED): 1,
    str(AdherenceStatus.VERIFIED): 2,
}


@dataclass
class PlanItem:
    template_id: int | None = None
    template_key: str | None = None
    title: str = ""
    why: str = ""
    clinical_target: str = ""
    task_kind: str | None = None
    verify_kind: str = "custom"
    params: dict[str, Any] = field(default_factory=dict)
    schedule: str = "daily"
    phase: str = "ongoing"
    feeds: list[str] = field(default_factory=list)
    due_at: datetime | None = None
    save_as_template: bool = False
    pin: bool = False
    assigned_by: str = "provider"     # "provider" | "ai"
    rationale: str | None = None


class PlanError(ValueError):
    """A plan item the service cannot turn into a task (the API answers 422)."""


def _clean(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def resolve_item(db: Session, item: PlanItem) -> tuple[PlanItem, TaskTemplate | None]:
    """Fill an item from its template (id or key) where the item is silent,
    then normalize every enum-ish field so THEIR ``create_task`` and our
    verification engine both accept it."""
    template: TaskTemplate | None = None
    if item.template_id is not None:
        template = db.get(TaskTemplate, item.template_id)
        if template is None:
            raise PlanError(f"Unknown template id {item.template_id}")
    elif item.template_key:
        template = db.scalar(select(TaskTemplate).where(TaskTemplate.key == item.template_key))
        if template is None:
            raise PlanError(f"Unknown template key {item.template_key!r}")

    title = _clean(item.title, TITLE_MAX) or (template.title if template else "")
    if not title:
        raise PlanError("A task needs a title")
    why = _clean(item.why, WHY_MAX) or (template.why if template else "")
    target = _clean(item.clinical_target, TARGET_MAX) or (
        template.clinical_target if template else "")
    if template is not None and item.verify_kind in (None, "", "custom"):
        verify_kind = as_kind(template.verify_kind)
    else:
        verify_kind = as_kind(item.verify_kind)
    task_kind = item.task_kind or (template.task_kind if template else None) \
        or default_task_kind(verify_kind)
    if task_kind not in TASK_KINDS:
        task_kind = default_task_kind(verify_kind)
    params = params_for(verify_kind, {**(template.params if template else {}), **(item.params or {})})
    schedule = item.schedule if item.schedule in SCHEDULES else (
        template.schedule if template and template.schedule in SCHEDULES else "daily")
    phase = item.phase if item.phase in PHASES else (
        template.phase if template and template.phase in PHASES else "ongoing")
    feeds = [str(f)[:8] for f in (item.feeds or (template.feeds if template else []))][:8]
    for text in (title, why):
        if BANNED.search(text):
            raise PlanError("Patient-facing text must not use diagnostic language")
    resolved = PlanItem(
        template_id=template.id if template else None,
        template_key=template.key if template else item.template_key,
        title=title, why=why, clinical_target=target, task_kind=task_kind,
        verify_kind=str(verify_kind), params=params, schedule=schedule, phase=phase,
        feeds=feeds, due_at=item.due_at, save_as_template=item.save_as_template, pin=item.pin,
        assigned_by=item.assigned_by if item.assigned_by in ("provider", "ai") else "provider",
        rationale=item.rationale,
    )
    return resolved, template


def care_payload(item: PlanItem, pathway_key: str, today: date) -> dict[str, Any]:
    return {
        "template_key": item.template_key,
        "verify": {"kind": item.verify_kind, "params": item.params},
        "feeds": list(item.feeds),
        "phase": item.phase,
        "schedule": item.schedule,
        "clinical_target": item.clinical_target,
        "pathway": pathway_key,
        "assigned_by": item.assigned_by,
        "assigned_on": today.isoformat(),
    }


def plan_text(patient: Patient, tasks: list[AdherenceTask]) -> str:
    """The one summary text. Only the task wording, which is number-free by
    library rule; never a metric, a score or a date."""
    first = (patient.name or "there").split()[0]
    n = len(tasks)
    head = f"Hi {first} — your care team added {n} task{'s' if n != 1 else ''} to your plan:\n"
    tail = "\nReply 1 to start the first one by text, or open the MedPull app."
    lines: list[str] = []
    budget = PLAN_TEXT_MAX - len(head) - len(tail)
    for i, task in enumerate(tasks, start=1):
        line = f"{i}. {task.title}" + (f" — {task.why}" if task.why else "")
        remaining = n - i
        reserve = len(f"\n…and {remaining} more") if remaining else 0
        if sum(len(x) + 1 for x in lines) + len(line) + reserve > budget:
            lines.append(f"…and {n - i + 1} more")
            break
        lines.append(line)
    return head + "\n".join(lines) + tail


def assign_plan(
    db: Session,
    patient: Patient,
    items: list[PlanItem],
    *,
    notify: bool,
    base_url: str = "",
    created_by: str = "provider",
) -> dict[str, Any]:
    if not items:
        raise PlanError("No tasks to assign")
    pathway = pathway_for(patient)
    today = date.today()
    # Resolve and validate EVERY item before creating any task. Resolution is
    # what rejects an unknown template, a missing title or diagnostic wording,
    # and it used to run inside the creation loop: item three failing left
    # items one and two committed and texted, with the caller seeing a 422 and
    # no way to know half a plan had been assigned.
    resolved = [resolve_item(db, raw) for raw in items]
    tasks: list[AdherenceTask] = []
    for item, template in resolved:
        task, _ = create_task(
            db, patient, title=item.title, why=item.why, kind=item.task_kind,
            due_at=item.due_at, notify=False, base_url=base_url, created_by=created_by,
        )
        task.payload = {**(task.payload or {}), "care": care_payload(item, pathway.key, today)}
        # create_task has flushed the row; the care payload above is what makes
        # it a plan task, so it must be in place before anything reads it.
        task.verified_by = verified_by_label(item.verify_kind)
        if template is not None:
            template.usage_count = int(template.usage_count or 0) + 1
        if item.save_as_template and template is None:
            db.add(TaskTemplate(
                key=None, title=item.title, why=item.why, clinical_target=item.clinical_target,
                task_kind=item.task_kind, verify_kind=item.verify_kind, params=item.params,
                schedule=item.schedule, phase=item.phase, feeds=list(item.feeds),
                pathways=[pathway.key], use_case="custom",
                source="ai" if item.assigned_by == "ai" else "custom",
                pinned=item.pin, created_by=created_by,
            ))
        elif item.pin and template is not None:
            template.pinned = True
        tasks.append(task)

    delivery: dict[str, Any] = {"channel": "none", "sent": False, "detail": "not requested"}
    if notify:
        if not patient.phone:
            delivery = {"channel": "none", "sent": False,
                        "detail": "patient has no phone number on file"}
        else:
            text = plan_text(patient, tasks)
            result = sendblue.send_sms(patient.phone, text)
            message = Message(
                patient_id=patient.id, sender="copilot", channel="sms", text=text,
                delivery_status="sent" if result.sent else "failed",
                delivery_detail=None if result.sent else result.detail,
                external_handle=result.message_handle,
            )
            db.add(message)
            if result.sent:
                now = datetime.now()
                for task in tasks:
                    task.status = "sent"
                    task.sent_at = now
            db.flush()
            delivery = {"channel": "sms", "sent": result.sent, "detail": result.detail,
                        "message_id": message.id}
    db.commit()

    # The input hash covers the newest task id, so this recomputes: M14/M15
    # and the verification engine see the plan at once.
    from app.engine.pipeline import run_patient

    run_patient(db, patient.id)
    plan = patient_plan(db, patient.id, today)
    ids = {t.id for t in tasks}
    return {
        "tasks": [t for t in plan["tasks"] if t["id"] in ids],
        "delivery": delivery,
        "summary": plan["summary"],
    }


# --- reading the plan ---------------------------------------------------------------


def active_tasks(db: Session, patient_id: str) -> list[AdherenceTask]:
    return list(db.scalars(
        select(AdherenceTask)
        .where(AdherenceTask.patient_id == patient_id, AdherenceTask.active.is_(True))
        .order_by(AdherenceTask.id)
    ).all())


def care_of(task: AdherenceTask) -> dict[str, Any] | None:
    payload = task.payload if isinstance(task.payload, dict) else {}
    care = payload.get("care")
    return care if isinstance(care, dict) else None


def active_template_keys(db: Session, patient_id: str) -> set[str]:
    keys: set[str] = set()
    for task in active_tasks(db, patient_id):
        care = care_of(task)
        if care and care.get("template_key"):
            keys.add(str(care["template_key"]))
    return keys


def _record_source(task: AdherenceTask, meta: TaskVerification | None) -> str:
    if meta is not None:
        return meta.source
    payload = task.payload if isinstance(task.payload, dict) else {}
    if payload.get("care") or payload.get("created_by") or task.result:
        return "self_report"
    return "seed"


def task_payload(
    task: AdherenceTask,
    records: dict[date, AdherenceRecord],
    meta: dict[date, TaskVerification],
    today: date,
) -> dict[str, Any]:
    care = care_of(task) or {}
    verify = care.get("verify") if isinstance(care.get("verify"), dict) else {}
    assigned_on = care.get("assigned_on")
    if assigned_on is None and task.created_at is not None:
        assigned_on = task.created_at.date().isoformat()
    last14: list[dict[str, Any]] = []
    counts = {"verified": 0, "self_attested": 0, "missed": 0}
    for i in range(WINDOW_DAYS):
        day = today - timedelta(days=WINDOW_DAYS - 1 - i)
        record = records.get(day)
        note = meta.get(day)
        if record is None:
            status = "pending" if day == today else "none"
            source, count = None, None
        else:
            status = str(record.status)
            source = _record_source(task, note)
            count = note.count if note is not None else None
            if status in counts:
                counts[status] += 1
        last14.append({"date": day.isoformat(), "status": status, "source": source,
                       "count": count})
    assigned = sum(counts.values())
    return {
        "id": task.id,
        "title": task.title,
        "why": task.why,
        "clinical_target": care.get("clinical_target", ""),
        "task_kind": task.kind or "custom",
        "kind_label": KIND_LABELS.get(task.kind or "custom", "Task"),
        "verify_kind": verify.get("kind"),
        "params": verify.get("params") or {},
        "schedule": care.get("schedule", "daily"),
        "phase": care.get("phase", "ongoing"),
        "feeds": list(care.get("feeds") or []),
        "verified_by": task.verified_by,
        "active": bool(task.active),
        "status": task.status or "pending",
        "assigned_at": task.created_at.isoformat() if task.created_at else None,
        "assigned_on": assigned_on,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "sent_at": task.sent_at.isoformat() if task.sent_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "completed_via": task.completed_via,
        "template_key": care.get("template_key"),
        "pathway": care.get("pathway"),
        "assigned_by": care.get("assigned_by", "seed" if not care else "provider"),
        "last14": last14,
        "rate": round((counts["verified"] + 0.5 * counts["self_attested"]) / assigned, 2)
        if assigned else None,
        "verified_rate": round(counts["verified"] / assigned, 2) if assigned else None,
        **counts,
    }


def patient_plan(db: Session, patient_id: str, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    start = today - timedelta(days=WINDOW_DAYS - 1)
    tasks = active_tasks(db, patient_id)
    records = db.scalars(
        select(AdherenceRecord).where(
            AdherenceRecord.patient_id == patient_id, AdherenceRecord.date >= start
        )
    ).all()
    notes = db.scalars(
        select(TaskVerification).where(
            TaskVerification.patient_id == patient_id, TaskVerification.date >= start
        )
    ).all()
    by_task: dict[int, dict[date, AdherenceRecord]] = {}
    for r in records:
        by_task.setdefault(r.task_id, {})[r.date] = r
    meta: dict[int, dict[date, TaskVerification]] = {}
    for n in notes:
        meta.setdefault(n.task_id, {})[n.date] = n
    payloads = [task_payload(t, by_task.get(t.id, {}), meta.get(t.id, {}), today) for t in tasks]
    totals = {"verified": 0, "self_attested": 0, "missed": 0}
    for p in payloads:
        for k in totals:
            totals[k] += p[k]
    assigned = sum(totals.values())
    return {
        "tasks": payloads,
        "summary": {
            "active": len(payloads),
            "rate": round((totals["verified"] + 0.5 * totals["self_attested"]) / assigned, 2)
            if assigned else None,
            "task_days": assigned,
            **totals,
        },
    }


# --- lifecycle -------------------------------------------------------------------------


def end_task(db: Session, task_id: int) -> AdherenceTask:
    """Take a task out of the plan.

    Everything the patient could still do with it goes too: an SMS
    conversation half-answered on it would otherwise keep asking questions
    for a task the console has retired, and the app would keep showing it as
    "started by text". The assessment is recomputed because the care metrics
    and the next-step rules score the active plan.
    """
    task = db.get(AdherenceTask, task_id)
    if task is None:
        raise PlanError(f"Unknown task {task_id}")
    task.active = False
    if task.status in ("pending", "sent", None):
        task.status = "skipped"
        task.completed_at = datetime.now()
        task.completed_via = "console"
    payload = dict(task.payload or {})
    payload.pop("sms", None)
    care = care_of(task)
    if care is not None:
        payload["care"] = {**care, "ended_on": date.today().isoformat()}
    task.payload = payload
    db.commit()

    from app.engine.pipeline import run_patient

    run_patient(db, task.patient_id)
    return task


def upsert_record(
    db: Session, task: AdherenceTask, on: date, status: AdherenceStatus | str, *,
    source: str, count: float | None = None, never_downgrade: bool = False,
) -> tuple[AdherenceRecord, bool]:
    """Write or update the (task, day) record and its provenance note.
    Returns the record and whether anything changed."""
    status = str(status)
    record = db.scalar(select(AdherenceRecord).where(
        AdherenceRecord.task_id == task.id, AdherenceRecord.date == on
    ))
    changed = False
    if record is None:
        record = AdherenceRecord(patient_id=task.patient_id, task_id=task.id, date=on,
                                 status=status)
        db.add(record)
        changed = True
    elif str(record.status) != status:
        if never_downgrade and RECORD_RANK.get(status, 0) < RECORD_RANK.get(str(record.status), 0):
            return record, False
        record.status = status
        changed = True
    note = db.scalar(select(TaskVerification).where(
        TaskVerification.task_id == task.id, TaskVerification.date == on
    ))
    if note is None:
        db.add(TaskVerification(patient_id=task.patient_id, task_id=task.id, date=on,
                                source=source, count=count))
    elif changed or note.source != source or note.count != count:
        note.source, note.count, note.updated_at = source, count, datetime.now()
    return record, changed


def record_provider_status(
    db: Session, task_id: int, on: date, status: str, count: float | None = None
) -> AdherenceRecord:
    """A provider-entered status is an explicit clinical entry: it may set
    any status, including over a data-verified one."""
    task = db.get(AdherenceTask, task_id)
    if task is None:
        raise PlanError(f"Unknown task {task_id}")
    try:
        parsed = AdherenceStatus(status)
    except ValueError:
        raise PlanError(f"Unknown status {status!r}")
    record, _ = upsert_record(db, task, on, parsed, source="provider", count=count)
    db.commit()
    from app.engine.pipeline import run_patient

    run_patient(db, task.patient_id)
    return record


__all__ = [
    "PlanItem", "PlanError", "VerifyKind", "assign_plan", "patient_plan", "end_task",
    "record_provider_status", "resolve_item", "plan_text", "task_payload", "active_tasks",
    "active_template_keys", "care_of", "upsert_record",
]
