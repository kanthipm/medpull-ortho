"""The care plan: a task library by use case, the AI task builder, quick
invoke, data verification of assigned tasks, message templates and the
actionable next-step planner. Built on the patient-app session's task and
message models (``app/tasks``, ``app/models/adherence.py``,
``app/models/mobile.py``), which it reads and creates rows through but
never redefines."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_ensured = False


def ensure_ready(db: Session) -> None:
    """Upsert the task and message libraries once per process. Called from
    the plan router's dependency and the worklist (which reads the library
    to name the tasks a next step would assign). Idempotent; a failure is
    logged and retried on the next request rather than failing the read."""
    global _ensured
    if _ensured:
        return
    from app.plan.library import ensure_library
    from app.plan.messages import ensure_message_library

    try:
        ensure_library(db)
        ensure_message_library(db)
    except Exception:  # noqa: BLE001 — a library upsert must never fail a request
        logger.exception("Care-plan library upsert failed")
        db.rollback()
        return
    _ensured = True


def reset_ready() -> None:
    """For tests and storage hydration: force the next request to re-upsert."""
    global _ensured
    _ensured = False
