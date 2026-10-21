"""Readiness and recovery for an athlete, and what to do about it today.

The personal tier's engine (``app/personal/metrics.py``) already turns the
wearable stream into readiness, HRV, resting heart rate, sleep, load,
fitness and body-signal panels against the athlete's own baselines. This
module runs it with an athlete's profile, then adds what a team sport
needs on top:

* the morning wellness questionnaire scored two ways: the Hooper index and
  per-item z-scores against the athlete's own four-week mean (z ≤ −1
  yellow, z ≤ −2 red, the tiers wellness-alert systems use);
* the week-on-week load change and monotony read as the primary load
  signals, with the acute:chronic ratio shown as context (it has no
  demonstrated predictive validity: Impellizzeri 2021), and jump load
  counted separately because tendons and shins respond to it;
* the HRV weekly coefficient of variation with Flatt's matrix (mean down
  and CV up is fatigue; mean down and CV down is suppression);
* the schedule: game density, back-to-backs, travel, days to the next game;
* an illness watch over skin temperature, breathing rate, resting HR and
  the wellness answers;
* hydration from the morning weigh-in and urine colour;
* a sports verdict for the day, and the recovery suggestions, each rule
  carrying its evidence grade.

The guardrail: nothing here is medicine, and the staff decide who plays.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.models.enums import MetricType as M
from app.models.sports import SportsEvent
from app.personal.metrics import compute_dashboard
from app.sports.catalog.wellness import HOOPER_KEYS, WELLNESS
from app.sports.data import SportsData

WELLNESS_BASELINE_DAYS = 28
WELLNESS_MIN = 5
LOAD_WEEK_WATCH = 10.0
LOAD_WEEK_FLAG = 15.0
HRV_CV_HIGH = 7.0
RHR_FLAG_BPM = 3.0
TEMP_FLAG = 0.5
MASS_DROP_FLAG_PCT = 2.0
URINE_FLAG = 4.0


class _ProfileShim:
    """What ``compute_dashboard`` reads off a profile."""

    def __init__(self, profile: Any) -> None:
        self.goal = "performance"
        self.sport = profile.sport
        self.weekly_target_minutes = None
        self.sleep_target_hours = None
        self.injury = None


def first_sentence(text: str | None) -> str:
    """The first sentence of a finding, without cutting at a decimal point."""
    if not text:
        return ""
    m = re.search(r"\.(?=\s|$)", text)
    return (text[:m.start()] if m else text).strip() + "."


def _fmt(value: float | None, digits: int = 0) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    return f"{value:.{digits}f}"


# --- wellness ----------------------------------------------------------------------------------


def wellness_panel(data: SportsData) -> dict[str, Any]:
    today = data.today
    items = []
    zs = []
    hooper_parts: dict[str, float] = {}
    answered_today = 0
    latest_day: date | None = None
    for key, spec in WELLNESS.items():
        if spec.kind != "scale":
            continue
        s = data.wellness.get(key)
        if s is None or len(s) == 0:
            continue
        d = s.index[-1]
        latest_day = max(latest_day, d) if latest_day else d
        value = float(s.iloc[-1])
        if d == today:
            answered_today += 1
        window = s[(s.index >= d - timedelta(days=WELLNESS_BASELINE_DAYS)) & (s.index < d)]
        z = None
        if len(window) >= WELLNESS_MIN:
            mean = float(window.mean())
            sd = float(window.std(ddof=1)) if len(window) > 1 else 0.0
            sd = max(sd, 0.8)  # a floor: a flat month must not make a one-point move a crisis
            raw = (value - mean) / sd
            # Normalise direction so negative always means worse.
            z = raw if spec.direction == "good" else -raw
            zs.append(z)
        items.append({
            "key": key, "label": spec.label, "value": value, "date": d.isoformat(), "z": round(z, 2) if z is not None else None,
            "direction": spec.direction, "symbol": spec.symbol,
            "state": ("flag" if z is not None and z <= -2 else "watch" if z is not None and z <= -1 else "ok"),
            "series": [{"date": dd.isoformat(), "value": float(v)} for dd, v in s.tail(14).items()],
        })
        if key in HOOPER_KEYS:
            hooper_parts[key] = value
    hooper = None
    if len(hooper_parts) == 4:
        # Hooper: four items on 1–7 with 7 = worst, so 0–10 maps to 1–7 with sleep inverted.
        def to7(v: float, bad_high: bool) -> float:
            v = v if bad_high else 10.0 - v
            return 1.0 + v * 0.6
        hooper = round(sum(to7(hooper_parts[k], WELLNESS[k].direction == "bad") for k in HOOPER_KEYS), 1)
    composite = float(np.mean(zs)) if zs else None
    status = "nodata" if not items else "ok"
    if composite is not None:
        status = "flag" if composite <= -2 or any(i["state"] == "flag" for i in items) else \
            "watch" if composite <= -1 or sum(1 for i in items if i["state"] == "watch") >= 2 else "ok"
    worst = sorted([i for i in items if i["z"] is not None], key=lambda i: i["z"])[:2]
    finding_parts = []
    if not items:
        finding = "Answer the morning questions and your wellness sits here beside the wearable numbers."
    else:
        for w in worst:
            if w["z"] is not None and w["z"] <= -1:
                finding_parts.append(f"{w['label']} is {abs(w['z']):.1f} SD worse than your usual.")
        if composite is not None and not finding_parts:
            finding_parts.append("Everything you reported is inside your usual range.")
        if latest_day and latest_day < today:
            finding_parts.append(f"Last answered {(today - latest_day).days} day{'s' if (today - latest_day).days != 1 else ''} ago.")
        finding = " ".join(finding_parts)
    return {
        "key": "wellness", "title": "How you feel", "status": status,
        "status_text": {"ok": "Usual self", "watch": "Worth noting", "flag": "Off", "nodata": "Not answered"}[status],
        "composite_z": round(composite, 2) if composite is not None else None,
        "hooper": hooper, "answered_today": answered_today, "latest_date": latest_day.isoformat() if latest_day else None,
        "items": items, "finding": finding,
        "method": "Each answer against your own 28-day mean as a z-score (sleep, mood and energy inverted so "
                  "negative is always worse); yellow at −1 SD, red at −2. The Hooper index sums fatigue, "
                  "stress, soreness and poor sleep on 1–7 (4 best, 28 worst).",
        "notes": data.wellness_text.get("note", [])[-3:],
    }


# --- HRV variability ------------------------------------------------------------------------------


def hrv_cv_read(data: SportsData, hrv_panel: dict[str, Any]) -> dict[str, Any] | None:
    key = str(M.HRV_RMSSD) if len(data.personal.get(str(M.HRV_RMSSD))) else str(M.HRV_SDNN)
    s = data.personal.get(key)
    s = s[s > 0]
    if len(s) < 10:
        return None
    ln = np.log(s.astype(float))
    today = data.today
    week = ln[ln.index > today - timedelta(days=7)]
    prior = ln[(ln.index > today - timedelta(days=35)) & (ln.index <= today - timedelta(days=7))]
    if len(week) < 3 or len(prior) < 7:
        return None
    cv_week = float(week.std(ddof=1) / week.mean() * 100.0)
    cv_prior = float(prior.std(ddof=1) / prior.mean() * 100.0)
    mean_week = float(week.mean())
    mean_prior = float(prior.mean())
    sd_prior = float(prior.std(ddof=1))
    swc = 0.5 * sd_prior
    mean_delta = mean_week - mean_prior
    mean_state = "down" if mean_delta < -swc else "up" if mean_delta > swc else "flat"
    cv_state = "up" if cv_week > cv_prior * 1.25 and cv_week >= HRV_CV_HIGH else "down" if cv_week < cv_prior * 0.75 else "flat"
    # Flatt's matrix.
    if mean_state == "down" and cv_state == "up":
        read, status = "Fatigue or stress: the mean is down and the day-to-day swing is up. Act on it.", "flag"
    elif mean_state == "down" and cv_state == "down":
        read, status = "Suppressed: the mean is down and the swing has gone quiet, which is not recovering. Act on it.", "flag"
    elif mean_state == "up" and cv_state == "down":
        read, status = "A positive response: the mean is up and steadier, the taper-and-fresh pattern.", "ok"
    elif mean_state == "flat" and cv_state == "up":
        read, status = "A new stimulus is being absorbed: the mean holds while the swing widens. Watch it.", "watch"
    else:
        read, status = "Stable against your own baseline.", "ok"
    # Parasympathetic saturation check: lnRMSSD falling with resting HR falling.
    rhr = data.personal.get(str(M.RESTING_HR))
    saturation = False
    if len(rhr) >= 10 and mean_state == "down":
        rhr_week = rhr[rhr.index > today - timedelta(days=7)]
        rhr_prior = rhr[(rhr.index > today - timedelta(days=35)) & (rhr.index <= today - timedelta(days=7))]
        if len(rhr_week) >= 3 and len(rhr_prior) >= 7 and float(rhr_week.mean()) < float(rhr_prior.mean()) - 1.0:
            saturation = True
            read = ("HRV is down while resting heart rate is also down: likely parasympathetic saturation in a "
                    "fit athlete, not fatigue. No action; an orthostatic test settles it.")
            status = "ok"
    return {"cv_week": round(cv_week, 1), "cv_prior": round(cv_prior, 1), "mean_state": mean_state,
            "cv_state": cv_state, "read": read, "status": status, "saturation": saturation,
            "swc_ln": round(swc, 3)}


# --- load ------------------------------------------------------------------------------------


def load_read(data: SportsData, load_panel: dict[str, Any]) -> dict[str, Any]:
    today = data.today
    series = data.session_load_series()
    source = "session RPE" if len(series) else (load_panel.get("extra") or {}).get("source")
    if not len(series):
        raw = load_panel.get("series") or []
        if raw:
            series = pd.Series([p["value"] for p in raw], index=[date.fromisoformat(p["date"]) for p in raw])
    week = series[series.index > today - timedelta(days=7)]
    prior = series[(series.index > today - timedelta(days=14)) & (series.index <= today - timedelta(days=7))]
    prior3 = series[(series.index > today - timedelta(days=28)) & (series.index <= today - timedelta(days=7))]
    week_sum = float(week.sum()) if len(week) else 0.0
    prior_sum = float(prior.sum()) if len(prior) else None
    # The change is read against the mean of the previous three weeks: one odd
    # week should not flag a normal one, and a real ramp still shows.
    weeks_available = max(1, min(3, int(np.ceil(len(prior3) / 7.0)))) if len(prior3) else 0
    prior_mean = float(prior3.sum()) / weeks_available if weeks_available else None
    change = None
    if prior_mean and prior_mean > 0:
        change = (week_sum - prior_mean) / prior_mean * 100.0
    sessions_week = [s for s in data.sessions if s.date > today - timedelta(days=7)]
    minutes_week = sum(float(s.minutes) for s in sessions_week)
    games_week = sum(1 for s in sessions_week if s.kind in ("game", "match"))
    kinds: dict[str, float] = {}
    for s in sessions_week:
        kinds[s.kind] = kinds.get(s.kind, 0.0) + float(s.load_au or 0.0)
    extra = load_panel.get("extra") or {}
    monotony = extra.get("monotony")
    acwr = extra.get("acwr")
    status = "ok"
    parts = []
    if change is not None:
        if change >= LOAD_WEEK_FLAG:
            status = "flag"
            parts.append(f"This week's load is {change:.0f}% above your recent weeks; a jump over 15% is where "
                         "injury risk climbs. Cap the rest of the week.")
        elif change >= LOAD_WEEK_WATCH:
            status = "watch"
            parts.append(f"Load is up {change:.0f}% on your recent weeks; keep the next step under 10%.")
        elif change <= -30:
            parts.append(f"Load is {abs(change):.0f}% lighter than your recent weeks: a deload if planned, a "
                         "detraining week if not.")
        else:
            parts.append(f"Load is {'up' if change >= 0 else 'down'} {abs(change):.0f}% on your recent weeks, inside "
                         "the range a body absorbs.")
    if monotony is not None and monotony >= 2.0:
        if status == "ok":
            status = "watch"
        parts.append(f"Monotony {monotony:.1f}: every day looks the same. A hard day needs an easy one beside it.")
    if acwr is not None and (extra.get("days_history") or 0) >= 14:
        parts.append(f"Acute:chronic {acwr:.2f} for context; the ratio itself does not predict injury "
                     "(Impellizzeri 2021), the weekly change does.")
    last_session = max((s.date for s in data.sessions), default=None)
    return {
        "source": source, "week_load": round(week_sum), "prior_week_load": round(prior_sum) if prior_sum is not None else None,
        "prior_mean_load": round(prior_mean) if prior_mean is not None else None,
        "change_pct": round(change, 1) if change is not None else None, "minutes_week": round(minutes_week),
        "sessions_week": len(sessions_week), "games_week": games_week, "by_kind": {k: round(v) for k, v in kinds.items()},
        "monotony": monotony, "strain": extra.get("strain_week"), "acwr": acwr, "status": status,
        "status_text": {"ok": "Balanced", "watch": "Building fast", "flag": "Spike"}[status],
        "finding": " ".join(parts) or "Log your sessions (minutes and RPE) and the weekly load reads here.",
        "last_session": last_session.isoformat() if last_session else None,
        "series": [{"date": d.isoformat(), "value": round(float(v))} for d, v in series.tail(28).items()],
        "method": "Session load is minutes × RPE (Foster), summed per day. The primary signals are this week "
                  "against the mean of the previous three (over 15% up is the published risk step), monotony (mean over SD of the week) and "
                  "strain (weekly load × monotony). The EWMA acute:chronic ratio is shown for context only.",
    }


# --- schedule -----------------------------------------------------------------------------------


def schedule_read(data: SportsData) -> dict[str, Any]:
    today = data.today
    events = data.events
    games = [e for e in events if e.kind in ("game", "match")]
    past_games = sorted([g for g in games if g.date <= today], key=lambda g: g.date)
    future = sorted([g for g in games if g.date > today], key=lambda g: g.date)
    game_today = next((g for g in games if g.date == today), None)
    game_yesterday = any(g.date == today - timedelta(days=1) for g in games)
    next_game = future[0] if future else None
    last_7 = [g for g in games if today - timedelta(days=7) < g.date <= today]
    last_4 = [g for g in games if today - timedelta(days=4) < g.date <= today]
    back_to_back = game_today is not None and game_yesterday
    three_in_four = len(last_4) >= 3
    travel = [e for e in events if e.kind == "travel" and today - timedelta(days=3) <= e.date <= today + timedelta(days=3)]
    away_recent = any((e.kind in ("game", "match")) and e.home is False and today - timedelta(days=2) <= e.date <= today for e in events)
    upcoming = [e for e in events if today <= e.date <= today + timedelta(days=7)]
    density = "heavy" if (three_in_four or len(last_7) >= 3) else "moderate" if len(last_7) == 2 else "light"
    parts = []
    if game_today:
        parts.append(f"Game day{' (back-to-back)' if back_to_back else ''}: " + (f"vs {game_today.opponent}" if game_today.opponent else game_today.title) + ".")
    elif next_game:
        d = (next_game.date - today).days
        parts.append(f"Next game in {d} day{'s' if d != 1 else ''}" + (f" vs {next_game.opponent}" if next_game.opponent else "") + ".")
    if game_yesterday and not game_today:
        parts.append("Game yesterday: today is a recovery day by the calendar.")
    if three_in_four:
        parts.append("Three games in four days.")
    if travel:
        parts.append("Travel in the window.")
    return {
        "game_today": _event_view(game_today) if game_today else None,
        "game_yesterday": game_yesterday, "back_to_back": back_to_back, "three_in_four": three_in_four,
        "next_game": _event_view(next_game) if next_game else None,
        "days_to_next_game": (next_game.date - today).days if next_game else None,
        "games_last_7": len(last_7), "density": density, "travel": bool(travel), "away_recent": away_recent,
        "today": [_event_view(e) for e in events if e.date == today],
        "upcoming": [_event_view(e) for e in upcoming][:10],
        "finding": " ".join(parts) or "No team calendar connected.",
        "last_game": _event_view(past_games[-1]) if past_games else None,
    }


def _event_view(e: SportsEvent) -> dict[str, Any]:
    return {"id": e.id, "date": e.date.isoformat(), "start_time": e.start_time, "kind": e.kind, "title": e.title,
            "opponent": e.opponent, "home": e.home, "location": e.location, "note": e.note}


# --- illness, hydration, cycle ---------------------------------------------------------------------


def illness_watch(data: SportsData, body_panel: dict[str, Any], rhr_panel: dict[str, Any], wellness: dict[str, Any]) -> dict[str, Any]:
    signals = []
    extra = body_panel.get("extra") or {}
    for s in extra.get("signals") or []:
        z = s.get("z")
        label = (s.get("label") or "").lower()
        if z is None:
            continue
        if "temp" in label and z >= 1.5:
            signals.append(f"skin temperature {s.get('latest')} vs {s.get('baseline')} usual")
        if ("breath" in label or "respir" in label) and z >= 1.5:
            signals.append(f"breathing rate {s.get('latest')} vs {s.get('baseline')} usual")
    rex = rhr_panel.get("extra") or {}
    if rex.get("z_latest") is not None and rex["z_latest"] >= 1.5 and rex.get("latest") is not None:
        signals.append(f"resting HR {rex['latest']:.0f} vs {rex.get('baseline_mean', 0):.0f} usual")
    ill = data.wellness_latest("illness")
    if ill and ill[0] >= data.today - timedelta(days=1) and ill[1] >= 1:
        signals.append("you reported feeling unwell")
    status = "flag" if len(signals) >= 2 else "watch" if len(signals) == 1 else "ok"
    return {"status": status, "signals": signals,
            "finding": ("Two or more overnight signals point the same way: treat today as an illness day, no "
                        "intensity, and tell the athletic trainer." if status == "flag"
                        else "One signal is off; the others are fine." if status == "watch"
                        else "Nothing pointing to illness.")}


def hydration_read(data: SportsData) -> dict[str, Any]:
    urine = data.wellness_latest("hydration")
    mass = data.wellness.get("body_mass_kg")
    parts = []
    status = "ok"
    today = data.today
    if urine and urine[0] >= today - timedelta(days=1):
        if urine[1] >= URINE_FLAG:
            status = "watch"
            parts.append(f"Urine colour {urine[1]:.0f}/8 this morning: start the day behind on fluid.")
    mass_drop = None
    if mass is not None and len(mass) >= 4:
        latest_d, latest_v = mass.index[-1], float(mass.iloc[-1])
        window = mass[(mass.index >= latest_d - timedelta(days=10)) & (mass.index < latest_d)]
        if len(window) >= 3 and latest_d >= today - timedelta(days=1):
            mean = float(window.mean())
            mass_drop = (mean - latest_v) / mean * 100.0
            if mass_drop >= MASS_DROP_FLAG_PCT:
                status = "flag"
                parts.append(f"Morning weight is {mass_drop:.1f}% under your 10-day norm: that is dehydration "
                             "carried into today, not fat loss.")
    return {"status": status, "urine": urine[1] if urine else None, "mass_drop_pct": round(mass_drop, 1) if mass_drop is not None else None,
            "finding": " ".join(parts) or "No hydration flags."}


def cycle_read(data: SportsData) -> dict[str, Any] | None:
    if not data.profile.cycle_tracking:
        return None
    phase = data.wellness_latest("cycle_phase")
    day = data.wellness_latest("cycle_day")
    names = {1: "menstrual", 2: "follicular", 3: "ovulatory", 4: "luteal"}
    s = data.wellness.get("cycle_day")
    flags = []
    cycle_len = None
    if s is not None and len(s) >= 2:
        # Cycle length from day-1 resets.
        ones = [d for d, v in s.items() if v == 1]
        if len(ones) >= 2:
            cycle_len = (ones[-1] - ones[-2]).days
            if cycle_len < 21 or cycle_len > 35:
                flags.append(f"Last cycle was {cycle_len} days; under 21 or over 35 is worth a conversation with the "
                             "team physician.")
        if ones and (data.today - ones[-1]).days > 90:
            flags.append("No period logged in over 90 days: that is a referral, not a training note.")
    return {"phase": names.get(int(phase[1])) if phase else None, "day": int(day[1]) if day else None,
            "cycle_length": cycle_len, "flags": flags,
            "note": "Tracked for context, never to set load by phase: pooled evidence finds only trivial "
                    "performance differences across the cycle (McNulty 2020). Symptoms decide, not the calendar."}


# --- verdict and suggestions -------------------------------------------------------------------------


def sports_verdict(board: dict[str, Any], wellness: dict[str, Any], neuro: dict[str, Any], load: dict[str, Any],
                   schedule: dict[str, Any], illness: dict[str, Any], availability: str, days_with_data: int) -> dict[str, Any]:
    personal = board.get("verdict") or {}
    kind = personal.get("kind", "unknown")
    readiness = (board.get("panels") or {}).get("readiness") or {}
    score = (readiness.get("extra") or {}).get("score")
    reasons: list[str] = []
    if availability == "out":
        return {"kind": "rehab", "title": "Rehab day", "score": score,
                "reason": "Your injury plan sets today.", "detail": "The Injury tab has the block that moves your next criterion.",
                "reasons": reasons}
    if illness["status"] == "flag":
        return {"kind": "rest", "title": "Illness watch", "score": score,
                "reason": illness["finding"], "detail": "No intensity. Fluids, food, sleep, and a word with the athletic trainer.",
                "reasons": illness["signals"]}
    if score is None and days_with_data >= 3:
        return {"kind": "learning", "title": "Waiting on last night", "score": None,
                "reason": "Your nights are in; today's HRV, resting heart rate and sleep haven't synced yet.",
                "detail": "Open your watch or band's app so it uploads last night, then pull down here.",
                "reasons": reasons}
    if kind == "unknown" or score is None or days_with_data < 3:
        return {"kind": "learning", "title": "Still learning you", "score": None,
                "reason": "Readiness needs a few nights of HRV, resting heart rate and sleep.",
                "detail": "Wear your watch overnight, answer the morning questions, and it fills in.", "reasons": reasons}
    severity = {"push": 0, "steady": 1, "easy": 2, "rest": 3}.get(kind, 1)
    if personal.get("reason"):
        reasons.append(personal["reason"])
    if wellness["status"] == "flag":
        severity = max(severity, 2)
        reasons.append(first_sentence(wellness["finding"]))
    elif wellness["status"] == "watch":
        severity = max(severity, 1)
        reasons.append(first_sentence(wellness["finding"]))
    if neuro["status"] == "flag":
        severity = max(severity, 2)
        reasons.append(first_sentence(neuro["finding"]))
    elif neuro["status"] == "watch":
        severity = max(severity, 1)
    if load["status"] == "flag":
        severity = max(severity, 2)
        reasons.append(first_sentence(load["finding"]))
    if schedule.get("game_yesterday") and not schedule.get("game_today"):
        severity = max(severity, 1)
    if availability == "modified":
        severity = max(severity, 1)
    game_today = bool(schedule.get("game_today"))
    if game_today:
        # A game is a game: the verdict is how to get to tip-off, not whether to train.
        if severity >= 2:
            return {"kind": "game_prime", "title": "Game day: prime, don't push", "score": score,
                    "reason": reasons[0] if reasons else "Your signals are under your usual.",
                    "detail": "Shootaround only, a 30–60 minute nap ending an hour before warm-up, fluids and carbs early. Save it for the game.",
                    "reasons": reasons}
        return {"kind": "game", "title": "Game day: green", "score": score,
                "reason": f"Readiness {score:.0f}; signals at or above your usual.",
                "detail": "Normal pre-game routine. Caffeine no later than mid-afternoon if tip-off is late.", "reasons": reasons}
    table = {
        0: ("push", "Full go", "Green light from your overnight signals and your answers.",
            "A quality session if one is planned. Your body is ready for it."),
        1: ("steady", "Train as planned", "Close to your usual; nothing says add, nothing says cut.",
            "Practice as written, moderate intensity. No extra on top."),
        2: ("modify", "Modify today", "Signals are under your usual.",
            "Keep skill and technical work; drop intensity and volume by a third. Recovery work this afternoon."),
        3: ("rest", "Recover today", "Your body is asking for a day.",
            "Light movement, food, water and an early night. No intensity."),
    }
    k, title, default_reason, detail = table[severity]
    reason = reasons[0] if reasons else default_reason
    if score is not None and not reason.lower().startswith("readiness"):
        reason = f"Readiness {score:.0f}. " + reason
    return {"kind": k, "title": title, "score": score, "reason": reason, "detail": detail, "reasons": reasons[:4]}


def suggestions(board: dict[str, Any], wellness: dict[str, Any], neuro: dict[str, Any], load: dict[str, Any],
                schedule: dict[str, Any], illness: dict[str, Any], hydration: dict[str, Any], hrv_cv: dict[str, Any] | None,
                jumps: dict[str, Any] | None, availability: str, cycle: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The signal → action rules, each with its evidence grade. Ordered by
    priority; the home shows the top three, the Recovery tab all of them."""
    out: list[dict[str, Any]] = []
    panels = board.get("panels") or {}
    sleep = panels.get("sleep") or {}
    sx = sleep.get("extra") or {}
    hrv = panels.get("hrv") or {}
    hx = hrv.get("extra") or {}
    rhr = panels.get("resting_hr") or {}
    rx = rhr.get("extra") or {}
    readiness = panels.get("readiness") or {}
    rdx = readiness.get("extra") or {}
    soreness = next((i for i in wellness["items"] if i["key"] == "soreness"), None)
    game_tomorrow = schedule.get("days_to_next_game") == 1
    game_today = bool(schedule.get("game_today"))
    next_in_2 = schedule.get("days_to_next_game") is not None and schedule["days_to_next_game"] <= 2

    def add(key: str, title: str, why: str, actions: list[str], grade: str, priority: int, category: str,
            source: str = "") -> None:
        out.append({"key": key, "title": title, "why": why, "actions": actions, "evidence": grade,
                    "priority": priority, "category": category, "source": source})

    # 15. Illness first.
    if illness["status"] == "flag":
        add("illness", "Illness day", illness["finding"],
            ["No high-intensity work today", "Fluids and food on schedule", "Sleep: an early night and a nap if you can",
             "Tell the athletic trainer; keep away from teammates if you have symptoms"], "B", 0, "illness",
            "Oura temperature-deviation logic; low physical well-being predicted illness in pro basketball")
    # 1. HRV down and RHR up for two days.
    hrv_down = hx.get("z_latest") is not None and hx["z_latest"] <= -1.0 and hrv.get("status") in ("watch", "flag")
    rhr_up = rx.get("delta_7d") is not None and rx["delta_7d"] >= RHR_FLAG_BPM
    if hrv_down and rhr_up and not (hrv_cv and hrv_cv.get("saturation")):
        add("autonomic", "Drop today's intensity",
            f"HRV is below your band and resting heart rate is {rx['delta_7d']:.0f} bpm above usual: the pattern that "
            "persists when the body has not absorbed the week.",
            ["Skill and technical work only; no conditioning", "Sleep need plus 30–60 minutes tonight",
             "A 20–30 minute nap between 1 and 4 pm", "Re-check tomorrow morning before deciding the week"],
            "B", 1, "recovery", "Buchheit 2014: act when a negative change persists 2–3 days")
    # 2. Saturation: no action.
    if hrv_cv and hrv_cv.get("saturation"):
        add("saturation", "Low HRV, but no alarm", hrv_cv["read"],
            ["Nothing to change today", "An orthostatic test (lie five minutes, stand two) settles it"], "B", 6, "recovery",
            "Buchheit 2014 saturation logic")
    # 3. CV up with mean down.
    if hrv_cv and hrv_cv["status"] == "flag" and not hrv_cv.get("saturation"):
        add("hrv_cv", "Cut the load for two or three days", hrv_cv["read"],
            ["Session load down 20–30% for 2–3 days", "What else is going on? Exams, travel, a cold: log it"],
            "C", 2, "load", "Flatt's weekly lnRMSSD CV matrix")
    # 4. Wellness z tiers.
    if wellness["status"] == "flag":
        add("wellness_red", "Individualise today", wellness["finding"],
            ["Trim drill minutes by 20%; keep the skill work", "Massage 20–30 minutes if soreness is the driver",
             "If temperature or breathing rate is also up, see the athletic trainer"], "B", 1, "recovery",
            "Wellness z ≤ −2 (AthleteMonitoring tiers); z −1 costs 5–9% of training output")
    elif wellness["status"] == "watch":
        add("wellness_yellow", "Trim, don't cut", wellness["finding"],
            ["Practice minutes down 10–20%", "15–20 minutes of active recovery after", "Compression this afternoon"],
            "B", 3, "recovery", "Wellness z ≤ −1")
    # 5/6. Soreness after a game with a game soon → massage/compression/CWI, with the strength-block exception.
    if soreness and soreness["z"] is not None and soreness["z"] <= -1 and next_in_2:
        add("doms_game_soon", "Soreness with a game in two days",
            f"Soreness is {abs(soreness['z']):.1f} SD above your usual and the next game is close.",
            ["Massage 20–30 minutes (the strongest single recovery effect)", "Compression garments for 2–8 hours",
             "Cold-water immersion 10–15 minutes at 15 °C or below", "Keep carbs up: 1 g/kg per hour for four hours after sessions"],
            "A", 1, "recovery", "Dupuy 2018 meta-analysis; Brown 2017 compression; CWI ≤ 15 °C")
    elif soreness and soreness["z"] is not None and soreness["z"] <= -1:
        add("doms", "Sore: recover actively, skip the ice bath",
            f"Soreness is {abs(soreness['z']):.1f} SD above your usual with no game in the next two days.",
            ["Active recovery 15–20 minutes easy", "Massage or compression", "No cold-water immersion after lifting: it blunts the strength adaptation you are training for"],
            "B", 4, "recovery", "Roberts 2015: CWI after resistance training blunts hypertrophy")
    # 7. Jump load up with a game tomorrow.
    if jumps and jumps["status"] in ("watch", "flag") and game_tomorrow:
        add("jumps_game", "Shootaround only tomorrow morning", jumps["text"],
            ["Morning countermovement jump (hands on hips) before deciding", "No plyometrics in the next 24 hours",
             "Compression and a nap in the afternoon"], "B", 2, "load",
            "Strategy metrics move before jump height; MD-1 RSI linked to in-game speed")
    elif jumps and jumps["status"] == "flag":
        add("jumps", "Flatten the jump count", jumps["text"],
            ["Keep tomorrow's jumps under your usual session", "Tendon isometrics (Spanish squat 5 × 45 s) if the knee is talking"],
            "C", 4, "load", "Session jump count > 28-day mean + 1 SD")
    # 8/9. Weekly load change and monotony.
    if load["status"] == "flag":
        add("load_spike", "Cap the rest of the week", first_sentence(load["finding"]),
            ["Hold intensity, cut volume for the next two days", "No new conditioning this week",
             "Next week's step: under 10%"], "B", 1, "load", "Gabbett 2016: ≥ 15% weekly increase, injury risk 21–49%")
    elif load["status"] == "watch":
        add("load_building", "Keep the next step small", first_sentence(load["finding"]),
            ["Next week under 10% up", "A hard day needs an easy day beside it"], "B", 4, "load", "Gabbett 2016 week-change data")
    if load.get("monotony") is not None and load["monotony"] >= 2.0:
        add("monotony", "Break the monotony",
            f"Monotony {load['monotony']:.1f}: every day looks the same, and that is how strain builds.",
            ["Insert a day at half your mean load", "Change the modality: pool, bike, skill-only"], "C", 5, "load",
            "Foster 1998")
    # 10. Sleep.
    debt = sx.get("debt_hours") or 0.0
    last = sx.get("last_night_hours")
    need = sx.get("need_hours")
    eff = sx.get("efficiency")
    if (last is not None and need is not None and last < need - 1.0) or debt >= 2.0 or (eff is not None and eff < 0.85):
        why = []
        if last is not None and need is not None and last < need - 1.0:
            why.append(f"Last night {last:.1f} h against a need of {need:.1f} h.")
        if debt >= 2.0:
            why.append(f"{debt:.1f} h of sleep debt this week.")
        if eff is not None and eff < 0.85:
            why.append(f"Efficiency {eff * 100:.0f}%, under the 85% line.")
        add("sleep", "Pay the sleep back tonight", " ".join(why),
            ["Lights out 60–90 minutes earlier for the next 3–7 nights", "A nap of 30 minutes or less, early afternoon",
             "Caffeine cut-off six hours before bed", "Bright light within an hour of waking"], "A", 2, "sleep",
            "Walsh 2021 consensus; Drake 2013 (caffeine at 6 h cut sleep by an hour)")
    bedtime_sd = sx.get("bedtime_sd_min")
    if bedtime_sd is not None and bedtime_sd > 60:
        add("regularity", "Anchor the wake time",
            f"Bedtime varies by {bedtime_sd:.0f} minutes night to night; the body clock cannot settle.",
            ["Same wake time seven days a week, even after a late game", "Bedtime follows from that"], "B", 5, "sleep",
            "Phillips 2017 (sleep regularity)")
    # 12. Travel.
    if schedule.get("travel"):
        add("travel", "Travel plan", "Travel in the window: sleep and the clock take the hit before the legs do.",
            ["Compression on the flight or bus", "Water: 500 ml per hour of travel", "No alcohol", "Nap brief and early; local bedtime on arrival",
             "Across three or more time zones: a day per zone eastward, half a day westward, morning light to shift"],
            "A", 3, "travel", "Janse van Rensburg 2021 jet-lag consensus")
    # 13. Back-to-back / three-in-four.
    if schedule.get("back_to_back") or schedule.get("three_in_four"):
        add("density", "Congested schedule",
            "Back-to-back games, and road back-to-backs run about three and a half times the in-game injury rate.",
            ["Post-game: 40 g protein within 20 minutes and 1–1.2 g/kg carbohydrate per hour for four hours",
             "Casein (40 g) before sleep", "Compression on the way home", "Tomorrow: recovery only, late start"],
            "B", 2, "nutrition", "Ranchordas 2017; Teramoto road back-to-back data")
    elif schedule.get("game_yesterday") and not game_today:
        add("post_game", "The day after a game",
            "Yesterday was a game; today's job is to arrive at the next one recovered.",
            ["15–20 minutes active recovery, then off the legs", "Carbohydrate 6–10 g/kg today", "Protein 20–40 g every three hours",
             "Compression 2–8 hours"], "A", 3, "recovery", "Dupuy 2018; Ranchordas 2017")
    # 14. Hydration.
    if hydration["status"] in ("watch", "flag"):
        add("hydration", "Start on the fluids", hydration["finding"],
            ["5–7 ml/kg of fluid two to four hours before practice", "After: 1.5 L per kg lost, with sodium (40–50 mmol/L)",
             "Weigh in before and after today's session"], "A", 2, "hydration", "NATA 2017 fluid replacement")
    # 16. Late tip-off.
    if game_today and schedule["game_today"].get("start_time") and schedule["game_today"]["start_time"] >= "19:30":
        add("late_game", "Late tip-off tonight", "A game after 7:30 pm pushes sleep back; the caffeine and the lights decide how far.",
            ["Caffeine 3 mg/kg or less, and only pre-game", "Nothing with caffeine after the game", "Dim light on the way home; shower, food, bed",
             "Tomorrow's first session no earlier than 10 am"], "B", 3, "sleep", "Caffeine–sleep evidence; Walsh 2021")
    # 19. Must-play game with low readiness → prime.
    if game_today and (rdx.get("band") in ("amber", "red") or neuro["status"] == "flag"):
        add("prime", "Prime, don't rest", "Low readiness on a game day is a priming problem, not a rest problem.",
            ["A short, low-volume neuromuscular prime in the morning (6–8 submaximal jumps, 2 × 20 m strides)",
             "A 30–60 minute nap ending at least an hour before warm-up", "Carbs early, fluids all afternoon"],
            "B", 1, "recovery", "Priming and nap literature")
    # 17. Return after a break.
    if load.get("sessions_week") == 0 and load.get("prior_week_load") == 0 and load.get("series"):
        add("ramp", "Coming back from a break", "No sessions in two weeks: the first week back sets the injury risk for the month.",
            ["Restart at 60–70% of your usual weekly load and jump count", "Add no more than 10% a week",
             "Rebuild your jump baseline over three tests"], "C", 4, "load", "The 10% rule; chronic load is protective")
    # 18. Cycle flags.
    if cycle and cycle.get("flags"):
        for f in cycle["flags"]:
            add("cycle", "Worth a conversation", f, ["Mention it to the team physician or athletic trainer"], "A", 3, "health",
                "IOC REDs 2023 screening thresholds")
    # Neuromuscular fatigue on a non-game day.
    if neuro["status"] == "flag" and not game_today:
        add("neuro", "Neuromuscular fatigue", neuro["finding"],
            ["No plyometrics or maximal sprints today", "Keep skill work; drop the conditioning piece",
             "Re-jump in 48 hours; expect it back within one SD"], "B", 2, "load",
            "Gathercole 2015: strategy metrics change first; ≥ 10% drop from baseline")
    # Good day: say so.
    if not out:
        add("green", "Nothing to fix", "Every signal is inside your usual range. The best recovery today is a normal day.",
            ["Train as planned", "Eat and sleep as usual", "Answer tomorrow's questions"], "A", 9, "recovery", "")
    out.sort(key=lambda s: (s["priority"], s["title"]))
    return out


