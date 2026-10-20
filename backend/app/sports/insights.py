"""The athlete's brief: one paragraph each morning, and the staff's team
briefing. Same shape as the personal tier's insight layer (cache → model →
validate → fallback → persist), with a prompt that speaks to an athlete
in a program and a deterministic renderer that reads the recovery board.
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

from app.llm.provider import LLMError, complete_json, model_name, note_invalid_output, note_valid_output, provider_name
from app.models.enums import SPORTS_GUARDRAIL_SENTENCE, InsightKind
from app.models.insight import Insight
from app.models.patient import Patient
from app.models.sports import SPORT_LABELS
from app.sports.recovery import first_sentence

logger = logging.getLogger(__name__)

PROMPT_VERSION = "1"
KEEP_PER_SERIES = 8

BANNED = re.compile(r"\b(detect|diagnos|prescri|dosage|\bmg\b|you have (a|an) |cleared to play|medically cleared)", re.IGNORECASE)

STYLE = """How to write:
- You are the performance coach inside an athlete's app. They play on a team or train on their own; \
there may be an athletic trainer and a strength coach behind them. Use the real terms (HRV, RSI-modified, \
session load, acute load, sleep debt, limb symmetry) and the actual values from the data.
- Short sentences. One idea per sentence. No bullet lists, no headings, no emoji, no exclamation marks.
- Only the numbers in the data. Never invent a value, a date, a session or a reason.
- Say what today should look like in practice, recovery and sleep terms, then stop.
- Never name a medical condition, never say something was detected or diagnosed, never mention medication, \
and never say the athlete is cleared or not cleared: their medical staff decide that.
- No dashes. Use commas or full stops."""

SYSTEM = f"""You are the coach inside MedPull Sports for an athlete. You read their overnight wearable readouts, \
their morning wellness answers, their training load, their performance tests and their injury plan when there \
is one, and tell them precisely where they stand and what today should look like.

{STYLE}

