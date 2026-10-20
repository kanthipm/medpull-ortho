"""The injury engine: where an athlete is in their return, what the
measures say, which criteria are met, and what the next block of work
should be. Criteria-based with the calendar as a floor; the staff's phase
override wins when they set one, and nothing here clears anyone.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.models.sports import SportsInjury, SportsRehabMeasure
from app.sports.catalog.injuries import INJURIES, MEASURES, CriterionSpec, InjurySpec, PhaseSpec
from app.sports.data import SportsData

INVOLVED = ("involved", "left", "right")


def _latest_by_side(rows: list[SportsRehabMeasure], injury: SportsInjury, key: str) -> dict[str, tuple[date, float]]:
    """{'involved': (date, value), 'uninvolved': (date, value)} for a measure,
    reading left/right rows through the injury's side."""
    out: dict[str, tuple[date, float]] = {}
    for r in rows:
        if r.measure_key != key:
            continue
        side = r.side
        if side in ("left", "right"):
            side = "involved" if side == injury.side else "uninvolved"
        if side is None:
            side = "involved"
        prev = out.get(side)
        if prev is None or r.date >= prev[0]:
            out[side] = (r.date, float(r.value))
    return out


def evaluate_criterion(c: CriterionSpec, rows: list[SportsRehabMeasure], injury: SportsInjury,
                       today: date) -> dict[str, Any]:
    spec = MEASURES.get(c.measure_key)
    out: dict[str, Any] = {"measure_key": c.measure_key, "label": c.label, "op": c.op, "target": c.value,
                           "use": c.use, "met": None, "value": None, "value_text": None, "rts": c.rts,
                           "measure_label": spec.label if spec else c.label, "unit": spec.unit if spec else ""}
    if c.use == "days":
        anchor = injury.date_of_surgery or injury.date_of_injury
        days = (today - anchor).days
        out["value"] = days
        weeks = days // 7
        out["value_text"] = f"{weeks} wk" if weeks < 20 else f"{days / 30.4:.1f} mo"
        out["unit"] = "days"
        out["met"] = _compare(days, c.op, c.value)
        return out
    latest = _latest_by_side(rows, injury, c.measure_key)
    inv = latest.get("involved")
    uninv = latest.get("uninvolved")
    if c.use == "lsi":
        if inv is None or uninv is None or uninv[1] <= 0 or inv[1] <= 0:
            out["note"] = "needs both sides"
            return out
        higher = spec.higher_is_better if spec else True
        lsi = (inv[1] / uninv[1]) * 100.0 if higher else (uninv[1] / inv[1]) * 100.0
        out["value"] = round(lsi, 1)
        out["value_text"] = f"{lsi:.0f}%"
        out["unit"] = "% LSI"
        out["date"] = max(inv[0], uninv[0]).isoformat()
        out["met"] = _compare(lsi, c.op, c.value)
        out["sides"] = {"involved": inv[1], "uninvolved": uninv[1]}
        return out
    if c.use == "diff":
        if inv is None or uninv is None:
            out["note"] = "needs both sides"
            return out
        diff = inv[1] - uninv[1]
        out["value"] = round(diff, 1)
        out["value_text"] = f"{diff:+.1f} {spec.unit if spec else ''}".strip()
        out["date"] = max(inv[0], uninv[0]).isoformat()
        # A diff criterion is written as "involved ≥ uninvolved − x" for a
        # range (op ">=", value negative) or "|diff| ≤ x" for a girth.
        if c.op == "<=":
            out["met"] = abs(diff) <= c.value
        else:
            out["met"] = _compare(diff, c.op, c.value)
        out["sides"] = {"involved": inv[1], "uninvolved": uninv[1]}
        return out
    if inv is None:
        return out
    out["value"] = inv[1]
    decimals = spec.decimals if spec else 0
    out["value_text"] = f"{inv[1]:.{decimals}f}"
    out["date"] = inv[0].isoformat()
    out["met"] = _compare(inv[1], c.op, c.value)
    return out


