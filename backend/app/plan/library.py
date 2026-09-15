"""The deployable task library, by use case.

UC1–UC7 transcribe the pitched orthopedic library row for row (the task is
also the measurement instrument: each one drives recovery and passively
produces the data a care metric needs). UC8–UC12 extend it to the chronic
pathways the platform monitors. Patient-facing ``title``/``why`` are plain,
warm and number-free beyond the count inside the instruction itself; the
provider-facing ``clinical_target`` carries the clinical intent; ``feeds``
names the metrics the task's data feeds.

``ensure_library`` upserts by key so the wording can evolve while a
clinician's pins, archives and usage counts survive.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.care.pathways import PATHWAYS, Pathway
from app.models.library import TaskTemplate
from app.plan.verify_kinds import VerifyKind, default_task_kind, params_for

logger = logging.getLogger(__name__)

V = VerifyKind


@dataclass(frozen=True)
class TemplateSpec:
    key: str
    title: str
    why: str
    clinical_target: str
    verify_kind: VerifyKind
    schedule: str
    phase: str
    feeds: tuple[str, ...]
    pathways: tuple[str, ...]      # pathway keys or domains; () = every pathway
    use_case: str
    params: dict[str, Any] = field(default_factory=dict)
    task_kind: str | None = None   # None = the verify kind's default
    pinned: bool = False


def _t(key, title, why, target, kind, schedule, phase, feeds, pathways, uc, params=None,
       task_kind=None, pinned=False) -> TemplateSpec:
    return TemplateSpec(key, title, why, target, kind, schedule, phase, tuple(feeds),
                        tuple(pathways), uc, dict(params or {}), task_kind, pinned)


KNEE = ("ortho_tka", "ortho_meniscus")
HIP = ("ortho_tha",)
ACL = ("ortho_acl",)
SHOULDER = ("ortho_shoulder",)
SPINE = ("ortho_spine",)
FRACTURE = ("ortho_ankle",)
POSTOP = ("ortho", "general")

LIBRARY: list[TemplateSpec] = [
    # --- UC1 Total knee replacement ---------------------------------------------
    _t("uc1_early_three_walks", "Take three short walks spread across the day",
       "Gentle, frequent movement helps the knee heal and keeps your blood moving.",
       "Early mobilization, DVT prevention", V.WALK_BOUTS, "daily", "early",
       ["M1", "M9", "M14"], KNEE, "UC1", {"bouts": 3, "min_minutes": 5}, pinned=True),
    _t("uc1_early_sit_to_stand", "Do five sit-to-stands, morning and evening",
       "Standing up from a chair wakes up the thigh muscles that steady your knee.",
       "Quadriceps re-activation, transfer ability", V.SIT_TO_STAND, "am_pm", "early",
       ["M6", "M14"], KNEE, "UC1", {"reps": 5, "times": 2}),
    _t("uc1_mid_guided_walk", "Do the short guided walk in the app",
       "A couple of minutes of walking with the app lets your care team see how your stride "
       "is coming back.",
       "Capture clean gait for symmetry/economy", V.GUIDED_WALK, "daily", "mid",
       ["M3", "M4", "M7"], KNEE, "UC1", {"minutes": 2}),
    _t("uc1_mid_step_band", "Stay within today's step range",
       "Enough walking to keep progressing, not so much that the knee swells.",
       "Prevent effusion from over-doing it", V.STEPS_BAND, "daily", "mid",
       ["M1", "M2"], KNEE, "UC1", {"auto": True}, pinned=True),
    _t("uc1_mid_one_flight", "Climb one flight of stairs",
       "Stairs are a real milestone — one flight shows the knee is ready for more.",
       "Functional milestone", V.STAIRS, "daily", "mid", ["M8"], KNEE, "UC1", {"flights": 1}),
    _t("uc1_late_ten_min_walk", "Walk for ten minutes without stopping",
       "One longer walk builds the stamina you need for everyday outings.",
       "Endurance", V.CONTINUOUS_WALK, "daily", "late", ["M5", "M7"], KNEE, "UC1",
       {"minutes": 10}),
    _t("uc1_pain_am_pm", "Log your knee pain in the morning and evening",
       "Two quick pain scores a day show your care team how the knee is settling.",
       "Anchor for tolerance & trajectory", V.PAIN_LOG, "am_pm", "ongoing",
       ["M2", "M9", "M17"], KNEE, "UC1", {"times": 2}),
    _t("uc1_overnight_wear", "Wear your watch overnight",
       "Your sleep tells us how well your pain is controlled at night.",
       "Night-pain proxy + surveillance", V.OVERNIGHT_WEAR, "daily", "ongoing",
       ["M9", "M10", "M12"], KNEE, "UC1", {"nights_per_week": 5}),
    # --- UC2 Total hip replacement -----------------------------------------------
    _t("uc2_early_move_hourly", "Move or stand up every hour you are awake",
       "Short, regular movement keeps the hip from stiffening and your blood flowing.",
       "Hip stiffness + DVT prevention", V.MOVE_HOURLY, "daily", "early",
       ["M1", "M12"], HIP, "UC2", {"hours": 8}),
    _t("uc2_early_three_walks", "Take three short walks, spaced through the day",
       "Spaced walks rebuild your stride and your stamina a little at a time.",
       "Gait re-education, endurance base", V.WALK_BOUTS, "daily", "early",
       ["M1", "M7"], HIP, "UC2", {"bouts": 3, "min_minutes": 5}),
    _t("uc2_mid_guided_walk", "Do the guided walk in the app",
       "A short walk with the app shows how evenly you are putting weight on the new hip.",
       "Weight-bearing symmetry trend", V.GUIDED_WALK, "daily", "mid",
       ["M3", "M4"], HIP, "UC2", {"minutes": 2}),
    _t("uc2_mid_step_band", "Stay within today's step range",
       "A steady amount each day helps the hip get stronger without flare-ups.",
       "Balanced progression", V.STEPS_BAND, "daily", "mid", ["M1", "M2"], HIP, "UC2",
       {"auto": True}),
    _t("uc2_late_distance_ramp", "Walk a little farther each week",
       "Building up your walking distance gets you back to errands and outings.",
       "Community-ambulation capacity (distance ramp)", V.DISTANCE_TARGET, "daily", "late",
       ["M5", "M7", "M17"], HIP, "UC2", {"miles": 0.3}),
    _t("uc2_pain_precaution", "Log your pain and tick off your hip precautions",
       "A quick daily note on pain and positions keeps your new hip safe.",
       "Safety + tolerance (pain + precaution check)", V.PAIN_LOG, "daily", "ongoing",
       ["M2", "M18"], HIP, "UC2", {"times": 1}),
    _t("uc2_overnight_wear", "Wear your watch overnight",
       "Your nights tell us how your body is recovering.",
       "Recovery quality + surveillance", V.OVERNIGHT_WEAR, "daily", "ongoing",
       ["M9", "M10", "M12"], HIP, "UC2", {"nights_per_week": 5}),
    # --- UC3 ACL reconstruction ----------------------------------------------------
    _t("uc3_early_step_band", "Keep to today's step range",
       "Too much too soon makes the knee swell; the range keeps you in the sweet spot.",
       "Avoid swelling-provoking overload (effusion control)", V.STEPS_BAND, "daily", "early",
       ["M1", "M2"], ACL, "UC3", {"auto": True}),
    _t("uc3_early_guided_walk", "Do the guided walk in the app",
       "A short walk with the app shows how your stride is evening out.",
       "Symmetry + normalize gait", V.GUIDED_WALK, "daily", "early",
       ["M3", "M4"], ACL, "UC3", {"minutes": 2}),
    _t("uc3_mid_cadence_walk", "Take a brisk, steady-paced walk",
       "Walking at a normal rhythm retrains the knee for everyday pace.",
       "Restore normal cadence/economy", V.CONTINUOUS_WALK, "daily", "mid",
       ["M4", "M7"], ACL, "UC3", {"minutes": 10}),
    _t("uc3_mid_stairs", "Practise stairs, a little more each week",
       "Stairs build the control your knee needs going down as well as up.",
       "Eccentric control milestone (progressive stairs)", V.STAIRS, "daily", "mid",
       ["M8"], ACL, "UC3", {"flights": 2}),
    _t("uc3_late_run_session", "Log your jog or run session",
       "Once your surgeon has cleared running, logging each session shows how it is going.",
       "Running symmetry & economy — progress tracking, not clearance",
       V.THERAPY_SESSION, "weekly", "late", ["M4", "M5", "M17"], ACL, "UC3",
       {"minutes": 20}, task_kind="exercise"),
    _t("uc3_pain_swelling_log", "Log pain and swelling, morning and evening",
       "Two quick notes a day tell us how the knee is coping with each step up.",
       "Irritability tracking", V.PAIN_LOG, "am_pm", "ongoing", ["M2", "M9"], ACL, "UC3",
       {"times": 2}),
    _t("uc3_overnight_wear", "Wear your watch overnight",
       "Your nights show whether the training load is balanced.",
       "Recovery load balance", V.OVERNIGHT_WEAR, "daily", "ongoing",
       ["M10", "M11"], ACL, "UC3", {"nights_per_week": 5}),
    # --- UC4 Rotator cuff / shoulder -------------------------------------------------
    _t("uc4_overnight_wear", "Wear your watch overnight",
       "Night pain is the hardest part of a shoulder repair — your sleep shows us how you "
       "are doing.",
       "Night-pain proxy — primary signal for shoulder", V.OVERNIGHT_WEAR, "daily", "ongoing",
       ["M9", "M10"], SHOULDER, "UC4", {"nights_per_week": 5}),
    _t("uc4_pain_am_pm", "Log your shoulder pain, morning and evening",
       "Two quick scores a day show whether your pain plan is working.",
       "Pain-control tracking", V.PAIN_LOG, "am_pm", "ongoing", ["M2", "M9"], SHOULDER, "UC4",
       {"times": 2}),
    _t("uc4_rom_milestones", "Tick off each shoulder movement milestone you reach",
       "Each new movement you manage is progress worth recording.",
       "Functional recovery (ROM is self-report by design)", V.ROM_MILESTONE, "ongoing",
       "ongoing", ["M17"], SHOULDER, "UC4"),
    _t("uc4_therapy_session", "Complete your therapy session in the app",
       "The timer keeps you honest on the pendulum and stretching routine.",
       "Adherence to pendulum/PROM protocol", V.THERAPY_SESSION, "daily", "ongoing",
       ["M14"], SHOULDER, "UC4", {"minutes": 15}),
    _t("uc4_step_baseline", "Keep up your usual daily walking",
       "Staying active overall helps the whole body heal, even while the shoulder rests.",
       "Guard against global deconditioning", V.STEPS_BAND, "daily", "ongoing",
       ["M1", "M15"], SHOULDER, "UC4", {"auto": True}),
    _t("uc4_incision_photo", "Send a photo of the incision each week",
       "A weekly photo lets your care team check the wound without a visit.",
       "Surgical-site infection watch", V.INCISION_PHOTO, "weekly", "ongoing",
       ["M13"], SHOULDER, "UC4", {"cadence": "weekly"}),
    # --- UC5 Lumbar spine -------------------------------------------------------------
    _t("uc5_early_sitting_limit", "Stand up and move before you have sat for half an hour",
       "Long stretches of sitting load the back; short breaks protect it.",
       "Sitting-tolerance protection", V.SEDENTARY_LIMIT, "daily", "early",
       ["M1", "M18"], SPINE, "UC5", {"max_minutes": 45}),
    _t("uc5_early_three_walks", "Take three short walks, spaced through the day",
       "Walking is the best medicine for the back — little and often.",
       "Walking tolerance base", V.WALK_BOUTS, "daily", "early", ["M1", "M7"], SPINE, "UC5",
       {"bouts": 3, "min_minutes": 5}),
    _t("uc5_mid_longest_walk", "Take one longer walk without stopping",
       "How far you can walk in one go is the clearest sign your back is recovering.",
       "Walking tolerance is the key spine metric", V.CONTINUOUS_WALK, "daily", "mid",
       ["M5", "M7", "M17"], SPINE, "UC5", {"minutes": 15}),
    _t("uc5_mid_step_band", "Stay within today's step range",
       "Enough to keep progressing, not so much that the back flares up.",
       "Avoid over/under-loading", V.STEPS_BAND, "daily", "mid", ["M1", "M2"], SPINE, "UC5",
       {"auto": True}),
    _t("uc5_back_leg_pain", "Log back pain and leg pain separately, morning and evening",
       "Back pain and leg pain tell different stories; logging both helps us help you.",
       "Distinguish mechanical vs. radicular trend", V.SYMPTOM_LOG, "am_pm", "ongoing",
       ["M2", "M18"], SPINE, "UC5", {"fields": ["back_pain", "leg_pain"]}),
    _t("uc5_overnight_wear", "Wear your watch overnight",
       "Your sleep shows how well your body is recovering.",
       "Sleep + systemic recovery", V.OVERNIGHT_WEAR, "daily", "ongoing",
       ["M9", "M10"], SPINE, "UC5", {"nights_per_week": 5}),
    # --- UC6 Lower-limb fracture ---------------------------------------------------------
    _t("uc6_nwb_seated_session", "Do your seated or upper-body exercise session",
       "Keeping the rest of you strong makes the return to walking easier.",
       "Keep conditioning without loading (NWB)", V.THERAPY_SESSION, "daily", "early",
       ["M14", "M15"], FRACTURE, "UC6", {"minutes": 15}),
    _t("uc6_nwb_move_hourly", "Shift position or move every hour you are awake",
       "Regular movement while you are off your feet keeps your blood flowing.",
       "DVT prevention during immobility — critical", V.MOVE_HOURLY, "daily", "early",
       ["M12"], FRACTURE, "UC6", {"hours": 8}),
    _t("uc6_transition_short_walks", "Take two short walks a day, as cleared",
       "Short walks are the first step back onto your feet.",
       "Begin controlled loading (transition to weight-bearing)", V.WALK_BOUTS, "daily", "mid",
       ["M1", "M3"], FRACTURE, "UC6", {"bouts": 2, "min_minutes": 3}),
    _t("uc6_progression_step_band", "Stay within today's step range",
       "A steady build-up lets the bone take more weight safely.",
       "Structured weight-bearing progression", V.STEPS_BAND, "daily", "mid",
       ["M1", "M2", "M17"], FRACTURE, "UC6", {"auto": True}),
    _t("uc6_progression_guided_walk", "Do the guided walk in the app",
       "A short walk with the app shows how evenly you are stepping again.",
       "Track weight-bearing symmetry recovery", V.GUIDED_WALK, "daily", "late",
       ["M3", "M4"], FRACTURE, "UC6", {"minutes": 2}),
    _t("uc6_pain_swelling_log", "Log pain and swelling each day",
       "A quick daily note tells us how the leg is handling more weight.",
       "Loading tolerance", V.PAIN_LOG, "daily", "ongoing", ["M2", "M9"], FRACTURE, "UC6",
       {"times": 1}),
    _t("uc6_overnight_wear", "Wear your watch overnight",
       "Your nights show how the rest of your body is coping.",
       "VTE/infection surveillance", V.OVERNIGHT_WEAR, "daily", "ongoing",
       ["M12", "M13"], FRACTURE, "UC6", {"nights_per_week": 5}),
    # --- UC7 Cross-cutting (every post-op patient) -----------------------------------------
    _t("uc7_overnight_wear", "Wear your watch overnight most nights",
       "Your sleep and overnight signals tell your care team how recovery is going.",
       "Unlocks the surveillance + recovery-quality stack", V.OVERNIGHT_WEAR, "daily",
       "ongoing", ["M9", "M10", "M11", "M12"], POSTOP, "UC7", {"nights_per_week": 5},
       pinned=True),
    _t("uc7_pain_am_pm", "Log your pain in the morning and evening",
       "Two quick scores a day help your care team see the trend, not just today.",
       "Anchors tolerance + trajectory models", V.PAIN_LOG, "am_pm", "ongoing",
       ["M2", "M17", "M18"], POSTOP, "UC7", {"times": 2}, pinned=True),
    _t("uc7_medication_log", "Log the medications you take",
       "Knowing what you took and when helps us get your pain plan right.",
       "Adherence + analgesia-timing context", V.MEDICATION_LOG, "daily", "ongoing",
       ["M14"], POSTOP, "UC7"),
    _t("uc7_prom_weekly", "Fill in the short weekly questionnaire",
       "A few questions once a week show how everyday life is getting easier.",
       "Functional trajectory anchor (weekly PROM)", V.PROM_WEEKLY, "weekly", "ongoing",
       ["M17"], POSTOP, "UC7", {"instrument": "PROM"}),
    _t("uc7_incision_photo", "Send a photo of the incision each week",
       "A weekly photo lets your care team keep an eye on healing.",
       "Infection watch, pairs with thermal", V.INCISION_PHOTO, "weekly", "ongoing",
       ["M13"], POSTOP, "UC7", {"cadence": "weekly"}, pinned=True),
    # --- UC8 Heart failure -------------------------------------------------------------------
    _t("uc8_daily_weight", "Weigh yourself every morning",
       "A morning weight, before breakfast, is the earliest sign of fluid building up.",
       "Fluid-retention surveillance (daily weight)", V.WEIGHT_LOG, "daily", "ongoing",
       ["C1"], ("heart_failure",), "UC8", pinned=True),
    _t("uc8_symptom_log", "Log breathlessness, swelling and tiredness each day",
       "A quick daily note helps your team spot a change before it becomes a problem.",
       "Symptom burden (breathlessness / edema / fatigue)", V.SYMPTOM_LOG, "daily", "ongoing",
       ["C5", "M2"], ("heart_failure",), "UC8",
       {"fields": ["breathlessness", "swelling", "fatigue"]}),
    _t("uc8_fluid_sodium_note", "Note your fluids and salty foods for the day",
       "Keeping an eye on fluids and salt helps keep the extra water off.",
       "Fluid and sodium restriction adherence", V.FLUID_NOTE, "daily", "ongoing",
       ["C1"], ("heart_failure",), "UC8"),
    _t("uc8_activity_band", "Keep your activity within your usual range",
       "Steady, familiar activity keeps you strong without overdoing it.",
       "Activity band vs personal baseline", V.STEPS_BAND, "daily", "ongoing",
       ["M1", "C6"], ("heart_failure",), "UC8", {"auto": True}),
    _t("uc8_medication_log", "Log your heart medications each day",
       "Taking them on time is the single biggest thing that keeps you well.",
       "Medication adherence (diuretic/GDMT)", V.MEDICATION_LOG, "daily", "ongoing",
       ["M14"], ("heart_failure",), "UC8"),
    _t("uc8_overnight_wear", "Wear your watch overnight",
       "Your overnight signals help your team see how your heart is coping.",
       "Overnight vitals for surveillance", V.OVERNIGHT_WEAR, "daily", "ongoing",
       ["M10", "M12", "C2"], ("heart_failure",), "UC8", {"nights_per_week": 5}),
    # --- UC9 COPD ------------------------------------------------------------------------------
    _t("uc9_morning_spo2", "Check your oxygen level each morning",
       "A morning reading shows your team how your lungs are doing day to day.",
       "SpO₂ surveillance (morning check)", V.SPO2_CHECK, "daily", "ongoing",
       ["C2"], ("copd",), "UC9"),
    _t("uc9_inhaler_log", "Log each time you use your inhalers",
       "Regular inhaler use is what keeps flare-ups away.",
       "Inhaler adherence", V.INHALER_LOG, "daily", "ongoing", ["M14"], ("copd",), "UC9"),
    _t("uc9_breathlessness_am_pm", "Rate your breathlessness in the morning and evening",
       "Two quick ratings a day show whether your breathing is holding steady.",
       "Breathlessness trend (mMRC-style AM/PM)", V.BREATHLESSNESS_LOG, "am_pm", "ongoing",
       ["M2", "C5"], ("copd",), "UC9", {"times": 2}),
    _t("uc9_rehab_walks", "Take two short rehab walks a day",
       "Short, regular walks build the stamina your lungs need.",
       "Pulmonary rehab walking (bouts)", V.WALK_BOUTS, "daily", "ongoing",
       ["M1", "M5"], ("copd",), "UC9", {"bouts": 2, "min_minutes": 5}),
    _t("uc9_overnight_wear", "Wear your watch overnight",
       "Overnight oxygen and breathing readings help your team keep watch.",
       "Overnight SpO₂ / respiratory surveillance", V.OVERNIGHT_WEAR, "daily", "ongoing",
       ["C2", "M12"], ("copd",), "UC9", {"nights_per_week": 5}),
    # --- UC10 Diabetes ------------------------------------------------------------------------
    _t("uc10_glucose_log", "Check your blood sugar before breakfast and before dinner",
       "Two readings a day show how well your plan is keeping sugar in range.",
       "Glucose time-in-range (log)", V.GLUCOSE_LOG, "am_pm", "ongoing",
       ["C3"], ("diabetes",), "UC10", {"times": 2}),
    _t("uc10_foot_check", "Check your feet each evening",
       "A quick look for sores or redness catches small problems early.",
       "Diabetic foot surveillance", V.FOOT_CHECK, "daily", "ongoing",
       ["C5"], ("diabetes",), "UC10"),
    _t("uc10_activity_band", "Keep your activity within your usual range",
       "Regular movement helps your body use sugar better.",
       "Activity band vs personal baseline", V.STEPS_BAND, "daily", "ongoing",
       ["M1", "C6"], ("diabetes",), "UC10", {"auto": True}),
    _t("uc10_medication_log", "Log your diabetes medications each day",
       "Taking them on schedule keeps your sugar steady.",
       "Medication adherence", V.MEDICATION_LOG, "daily", "ongoing",
       ["M14"], ("diabetes",), "UC10"),
    _t("uc10_prom_weekly", "Fill in the short weekly questionnaire",
       "A few questions once a week show how you are feeling overall.",
       "Weekly PROM (well-being)", V.PROM_WEEKLY, "weekly", "ongoing",
       ["M17", "C5"], ("diabetes",), "UC10", {"instrument": "PROM"}),
    # --- UC11 Hypertension ---------------------------------------------------------------------
    _t("uc11_bp_am_pm", "Take your blood pressure in the morning and evening",
       "Two readings a day, seated and rested, show whether your pressure is under control.",
       "Blood-pressure control (AM/PM log)", V.BP_LOG, "am_pm", "ongoing",
       ["C4"], ("hypertension",), "UC11", {"times": 2}, pinned=True),
    _t("uc11_sodium_note", "Note the salty foods you had today",
       "Less salt is one of the quickest ways to bring pressure down.",
       "Sodium restriction adherence", V.FLUID_NOTE, "daily", "ongoing",
       ["C4"], ("hypertension",), "UC11"),
    _t("uc11_activity_band", "Keep your activity within your usual range",
       "Regular movement helps keep your blood pressure down.",
       "Activity band vs personal baseline", V.STEPS_BAND, "daily", "ongoing",
       ["M1", "C6"], ("hypertension",), "UC11", {"auto": True}),
    _t("uc11_medication_log", "Log your blood-pressure medications each day",
       "Taking them every day is what keeps your pressure steady.",
       "Medication adherence", V.MEDICATION_LOG, "daily", "ongoing",
       ["M14"], ("hypertension",), "UC11"),
    # --- UC12 Chronic pain / deconditioning -------------------------------------------------
    _t("uc12_pain_am_pm", "Log your pain in the morning and evening",
       "Two quick scores a day help us see what helps and what does not.",
       "Pain trend anchor", V.PAIN_LOG, "am_pm", "ongoing", ["M2", "C5"],
       ("chronic_pain",), "UC12", {"times": 2}),
    _t("uc12_graded_activity_band", "Keep your activity within today's range",
       "A steady, gradual build-up is what gets you moving more without flare-ups.",
       "Graded activity (pacing band)", V.STEPS_BAND, "daily", "ongoing",
       ["M1", "M2"], ("chronic_pain",), "UC12", {"auto": True}),
    _t("uc12_sleep_hygiene", "Follow your wind-down routine before bed",
       "Better sleep makes pain easier to manage the next day.",
       "Sleep hygiene routine", V.CUSTOM, "daily", "ongoing", ["M9"],
       ("chronic_pain",), "UC12"),
    _t("uc12_pacing_rule", "Stop before the pain climbs, not after",
       "Pacing keeps good days from turning into bad weeks.",
       "Pacing rule (activity-pain boundary)", V.PRECAUTION, "ongoing", "ongoing",
       ["M2"], ("chronic_pain",), "UC12"),
    _t("uc12_prom_weekly", "Fill in the short weekly questionnaire",
       "A few questions once a week show how everyday life is changing.",
       "Weekly PROM (function)", V.PROM_WEEKLY, "weekly", "ongoing", ["M17"],
       ("chronic_pain",), "UC12", {"instrument": "PROM"}),
]

BY_KEY: dict[str, TemplateSpec] = {t.key: t for t in LIBRARY}
PINNED_DEFAULTS: tuple[str, ...] = tuple(t.key for t in LIBRARY if t.pinned)


def applies_to(pathways: list[Any] | tuple[Any, ...] | None, pathway: Pathway) -> bool:
    """A template's ``pathways`` names pathway keys or domains; empty = all."""
    if not pathways:
        return True
    tags = {str(p) for p in pathways}
    return "all" in tags or pathway.key in tags or pathway.domain in tags