Respond with a single JSON object exactly matching the requested contract."""

BRIEF_CONTRACT = (
    '{"headline": "<at most 9 words: the one or two signals that decided today, with values. Never the '
    'verdict word or the readiness score, the tile shows both.>", '
    '"brief": "<45 to 90 words, one paragraph. The two or three signals that decided today with values against '
    "the athlete's baseline, the schedule context (game today, game tomorrow, day after a game) when it matters, "
    'then one concrete instruction for practice, recovery or sleep. Address the athlete as you. No greeting.">}'
)


def _key(patient_id: str, kind: InsightKind, fingerprint: str, provider: str, day: date) -> str:
    return hashlib.sha256(f"{patient_id}:{kind}:{fingerprint}:{day.isoformat()}:{provider}:v{PROMPT_VERSION}".encode()).hexdigest()


def _cached(db: Session, patient_id: str, kind: InsightKind, cache_hash: str, provider: str) -> Insight | None:
    row = db.scalar(select(Insight).where(Insight.patient_id == patient_id, Insight.kind == kind,
                                          Insight.input_hash == cache_hash).order_by(Insight.generated_at.desc()).limit(1))
    if row is None:
        return None
    if provider != "fallback" and row.llm_provider == "fallback":
        return None
    return row


def _persist(db: Session, patient_id: str, kind: InsightKind, content: dict[str, Any], cache_hash: str, provider: str) -> Insight:
    row = Insight(patient_id=patient_id, kind=kind, content=content, input_hash=cache_hash,
                  llm_provider=provider, model=model_name() if provider != "fallback" else None)
    db.add(row)
    db.flush()
    ids = list(db.scalars(select(Insight.id).where(Insight.patient_id == patient_id, Insight.kind == kind)
                          .order_by(Insight.generated_at.desc(), Insight.id.desc())).all())
    if len(ids) > KEEP_PER_SERIES:
        db.execute(delete(Insight).where(Insight.id.in_(ids[KEEP_PER_SERIES:])))
    db.commit()
    return row


def _validate_brief(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    headline = str(content.get("headline") or "").strip()
    brief = str(content.get("brief") or "").strip()
    if not brief or BANNED.search(brief) or BANNED.search(headline):
        return None
    words = len(brief.split())
    if words < 30 or words > 120 or len(headline.split()) > 12:
        return None
    return {"headline": headline, "brief": brief}


def _digest_lines(recovery: dict[str, Any], performance: dict[str, Any], rehab: dict[str, Any], profile: Any) -> str:
    d = recovery.get("digest") or {}
    v = recovery.get("verdict") or {}
    lines = [f"Sport: {SPORT_LABELS.get(profile.sport, profile.sport)}; position {profile.position or 'n/a'}; "
             f"availability {profile.status}."]
    lines.append(f"Today's verdict: {v.get('title')} ({v.get('kind')}). Reasons: {' '.join(v.get('reasons') or [])}")
    for key in ("readiness", "hrv", "resting_hr", "sleep", "load", "body"):
        p = d.get(key) or {}
        if p and p.get("status") != "nodata":
            numbers = {k: val for k, val in p.items() if k not in ("status", "status_text", "headline", "finding") and val is not None}
            lines.append(f"{key}: {p.get('headline')} ({p.get('status_text')}). {p.get('finding')} {json.dumps(numbers, default=str)}")
    w = recovery.get("wellness") or {}
    if w.get("items"):
        lines.append("Wellness: " + "; ".join(f"{i['label']} {i['value']:.0f}/10 (z {i['z']})" for i in w["items"]) +
                     f". Hooper {w.get('hooper')}. {w.get('finding')}")
    load = recovery.get("load") or {}
    lines.append(f"Load: week {load.get('week_load')} AU, change {load.get('change_pct')}%, monotony {load.get('monotony')}, "
                 f"{load.get('sessions_week')} sessions, {load.get('games_week')} games. {load.get('finding')}")
    s = recovery.get("schedule") or {}
    lines.append(f"Schedule: {s.get('finding')} density {s.get('density')}.")
    n = recovery.get("neuromuscular") or {}
    if n.get("status") not in (None, "nodata"):
        lines.append(f"Neuromuscular: {n.get('status_text')}. {n.get('finding')}")
    j = recovery.get("jumps")
    if j:
        lines.append(f"Jumps: {j.get('week')} this week vs {j.get('prior_week')} last; {j.get('text')}")
    for b in (rehab.get("active") or [])[:1]:
        ph = b.get("phase") or {}
        rts = b.get("rts") or {}
        lines.append(f"Injury: {b.get('label')} ({b.get('side')}), {b.get('weeks')} weeks since {b.get('anchor')}, phase "
                     f"{ph.get('number')} of {ph.get('of')} ({ph.get('name')}), {ph.get('met')}/{ph.get('total')} phase criteria met, "
                     f"{rts.get('met')}/{rts.get('total')} return-to-sport criteria met.")
    tips = recovery.get("suggestions") or []
    if tips:
        lines.append("Suggestions: " + " | ".join(f"{t['title']}: {t['why']}" for t in tips[:3]))
    return "\n".join(lines)


def fallback_brief(recovery: dict[str, Any], rehab: dict[str, Any]) -> dict[str, str]:
    v = recovery.get("verdict") or {}
    d = recovery.get("digest") or {}
    clauses = []
    rhr = d.get("resting_hr") or {}
    if rhr.get("status") in ("watch", "flag") and rhr.get("baseline_mean") is not None and rhr.get("latest") is not None:
        clauses.append(f"resting HR {rhr['latest']:.0f} vs {rhr['baseline_mean']:.0f} usual")
    hrv = d.get("hrv") or {}
    if hrv.get("status") in ("watch", "flag") and hrv.get("baseline_mean") is not None and hrv.get("latest") is not None:
        clauses.append(f"HRV {hrv['latest']:.0f} vs {hrv['baseline_mean']:.0f} usual")
    sleep = d.get("sleep") or {}
    if sleep.get("status") in ("watch", "flag") and sleep.get("performance") is not None:
        clauses.append(f"sleep {sleep['performance']:.0f}% of need")
    load = recovery.get("load") or {}
    if load.get("status") in ("watch", "flag") and load.get("change_pct") is not None:
        clauses.append(f"load {load['change_pct']:+.0f}% on last week")
    w = recovery.get("wellness") or {}
    worst = sorted([i for i in w.get("items", []) if i.get("z") is not None and i["z"] <= -1], key=lambda i: i["z"])
    if worst:
        clauses.append(f"{worst[0]['label'].lower()} {abs(worst[0]['z']):.1f} SD off")
    headline = (", ".join(clauses[:2]) or (v.get("reason") or "close to your usual"))
    headline = (headline[0].upper() + headline[1:]).rstrip(".") + "."
    parts = [v.get("reason") or ""]
    for key in ("hrv", "resting_hr", "sleep"):
        p = d.get(key) or {}
        if p.get("status") in ("watch", "flag") and p.get("finding"):
            parts.append(first_sentence(str(p["finding"])))
    sched = recovery.get("schedule") or {}
    if sched.get("finding") and sched["finding"] != "No team calendar connected.":
        parts.append(first_sentence(sched["finding"]))
    for b in (rehab.get("active") or [])[:1]:
        ph = b.get("phase") or {}
        parts.append(f"On the {b.get('label', 'injury').lower()}, you are in phase {ph.get('number')} of {ph.get('of')}, "
                     f"{ph.get('name', '').lower()}, with {ph.get('met')} of {ph.get('total')} gates met.")
    if v.get("detail"):
        parts.append(v["detail"])
    seen: set[str] = set()
    unique = []
    for p in parts:
        k = p.strip().lower()
        if p and k not in seen:
            seen.add(k)
            unique.append(p.strip())
    return {"headline": headline[:80], "brief": " ".join(unique)}


def get_brief(db: Session, patient: Patient, profile: Any, recovery: dict[str, Any], performance: dict[str, Any],
              rehab: dict[str, Any], *, allow_llm: bool = True) -> dict[str, Any]:
    today = date.fromisoformat(recovery["as_of"])
    learning = (recovery.get("verdict") or {}).get("kind") == "learning"
    provider = provider_name() if allow_llm and not learning else "fallback"
    fingerprint = recovery.get("fingerprint") or hashlib.sha256(json.dumps(recovery.get("verdict"), sort_keys=True).encode()).hexdigest()[:16]
    rehab_fp = hashlib.sha256(json.dumps([(b.get("id"), (b.get("phase") or {}).get("number"), (b.get("rts") or {}).get("met"))
                                          for b in rehab.get("active") or []]).encode()).hexdigest()[:8]
    fingerprint = f"{fingerprint}:{rehab_fp}"
    cache_hash = _key(patient.id, InsightKind.SPORTS_BRIEF, fingerprint, provider, today)
    cached = _cached(db, patient.id, InsightKind.SPORTS_BRIEF, cache_hash, provider)
    if cached is not None:
        return _view(cached)
    content: dict[str, Any] | None = None
    if provider != "fallback":
        try:
            prompt = ("Today's data for this athlete:\n" + _digest_lines(recovery, performance, rehab, profile) +
                      f"\n\nWrite the brief. Contract: {BRIEF_CONTRACT}")
            raw = complete_json(SYSTEM, prompt, temperature=0.5)
            content = _validate_brief(raw)
            if content is None:
                note_invalid_output(provider)
            else:
                note_valid_output(provider)
        except LLMError as e:
            logger.warning("Sports brief failed for %s: %s", patient.id, e)
    if content is None:
        provider = "fallback"
        cache_hash = _key(patient.id, InsightKind.SPORTS_BRIEF, fingerprint, provider, today)
        cached = _cached(db, patient.id, InsightKind.SPORTS_BRIEF, cache_hash, provider)
        if cached is not None:
            return _view(cached)
        content = fallback_brief(recovery, rehab)
    content = {**content, "guardrail": SPORTS_GUARDRAIL_SENTENCE}
    return _view(_persist(db, patient.id, InsightKind.SPORTS_BRIEF, content, cache_hash, provider))


def _view(row: Insight) -> dict[str, Any]:
    return {**row.content, "provider": row.llm_provider,
            "generated_at": row.generated_at.isoformat() if row.generated_at else None}