def _compare(value: float, op: str, target: float) -> bool:
    if op == ">=":
        return value >= target
    if op == "<=":
        return value <= target
    if op == "<":
        return value < target
    if op == ">":
        return value > target
    return abs(value - target) < 1e-9


def _phase_for(spec: InjurySpec, injury: SportsInjury, rows: list[SportsRehabMeasure], today: date) -> tuple[int, list[list[dict[str, Any]]]]:
    """Walk the phases: the athlete is in the first phase whose exit
    criteria are not all met (with the week floor honoured)."""
    anchor = injury.date_of_surgery or injury.date_of_injury
    weeks = (today - anchor).days / 7.0
    evaluations: list[list[dict[str, Any]]] = []
    current = len(spec.phases)
    settled = False
    for phase in spec.phases:
        evals = [evaluate_criterion(c, rows, injury, today) for c in phase.exit_criteria]
        evaluations.append(evals)
        if settled:
            continue
        all_met = all(e["met"] is True for e in evals) if evals else weeks >= phase.weeks_min
        floor_ok = weeks >= phase.weeks_min
        if not (all_met and floor_ok):
            current = phase.number
            settled = True
    if injury.phase_override:
        current = max(1, min(injury.phase_override, len(spec.phases)))
    return current, evaluations


def _next_focus(spec: InjurySpec, phase: PhaseSpec, evals: list[dict[str, Any]], injury: SportsInjury,
                rows: list[SportsRehabMeasure], today: date) -> list[dict[str, Any]]:
    """What to work on this week: the unmet criteria, each with the block of
    work that moves it, then the phase's standing focus."""
    focus: list[dict[str, Any]] = []
    unmet = [e for e in evals if e["met"] is not True]
    for e in unmet:
        key = e["measure_key"]
        if key == "__days":
            focus.append({"kind": "time", "title": e["label"],
                          "why": "The calendar is a floor here: tissue heals on its own clock.",
                          "actions": ["Keep the phase's work going; the date arrives on its own."]})
            continue
        spec_m = MEASURES.get(key)
        actions = FOCUS_ACTIONS.get(key, [])
        missing = e.get("value") is None
        focus.append({
            "kind": "measure", "measure_key": key, "title": e["label"],
            "why": (f"Not measured yet: log {spec_m.label.lower()} to see where this stands." if missing
                    else f"Now {e['value_text']}; the gate is {e['op']} {e['target']:g}{'% LSI' if e['use'] == 'lsi' else ''}."),
            "actions": actions[:3] if not missing else [f"Log {spec_m.label.lower()}" + (" on both sides." if spec_m.sided else ".")],
            "missing": missing,
        })
    for f in phase.focus[:4]:
        focus.append({"kind": "block", "title": f, "why": "", "actions": []})
    return focus[:8]


