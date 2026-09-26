"""AI on top of the readouts: the morning brief and the deep dives.

Same shape as the clinic's insight layer (cache → model → validate →
fallback → persist), same provider chain, same ``insights`` table, but a
different reader. The brief is the one paragraph a subscriber reads with
their coffee: everything that matters today in plain words, ending in what
to do. The deep dives are for the person who wants the numbers explained
the way a coach who reads the literature would explain them — ACWR, ln-RMSSD
bands, sleep debt, Banister form — without being told what condition they
might have, because nothing here is medicine.

Every model paragraph is validated: the diagnostic-language ban the clinic
uses, plus a ban on prescribing (dose, medication, "you should see a doctor
for X"), plus a length check. A paragraph that fails is replaced by the
deterministic renderer, which reads the same digest.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.llm.provider import (
    LLMError,
    complete_json,
    model_name,
    note_invalid_output,
    note_valid_output,
    provider_name,
)
from app.models.enums import PERSONAL_GUARDRAIL_SENTENCE, InsightKind
from app.models.insight import Insight
from app.models.patient import Patient
from app.models.personal import GOAL_LABELS

logger = logging.getLogger(__name__)

PERSONAL_PROMPT_VERSION = "3"
KEEP_PER_SERIES = 8
DOMAINS = ("recovery", "training", "sleep", "weekly")

BANNED = re.compile(
    r"\b(detect|diagnos|prescri|dosage|\bmg\b|overtraining syndrome|you have (a|an) )",
    re.IGNORECASE,
)

COACH_STYLE = """How to write:
- You are talking to someone who trains seriously and reads their own numbers. Use the \
real terms (HRV, ln-RMSSD, acute:chronic ratio, sleep debt, form, monotony) and give the \
actual values from the data. Never dumb it down, never pad it.
- Short sentences. One idea per sentence. No bullet lists, no headings, no emoji, no \
exclamation marks.
- Only the numbers in the data. Never invent a value, a date, a workout or a reason.
- Say what the picture means for this person today and what to do about it in training \
or sleep terms. Then stop.
- Hedge once where the data is thin. Never stack hedges.
- Never name a medical condition, never say something was detected or diagnosed, never \
mention medication or doses. If signals look like illness, say "if you feel unwell, ease \
off and see a clinician" and nothing more specific.
- Everyday words between the technical terms. Never: leverage, utilize, robust, holistic, \
optimize, journey, crucial, it's worth noting, overall, ultimately.
- No dashes. Use commas or full stops."""

SYSTEM = f"""You are the coach inside MedPull for a personal subscriber. You read their \
wearable-derived readouts and their own check-in answers and tell them, precisely, where \
they stand and what today should look like.

{COACH_STYLE}

