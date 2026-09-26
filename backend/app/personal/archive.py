"""The lake: a copy of what matters, one JSON object at a time, in the
personal bucket, for later.

The database is the live truth and it is already durable in S3, but it is
one SQLite file that a future analysis would have to reopen whole. This is
the other shape: per account, per day, a small document with the readouts,
the verdict, the brief, the plan and the day's log; per consent, the full
text and what was agreed; per AI result, the prompt's digest and the words.
Nothing here is read by the app. Everything here is under
``personal/<account>/lake/`` in the personal bucket (a sibling directory on
a laptop), so an account deletion sweeps it with the rest.

Writes never raise into a request: a failed archive is logged and the row
in the database stands.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

from app.models.patient import Patient
from app.models.personal import Consent
from app.storage import blobs

logger = logging.getLogger(__name__)

LAKE = "lake"


def _key(patient_id: str, *parts: str) -> str:
    return "/".join([blobs.PERSONAL_PREFIX, patient_id, LAKE, *parts])


def _write(key: str, document: dict[str, Any]) -> str | None:
    try:
        payload = json.dumps(document, default=str, sort_keys=True).encode()
        blobs.put_json(key, payload)
        return key
    except Exception:  # noqa: BLE001 — see the module docstring
        logger.exception("archive write failed for %s", key)
        return None


def archive_consent(patient: Patient, consent: Consent) -> str | None:
    from app.personal.auth import CONSENT_SCOPES, CONSENT_TEXT

    key = _key(patient.id, "consent", f"{consent.version}.json")
    return _write(key, {
        "kind": "consent",
        "account": patient.id,
        "name": patient.name,
        "version": consent.version,
        "text_sha256": consent.text_sha256,
        "text": CONSENT_TEXT,
        "scopes": consent.scopes,
        "scope_definitions": CONSENT_SCOPES,
        "signature": consent.signature,
        "accepted_at": consent.accepted_at,
        "withdrawn_at": consent.withdrawn_at,
        "device_name": consent.device_name,
        "app_version": consent.app_version,
        "archived_at": datetime.now(),
    })


def _compact_panels(dashboard: dict[str, Any]) -> dict[str, Any]:
    """Panels without their chart series: the numbers and the words."""
    out: dict[str, Any] = {}
    for key, panel in (dashboard.get("panels") or {}).items():
        out[key] = {k: v for k, v in panel.items() if k not in ("series",)}
        extra = dict(panel.get("extra") or {})
        for heavy in ("form_series", "components", "signals"):
            extra.pop(heavy, None)
        out[key]["extra"] = extra
    return out


def archive_day(patient: Patient, day: date, *, dashboard: dict[str, Any],
                brief: dict[str, Any] | None, plan: dict[str, Any] | None,
                logs: dict[str, Any] | None = None, care: dict[str, Any] | None = None) -> str | None:
    key = _key(patient.id, "days", f"{day.isoformat()}.json")
    return _write(key, {
        "kind": "day",
        "account": patient.id,
        "date": day.isoformat(),
        "goal": dashboard.get("goal"),
        "days_with_data": dashboard.get("days_with_data"),
        "verdict": dashboard.get("verdict"),
        "digest": dashboard.get("digest"),
        "panels": _compact_panels(dashboard),
        "care": {k: v for k, v in (care or {}).items() if k != "metrics"} if care else None,
        "care_metrics": [
            {k: m.get(k) for k in ("id", "key", "status", "status_text", "value", "unit", "finding")}
            for m in (care or {}).get("metrics", [])
        ] if care else None,
        "brief": brief,
        "plan": plan,
        "logs": logs,
        "archived_at": datetime.now(),
    })


def archive_ai(patient: Patient, kind: str, content: dict[str, Any], *,
               fingerprint: str, provider: str | None, model: str | None = None) -> str | None:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    key = _key(patient.id, "ai", kind, f"{stamp}.json")
    return _write(key, {
        "kind": f"ai:{kind}",
        "account": patient.id,
        "fingerprint": fingerprint,
        "provider": provider,
        "model": model,
        "content": content,
        "archived_at": datetime.now(),
    })


def archive_coach_turn(patient: Patient, text: str, result: dict[str, Any], channel: str) -> str | None:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    key = _key(patient.id, "coach", f"{stamp}.json")
    return _write(key, {
        "kind": "coach_turn",
        "account": patient.id,
        "channel": channel,
        "said": text[:2000],
        "reply": result.get("reply"),
        "actions": result.get("actions"),
        "flagged": result.get("flagged"),
        "provider": result.get("provider"),
        "archived_at": datetime.now(),
    })


def archive_event(patient: Patient, name: str, detail: dict[str, Any] | None = None) -> str | None:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    key = _key(patient.id, "events", f"{stamp}-{name}.json")
    return _write(key, {"kind": "event", "account": patient.id, "name": name,
                        "detail": detail or {}, "archived_at": datetime.now()})
