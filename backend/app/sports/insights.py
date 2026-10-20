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


# --- the Stats tab's read of the battery -----------------------------------------------------------

PERFORMANCE_CONTRACT = (
    '{"headline": "<at most 9 words: the clearest strength and the clearest gap, with a number>", '
    '"strengths": ["<two or three items, each under 14 words: a test, its value and where it sits for the level>"], '
    '"improve": ["<two or three items, each under 18 words: the test or symmetry to build, its value, and one concrete '
    'block of work>"], '
    '"brief": "<45 to 85 words, one paragraph: what the battery says about this athlete as a player, which quality to '
    'build this month and how, and how the weekly jump reads. Address the athlete as you. No greeting.">}'
)

INJURY_CONTRACT = (
    '{"headline": "<at most 9 words: where the plan stands and the gate that matters>", '
    '"read": "<45 to 85 words, one paragraph: the phase and what it is for, which gates are met and which is not with '
    'the latest values, the one block of work for this week, and that the staff make the return call. Address the '
    'athlete as you. No greeting.">}'
)


def _clean_lines(raw: Any, limit_words: int, keep: int) -> list[str] | None:
    if not isinstance(raw, list):
        return None
    out = []
    for item in raw:
        text = str(item).strip().rstrip(".")
        if not text or BANNED.search(text) or len(text.split()) > limit_words:
            continue
        out.append(text)
    return out[:keep] or None


