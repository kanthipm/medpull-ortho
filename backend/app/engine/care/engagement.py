"""Adherence & engagement: M14 verified adherence, M15 disengagement risk,
M16 data confidence. M16 gates the rest — if the device is not being worn
the honest reading is "cannot see this patient", not "this patient is fine".
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from app.engine.care._common import build, nodata
from app.engine.care.types import CareContext, CareMetric, ChartSpec
from app.engine.confidence import KEY_METRICS
from app.models.enums import AdherenceStatus, ConfidenceLevel, MetricStatus
from app.models.enums import MetricType as M

LABELS = {
    str(M.STEPS): "Steps", str(M.RESTING_HR): "Resting HR", str(M.HRV_RMSSD): "HRV",
    str(M.SLEEP_DURATION): "Sleep", str(M.SKIN_TEMP): "Skin temp", str(M.SPO2): "SpO₂",
}
_SCORE = {str(AdherenceStatus.VERIFIED): 1.0, str(AdherenceStatus.SELF_ATTESTED): 0.5,
          str(AdherenceStatus.MISSED): 0.0}


def m14(ctx: CareContext) -> CareMetric:
    tasks = ctx.tasks
    if not tasks:
        return nodata("M14", ctx)
    today = ctx.today
    days = [today - timedelta(days=13 - i) for i in range(14)]
    totals = {"verified": 0, "self_attested": 0, "missed": 0}
    per_task = []
    by_date_scores: dict = {}
    for task in tasks:
        counts = {"verified": 0, "self_attested": 0, "missed": 0}
        for record_date, (status, _source) in task["records"].items():
            key = str(status).replace("AdherenceStatus.", "").lower()
            if key in counts:
                counts[key] += 1
                by_date_scores.setdefault(record_date, []).append(_SCORE.get(key, 0.0))
        assigned = sum(counts.values())
        for k in totals:
            totals[k] += counts[k]
        per_task.append({
            "task_id": task["id"], "title": task["title"], "kind": task["kind"],
            "assigned": assigned,
            "rate": round((counts["verified"] + 0.5 * counts["self_attested"]) / assigned, 2)
            if assigned else None,
            **counts,
        })
    assigned_total = sum(totals.values())
    if assigned_total == 0:
        return nodata(
            "M14", ctx, "No records yet",
            finding=f"{len(tasks)} active task{'s' if len(tasks) != 1 else ''}, no completions "
                    "recorded in the last 14 days.",
            unlock="Completions arrive from check-ins, the app, or wearable verification.",
        )
    rate = (totals["verified"] + 0.5 * totals["self_attested"]) / assigned_total
    if ctx.adherence.assigned == assigned_total:
        rate = float(ctx.adherence.rate)  # the number the risk rule used, verbatim
    verified_rate = totals["verified"] / assigned_total

    def _window_rate(window: list) -> float | None:
        scores = [s for d in window for s in by_date_scores.get(d, [])]
        verified = [s for s in scores if s == 1.0]
        return len(verified) / len(scores) if scores else None

    last7, prior7 = _window_rate(days[7:]), _window_rate(days[:7])
    trend = (last7 - prior7) if last7 is not None and prior7 is not None else None
    # A falling verified rate is "slipping" only when it has somewhere to
    # slip from: two tasks over a week is 14 task-days, where three missed
    # completions read as −21 points, so a still-high rate is left alone.
    if rate < 0.5:
        status, text = MetricStatus.FLAG, "Adherence low"
    elif rate < 0.75 or (trend is not None and trend <= -0.2 and rate < 0.9):
        status, text = MetricStatus.WATCH, "Adherence slipping"
    else:
        status, text = MetricStatus.OK, "Adherence on track"
    finding = (f"{verified_rate * 100:.0f}% of task-days verified and {rate * 100:.0f}% counting "
               f"self-reports at half weight, across {len(tasks)} task"
               f"{'s' if len(tasks) != 1 else ''} over 14 days")
    if trend is not None:
        finding += f"; verified rate {trend * 100:+.0f} points this week vs last"
    finding += "."
    if status is MetricStatus.FLAG:
        finding += " Adherence is below the level the plan was built on."
    heat = []
    for task in tasks[:4]:
        for d in days:
            record = task["records"].get(d)
            key = str(record[0]).replace("AdherenceStatus.", "").lower() if record else None
            heat.append({"x": (d - ctx.surgery_date).days, "row": task["title"],
                         "v": _SCORE.get(key) if key else None})
    chart = ChartSpec(kind="heat", series=heat[:60], y_label="task",
                      extra={"tasks_shown": min(4, len(tasks)), "tasks_total": len(tasks)})
    return build(
        "M14", ctx, status=status, status_text=text, finding=finding,
        value=f"{verified_rate * 100:.0f}%", value_num=verified_rate * 100, unit="verified",
        value_label="verified task-days",
        delta_text=f"{rate * 100:.0f}% incl. self-reported · {len(tasks)} tasks",
        chart=chart, drivers=per_task,
        next_step="Ask which task is hardest to fit in; simplify the plan before adding to it."
        if status is not MetricStatus.OK else None,
        coverage_text=f"{assigned_total} task-days in 14 days", confidence=ctx.confidence.level,
    )


def m15(ctx: CareContext) -> CareMetric:
    checkins = ctx.checkins
    steps = ctx.series.get(str(M.STEPS))
    has_tasks = ctx.adherence.assigned > 0 or bool(ctx.tasks)
    if not checkins and not has_tasks and steps is None:
        return nodata("M15", ctx)
    if checkins:
        last = checkins[-1]["occurred_at"].date()
        days_since = max(0, (ctx.today - last).days)
        latency = min(1.0, max(0.0, days_since / 4.0))
    else:
        days_since, latency = None, 1.0
    length_decay = 0.0
    if len(checkins) >= 4:
        first3 = np.mean([c["patient_chars"] for c in checkins[:3]])
        last3 = np.mean([c["patient_chars"] for c in checkins[-3:]])
        if first3 > 0:
            length_decay = 1.0 - min(1.0, max(0.0, last3 / first3))
    movement = 0.0
    if steps is not None:
        post = steps[steps.index >= 0]
        last7 = post[post.index > ctx.postop_day - 7]
        prior7 = post[(post.index > ctx.postop_day - 14) & (post.index <= ctx.postop_day - 7)]
        if len(last7) >= 4 and len(prior7) >= 4 and prior7.mean() > 0:
            movement = 1.0 - min(1.0, max(0.0, float(last7.mean() / prior7.mean())))
    adherence = (1.0 - float(ctx.adherence.rate)) if ctx.adherence.assigned > 0 else 0.0
    score = 100.0 * (0.4 * latency + 0.2 * length_decay + 0.2 * movement + 0.2 * adherence)
    if score >= 60:
        status, text = MetricStatus.FLAG, "Disengaging"
    elif score >= 35:
        status, text = MetricStatus.WATCH, "Engagement slipping"
    else:
        status, text = MetricStatus.OK, "Engaged"
    drivers = [
        {"key": "latency", "label": "Check-in latency", "value": round(latency, 2), "weight": 0.4,
         "detail": f"{days_since} days since last check-in" if days_since is not None
         else "no check-ins yet"},
        {"key": "length_decay", "label": "Shrinking replies", "value": round(length_decay, 2),
         "weight": 0.2},
        {"key": "movement", "label": "Falling movement", "value": round(movement, 2), "weight": 0.2},
        {"key": "adherence", "label": "Missed tasks", "value": round(adherence, 2), "weight": 0.2},
    ]
    lead = max(drivers, key=lambda d: d["value"] * d["weight"])
    finding = f"Disengagement score {score:.0f}/100"
    parts = []
    if days_since is not None:
        parts.append(f"last check-in {days_since} day{'s' if days_since != 1 else ''} ago")
    else:
        parts.append("no check-ins yet")
    if length_decay > 0:
        parts.append(f"replies {length_decay * 100:.0f}% shorter than at the start")
    if movement > 0:
        parts.append(f"movement down {movement * 100:.0f}% week on week")
    if adherence > 0:
        parts.append(f"{adherence * 100:.0f}% of task-days missed")
    finding += " — " + ", ".join(parts) + "."
    if status is not MetricStatus.OK:
        finding += f" The largest contributor is {lead['label'].lower()}."
    chart = ChartSpec(kind="gauge", series=[], x_label="", y_label="/100",
                      extra={"value": round(score, 1), "min": 0, "max": 100,
                             "bands": [{"to": 35, "tone": "low"}, {"to": 60, "tone": "med"},
                                       {"to": 100, "tone": "high"}]})
    return build(
        "M15", ctx, status=status, status_text=text, finding=finding,
        value=f"{score:.0f}", value_num=score, unit="/100", value_label="disengagement score",
        delta_text=f"largest driver: {lead['label'].lower()}", chart=chart, drivers=drivers,
        next_step="Reach out today — a short personal message restores engagement more often "
                  "than another reminder." if status is MetricStatus.FLAG else None,
        coverage_text=f"{len(checkins)} check-ins on record", confidence=ctx.confidence.level,
    )


def m16(ctx: CareContext) -> CareMetric:
    conf = ctx.confidence
    window = conf.window_days or 7
    coverage = []
    for metric in KEY_METRICS:
        s = ctx.series.get(str(metric))
        present = 0
        if s is not None:
            present = int(((s.index > ctx.postop_day - window) & (s.index <= ctx.postop_day)).sum())
        coverage.append({"metric_type": str(metric), "label": LABELS[str(metric)],
                         "coverage": round(present / window, 2), "days": present})
    sync_hours = None
    if ctx.device_last_sync is not None and ctx.now is not None:
        sync_hours = max(0.0, (ctx.now - ctx.device_last_sync).total_seconds() / 3600.0)
    wear = ctx.series.get(str(M.WEAR_TIME_MINUTES))
    wear_mean = None
    if wear is not None:
        recent = wear[(wear.index > ctx.postop_day - window) & (wear.index <= ctx.postop_day)]
        wear_mean = float(recent.mean()) if len(recent) else None
    if conf.level == ConfidenceLevel.HIGH:
        status, text = MetricStatus.OK, "Watching clearly"
    elif conf.level == ConfidenceLevel.MEDIUM:
        status, text = MetricStatus.WATCH, "Partial coverage"
    else:
        status, text = MetricStatus.FLAG, "Cannot see this patient"
    dark = [LABELS.get(m, m) for m in conf.dark_metrics]
    finding = (f"{conf.days_with_data} of {window} recent days carried at least three key signals; "
               f"panel coverage {conf.score * 100:.0f}%")
    if dark:
        finding += f"; silent all window: {', '.join(dark)}"
    if sync_hours is not None:
        finding += f"; last device sync {sync_hours:.0f} h ago"
    elif ctx.device_last_sync is None:
        finding += "; no device connected"
    if wear_mean is not None:
        finding += f"; worn {wear_mean / 60:.1f} h/day"
    finding += "."
    if status is MetricStatus.FLAG:
        finding += " Every other reading on this page rests on thin data."
    sync_text = (f"last sync {sync_hours:.0f}h ago" if sync_hours is not None
                 else "no device" if ctx.device_last_sync is None else "sync time unknown")
    chart = ChartSpec(kind="bars",
                      series=[{"x": c["label"], "y": round(c["coverage"] * 100)} for c in coverage],
                      x_label="Signal", y_label="% of days")
    return build(
        "M16", ctx, status=status, status_text=text, finding=finding,
        value=f"{conf.score * 100:.0f}%", value_num=conf.score * 100, unit="coverage",
        value_label="data coverage",
        delta_text=f"{conf.days_with_data}/{window} days · {sync_text}", chart=chart,
        drivers=coverage, confidence=conf.level,
        next_step="Confirm the wearable is charged, worn and synced; assign the *Wear watch "
                  "overnight* task." if status is not MetricStatus.OK else None,
        coverage_text=f"{conf.days_with_data} of {window} days with 3+ key signals",
    )
