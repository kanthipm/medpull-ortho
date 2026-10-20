"""Deterministic answers for the coach when no model is available.

The copilot's own fallback can log and list tasks; it cannot explain a
number. An athlete asking "why is my readiness low" deserves the actual
answer, which the recovery board already holds in words. These intents
are matched by keyword and answered from the boards; anything else falls
through to the copilot's reply.
"""

from __future__ import annotations

import re
from typing import Any


def _fmt(v: Any, digits: int = 0) -> str:
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def answer(text: str, home: dict[str, Any] | None, profile: Any) -> str | None:
    if home is None:
        return None
    t = text.lower()
    rec = home.get("recovery") or {}
    perf = home.get("performance") or {}
    rehab = home.get("rehab") or {}
    v = rec.get("verdict") or {}
    d = rec.get("digest") or {}
    tips = rec.get("suggestions") or []
    sched = rec.get("schedule") or {}

    if re.search(r"\b(readiness|why am i|how am i|how do i look|today'?s? (verdict|read))\b", t) or re.search(r"\bwhy\b.*\b(low|down|red|high)\b", t):
        parts = [f"{v.get('title', 'Today')}: {v.get('reason', '')}".strip()]
        for r_ in (v.get("reasons") or [])[1:3]:
            parts.append(r_)
        if v.get("detail"):
            parts.append(v["detail"])
        return " ".join(p for p in parts if p)[:420]

    if re.search(r"\b(sleep|slept|tired|bed)\b", t):
        p = d.get("sleep") or {}
        if p.get("status") in (None, "nodata"):
            return "No sleep on file yet. Wear your watch tonight and it reads here tomorrow."
        tip = next((x for x in tips if x["category"] == "sleep"), None)
        return (f"Sleep: {p.get('headline', '')}. {p.get('finding', '')} " + (f"{tip['actions'][0]}." if tip else "")).strip()[:420]

    if re.search(r"\b(hrv|heart rate variability|resting heart|rhr)\b", t):
        p = d.get("hrv") or {}
        q = d.get("resting_hr") or {}
        cv = rec.get("hrv_cv") or {}
        out = []
        if p.get("status") not in (None, "nodata"):
            out.append(f"HRV: {p.get('headline', '')}. {p.get('finding', '')}")
        if q.get("status") not in (None, "nodata"):
            out.append(f"Resting HR: {q.get('headline', '')}. {q.get('finding', '')}")
        if cv.get("read"):
            out.append(cv["read"])
        return " ".join(out)[:420] or None

    if re.search(r"\b(load|acwr|volume|too much|overtrain|monoton)\b", t):
        load = rec.get("load") or {}
        return (f"Load: {load.get('finding', '')} This week {_fmt(load.get('week_load'))} AU over {load.get('sessions_week')} "
                f"sessions.").strip()[:420]

    if re.search(r"\b(jump|cmj|legs feel|neuro|fatigue|fresh)\b", t):
        n = rec.get("neuromuscular") or {}
        return (f"Jump test: {n.get('status_text', '')}. {n.get('finding', '')}").strip()[:420]

    if re.search(r"\b(game|practice|schedule|tomorrow|tonight|next)\b", t):
        s = sched.get("finding") or "No team calendar connected."
        tip = tips[0] if tips else None
        return (s + (f" Today: {tip['title'].lower()}: {tip['actions'][0]}." if tip else "")).strip()[:420]

    if re.search(r"\b(injur|knee|ankle|acl|rehab|return|cleared|hop|lsi|symmetr)\b", t):
        active = rehab.get("active") or []
        if not active:
            return "No active injury on file. If something is bothering you, tell your athletic trainer and log it under Injury."
        b = active[0]
        ph = b.get("phase") or {}
        rts = b.get("rts") or {}
        unmet = [c["label"] for c in ph.get("criteria") or [] if c.get("met") is not True]
        focus = [f["title"] for f in (b.get("focus") or [])[:2]]
        return (f"{b.get('label')}, week {_fmt(b.get('weeks'), 1)}: phase {ph.get('number')} of {ph.get('of')}, {ph.get('name', '').lower()}. "
                f"{ph.get('met')} of {ph.get('total')} gates met" + (f"; still open: {', '.join(unmet[:3])}." if unmet else ".")
                + f" Return-to-sport criteria {rts.get('met')} of {rts.get('total')}, projected {rts.get('projected')}."
                + (f" This week: {'; '.join(focus)}." if focus else "")
                + " Clearance is your medical staff's call.")[:420]

    if re.search(r"\b(what should i do|plan|do today|recover|recovery)\b", t):
        if not tips:
            return f"{v.get('title', 'Today')}: {v.get('detail', '')}"
        tip = tips[0]
        return (f"{tip['title']}: {tip['why']} " + " ".join(f"{a}." for a in tip["actions"][:2])).strip()[:420]

    if re.search(r"\b(test|vertical|sprint|agility|strength|percentile|benchmark|stats?)\b", t):
        head = [h for h in (perf.get("headline") or []) if h.get("logged")]
        if not head:
            return "No performance tests logged yet. Log one on the Stats tab and I can read it against your level."
        bits = [f"{h['label']} {h['latest_text']} {h['unit']} ({(h.get('band') or {}).get('word', '')})" for h in head[:4]]
        return ("Your latest: " + "; ".join(bits) + f". Overall you sit around the {perf.get('overall_percentile')}th percentile for your level.")[:420]

    return None