FOCUS_ACTIONS: dict[str, list[str]] = {
    "knee_extension_deficit": ["Heel props 10 min, 3× a day", "Prone hangs 5 min", "Low-load long-duration extension stretch"],
    "knee_flexion": ["Heel slides to tolerance, 3 × 15", "Stationary bike, rock until a full revolution", "Wall slides"],
    "effusion_grade": ["Compression and elevation after sessions", "Drop the session that spiked it by 30%", "Ice 15 min after loading"],
    "slr_lag": ["Quad sets with NMES, 10 × 10 s", "Terminal knee extension with a band", "Straight-leg raise with a 2 s hold"],
    "quad_strength": ["Leg press and single-leg press 3 × 8 heavy", "Leg extension in the safe range, 3 × 10", "Split squats, 3 × 8 each side"],
    "hamstring_strength": ["Nordic lowers 3 × 5", "Single-leg bridge 3 × 10", "Razor curls 3 × 8"],
    "hop_single": ["Single-leg landing stick, 3 × 5", "Submaximal single hops, 3 × 5", "Box-to-floor single-leg landings"],
    "hop_triple": ["Bounding progressions", "Triple hop at 70%, then 85%"],
    "hop_crossover": ["Lateral hop and stick", "Crossover hop at 70%, then 85%"],
    "hop_timed_6m": ["Fast single-leg hops over 3 m, 4 reps", "Pogo hops single leg 3 × 10"],
    "single_leg_cmj": ["Single-leg CMJ 3 × 5 at full effort, twice a week", "Single-leg box jumps"],
    "acl_rsi": ["Graded exposure to the move that worries you, on film", "A confidence conversation with the athletic trainer", "Re-take the ACL-RSI after each sport progression"],
    "ikdc": ["Keep logging symptoms; the score follows function"],
    "visa_p": ["Heavy slow resistance 3×/week", "Decline squat isometrics 5 × 45 s"],
    "decline_squat_pain": ["Isometric holds 5 × 45 s at 70%", "Cut plyometric volume by a third until it drops"],
    "pain_next_morning": ["Hold the load until the morning score settles", "Space hard sessions 48 h apart"],
    "pain_nrs": ["Stay within the 3/10 pain rule during loading", "Settle by the next morning before the next step"],
    "ankle_dorsiflexion": ["Knee-to-wall mobilisation 3 × 30 s with a band", "Calf stretch with the knee bent and straight"],
    "single_leg_balance_s": ["Eyes-closed single-leg stance 3 × 30 s", "Unstable surface balance, 3 × 30 s", "Balance with ball toss"],
    "calf_raise_reps": ["Single-leg calf raises 3 × 15 off a step", "Seated calf raise heavy 3 × 10"],
    "hop_lateral": ["Lateral hops over a line, 3 × 10", "Side hop and stick, 3 × 5"],
    "faam_sport": ["Keep logging; function follows the hop work"],
    "cait": ["Balance training three times a week", "Brace or tape in practice"],
    "ankle_girth_figure8": ["Compression sleeve between sessions", "Elevate and pump after loading"],
    "nordic_force": ["Nordic lowers 3 × 4, twice a week", "Hip extension bridges heavy"],
    "hamstring_ake": ["Extenders and divers (Askling L-protocol)", "Long-length isometrics"],
    "askling_h_pain": ["Keep sprint exposure below the pain line", "Repeat the H-test daily; it clears when it clears"],
    "sprint_pct_max": ["Sprint exposure at 80%, 85%, 90%, then 95%+ over sessions", "Flying 20s with full recovery"],
    "adductor_squeeze": ["Copenhagen adduction, short lever 3 × 8", "Isometric squeeze holds 5 × 30 s"],
    "hagos_sport": ["Keep logging; the score tracks the squeeze"],
    "hip_ir_rom": ["90/90 hip rotations", "Hip internal rotation holds 3 × 30 s"],
    "thomas_test": ["Hip flexor stretch 3 × 45 s", "Couch stretch"],
    "swelling_grade": ["Compression and elevation", "Drop the provoking load for 48 h"],
    "symptom_score": ["Relative rest, screens limited", "Sleep first; symptoms decide the next step"],
    "exertion_symptoms": ["Repeat the current step tomorrow; progress only after 24 h symptom-free"],
    "reaction_time": ["Repeat the tap test each morning"],
    "odi": ["Walk 30 min daily", "Trunk endurance (McGill) 3× a week"],
    "shoulder_ir": ["Sleeper stretch 3 × 30 s", "Cross-body stretch 3 × 30 s"],
    "shoulder_er_ir_ratio": ["External rotation at 90° with a band, 3 × 15", "Prone Y, T, W, 3 × 10"],
    "kjoc": ["Keep logging; it follows the cuff strength"],
    "serve_pct_max": ["Serve ladder: 50, 60, 70, 80, 90, 100%, two sessions each"],
    "prtee": ["Isometric wrist extension holds", "Grip and racquet check"],
    "grip_strength": ["Grip work 3 × 10 with a gripper", "Wrist curls light"],
    "atrs": ["Keep logging; it tracks the calf raise"],
    "visa_a": ["Heavy slow calf raises 3×/week, bent and straight knee"],
    "knee_valgus_dvj": ["Landing mechanics drills: soft, knees over toes", "Film a drop jump every two weeks"],
    "y_balance_anterior_diff": ["Single-leg reaches 3 × 10 each direction"],
    "koos_sport": [], "tampa_tsk": ["Graded exposure with the athletic trainer"], "lysholm": [], "kujala": [],
    "sebt_composite": ["Y-balance reaches 3 × 10 each direction"],
}