# --- assembly ------------------------------------------------------------------------------------


def compute_recovery(data: SportsData, patient: Any, performance: dict[str, Any], availability: str) -> dict[str, Any]:
    shim = _ProfileShim(data.profile)
    board = compute_dashboard(data.personal, patient, shim)
    panels = board["panels"]
    wellness = wellness_panel(data)
    hrv_cv = hrv_cv_read(data, panels.get("hrv") or {})
    load = load_read(data, panels.get("load") or {})
    schedule = schedule_read(data)
    illness = illness_watch(data, panels.get("body") or {}, panels.get("resting_hr") or {}, wellness)
    hydration = hydration_read(data)
    cycle = cycle_read(data)
    neuro = performance.get("neuromuscular") or {"status": "nodata", "finding": "", "signals": []}
    jumps = performance.get("jumps")
    verdict = sports_verdict(board, wellness, neuro, load, schedule, illness, availability, board.get("days_with_data", 0))
    tips = suggestions(board, wellness, neuro, load, schedule, illness, hydration, hrv_cv, jumps, availability, cycle)
    readiness = panels.get("readiness") or {}
    return {
        "as_of": board["as_of"], "days_with_data": board.get("days_with_data", 0),
        "verdict": verdict,
        "readiness": readiness, "panels": panels,
        "sections": ["readiness", "sleep", "hrv", "resting_hr", "load", "fitness", "body", "activity", "rhythm"],
        "wellness": wellness, "hrv_cv": hrv_cv, "load": load, "schedule": schedule, "illness": illness,
        "hydration": hydration, "cycle": cycle, "neuromuscular": neuro, "jumps": jumps,
        "suggestions": tips,
        "trends": board.get("trends"), "week": board.get("week"),
        "digest": board.get("digest"), "fingerprint": board.get("fingerprint"),
    }