def _validate_performance(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    headline = str(content.get("headline") or "").strip().rstrip(".")
    brief = str(content.get("brief") or "").strip()
    strengths = _clean_lines(content.get("strengths"), 20, 3)
    improve = _clean_lines(content.get("improve"), 24, 3)
    if not brief or not headline or strengths is None or improve is None:
        return None
    if BANNED.search(brief) or BANNED.search(headline) or len(headline.split()) > 12:
        return None
    if not 25 <= len(brief.split()) <= 130:
        return None
    return {"headline": headline, "brief": brief, "strengths": strengths, "improve": improve}


def _validate_injury(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    headline = str(content.get("headline") or "").strip().rstrip(".")
    read = str(content.get("read") or "").strip()
    if not read or not headline or BANNED.search(read) or BANNED.search(headline):
        return None
    if len(headline.split()) > 12 or not 25 <= len(read.split()) <= 130:
        return None
    return {"headline": headline, "read": read}


def _performance_digest(performance: dict[str, Any], profile: Any, sex: str | None) -> str:
    lines = [f"Sport: {SPORT_LABELS.get(profile.sport, profile.sport)}; position {profile.position or 'n/a'}; "
             f"level {performance.get('level')}; benchmarks for {('women' if sex == 'F' else 'men')}; "
             f"{performance.get('logged')} of {performance.get('available')} tests logged; overall core-battery percentile "
             f"{performance.get('overall_percentile')}."]
    for cat in performance.get("categories") or []:
        if not cat.get("cards"):
            continue
        best, weak = cat.get("best") or {}, cat.get("weakest") or {}
        lines.append(f"{cat['label']}: percentile {cat.get('percentile')} ({cat.get('word')}), trend {cat.get('trend_pct')}%, "
                     f"{cat.get('logged_count')} tests; best {best.get('label')} {best.get('latest_text')} {best.get('unit')} "
                     f"(p{best.get('percentile')}); weakest {weak.get('label')} {weak.get('latest_text')} {weak.get('unit')} "
                     f"(p{weak.get('percentile')}).")
    for h in performance.get("headline") or []:
        if h.get("logged"):
            band = h.get("band") or {}
            tr = h.get("trend") or {}
            lines.append(f"Core {h['label']}: {h.get('latest_text')} {h.get('unit')}, p{band.get('percentile')} {band.get('word')}, "
                         f"trend {tr.get('pct')}% ({'better' if tr.get('better') else 'worse' if tr.get('better') is False else 'flat'}).")
        else:
            lines.append(f"Core {h['label']}: not logged.")
    for a in performance.get("asymmetries") or []:
        asym = a.get("asymmetry") or {}
        lines.append(f"Asymmetry {a['label']}: {asym.get('pct')}% apart, {asym.get('weaker')} weaker, LSI {asym.get('lsi')}%, {a.get('status')}.")
    n = performance.get("neuromuscular") or {}
    if n.get("status") not in (None, "nodata"):
        lines.append(f"Weekly jump: {n.get('status_text')}. {n.get('finding')} " +
                     "; ".join(f"{sg['label']} {sg['value']} ({sg['pct']:+.0f}% vs {sg['baseline']})" for sg in n.get("signals") or []))
    for b in performance.get("recent_bests") or []:
        lines.append(f"Recent best: {b['label']} {b['latest_text']} {b['unit']} on {b.get('date')}.")
    return "\n".join(lines)


def fallback_performance_brief(performance: dict[str, Any]) -> dict[str, Any]:
    strengths = performance.get("strengths") or []
    gaps = performance.get("gaps") or []
    n = performance.get("neuromuscular") or {}
    overall = performance.get("overall_percentile")

    def line(x: dict[str, Any]) -> str:
        value = f"{x.get('latest_text')} {x.get('unit')}".strip()
        where = f", {x['word'].lower()} for the level (p{x['percentile']})" if x.get("percentile") is not None else ""
        note = f", {x['note']}" if x.get("note") else ""
        return f"{x['label']} {value}{where}{note}"

    s_lines = [line(x) for x in strengths] or ["Log the core battery and your strengths show here"]
    i_lines = [line(x) for x in gaps] or ["Nothing sits under the level yet; keep the weekly jump going"]
    if n.get("status") in ("watch", "flag"):
        i_lines.insert(0, f"Weekly jump reads {n.get('status_text', '').lower()}: {first_sentence(n.get('finding', ''))}".rstrip("."))
    top = strengths[0]["label"] if strengths else "The battery"
    low = gaps[0]["label"] if gaps else None
    headline = (f"{top} leads; {low} is the gap" if low else f"{top} leads the battery")
    if overall is not None:
        headline = f"P{overall} overall: {headline}"
    parts = []
    if overall is not None:
        parts.append(f"Your logged core tests sit at the {overall}th percentile for the level.")
    if strengths:
        parts.append("Strongest: " + ", ".join(x["label"] for x in strengths[:3]) + ".")
    if gaps:
        parts.append("The quality to build this month is " + gaps[0]["label"] +
                     (f" ({gaps[0]['note']})" if gaps[0].get("note") else "") + ": two focused blocks a week, retest in four.")
    if n.get("status") not in (None, "nodata"):
        parts.append(f"The weekly jump reads {n.get('status_text', '').lower()}.")
    return {"headline": headline[:90], "brief": " ".join(parts) or "Log a few tests and the read sits here.",
            "strengths": s_lines[:3], "improve": i_lines[:3]}


def get_performance_brief(db: Session, patient: Patient, profile: Any, performance: dict[str, Any], sex: str | None = None,
                          *, allow_llm: bool = True) -> dict[str, Any]:
    today = date.fromisoformat(performance["as_of"])
    thin = (performance.get("logged") or 0) < 3
    provider = provider_name() if allow_llm and not thin else "fallback"
    fp_src = json.dumps({"logged": performance.get("logged"), "overall": performance.get("overall_percentile"),
                         "cats": [(c["key"], c.get("percentile"), c.get("logged_count")) for c in performance.get("categories") or []],
                         "latest": [(h["key"], h.get("latest_text"), h.get("days_ago")) for h in performance.get("headline") or []],
                         "asym": [a["key"] for a in performance.get("asymmetries") or []],
                         "neuro": (performance.get("neuromuscular") or {}).get("status")}, sort_keys=True, default=str)
    fingerprint = hashlib.sha256(fp_src.encode()).hexdigest()[:16]
    kind = InsightKind.SPORTS_PERFORMANCE_BRIEF
    cache_hash = _key(patient.id, kind, fingerprint, provider, today)
    cached = _cached(db, patient.id, kind, cache_hash, provider)
    if cached is not None:
        return _view(cached)
    content: dict[str, Any] | None = None
    if provider != "fallback":
        try:
            prompt = ("This athlete's performance battery:\n" + _performance_digest(performance, profile, sex) +
                      f"\n\nWrite the read of the battery. Contract: {PERFORMANCE_CONTRACT}")
            raw = complete_json(SYSTEM, prompt, temperature=0.5)
            content = _validate_performance(raw)
            if content is None:
                note_invalid_output(provider)
            else:
                note_valid_output(provider)
        except LLMError as e:
            logger.warning("Sports performance brief failed for %s: %s", patient.id, e)
    if content is None:
        provider = "fallback"
        cache_hash = _key(patient.id, kind, fingerprint, provider, today)
        cached = _cached(db, patient.id, kind, cache_hash, provider)
        if cached is not None:
            return _view(cached)
        content = fallback_performance_brief(performance)
    content = {**content, "guardrail": SPORTS_GUARDRAIL_SENTENCE}
    return _view(_persist(db, patient.id, kind, content, cache_hash, provider))


# --- the injury plan's read ------------------------------------------------------------------------


def _injury_digest(board: dict[str, Any], profile: Any) -> str:
    ph = board.get("phase") or {}
    rts = board.get("rts") or {}
    lines = [f"Sport: {SPORT_LABELS.get(profile.sport, profile.sport)}; position {profile.position or 'n/a'}.",
             f"Injury: {board.get('label')} ({board.get('side') or 'not sided'}), {board.get('grade') or ''} {board.get('graft') or ''}, "
             f"{board.get('days')} days ({board.get('weeks')} weeks) since {board.get('anchor')}. {board.get('summary') or ''}",
             f"Phase {ph.get('number')} of {ph.get('of')}: {ph.get('name')} ({ph.get('window')}). Goals: {'; '.join(ph.get('goals') or [])}. "
             f"Hold off on: {', '.join(ph.get('avoid') or []) or 'nothing listed'}."]
    for c in ph.get("criteria") or []:
        state = "met" if c.get("met") is True else "not met" if c.get("met") is False else "not measured"
        lines.append(f"Phase gate {c['label']}: {state}, latest {c.get('value_text')} on {c.get('date')}.")
    lines.append(f"Return-to-sport criteria: {rts.get('met')} of {rts.get('total')} met ({rts.get('known')} measured); "
                 f"projected {rts.get('projected')}; typical window {rts.get('typical_weeks')} weeks.")
    for c in rts.get("criteria") or []:
        state = "met" if c.get("met") is True else "not met" if c.get("met") is False else "not measured"
        lines.append(f"RTS gate {c['label']}: {state}, latest {c.get('value_text')}.")
    for f in (board.get("focus") or [])[:3]:
        lines.append(f"Focus: {f.get('title')}: {f.get('why')} Work: {'; '.join(f.get('actions') or [])}")
    for m in board.get("measures") or []:
        if m.get("logged"):
            lines.append(f"Measure {m['label']}: {m.get('latest')} {m.get('unit')} on {m.get('latest_date')}"
                         + (f", other side {m.get('uninvolved_latest')}, LSI {m.get('lsi')}%" if m.get("lsi") is not None else "") + ".")
    if board.get("pain"):
        lines.append(f"Pain {board['pain'].get('value')}/10 on {board['pain'].get('date')}.")
    if board.get("note"):
        lines.append(f"Staff note: {board['note']}")
    return "\n".join(lines)


def fallback_injury_read(board: dict[str, Any]) -> dict[str, Any]:
    ph = board.get("phase") or {}
    rts = board.get("rts") or {}
    unmet = [c for c in ph.get("criteria") or [] if c.get("met") is not True]
    parts = [f"{board.get('label')}, {board.get('weeks')} weeks since {board.get('anchor')}: phase {ph.get('number')} of {ph.get('of')}, "
             f"{str(ph.get('name', '')).lower()}."]
    if ph.get("total"):
        parts.append(f"{ph.get('met')} of {ph.get('total')} gates for this phase are met.")
        if unmet:
            u = unmet[0]
            parts.append(f"The one that matters is {u['label']}" +
                         (f", now {u['value_text']}" if u.get("value_text") else ", not measured yet") + ".")
    else:
        parts.append("No gates are left in this phase; the work is prevention.")
    if rts.get("total"):
        parts.append(f"{rts.get('met')} of {rts.get('total')} return-to-sport criteria are met.")
    focus = (board.get("focus") or [{}])[0]
    if focus.get("actions"):
        parts.append(f"This week: {focus['actions'][0].lower()}.")
    parts.append("Return-to-play is your medical staff's call.")
    if unmet:
        headline = f"Phase {ph.get('number')} of {ph.get('of')}: {unmet[0]['label']} is the gate"
    elif ph.get("total"):
        headline = f"Phase {ph.get('number')} of {ph.get('of')} gates all met"
    else:
        headline = f"Final phase: {rts.get('met')} of {rts.get('total')} return criteria met"
    return {"headline": headline[:90], "read": " ".join(parts)}


def get_injury_read(db: Session, patient: Patient, profile: Any, board: dict[str, Any], *, allow_llm: bool = True) -> dict[str, Any]:
    today = date.today()
    provider = provider_name() if allow_llm and board.get("phase") else "fallback"
    ph = board.get("phase") or {}
    rts = board.get("rts") or {}
    fp_src = json.dumps([board.get("id"), ph.get("number"), ph.get("met"), ph.get("total"), rts.get("met"), rts.get("total"),
                         board.get("last_measure"), board.get("status")], default=str)
    fingerprint = hashlib.sha256(fp_src.encode()).hexdigest()[:16]
    kind = InsightKind.SPORTS_INJURY_READ
    cache_hash = _key(patient.id, kind, fingerprint, provider, today)
    cached = _cached(db, patient.id, kind, cache_hash, provider)
    if cached is not None:
        return _view(cached)
    content: dict[str, Any] | None = None
    if provider != "fallback":
        try:
            prompt = ("This athlete's injury plan:\n" + _injury_digest(board, profile) +
                      f"\n\nWrite the read of the plan. Contract: {INJURY_CONTRACT}")
            raw = complete_json(SYSTEM, prompt, temperature=0.4)
            content = _validate_injury(raw)
            if content is None:
                note_invalid_output(provider)
            else:
                note_valid_output(provider)
        except LLMError as e:
            logger.warning("Sports injury read failed for %s: %s", patient.id, e)
    if content is None:
        provider = "fallback"
        cache_hash = _key(patient.id, kind, fingerprint, provider, today)
        cached = _cached(db, patient.id, kind, cache_hash, provider)
        if cached is not None:
            return _view(cached)
        content = fallback_injury_read(board)
    content = {**content, "guardrail": SPORTS_GUARDRAIL_SENTENCE}
    return _view(_persist(db, patient.id, kind, content, cache_hash, provider))