def _measure_history(rows: list[SportsRehabMeasure], injury: SportsInjury, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    out = []
    for key in keys:
        spec = MEASURES.get(key)
        if spec is None:
            continue
        mine = [r for r in rows if r.measure_key == key]
        if not mine:
            out.append({"key": key, "label": spec.label, "unit": spec.unit, "sided": spec.sided,
                        "kind": spec.kind, "phone": spec.phone, "higher_is_better": spec.higher_is_better,
                        "lo": spec.lo, "hi": spec.hi, "decimals": spec.decimals, "logged": False,
                        "involved": [], "uninvolved": [], "latest": None, "lsi": None, "protocol": spec.protocol,
                        "why": spec.why, "symbol": spec.symbol, "test_key": spec.test_key})
            continue
        involved, uninvolved = [], []
        for r in mine:
            side = r.side
            if side in ("left", "right"):
                side = "involved" if side == injury.side else "uninvolved"
            point = {"date": r.date.isoformat(), "value": float(r.value), "source": r.source}
            (uninvolved if side == "uninvolved" else involved).append(point)
        latest = _latest_by_side(mine, injury, key)
        inv = latest.get("involved")
        uninv = latest.get("uninvolved")
        lsi = None
        if spec.sided and inv and uninv and inv[1] > 0 and uninv[1] > 0:
            lsi = round((inv[1] / uninv[1]) * 100.0 if spec.higher_is_better else (uninv[1] / inv[1]) * 100.0, 1)
        out.append({"key": key, "label": spec.label, "unit": spec.unit, "sided": spec.sided, "kind": spec.kind,
                    "phone": spec.phone, "higher_is_better": spec.higher_is_better, "lo": spec.lo, "hi": spec.hi,
                    "decimals": spec.decimals, "logged": True, "involved": involved[-20:], "uninvolved": uninvolved[-20:],
                    "latest": inv[1] if inv else None, "latest_date": inv[0].isoformat() if inv else None,
                    "uninvolved_latest": uninv[1] if uninv else None, "lsi": lsi, "protocol": spec.protocol,
                    "why": spec.why, "symbol": spec.symbol, "test_key": spec.test_key})
    return out


def injury_board(injury: SportsInjury, rows: list[SportsRehabMeasure], today: date) -> dict[str, Any]:
    spec = INJURIES.get(injury.injury_key)
    anchor = injury.date_of_surgery or injury.date_of_injury
    days = (today - anchor).days
    base = {
        "id": injury.id, "injury_key": injury.injury_key, "label": injury.label, "side": injury.side,
        "body_region": injury.body_region, "date_of_injury": injury.date_of_injury.isoformat(),
        "date_of_surgery": injury.date_of_surgery.isoformat() if injury.date_of_surgery else None,
        "graft": injury.graft, "grade": injury.grade, "mechanism": injury.mechanism, "status": injury.status,
        "days": days, "weeks": round(days / 7.0, 1), "anchor": "surgery" if injury.date_of_surgery else "injury",
        "target_return_date": injury.target_return_date.isoformat() if injury.target_return_date else None,
        "cleared_at": injury.cleared_at.isoformat() if injury.cleared_at else None,
        "clinician": injury.clinician, "note": injury.note, "symbol": spec.symbol if spec else "cross.case.fill",
    }
    if spec is None:
        return {**base, "known": False, "phase": None, "phases": [], "measures": [], "rts": None, "focus": []}
    current, evaluations = _phase_for(spec, injury, rows, today)
    phases = []
    for phase, evals in zip(spec.phases, evaluations):
        met = sum(1 for e in evals if e["met"] is True)
        phases.append({
            "number": phase.number, "name": phase.name, "window": phase.window, "goals": list(phase.goals),
            "focus": list(phase.focus), "avoid": list(phase.avoid), "weeks_min": phase.weeks_min,
            "state": "done" if phase.number < current else "current" if phase.number == current else "ahead",
            "criteria": evals, "met": met, "total": len(evals),
        })
    current_phase = next(p for p in spec.phases if p.number == current)
    current_evals = evaluations[current - 1] if current - 1 < len(evaluations) else []
    rts_evals = [evaluate_criterion(c, rows, injury, today) for c in spec.rts_criteria]
    rts_met = sum(1 for e in rts_evals if e["met"] is True)
    rts_known = sum(1 for e in rts_evals if e["met"] is not None)
    # Projection: the typical window from the anchor, narrowed by progress.
    lo, hi = spec.typical_return_weeks
    projected_lo = anchor + timedelta(weeks=lo)
    projected_hi = anchor + timedelta(weeks=hi)
    progress = rts_met / len(rts_evals) if rts_evals else 0.0
    projected = anchor + timedelta(weeks=lo + (hi - lo) * (1.0 - progress))
    if injury.target_return_date:
        projected = injury.target_return_date
    pain = _latest_by_side(rows, injury, "pain_nrs").get("involved")
    return {
        **base, "known": True, "summary": spec.summary, "surgical": spec.surgical,
        "phase": {"number": current, "name": current_phase.name, "window": current_phase.window,
                  "of": len(spec.phases), "goals": list(current_phase.goals), "avoid": list(current_phase.avoid),
                  "criteria": current_evals, "met": sum(1 for e in current_evals if e["met"] is True),
                  "total": len(current_evals), "override": injury.phase_override},
        "phases": phases,
        "rts": {"criteria": rts_evals, "met": rts_met, "total": len(rts_evals), "known": rts_known,
                "pct": round(progress * 100), "projected": projected.isoformat(),
                "window": [projected_lo.isoformat(), projected_hi.isoformat()],
                "typical_weeks": [lo, hi], "reinjury_note": spec.reinjury_note},
        "measures": _measure_history(rows, injury, spec.measures),
        "focus": _next_focus(spec, current_phase, current_evals, injury, rows, today),
        "sport_progression": list(spec.sport_progression),
        "sources": list(spec.sources), "retest": list(spec.retest),
        "pain": {"value": pain[1], "date": pain[0].isoformat()} if pain else None,
        "last_measure": max((r.date for r in rows), default=None).isoformat() if rows else None,
    }


def compute_rehab(data: SportsData) -> dict[str, Any]:
    boards = [injury_board(i, data.measures.get(i.id, []), data.today) for i in data.injuries]
    active = [b for b in boards if b["status"] == "active"]
    past = [b for b in boards if b["status"] != "active"]
    return {"active": active, "past": past, "availability": _engine_availability(active),
            "as_of": data.today.isoformat()}


def _engine_availability(active: list[dict[str, Any]]) -> str:
    """Out until the sport-specific progression phase, modified in the last
    one; an overuse injury that is managed in training caps at modified."""
    status = "available"
    for b in active:
        ph = b.get("phase")
        if not ph:
            continue
        spec = INJURIES.get(b["injury_key"])
        sidelines = spec.sidelines if spec else True
        here = "out" if ph["number"] < max(ph["of"] - 1, 1) else "modified"
        if not sidelines and here == "out":
            here = "modified"
        if here == "out" or (here == "modified" and status == "available"):
            status = here
    return status


def availability_for(injury_boards: list[dict[str, Any]], profile_status: str) -> str:
    """The roster status: the staff's own setting wins over the engine's."""
    if profile_status in ("out", "modified"):
        return profile_status
    return _engine_availability([b for b in injury_boards if b["status"] == "active" and b.get("phase")])
