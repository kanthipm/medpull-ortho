"""The standard exercise library: the 30 common PT exercises from the HEP
spec (section 5A), until the pilot clinic's own list replaces or extends it.

Wording is patient-facing and plain. No dose lives here: sets, reps, holds
and frequency are the clinician's, set per plan. ``animation_priority``
orders the first demonstrations to be produced; every entry ships without
media and in ``draft`` until a PT has reviewed it.

``ensure_catalog`` upserts by key, so wording can evolve while a clinic's
usage counts and review status survive. ``CATALOG_VERSION`` is bumped on
every change to the list and recorded so the seed is traceable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.hep.models import BODY_REGIONS, CATEGORIES, Exercise

logger = logging.getLogger(__name__)

CATALOG_VERSION = 1


@dataclass(frozen=True)
class ExerciseSpec:
    key: str
    title: str
    body_region: str
    category: str
    synonyms: tuple[str, ...]
    instructions: tuple[str, ...]
    equipment: str = ""
    precautions: str = ""
    animation_priority: int | None = None  # 1..10 = first demonstration batch


def _e(key, title, region, category, synonyms, steps, equipment="", precautions="",
       priority=None) -> ExerciseSpec:
    return ExerciseSpec(key, title, region, category, tuple(synonyms), tuple(steps),
                        equipment, precautions, priority)


LYING = "Lie on your back on a bed or a firm mat."
STAND_SUPPORT = "Stand tall holding a counter or the back of a sturdy chair for balance."
STOP_RULE = "Stop if you feel sharp pain. Mild muscle effort is expected."

CATALOG: list[ExerciseSpec] = [
    # --- knee -------------------------------------------------------------------
    _e("knee_heel_slides", "Heel Slides", "knee", "mobility",
       ["heel slide", "knee flexion slide", "supine knee bend"],
       [LYING, "Slowly slide the heel of one leg toward your bottom, bending the knee as far as "
        "is comfortable.", "Hold briefly at the end of the movement.",
        "Slide the heel back down until the leg is straight."],
       precautions="Keep the heel on the surface. Do not force the bend.", priority=1),
    _e("knee_quad_sets", "Quad Sets", "knee", "strengthening",
       ["quad set", "quadriceps setting", "static quad", "knee press"],
       [LYING + " Keep the leg straight.", "Tighten the muscle on the front of your thigh "
        "and press the back of the knee down toward the surface.",
        "Hold the squeeze, then relax completely."],
       precautions=STOP_RULE, priority=2),
    _e("knee_straight_leg_raises", "Straight Leg Raises", "knee", "strengthening",
       ["SLR", "straight leg raise", "leg lift"],
       [LYING + " Bend the other knee so that foot is flat.", "Tighten the thigh of the "
        "straight leg and lift it to the height of the bent knee.",
        "Hold briefly, then lower slowly with control."],
       precautions="Keep the knee straight through the whole lift. Lower slowly.",
       priority=3),
    _e("knee_short_arc_quads", "Short Arc Quads", "knee", "strengthening",
       ["short arc quad", "SAQ", "terminal knee extension over a roll"],
       [LYING + " Place a rolled towel under the knee so it is slightly bent.",
        "Straighten the knee by lifting the foot, keeping the back of the knee on the towel.",
        "Hold briefly at the top, then lower slowly."],
       equipment="Rolled towel or small bolster", precautions=STOP_RULE, priority=4),
    _e("knee_long_arc_quads", "Long Arc Quads", "knee", "strengthening",
       ["long arc quad", "LAQ", "seated knee extension"],
       ["Sit on a chair with your back supported and feet hanging.",
        "Straighten one knee fully, lifting the foot until the leg is level.",
        "Hold briefly, then lower slowly."],
       precautions="Move through a comfortable range only."),
    _e("knee_terminal_extensions", "Terminal Knee Extensions", "knee", "strengthening",
       ["TKE", "terminal knee extension", "standing knee extension with band"],
       ["Loop a resistance band around a stable anchor and behind one knee.",
        "Stand facing the anchor with the band pulling the knee forward and the knee "
        "slightly bent.", "Straighten the knee against the band, squeezing the thigh.",
        "Return slowly."],
       equipment="Resistance band and an anchor point",
       precautions="Keep the movement small and controlled."),
    # --- hip --------------------------------------------------------------------
    _e("hip_glute_bridges", "Glute Bridges", "hip", "strengthening",
       ["bridge", "bridging", "hip bridge", "supine bridge"],
       [LYING + " Bend both knees so your feet are flat and hip-width apart.",
        "Squeeze your buttocks and lift your hips until they line up with your knees and "
        "shoulders.", "Hold briefly, then lower slowly."],
       precautions="Do not arch the lower back. Lift with the buttocks.", priority=5),
    _e("hip_clamshells", "Clamshells", "hip", "strengthening",
       ["clamshell", "clam", "side-lying hip external rotation"],
       ["Lie on your side with your knees bent and stacked, heels in line with your "
        "bottom.", "Keeping your feet together, lift the top knee like a clam opening.",
        "Keep your hips still and stacked.", "Lower slowly."],
       precautions="Do not let the pelvis roll backward.", priority=6),
    _e("hip_sidelying_abduction", "Side-Lying Hip Abduction", "hip", "strengthening",
       ["side leg raise", "side-lying leg lift", "hip abduction"],
       ["Lie on your side with the bottom knee bent for balance and the top leg straight.",
        "Lift the top leg toward the ceiling, keeping the toes pointing forward.",
        "Hold briefly, then lower slowly."],
       precautions="Keep the leg in line with the body, not forward.", priority=7),
    _e("hip_standing_extension", "Standing Hip Extension", "hip", "strengthening",
       ["hip extension", "standing leg back", "glute kickback"],
       [STAND_SUPPORT, "Keeping the knee straight and the body upright, move one leg "
        "straight back.", "Squeeze the buttock, hold briefly, then return."],
       precautions="Do not lean forward or arch the back."),
    _e("hip_standing_abduction", "Standing Hip Abduction", "hip", "strengthening",
       ["standing leg out to side", "hip abduction standing", "side leg lift standing"],
       [STAND_SUPPORT, "Keeping the knee straight and the toes forward, move one leg out "
        "to the side.", "Hold briefly, then return with control."],
       precautions="Keep the body upright. Do not swing the leg."),
    # --- ankle ------------------------------------------------------------------
    _e("ankle_pumps", "Ankle Pumps", "ankle", "mobility",
       ["ankle pump", "foot pumps", "calf pumps", "ankle dorsiflexion plantarflexion"],
       ["Sit or lie with your legs out in front of you.",
        "Point the toes away from you, then pull them back toward you.",
        "Repeat in a steady rhythm."],
       precautions="Move within a comfortable range.", priority=10),
    _e("ankle_circles", "Ankle Circles", "ankle", "mobility",
       ["ankle circle", "ankle rotations"],
       ["Sit or lie with the leg supported and the foot free.",
        "Draw slow circles with your toes, moving only the ankle.",
        "Change direction after each set."],
       precautions="Keep the movement smooth and pain free."),
    _e("ankle_calf_raises", "Calf Raises", "ankle", "strengthening",
       ["heel raise", "heel rise", "calf raise", "toe raise"],
       [STAND_SUPPORT, "Rise up onto the balls of both feet, lifting the heels.",
        "Hold briefly at the top, then lower slowly."],
       precautions="Use the support for balance, not to pull up."),
    _e("ankle_dorsiflexion_stretch", "Ankle Dorsiflexion Stretch", "ankle", "mobility",
       ["calf stretch", "wall calf stretch", "gastroc stretch", "ankle stretch"],
       ["Stand facing a wall with your hands on it.", "Step one foot back, keeping that "
        "heel down and the knee straight.", "Lean forward until you feel a stretch in the "
        "back of the lower leg.", "Hold, then relax."],
       equipment="A wall", precautions="Keep the back heel on the floor."),
    # --- functional -------------------------------------------------------------
    _e("functional_sit_to_stand", "Sit-to-Stand", "full_body", "functional",
       ["sit to stand", "chair stand", "chair rise", "STS"],
       ["Sit toward the front of a sturdy chair with feet flat and hip-width apart.",
        "Lean forward slightly and stand up, pushing through your heels.",
        "Sit back down slowly with control."],
       equipment="A sturdy chair",
       precautions="Use the armrests only if needed. Keep the knees over the feet.",
       priority=8),
    _e("functional_mini_squats", "Mini Squats", "full_body", "functional",
       ["mini squat", "partial squat", "quarter squat", "shallow squat"],
       [STAND_SUPPORT + " Feet hip-width apart.", "Bend the knees and hips a small amount, "
        "as if starting to sit.", "Keep the knees in line with the feet and the heels down.",
        "Return to standing."],
       precautions="Keep the squat shallow. Knees stay behind the toes.", priority=9),
    _e("functional_step_ups", "Step-Ups", "full_body", "functional",
       ["step up", "forward step up", "stair step"],
       ["Stand facing a low step, holding a rail if available.",
        "Step up with one foot, then bring the other foot up.",
        "Step down slowly, leading with the same foot each time."],
       equipment="A low step or bottom stair",
       precautions="Keep the knee over the foot. Use a rail for balance."),
    _e("functional_lateral_step_ups", "Lateral Step-Ups", "full_body", "functional",
       ["lateral step up", "side step up", "sideways step"],
       ["Stand beside a low step, holding a rail if available.",
        "Step up sideways with the foot nearest the step, then bring the other foot up.",
        "Step down slowly the same way."],
       equipment="A low step or bottom stair",
       precautions="Keep the knee over the foot. Do not push off the floor foot."),
    _e("functional_wall_sits", "Wall Sits", "full_body", "functional",
       ["wall sit", "wall squat hold", "wall slide squat"],
       ["Stand with your back against a wall and feet shoulder-width apart, a step out "
        "from the wall.", "Slide down the wall until the knees are comfortably bent.",
        "Hold with the back flat against the wall, then slide back up."],
       equipment="A wall", precautions="Keep the knees behind the toes. Breathe normally."),
    # --- balance ----------------------------------------------------------------
    _e("balance_single_leg_stance", "Single-Leg Stance", "full_body", "balance",
       ["single leg stand", "one leg balance", "SLS"],
       [STAND_SUPPORT, "Lift one foot off the floor and balance on the other.",
        "Hold, using the support as little as possible.", "Switch legs."],
       precautions="Stay near the support. Stop if you feel unsteady."),
    _e("balance_tandem_stance", "Tandem Stance", "full_body", "balance",
       ["heel to toe stand", "tandem stand", "heel-toe balance"],
       [STAND_SUPPORT, "Place one foot directly in front of the other, heel touching toe.",
        "Hold the position, then swap which foot is in front."],
       precautions="Stay near the support."),
    _e("balance_weight_shifts", "Weight Shifts", "full_body", "balance",
       ["weight shift", "side to side shift", "lateral weight shift"],
       [STAND_SUPPORT + " Feet hip-width apart.", "Slowly shift your weight onto one "
        "leg, then onto the other.", "Then shift forward onto the toes and back onto the heels."],
       precautions="Keep both feet on the floor."),
    # --- shoulder ---------------------------------------------------------------
    _e("shoulder_pendulum_swings", "Pendulum Swings", "shoulder", "mobility",
       ["pendulum", "Codman", "pendular exercise", "arm swings"],
       ["Lean forward with one hand on a table and let the other arm hang down.",
        "Let the arm swing gently forward and back, then side to side, then in small circles.",
        "Use your body to move the arm, keeping the shoulder relaxed."],
       equipment="A table or counter", precautions="Do not lift the arm with its own muscles."),
    _e("shoulder_wall_slides", "Wall Slides", "shoulder", "mobility",
       ["wall slide", "wall walk", "finger wall walk", "wall climb"],
       ["Stand facing a wall with your hand on it at shoulder height.",
        "Slide the hand up the wall as far as is comfortable, stepping closer if needed.",
        "Hold briefly, then slide back down."],
       equipment="A wall", precautions="Keep the shoulder down, away from the ear."),
    _e("shoulder_scapular_retractions", "Scapular Retractions", "shoulder", "strengthening",
       ["scapular squeeze", "shoulder blade squeeze", "scap retraction", "shoulder blade pinch"],
       ["Sit or stand tall with the arms relaxed.",
        "Squeeze the shoulder blades back and together, as if holding a pencil between them.",
        "Hold, then relax."],
       precautions="Keep the shoulders down. Do not shrug."),
    _e("shoulder_band_external_rotation", "Band External Rotation", "shoulder", "strengthening",
       ["external rotation", "ER with band", "rotator cuff band", "shoulder external rotation"],
       ["Hold a resistance band with both hands, elbows bent and tucked at your sides.",
        "Keeping the elbow in, rotate one forearm outward against the band.",
        "Return slowly."],
       equipment="Resistance band",
       precautions="Keep the elbow at your side. Keep the movement slow."),
    # --- back and core ----------------------------------------------------------
    _e("back_pelvic_tilts", "Pelvic Tilts", "back_core", "mobility",
       ["pelvic tilt", "posterior pelvic tilt", "flatten the back"],
       [LYING + " Bend both knees so your feet are flat.",
        "Tighten the stomach muscles and press the lower back into the surface.",
        "Hold, then relax."],
       precautions="Keep the movement gentle."),
    _e("back_cat_cow", "Cat-Cow", "back_core", "mobility",
       ["cat cow", "cat camel", "cat and cow", "spinal flexion extension"],
       ["Kneel on hands and knees with hands under the shoulders and knees under the hips.",
        "Round your back toward the ceiling, tucking the chin.",
        "Then let the back dip down gently, lifting the head.", "Move slowly between the two."],
       precautions="Move within a comfortable range. Keep the arms straight."),
    _e("back_bird_dog", "Bird Dog", "back_core", "strengthening",
       ["bird dog", "quadruped arm and leg raise", "opposite arm leg raise"],
       ["Kneel on hands and knees with a flat back.",
        "Reach one arm forward and the opposite leg back, keeping the hips level.",
        "Hold briefly, then return and switch sides."],
       precautions="Keep the back flat and still. Do not arch."),
]

BY_KEY: dict[str, ExerciseSpec] = {e.key: e for e in CATALOG}
FIRST_ANIMATIONS: tuple[str, ...] = tuple(
    e.key for e in sorted((e for e in CATALOG if e.animation_priority), key=lambda e: e.animation_priority)
)

assert len(CATALOG) == 30 and len(BY_KEY) == 30
assert all(e.body_region in BODY_REGIONS and e.category in CATEGORIES for e in CATALOG)


def ensure_catalog(db: Session) -> int:
    """Upsert the standard library by key. Wording, region, category,
    synonyms, equipment and precautions follow the code and bump the row's
    version when they change; ``status``, ``media_id`` and ``usage_count``
    are the clinic's and are left alone. Returns the number created."""
    existing = {
        e.key: e for e in db.scalars(select(Exercise).where(Exercise.key.is_not(None)))
    }
    created = 0
    for spec in CATALOG:
        fields = dict(
            title=spec.title, synonyms=list(spec.synonyms), body_region=spec.body_region,
            category=spec.category, instructions="\n".join(spec.instructions),
            equipment=spec.equipment, precautions=spec.precautions,
        )
        row = existing.get(spec.key)
        if row is None:
            db.add(Exercise(key=spec.key, origin="standard", hospital_id=None,
                            status="draft", created_by="library", **fields))
            created += 1
            continue
        changed = False
        for name, value in fields.items():
            if getattr(row, name) != value:
                setattr(row, name, value)
                changed = True
        if row.origin != "standard":
            row.origin = "standard"
        if changed:
            row.version = (row.version or 1) + 1
            from datetime import datetime

            row.updated_at = datetime.now()
    db.commit()
    if created:
        logger.info("HEP catalog v%d: %d exercise(s) added", CATALOG_VERSION, created)
    return created