Respond with a single JSON object exactly matching the requested contract."""

BRIEF_CONTRACT = (
    '{"headline": "<at most 9 words: why today is what it is, the one or two signals '
    'that decided it with their values, e.g. \\"Resting HR 5 up, sleep 74% of need.\\" '
    'Never the verdict word or the readiness score: the app shows both beside it.>", '
    '"brief": "<45 to 90 words, one paragraph. The two or three signals that decided today, '
    "with values and the comparison to the person's baseline, then one concrete "
    "instruction for training or sleep. Do not repeat the headline. Address the person as "
    'you. No greeting, no sign-off.">}'
)

DEEP_CONTRACTS = {
    "recovery": (
        '{"title": "<max 6 words>", "body": "<140 to 220 words on recovery state: HRV vs the '
        "baseline band and the balance ratio, resting heart rate delta, the strain tally of "
        "overnight signals, how they fit together, and what it implies for the next two or "
        'three days of training or rehab. Two paragraphs separated by a blank line.">}'
    ),
    "training": (
        '{"title": "<max 6 words>", "body": "<140 to 220 words on training load: acute:chronic '
        "ratio and what range it is in, fitness/fatigue/form in Banister terms, monotony and "
        "strain, weekly minutes against the target if there is one, and a concrete plan for "
        'the coming week. Two paragraphs separated by a blank line.">}'
    ),
    "sleep": (
        '{"title": "<max 6 words>", "body": "<140 to 220 words on sleep: last night against '
        "need, the debt over the week and how it was built, efficiency and stage shares if "
        "present, bedtime regularity, and the one change that would pay off most. Two "
        'paragraphs separated by a blank line.">}'
    ),
    "weekly": (
        '{"title": "<max 6 words>", "body": "<160 to 240 words reviewing the last seven days '
        "across readiness, load, sleep and body signals: what went well, what cost them, "
        "how the numbers moved, and two specific intentions for next week. Two paragraphs "
        'separated by a blank line.">}'
    ),
}


def _key(patient_id: str, kind: InsightKind, domain: str | None, fingerprint: str,
         provider: str, day: date) -> str:
    return hashlib.sha256(
        f"{patient_id}:{kind}:{domain or ''}:{fingerprint}:{day.isoformat()}:"
        f"{PERSONAL_PROMPT_VERSION}:{provider}".encode()
    ).hexdigest()


def _cached(db: Session, patient_id: str, kind: InsightKind, cache_hash: str,
            key_provider: str) -> Insight | None:
    row = db.scalar(
        select(Insight)
        .where(Insight.patient_id == patient_id, Insight.kind == kind,
               Insight.input_hash == cache_hash)
        .order_by(Insight.id.desc())
        .limit(1)
    )
    if row is not None and row.llm_provider == "fallback" and key_provider != "fallback":
        return None
    return row


def _persist(db: Session, patient_id: str, kind: InsightKind, content: dict[str, Any],
             cache_hash: str, provider: str) -> Insight:
    insight = Insight(
        patient_id=patient_id, kind=kind, content=content, input_hash=cache_hash,
        llm_provider=provider, model=model_name() if provider != "fallback" else None,
    )
    db.add(insight)
    db.flush()
    # A copy for the lake (app/personal/archive.py): the words, the provider
    # and the fingerprint of the numbers they were written from.
    patient = db.get(Patient, patient_id)
    if patient is not None:
        from app.personal import archive

        archive.archive_ai(patient, str(kind), content, fingerprint=cache_hash,
                           provider=provider, model=insight.model)
    superseded = db.scalars(
        select(Insight.id)
        .where(Insight.patient_id == patient_id, Insight.kind == kind)
        .order_by(Insight.id.desc())
        .offset(KEEP_PER_SERIES)
    ).all()
    if superseded:
        db.execute(delete(Insight).where(Insight.id.in_(superseded)))
    db.commit()
    return insight


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _validate_brief(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    text = str(content.get("brief", "")).strip()
    headline = " ".join(str(content.get("headline", "")).split())
    words = len(text.split())
    if words < 30 or words > 130:
        return None
    if not headline or len(headline) > 80 or len(headline.split()) > 12:
        return None
    for t in (text, headline):
        if BANNED.search(t):
            return None
    return {"headline": headline, "brief": text}


def _validate_deep(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    title = str(content.get("title", "")).strip()[:60]
    body = str(content.get("body", "")).strip()
    words = len(body.split())
    if not title or words < 80 or words > 320:
        return None
    for text in (title, body):
        if BANNED.search(text):
            return None
    return {"title": title, "body": body}


def _prompt(digest: dict[str, Any], profile: Any, contract: str, notes: list[dict] | None = None,
            domain: str | None = None) -> str:
    payload = {
        "person": {
            "goal": GOAL_LABELS.get(digest.get("goal", ""), digest.get("goal")),
            "sport": getattr(profile, "sport", None),
            "weekly_target_minutes": getattr(profile, "weekly_target_minutes", None),
            "sleep_target_hours": getattr(profile, "sleep_target_hours", None),
            "coming_back_from": getattr(profile, "injury", None),
        },
        "readouts": digest,
        "recent_notes": (notes or [])[-5:],
    }
    focus = f"Focus: {domain}.\n" if domain else ""
    return (f"{focus}Data:\n{json.dumps(payload, default=str)}\n\n"
            f"Produce JSON matching exactly this contract:\n{contract}")


# --- the deterministic renderer ------------------------------------------------------


def _first_sentence(text: str | None) -> str:
    if not text:
        return ""
    return text.split(". ")[0].rstrip(".") + "."


def _first_number(text: Any) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", str(text or ""))
    return float(m.group()) if m else None


def _headline(digest: dict[str, Any]) -> str:
    """Why today is what it is, in one breath. The tile already shows the
    verdict and the score, so the headline names the signals that decided
    them: at most two, strongest first, with their values."""
    v = digest.get("verdict") or {}
    clauses: list[str] = []
    body = digest.get("body") or {}
    if body.get("status") == "flag" and body.get("adverse") is not None:
        clauses.append(f"{body['adverse']} of {body.get('scored', '?')} overnight signals off")
    rhr = digest.get("resting_hr") or {}
    if rhr.get("status") in ("watch", "flag") and rhr.get("baseline_mean") is not None:
        # Last night's value when it is the story, else the seven-day figure.
        value = rhr.get("latest") if rhr.get("latest_is_last_night") and rhr.get("latest") is not None \
            else _first_number(rhr.get("headline"))
        if value is not None:
            clauses.append(f"resting HR {value:.0f} vs {rhr['baseline_mean']:.0f} usual")
    hrv = digest.get("hrv") or {}
    if hrv.get("status") in ("watch", "flag") and hrv.get("baseline_mean") is not None:
        value = hrv.get("latest") if hrv.get("latest") is not None else _first_number(hrv.get("headline"))
        if value is not None:
            clauses.append(f"HRV {value:.0f} vs {hrv['baseline_mean']:.0f} usual")
    sleep = digest.get("sleep") or {}
    if sleep.get("status") in ("watch", "flag") and sleep.get("performance") is not None:
        clauses.append(f"sleep {sleep['performance']:.0f}% of need")
    load = digest.get("load") or {}
    if load.get("status") in ("watch", "flag") and load.get("acwr") is not None:
        clauses.append(f"load {load['acwr']:.2f}× chronic")
    if clauses:
        text = ", ".join(clauses[:2])
        return (text[0].upper() + text[1:] + ".")[:80]
    reason = str(v.get("reason") or "").strip()
    # "Readiness 71: recovery signals are above your normal." -> the clause.
    reason = re.sub(r"^Readiness \d+[:,]\s*(but\s+)?", "", reason)
    if not reason:
        reason = "close to your normal."
    return (reason[0].upper() + reason[1:])[:80]


def fallback_brief(digest: dict[str, Any]) -> dict[str, str]:
    v = digest.get("verdict") or {}
    headline = _headline(digest)
    parts = []
    if v.get("reason"):
        parts.append(str(v["reason"]))
    for key in ("hrv", "resting_hr", "sleep", "load", "body"):
        p = digest.get(key) or {}
        if p.get("status") in ("watch", "flag"):
            parts.append(_first_sentence(p.get("finding")))
    if v.get("detail"):
        parts.append(str(v["detail"]))
    # The verdict's reason is often a panel's first sentence too; say it once.
    seen: set[str] = set()
    unique = []
    for part in parts:
        key = part.strip().lower()
        if part and key not in seen:
            seen.add(key)
            unique.append(part)
    return {"headline": headline, "brief": " ".join(unique)}


def fallback_deep(digest: dict[str, Any], domain: str) -> dict[str, str]:
    if domain == "training":
        p = digest.get("load") or {}
        title = p.get("status_text") or "Training load"
        body = " ".join(x for x in (p.get("finding"),
                                   f"Fitness {p.get('fitness', '—')}, fatigue {p.get('fatigue', '—')}, form {p.get('form', '—')}."
                                   if p.get("fitness") is not None else None) if x)
    elif domain == "sleep":
        p = digest.get("sleep") or {}
        rh = digest.get("rhythm") or {}
        title = p.get("status_text") or "Sleep"
        body = " ".join(x for x in (p.get("finding"), rh.get("finding")) if x)
    elif domain == "weekly":
        title = "Your week"
        body = " ".join(_first_sentence((digest.get(k) or {}).get("finding"))
                        for k in ("readiness", "load", "sleep", "hrv", "resting_hr", "body"))
    else:
        title = (digest.get("readiness") or {}).get("status_text") or "Recovery"
        body = " ".join(x for x in ((digest.get("readiness") or {}).get("finding"),
                                   (digest.get("hrv") or {}).get("finding"),
                                   (digest.get("resting_hr") or {}).get("finding"),
                                   (digest.get("body") or {}).get("finding")) if x)
    return {"title": title[:60], "body": body or "Not enough data yet for this one."}


# --- the two entry points -------------------------------------------------------------


def get_brief(db: Session, patient, profile, dashboard: dict[str, Any], *,
              allow_llm: bool = True) -> dict[str, Any]:
    """Today's brief for this person, cached under the dashboard's fingerprint."""
    digest = dashboard["digest"]
    today = date.fromisoformat(dashboard["as_of"])
    # Nothing to score yet means nothing for a model to say: the first days
    # get the deterministic "learning you" brief and cost no model call.
    learning = (digest.get("verdict") or {}).get("kind") == "unknown"
    provider = provider_name() if allow_llm and not learning else "fallback"
    cache_hash = _key(patient.id, InsightKind.PERSONAL_BRIEF, None, dashboard["fingerprint"],
                      provider, today)
    cached = _cached(db, patient.id, InsightKind.PERSONAL_BRIEF, cache_hash, provider)
    if cached is not None:
        return _view(cached)
    content: dict[str, Any] | None = None
    if provider != "fallback":
        try:
            raw = complete_json(SYSTEM, _prompt(digest, profile, BRIEF_CONTRACT,
                                                dashboard.get("notes")), temperature=0.5)
            content = _validate_brief(raw)
            if content is None:
                note_invalid_output(provider)
            else:
                note_valid_output(provider)
        except LLMError as e:
            logger.warning("Personal brief failed for %s: %s", patient.id, e)
    if content is None:
        provider = "fallback"
        cache_hash = _key(patient.id, InsightKind.PERSONAL_BRIEF, None,
                          dashboard["fingerprint"], provider, today)
        cached = _cached(db, patient.id, InsightKind.PERSONAL_BRIEF, cache_hash, provider)
        if cached is not None:
            return _view(cached)
        content = fallback_brief(digest)
    content = {**content, "guardrail": PERSONAL_GUARDRAIL_SENTENCE}
    return _view(_persist(db, patient.id, InsightKind.PERSONAL_BRIEF, content, cache_hash,
                          provider))


def get_deep_dive(db: Session, patient, profile, dashboard: dict[str, Any], domain: str, *,
                  allow_llm: bool = True) -> dict[str, Any]:
    if domain not in DOMAINS:
        raise ValueError(f"Unknown domain {domain!r}")
    digest = dashboard["digest"]
    today = date.fromisoformat(dashboard["as_of"])
    learning = (dashboard["digest"].get("verdict") or {}).get("kind") == "unknown"
    provider = provider_name() if allow_llm and not learning else "fallback"
    cache_hash = _key(patient.id, InsightKind.PERSONAL_DEEP, domain, dashboard["fingerprint"],
                      provider, today)
    cached = _cached(db, patient.id, InsightKind.PERSONAL_DEEP, cache_hash, provider)
    if cached is not None and cached.content.get("domain") == domain:
        return _view(cached)
    content: dict[str, Any] | None = None
    if provider != "fallback":
        try:
            raw = complete_json(SYSTEM, _prompt(digest, profile, DEEP_CONTRACTS[domain],
                                                dashboard.get("notes"), domain),
                                temperature=0.5)
            content = _validate_deep(raw)
            if content is None:
                note_invalid_output(provider)
            else:
                note_valid_output(provider)
        except LLMError as e:
            logger.warning("Personal deep dive %s failed for %s: %s", domain, patient.id, e)
    if content is None:
        provider = "fallback"
        cache_hash = _key(patient.id, InsightKind.PERSONAL_DEEP, domain,
                          dashboard["fingerprint"], provider, today)
        cached = _cached(db, patient.id, InsightKind.PERSONAL_DEEP, cache_hash, provider)
        if cached is not None and cached.content.get("domain") == domain:
            return _view(cached)
        content = fallback_deep(digest, domain)
    content = {**content, "domain": domain, "guardrail": PERSONAL_GUARDRAIL_SENTENCE}
    return _view(_persist(db, patient.id, InsightKind.PERSONAL_DEEP, content, cache_hash,
                          provider))


def _view(row: Insight) -> dict[str, Any]:
    return {
        **row.content,
        "provider": row.llm_provider,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
    }