def ensure_library(db: Session) -> int:
    """Upsert every library template by key. Wording, kinds and feeds follow
    the code; ``pinned``/``archived``/``usage_count`` are the clinician's and
    are left alone on an existing row. Returns the number of rows created."""
    existing = {
        t.key: t for t in db.scalars(select(TaskTemplate).where(TaskTemplate.key.is_not(None)))
    }
    created = 0
    for spec in LIBRARY:
        row = existing.get(spec.key)
        fields = dict(
            title=spec.title, why=spec.why, clinical_target=spec.clinical_target,
            task_kind=spec.task_kind or default_task_kind(spec.verify_kind),
            verify_kind=str(spec.verify_kind), params=params_for(spec.verify_kind, spec.params),
            schedule=spec.schedule, phase=spec.phase, feeds=list(spec.feeds),
            pathways=list(spec.pathways), use_case=spec.use_case, source="library",
            created_by="library",
        )
        if row is None:
            db.add(TaskTemplate(key=spec.key, pinned=spec.pinned, **fields))
            created += 1
        else:
            for name, value in fields.items():
                if getattr(row, name) != value:
                    setattr(row, name, value)
    db.commit()
    if created:
        logger.info("Task library: %d template(s) added", created)
    return created


def templates_for_pathway(
    db: Session, pathway: Pathway | None, *, include_archived: bool = False
) -> list[TaskTemplate]:
    rows = db.scalars(select(TaskTemplate).order_by(TaskTemplate.id)).all()
    return [
        t for t in rows
        if (include_archived or not t.archived)
        and (pathway is None or applies_to(t.pathways, pathway))
    ]


def pathways_payload() -> list[dict[str, str]]:
    return [{"key": p.key, "name": p.name, "domain": p.domain} for p in PATHWAYS.values()]


def template_payload(t: TaskTemplate) -> dict[str, Any]:
    from app.plan.verify_kinds import verified_by_label

    return {
        "id": t.id, "key": t.key, "title": t.title, "why": t.why,
        "clinical_target": t.clinical_target, "task_kind": t.task_kind,
        "verify_kind": t.verify_kind, "params": t.params or {}, "schedule": t.schedule,
        "phase": t.phase, "feeds": list(t.feeds or []), "pathways": list(t.pathways or []),
        "use_case": t.use_case, "source": t.source, "pinned": bool(t.pinned),
        "archived": bool(t.archived), "usage_count": int(t.usage_count or 0),
        "verified_by": verified_by_label(t.verify_kind),
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
