"""What the patient reported, read as signals.

A clinic that follows people who train between visits (the HIRT roster,
app/seed/hirt.py) has no wearable on them. What it has is the daily text
check-in: pain, whether anything new hurts, the night, whether today's
program got done, and how hard and how long the training was. This module
turns those into one ``ReportedSignals`` record per patient so the risk tier
(engine/risk.py) can judge a chart from check-ins alone instead of parking it
in Missing data for ever, and so the console's progress line can say "load
vs prior weeks, pain this week, program done" without a second read.

Where each signal comes from:

* check-in cadence     ``Checkin.occurred_at`` — how many in 7 and 14 days,
                       and how many days since the last one;
* training load        the SESSION_LOAD series (tasks/reported.py), judged
                       with the very windows M1 uses (care/load.load_windows)
                       so the tile and the tier agree, plus a plain this-week
                       vs the-weeks-before comparison for the progress line;
* pain                 the transcripts, through the same parser the care
                       metrics use (care/loaders.load_symptom);
* new pain             the yes line tasks/service.PHRASES writes for the
                       "new pain since your last visit?" question;
* program completion   the PROGRAM_DONE series: 1 all, 0.5 some, 0 none.

Nothing here stores anything, and nothing here decides a tier.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.care.load import load_windows
from app.engine.care.loaders import load_symptom
from app.engine.types import ReportedSignals
from app.models.checkin import Checkin, CheckinMessage
from app.models.enums import MetricType as M

# The patient lines tasks/service.PHRASES writes for the new-pain question.
NEW_PAIN_YES = re.compile(r"new pain that wasn't there", re.IGNORECASE)
NEW_PAIN_NO = re.compile(r"no new pain", re.IGNORECASE)
# A "yes" older than this has been seen at a visit or answered since.
NEW_PAIN_RECENT_DAYS = 3
# Days of pain scores a "vs the week before" needs before it is a comparison.
PAIN_PRIOR_MIN = 3
# Days of load either side of the week boundary for a this-week-vs-prior read.
LOAD_WINDOW_MIN = 3
PROGRAM_WINDOW = 3
PROGRAM_ANSWERS_MIN = 2
WEEK = 7


def _present(series: pd.Series | None, lo: int, hi: int) -> pd.Series:
    """Values on days lo < day <= hi, gaps dropped, program days only."""
    if series is None or len(series) == 0:
        return pd.Series(dtype=float)
    s = series[(series.index >= 0) & (series.index > lo) & (series.index <= hi)]
    return s.dropna().astype(float)


def _checkin_cadence(db: Session, patient_id: str, today: date) -> tuple[int, int, int | None]:
    stamps = db.scalars(
        select(Checkin.occurred_at).where(Checkin.patient_id == patient_id)
    ).all()
    days = sorted({s.date() for s in stamps if s is not None})
    if not days:
        return 0, 0, None
    in7 = sum(1 for d in days if 0 <= (today - d).days < 7)
    in14 = sum(1 for d in days if 0 <= (today - d).days < 14)
    return in7, in14, max(0, (today - days[-1]).days)


def _new_pain(db: Session, patient_id: str, surgery_date: date, today: date) -> tuple[bool, int | None]:
    """The most recent answer to the new-pain question, when it was given in
    the last few days: (it was yes, the program day it was said on)."""
    rows = db.execute(
        select(Checkin.occurred_at, CheckinMessage.text)
        .join(CheckinMessage, CheckinMessage.checkin_id == Checkin.id)
        .where(Checkin.patient_id == patient_id, CheckinMessage.who == "patient")
        .order_by(Checkin.occurred_at.desc(), CheckinMessage.seq.desc())
    ).all()
    for occurred_at, text in rows:
        text = text or ""
        if NEW_PAIN_NO.search(text):
            return False, None
        if NEW_PAIN_YES.search(text):
            if (today - occurred_at.date()).days > NEW_PAIN_RECENT_DAYS:
                return False, None
            return True, (occurred_at.date() - surgery_date).days
    return False, None


def reported_signals(
    db: Session, patient, today: date, postop_day: int, series: dict[str, pd.Series],
) -> ReportedSignals:
    in7, in14, since = _checkin_cadence(db, patient.id, today)
    out = ReportedSignals(checkins_7d=in7, checkins_14d=in14, days_since_checkin=since)

    load = series.get(str(M.SESSION_LOAD))
    program = series.get(str(M.PROGRAM_DONE))
    reported_days = [int(d) for s in (load, program) if s is not None for d in s.index if d >= 0]
    # The 7-day windows end on the last day anything was reported (never
    # later than today): at 7:55 in the morning today's session has not
    # happened yet, and a perfect week must not read as six of seven.
    week_end = min(postop_day, max(reported_days)) if reported_days else None
    out.week_end_day = week_end

    if load is not None and len(load[load.index >= 0]):
        post = load[load.index >= 0].dropna()
        out.load_days = int(len(post))
        windows = load_windows(load, postop_day)
        out.load_ratio = windows.ratio
        out.load_provisional = windows.provisional
        if week_end is not None:
            week = _present(load, week_end - WEEK, week_end)
            prior = _present(load, -1, week_end - WEEK)
            if len(week) >= LOAD_WINDOW_MIN and len(prior) >= LOAD_WINDOW_MIN:
                out.load_week_mean = round(float(week.mean()), 1)
                out.load_prior_mean = round(float(prior.mean()), 1)
                if out.load_prior_mean > 0:
                    out.load_vs_prior_pct = round(
                        (out.load_week_mean / out.load_prior_mean - 1.0) * 100.0, 1
                    )

    pain = load_symptom(db, patient.id, patient.surgery_date, "pain")
    pain = pain[pain["day"] <= postop_day] if not pain.empty else pain
    if not pain.empty:
        by_day = {int(r.day): float(r.mean) for r in pain.itertuples() if r.mean == r.mean}
        if by_day:
            latest_day = max(by_day)
            out.pain_latest = round(by_day[latest_day], 1)
            out.pain_latest_day = latest_day
            prior = [v for d, v in by_day.items() if latest_day - WEEK <= d < latest_day]
            if len(prior) >= PAIN_PRIOR_MIN:
                out.pain_prior_mean = round(sum(prior) / len(prior), 1)
                out.pain_delta = round(out.pain_latest - out.pain_prior_mean, 1)

    out.new_pain, out.new_pain_day = _new_pain(db, patient.id, patient.surgery_date, today)

    if program is not None and len(program[program.index >= 0]):
        post = program[program.index >= 0].dropna()
        out.program_days = int(len(post))
        if week_end is not None:
            last3 = _present(program, week_end - PROGRAM_WINDOW, week_end)
            out.program_answers_3d = int(len(last3))
            if len(last3) >= PROGRAM_ANSWERS_MIN:
                out.program_rate_3d = round(float(last3.mean()), 2)
            week = _present(program, week_end - WEEK, week_end)
            out.program_done_7d = round(float(week.sum()), 1)
            out.program_week_days = WEEK
    return out


# --- the console's progress line ------------------------------------------------------------


def reported_progress(analytics: dict[str, Any]) -> dict[str, Any] | None:
    """The three numbers the patient page shows for a chart followed by
    check-ins — load vs prior weeks, pain this week, program done — or None
    for a patient with no reported training on file, whose row stays as it
    was."""
    reported = analytics.get("reported") if isinstance(analytics, dict) else None
    if not isinstance(reported, dict):
        return None
    if not reported.get("load_days") and not reported.get("program_days"):
        return None
    pain = None
    if reported.get("pain_latest") is not None:
        pain = {
            "latest": reported["pain_latest"],
            "prior_mean": reported.get("pain_prior_mean"),
            "delta": reported.get("pain_delta"),
        }
    program = None
    if reported.get("program_days"):
        program = {
            "done": reported.get("program_done_7d", 0.0),
            "of": reported.get("program_week_days", WEEK),
            "rate_3d": reported.get("program_rate_3d"),
        }
    return {
        "load_vs_prior_pct": reported.get("load_vs_prior_pct"),
        "load_ratio": reported.get("load_ratio"),
        "load_week_mean": reported.get("load_week_mean"),
        "load_prior_mean": reported.get("load_prior_mean"),
        "pain": pain,
        "program": program,
        "checkins_7d": reported.get("checkins_7d", 0),
        "days_since_checkin": reported.get("days_since_checkin"),
    }


__all__ = ["reported_signals", "reported_progress", "NEW_PAIN_YES", "NEW_PAIN_NO"]
